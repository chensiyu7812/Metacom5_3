import copy
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.evaluation.gemini_teacher import (
    MODEL, STAGE, count_requests, reported_cost, run_requests, validate_requests,
)

PROJECT = Path(__file__).resolve().parents[1]


def make_rows(n=1):
    identity = json.loads((PROJECT / "data/paper1_authority/paper1_gemini_pairwise_teacher_identity_20260908_v2.json").read_text())
    g = identity["generation"]
    config = {"maxOutputTokens": g["maxOutputTokens"], "responseJsonSchema": g["responseJsonSchema"],
              "responseMimeType": g["responseMimeType"], "seed": g["seed"],
              "temperature": g["temperature"], "thinkingConfig": g["thinking_config"]}
    rows = []
    for i in range(n):
        body = {"contents": [{"role": "user", "parts": [{"text": f"test pair {i}"}]}],
                "generationConfig": config}
        rows.append({"presentation_id": f"p{i}", "body": body, "body_sha256": sha256_text(canonical_json(body)),
                     "request_model": MODEL, "maximum_output_tokens": 256})
    identity["exact_request_manifest"]["presentations"] = n
    return rows, identity


def good_response(version=MODEL):
    return {"modelVersion": version, "candidates": [{"finishReason": "STOP", "content": {
        "parts": [{"text": '{"verdict":"equivalent","rationale":"Same answer."}'}]}}],
        "usageMetadata": {"promptTokenCount": 18, "candidatesTokenCount": 11}}


class Transport:
    def __init__(self, replies=None):
        self.replies = list(replies or [good_response()])
        self.generations = []
        self.counts = 0

    def __call__(self, request):
        if request.method == "GET":
            return httpx.Response(200, json={"name": f"models/{MODEL}", "version": "001",
                "inputTokenLimit": 1048576, "supportedGenerationMethods": ["generateContent", "countTokens"]})
        if request.url.path.endswith(":countTokens"):
            self.counts += 1
            assert "generateContentRequest" in json.loads(request.content)
            return httpx.Response(200, json={"totalTokens": 18})
        assert request.url.path.endswith(":generateContent")
        self.generations.append(json.loads(request.content))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": {"code": reply}})
        return httpx.Response(200, json=reply)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("metacom_pm.paper1.evaluation.gemini_teacher.time.sleep", lambda _: None)
    def create(replies=None, n=1):
        rows, _ = make_rows(n)
        transport = Transport(replies)
        client = httpx.Client(transport=httpx.MockTransport(transport))
        provider = count_requests(client, rows, tmp_path / "run")
        ledger = CumulativePaper1ApiBudgetLedger(tmp_path / "budget.jsonl", opening_cost_usd=Decimal("0"))
        return rows, transport, client, provider, ledger, tmp_path / "run"
    return create


def test_default_runner_cannot_spend_without_authorization(setup):
    rows, transport, client, provider, ledger, out = setup()
    with pytest.raises(PermissionError):
        run_requests(client, rows, provider, ledger, out)
    assert transport.generations == []
    assert not ledger.path.exists()


def test_provider_preflight_is_cached_and_never_generates(setup):
    rows, transport, client, provider, ledger, out = setup(n=2)
    again = count_requests(client, rows, out)
    assert transport.counts == 2
    assert transport.generations == []
    assert provider == again
    assert not ledger.path.exists()


def test_success_resume_never_rebills_and_keeps_exact_body(setup):
    rows, transport, client, provider, ledger, out = setup()
    first = run_requests(client, rows, provider, ledger, out, authorized=True)
    spent = ledger.accounted_cost_usd
    resumed_ledger = CumulativePaper1ApiBudgetLedger(ledger.path, opening_cost_usd=Decimal("0"))
    second = run_requests(client, rows, provider, resumed_ledger, out, authorized=True)
    assert first == second
    assert first[0]["status"] == "SUCCEEDED"
    assert transport.generations == [rows[0]["body"]]
    assert resumed_ledger.accounted_cost_usd == spent


