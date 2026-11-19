#!/usr/bin/env python3
"""WS-B independent E6 acceptance of the WS-A limited executor (Draft PR #21, fixed HEAD) by fault injection.

System under test (SUT): metacom_pm.rl1v3.generator.limited_run from a detached worktree of #21's HEAD.  B never
uses A's tests or acceptance helpers as the oracle; every expectation below is B's.  Replaced dependencies (all
written by B, all CPU-only, no model or GPU access):
  * the HF worker      -> dummy_worker.py (speaks the same JSON-lines protocol; logs what it receives)
  * nvidia-smi         -> fake script on PATH (state file: uuid / free MiB / pids / failure / switch after N calls)
  * DATA root          -> per-scenario temporary directory (lock, claims and journals never touch the real paths)
  * model byte list    -> one small real file of the model directory (config.json), right or deliberately wrong hash,
                          so 24 GB of weights are not read; the python executable in the plan -> the dummy worker
Each scenario runs in its own child process (signals, monkeypatches and locks are isolated).

usage:  python V321A_e6_harness.py --wt <#21 worktree> --out <dir> [--only name,...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HEAD = "46349ccf02fef477bfc8fd76114bf1e38044e1d3"
A0_PLAN = "project/outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/A0_MIN_PLAN.json"
PP1_PLAN = "project/outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/PP1_PLAN.json"
GPU = "GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4"
ENV_REDIRECT = ("TMPDIR", "TMP", "TEMP", "HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "XDG_CACHE_HOME", "TORCH_HOME",
                "TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR", "CUDA_CACHE_PATH", "PYTHONPYCACHEPREFIX")

FAKE_NVSMI = r'''#!/usr/bin/env python3
import json, os, sys
st_path = os.environ["FAKE_NVSMI_STATE"]
st = json.load(open(st_path))
st["calls"] = st.get("calls", 0) + 1
json.dump(st, open(st_path, "w"))
with open(os.environ["FAKE_NVSMI_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
if st.get("fail"):
    sys.exit(3)
cur = st
if st.get("switch_after") is not None and st["calls"] > st["switch_after"]:
    cur = dict(st, **st["switch_to"])
if any(a.startswith("--query-gpu") for a in sys.argv):
    print(f"{cur['uuid']}, {cur['free']}")
else:
    for pid in cur.get("pids", []):
        print(f"{cur['uuid']}, {pid}")
'''

DUMMY = r'''#!__PY__
# B's dummy worker: same JSON-lines protocol as limited_hf_worker; behaviour per call from DUMMY_CFG.
import glob, hashlib, json, os, signal, subprocess, sys, time
cfg = json.load(open(os.environ["DUMMY_CFG"]))
if cfg.get("ignore_term"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
log = open(cfg["log"], "a", buffering=1)
def note(**k):
    log.write(json.dumps(dict(t=time.time(), pid=os.getpid(), **k)) + "\n")
note(op="spawn", ppid=os.getppid(), supervisor=os.environ.get("PMRL1_LIMITED_SUPERVISOR_PID"),
     cuda=os.environ.get("CUDA_VISIBLE_DEVICES"))
n = 0
def tokens(payload, variant=0):
    h = hashlib.sha256(json.dumps(payload["input_ids"]).encode() + bytes([variant])).digest()
    return [1000 + b for b in h[:6]]
for line in sys.stdin:
    cmd = json.loads(line)
    if cmd["operation"] == "load":
        act = cfg.get("load", "ok")
        note(op="load", act=act)
        if act.startswith("slow:"):
            time.sleep(float(act[5:]))
        if act == "error":
            sys.stdout.write(json.dumps({"ok": False, "error": "OutOfMemoryError: CUDA out of memory (simulated)"}) + "\n")
            sys.stdout.flush(); sys.exit(1)
        sys.stdout.write(json.dumps({"ok": True, "result": {"seconds": 0.01, "simulated": True}}) + "\n"); sys.stdout.flush()
        continue
    n += 1
    p = cmd["payload"]
    starts = len(glob.glob(os.path.join(os.getcwd(), "*-REQUEST_START.json")))
    act = cfg.get("calls", {}).get(str(n), "ok")
    note(op="generate", ordinal=n, act=act, start_files_on_disk=starts)
    eos = p["decode"]["eos_token_id"]; eos = [eos] if isinstance(eos, int) else eos
    ids = tokens(p) + [eos[0]]
    reason = "eos"
    if act.startswith("slow:"):
        time.sleep(float(act[5:])); note(op="finished_slow", ordinal=n)
    if act == "hang":
        time.sleep(3600)
    if act == "spawn_hang":
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)", cfg["marker"]])
        time.sleep(3600)
    if act == "spawn_crash":
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)", cfg["marker"]])
        sys.exit(9)
    if act == "ignore_term_hang":
        signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(3600)
    if act == "crash":
        os._exit(7)
    if act == "garbage":
        sys.stdout.write("this is not json\n"); sys.stdout.flush(); continue
    if act == "error":
        sys.stdout.write(json.dumps({"ok": False, "error": "RuntimeError: simulated worker failure"}) + "\n"); sys.stdout.flush(); continue
    if act == "length":
        ids = (tokens(p) * 60)[:p["decode"]["max_new_tokens"]]; reason = "length"
    if act == "differ":
        ids = tokens(p, 1) + [eos[0]]
    text = "" if act == "empty" else "simulated reply"
    res = {"token_ids": ids, "text": text, "finish_reason": reason, "seconds": 0.01, "input_tokens": len(p["input_ids"])}
    sys.stdout.write(json.dumps({"ok": True, "result": res}) + "\n"); sys.stdout.flush()
    note(op="returned", ordinal=n)
note(op="eof_exit")
'''


# ------------------------------------------------------------------ child side (runs one scenario in-process)
def child(args):
    wt, S = Path(args.wt), Path(args.scenario_dir)
    cfg = json.loads((S / "scenario.json").read_text())
    sys.path.insert(0, str(wt / "project/src"))
    import metacom_pm.rl1v3.generator.limited_run as L          # the system under test
    from metacom_pm.rl1v3.io import object_sha256               # shared project hashing (not an A acceptance helper)
    data = S / "data"
    (data / "tokkio_projects/pmrl1-validation").mkdir(parents=True, exist_ok=True)
    data = data.resolve()
    L.DATA = data
    run_root = data / "runs" / cfg.get("run_name", "job")
    for name in ENV_REDIRECT:
        os.environ[name] = str(run_root / "tmp") if not (cfg.get("bad_env") == name) else "/tmp"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    (S / "pid").write_text(str(os.getpid()))
    if cfg.get("root_free_bytes") is not None:
        real = os.statvfs

        class _V:
            def __init__(self, v, free):
                self.f_bavail, self.f_frsize, self.f_favail = free, 1, v.f_favail

        def fake(path):
            v = real(path)
            return _V(v, cfg["root_free_bytes"]) if os.path.realpath(path) == "/" else v
        L.os.statvfs = fake
    real_read = L.read_plan
    model_file = Path("/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3/config.json")
    msha = hashlib.sha256(model_file.read_bytes()).hexdigest()

    def read_plan(root, path):
        plan, rows, baseline = real_read(root, path)                 # full, unmodified admission of the real plan
        plan = dict(plan, python=str(S / "dummy_worker.py"))
        baseline = json.loads(json.dumps(baseline))
        baseline["spec"]["model"]["files"] = {"config.json": dict(bytes=model_file.stat().st_size,
                                                                 sha256="0" * 64 if cfg.get("bad_model_hash") else msha)}
        return plan, rows, baseline
    L.read_plan = read_plan
    out = dict(name=cfg["name"])
    try:
        if cfg["kind"] == "run":
            plan, _rows, _b = read_plan(wt, wt / cfg["plan"])
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=wt, text=True).strip()
            auth = dict(authorized=True, job_kind=plan["job_kind"], plan_sha256=object_sha256(plan),
                        max_calls=plan["max_calls"], researcher="TEST-ONLY (WS-B E6 harness; not a researcher)",
                        decision_evidence="WS-B E6 fault-injection harness; NOT an authorization " + cfg.get("salt", ""),
                        executor_checkout_head=head, executor_review_evidence="TEST-ONLY",
                        g0e_identity_decision=dict(source_head=L.G0E_HEAD, signed_by="TEST-ONLY", evidence="TEST-ONLY",
                                                   route="researcher_written_limited"))
            for k, v in cfg.get("auth_patch", {}).items():
                if v is None:
                    auth.pop(k, None)
                else:
                    auth[k] = v
            if cfg.get("auth_plan_unmodified"):
                auth["plan_sha256"] = object_sha256(real_read(wt, wt / cfg["plan"])[0])
            ap = S / ("approval_%s.json" % cfg.get("salt", "0"))
            ap.write_text(json.dumps(auth))
            res = L.run(wt, wt / cfg["plan"], ap, run_root)
            out.update(outcome="returned", summary=res)
        elif cfg["kind"] == "drive":
            plan, rows, baseline = real_read(wt, wt / cfg["plan"])
            t = [0.0]
            clock = lambda: t[0]                                           # noqa: E731
            calls = []

            class Fake:
                kind = "b_fake"

                def load(self, sec):
                    t[0] += cfg.get("load_seconds", 10)
                    return {"seconds": cfg.get("load_seconds", 10)}

                def generate(self, payload, sec):
                    n = len(calls) + 1
                    calls.append(dict(n=n, budget=sec))
                    dur = cfg.get("call_seconds", 20)
                    if dur > sec:
                        t[0] += sec
                        raise TimeoutError(f"call {n} exceeded its {sec:.0f}s budget")
                    t[0] += dur
                    eos = payload["decode"]["eos_token_id"]
                    eos = [eos] if isinstance(eos, int) else eos
                    if n in cfg.get("length_at", []):
                        ids = ([1234] * 400)[:payload["decode"]["max_new_tokens"]]
                        return dict(token_ids=ids, text="x", finish_reason="length", seconds=dur,
                                    input_tokens=len(payload["input_ids"]))
                    return dict(token_ids=[1234, eos[0]], text="x", finish_reason="eos", seconds=dur,
                                input_tokens=len(payload["input_ids"]))

                def close(self):
                    pass
            j = L.Journal(S / "journal")
            res = L.drive(plan, rows, baseline, j, Fake(), clock=clock, started=0.0)
            out.update(outcome="returned", summary=res, fake_calls=calls)
        elif cfg["kind"] == "subprocess_deadline":
            plan, rows, baseline = read_plan(wt, wt / cfg["plan"])
            L.device_guard = lambda own_pid=None, initial=False: {"gpu_uuid": GPU}
            outdir = S / "journal"
            outdir.mkdir()
            b = L.SubprocessHF(wt, plan, baseline, outdir, time.monotonic() + cfg["deadline"])
            t0 = time.monotonic()
            try:
                b.load(30)
                b.generate(rows[0]["model_input"], 300)
                out.update(outcome="returned")
            except BaseException as e:                                   # noqa: BLE001
                out.update(outcome="raised", error=f"{type(e).__name__}: {e}")
            out["seconds"] = round(time.monotonic() - t0, 2)
            out["worker_pid"] = b.p.pid if b.p else None
            b.close()
    except BaseException as e:                                           # noqa: BLE001
        out.update(outcome="raised", error=f"{type(e).__name__}: {e}"[:400])
    (S / "result.json").write_text(json.dumps(out, default=str))


# ------------------------------------------------------------------ parent side
def alive(pattern: str) -> list[int]:
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split() if int(x) != os.getpid()]


def journal_events(S: Path) -> list[dict]:
    files = sorted(S.rglob("job-*/*.json")) or sorted((S / "journal").glob("*.json")) if (S / "journal").exists() else \
        sorted(S.rglob("job-*/*.json"))
    out = []
    for f in files:
        try:
            d = json.loads(f.read_text())
        except Exception:                                                # noqa: BLE001
            d = {"unreadable": True}
        out.append(dict(file=f.name, sha256=hashlib.sha256(f.read_bytes()).hexdigest(), **d))
    return out


def chain_ok(events: list[dict]) -> bool:
    ev = [e for e in events if "seq" in e]
    for a, b in zip(ev, ev[1:]):
        if b.get("previous_event_sha256") != a["sha256"]:
            return False
    return bool(ev) and ev[0].get("previous_event_sha256") is None


def dummy_log(S: Path) -> list[dict]:
    p = S / "dummy.log"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def nvsmi_calls(S: Path) -> int:
    p = S / "nvsmi.log"
    return len(p.read_text().splitlines()) if p.exists() else 0


class Scenario:
    def __init__(self, base: Path, wt: Path, name: str, **cfg):
        self.S = base / name
        if self.S.exists():
            shutil.rmtree(self.S)
        (self.S / "bin").mkdir(parents=True)
        self.wt, self.name = wt, name
        self.cfg = dict(dict(kind="run", plan=A0_PLAN), name=name, **cfg)
        (self.S / "scenario.json").write_text(json.dumps(self.cfg))
        nv = self.S / "bin/nvidia-smi"
        nv.write_text(FAKE_NVSMI)
        nv.chmod(0o755)
        st = dict(uuid=GPU, free=48000, pids=[], fail=False, switch_after=None, switch_to={})
        st.update(cfg.get("nvsmi", {}))
        (self.S / "nvsmi.json").write_text(json.dumps(st))
        dw = self.S / "dummy_worker.py"
        dw.write_text(DUMMY.replace("__PY__", sys.executable))
        dw.chmod(0o755)
        (self.S / "dummy.json").write_text(json.dumps(dict(log=str(self.S / "dummy.log"), marker=f"E6MARK-{name}",
                                                           **cfg.get("dummy", {}))))

    def env(self):
        e = dict(os.environ, PATH=str(self.S / "bin") + ":" + os.environ["PATH"], FAKE_NVSMI_STATE=str(self.S / "nvsmi.json"),
                 FAKE_NVSMI_LOG=str(self.S / "nvsmi.log"), DUMMY_CFG=str(self.S / "dummy.json"),
                 PYTHONDONTWRITEBYTECODE="1")
        e.pop("PYTHONPATH", None)
        return e

    def start(self):
        return subprocess.Popen([sys.executable, __file__, "--child", "--wt", str(self.wt), "--scenario-dir", str(self.S)],
                                env=self.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def run(self, timeout=180):
        p = self.start()
        try:
            p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
        return self.result()

    def result(self):
        r = json.loads((self.S / "result.json").read_text()) if (self.S / "result.json").exists() else {"outcome": "no_result"}
        r["events"] = [e.get("event") for e in journal_events(self.S)]
        r["chain_ok"] = chain_ok(journal_events(self.S))
        r["dummy"] = dummy_log(self.S)
        r["nvidia_smi_calls"] = nvsmi_calls(self.S)
        r["claims"] = len(list((self.S / "data/tokkio_projects/pmrl1-validation/limited-g0e-claims").glob("*.json"))) \
            if (self.S / "data").exists() else 0
        r["orphans"] = alive(str(self.S / "dummy_worker.py")) + alive(f"E6MARK-{self.name}")
        return r

    def wait_dummy(self, op, ordinal=None, timeout=60):
        t0 = time.time()
        while time.time() - t0 < timeout:
            for d in dummy_log(self.S):
                if d["op"] == op and (ordinal is None or d.get("ordinal") == ordinal):
                    return True
            time.sleep(0.1)
        return False

    def cleanup(self):
        for pid in alive(str(self.S / "dummy_worker.py")) + alive(f"E6MARK-{self.name}"):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def gens(r):
    return [d for d in r["dummy"] if d["op"] == "generate"]


def main(args):
    wt, base = Path(args.wt), Path(args.out)
    base.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=wt, text=True).strip()
    assert head == HEAD, f"worktree is at {head}, expected {HEAD}"
    checks = []

    def ck(area, name, ok, detail=None, severity=None):
        checks.append(dict(area=area, name=name, ok=bool(ok), detail=detail, severity=severity))
        print(("PASS " if ok else "FAIL ") + area + " | " + name)

    only = set(args.only.split(",")) if args.only else None

    def want(n):
        return only is None or n in only

    def sc(name, **cfg):
        return Scenario(base, wt, name, **cfg)

    # ---------------- A: admission (refused before any device query, claim, journal or worker)
    adm = {
        "A1_not_authorized": dict(auth_patch=dict(authorized=False)),
        "A2_job_kind_transfer": dict(auth_patch=dict(job_kind="PP1")),
        "A3_plan_sha_mismatch": dict(auth_plan_unmodified=False, auth_patch=dict(plan_sha256="0" * 64)),
        "A4_call_budget_mismatch": dict(auth_patch=dict(max_calls=5)),
        "A5_checkout_head_not_pinned": dict(auth_patch=dict(executor_checkout_head="0" * 40)),
        "A6_g0e_identity_not_fixed": dict(auth_patch=dict(g0e_identity_decision=dict(source_head="0" * 40, signed_by="x",
                                                                                     evidence="x", route="researcher_written_limited"))),
        "A7_no_executor_review": dict(auth_patch=dict(executor_review_evidence=None)),
        "A8_no_researcher": dict(auth_patch=dict(researcher=None)),
    }
    for n, cfg in adm.items():
        if not want(n):
            continue
        s = sc(n, **cfg)
        r = s.run()
        ck("admission", f"{n}: refused before device/claim/journal/worker",
           r["outcome"] == "raised" and "AdmissionError" in r.get("error", "") and r["nvidia_smi_calls"] == 0
           and r["claims"] == 0 and not r["events"] and not r["dummy"], r.get("error"))
    # bound-file and executor-file tampering (temporary edits inside the worktree, always restored)
    for n, rel, why in (("A9_bound_request_file_changed",
                         "project/outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/A0_CALLS_4.jsonl", "bound file changed"),
                        ("A10_executor_script_changed", "project/scripts/rl1v3/limited_g0e_run.py", "executor source changed"),
                        ("A11_dirty_tracked_checkout", "README.md", "dirty")):
        if not want(n):
            continue
        p = wt / rel
        orig = p.read_bytes()
        try:
            p.write_bytes(orig + b"\n")
            r = sc(n).run()
        finally:
            p.write_bytes(orig)
        ck("admission", f"{n}: refused ({why})", r["outcome"] == "raised" and r["nvidia_smi_calls"] == 0 and not r["dummy"],
           r.get("error"))
    assert not subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=wt, text=True)

    # ---------------- B: device / storage / model-byte guards
    guards = {
        "B1_gpu_uuid_mismatch": dict(nvsmi=dict(uuid="GPU-00000000-0000-0000-0000-000000000000")),
        "B2_gpu_free_below_floor": dict(nvsmi=dict(free=30000)),
        "B3_gpu_occupied_by_other_pid": dict(nvsmi=dict(pids=[999999])),
        "B4_nvidia_smi_failure": dict(nvsmi=dict(fail=True)),
        "B5_root_below_1GiB": dict(root_free_bytes=200 * 1024 ** 2),
        "B6_tmpdir_not_redirected": dict(bad_env="TMPDIR"),
    }
    for n, cfg in guards.items():
        if not want(n):
            continue
        r = sc(n, **cfg).run()
        ck("guards", f"{n}: refused before claim, journal and worker",
           r["outcome"] == "raised" and r["claims"] == 0 and not r["events"] and not r["dummy"], r.get("error"))
    if want("B7_model_bytes_wrong"):
        r = sc("B7_model_bytes_wrong", bad_model_hash=True).run()
        ck("guards", "B7_model_bytes_wrong: STOP before LOAD_START, no worker spawned",
           r["outcome"] == "raised" and r["events"][:1] == ["RUN_START"] and "STOP" in r["events"]
           and "LOAD_START" not in r["events"] and not r["dummy"], dict(error=r.get("error"), events=r["events"]))
    if want("B8_gpu_taken_mid_run"):
        s = sc("B8_gpu_taken_mid_run", nvsmi=dict(switch_after=8, switch_to=dict(pids=[999999])),
               dummy=dict(calls={"2": "slow:3"}))
        r = s.run()
        g = gens(r)
        ck("guards", "B8_gpu_taken_mid_run: another process on the GPU stops the job; no further START; worker gone",
           r.get("summary", {}).get("status") == "STOPPED" and r["events"].count("REQUEST_START") == len(g) < 4
           and not r["orphans"], dict(reason=r.get("summary", {}).get("reason"), starts=r["events"].count("REQUEST_START"),
                                      orphans=r["orphans"]))
        s.cleanup()

    # ---------------- C: normal run, journal semantics
    if want("C1_normal_A0"):
        s = sc("C1_normal_A0")
        r = s.run()
        g = gens(r)
        seq = r["events"]
        exp = ["RUN_START", "MODEL_BYTES_VERIFIED", "LOAD_START", "LOAD_OK"] + \
              ["REQUEST_START", "REQUEST_RETURNED", "REQUEST_VALIDATED"] * 4
        ck("journal", "C1: FINISHED with exactly 4 physical calls (no warm-up, no extra call)",
           r.get("summary", {}).get("status") == "FINISHED" and r["summary"]["physical_calls"] == 4 and len(g) == 4,
           r.get("summary"))
        ck("journal", "C1: event order RUN_START…LOAD_OK, then START/RETURNED/VALIDATED ×4, SUMMARY last",
           [e for e in seq if e] == exp and seq[-1] is None, seq)
        ck("journal", "C1: every REQUEST_START is durable on disk before the worker receives that request",
           all(d["start_files_on_disk"] == d["ordinal"] for d in g), [d["start_files_on_disk"] for d in g])
        ck("journal", "C1: hash chain re-computed by B from file bytes", r["chain_ok"])
        ck("journal", "C1: worker received the pinned GPU UUID and the supervisor pid; exited after the run",
           r["dummy"][0].get("cuda") == GPU and r["dummy"][0].get("supervisor") and not r["orphans"])
        # same approval again -> refused (claim exists); START/RESULT already recorded
        r2 = s.run()
        ck("retry", "C1b: the same approval cannot run twice (claim is write-once)",
           r2["outcome"] == "raised" and ("FileExistsError" in r2.get("error", "") or "exists" in r2.get("error", ""))
           and len(gens(r2)) == 4, r2.get("error"))

    # ---------------- D: technical failures stop immediately; no retry; worker gone
    fails = {   # pending = unattempted + failed + truncated (summary["pending"])
        "D1_worker_error": dict(calls={"2": "error"}, stop_at=2, pending=3),
        "D2_worker_crash": dict(calls={"2": "crash"}, stop_at=2, pending=3),
        "D3_empty_output": dict(calls={"1": "empty"}, stop_at=1, pending=4),
        "D4_garbage_response": dict(calls={"3": "garbage"}, stop_at=3, pending=2),
        "D5_A0_first_length": dict(calls={"2": "length"}, stop_at=2, pending=3),
        "D6_A0_repeat_differs": dict(calls={"2": "differ"}, stop_at=2, pending=2),
    }
    for n, d in fails.items():
        if not want(n):
            continue
        stop_at, npend = d.pop("stop_at"), d.pop("pending")
        s = sc(n, dummy=d)
        r = s.run()
        g = gens(r)
        su = r.get("summary", {})
        ck("failure", f"{n}: STOPPED at call {stop_at}; no later START; pending recorded; worker gone",
           su.get("status") == "STOPPED" and len(g) == stop_at and r["events"].count("REQUEST_START") == stop_at
           and "STOP" in r["events"] and len(su.get("pending", [])) == npend and not r["orphans"],
           dict(reason=su.get("reason"), gens=len(g), pending=len(su.get("pending", [])), orphans=r["orphans"]))
        s.cleanup()
    if want("D7_load_oom"):
        s = sc("D7_load_oom", dummy=dict(load="error"))
        r = s.run()
        ck("failure", "D7_load_oom: OOM during load stops before any REQUEST_START; worker gone",
           r.get("summary", {}).get("status") == "STOPPED" and "REQUEST_START" not in r["events"] and not r["orphans"],
           r.get("summary", {}).get("reason"))
    if want("D8_third_length_PP1"):
        r = sc("D8_third_length_PP1", kind="drive", plan=PP1_PLAN, length_at=[2, 5, 9]).run()
        su = r.get("summary", {})
        ck("failure", "D8: PP1 stops at the third length (call 9); truncated kept; 7 unattempted pending",
           su.get("status") == "STOPPED" and su.get("physical_calls") == 9 and len(su.get("truncated_pending", [])) == 3
           and len(su.get("unattempted_or_failed_pending", [])) == 7 and len(r.get("fake_calls", [])) == 9, su)
    if want("D9_global_1200s"):
        r = sc("D9_global_1200s", kind="drive", plan=PP1_PLAN, load_seconds=100, call_seconds=250).run()
        su = r.get("summary", {})
        fc = r.get("fake_calls", [])
        ck("failure", "D9: 1,200 s total budget: the last call only gets the remaining time; nothing starts after it",
           su.get("status") == "STOPPED" and fc and fc[-1]["budget"] <= 1200 - 100 - 250 * (len(fc) - 1) + 1e-6
           and su.get("physical_calls") == len(fc) and su.get("wall_seconds", 0) <= 1200 + 1e-6,
           dict(calls=len(fc), last_budget=fc[-1]["budget"] if fc else None, reason=su.get("reason"),
                wall=su.get("wall_seconds")))

    # ---------------- E: hard deadline, process groups, signals
    if want("E1_hard_deadline_kills_group"):
        s = sc("E1_hard_deadline_kills_group", kind="subprocess_deadline", deadline=6, dummy=dict(calls={"1": "spawn_hang"}))
        r = s.run(timeout=60)
        time.sleep(0.5)
        ck("process", "E1: the supervisor's hard deadline kills the hung worker and its child (same process group)",
           r["outcome"] == "raised" and r.get("seconds", 99) < 12 and not s.result()["orphans"],
           dict(error=r.get("error"), seconds=r.get("seconds"), orphans=s.result()["orphans"]))
        s.cleanup()
    if want("E2_close_escalates_to_sigkill"):
        s = sc("E2_close_escalates_to_sigkill", nvsmi=dict(switch_after=12, switch_to=dict(pids=[999999])),
               dummy=dict(ignore_term=True, calls={"1": "hang"}))
        r = s.run(timeout=120)
        time.sleep(0.5)
        ck("process", "E2: a worker that ignores SIGTERM is still removed when the job stops (SIGKILL escalation)",
           r.get("summary", {}).get("status") == "STOPPED" and not s.result()["orphans"],
           dict(reason=r.get("summary", {}).get("reason"), orphans=s.result()["orphans"]))
        s.cleanup()
    if want("E3_worker_exit_leaves_child"):
        s = sc("E3_worker_exit_leaves_child", dummy=dict(calls={"2": "spawn_crash"}))
        r = s.run()
        time.sleep(0.5)
        orph = s.result()["orphans"]
        ck("process", "E3: when the worker itself dies, its children in the same process group are also removed",
           not orph, dict(orphans=orph, reason=r.get("summary", {}).get("reason")), severity="low")
        s.cleanup()
    for sig, n in ((signal.SIGINT, "E4_parent_SIGINT"), (signal.SIGTERM, "E5_parent_SIGTERM"),
                   (signal.SIGKILL, "E6_parent_SIGKILL")):
        if not want(n):
            continue
        s = sc(n, dummy=dict(calls={"2": "slow:12"}))
        p = s.start()
        ok_wait = s.wait_dummy("generate", 2)
        time.sleep(0.5)
        os.kill(p.pid, sig)
        try:
            p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
        time.sleep(2.0)
        mid = s.result()
        alive_after_2s = bool(mid["orphans"])
        s.wait_dummy("finished_slow", 2, timeout=20)
        time.sleep(1.5)
        end = s.result()
        g = gens(end)
        stop_logged = "STOP" in end["events"]
        detail = dict(waited=ok_wait, events=end["events"], worker_alive_2s_after_signal=alive_after_2s,
                      worker_finished_current_call=any(d["op"] == "finished_slow" for d in end["dummy"]),
                      generate_calls=len(g), orphans_end=end["orphans"])
        if sig == signal.SIGINT:
            ck("process", f"{n}: Ctrl-C stops the job, journals STOP, kills the worker at once",
               stop_logged and not alive_after_2s and len(g) == 2, detail)
        else:
            ck("process", f"{n}: after the supervisor is killed, the worker must not keep running (no orphan)",
               not alive_after_2s, detail, severity="high" if sig == signal.SIGTERM else "medium")
            ck("process", f"{n}: no new call is issued after the supervisor dies", len(g) == 2, detail)
            ck("journal", f"{n}: an interrupted run leaves an unresolved START (no RESULT) that blocks reuse of the same approval",
               end["events"].count("REQUEST_START") > end["events"].count("REQUEST_VALIDATED") and end["claims"] == 1, detail)
        s.cleanup()

    # ---------------- F: retries across approvals, concurrency, standalone worker
    if want("F1_reapproval_after_unresolved_start"):
        s = sc("F1_reapproval_after_unresolved_start", dummy=dict(calls={"2": "crash"}), salt="first")
        r1 = s.run()
        cfg = json.loads((s.S / "scenario.json").read_text())
        cfg.update(salt="second", run_name="job2")
        cfg["dummy"] = {}
        (s.S / "scenario.json").write_text(json.dumps(cfg))
        (s.S / "dummy.json").write_text(json.dumps(dict(log=str(s.S / "dummy.log"), marker="E6MARK-F1")))
        (s.S / "result.json").unlink()
        r2 = s.run()
        g = gens(r2)
        ck("retry", "F1: a second approval for the same plan must not re-run requests whose START is unresolved",
           r2["outcome"] == "raised" and len(g) == 2,
           dict(first=r1.get("summary", {}).get("reason"), second_outcome=r2.get("outcome"),
                second_status=r2.get("summary", {}).get("status"), total_generate_calls=len(g), claims=r2["claims"]),
           severity="high")
        s.cleanup()
    if want("F2_concurrent_job_blocked"):
        a = sc("F2_concurrent_job_blocked", dummy=dict(calls={"1": "slow:8"}), salt="a")
        pa = a.start()
        a.wait_dummy("generate", 1)
        cfg = json.loads((a.S / "scenario.json").read_text())
        b_dir = a.S.parent / "F2b"
        if b_dir.exists():
            shutil.rmtree(b_dir)
        shutil.copytree(a.S, b_dir, ignore=shutil.ignore_patterns("data", "dummy.log", "result.json", "pid", "nvsmi.log"))
        os.symlink(a.S / "data", b_dir / "data")
        cfg.update(salt="b", run_name="jobb")
        (b_dir / "scenario.json").write_text(json.dumps(cfg))
        b = Scenario.__new__(Scenario)
        b.S, b.wt, b.name, b.cfg = b_dir, wt, "F2b", cfg
        rb = b.run()
        pa.communicate(timeout=60)
        ck("retry", "F2: a second job cannot start while one holds the exclusive lock",
           rb["outcome"] == "raised" and ("BlockingIOError" in rb.get("error", "") or "Resource" in rb.get("error", ""))
           and not gens(rb), rb.get("error"))
        a.cleanup()
    if want("F3_worker_refuses_standalone"):
        env = dict(os.environ, PYTHONPATH=str(wt / "project/src"))
        env.pop("PMRL1_LIMITED_SUPERVISOR_PID", None)
        r = subprocess.run([sys.executable, "-m", "metacom_pm.rl1v3.generator.limited_hf_worker"], input="", env=env,
                           capture_output=True, text=True, timeout=60)
        env["PMRL1_LIMITED_SUPERVISOR_PID"] = "1"
        r2 = subprocess.run([sys.executable, "-m", "metacom_pm.rl1v3.generator.limited_hf_worker"], input="", env=env,
                            capture_output=True, text=True, timeout=60)
        ck("admission", "F3: the real worker module refuses to start without (or with a forged) supervisor pid, before torch",
           r.returncode != 0 and "supervisor" in r.stderr and r2.returncode != 0 and "torch" not in r.stderr.split("Error")[0],
           dict(rc=(r.returncode, r2.returncode), err=r.stderr.strip().splitlines()[-1:]))

    report = dict(sut=dict(pr=21, head=HEAD, code_head="575011b43947f4aaf73d6bb31f376bf4c36405fc",
                           modules=["generator/limited_run.py", "generator/limited_hf_worker.py", "scripts/rl1v3/limited_g0e_run.py"]),
                  harness=dict(python=sys.version.split()[0], replaced=["HF worker -> B dummy", "nvidia-smi -> B fake",
                                                                       "DATA -> temp", "model byte list -> config.json"]),
                  totals=dict(checks=len(checks), passed=sum(c["ok"] for c in checks),
                              failed=sum(not c["ok"] for c in checks)), checks=checks)
    (base / "E6_HARNESS_RESULT.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(report["totals"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--wt", required=True)
    ap.add_argument("--scenario-dir")
    ap.add_argument("--out")
    ap.add_argument("--only")
    a = ap.parse_args()
    child(a) if a.child else main(a)
