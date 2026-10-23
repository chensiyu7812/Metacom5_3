#!/usr/bin/env python3
"""Export frozen blind human-review packets to editable CSV/HTML/Markdown."""

from __future__ import annotations

import csv
from html import escape
import io
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import iter_jsonl, read_json  # noqa: E402


SOURCE = PROJECT / "data/paper1_authority"
OUTPUT = PROJECT / "data/paper1_human_review"
RS_INPUT = SOURCE / "paper1_rs_resource_semantics_blind_review_20260820_v1.jsonl"
RS_RULE = SOURCE / "paper1_rs_resource_semantics_aggregate_rule_20260820_v1.json"
ESC_A = SOURCE / "paper1_esc_evaluator_human_blind_sheet_rater_a_20260820_v1.jsonl"
ESC_B = SOURCE / "paper1_esc_evaluator_human_blind_sheet_rater_b_20260820_v1.jsonl"
ESC_ADJ = SOURCE / "paper1_esc_evaluator_human_adjudication_template_20260820_v1.jsonl"
ESC_INSTRUMENT = SOURCE / "paper1_esc_evaluator_human_instrument_20260820_v1.json"

RS_FIELDS = (
    "blind_item_id",
    "visible_state",
    "current_user_text",
    "candidate_move",
    "atomicity",
    "state_appropriateness",
    "boundary_compatibility",
    "executability",
    "leakage",
    "redundancy_near_duplicate",
    "rationale",
    "reviewer_id",
)
ESC_DIMENSIONS = (
    "Fluency",
    "Expression",
    "Empathy",
    "Information",
    "Skillful",
    "Humanoid",
    "Overall",
)


def _blind_rs_treatment(text: str) -> str:
    """Remove the rendered family label while preserving the atomic move text."""

    match = re.fullmatch(r"Strategy family \[[^\]]+\]:\s*(.+)", text, flags=re.DOTALL)
    if match is None:
        raise RuntimeError("RS rendered treatment does not match the frozen family wrapper")
    return match.group(1)


