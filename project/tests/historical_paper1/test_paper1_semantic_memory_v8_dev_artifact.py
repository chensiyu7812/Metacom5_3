import json
from pathlib import Path

from metacom_pm.io import sha256_file
from metacom_pm.paper1.semantic_memory.evidence_v8 import (
    METypedEvidence,
    MPTypedEvidence,
)


PROJECT = Path(__file__).resolve().parents[2]
MATRIX = (
    PROJECT
    / "data/paper1_authority/paper1_semantic_memory_v8_dev_matrix_20260820_v1.jsonl"
)
SUMMARY = (
    PROJECT
    / "data/paper1_authority/paper1_semantic_memory_v8_dev_results_20260820_v1.json"
)


def _rows():
    return [json.loads(line) for line in MATRIX.read_text(encoding="utf-8").splitlines()]


def test_v8_dev_artifact_is_exact_old_dev_scope_and_contains_no_model_verdict():
    rows = _rows()
    assert len(rows) == 32
    assert {row["memory_class"] for row in rows} == {"MP", "ME"}
    assert len({row["memory_id"] for row in rows}) == 32
    for row in rows:
        assert row["outcome_calls"] == 0
        evidence = row["v8_typed_evidence"]
        if evidence is None:
            assert row["mismatch_reason"] in {"SCHEMA_REJECT", "CALL_FAILURE"}
            continue
        assert "accepted" not in evidence
        assert "reason" not in evidence
        if row["memory_class"] == "MP":
            MPTypedEvidence.model_validate(evidence)
        else:
            METypedEvidence.model_validate(evidence)


def test_v8_dev_summary_binds_matrix_and_stops_before_401():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["identity"]["matrix_sha256"] == sha256_file(MATRIX)
    assert summary["counts"]["items"] == 32
    assert summary["counts"]["source_sessions"] == 29
    assert summary["counts"]["provider_call_successes"] == 29
    assert summary["counts"]["provider_call_failures"] == 0
    assert summary["cost"]["hard_cap_usd"] == "0.25"
    assert float(summary["cost"]["accounted_usd"]) <= 0.25
    assert summary["full_401_started"] is False
    assert summary["new_catalog_created"] is False
    assert summary["heldout_ids_frozen"] is False
    assert summary["outcome_calls"] == 0
    assert set(summary["locks"].values()) == {"CLOSED"}
