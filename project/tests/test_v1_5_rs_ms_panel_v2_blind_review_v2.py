from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_blind_review_manifest_v2_20260813"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_rs_ms_panel_v2_blind_review_v2_execution_phase_v1.json"
GATE = ROOT / "data/pm_v1_5_contracts/paper1_rs_ms_panel_v2_blind_review_v2_development_gate_v1.json"
CLOSEOUT_TEMPLATE = ROOT / "data/pm_v1_5_contracts/paper1_rs_ms_panel_v2_blind_review_v2_closeout_template_v1.json"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_v2_call_totals_and_cost_match_spec():
    report = _read(MANIFEST_OUT / "report.json")
    counts = report["call_counts"]
    assert counts["quality_total"] == 25
    assert counts["risk_total"] == 50
    assert counts["function_total"] == 26
    assert counts["total"] == 101
    assert report["estimated_usd"] == 1.1735
    assert all(report["checks"].values())


def test_old_v1_identity_is_registered_superseded_and_unused():
    manifest = _read(RELEASE_MANIFEST)
    stale = manifest["stale_unapproved_dry_runs"]["paper1_rs_ms_panel_v2_blind_review_v1_89call"]
    assert stale["run_identity"] == "4ee5607d47e9285860464fb8e47b933a22289a90d1f72482386155d332b6a600"
    assert stale["paid_execution_authorized"] is False
    assert stale["stale_without_consumption"] is True
    approvals = manifest.get("stage_approvals") or {}
    assert "paper1_rs_ms_panel_v2_blind_review_v1" not in approvals


def test_execution_phase_binds_every_required_hash():
    phase = _read(PHASE)
    for binding in phase["input_bindings"] + phase["implementation_bindings"]:
        assert _sha(ROOT / binding["path"]) == binding["sha256"], binding["role"]
    schema_bindings = phase["schema_bindings"]
    assert all(v.startswith(("REPLACED", "PLACEHOLDER")) is False for v in schema_bindings.values())
    execution = phase["execution"]
    assert execution["temperature"] == 0.0
    assert execution["max_output_tokens"] == 500
    assert execution["absolute_usd_cap"] == 1.35
    assert execution["run_identity"] == "c6426edaae0e1db5f2b1ed66ee91a895ea2ef2173df078ad53db0c1df290f0f4"


def test_runner_contract_names_the_provider_safe_boundary():
    runner_contract = _read(PHASE)["runner_contract"]
    assert set(runner_contract["provider_safe_keys"]) == {
        "messages", "temperature", "max_output_tokens", "seed", "schema_sha256",
    }
    assert "case_id" in runner_contract["forbidden_from_provider_payload"]
    assert "arm" in runner_contract["forbidden_from_provider_payload"]
    assert "owner_cluster" in runner_contract["forbidden_from_provider_payload"]


def test_stop_rules_cover_cost_cap_and_consecutive_failures():
    stop_rules = " ".join(_read(PHASE)["stop_rules"])
    assert "absolute_usd_cap" in stop_rules
    assert "5 consecutive" in stop_rules
    assert "resumable" in stop_rules


def test_development_gate_is_frozen_before_any_call():
    gate = _read(GATE)
    assert gate["status"] == "FROZEN_BEFORE_ANY_JUDGE_CALL"
    assert gate["scope_limitation"]["current_user_text_only"] is True
    criteria = gate["criteria"]
    assert set(criteria) == {
        "rs_quality", "ms_quality", "rs_risk", "ms_risk",
        "rs_function", "ms_function", "ms_rs_interaction", "ms_rs_combined_risk",
    }


def test_gate_forbids_significance_claims_and_post_hoc_changes():
    forbidden = " ".join(_read(GATE)["forbidden"])
    assert "significance test" in forbidden
    assert "after seeing results" in forbidden
    assert "formal external-test pass" in forbidden


def test_closeout_template_has_no_filled_result_values():
    template = _read(CLOSEOUT_TEMPLATE)
    assert template["status"].startswith("TEMPLATE_NOT_A_RESULT")
    fields = template["fields_to_fill"]
    assert fields["verdict"]["label"] is None
    assert all(v is None for v in fields["criteria"].values())
