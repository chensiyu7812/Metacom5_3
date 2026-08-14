from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/v1_5/203l_audit_paper1_v3_g3_candidate_surface_v1_5.py"


def _module():
    spec = importlib.util.spec_from_file_location("paper1_v3_g3_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_g3_candidate_surface_passes_structural_and_leakage_gates():
    diagnostics, report = _module().build_audit()
    assert report["status"] == (
        "G3_CANDIDATE_SURFACE_PASS_MP_MS_G4_PACKET_DESIGN_READY_ME_PROVISIONAL"
    )
    assert report["failed_checks"] == []
    assert all(report["structural_checks"].values())
    assert len(diagnostics) == 4689 * 3
    assert all(row["suitability_label"] is None for row in diagnostics)
    assert report["api_calls"] == 0
    assert report["labels_created"] == 0
    assert report["pm_fit"] is False


def test_component_decisions_remain_nonexclusive_at_the_same_state():
    diagnostics, report = _module().build_audit()
    by_state = {}
    for row in diagnostics:
        if row["candidate_present"]:
            by_state.setdefault(row["state_id"], set()).add(row["component"])
    all_three = [state for state, components in by_state.items() if components == {"MP", "MS", "ME"}]
    assert len(all_three) == 93
    assert report["counts"]["co_presence"]["MP+MS+ME"] == 93
    for state_id in all_three:
        assert sum(row["state_id"] == state_id for row in diagnostics) == 3


def test_ms_historical_failure_modes_are_retained_as_unlabeled_strata():
    diagnostics, report = _module().build_audit()
    ms_present = [
        row for row in diagnostics if row["component"] == "MS" and row["candidate_present"]
    ]
    assert len(ms_present) == 4442
    assert sum(bool(row["atomic_single_seeker_turn"]) for row in ms_present) == 4442
    assert sum(bool(row["low_information_rank1"]) for row in ms_present) == 21
    assert sum(bool(row["exact_or_containment_current_echo"]) for row in ms_present) == 32
    assert all(row["proxy_flags_are_not_labels"] is True for row in ms_present)
    assert report["head_decisions"]["MS"].startswith("G4_PACKET_DESIGN_READY")


def test_mp_is_stratified_and_me_stays_provisional():
    _, report = _module().build_audit()
    assert report["diagnostics"]["MP"]["field_counts"] == {
        "age": 14,
        "education": 150,
        "gender": 11,
        "job": 575,
        "location": 89,
        "nationality": 7,
    }
    assert report["diagnostics"]["MP"]["exact_profile_value_already_visible"] == 12
    assert report["counts"]["components"]["ME"]["connected_groups_with_present_candidate"] == 15
    assert report["counts"]["components"]["ME"]["reuse"]["unique_candidates"] == 23
    assert report["diagnostics"]["ME"]["typed_action_and_result_exact"] == 417
    assert report["diagnostics"]["ME"]["compiler_valid"] == 417
    assert "PROVISIONAL" in report["head_decisions"]["ME"]


def test_html_report_is_answer_first_and_records_no_labels_or_api():
    module = _module()
    _, report = module.build_audit()
    html = module._render_html(report)
    assert "MP 与 atomic MS 可以进入 G4 标注包设计" in html
    assert "all-memory co-present states" in html
    assert "API calls=0" in html
    assert "labels created=0" in html
