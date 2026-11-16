#!/usr/bin/env python3
"""Prepared adapter: existing G, BGE, paired.run, ledger and PPO. Offline by default."""
from contextlib import ExitStack
from dataclasses import asdict
from decimal import Decimal
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
BASE = PROJECT / "outputs/pm_rl1/judge_selection_preparation_20261014_v1"
PREP = BASE / "four_head_diagnostic_preparation_20261020_v1"


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def check():
    from metacom_pm.rl1.diagnostic_session import read
    from metacom_pm.rl1.calibration_workflow import verify_identity
    p = read(PREP / "protocol.json")
    verify_identity(p)
    for path, expected in p["immutable_files"].items():
        if sha(path) != expected:
            raise ValueError("prepared code or input changed")
    for path, expected in p["old_stop_hashes"].items():
        if sha(path) != expected:
            raise ValueError("old STOP changed")
    for path, expected in p["historical_started_hashes"].items():
        if sha(path) != expected:
            raise ValueError("historical attempt changed")
    old = [x for name in ("live_runs", "paired_diagnostic_runs", "action_stage_runs",
                          "reward_noise_runs", "anchor_calibration_runs")
           for x in (BASE / name).rglob("*.started.json") if "management" not in x.parts]
    if set(map(str, old)) != set(p["historical_started_hashes"]):
        raise ValueError("new historical attempt exists; do not reset count")
    root = Path(p["run_dir"])
    if any(not x.is_relative_to(root) for x in (BASE / "four_head_diagnostic_runs").rglob("*.started.json")):
        raise ValueError("another diagnostic version has started; reconcile across versions")
    return p


def report(protocol):
    """Read-only audit, usable before execution or while reviews are pending."""
    import sqlite3
    from metacom_pm.rl1.diagnostic_session import read
    from metacom_pm.rl1.diagnostic_scope import feedback_disposition
    from metacom_pm.rl1.diagnostic_analysis import summarize_results
    from metacom_pm.rl1.schema import digest
    root = Path(protocol["run_dir"])
    records, latest = [], {}
    for p in sorted(root.glob("transition_*.done.json")):
        for r in read(p).get("current_results", []):
            latest[r["trajectory_id"]] = r
    for p in root.glob("*.results.json"):
        for r in read(p):
            latest[r["trajectory_id"]] = r
    if (root / "feedback.sqlite").exists():
        with sqlite3.connect(f"file:{root / 'feedback.sqlite'}?mode=ro", uri=True) as db:
            for (raw,) in db.execute("SELECT result FROM feedback WHERE kind='measurement' AND state='SETTLED'"):
                r = json.loads(raw)
                review = root / "coordinator_reviews" / (digest(r) + ".json")
                review = read(review) if review.exists() else None
                records.append(dict(record=r, review=review, disposition=feedback_disposition(r, review)))
    result = summarize_results(protocol, {"latest":list(latest.values())}, records)
    js = [read(p) for p in (root / "measurements").rglob("*.result.json")]
    gs = [read(p) for p in (root / "new_generations").glob("*.raw.json")]
    result.update(actual_new_judge_attempts=len(list((root / "measurements").rglob("*.started.json"))),
        actual_new_generation_attempts=len(list((root / "new_generations").glob("*.started.json"))),
        judge_seconds=sum(x["elapsed_seconds"] for x in js),
        generation_seconds=sum(x.get("generation_seconds", 0) for x in gs),
        settled_accounted_usd=str(sum((Decimal(x["financial"]["accounted_upper_usd"] or "0") for x in js),Decimal(0))),
        raw_usage_records=[x["usage"] for x in js],
        financial_reconciliation_required=True,
        stop=read(root / "STOP.json") if (root / "STOP.json").exists() else None)
    # An incomplete model entry may have no result. Ledger liability remains
    # authoritative; never claim zero unsettled from the result subset.
    return result


