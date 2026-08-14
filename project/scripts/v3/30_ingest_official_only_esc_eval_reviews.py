#!/usr/bin/env python3
"""Ingest official-seven-dimension-only reviews and blind-adjudicate deltas.

Some completed review exports intentionally contain only the official
ESC-Eval dimensions and explicitly omit project guardrails. This script keeps
those valid official scores, refuses to invent missing guardrails, and creates
a third-review packet only for predeclared >=2-point dimension disagreements.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from statistics import mean, median
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIMENSIONS = ("Fluency", "Expression", "Empathy", "Information", "Humanoid", "Skill", "Overall")
SOURCE_PACKET_PROTOCOL = "metacom-v3-g0-esc-eval-human-review-packet-v1"
RESPONSE_PROTOCOL = "metacom-v3-esc-eval-human-review-response-v1"


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _load_materializer():
    path = Path(__file__).with_name("27_materialize_g0_esc_eval_human_review.py")
    spec = importlib.util.spec_from_file_location("g0_esc_eval_human_packet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ESC-Eval human packet materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stable_hex(*parts: str, n: int = 20) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:n]


def _read_primary(path: Path, reviewer: str, expected_ids: set[str]) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("source_packet_protocol") != SOURCE_PACKET_PROTOCOL or data.get("reviewer") != reviewer:
        raise ValueError(f"{reviewer}: source packet protocol or reviewer identity mismatch")
    if "guardrails were not scored" not in str(data.get("scope", "")):
        raise ValueError(f"{reviewer}: official-only scope is not explicit")
    answers = data.get("answers")
    if not isinstance(answers, dict) or set(answers) != expected_ids:
        raise ValueError(f"{reviewer}: expected exactly {len(expected_ids)} frozen assignment IDs")
    orders: set[int] = set()
    for item_id, answer in answers.items():
        dimensions = answer.get("dimensions")
        if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
            raise ValueError(f"{reviewer}/{item_id}: seven official dimensions required")
        if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4 for value in dimensions.values()):
            raise ValueError(f"{reviewer}/{item_id}: score outside integer 0..4")
        expected_mean = round(sum(dimensions.values()) / 7, 3)
        if answer.get("mean_7d") != expected_mean:
            raise ValueError(f"{reviewer}/{item_id}: mean_7d mismatch")
        if answer.get("review_status") not in {"SCORED", "ADJUDICATED", "FLAGGED_HIGH_CONFIDENCE"}:
            raise ValueError(f"{reviewer}/{item_id}: invalid review_status")
        orders.add(answer.get("display_order"))
    if orders != set(range(1, 73)):
        raise ValueError(f"{reviewer}: display orders are incomplete or duplicated")
    return data


def _read_adjudication(path: Path, expected_ids: set[str]) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("protocol") != RESPONSE_PROTOCOL or data.get("reviewer") != "HUMAN_C":
        raise ValueError("Human C response protocol or identity mismatch")
    answers = data.get("answers")
    if not isinstance(answers, dict) or set(answers) != expected_ids:
        raise ValueError("Human C assignment IDs differ from the frozen disagreement packet")
    for item_id, answer in answers.items():
        dimensions = answer.get("dimensions")
        if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
            raise ValueError(f"HUMAN_C/{item_id}: seven dimensions required")
        if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4 for value in dimensions.values()):
            raise ValueError(f"HUMAN_C/{item_id}: score outside integer 0..4")
        if answer.get("transcript_integrity") not in {"PASS", "PACKET_ERROR", "UNCERTAIN"}:
            raise ValueError(f"HUMAN_C/{item_id}: transcript integrity missing")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-dir", required=True, type=Path)
    parser.add_argument("--human-a", required=True, type=Path)
    parser.add_argument("--human-b", required=True, type=Path)
    parser.add_argument("--human-c", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise RuntimeError("output directory exists; refusing overwrite")
    args.out_dir.mkdir(parents=True)

    public_items = {
        reviewer: _rows(args.packet_dir / f"{reviewer.lower()}_blind_items.jsonl")
        for reviewer in ("HUMAN_A", "HUMAN_B")
    }
    expected = {reviewer: {row["assignment_id"] for row in rows} for reviewer, rows in public_items.items()}
    reviews = {
        "HUMAN_A": _read_primary(args.human_a, "HUMAN_A", expected["HUMAN_A"]),
        "HUMAN_B": _read_primary(args.human_b, "HUMAN_B", expected["HUMAN_B"]),
    }
    mapping = _rows(args.packet_dir / "private_blinding_map.jsonl")
    by_assignment = {row["assignment_id"]: row for row in mapping}
    by_dialogue: dict[str, dict[str, str]] = defaultdict(dict)
    meta: dict[str, dict[str, str]] = {}
    for row in mapping:
        by_dialogue[row["dialogue_key"]][row["reviewer"]] = row["assignment_id"]
        meta[row["dialogue_key"]] = row
    public_by_assignment = {row["assignment_id"]: row for rows in public_items.values() for row in rows}

    escalations: list[dict[str, Any]] = []
    exact = 0
    for dialogue_key, assignments in sorted(by_dialogue.items()):
        aa = reviews["HUMAN_A"]["answers"][assignments["HUMAN_A"]]
        bb = reviews["HUMAN_B"]["answers"][assignments["HUMAN_B"]]
        reasons: list[str] = []
        for dimension in DIMENSIONS:
            av, bv = aa["dimensions"][dimension], bb["dimensions"][dimension]
            exact += av == bv
            if abs(av - bv) >= 2:
                reasons.append(f"DIMENSION_DISAGREEMENT_GE_2:{dimension}")
        if reasons:
            escalations.append(
                {
                    "assignment_id": "esceval_adj_" + _stable_hex("official-only", dialogue_key),
                    "display_order": len(escalations) + 1,
                    "dialogue_key": dialogue_key,
                    "reasons": reasons,
                    "transcript": public_by_assignment[assignments["HUMAN_A"]]["transcript"],
                }
            )
    materializer = _load_materializer()
    rubric = json.loads((args.packet_dir / "official_english_rubric.json").read_text(encoding="utf-8"))
    public_c_items = [
        {"assignment_id": row["assignment_id"], "display_order": row["display_order"], "transcript": row["transcript"]}
        for row in escalations
    ]
    payload = {
        "packet_protocol": "metacom-v3-g0-esc-eval-official-only-adjudication-v1",
        "response_protocol": RESPONSE_PROTOCOL,
        "reviewer": "HUMAN_C",
        "dimensions": list(DIMENSIONS),
        "guardrails": [],
        "rubric": rubric,
        "items": public_c_items,
    }
    (args.out_dir / "human_c_official_blind_items.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in public_c_items), encoding="utf-8"
    )
    (args.out_dir / "human_c_official_review.html").write_text(materializer._html(payload), encoding="utf-8")
    (args.out_dir / "private_c_mapping.json").write_text(
        json.dumps({row["assignment_id"]: row["dialogue_key"] for row in escalations}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(args.human_a, args.out_dir / "human_a_official_raw_frozen.json")
    shutil.copy2(args.human_b, args.out_dir / "human_b_official_raw_frozen.json")

    report: dict[str, Any] = {
        "protocol": "metacom-v3-g0-esc-eval-official-only-review-ingestion-v1",
        "primary_reviews_valid": True,
        "reviewer_provenance": "USER_PROVIDED_REVIEWER_LABELS_HUMAN_A_AND_HUMAN_B_NOT_INDEPENDENTLY_VERIFIED_BY_CODEX",
        "dialogues": 72,
        "official_dimension_cells": 504,
        "exact_agreement_cells": exact,
        "exact_agreement_rate": exact / 504,
        "dimension_disagreement_ge_2_cells": sum(len(row["reasons"]) for row in escalations),
        "dialogues_requiring_human_c": len(escalations),
        "project_guardrails": "NOT_MEASURED_EXPLICITLY_EXCLUDED_BY_BOTH_SOURCE_FILES",
        "api_calls": 0,
    }
    if escalations and args.human_c is None:
        report.update(
            {
                "status": "OFFICIAL_PRIMARY_REVIEWS_VALID_HUMAN_C_PENDING_PROJECT_GUARDRAILS_MISSING",
                "generator_selected": False,
                "next": "Human C independently scores the frozen seven-dialogue official-only packet; project guardrails remain a separate missing gate.",
            }
        )
        (args.out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    c_answers: dict[str, Any] = {}
    if escalations:
        c = _read_adjudication(args.human_c, {row["assignment_id"] for row in escalations})  # type: ignore[arg-type]
        c_answers = c["answers"]
        shutil.copy2(args.human_c, args.out_dir / "human_c_official_raw_frozen.json")  # type: ignore[arg-type]
    final_rows: list[dict[str, Any]] = []
    for dialogue_key, assignments in sorted(by_dialogue.items()):
        aa = reviews["HUMAN_A"]["answers"][assignments["HUMAN_A"]]
        bb = reviews["HUMAN_B"]["answers"][assignments["HUMAN_B"]]
        c_id = next((row["assignment_id"] for row in escalations if row["dialogue_key"] == dialogue_key), None)
        cc = c_answers.get(c_id) if c_id else None
        scores: dict[str, float] = {}
        for dimension in DIMENSIONS:
            av, bv = aa["dimensions"][dimension], bb["dimensions"][dimension]
            scores[dimension] = float(median([av, bv, cc["dimensions"][dimension]])) if abs(av - bv) >= 2 else mean([av, bv])
        final_rows.append(
            {
                "dialogue_key": dialogue_key,
                "screen_id": meta[dialogue_key]["screen_id"],
                "card_key": meta[dialogue_key]["card_key"],
                "candidate_id": meta[dialogue_key]["candidate_id"],
                "official_scores": scores,
                "project_guardrails": "NOT_MEASURED",
            }
        )
    summary: dict[str, Any] = {}
    for candidate in sorted({row["candidate_id"] for row in final_rows}):
        subset = [row for row in final_rows if row["candidate_id"] == candidate]
        summary[candidate] = {
            dimension: mean(row["official_scores"][dimension] for row in subset)
            for dimension in DIMENSIONS
        }
    (args.out_dir / "private_official_final_scores.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in final_rows), encoding="utf-8"
    )
    report.update(
        {
            "status": "OFFICIAL_SEVEN_DIMENSION_AGGREGATION_COMPLETE_PROJECT_GUARDRAILS_MISSING",
            "candidate_official_means": summary,
            "generator_selected": False,
            "next": "Apply official Quality analysis, then complete the separately frozen project-integrity gate before generator qualification.",
        }
    )
    (args.out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