def _csv_text(rows: list[dict[str, str]], fields: Iterable[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _markdown_table(rows: list[dict[str, str]], fields: Iterable[str]) -> str:
    selected = list(fields)

    def cell(value: str) -> str:
        return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")

    lines = [
        "| " + " | ".join(selected) + " |",
        "| " + " | ".join("---" for _ in selected) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell(row[field]) for field in selected) + " |")
    return "\n".join(lines)


def _html_table(rows: list[dict[str, str]], fields: Iterable[str]) -> str:
    selected = list(fields)
    header = "".join(f"<th>{escape(field)}</th>" for field in selected)
    body = []
    for row in rows:
        cells = []
        for field in selected:
            attrs = ' contenteditable="true"' if row[field] == "" else ""
            cells.append(f"<td{attrs}>{escape(row[field]).replace(chr(10), '<br>')}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _document(title: str, instructions: str, rubric: str, table: str, *, html: bool) -> str:
    if not html:
        return f"# {title}\n\n{instructions}\n\n{rubric}\n\n{table}\n"
    return """<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:system-ui,sans-serif;margin:24px;line-height:1.4}table{border-collapse:collapse;width:100%}
th,td{border:1px solid #999;padding:6px;vertical-align:top;min-width:8em}th{background:#eee;position:sticky;top:0}
td[contenteditable=true]{background:#fffde7}pre{white-space:pre-wrap}.rubric{margin-bottom:20px}
</style></head><body>""" + (
        f"<h1>{escape(title)}</h1><p>{escape(instructions)}</p>"
        f"<div class=\"rubric\">{rubric}</div>{table}</body></html>"
    )


def _rs_rubric(rule: dict[str, Any], *, html: bool) -> str:
    parts = []
    for name, spec in rule["review_form_rubric"].items():
        if not isinstance(spec, dict) or "question" not in spec:
            continue
        labels = ", ".join(spec["labels"])
        if html:
            parts.append(
                f"<p><b>{escape(name)}</b>: {escape(spec['question'])}<br>"
                f"Allowed labels: {escape(labels)}</p>"
            )
        else:
            parts.append(f"- `{name}`: {spec['question']} Allowed labels: {labels}")
    return "".join(parts) if html else "## Frozen rubric\n\n" + "\n".join(parts)


def export_rs() -> None:
    raw_rows = list(iter_jsonl(RS_INPUT))
    if len(raw_rows) != 64 or any(
        row[field] is not None
        for row in raw_rows
        for field in (
            "atomicity",
            "state_appropriateness",
            "boundary_compatibility",
            "executability",
            "leakage",
            "redundancy_near_duplicate",
            "rationale",
            "reviewer_id",
        )
    ):
        raise RuntimeError("RS blind source must contain 64 completely unfilled review rows")
    rows = [
        {
            "blind_item_id": row["blind_item_id"],
            "visible_state": row["visible_state"],
            "current_user_text": row["current_user_text"],
            "candidate_move": _blind_rs_treatment(row["exact_rendered_treatment"]),
            **{field: "" for field in RS_FIELDS[4:]},
        }
        for row in raw_rows
    ]
    rule = read_json(RS_RULE)
    stem = OUTPUT / "paper1_rs_semantics_human_review_20260820_v1"
    stem.with_suffix(".csv").write_text(_csv_text(rows, RS_FIELDS), encoding="utf-8")
    instructions = (
        "Fill only the six frozen rubric fields, rationale, and reviewer_id. "
        "Do not assess response quality, helpfulness, utility, or a runtime on/off decision."
    )
    stem.with_suffix(".md").write_text(
        _document(
            "Paper-1 RS blind semantics review",
            instructions,
            _rs_rubric(rule, html=False),
            _markdown_table(rows, RS_FIELDS),
            html=False,
        ),
        encoding="utf-8",
    )
    stem.with_suffix(".html").write_text(
        _document(
            "Paper-1 RS blind semantics review",
            instructions,
            _rs_rubric(rule, html=True),
            _html_table(rows, RS_FIELDS),
            html=True,
        ),
        encoding="utf-8",
    )


def _dialogue_text(dialogue: list[str]) -> str:
    return "\n".join(dialogue)


def _esc_rows(path: Path) -> list[dict[str, str]]:
    raw_rows = list(iter_jsonl(path))
    if len(raw_rows) != 24:
        raise RuntimeError("ESC blind reviewer source must contain exactly 24 items")
    rows: list[dict[str, str]] = []
    for raw in raw_rows:
        if raw["human_completed"] or raw["notes"] is not None or any(
            value is not None for value in raw["scores"].values()
        ):
            raise RuntimeError("ESC reviewer source contains a prefilled human field")
        rows.append(
            {
                "blind_item_id": raw["blind_item_id"],
                "dialogue": _dialogue_text(raw["dialogue"]),
                **{dimension: "" for dimension in ESC_DIMENSIONS},
                "notes": "",
                "human_completed": "",
            }
        )
    return rows


def _esc_rubric(instrument: dict[str, Any], *, html: bool) -> str:
    parts = []
    for dimension in instrument["dimensions"]:
        name = dimension["paper_dimension"]
        text = dimension["official_rubric_text"]
        if html:
            parts.append(f"<details><summary>{escape(name)}</summary><pre>{escape(text)}</pre></details>")
        else:
            parts.append(f"### {name}\n\n{text}")
    return "".join(parts) if html else "## Frozen official rubric\n\n" + "\n\n".join(parts)


def _export_esc_reviewer(label: str, source: Path, instrument: dict[str, Any]) -> None:
    fields = ("blind_item_id", "dialogue", *ESC_DIMENSIONS, "notes", "human_completed")
    rows = _esc_rows(source)
    stem = OUTPUT / f"paper1_esc_evaluator_reviewer_{label.lower()}_20260820_v1"
    stem.with_suffix(".csv").write_text(_csv_text(rows, fields), encoding="utf-8")
    instructions = (
        "Rate every blind dialogue independently on the frozen 0-4 dimensions. "
        "Do not seek system, model, treatment, or arm identity."
    )
    stem.with_suffix(".md").write_text(
        _document(
            f"Paper-1 ESC evaluator qualification Reviewer {label}",
            instructions,
            _esc_rubric(instrument, html=False),
            _markdown_table(rows, fields),
            html=False,
        ),
        encoding="utf-8",
    )
    stem.with_suffix(".html").write_text(
        _document(
            f"Paper-1 ESC evaluator qualification Reviewer {label}",
            instructions,
            _esc_rubric(instrument, html=True),
            _html_table(rows, fields),
            html=True,
        ),
        encoding="utf-8",
    )


def export_esc_adjudication() -> None:
    template = list(iter_jsonl(ESC_ADJ))
    dialogue_by_id: dict[str, str] = {}
    for path in (ESC_A, ESC_B):
        for row in iter_jsonl(path):
            dialogue_by_id.setdefault(row["blind_item_id"], _dialogue_text(row["dialogue"]))
    if len(template) != 24 or {row["blind_item_id"] for row in template} != set(
        dialogue_by_id
    ):
        raise RuntimeError("ESC adjudication identities differ from the two blind sheets")
    fields = ["blind_item_id", "dialogue"]
    for dimension in ESC_DIMENSIONS:
        fields.extend(
            (
                f"reviewer_a_{dimension}",
                f"reviewer_b_{dimension}",
                f"adjudicated_{dimension}",
            )
        )
    fields.extend(("adjudication_notes", "adjudicator_id", "adjudication_completed"))
    rows = [
        {
            "blind_item_id": row["blind_item_id"],
            "dialogue": dialogue_by_id[row["blind_item_id"]],
            **{field: "" for field in fields[2:]},
        }
        for row in template
    ]
    stem = OUTPUT / "paper1_esc_evaluator_adjudication_20260820_v1"
    stem.with_suffix(".csv").write_text(_csv_text(rows, fields), encoding="utf-8")
    instructions = (
        "Use only after both independent blind reviews are locked. Copy the two scores, "
        "then record a separate adjudicated score without revealing any model identity."
    )
    stem.with_suffix(".md").write_text(
        _document(
            "Paper-1 ESC evaluator qualification adjudication",
            instructions,
            "",
            _markdown_table(rows, fields),
            html=False,
        ),
        encoding="utf-8",
    )
    stem.with_suffix(".html").write_text(
        _document(
            "Paper-1 ESC evaluator qualification adjudication",
            instructions,
            "",
            _html_table(rows, fields),
            html=True,
        ),
        encoding="utf-8",
    )


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    export_rs()
    instrument = read_json(ESC_INSTRUMENT)
    _export_esc_reviewer("A", ESC_A, instrument)
    _export_esc_reviewer("B", ESC_B, instrument)
    export_esc_adjudication()
    manifest = {
        "protocol": "paper1-human-review-readable-export-v1",
        "status": "BLANK_BLIND_SHEETS_READY",
        "counts": {"rs": 64, "esc_reviewer_a": 24, "esc_reviewer_b": 24, "esc_adjudication": 24},
        "formats": ["csv", "html", "markdown"],
        "prefilled_human_or_llm_verdicts": 0,
        "outcome_calls": 0,
    }
    (OUTPUT / "paper1_human_review_export_manifest_20260820_v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
