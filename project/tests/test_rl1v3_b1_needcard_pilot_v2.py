"""NeedCard pilot plan v2 (20 first calls, no re-ask) and audit protocol v2.  CPU fixtures; no model."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from metacom_pm.rl1v3.checklist import writer_v3 as CW3
from metacom_pm.rl1v3.checklist.ledger import ChecklistLedger
from metacom_pm.rl1v3.needs import pilot as PL1, pilot_audit as A1, pilot_audit_v2 as A2, pilot_v2 as PL2
from test_rl1v3_b1_needcard_pilot import GOOD, WRITER, gen, lines, setup

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/rl1v3"


def plan2(n, statuses=None):
    plan, ctxs, packs, pack = setup(n)
    for r in plan["inputs"]:
        r["status"] = "ready"
    for pid, st in (statuses or {}).items():
        packs[pid] = dict(pack, status=st)
        next(r for r in plan["inputs"] if r["prefix_id"] == pid)["status"] = st
    return plan, ctxs, packs, pack


def test_v2_limits_are_20_first_calls_and_no_retry_and_v1_is_unchanged():
    assert PL2.LIMITS["max_first_calls"] == 20 and PL2.LIMITS["max_retry_calls"] == 0 and PL2.LIMITS["total_calls"] == 20
    assert PL1.LIMITS == dict(first_calls=20, reasks=20, total_calls=40, per_call_seconds=600, wall_seconds=7200,
                              early_stop_after_prefixes=5, early_stop_writer_failed=3)
    assert "NOT J1" in PL2.WORKLOAD_LABEL


def test_one_failed_call_is_writer_failed_without_reask_and_calls_are_fully_recorded(tmp_path):
    plan, ctxs, packs, pack = plan2(3)
    s = PL2.run_pilot(plan, ctxs, packs, gen([GOOD, "not json", (GOOD, "length")], pack), writer=WRITER,
                      out=tmp_path, max_first_calls=20)
    calls = lines(tmp_path / "calls.jsonl")
    assert s["calls"] == dict(first=3, retry=0, total=3) and s["envelopes"]["writer_failed"] == 2
    assert [c["writer_failed"] for c in calls] == [False, True, True]
    keys = {"pack_sha256", "messages_sha256", "input_tokens", "output_text", "output_sha256", "finish_reason",
            "output_tokens", "seconds", "peak_bytes", "error", "writer_failed"}
    assert all(keys <= set(c) for c in calls) and calls[2]["error"] == "finish_reason:length"
    env = lines(tmp_path / "envelopes.jsonl")
    assert env[1]["status"] == "writer_failed" and env[1]["derived_stratum"] is None
    assert s["a0_handoff"]["label"] == PL2.WORKLOAD_LABEL and s["a0_handoff"]["calls"] == 3


def test_pre_call_blocked_pack_is_never_called(tmp_path):
    plan, ctxs, packs, pack = plan2(3, statuses={"p2": "over_budget_operational"})
    s = PL2.run_pilot(plan, ctxs, packs, gen([GOOD, GOOD], pack), writer=WRITER, out=tmp_path, max_first_calls=20)
    assert s["calls"]["total"] == 2 and s["envelopes"] == dict(ok=2, writer_failed=0, pre_call_blocked=1)
    env = lines(tmp_path / "envelopes.jsonl")
    assert env[1]["status"] == "pre_call_blocked" and env[1]["blocked_status"] == "over_budget_operational"


def test_v2_caps_stops_and_authorization(tmp_path):
    plan, ctxs, packs, pack = plan2(4)
    s = PL2.run_pilot(plan, ctxs, packs, gen([GOOD] * 4, pack), writer=WRITER, out=tmp_path / "a", max_first_calls=2)
    assert s["stop_reason"] == "S2:call_cap" and s["calls"]["total"] == 2
    plan, ctxs, packs, pack = plan2(6)
    s = PL2.run_pilot(plan, ctxs, packs, gen(["bad"] * 3 + [GOOD] * 3, pack), writer=WRITER, out=tmp_path / "b",
                      max_first_calls=20)
    assert s["stop_reason"] == "S4:early_systematic_failure" and s["calls"]["total"] == 5
    p = dict(task_id="B1_needcard_pilot_v2", plan_sha256="f" * 64)
    ok = dict(authorized_by="researcher", granted_at="2026-11-18T12:00:00Z", scope=p["task_id"], plan_sha256="f" * 64,
              max_first_calls=20, max_retry_calls=0, gpu_uuid="GPU-a", paid_api_calls=0)
    PL2.check_authorization(ok, p, gpu_uuid="GPU-a")
    for bad in (dict(max_retry_calls=1), dict(max_first_calls=21), dict(scope="B1_needcard_pilot_v1"),
                dict(authorized_by="wsb")):
        with pytest.raises(PL2.PilotStopped):
            PL2.check_authorization(dict(ok, **bad), p, gpu_uuid="GPU-a")


def _audit_rows(tmp_path, n, answers, statuses=None):
    plan, ctxs, packs, pack = plan2(n, statuses)
    outs = [GOOD if a != "failed" else "bad" for a in answers if a != "blocked"]
    PL2.run_pilot(plan, ctxs, packs, gen(outs, pack), writer=WRITER, out=tmp_path, max_first_calls=20)
    spec = importlib.util.spec_from_file_location("audit_v2", SCRIPTS / "B1_needcard_pilot_audit_v2.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    env = mod.load_envelopes(tmp_path / "envelopes.jsonl")
    rows = A2.prepare(env)
    by = {r["prefix_id"]: r for r in rows}
    for k, a in enumerate(answers):
        r = rows[k] if k < len(rows) else None
        if isinstance(a, dict):
            r["answers"] = dict({c: "yes" for c in A2.CHECKS}, **a)
            r["reviewer"] = "wsb-dev-audit"
            r["notes"]["evidence_supports_claim"] = "checked against the quoted turn"
            r["fix_reason"] = "reviewer note" if any(v != "yes" for v in a.values()) else None
    return env, rows, by


def test_audit_v2_labels_gates_and_b6e_pause(tmp_path):
    env, rows, _ = _audit_rows(tmp_path, 6, [{}, {"optional_not_mislabeled": "no"}, {"state_not_confused": "no"},
                                             {"method_need_supported": "cannot_judge"}, "failed", "blocked"],
                               statuses={"p6": "blocked_catalog"})
    pids = [r["prefix_id"] for r in rows]
    rep = A2.report(rows, b6e_prefixes=[pids[0]])
    assert [x["verdict"] for x in rep["rows"]] == ["valid", "stratum_error", "evidence_error", "uncertain",
                                                    "writer_failed", "pre_call_blocked"]
    assert rep["rows"][2]["error_types"] == ["state_not_confused"] and rep["rows"][0]["notes"]["evidence_supports_claim"]
    assert rep["evidence_error_rate"] == pytest.approx(1 / 4) and rep["gate_passed"] is False and rep["b6e_paused"]
    assert rep["checks_identical_to"] == A1.AUDIT_PROTOCOL and A2.CHECKS is A1.CHECKS


def test_audit_v2_b6e_gate_needs_every_selected_prefix_valid(tmp_path):
    env, rows, _ = _audit_rows(tmp_path, 2, [{}, {}])
    rep = A2.report(rows, b6e_prefixes=[rows[0]["prefix_id"], "x" * 64])
    assert rep["gate_passed"] and not rep["b6e_gate_passed"] and rep["b6e_prefixes_without_valid_card"] == ["x" * 64]
    rep = A2.report(rows, b6e_prefixes=[rows[0]["prefix_id"]])
    assert rep["b6e_gate_passed"] and not rep["b6e_paused"]
    frozen = A2.freeze_checklists(rep, env[:1], ChecklistLedger(tmp_path / "ledger"), CW3.build)
    assert list(frozen) == [rows[0]["prefix_id"]] and frozen[rows[0]["prefix_id"]]["writer_identity"] == CW3.writer_identity()
