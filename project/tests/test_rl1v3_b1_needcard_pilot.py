"""NeedCard pilot runner core, authorization gate, audit and checklist-v3 freeze.  CPU fixtures only:
``generate`` is a stub; no model, GPU or paid call."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from metacom_pm.rl1v3.checklist import writer_v3 as CW3
from metacom_pm.rl1v3.checklist.ledger import ChecklistLedger, ChecklistOrderError
from metacom_pm.rl1v3.needs import pilot as PL, pilot_audit as A, protocol_v2 as W
from rl1v3_wsb_fixtures import context, writer_output
from test_rl1v3_b1_needcard_v2 import FakeRegistry, catalog, count_chars

SRC = Path(__file__).resolve().parents[1] / "src/metacom_pm/rl1v3"
WRITER = "fixture-writer"


def setup(n=6, out=None):
    ctx = context()
    pack = W.build_pack(ctx, catalog(), registry=FakeRegistry(), count_prompt=count_chars,
                        native_context_tokens=200_000, operational_max_input_tokens=100_000, tokenizer_identity="test")
    keys = [f"p{i}" for i in range(1, n + 1)]
    plan = dict(task_id="B1_needcard_pilot_v1", plan_sha256="f" * 64,
                inputs=[dict(order=i + 1, prefix_id=k, pack_sha256=pack["pack_sha256"]) for i, k in enumerate(keys)])
    return plan, {k: ctx for k in keys}, {k: pack for k in keys}, pack


def gen(script, pack, finish="stop"):
    """script: list of outputs (str) or exceptions, consumed one per call."""
    it = iter(script)

    def g(msgs, p):
        x = next(it)
        if isinstance(x, BaseException):
            raise x
        text, fin = (x, finish) if isinstance(x, str) else x
        return dict(text=text, output_tokens=len(text) // 4, finish_reason=fin, input_tokens=p["input_tokens"],
                    seconds=0.1, peak_bytes=123)
    return g


GOOD = writer_output(method_need="providing_suggestions")


def lines(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def test_ok_path_one_call_per_prefix_and_write_once(tmp_path):
    plan, ctxs, packs, pack = setup(3)
    s = PL.run_pilot(plan, ctxs, packs, gen([GOOD] * 3, pack), writer=WRITER, out=tmp_path, max_calls=40)
    assert s["stop_reason"] == "completed" and s["calls"] == dict(first=3, reask=0, total=3)
    assert s["envelopes"] == dict(ok=3, writer_failed=0) and s["needcards_enter_pm_or_g_observation"] is False
    env = lines(tmp_path / "envelopes.jsonl")
    assert all(e["visibility_scope"] == "evaluation_only" and e["plan_sha256"] == plan["plan_sha256"] for e in env)
    with pytest.raises(PL.PilotStopped, match="output_exists"):
        PL.run_pilot(plan, ctxs, packs, gen([GOOD] * 3, pack), writer=WRITER, out=tmp_path, max_calls=40)


def test_one_reask_then_writer_failed_never_stratum_none(tmp_path):
    plan, ctxs, packs, pack = setup(2)
    s = PL.run_pilot(plan, ctxs, packs, gen(["not json", GOOD, "bad", "still bad"], pack), writer=WRITER,
                     out=tmp_path, max_calls=40)
    env = lines(tmp_path / "envelopes.jsonl")
    assert [e["status"] for e in env] == ["ok", "writer_failed"] and env[1]["derived_stratum"] is None
    assert s["calls"] == dict(first=2, reask=2, total=4) and len(env[1]["errors"]) == 2


def test_length_or_timeout_finish_is_a_failed_attempt_even_if_parseable(tmp_path):
    plan, ctxs, packs, pack = setup(1)
    PL.run_pilot(plan, ctxs, packs, gen([(GOOD, "length"), (GOOD, "timeout")], pack), writer=WRITER,
                 out=tmp_path, max_calls=40)
    env = lines(tmp_path / "envelopes.jsonl")
    assert env[0]["status"] == "writer_failed" and env[0]["errors"] == ["finish_reason:length", "finish_reason:timeout"]


def test_call_cap_stops_and_never_exceeds_authorised_calls(tmp_path):
    plan, ctxs, packs, pack = setup(3)
    s = PL.run_pilot(plan, ctxs, packs, gen(["bad"] * 10, pack), writer=WRITER, out=tmp_path, max_calls=3)
    assert s["stop_reason"] == "S2:call_cap" and s["calls"]["total"] == 3 and s["prefixes_done"] == 1
    assert len(lines(tmp_path / "calls.jsonl")) == 3


def test_exception_stops_at_once_without_retry(tmp_path):
    plan, ctxs, packs, pack = setup(3)
    s = PL.run_pilot(plan, ctxs, packs, gen([GOOD, RuntimeError("CUDA out of memory")], pack), writer=WRITER,
                     out=tmp_path, max_calls=40)
    calls = lines(tmp_path / "calls.jsonl")
    assert s["stop_reason"] == "S3:exception:RuntimeError" and len(calls) == 2 and calls[-1]["status"] == "exception"
    assert s["prefixes_done"] == 1


def test_early_systematic_failure_stops_after_five_prefixes(tmp_path):
    plan, ctxs, packs, pack = setup(7)
    s = PL.run_pilot(plan, ctxs, packs, gen(["bad"] * 6 + [GOOD] * 2, pack), writer=WRITER, out=tmp_path, max_calls=40)
    assert s["stop_reason"] == "S4:early_systematic_failure" and s["prefixes_done"] == 5
    assert s["envelopes"] == dict(ok=2, writer_failed=3)


def test_wall_clock_stop(tmp_path):
    plan, ctxs, packs, pack = setup(3)
    t = iter([0, 0, 8000, 8000, 8000])
    s = PL.run_pilot(plan, ctxs, packs, gen([GOOD] * 3, pack), writer=WRITER, out=tmp_path, max_calls=40,
                     clock=lambda: next(t))
    assert s["stop_reason"] == "S5:wall_clock" and s["calls"]["total"] == 1


def test_inputs_must_match_the_plan_and_the_counted_tokens(tmp_path):
    plan, ctxs, packs, pack = setup(2)
    bad = dict(packs, p2=dict(pack, pack_sha256="0" * 64))
    with pytest.raises(PL.PilotStopped, match="S1:inputs"):
        PL.run_pilot(plan, ctxs, bad, gen([GOOD], pack), writer=WRITER, out=tmp_path / "a", max_calls=40)
    assert not (tmp_path / "a" / "calls.jsonl").exists()

    def wrong_tokens(msgs, p):
        return dict(text=GOOD, output_tokens=1, finish_reason="stop", input_tokens=p["input_tokens"] + 1, seconds=0)
    s = PL.run_pilot(plan, ctxs, packs, wrong_tokens, writer=WRITER, out=tmp_path / "b", max_calls=40)
    assert s["stop_reason"] == "S1:input_token_mismatch" and s["prefixes_done"] == 0


@pytest.mark.parametrize("change,field", [
    (dict(plan_sha256="0" * 64), "plan_sha256"), (dict(authorized_by="WS-B codex"), "authorized_by"),
    (dict(max_calls=41), "max_calls"), (dict(gpu_uuid="GPU-other"), "gpu_uuid"), (dict(paid_api_calls=1), "paid_api_calls"),
    (dict(granted_at=""), "granted_at"), (dict(scope="other"), "scope")])
def test_authorization_is_bound_to_plan_caps_and_card(change, field):
    plan = dict(task_id="B1_needcard_pilot_v1", plan_sha256="f" * 64)
    ok = dict(authorized_by="researcher", granted_at="2026-11-18T10:00:00Z", scope=plan["task_id"],
              plan_sha256=plan["plan_sha256"], max_calls=40, gpu_uuid="GPU-a6000", paid_api_calls=0)
    PL.check_authorization(ok, plan, gpu_uuid="GPU-a6000")
    with pytest.raises(PL.PilotStopped, match=field):
        PL.check_authorization(dict(ok, **change), plan, gpu_uuid="GPU-a6000")


# ------------------------------------------------------------------ audit + freeze

def audited(tmp_path, answers_by_card, fix=None):
    plan, ctxs, packs, pack = setup(len(answers_by_card))
    outs = [GOOD if a != "failed" else "bad" for a in answers_by_card for _ in ((0,) if a != "failed" else (0, 1))]
    PL.run_pilot(plan, ctxs, packs, gen(outs, pack), writer=WRITER, out=tmp_path, max_calls=40)
    raw = lines(tmp_path / "envelopes.jsonl")
    import importlib.util                                              # the audit script's on-disk loader
    spec = importlib.util.spec_from_file_location(
        "audit_script", Path(__file__).resolve().parents[1] / "scripts/rl1v3/B1_needcard_pilot_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    env = mod.load_envelopes(tmp_path / "envelopes.jsonl")
    rows = A.prepare(env)
    for r, a in zip(rows, answers_by_card):
        if a != "failed":
            r["answers"] = dict({k: "yes" for k in A.CHECKS}, **a)
            r["reviewer"] = "wsb-dev-audit"
            r["fix_reason"] = (fix or {}).get(r["prefix_id"]) if any(v != "yes" for v in a.values()) else None
    return env, rows, raw


def test_audit_verdicts_are_derived_and_rs_need_is_not_gold(tmp_path):
    env, rows, _ = audited(tmp_path, [{}, {"optional_not_mislabeled": "no"}, {"state_not_confused": "no"},
                                      {"method_need_supported": "cannot_judge"}, "failed"])
    with pytest.raises(ValueError, match="fix reason"):
        A.report(rows)
    for r in rows[1:4]:
        r["fix_reason"] = "reviewer note"
    rep = A.report(rows)
    assert [x["verdict"] for x in rep["rows"]] == ["valid", "tier_error", "evidence_error", "cannot_judge", "writer_failed"]
    assert rep["counts"]["writer_failed"] == 1 and rep["evidence_error_rate"] == pytest.approx(1 / 4)
    assert rep["gate_passed"] is False and rep["checklist_eligible"] == [rows[0]["prefix_id"]]
    assert rows[0]["facts"]["rs_head_need_is_gold_for_get_rs"] is False and rep["rs_method_need_is_gold_for_get_rs"] is False
    assert "40-card audit" in rep["scope"]


def test_freeze_only_valid_cards_and_only_before_candidates(tmp_path):
    env, rows, _ = audited(tmp_path / "run", [{}])
    rep = A.report(rows)
    assert rep["gate_passed"]
    ledger = ChecklistLedger(tmp_path / "ledger")
    frozen = A.freeze_checklists(rep, env, ledger, CW3.build)
    pid = rows[0]["prefix_id"]
    assert frozen[pid]["writer_identity"] == CW3.writer_identity() and ledger.frozen(pid)
    ledger.register_candidate(pid, "k" * 64, "r" * 64)
    with pytest.raises(ChecklistOrderError):
        ledger.freeze(CW3.build(env[0]["needcard"], method_evidence=tuple(env[0]["method_evidence"])), env[0]["needcard"])
    failing = dict(rep, gate_passed=False)
    with pytest.raises(ValueError, match="gate"):
        A.freeze_checklists(failing, env, ChecklistLedger(tmp_path / "l2"), CW3.build)


# ------------------------------------------------------------------ NeedCards never reach PM / G inputs

def test_pm_and_g_packages_never_import_needcard_checklist_or_judge_code():
    bad = []
    for pkg in ("env", "render", "policies", "train", "generator", "retrieve"):
        for f in (SRC / pkg).glob("*.py"):
            for node in ast.walk(ast.parse(f.read_text())):
                mods = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                        [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                bad += [f"{pkg}/{f.name}:{m}" for m in mods
                        if any(m.split(".")[i:i + 1] == [x] for x in ("needs", "checklist", "judge") for i in range(4))]
    assert not bad, bad
