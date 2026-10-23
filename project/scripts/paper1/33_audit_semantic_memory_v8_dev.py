#!/usr/bin/env python3
"""Build a bounded, outcome-blind data-quality audit of the frozen v8 DEV run."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT / "data/paper1_authority/paper1_semantic_memory_v8_dev_matrix_20260820_v1.jsonl"
RESULTS = PROJECT / "data/paper1_authority/paper1_semantic_memory_v8_dev_results_20260820_v1.json"
AUDIT = PROJECT / "data/paper1_authority/paper1_semantic_memory_v8_data_quality_audit_20260823_v1.json"
REPORT_ROOT = PROJECT / "reports/paper1_semantic_memory_v8_dev_audit_20260823"
ARTIFACT = REPORT_ROOT / "artifact.json"
GENERATED_AT = "2026-08-23T00:00:00+09:00"


SUMMARY_SQL = """SELECT
  COUNT(*) AS items,
  SUM(CASE WHEN old_human_label = 'PASS' THEN 1 ELSE 0 END) AS old_pass_total,
  SUM(CASE WHEN old_human_label = 'PASS' AND deterministic_v8_verdict = 'ACCEPT' THEN 1 ELSE 0 END) AS old_pass_retained,
  SUM(CASE WHEN old_human_label IN ('FAIL','REVIEW') THEN 1 ELSE 0 END) AS known_fail_review_total,
  SUM(CASE WHEN old_human_label IN ('FAIL','REVIEW') AND deterministic_v8_verdict != 'ACCEPT' THEN 1 ELSE 0 END) AS known_fail_review_rejected,
  SUM(outcome_calls) AS outcome_calls
FROM v8_dev_matrix"""

HEAD_SQL = """SELECT
  memory_class,
  COUNT(*) AS total,
  SUM(CASE WHEN mismatch_reason = 'MATCH' THEN 1 ELSE 0 END) AS match,
  SUM(CASE WHEN mismatch_reason = 'SEMANTIC_FALSE_REJECT' THEN 1 ELSE 0 END) AS false_reject,
  SUM(CASE WHEN mismatch_reason = 'SEMANTIC_FALSE_ACCEPT' THEN 1 ELSE 0 END) AS false_accept,
  SUM(CASE WHEN mismatch_reason = 'SCHEMA_REJECT' THEN 1 ELSE 0 END) AS schema_reject,
  SUM(CASE WHEN old_human_label = 'PASS' THEN 1 ELSE 0 END) AS old_pass_total,
  SUM(CASE WHEN old_human_label IN ('FAIL','REVIEW') THEN 1 ELSE 0 END) AS old_fail_review_total
FROM v8_dev_matrix
GROUP BY memory_class
ORDER BY memory_class"""

ITEM_SQL = """SELECT
  memory_class, memory_id, old_human_label, v7_verdict,
  deterministic_v8_verdict, mismatch_reason, local_gate_reason
FROM v8_dev_matrix
ORDER BY memory_class, memory_id"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_rows() -> list[dict[str, Any]]:
    return [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]


