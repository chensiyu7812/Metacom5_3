import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parent
AUTHORITY = PROJECT / "data/paper1_authority"


def _json(name: str):
    return json.loads((AUTHORITY / name).read_text(encoding="utf-8"))


def test_official_compatibility_amendment_is_pre_outcome_and_scoped():
    amendment = _json("paper1_official_esc_eval_compatibility_amendment_20260902_v1.json")
    assert amendment["status"] == "ACTIVE_RESEARCHER_AUTHORIZED_SCOPED_AMENDMENT_PRE_OUTCOME"
    assert amendment["researcher_approval"]["formal_outcomes_observed_before_approval"] == 0
    assert amendment["researcher_approval"]["PM_training_runs_before_approval"] == 0
    assert set(amendment["locks"].values()) == {"CLOSED"}
    assert amendment["authorization_boundary"] == {
        "zero_outcome_evaluator_qualification_allowed": True,
        "formal_ESC_Eval_allowed": False,
        "calibration_outcome_allowed": False,
        "confirmatory_outcome_allowed": False,
        "PM_training_allowed": False,
    }


def test_official_parser_is_primary_and_strict_parser_is_diagnostic_only():
    amendment = _json("paper1_official_esc_eval_compatibility_amendment_20260902_v1.json")
    binding = amendment["parser_binding"]
    assert binding["primary"].startswith("iterate labels 0,1,2,3,4")
    assert binding["strict_full_string_parser"] == "SUPPLEMENTAL_DIAGNOSTIC_ONLY"
    assert binding["multiple_label_conflict_check"].startswith("SUPPLEMENTAL_DIAGNOSTIC_ONLY")
    assert amendment["runtime_evidence_before_amendment"]["strict_full_string_valid"] == 0
    assert amendment["runtime_evidence_before_amendment"]["official_parser_valid"] == 42


def test_proxy_judges_cannot_replace_official_rq1_scorer():
    protocol = _json("paper1_esc_evaluator_prequalification_protocol_20260902_v3.json")
    assert protocol["official_main_scorer_replaceable_by_proxy"] is False
    assert protocol["selection_rule"]["official_ESC_RANK_remains_main"] is True
    assert all(
        "supplemental" in candidate["role"]
        for candidate in protocol["candidate_set"]
        if candidate["candidate"] != "ESC-RANK"
    )


def test_patch_manifest_binds_exact_official_parser_and_auxiliary_dependencies():
    manifest = _json("paper1_esc_rank_24gib_patch_manifest_20260902_v2.json")
    assert manifest["official_parser"]["label_order"] == ["0", "1", "2", "3", "4"]
    assert "official parser semantics" in manifest["forbidden_patches"]
    assert manifest["auxiliary_runtime_pins"] == {
        "einops": "0.8.1",
        "sentencepiece": "0.2.1",
        "protobuf": "5.29.5",
    }


def test_root_authority_lists_official_compatibility_before_base_authority():
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    official = agents.index("PM_PAPER1_OFFICIAL_ESC_EVAL_COMPATIBILITY_AMENDMENT_20260902_ZH.md")
    threshold = agents.index("PM_PAPER1_THRESHOLD_POLICY_CALIBRATION_AMENDMENT_20260831_ZH.md")
    reconciliation = agents.index("PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md")
    assert official < threshold < reconciliation