class LocalProviders:
    """One designated GPU; lazy load, exact cache reuse, no download or fallback."""
    def __init__(self, protocol, data, renderer, run):
        self.protocol, self.data, self.renderer, self.run = protocol, data, renderer, run
        self.generator, self.bge, self.gpu_check = None, None, None
        self.guard_dir = None

    def ensure_gpu(self):
        if self.generator is not None:
            self.assert_idle_others()
            return
        import subprocess
        from metacom_pm.rl1.diagnostic_session import save_once
        from metacom_pm.rl1.schema import digest
        sys.path.insert(0, str(BASE))
        from resume_engineering import GPUChecks
        r = self.protocol["executor_runtime"]
        if (os.environ.get("CUDA_VISIBLE_DEVICES") != r["cuda_visible_devices"]
                or os.environ.get("CUDA_DEVICE_ORDER") != r["cuda_device_order"]):
            raise ValueError("frozen CUDA deployment changed")
        if len(list((self.run / "gpu_checks").glob("*/device_mapping.json"))) >= self.protocol["limits"]["max_gpu_loads"]:
            raise ValueError("approved GPU load count exhausted")
        self.guard_dir = self.run / "gpu_checks" / str(time.time_ns())
        self.guard_dir.mkdir(parents=True, mode=0o700)
        mapping = subprocess.run(["nvidia-smi", "--query-gpu=pci.bus_id,uuid", "--format=csv,noheader"],
                                 capture_output=True, text=True, timeout=20)
        save_once(self.guard_dir / "device_mapping.json", dict(returncode=mapping.returncode,
                    stdout=mapping.stdout, stderr=mapping.stderr, time=time.time()))
        rows = sorted([x.strip() for x in line.split(",")] for line in mapping.stdout.splitlines())
        ordinal = int(r["cuda_visible_devices"])
        if mapping.returncode or len(rows) <= ordinal or rows[ordinal][1] != self.protocol["approval_scope"]["gpu_uuid"]:
            raise ValueError("GPU ordinal/UUID mismatch")
        self.gpu_check = GPUChecks(self.guard_dir)
        if not self.gpu_check.wait_idle(seconds=self.protocol["limits"]["idle_wait_seconds_per_load"])["eligible"]:
            raise ValueError("GPU original idle/process guard blocked")
        for name, expected in r["model_files"].items():
            if sha(Path(r["model_dir"]) / name) != expected:
                raise ValueError("local weights changed; no download")
        for name, expected in r["adapter"]["files"].items():
            if sha(Path(r["adapter"]["path"]) / name) != expected:
                raise ValueError("local adapter changed")
        # Existing vendor, not an install or alternate dependency version.
        sys.path.insert(0, "/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929")
        loader = import_file("rl1_p2_loader", PROJECT / "scripts/rl1/92_run_p2_common_pool.py")
        self.generator = loader.load_frozen_generator(r)
        if digest(dict(self.generator.manifest, identity=self.generator.identity)) != digest(r):
            raise ValueError("live generator identity changed")
        save_once(self.guard_dir / "generator_runtime.json", dict(
            self.generator.manifest, identity=self.generator.identity))

    def assert_idle_others(self):
        if not self.gpu_check.check(own_pid=os.getpid())["eligible"]:
            raise ValueError("another or invisible GPU process; do not operate on it")

    def encode(self, texts):
        import torch
        # GPU loaders may seed torch internally. They cannot perturb the CPU
        # policy sampling stream retained in the on-policy checkpoint.
        with torch.random.fork_rng(devices=[]):
            return self._encode(texts)

    def _encode(self, texts):
        self.ensure_gpu()  # Load G before BGE, preserving G's >=40GiB load guard.
        from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Encoder
        from metacom_pm.rl1.schema import digest
        if self.bge is None:
            self.bge = BgeM3Encoder()
            actual = asdict(self.bge.runtime_identity)
            if actual != self.protocol["bge_expected_runtime"]:
                raise ValueError("live BGE identity differs from prepared expected runtime")
            if digest(dict(binding=asdict(self.bge.binding), runtime=actual)) != self.protocol["text_encoder_identity"]:
                raise ValueError("BGE feature binding changed")
        self.assert_idle_others()
        return self.bge.encode(texts)

    def generate(self, job):
        import torch
        with torch.random.fork_rng(devices=[]):
            return self._generate(job)

    def _generate(self, job):
        from metacom_pm.rl1.diagnostic_session import read, save_once
        from metacom_pm.rl1.schema import digest
        req = job["payload"]
        cache = self.data["generation_cache"].get(req["request_id"])
        if cache:
            if (sha(cache["request_path"]) != cache["request_sha256"]
                    or sha(cache["raw_path"]) != cache["raw_sha256"] or read(cache["request_path"]) != req):
                raise ValueError("generation cache mismatch")
            result = read(cache["raw_path"])
            save_once(self.run / "generation_reuse" / (job["id"] + ".json"),
                      dict(queue_id=job["id"], **cache))
            return result
        self.ensure_gpu()
        out = self.run / "new_generations"
        out.mkdir(exist_ok=True)
        if len(list(out.glob("*.started.json"))) >= self.protocol["limits"]["new_generations"]:
            raise ValueError("new generation cap")
        if (out / (job["id"] + ".started.json")).exists():
            raise ValueError("generation already started; no retry")
        self.assert_idle_others()
        save_once(out / (job["id"] + ".started.json"), dict(time=time.time(),
            request_id=req["request_id"], protocol_identity=self.protocol["identity"]))
        save_once(out / (job["id"] + ".request.json"), req)
        result = self.generator.generate(req)
        save_once(out / (job["id"] + ".raw.json"), result)
        if result["source_provenance_identity"] != digest(req["provenance"]):
            raise ValueError("generation source binding changed")
        return result


