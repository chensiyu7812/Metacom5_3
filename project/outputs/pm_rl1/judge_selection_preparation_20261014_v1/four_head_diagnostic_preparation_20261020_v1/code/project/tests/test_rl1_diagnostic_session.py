from copy import deepcopy
import pytest
import torch
from test_rl1_diagnostic_scope import fixture, reviewed
from rl1_batch_fixtures import answer
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.diagnostic_scope import DiagnosticEpisode
from metacom_pm.rl1.diagnostic_session import DiagnosticSession
from metacom_pm.rl1.observation_features import make_actor_critic
from metacom_pm.rl1.schema import digest
from dataclasses import replace


def prepared(tmp_path):
    enc, p, a, reviews, build = fixture()
    src = {x.trajectory_id:x for x in build()}
    manifest = deepcopy(p["trajectory_manifest"])
    phases = {}
    for phase in ("initial_dev", "post_dev"):
        phases[phase] = []
        for i, condition in enumerate(("policy", "FixedRS1") if phase == "initial_dev" else ("policy",)):
            t = f"{phase}-{i}"
            base = next(iter(src.values()))
            spec = replace(base.spec, prefix=replace(base.spec.prefix, split="dev"))
            src[t] = type("SpecHolder", (), dict(spec=spec, renderer=base.renderer, evidence=base.evidence))()
            manifest[t] = dict(prefix_identity=spec.prefix.identity, split="dev",
                               evidence_identity=digest(base.evidence), condition=condition)
            phases[phase].append(t)
    p.pop("identity")
    p = stamp(dict(p, run_dir=str(tmp_path.resolve()), trajectory_manifest=manifest, dev_phases=phases))
    a["protocol_identity"] = p["identity"]
    def build_new(t):
        x = src[t]
        return DiagnosticEpisode(x.spec, x.renderer, evidence=x.evidence, protocol=p,
            approval=a, trajectory_id=t, review_lookup=reviews.get)
    def make():
        torch.manual_seed(17)
        return DiagnosticSession(p, a, tmp_path, make_actor_critic(enc.feature_dimension), enc, build_new)
    return make, reviews


def test_session_four_phases_resume_and_never_train_on_dev(tmp_path):
    torch.set_num_threads(1)
    make, reviews = prepared(tmp_path)
    session = make()
    calls = []
    def provider(job):
        calls.append(job["id"])
        rec = answer(job)
        if job["kind"] == "measurement":
            reviews[digest(rec)] = reviewed(rec, True)
        return rec
    for _ in range(32):
        session.advance()
        if session.phase == "complete":
            break
        session.worker(dict(generation=provider, measurement=provider))
        session = make()  # Every phase/poll is restartable without new sampling.
    assert session.phase == "complete"
    assert session.batch.trainer.version == 2
    assert len(calls) == len(set(calls))
    assert len(list((tmp_path / "updates").glob("*.update_done.json"))) == 2
    assert session.status()["reward_qualified"] is False
    assert len(session.protocol["train_batches"][0] + session.protocol["train_batches"][1]) == 32


def test_unfinished_transition_fails_closed(tmp_path):
    make, _ = prepared(tmp_path)
    session = make()
    session._commit("interrupted_before_sampling")
    with pytest.raises(ValueError, match="unfinished transition"):
        make()


def test_model_unknown_is_preserved_and_never_updates(tmp_path):
    make, reviews = prepared(tmp_path)
    session = make()
    for _ in range(5):
        session.advance()
        def provider(job):
            return answer(job, "semantic_uncertainty") if job["kind"] == "measurement" else answer(job)
        session.worker(dict(generation=provider, measurement=provider))
        if session.status()["stopped"]:
            break
    assert session.status()["stopped"] and session.batch.trainer.version == 0
    assert any(x["original_q"] is None for x in session.status()["feedback_records"])


def test_started_worker_is_not_retried(tmp_path):
    make, _ = prepared(tmp_path)
    s = make()
    s.advance()
    job = s.queue.claim_next()
    assert job is not None
    def forbidden(_):
        raise AssertionError("must never redispatch")
    s.worker(dict(generation=forbidden, measurement=forbidden))
    assert s.status()["stopped"]
