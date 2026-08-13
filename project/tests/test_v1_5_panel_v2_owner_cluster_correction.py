from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_panel_v2_owner_cluster_correction_and_roadmap_v1.json"


def _read() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_owner_cluster_violations_are_disclosed_with_exact_case_ids():
    violations = _read()["owner_cluster_violation"]
    mp = violations["mp_panel"]["violations"]
    assert {v["owner"] for v in mp} == {"evo::p2", "evo::p9"}
    rs_ms = violations["rs_ms_panel_v2"]["violations"]
    assert rs_ms[0]["owner"] == "evo::p1"
    assert len(rs_ms[0]["case_ids"]) == 2


def test_mp_is_inconclusive_not_a_head_failure():
    status = _read()["corrected_status"]["MP"]
    assert status["corrected_label"] == "PANEL_TREATMENT_INTERFACE_INCONCLUSIVE"
    assert "a formal MP head failure" in status["explicitly_not"]


def test_ms_is_subgate_positive_not_full_promotion():
    status = _read()["corrected_status"]["MS"]
    assert status["corrected_label"] == "FUNCTION_SUBGATE_POSITIVE"
    assert "full development_promotion" in status["explicitly_not"]
    assert "MS_pass" in status["explicitly_not"]


def test_six_step_roadmap_present_and_only_step_1_2_active():
    roadmap = _read()["six_step_roadmap"]
    assert set(roadmap) == {
        "step_1_correction",
        "step_2_blind_review_manifest",
        "step_2_5_v2_manifest_and_frozen_gate",
        "step_3_root_fix_mp",
        "step_4_selector_honesty",
        "step_5_formal_chain",
        "step_6_me_bounded_rescue",
    }
    assert roadmap["step_2_blind_review_manifest"]["status"] == "SUPERSEDED_BY_STEP_2_5_V2_MANIFEST"
    for key in ("step_3_root_fix_mp", "step_4_selector_honesty", "step_5_formal_chain", "step_6_me_bounded_rescue"):
        assert roadmap[key]["status"] == "NOT_STARTED"


def test_forbidden_reinterpretations_cover_both_corrected_labels():
    forbidden = " ".join(_read()["forbidden_reinterpretations"])
    assert "FUNCTION_SUBGATE_POSITIVE" in forbidden
    assert "PANEL_TREATMENT_INTERFACE_INCONCLUSIVE" in forbidden


def test_authorization_is_zero_api():
    auth = _read()["authorization"]
    assert auth["api_calls"] == 0
    assert auth["judge_calls"] == 0
    assert auth["external_execution"] is False
