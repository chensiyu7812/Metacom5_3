from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json"
REGISTRY = ROOT / "data/pm_v1_5_contracts/paper1_experiment_version_registry_v1.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_function_v2_is_observable_and_not_latent_chain_of_thought() -> None:
    contract = _read(CONTRACT)
    function = contract["function_observability_v2"]
    assert function["development_decision_rule"]["standalone_binary_function_count_gate"] is False
    assert set(function["layers"]["observable_contribution"]["labels"]) == {
        "CLEAR", "PLAUSIBLE", "NONE", "UNCERTAIN"
    }
    assert "not automatic failure" in function["layers"]["observable_contribution"]["labels"]["UNCERTAIN"]
    assert any("hidden chain of thought" in item for item in function["layers"]["observable_contribution"]["prohibitions"])


def test_old_review_and_old_56_call_panel_cannot_gate_or_execute() -> None:
    contract = _read(CONTRACT)
    addendum = contract["amends"]["baseline_and_generator_addendum_v1"]
    review = contract["historical_evidence_disposition"]["claimed_use_review"]
    panel = contract["historical_evidence_disposition"]["existing_four_arm_panel"]
    assert _sha(ROOT / addendum["path"]) == addendum["sha256"]
    assert _sha(ROOT / review["path"]) == review["sha256"]
    assert "a standalone development blocker" in review["forbidden_use"]
    assert panel["current_disposition"] == "DO_NOT_EXECUTE_AS_MS_SCIENTIFIC_QUALIFICATION"
    assert "withdrawn" in panel["authorization"]
    retired_script = (
        ROOT / "scripts/v1_5/324l_materialize_paper1_r0_delta_four_arm_development_panel_v1_5.py"
    ).read_text(encoding="utf-8")
    assert "Historical V1 panel materializer is retired" in retired_script


def test_panel_v2_has_use_ask_ignore_and_critical_controls() -> None:
    panel = _read(CONTRACT)["panel_v2_requirements"]
    assert set(panel["minimum_strata"]) == {"CLEAR_USE", "ASK", "IGNORE"}
    assert {"wrong owner", "stale or conflicting continuity", "current-context echo"}.issubset(
        set(panel["required_negative_controls"])
    )
    assert "At least 12 states" in panel["RS_coverage"]
    assert "64" in panel["call_budget"]


def test_experiment_registry_changes_no_method_version() -> None:
    registry = _read(REGISTRY)
    assert registry["method_boundary"]["new_method_version_created"] is False
    assert registry["active_revision"] == "PANEL_V2_OWNER_CLUSTER_CORRECTION_AND_ROADMAP"
    active = next(row for row in registry["revisions"] if row["version"] == registry["active_revision"])
    assert active["live_calls_authorized"] == 0


def test_rs_ms_milestone_does_not_impersonate_full_paper1() -> None:
    claims = _read(CONTRACT)["claim_staging"]
    assert claims["first_pm_milestone"]["name"] == "SELECTIVE_RS_PLUS_MS_PM"
    assert claims["full_paper1_primary"]["predicate_unchanged"] == "RS_pass AND count_pass(MP,MS,ME) >= 2"
    assert "must be augmented or rerun" in claims["full_paper1_primary"]["consequence"]
