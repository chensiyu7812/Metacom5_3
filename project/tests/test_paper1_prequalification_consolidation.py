import hashlib
import json
from pathlib import Path

import yaml


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parent


def _json(relative):
    return json.loads((PROJECT / relative).read_text(encoding="utf-8"))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_master_register_uses_only_closed_status_vocabulary():
    register = _json("data/paper1_authority/paper1_master_decision_register_20260820_v1.json")
    allowed = set(register["allowed_statuses"])
    assert allowed == {
        "FROZEN",
        "READY",
        "EXPERIMENT_REQUIRED",
        "AUDIT_REQUIRED",
        "IMPLEMENTATION_PENDING",
        "BLOCKED",
    }
    assert register["status"] in allowed
    assert all(item["status"] in allowed for item in register["decisions"])
    ready = {item["id"]: item for item in register["decisions"]}
    assert ready["ESC_split_large_52"]["status"] == "FROZEN"
    assert ready["RQ2_outer_folds_K5_seed0"]["status"] == "FROZEN"
    assert "seed changes forbidden" in ready["ESC_split_large_52"]["evidence"]
    assert "seed changes forbidden" in ready["RQ2_outer_folds_K5_seed0"]["evidence"]


def test_four_outcome_locks_are_independently_closed():
    config = yaml.safe_load((PROJECT / "configs/paper1_public_only.yaml").read_text())
    for key in (
        "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
        "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
        "RQ1_CONFIRMATORY_OUTCOME_LOCK",
        "RQ2_CONFIRMATORY_OUTCOME_LOCK",
    ):
        assert config[key]["status"] == "CLOSED"
        assert not any(value is True for field, value in config[key].items() if field.endswith("allowed"))


def test_canonical_top8_artifacts_are_hash_bound_and_complete():
    report = _json("data/paper1_public_rs/esconv_rs_canonical_bge_top8_report_v1.json")
    catalog = PROJECT / "data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl"
    top8 = PROJECT / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_v1.jsonl"
    assert report["counts"] == {
        "raw_atomic_units": 15061,
        "exact_canonical_treatments": 13172,
        "exact_alias_instances_beyond_first": 1889,
        "decision_states": 11883,
    }
    assert _sha(catalog) == report["identities"]["canonical_catalog_sha256"]
    assert _sha(top8) == report["identities"]["canonical_top8_sha256"]
    for k in (1, 2, 3, 4, 6, 8):
        cell = report["k_surface"][str(k)]
        assert cell["coverage"] == 1.0
        assert cell["truncation_rate_common_cap384"] == 0.0
    assert report["compute"]["outcome_calls"] == 0
    assert report["compute"]["Generator_calls"] == 0


def test_qualification_packets_are_unjudged_and_isolated():
    rs = _json("data/paper1_authority/paper1_rs_resource_semantics_qualification_packet_20260820_v1.json")
    assert len(rs["rows"]) == 64
    assert {row["source_split"] for row in rs["rows"]} == {"validation"}
    assert all(row["human_review"] is None for row in rs["rows"])
    assert rs["human_judgments_completed"] == 0
    assert rs["outcome_calls"] == 0
    ms = _json("data/paper1_authority/paper1_ms_semantic_audit_packet_20260820_v1.json")
    assert len(ms["rows"]) == 48
    assert all(row["human_labels"] is None for row in ms["rows"])
    assert ms["outcome_calls"] == 0


def test_memory_precision_artifact_does_not_claim_live_v7_success():
    precision = _json("data/paper1_authority/paper1_semantic_memory_precision_repair_v7_20260820.json")
    regression = _json("data/paper1_authority/paper1_semantic_memory_old_dev_regression_v7_20260820.json")
    results = _json("data/paper1_authority/paper1_semantic_memory_v7_dev_live_results_20260820_v1.json")
    assert precision["status"] == "DEV_REGRESSION_FAILED_401_NOT_RUN"
    assert precision["live_dev_execution"]["full_401_started"] is False
    assert precision["live_dev_execution"]["new_catalog_created"] is False
    assert regression["scope"] == "DEV_EXPECTATION_AND_GENERIC_GATE_COVERAGE_ONLY_NOT_HELDOUT_QUALIFICATION"
    assert all(row["live_qwen_v7_result"] is None for row in regression["rows"])
    assert regression["outcome_calls"] == 0
    assert results["status"] == "DEV_REGRESSION_FAILED_STOP_BEFORE_401"
    assert results["execution_stop"]["outcome_calls"] == 0


def test_root_authority_lists_new_scoped_amendment_first():
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    first = "project/docs/PM_PAPER1_PREQUALIFICATION_CONSOLIDATION_AMENDMENT_20260820_ZH.md"
    prior = "project/docs/PM_PAPER1_RESOURCE_AMOUNT_AND_EVALUATOR_CALIBRATION_AMENDMENT_20260820_ZH.md"
    assert agents.index(first) < agents.index(prior)