class PaidProvider:
    """Use paired.run for each dynamically selected, identity-bound terminal."""
    def __init__(self, protocol, approval, run, stack):
        from metacom_pm.rl1.diagnostic_session import read, save_once
        sys.path.insert(0, str(BASE / "paired_diagnostic_20261019_v1"))
        import paired as p
        from deepseek_access import read_key, credential_scope, management_once, visible_paid_writers
        from live import public_service_check
        from adapters import DeepSeekTransport
        self.p, self.s, self.protocol, self.approval, self.run = p, p.s, protocol, approval, run
        self.visible_paid_writers = visible_paid_writers
        self.prompt = read(PREP / "joint_system_prompt.json")["content"]
        ledger = Path(protocol["financial_baseline"]["ledger_path"])
        baseline = protocol["financial_baseline"]
        original = ledger.read_bytes()[:baseline["ledger_bytes"]]
        if hashlib.sha256(original).hexdigest() != baseline["ledger_sha256"]:
            raise ValueError("shared ledger historical prefix changed")
        self.ledger, self.original = ledger, original
        self.guard()
        management = run / "management"
        preflight = management / "preflight.json"
        management.mkdir(exist_ok=True)
        # No retries for account requests either; interrupted preflight remains blocked.
        key = read_key()
        stack.enter_context(credential_scope(key))
        if not preflight.exists():
            if list(management.iterdir()):
                raise ValueError("account preflight previously started; no retry")
            public_service_check(management, protocol["public_price_table_identity"])
            models = management_once(management, "models", key)
            if models["status"] != 200:
                raise ValueError("model-list query failed")
            model = next((m for m in models.get("body", {}).get("data", []) if m.get("id") == "deepseek-flash"), {})
            if (not model or ("name" in model and model["name"] not in
                    ("DeepSeek-V4.1-Flash", "DeepSeek-V4.1-Flash-1017")) or
                    ("context_window" in model and model["context_window"] != 1048576) or
                    ("max_output_tokens" in model and model["max_output_tokens"] != 393216)):
                raise ValueError("service identity/capability drift")
            bal = management_once(management, "user/balance", key)
            if bal["status"] != 200 or not bal.get("body", {}).get("is_available"):
                raise ValueError("balance unavailable")
            amounts = {x["currency"]:Decimal(x["total_balance"]) for x in bal["body"]["balance_infos"]}
            available = amounts.get("USD", Decimal(0)) + amounts.get("CNY", Decimal(0))*Decimal(".15")
            save_once(preflight, dict(service=model, available_tariff_equivalent_usd=str(available),
                basis="existing official USD/CNY tariff ratio, not FX", time=time.time(),
                protocol_identity=protocol["identity"], approval_identity=self.s.digest(approval),
                account_visibility="known ledger and visible writers; not guaranteed account-wide visibility"))
        prior = read(preflight)
        if prior["protocol_identity"] != protocol["identity"] or prior["approval_identity"] != self.s.digest(approval):
            raise ValueError("preflight binding changed")
        limits = protocol["limits"]
        self.budget = p.DiagnosticBudget(ledger, trial=baseline["financial_trial_identity"],
            study=protocol["version"], stage_cap=self.s.nanodollars(limits["stage_usd"]),
            trial_cap=self.s.nanodollars(limits["trial_usd"]),
            shared_cap=self.s.nanodollars(Decimal(limits["shared_usd"]) -
                                         Decimal(limits["final_evaluation_planning_hold_usd"])),
            baseline=self.s.nanodollars("1.50724291"), opening=self.s.nanodollars(".03079930"),
            account_opening=self.s.nanodollars(prior["available_tariff_equivalent_usd"]),
            opening_trial=self.s.nanodollars(baseline["trial_accounted_usd"]))
        _, _, reserved, settled = self.budget._totals(self.budget.events())
        if set(reserved) - set(settled):
            raise ValueError("unresolved responsibility retained; no more dispatch")
        self.transport = DeepSeekTransport(protocol["config"])
        del key

    def guard(self):
        check()
        if self.visible_paid_writers():
            raise ValueError("visible concurrent paid writer")
        current = self.ledger.read_bytes()
        if not current.startswith(self.original):
            raise ValueError("shared history changed")
        events = [json.loads(line) for line in current[len(self.original):].decode().splitlines()]
        allowed = {e["reservation_id"] for e in events if e.get("event") == "RESERVED"
                   and e.get("stage") == self.protocol["version"]
                   and e.get("binding", {}).get("study") == self.protocol["version"]}
        for event in events:
            if event.get("reservation_id") not in allowed or event.get("event") not in ("RESERVED", "SETTLED"):
                raise ValueError("foreign paid writer since bound baseline; recheck funds")

    def __call__(self, job):
        from metacom_pm.rl1.diagnostic_session import read, save_once
        from metacom_pm.rl1.diagnostic_scope import require_approval
        from metacom_pm.rl1.schema import digest
        p, s = self.p, self.s
        self.guard()
        binding = job["payload"]["binding"]
        if (job["id"] != digest(dict(kind="measurement", payload=job["payload"]))
                or binding["response_identity"] != digest(job["payload"]["reply"])
                or binding["evidence_identity"] != digest(job["payload"]["evidence"])
                or binding["freeze_identity"] != self.protocol["identity"]
                or binding["runtime_identity"] != self.protocol["measurement_identity"]
                or binding["rubric_identity"] != self.protocol["rubric_identity"]
                or binding["evidence_identity"] not in
                    {x["evidence_identity"] for x in self.protocol["trajectory_manifest"].values()}):
            raise ValueError("outbound reply/source/protocol binding mismatch")
        import sqlite3
        with sqlite3.connect(f"file:{self.run / 'feedback.sqlite'}?mode=ro", uri=True) as db:
            generation = [json.loads(row[0]) for row in db.execute(
                "SELECT result FROM feedback WHERE kind='generation' AND state='SETTLED'")]
        matches = [x for x in generation if x["request_id"] == binding["generation_request_id"]]
        if (len(matches) != 1 or matches[0]["finish_reason"] != "natural_stop"
                or matches[0]["text"] != job["payload"]["reply"]
                or matches[0]["runtime_identity"] != self.protocol["executor_identity"]):
            raise ValueError("only a complete source-bound generator output may be scored")
        root = self.run / "measurements" / job["id"]
        starts = list((self.run / "measurements").rglob("*.started.json"))
        if len(starts) >= self.protocol["limits"]["judge_calls"]:
            raise ValueError("80-call diagnostic cap")
        slot = dict(slot_id=job["id"], component="joint", item_key=job["id"], position=len(starts)+1)
        sub = dict(config=self.protocol["config"], schedule=[slot], parent_protocol=self.protocol["identity"])
        sub["identity"] = digest(sub)
        item = dict(evidence=job["payload"]["evidence"], reply=job["payload"]["reply"])
        def payload(x, component, first=None):
            messages, schema = p.payload(x, component, first)
            messages[0]["content"] = self.prompt
            return messages, schema
        def approve(subprotocol, auth):
            require_approval(self.protocol, auth)
            if subprotocol != sub:
                raise ValueError("dynamic subrequest identity mismatch")
        def failure_policy(pr, st, results):
            for sid in st:
                row = results.get(sid)
                if row is None:
                    return "started request incomplete", 0, {}
                if row.get("hard_stop") or not row["technical_valid"] or row["evaluation"].get("model_unknown"):
                    return "technical failure, model unknown or integrity failure", 0, {}
            return None, 0, {}
        def summary(pr, out, baseline):
            _, rs = p.replay(out, pr)
            return rs
        def before():
            self.guard()
            fingerprints = {read(x).get("fingerprint") for x in
                            (self.run / "measurements").rglob("*.result.json")}
            fingerprints.discard(None)
            if len(fingerprints) > 1:
                raise ValueError("service fingerprint drift")
        rows = p.run(sub, {job["id"]:item}, root, self.transport, self.budget, mode="live",
            auth=self.approval, before_dispatch=before,
            global_count=lambda:225+len([x for x in (self.run / "measurements").rglob("*.started.json")
                                        if x.parent != root]),
            runtime=dict(max_calls=1, cap=self.protocol["limits"]["cumulative"],
                study=self.protocol["version"], version=self.protocol["version"],
                approve=approve, payload=payload, streaks=failure_policy, summarize=summary,
                semantic_revisions_applied=2, joint_prompt_unchanged=True))
        row = rows.get(job["id"])
        if row is None:
            raise ValueError("pre-dispatch stop; queue claim retained and not retried")
        fp = row.get("fingerprint")
        older = {read(x).get("fingerprint") for x in (self.run / "measurements").rglob("*.result.json")
                 if x.parent != root}
        older.discard(None)
        drift = bool(older and fp and older != {fp})
        ev = row["evaluation"]
        valid = row["technical_valid"] and not drift
        status = "technical_failure" if not valid else (
            "semantic_uncertainty" if ev.get("model_unknown") else "measured_candidate")
        return dict(binding=job["payload"]["binding"], measurement_status=status,
            q=ev.get("q") if status == "measured_candidate" else None,
            m=ev.get("m") if status == "measured_candidate" else None,
            original_result_path=str(root / (job["id"] + ".result.json")),
            original_result_sha256=sha(root / (job["id"] + ".result.json")),
            final_response_path=str(root / (job["id"] + ".response.json")),
            service_fingerprint_drift=drift, reward_qualified=False)


