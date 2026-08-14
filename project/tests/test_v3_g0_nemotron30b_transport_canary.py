from __future__ import annotations

import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"
RUNNER = PROJECT_ROOT / "scripts" / "v3" / "19_run_g0_nemotron30b_transport_canary.py"


def _json(name: str) -> dict:
    return json.loads((AUTHORITY / name).read_text(encoding="utf-8"))


def _module():
    spec = importlib.util.spec_from_file_location("nemotron_canary", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrong_70b_route_is_explicitly_removed_without_erasing_evidence() -> None:
    correction = _json("g0_wrong_70b_reference_correction_v1.json")
    assert correction["status"] == "CORRECTED_70B_REMOVED_FROM_CANDIDATE_SET_RAW_EVIDENCE_RETAINED"
    assert correction["correction"]["wrong_route"] == "meta/llama-3.3-70b-instruct"
    assert correction["correction"]["intended_route"] == "nvidia/nemotron-3-nano-30b-a3b"
    assert correction["evidence_policy"]["delete_private_raw_evidence"] is False


def test_nemotron_preflight_is_zero_call_uncapped_and_identity_bound() -> None:
    contract = _json("g0_nemotron30b_transport_canary_contract_v1.json")
    report = _json("g0_nemotron30b_transport_canary_preflight_v1.json")
    assert report["status"] == "ZERO_CALL_PREFLIGHT_PASS_EXECUTION_REQUIRES_IDENTITY_SPECIFIC_APPROVAL"
    assert report["api_calls"] == 0
    assert report["model"] == contract["candidate"]["model"] == "nvidia/nemotron-3-nano-30b-a3b"
    assert report["logical_supporter_calls"] == 10
    assert report["maximum_cost_usd"] == 0
    assert report["run_identity"] == "92bd2e530a22525ad7a8afc6daff1d6d178faad42c9c6dbd01349eeba5f740bc"
    assert contract["same_surface_lock"]["researcher_output_token_cap"] is None


def test_operational_gate_separates_rate_limit_instability_and_slowness() -> None:
    contract = _json("g0_nemotron30b_transport_canary_contract_v1.json")
    taxonomy = contract["diagnostic_taxonomy"]
    assert "HTTP 429" in taxonomy["explicit_rate_limit"]
    assert "HTTP 5xx" in taxonomy["route_instability"]
    assert contract["operational_retention_gate"]["explicit_429_physical_attempts_maximum"] == 0
    assert contract["operational_retention_gate"]["successful_request_p90_latency_seconds_maximum"] == 30.0

    runner = _module()
    assert runner._early_stop_reason([
        {"event": "supporter_failed", "failure_class": "rate_limited_429"},
        {"event": "supporter_failed", "failure_class": "rate_limited_429"},
    ]) == "TWO_EXPLICIT_HTTP_429_ATTEMPTS"
    assert runner._early_stop_reason([
        {"event": "supporter_succeeded", "latency_ms": 46_000},
        {"event": "supporter_succeeded", "latency_ms": 47_000},
        {"event": "supporter_succeeded", "latency_ms": 48_000},
    ]) == "THREE_SUCCESS_MEDIAN_ABOVE_45_SECONDS"