@pytest.mark.parametrize("failure", [503, httpx.ReadTimeout("simulated timeout"), {"modelVersion": MODEL, "candidates": []}])
def test_retryable_failures_have_one_bounded_retry(setup, failure):
    rows, transport, client, provider, ledger, out = setup([failure, good_response()])
    result = run_requests(client, rows, provider, ledger, out, authorized=True)
    assert result[0]["attempts"] == 2
    assert result[0]["status"] == "SUCCEEDED"
    assert len(transport.generations) == 2
    assert len(ledger.path.read_text().splitlines()) == 4


def test_two_failures_remain_operational_and_are_not_retried_on_resume(setup):
    failure = {"modelVersion": MODEL, "candidates": []}
    rows, transport, client, provider, ledger, out = setup([failure, failure])
    result = run_requests(client, rows, provider, ledger, out, authorized=True)
    assert result[0]["parsed_verdict"] is None
    assert result[0]["verdict"] == "uncertain"
    assert result[0]["status"] == "OPERATIONAL_FAILURE"
    run_requests(client, rows, provider, ledger, out, authorized=True)
    assert len(transport.generations) == 2


def test_configuration_failure_stops_before_next_presentation(setup):
    rows, transport, client, provider, ledger, out = setup([403], n=2)
    with pytest.raises(RuntimeError, match="HTTP_403"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    assert len(transport.generations) == 1
    assert ledger.accounted_stage_cost_usd(STAGE) > 0


def test_stage_cap_blocks_call_before_transport(setup):
    rows, transport, client, provider, ledger, out = setup()
    reservation = ledger.reserve(reservation_id="existing", logical_call_id="existing", call_hash="existing",
        stage=STAGE, provider="test", model=MODEL, maximum_cost_usd=Decimal("0.10"), call_class="OPTIONAL")
    ledger.settle(reservation, actual_cost_usd=Decimal("0.10"), outcome="FAILED")
    with pytest.raises(RuntimeError, match="stage hard cap"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    assert transport.generations == []


def test_optional_teacher_retry_cannot_consume_primary_retry_reserve(setup):
    rows, transport, client, provider, ledger, out = setup([503])
    ledger = CumulativePaper1ApiBudgetLedger(ledger.path, opening_cost_usd=Decimal("42.99980"))
    with pytest.raises(RuntimeError, match="including retries"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    assert len(transport.generations) == 1


def test_interruption_after_response_before_settlement_recovers_without_call(setup, monkeypatch):
    rows, transport, client, provider, ledger, out = setup()
    monkeypatch.setattr(ledger, "settle", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated crash")))
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    reloaded = CumulativePaper1ApiBudgetLedger(ledger.path, opening_cost_usd=Decimal("0"))
    recovered = run_requests(client, rows, provider, reloaded, out, authorized=True)
    assert recovered[0]["status"] == "SUCCEEDED"
    assert len(transport.generations) == 1


def test_interruption_without_saved_response_stops_without_rebilling(setup, monkeypatch):
    rows, transport, client, provider, ledger, out = setup()
    monkeypatch.setattr("metacom_pm.paper1.evaluation.gemini_teacher.write_json",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated disk failure")))
    with pytest.raises(RuntimeError, match="disk failure"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    with pytest.raises(RuntimeError, match="do not rebill"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    assert len(transport.generations) == 1


def test_mixed_versions_fail_closed_and_keep_partial_results(setup):
    rows, transport, client, provider, ledger, out = setup([good_response(), good_response("new-version")], n=2)
    with pytest.raises(RuntimeError, match="mixed_response_model_versions"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    assert len(json.loads((out / "results.json").read_text())) == 1
    assert len(list((out / "attempts").glob('*.json'))) == 2


def test_provider_output_cap_violation_stops_even_when_total_cost_fits(setup):
    reply = good_response()
    reply["usageMetadata"]["candidatesTokenCount"] = 300
    rows, transport, client, provider, ledger, out = setup([reply])
    with pytest.raises(RuntimeError, match="token_envelope"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    assert len(transport.generations) == 1


def test_reported_thinking_is_charged_and_flagged_without_changing_request(setup):
    reply = good_response()
    reply["usageMetadata"]["thoughtsTokenCount"] = 2
    rows, transport, client, provider, ledger, out = setup([reply])
    result = run_requests(client, rows, provider, ledger, out, authorized=True)
    assert result[0]["status"] == "SUCCEEDED"
    assert result[0]["thinking_usage_despite_requested_zero"] is True
    assert result[0]["provider_reported_thinking_tokens"] == 2
    assert ledger.accounted_cost_usd == Decimal("0.0000070")
    assert transport.generations == [rows[0]["body"]]
    assert transport.generations[0]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


def test_combined_visible_and_thinking_output_cap_is_enforced(setup):
    reply = good_response()
    reply["usageMetadata"].update(candidatesTokenCount=255, thoughtsTokenCount=2)
    rows, transport, client, provider, ledger, out = setup([reply])
    with pytest.raises(RuntimeError, match="token_envelope"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    assert len(transport.generations) == 1


@pytest.mark.parametrize("bad", [-1, True, "2", 1.5])
def test_invalid_thinking_usage_cannot_be_charged_as_valid(bad):
    reply = good_response()
    reply["usageMetadata"]["thoughtsTokenCount"] = bad
    with pytest.raises(ValueError):
        reported_cost(reply)


def test_pre_repair_failed_settlement_needs_exact_reconciliation_and_never_rebills(setup, monkeypatch):
    reply = good_response()
    reply["usageMetadata"]["thoughtsTokenCount"] = 2
    rows, transport, client, provider, ledger, out = setup([reply])
    with monkeypatch.context() as patch:
        patch.setattr("metacom_pm.paper1.evaluation.gemini_teacher.reported_cost",
                      lambda _: (_ for _ in ()).throw(RuntimeError("old zero-usage assumption")))
        with pytest.raises(RuntimeError, match="provider_usage_outside_frozen_contract"):
            run_requests(client, rows, provider, ledger, out, authorized=True)
    before = ledger.path.read_bytes()
    with pytest.raises(RuntimeError, match="cached parse disagrees"):
        run_requests(client, rows, provider, ledger, out, authorized=True)
    record = json.loads(next((out / "attempts").glob("*.json")).read_text())
    rid = f"{STAGE}:p0:1"
    proof = {"call_hash": record["call_hash"], "response_sha256": record["response_sha256"],
             "reason": "saved_valid_response_rejected_by_removed_zero_thinking_usage_assumption"}
    with pytest.raises(RuntimeError, match="cached parse disagrees"):
        run_requests(client, rows, provider, ledger, out, authorized=True,
                     saved_settlement_reconciliations={rid: {**proof, "response_sha256": "wrong"}})
    result = run_requests(client, rows, provider, ledger, out, authorized=True,
                          saved_settlement_reconciliations={rid: proof})
    assert result[0]["status"] == "SUCCEEDED"
    assert result[0]["saved_settlement_reconciled_without_rebilling"] is True
    assert result[0]["attempts"] == 1
    assert ledger.path.read_bytes() == before
    assert len(transport.generations) == 1


def test_request_changes_and_duplicate_bodies_fail_closed():
    rows, identity = make_rows()
    validate_requests(rows, identity)
    rows[0]["body"]["generationConfig"]["temperature"] = 1
    with pytest.raises(ValueError, match="drifted"):
        validate_requests(rows, identity)
    rows, identity = make_rows(2)
    rows[1]["body"] = copy.deepcopy(rows[0]["body"])
    rows[1]["body_sha256"] = rows[0]["body_sha256"]
    with pytest.raises(ValueError, match="duplicate paid"):
        validate_requests(rows, identity)


def test_approval_requires_exact_plan_and_reference_scope():
    spec = importlib.util.spec_from_file_location("teacher_runner", PROJECT / "scripts/paper1/64_run_gemini_teacher_qualification.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    plan = {"provider_preflight_sha256": "provider"}
    approval = {"status": "AUTHORIZED", "researcher_approved": True,
                "reference_protocol_amendment_approved": True,
                "execution_plan_sha256": sha256_text(canonical_json(plan))}
    runner.require_authorization(approval, plan)
    with pytest.raises(PermissionError):
        runner.require_authorization({**approval, "researcher_approved": False}, plan)
    with pytest.raises(PermissionError):
        runner.require_authorization(approval, {**plan, "changed": True})
