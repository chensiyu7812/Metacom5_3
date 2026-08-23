import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
AUDIT = PROJECT / "data/paper1_authority/paper1_semantic_memory_v8_data_quality_audit_20260823_v1.json"
ARTIFACT = PROJECT / "reports/paper1_semantic_memory_v8_dev_audit_20260823/artifact.json"


def test_v8_data_quality_audit_is_bounded_and_outcome_blind():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "DEV_DIAGNOSIS_COMPLETE_V9_LIVE_NOT_AUTHORIZED"
    assert audit["source_identity"]["rows"] == 32
    assert audit["source_identity"]["unique_memory_ids"] == 32
    assert audit["new_human_ratings_performed"] == 0
    assert audit["provider_calls"] == 0
    assert audit["outcome_calls"] == 0
    assert audit["full_401_authorized"] is False
    assert set(audit["locks"].values()) == {"CLOSED"}
    assert audit["trust_assessment"]["ms_qualification"].startswith("NOT_ASSESSED")


def test_v8_data_quality_audit_records_general_not_item_specific_repairs():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    domains = {row["issue_domain"] for row in audit["v9_general_repairs"]}
    assert domains >= {
        "mp_support_relation_collapse",
        "mp_persistence_basis_missing",
        "me_semantic_order_span_topology_conflation",
        "schema_enum_conformance",
    }
    serialized = json.dumps(audit["v9_general_repairs"])
    assert "smu_" not in serialized


def test_portable_report_artifact_has_required_technical_sections_and_chart():
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["surface"] == "report"
    assert artifact["snapshot"]["status"] == "ready"
    assert len(artifact["snapshot"]["datasets"]["items"]) == 32
    assert artifact["manifest"]["charts"][0]["type"] == "stackedBar"
    bodies = "\n".join(
        block.get("body", "") for block in artifact["manifest"]["blocks"]
    )
    for heading in (
        "# Paper-1 Semantic Memory v8 DEV Data-Quality Audit",
        "## Technical Summary",
        "## Key Findings",
        "## Scope and Definitions",
        "## Methodology",
        "## Limitations and Robustness",
        "## Recommended Next Steps",
        "## Further Questions",
    ):
        assert heading in bodies
