"""Historical 2026-08-20 prequalification tests; excluded from routine CI."""

import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]


def _json(relative):
    return json.loads((PROJECT / relative).read_text(encoding="utf-8"))


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
