from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"


def _report() -> dict:
    return json.loads((AUTHORITY / "g0_nemotron30b_transport_canary_closeout_v1.json").read_text(encoding="utf-8"))


def test_nemotron_route_passes_only_the_frozen_operational_gate() -> None:
    report = _report()
    assert report["run_identity"] == "92bd2e530a22525ad7a8afc6daff1d6d178faad42c9c6dbd01349eeba5f740bc"
    assert report["status"] == "OPERATIONAL_RETENTION_GATE_PASS_QUALITY_NOT_JUDGED_NO_GENERATOR_SELECTED"
    assert report["api_scope"]["supporter_successful_turns"] == 10
    assert report["transport"]["explicit_http_429_attempts"] == 0
    assert report["frozen_gate_evaluation"]["all_operational_thresholds_pass"] is True
    assert report["decision"] == {
        "candidate_retained": True,
        "candidate_deleted_from_g0": False,
        "next_role": "Provisional candidate for a larger same-surface Quality/Risk/latency comparison against Llama 3.1 8B and Qwen 3.7 Plus.",
        "quality_judged": False,
        "generator_selected": False,
        "reason": "The canary answered only transport, completion, and latency questions; two development cards cannot establish emotional-support quality or model superiority."
    }


def test_public_nemotron_closeout_is_text_free_and_does_not_invent_reasoning_tokens() -> None:
    report = _report()
    rendered = json.dumps(report, ensure_ascii=False).lower()
    assert "seeker_text" not in rendered and "supporter_text" not in rendered
    assert report["generation"]["provider_reported_reasoning_token_count_available"] is False
    assert report["generation"]["provider_default_reasoning_present_turns"] == 10
    assert all(len(value) == 64 for value in report["private_evidence_hashes"].values())
