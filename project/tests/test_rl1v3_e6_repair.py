"""CPU-only regressions for B's E3/E5/E6/F1 findings. No research input bodies."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from metacom_pm.rl1v3.generator import limited_run as L
from metacom_pm.rl1v3.io import object_sha256

ROOT = Path(__file__).resolve().parents[2]


def wait_for(predicate, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.02)
    return bool(predicate())


def live(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
    except FileNotFoundError:
        return False


@pytest.mark.parametrize("mode", ["SIGTERM", "SIGKILL", "worker_exit", "deadline_parent_stopped"])
def test_guard_stops_worker_and_descendants_after_lifecycle_failure(tmp_path, mode):
    # A fresh supervisor launches the real stdlib guard, then a synthetic worker
    # that starts a TERM-ignoring child. All PIDs belong to this test only.
    child_code = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"
    worker = tmp_path / "dummy.py"
    worker.write_text("import os,sys,subprocess,time,json\nfrom pathlib import Path\n"
        f"p=subprocess.Popen([sys.executable,'-c',{child_code!r}])\n"
        f"Path({str(tmp_path/'pids.json')!r}).write_text(json.dumps([os.getpid(),p.pid]))\n"
        + ("time.sleep(.2);os._exit(7)\n" if mode == "worker_exit" else "time.sleep(60)\n"))
    supervisor = tmp_path / "supervisor.py"
    supervisor.write_text("import os,subprocess,sys,time\n"
        "env=dict(os.environ,PMRL1_LIMITED_SUPERVISOR_PID=str(os.getpid()),"
        "PMRL1_LIMITED_DEADLINE=str(time.monotonic()+3))\n"
        f"p=subprocess.Popen([sys.executable,'-m','metacom_pm.rl1v3.generator.limited_worker_guard',sys.executable,{str(worker)!r}],env=env,start_new_session=True)\n"
        "p.wait()\n")
    env = dict(os.environ, PYTHONPATH=str(ROOT / "project/src"), PYTHONDONTWRITEBYTECODE="1")
    parent = subprocess.Popen([sys.executable, str(supervisor)], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pids = []
    try:
        assert wait_for(lambda: (tmp_path / "pids.json").is_file())
        pids = json.loads((tmp_path / "pids.json").read_text())
        if mode in {"SIGTERM", "SIGKILL"}:
            os.kill(parent.pid, getattr(signal, mode))
        elif mode == "deadline_parent_stopped":
            os.kill(parent.pid, signal.SIGSTOP)
        assert wait_for(lambda: not any(live(pid) for pid in pids)), "guard left computing descendants"
    finally:
        if mode == "deadline_parent_stopped":
            os.kill(parent.pid, signal.SIGCONT)
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=5)
        if pids and any(live(pid) for pid in pids):
            os.killpg(pids[0], signal.SIGKILL)


def request_plan():
    return dict(job_kind="A0_MIN", requests_sha256="fixed-requests", ordered_request_ids=["r0", "r1"],
                baseline_sha256="fixed-baseline", executor_source_head="old")


def test_changed_approval_and_executor_do_not_reopen_request_set(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DATA", tmp_path)
    plan = request_plan()
    L.claim_request_set(plan, {"fixture": "first"})
    plan["executor_source_head"] = "repaired"
    with pytest.raises(FileExistsError, match="cannot retry"):
        L.claim_request_set(plan, {"fixture": "second"})
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_legacy_or_partial_claim_cannot_be_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DATA", tmp_path)
    plan = request_plan()
    old = tmp_path / "tokkio_projects/pmrl1-validation/limited-g0e-claims/old.json"
    L.write_once(old, dict(plan_sha256=object_sha256(plan), approval_sha256="old"))
    with pytest.raises(FileExistsError):
        L.claim_request_set(plan, {"fixture": "second"})
    old.write_text("{")  # synthetic interrupted record, never repaired/deleted by admission
    with pytest.raises(ValueError):
        L.claim_request_set(plan, {"fixture": "third"})


def test_repair_binding_needs_its_own_signed_sha_before_git_access(monkeypatch):
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: pytest.fail("early git access"))
    plan = request_plan()
    auth = dict(authorized=True, job_kind="A0_MIN", plan_sha256=object_sha256(plan))
    with pytest.raises(L.AdmissionError, match="executor binding SHA"):
        L.authorize(ROOT, plan, auth, {"fixture": "binding"})


def test_binding_cannot_omit_the_guard_file():
    plan = dict(executor_source_head="old", executor_files_sha256={"old.py": "hash"})
    binding = dict(protocol="pmrl1-executor-repair-binding-1", authorized=False, research_qualified=False,
                   original_plan_sha256=object_sha256(plan), original_executor_source_head="old",
                   executor_files_sha256={"old.py": "hash"})
    with pytest.raises(L.AdmissionError, match="file set"):
        L.check_executor_binding(ROOT, plan, binding)
