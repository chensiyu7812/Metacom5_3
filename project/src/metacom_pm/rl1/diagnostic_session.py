"""A bounded natural-data diagnostic, composed from the existing batch bridge.

Providers and a source-review lookup are injected. This module never loads a
model, opens credentials, invents feedback, or grants measurement qualification.
An interrupted transition is retained and blocks replay rather than resampling.
"""
from copy import deepcopy
from pathlib import Path
import json
import os

import torch

from .diagnostic_scope import DIAGNOSTIC, require_approval
from .natural_batch import PendingBatch, FeedbackQueue, parameter_identity
from .schema import digest


def read(path):
    return json.loads(Path(path).read_text())


def save_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if digest(read(path)) != digest(value):
            raise ValueError("immutable diagnostic artifact changed")
        return
    with path.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    path.chmod(0o600)


class DiagnosticSession:
    """Four phases: initial dev, two fresh on-policy batches, final dev.

    ``advance`` never dispatches a provider request itself. It returns pending
    work or review needs. ``worker`` uses the durable queue exactly once per
    claim. Reviews are coordinator evidence audits, not independent human labels.
    """
    phases = ("initial_dev", "train_0", "train_1", "post_dev", "complete")

    def __init__(self, protocol, approval, root, model, encoder, make_episode):
        require_approval(protocol, approval)
        if str(Path(root).resolve()) != protocol["run_dir"]:
            raise ValueError("one locked run directory; no cloned training run")
        self.protocol, self.approval = deepcopy(protocol), deepcopy(approval)
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.queue = FeedbackQueue(self.root / "feedback.sqlite")
        self.batch = PendingBatch(model, encoder, self.root / "updates",
                                  mode=DIAGNOSTIC, protocol=protocol, approval=approval)
        self.make_episode = make_episode
        self.phase, self.sequence, self.dev = "initial_dev", 0, []
        save_once(self.root / "protocol.json", protocol)
        save_once(self.root / "approval.json", approval)
        self._restore_latest()

    def _restore_latest(self):
        intents = sorted(self.root.glob("transition_*.intent.json"))
        for path in intents:
            if not path.with_name(path.name.replace(".intent", ".done")).exists():
                raise ValueError("unfinished transition retained; no automatic replay")
        if not intents:
            return
        done = read(intents[-1].with_name(intents[-1].name.replace(".intent", ".done")))
        self.sequence, self.phase = done["sequence"], done["phase"]
        if done["protocol_identity"] != self.protocol["identity"]:
            raise ValueError("session protocol changed")
        checkpoint = self.root / done["checkpoint"]
        import hashlib
        if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != done["checkpoint_sha256"]:
            raise ValueError("checkpoint changed")
        es = [self.make_episode(t) for t in done["batch_trajectories"]]
        self.batch.restore(checkpoint, es)
        self.dev = []
        for row in done["dev"]:
            e = self.make_episode(row["trajectory_id"])
            e.restore(row["snapshot"])
            self.dev.append(e)

    def _commit(self, operation):
        """Durable intent precedes sampling or an optimizer event."""
        require_approval(self.protocol, self.approval)
        self.sequence += 1
        name = f"transition_{self.sequence:04d}"
        intent = self.root / (name + ".intent.json")
        if intent.exists():
            raise ValueError("transition already started")
        save_once(intent, dict(sequence=self.sequence, phase=self.phase, operation=operation,
                               protocol_identity=self.protocol["identity"]))
        return name

    def _finish(self, name):
        import hashlib
        checkpoint = self.root / (name + ".pt")
        self.batch.save(checkpoint)
        save_once(self.root / (name + ".done.json"), dict(sequence=self.sequence,
            phase=self.phase, protocol_identity=self.protocol["identity"],
            checkpoint=checkpoint.name,
            checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            batch_trajectories=[r["episode"].trajectory_id for r in self.batch.records],
            current_results=[e.result() for e in self.dev] +
                [r["episode"].result() for r in self.batch.records],
            dev=[dict(trajectory_id=e.trajectory_id, snapshot=e.snapshot()) for e in self.dev]))

    def _dev_policy(self, trajectory_id):
        item = self.protocol["trajectory_manifest"][trajectory_id]
        if item["condition"] == "FixedRS1":
            def fixed(o):
                if o.counts == (0, 0, 0, 0):
                    if not o.action_mask[1]:
                        raise ValueError("preselected FixedRS1 became unreachable")
                    return 1
                return 0
            return fixed
        def greedy(observation):
            f = self.batch.encoder.encode(observation)
            with torch.no_grad():
                dist, _ = self.batch.model(torch.tensor(f.values, dtype=torch.float32),
                                          torch.tensor(f.action_mask, dtype=torch.bool))
                return int(dist.probs.argmax())
        return greedy

    def advance(self):
        if (self.root / "STOP.json").exists() or self.phase == "complete":
            return self.status()
        name = self._commit("advance")
        if self.phase in ("initial_dev", "post_dev"):
            if not self.dev:
                for tid in self.protocol["dev_phases"][self.phase]:
                    e = self.make_episode(tid)
                    e.acquire(self._dev_policy(tid))
                    self.dev.append(e)
            results = [e.advance(self.queue.generate, self.queue.measure) for e in self.dev]
        else:
            batch_index = int(self.phase[-1])
            if self.batch.consumed:
                self.batch.next_batch()
            if self.batch.batch_id is None:
                self.batch.collect([self.make_episode(t) for t in
                    self.protocol["train_batches"][batch_index]], batch_id=self.phase)
            results = self.batch.poll(self.queue)
        es = self.dev if self.phase in ("initial_dev", "post_dev") else [
            r["episode"] for r in self.batch.records]
        blocked = [v for e in es for v in e.feedback_diagnostics.values()
                   if v["disposition"] in ("stop_stage", "stop_before_update", "pending_stop_stage")]
        if blocked or any(r["phase"] == "technical_failure" for r in results):
            save_once(self.root / "STOP.json", dict(phase=self.phase,
                reason="technical_failure_or_model_unknown_or_confirmed_checking_error",
                diagnostic_records=blocked, old_stops_released=False,
                failed_results=[r for r in results if r["phase"] == "technical_failure"]))
        elif all(r["phase"] == "terminal" for r in results):
            # Even terminal dev results are rechecked before being accepted.
            for e in es:
                e.require_update_feedback()
            save_once(self.root / (self.phase + ".results.json"), results)
            if self.phase.startswith("train"):
                receipt = self.batch.update_once()
                save_once(self.root / (self.phase + ".update.json"), receipt)
            self.phase = self.phases[self.phases.index(self.phase) + 1]
            self.dev = []
        self._finish(name)
        return self.status()

    def worker(self, providers):
        """Drain only currently queued work; STARTED never gets claimed again."""
        require_approval(self.protocol, self.approval)
        if (self.root / "STOP.json").exists():
            return self.status()
        with self.queue.transaction() as db:
            unresolved = db.execute("SELECT COUNT(*) FROM feedback WHERE state='STARTED'").fetchone()[0]
        if unresolved:
            save_once(self.root / "STOP.json", dict(reason="interrupted started request; no retry"))
            return self.status()
        while (job := self.queue.claim_next()) is not None:
            result = providers[job["kind"]](job)
            self.queue.settle(job["id"], result)
            if ((job["kind"] == "generation" and result["finish_reason"] != "natural_stop")
                    or (job["kind"] == "measurement" and
                        result["measurement_status"] != "measured_candidate")):
                save_once(self.root / "STOP.json", dict(reason="provider_failure_or_model_unknown",
                    queue_id=job["id"], original_result=result))
                break
        return self.status()

    def status(self):
        reviews = []
        with self.queue.transaction() as db:
            for key, raw in db.execute(
                    "SELECT id,result FROM feedback WHERE kind='measurement' AND state='SETTLED'"):
                r = json.loads(raw)
                reviews.append(dict(queue_id=key, record_identity=digest(r),
                    model_status=r["measurement_status"], original_q=r.get("q"), original_m=r.get("m")))
        return dict(scope=DIAGNOSTIC, protocol_identity=self.protocol["identity"],
            phase=self.phase, sequence=self.sequence, policy_version=self.batch.trainer.version,
            parameter_identity=parameter_identity(self.batch.model), queue=self.queue.counts(),
            feedback_records=reviews, stopped=(self.root / "STOP.json").exists(),
            reward_qualified=False, full_research_complete=False)