class PaidProcess:
    """Private local IPC to the already installed judge environment; no new service.

    The parent retains the shared locks. The child owns process-only credentials.
    Neither authentication headers nor provider exceptions enter the IPC stream.
    """
    def __init__(self, protocol, approval_path, lock_fd):
        import subprocess
        self.timeout = protocol["config"]["timeout_seconds"] + 120
        env = dict(os.environ, CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        # Do not import the generator vendor into the different judge interpreter.
        env["PYTHONPATH"] = str(PROJECT / "src")
        self.child = subprocess.Popen([protocol["judge_python"], str(Path(__file__).resolve()),
            "--paid-worker", "--approval", str(approval_path), "--parent-lock-fd", str(lock_fd)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, env=env, pass_fds=(lock_fd,))
        try:
            if self._read(90).get("state") != "ready":
                raise ValueError("judge subprocess preflight failed; no retry")
        except BaseException:
            self.close()
            raise

    def _read(self, timeout):
        import selectors
        with selectors.DefaultSelector() as selector:
            selector.register(self.child.stdout, selectors.EVENT_READ)
            if not selector.select(timeout):
                raise ValueError("judge worker unresponsive; preserve responsibility; no retry")
            line = self.child.stdout.readline()
        if not line:
            raise ValueError("judge worker exited; no automatic retry")
        value = json.loads(line)
        if value.get("state") == "error":
            raise ValueError("judge worker stopped; local receipt retained")
        return value

    def __call__(self, job):
        self.child.stdin.write(json.dumps(dict(command="measure", job=job), ensure_ascii=False) + "\n")
        self.child.stdin.flush()
        row = self._read(self.timeout)
        if row.get("queue_id") != job["id"]:
            raise ValueError("judge IPC response identity mismatch")
        return row["record"]

    def close(self):
        import subprocess
        if self.child.poll() is None:
            try:
                self.child.stdin.close()
                self.child.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                # Only this runner's own child, never another user's process.
                self.child.terminate()
                self.child.wait(timeout=5)


def paid_worker(protocol, approval, lock_fd):
    from metacom_pm.rl1.diagnostic_scope import require_approval
    from metacom_pm.rl1.diagnostic_session import read, save_once
    require_approval(protocol, approval)
    root = Path(protocol["run_dir"])
    # An inherited, already held descriptor is mandatory; direct invocation is
    # not a second paid entry point outside the parent/shared locks.
    if lock_fd is None or os.fstat(lock_fd).st_ino != (root / ".execution.lock").stat().st_ino:
        raise ValueError("paid worker requires the parent's locked session")
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if Path(sys.executable).resolve() != Path(protocol["judge_python"]).resolve():
        raise ValueError("wrong existing judge interpreter")
    import importlib.metadata
    if {k:importlib.metadata.version(k) for k in protocol["judge_packages"]} != protocol["judge_packages"]:
        raise ValueError("judge environment changed; no installs")
    try:
        with ExitStack() as stack:
            provider = PaidProvider(protocol, approval, root, stack)
            print(json.dumps(dict(state="ready")), flush=True)
            for line in sys.stdin:
                message = json.loads(line)
                if message.get("command") != "measure":
                    raise ValueError("unknown worker command")
                job = message["job"]
                # The parent must already have durably claimed this exact job.
                import sqlite3
                with sqlite3.connect(f"file:{root / 'feedback.sqlite'}?mode=ro", uri=True) as db:
                    bound = db.execute("SELECT kind,payload,state FROM feedback WHERE id=?", (job["id"],)).fetchone()
                if not bound or bound[0] != "measurement" or bound[2] != "STARTED" or json.loads(bound[1]) != job["payload"]:
                    raise ValueError("worker job is not the parent's started queue item")
                print(json.dumps(dict(queue_id=job["id"], record=provider(job)), ensure_ascii=False), flush=True)
    except BaseException as exc:
        save_once(root / ("worker_failure_" + str(time.time_ns()) + ".json"),
                  dict(exception_type=type(exc).__name__, details_suppressed=True, retries=0))
        print(json.dumps(dict(state="error", detail="retained local failure; no retry")), flush=True)


def advance(protocol, approval):
    from metacom_pm.rl1.diagnostic_scope import require_approval, DiagnosticEpisode
    require_approval(protocol, approval)  # Before run directory, credentials, GPU, HTTP.
    import importlib.metadata
    if Path(sys.executable).resolve() != Path(protocol["generator_python"]).resolve():
        raise ValueError("use original generator interpreter; no environment substitution")
    r = protocol["executor_runtime"]
    if ({k:importlib.metadata.version(k) for k in r["packages"]} != r["packages"]
            or importlib.metadata.version("peft") != r["adapter"]["peft_version"]):
        raise ValueError("use the existing generator environment and original SFT vendor")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = r["cuda_visible_devices"]
    os.environ["CUDA_DEVICE_ORDER"] = r["cuda_device_order"]
    import torch
    from transformers import AutoTokenizer
    from metacom_pm.rl1.diagnostic_session import DiagnosticSession, read, save_once
    from metacom_pm.rl1.observation_features import PlanAwareFeatureEncoder, make_actor_critic
    from metacom_pm.rl1.representation_direct import DirectReplyRenderer
    prep = import_file("rl1_diagnostic_prep", PROJECT / "scripts/rl1/111_prepare_four_head_diagnostic.py")
    run = Path(protocol["run_dir"])
    run.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as stack:
        paths = [run / ".execution.lock", BASE / "live_runs/.pool.lock",
                 Path(protocol["financial_baseline"]["ledger_path"]).with_suffix(".lock")]
        paths += [BASE / name / ".launch.lock" for name in (
            "paired_diagnostic_runs", "action_stage_runs", "reward_noise_runs", "anchor_calibration_runs")]
        parent_lock_fd = None
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            f = stack.enter_context(path.open("a"))
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if path == run / ".execution.lock":
                parent_lock_fd = f.fileno()
        if (run / "STOP.json").exists():
            return dict(status="STOP_PRESERVED", new_calls=0)
        data = read(PREP / "inputs_private.json")
        tok = AutoTokenizer.from_pretrained(r["model_dir"], local_files_only=True)
        renderer = DirectReplyRenderer(count_text=lambda t:len(tok.encode(t, add_special_tokens=False)),
            count_chat=lambda m:len(tok.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
            tokenizer_identity=protocol["renderer_tokenizer_identity"], context_limit=r["policy"]["context_limit"])
        local = LocalProviders(protocol, data, renderer, run)
        encoder = PlanAwareFeatureEncoder(local.encode, embedding_dimension=1024,
                                          text_encoder_identity=protocol["text_encoder_identity"])
        specs = {p:prep.spec_from(s) for p,s in data["specs"].items()}
        def lookup(rid):
            path = run / "coordinator_reviews" / (rid + ".json")
            return read(path) if path.exists() else None
        def make(t):
            pid = protocol["trajectory_manifest"][t]["prefix_identity"]
            return DiagnosticEpisode(specs[pid], renderer, evidence=data["evidence"][pid],
                protocol=protocol, approval=approval, trajectory_id=t, review_lookup=lookup)
        torch.set_num_threads(1)
        torch.manual_seed(17)
        model = make_actor_critic(encoder.feature_dimension)
        session = DiagnosticSession(protocol, approval, run, model, encoder, make)
        paid = None
        try:
            if session.sequence == 0:
                paid = PaidProcess(protocol, run / "approval.json", parent_lock_fd)
                stack.callback(paid.close)
            # No repeated polling while reviews are absent. Source review is an
            # explicit coordinator work item, never a model or human auto-label.
            while True:
                before_phase = session.phase
                status = session.advance()
                if status["stopped"] or status["phase"] == "complete":
                    break
                waiting = sum(x["count"] for x in status["queue"] if x["state"] == "WAITING")
                started = sum(x["count"] for x in status["queue"] if x["state"] == "STARTED")
                if not waiting and not started:
                    if before_phase != session.phase:
                        continue
                    return dict(status="PENDING_COORDINATOR_REVIEW", **status)
                if paid is None:
                    paid = PaidProcess(protocol, run / "approval.json", parent_lock_fd)
                    stack.callback(paid.close)
                status = session.worker(dict(generation=local.generate, measurement=paid))
                if status["stopped"]:
                    break
            return status
        except BaseException as exc:
            # Never echo provider/credential exception messages.
            if not (run / "STOP.json").exists():
                save_once(run / "STOP.json", dict(reason="execution guard or interrupted phase",
                    exception_type=type(exc).__name__, automatic_retry=False,
                    diagnostic_only=True, old_stops_released=False))
            raise RuntimeError("diagnostic stopped; retained local state, no automatic retry") from None


if __name__ == "__main__":
    os.umask(0o077)
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--advance", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--approval", type=Path)
    ap.add_argument("--paid-worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--parent-lock-fd", type=int, help=argparse.SUPPRESS)
    args = ap.parse_args()
    protocol = check()
    if args.paid_worker:
        if args.approval is None:
            raise SystemExit("whole-scope approval required before worker start")
        from metacom_pm.rl1.diagnostic_session import read
        paid_worker(protocol, read(args.approval), args.parent_lock_fd)
        raise SystemExit(0)
    if args.report and args.advance:
        raise SystemExit("choose read-only report or explicitly approved advance")
    if args.report:
        result = report(protocol)
    elif args.advance:
        if args.approval is None:
            raise SystemExit("Explicit whole-scope approval required; no execution")
        from metacom_pm.rl1.diagnostic_session import read
        result = advance(protocol, read(args.approval))
    else:
        result = dict(status="OFFLINE_PACKAGE_VALID", protocol_identity=protocol["identity"],
            real_execution_authorized=False, max_new_J=80, max_trajectories=32,
            BC_initialization_present=False, old_STOPS_preserved=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