def _database(rows: list[dict[str, Any]]) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE v8_dev_matrix (
          memory_class TEXT NOT NULL,
          memory_id TEXT NOT NULL PRIMARY KEY,
          old_human_label TEXT NOT NULL,
          v7_verdict TEXT NOT NULL,
          deterministic_v8_verdict TEXT NOT NULL,
          mismatch_reason TEXT NOT NULL,
          local_gate_reason TEXT NOT NULL,
          outcome_calls INTEGER NOT NULL
        )"""
    )
    db.executemany(
        "INSERT INTO v8_dev_matrix VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                row["memory_class"],
                row["memory_id"],
                row["old_human_label"],
                row["v7_verdict"],
                row["deterministic_v8_verdict"],
                row["mismatch_reason"],
                json.dumps(row["local_gate_reason"], ensure_ascii=False),
                row["outcome_calls"],
            )
            for row in rows
        ],
    )
    return db


def _query(db: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(sql)]


def _issue_domain(row: dict[str, Any]) -> str:
    reasons = set(row["local_gate_reason"])
    if row["mismatch_reason"] == "SCHEMA_REJECT":
        return "schema_enum_conformance"
    if row["memory_class"] == "MP" and row["mismatch_reason"] == "SEMANTIC_FALSE_REJECT":
        return "mp_support_relation_collapse"
    if row["memory_class"] == "MP" and row["mismatch_reason"] == "SEMANTIC_FALSE_ACCEPT":
        return "mp_persistence_basis_missing"
    if "temporal_order_reversed_or_same" in reasons:
        return "me_semantic_order_span_topology_conflation"
    if "same_experience_linkage_unresolved" in reasons:
        return "me_experience_linkage_observation"
    if row["mismatch_reason"] == "MATCH":
        return "no_observed_mismatch"
    return "other"


def _artifact(
    summary: dict[str, Any],
    heads: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    summary_row = {
        **summary,
        "old_pass_retention_rate": summary["old_pass_retained"] / summary["old_pass_total"],
        "known_fail_review_rejection_rate": summary["known_fail_review_rejected"]
        / summary["known_fail_review_total"],
    }
    source_path = "project/data/paper1_authority/paper1_semantic_memory_v8_dev_matrix_20260820_v1.jsonl"
    sources = [
        {
            "id": "summary_source",
            "label": "Frozen v8 DEV matrix summary",
            "path": source_path,
            "query": {
                "engine": "SQLite 3 in-memory audit",
                "sql": SUMMARY_SQL,
                "description": "Counts frozen v8 DEV items and descriptive retention/rejection rates.",
                "tables_used": ["v8_dev_matrix"],
                "filters": ["none; all 32 frozen old-DEV rows"],
                "metric_definitions": [
                    "old_pass_retention_rate = old_pass_retained / old_pass_total",
                    "known_fail_review_rejection_rate = known_fail_review_rejected / known_fail_review_total",
                    "These are DEV diagnostics, not research PASS gates.",
                ],
            },
        },
        {
            "id": "head_source",
            "label": "Frozen v8 DEV mismatch counts by memory class",
            "path": source_path,
            "query": {
                "engine": "SQLite 3 in-memory audit",
                "sql": HEAD_SQL,
                "description": "Groups the frozen item matrix by MP/ME and mismatch class.",
                "tables_used": ["v8_dev_matrix"],
                "filters": ["none; MS had no items in the old DEV packet"],
                "metric_definitions": ["Each stacked segment is an item count; denominator is shown as total."],
            },
        },
        {
            "id": "item_source",
            "label": "Frozen v8 DEV item-level decisions",
            "path": source_path,
            "query": {
                "engine": "SQLite 3 in-memory audit",
                "sql": ITEM_SQL,
                "description": "Selects the bounded item-level audit fields for exact review.",
                "tables_used": ["v8_dev_matrix"],
                "filters": ["no candidate content or new human judgments included"],
                "metric_definitions": [],
            },
        },
    ]
    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "Paper-1 Semantic Memory v8 DEV Data-Quality Audit",
            "description": "Outcome-blind diagnosis of the frozen 32-item MP/ME DEV matrix.",
            "generatedAt": GENERATED_AT,
            "sources": sources,
            "cards": [
                {
                    "id": "items_card",
                    "dataset": "summary",
                    "sourceId": "summary_source",
                    "description": "All frozen old-DEV rows; no held-out or outcome data.",
                    "metrics": [{"label": "DEV items", "field": "items", "format": "number"}],
                },
                {
                    "id": "pass_retention_card",
                    "dataset": "summary",
                    "sourceId": "summary_source",
                    "description": "Previously human-labeled PASS items accepted by deterministic v8.",
                    "metrics": [
                        {"label": "Old PASS retained", "field": "old_pass_retention_rate", "format": "percent"},
                        {"label": "Retained", "field": "old_pass_retained", "format": "number"},
                        {"label": "Old PASS", "field": "old_pass_total", "format": "number"},
                    ],
                },
                {
                    "id": "fail_reject_card",
                    "dataset": "summary",
                    "sourceId": "summary_source",
                    "description": "Previously human-labeled FAIL/REVIEW items rejected or failed closed by v8.",
                    "metrics": [
                        {"label": "FAIL/REVIEW rejected", "field": "known_fail_review_rejection_rate", "format": "percent"},
                        {"label": "Rejected", "field": "known_fail_review_rejected", "format": "number"},
                        {"label": "FAIL/REVIEW", "field": "known_fail_review_total", "format": "number"},
                    ],
                },
                {
                    "id": "outcome_card",
                    "dataset": "summary",
                    "sourceId": "summary_source",
                    "description": "Formal or calibration outcome calls in this audit.",
                    "metrics": [{"label": "Outcome calls", "field": "outcome_calls", "format": "number"}],
                },
            ],
            "charts": [
                {
                    "id": "mismatch_by_head",
                    "title": "v8 DEV verdict agreement by memory class",
                    "subtitle": "Item counts; MP n=20, ME n=12; frozen old-DEV labels only",
                    "intent": "composition",
                    "question": "Where do v8 errors concentrate across MP and ME?",
                    "rationale": "A stacked categorical bar shows the mismatch composition while retaining class denominators.",
                    "comparisonContext": {"grain": "memory class", "unit": "items", "denominator": "all frozen old-DEV items in each class"},
                    "type": "stackedBar",
                    "dataset": "head_outcomes",
                    "sourceId": "head_source",
                    "encodings": {
                        "x": {"field": "memory_class", "type": "nominal", "label": "Memory class"},
                        "y": {"fields": ["match", "false_reject", "false_accept", "schema_reject"], "type": "quantitative", "label": "Items", "unit": "items"},
                        "tooltip": [
                            {"field": "total", "type": "quantitative", "label": "Total"},
                            {"field": "old_pass_total", "type": "quantitative", "label": "Old PASS"},
                            {"field": "old_fail_review_total", "type": "quantitative", "label": "Old FAIL/REVIEW"},
                        ],
                    },
                    "palette": {"kind": "categorical", "name": "blue-orange-neutral"},
                    "settings": {"showValues": True, "sort": "none"},
                    "surface": {"viewMode": "both", "interactiveLegend": True},
                }
            ],
            "tables": [
                {
                    "id": "issue_table",
                    "title": "General interface defects and bounded repairs",
                    "subtitle": "Counts diagnose v8 only; proposed repairs are class-general and outcome-blind",
                    "dataset": "issues",
                    "sourceId": "item_source",
                    "density": "spacious",
                    "columns": [
                        {"field": "issue_domain", "label": "Issue domain"},
                        {"field": "affected_items", "label": "Items", "format": "number"},
                        {"field": "interpretation", "label": "Interpretation"},
                        {"field": "v9_repair", "label": "v9 repair"},
                    ],
                },
                {
                    "id": "item_table",
                    "title": "Frozen item-level audit matrix",
                    "subtitle": "No source text, new rating, held-out item, or outcome field is included",
                    "dataset": "items",
                    "sourceId": "item_source",
                    "density": "dense",
                    "defaultSort": {"field": "memory_class", "direction": "asc"},
                    "columns": [
                        {"field": "memory_class", "label": "Class"},
                        {"field": "memory_id", "label": "Memory ID"},
                        {"field": "old_human_label", "label": "Frozen DEV label"},
                        {"field": "v7_verdict", "label": "v7"},
                        {"field": "deterministic_v8_verdict", "label": "v8"},
                        {"field": "mismatch_reason", "label": "Audit result"},
                        {"field": "local_gate_reason", "label": "Local reasons"},
                    ],
                },
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# Paper-1 Semantic Memory v8 DEV Data-Quality Audit"},
                {"id": "summary_heading", "type": "markdown", "sourceId": "summary_source", "body": "## Technical Summary\n\nv8 improved rejection of known bad/review cases but retained only 9 of 20 old PASS items. The evidence is sufficient to diagnose schema/interface defects, not to estimate catalog quality, select a model, or authorize the 401-session compile."},
                {"id": "metrics", "type": "metric-strip", "cardIds": ["items_card", "pass_retention_card", "fail_reject_card", "outcome_card"]},
                {"id": "findings", "type": "markdown", "sourceId": "item_source", "body": "## Key Findings\n\nME errors concentrate in the field that conflates semantic action-outcome order with shared-span layout. MP false rejects concentrate in a binary exact-entailment field that cannot represent ordinary conventional entailment. The single MP false accept shows that a persistence label needs an independently observed basis. One malformed enum failed closed as intended. Local-code rejects were zero after the shared-span ordering repair."},
                {"id": "head_chart", "type": "chart", "chartId": "mismatch_by_head"},
                {"id": "scope", "type": "markdown", "body": "## Scope and Definitions\n\nThe population is the already-frozen old MP20 + ME12 DEV packet across 29 public source sessions. `MATCH` means the deterministic v8 verdict agrees with the frozen DEV label convention; `SEMANTIC_FALSE_REJECT` and `SEMANTIC_FALSE_ACCEPT` are DEV diagnostic categories. No MS item was present, so this audit cannot qualify MS."},
                {"id": "method", "type": "markdown", "sourceId": "item_source", "body": "## Methodology\n\nThe script loads the immutable JSONL matrix into an in-memory SQLite table, executes the source queries attached to this report, checks unique item IDs and zero outcome calls, then classifies only observed mismatch patterns. It does not reread source dialogue, change a frozen label, or infer a new human verdict."},
                {"id": "issues", "type": "table", "tableId": "issue_table"},
                {"id": "limitations", "type": "markdown", "body": "## Limitations and Robustness\n\nThis is a deliberately reused DEV set, not held-out evidence. Small per-class denominators make percentages unstable. The old labels are treated as frozen diagnostic references, not ground truth for formal Paper-1 effects. The proposed v9 schema must still pass a separately authorized live DEV rerun before any 401-session compile can be considered."},
                {"id": "details", "type": "table", "tableId": "item_table"},
                {"id": "next", "type": "markdown", "body": "## Recommended Next Steps\n\nRun offline v9 contract and binding tests now. Later, only after a new explicit API cap, rerun the same 29 source sessions and produce a v7/v8/v9 matrix. Stop again for researcher review; do not auto-start 401 sessions."},
                {"id": "questions", "type": "markdown", "body": "## Further Questions\n\nA later human review must decide whether the remaining ambiguous conventional-entailment and same-experience cases are consistently labeled. The present implementation must not answer those questions by item-specific code."},
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": GENERATED_AT,
            "status": "ready",
            "datasets": {
                "summary": [summary_row],
                "head_outcomes": heads,
                "issues": issues,
                "items": items,
            },
        },
        "sources": sources,
    }


def main() -> int:
    rows = _load_rows()
    if len(rows) != 32 or len({row["memory_id"] for row in rows}) != 32:
        raise RuntimeError("frozen v8 DEV matrix must contain exactly 32 unique items")
    if any(row["outcome_calls"] != 0 for row in rows):
        raise RuntimeError("v8 DEV matrix contains outcome calls")
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    if results["outcome_calls"] != 0 or results["full_401_started"]:
        raise RuntimeError("v8 results violate the pre-outcome scope")
    if set(results["locks"].values()) != {"CLOSED"}:
        raise RuntimeError("all four locks must remain CLOSED")

    db = _database(rows)
    summary = _query(db, SUMMARY_SQL)[0]
    heads = _query(db, HEAD_SQL)
    item_rows = _query(db, ITEM_SQL)
    domains = Counter(_issue_domain(row) for row in rows)
    issue_definitions = {
        "mp_support_relation_collapse": (
            "A binary exact-entailment observation rejects conventional direct entailments.",
            "Replace the boolean with a closed support relation; accept only direct-explicit or conventional-entailment evidence.",
        ),
        "mp_persistence_basis_missing": (
            "A durability label has no independent evidence basis, allowing temporary narration to look stable.",
            "Record persistence basis separately and reject durable/recurrent labels backed by temporary, episodic, or no evidence.",
        ),
        "me_semantic_order_span_topology_conflation": (
            "Semantic time order and a shared broad source span are collapsed into one enum.",
            "Use minimal exact subspans, a semantic-order enum, and a separately computed mechanical source order.",
        ),
        "me_experience_linkage_observation": (
            "The annotator left same-experience linkage unresolved for an old PASS case.",
            "Retain fail-closed linkage semantics; remeasure under the clearer minimal-span prompt without an item exception.",
        ),
        "schema_enum_conformance": (
            "One provider enum value failed the strict schema.",
            "Keep per-item fail-closed parsing; do not coerce unknown enum values.",
        ),
    }
    issues = [
        {
            "issue_domain": domain,
            "affected_items": count,
            "interpretation": issue_definitions[domain][0],
            "v9_repair": issue_definitions[domain][1],
        }
        for domain, count in sorted(domains.items())
        if domain in issue_definitions
    ]
    gate_counts = Counter(reason for row in rows for reason in row["local_gate_reason"])
    audit = {
        "protocol": "paper1-semantic-memory-v8-data-quality-audit-v1",
        "status": "DEV_DIAGNOSIS_COMPLETE_V9_LIVE_NOT_AUTHORIZED",
        "generated_at": GENERATED_AT,
        "source_identity": {
            "matrix_sha256": _sha(SOURCE),
            "results_sha256": _sha(RESULTS),
            "rows": len(rows),
            "unique_memory_ids": len({row["memory_id"] for row in rows}),
        },
        "descriptive_counts": {
            **summary,
            "old_pass_retention_rate": summary["old_pass_retained"] / summary["old_pass_total"],
            "known_fail_review_rejection_rate": summary["known_fail_review_rejected"]
            / summary["known_fail_review_total"],
            "by_memory_class": heads,
            "gate_reason_counts": dict(sorted(gate_counts.items())),
            "issue_domain_counts": dict(sorted(domains.items())),
        },
        "trust_assessment": {
            "safe_uses": [
                "diagnose general v8 schema and local-gate interface defects",
                "define outcome-blind v9 contract regression tests",
                "verify that errors are semantic/schema rather than local-code rejects",
            ],
            "unsafe_uses": [
                "estimate full-catalog precision or recall",
                "select a model or evaluator",
                "train PM heads",
                "open calibration or confirmatory outcome locks",
                "authorize the 401-session compile",
            ],
            "ms_qualification": "NOT_ASSESSED_NO_MS_ITEMS_IN_OLD_DEV_PACKET",
        },
        "v9_general_repairs": issues,
        "new_human_ratings_performed": 0,
        "provider_calls": 0,
        "outcome_calls": 0,
        "full_401_authorized": False,
        "locks": results["locks"],
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(_artifact(summary, heads, issues, item_rows), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"audit": str(AUDIT), "artifact": str(ARTIFACT), "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
