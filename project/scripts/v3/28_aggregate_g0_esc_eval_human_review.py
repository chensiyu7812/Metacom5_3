#!/usr/bin/env python3
"""Validate two ESC-Eval reviews, prepare blind adjudication, and aggregate.

The script never calls a model. Candidate identities are revealed only after
both primary review files validate. A third reviewer independently re-scores
only items triggered by the predeclared disagreement/integrity rules.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from statistics import mean, median
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIMENSIONS = ("Fluency", "Expression", "Empathy", "Information", "Humanoid", "Skill", "Overall")
GUARDRAILS = (
    "low_burden",
    "no_premature_action",
    "no_unsupported_personal_inference",
    "safety_signal_handling",
    "no_scaffold_leakage",
)
RESPONSE_PROTOCOL = "metacom-v3-esc-eval-human-review-response-v1"
ALLOWED_GUARD = {"PASS", "FAIL", "UNCERTAIN", "NOT_APPLICABLE"}
ALLOWED_INTEGRITY = {"PASS", "PACKET_ERROR", "UNCERTAIN"}


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _stable_hex(*parts: str, n: int = 24) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:n]


def _load_materializer():
    path = Path(__file__).with_name("27_materialize_g0_esc_eval_human_review.py")
    spec = importlib.util.spec_from_file_location("g0_esc_eval_human_packet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load human packet materializer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_review(path: Path, reviewer: str, expected_ids: set[str]) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("protocol") != RESPONSE_PROTOCOL or data.get("reviewer") != reviewer:
        raise ValueError(f"{reviewer}: response protocol or reviewer identity mismatch")
    answers = data.get("answers")
    if not isinstance(answers, dict) or set(answers) != expected_ids:
        missing = expected_ids - set(answers or {})
        extra = set(answers or {}) - expected_ids
        raise ValueError(f"{reviewer}: answer IDs differ: missing={len(missing)}, extra={len(extra)}")
    for item_id, answer in answers.items():
        dims = answer.get("dimensions")
        guards = answer.get("guardrails")
        if not isinstance(dims, dict) or set(dims) != set(DIMENSIONS):
            raise ValueError(f"{reviewer}/{item_id}: seven official dimensions required")
        if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4 for value in dims.values()):
            raise ValueError(f"{reviewer}/{item_id}: every official score must be integer 0..4")
        if not isinstance(guards, dict) or set(guards) != set(GUARDRAILS) or any(value not in ALLOWED_GUARD for value in guards.values()):
            raise ValueError(f"{reviewer}/{item_id}: project guardrails are incomplete or invalid")
        integrity = answer.get("transcript_integrity")
        if integrity not in ALLOWED_INTEGRITY:
            raise ValueError(f"{reviewer}/{item_id}: transcript_integrity is invalid")
        flagged = integrity != "PASS" or any(value not in {"PASS", "NOT_APPLICABLE"} for value in guards.values())
        if flagged and not str(answer.get("notes") or "").strip():
            raise ValueError(f"{reviewer}/{item_id}: notes required for flagged item")
    return data


def _write_adjudication_packet(
    packet_dir: Path,
    out_dir: Path,
    escalations: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    materializer = _load_materializer()
    rubric = json.loads((packet_dir / "official_english_rubric.json").read_text(encoding="utf-8"))
    items = [
        {
            "assignment_id": row["adjudication_assignment_id"],
            "display_order": index,
            "transcript": row["transcript"],
        }
        for index, row in enumerate(escalations, start=1)
    ]
    payload = {
        "packet_protocol": "metacom-v3-g0-esc-eval-human-adjudication-packet-v1",
        "response_protocol": RESPONSE_PROTOCOL,
        "reviewer": "HUMAN_C",
        "dimensions": list(DIMENSIONS),
        "guardrails": list(GUARDRAILS),
        "rubric": rubric,
        "items": items,
    }
    public = out_dir / "human_c_blind_items.jsonl"
    public.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in items),
        encoding="utf-8",
    )
    html = out_dir / "human_c_review.html"
    html.write_text(materializer._html(payload), encoding="utf-8")
    template = out_dir / "human_c_response_template.json"
    template.write_text(
        json.dumps(
            {
                "protocol": RESPONSE_PROTOCOL,
                "packet_protocol": payload["packet_protocol"],
                "reviewer": "HUMAN_C",
                "answers": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    public_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (public, html, template)}
    private_map = {row["adjudication_assignment_id"]: row["dialogue_key"] for row in escalations}
    return public_hashes, private_map


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
        "HUMAN_A": _read_review(args.human_a, "HUMAN_A", expected["HUMAN_A"]),
        "HUMAN_B": _read_review(args.human_b, "HUMAN_B", expected["HUMAN_B"]),
    }
    mapping_rows = _rows(args.packet_dir / "private_blinding_map.jsonl")
    by_assignment = {row["assignment_id"]: row for row in mapping_rows}
    if len(by_assignment) != 144:
        raise RuntimeError("private assignment mapping drifted")
    public_by_assignment = {
        row["assignment_id"]: row
        for rows in public_items.values()
        for row in rows
    }
    by_dialogue: dict[str, dict[str, str]] = defaultdict(dict)
    dialogue_meta: dict[str, dict[str, str]] = {}
    for row in mapping_rows:
        by_dialogue[row["dialogue_key"]][row["reviewer"]] = row["assignment_id"]
        dialogue_meta[row["dialogue_key"]] = row
    if len(by_dialogue) != 72 or any(set(value) != {"HUMAN_A", "HUMAN_B"} for value in by_dialogue.values()):
        raise RuntimeError("dialogue/reviewer mapping is not a complete 72 by 2 design")

    escalations: list[dict[str, Any]] = []
    exact_dimension_cells = 0
    exact_guardrail_cells = 0
    for dialogue_key, assignments in sorted(by_dialogue.items()):
        aa = reviews["HUMAN_A"]["answers"][assignments["HUMAN_A"]]
        bb = reviews["HUMAN_B"]["answers"][assignments["HUMAN_B"]]
        reasons: list[str] = []
        for dimension in DIMENSIONS:
            delta = abs(aa["dimensions"][dimension] - bb["dimensions"][dimension])
            exact_dimension_cells += delta == 0
            if delta >= 2:
                reasons.append(f"DIMENSION_DISAGREEMENT_GE_2:{dimension}")
        if aa["transcript_integrity"] != "PASS" or bb["transcript_integrity"] != "PASS":
            reasons.append("TRANSCRIPT_INTEGRITY_FLAG")
        for guardrail in GUARDRAILS:
            av, bv = aa["guardrails"][guardrail], bb["guardrails"][guardrail]
            exact_guardrail_cells += av == bv
            if av != bv or av in {"FAIL", "UNCERTAIN"} or bv in {"FAIL", "UNCERTAIN"}:
                reasons.append(f"GUARDRAIL_REVIEW:{guardrail}")
        if reasons:
            transcript = public_by_assignment[assignments["HUMAN_A"]]["transcript"]
            escalations.append(
                {
                    "adjudication_assignment_id": "esceval_adj_" + _stable_hex("adjudication", dialogue_key, n=20),
                    "dialogue_key": dialogue_key,
                    "reasons": reasons,
                    "transcript": transcript,
                }
            )

    public_hashes, adjudication_map = _write_adjudication_packet(args.packet_dir, args.out_dir, escalations)
    (args.out_dir / "private_adjudication_map.json").write_text(
        json.dumps(adjudication_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(args.human_a, args.out_dir / "human_a_raw_frozen.json")
    shutil.copy2(args.human_b, args.out_dir / "human_b_raw_frozen.json")

    base_report: dict[str, Any] = {
        "protocol": "metacom-v3-g0-esc-eval-two-human-aggregation-v1",
        "reviews_valid": True,
        "dialogues": 72,
        "official_dimension_cells": 72 * 7,
        "official_dimension_exact_agreement": exact_dimension_cells,
        "project_guardrail_cells": 72 * len(GUARDRAILS),
        "project_guardrail_exact_agreement": exact_guardrail_cells,
        "items_requiring_blind_adjudication": len(escalations),
        "adjudication_public_hashes": public_hashes,
        "api_calls": 0,
    }
    if escalations and args.human_c is None:
        base_report.update(
            {
                "status": "TWO_PRIMARY_REVIEWS_VALID_BLIND_ADJUDICATION_PENDING",
                "generator_selected": False,
                "next": "A third independent reviewer completes human_c_review.html without seeing candidate identity or the first two scores.",
            }
        )
        (args.out_dir / "report.json").write_text(json.dumps(base_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(base_report, ensure_ascii=False, indent=2))
        return 0

    c_answers: dict[str, Any] = {}
    if escalations:
        c_review = _read_review(args.human_c, "HUMAN_C", set(adjudication_map))  # type: ignore[arg-type]
        c_answers = c_review["answers"]
        shutil.copy2(args.human_c, args.out_dir / "human_c_raw_frozen.json")  # type: ignore[arg-type]
    elif args.human_c is not None:
        raise ValueError("human-c was supplied but no adjudication item exists")

    final_rows: list[dict[str, Any]] = []
    for dialogue_key, assignments in sorted(by_dialogue.items()):
        aa = reviews["HUMAN_A"]["answers"][assignments["HUMAN_A"]]
        bb = reviews["HUMAN_B"]["answers"][assignments["HUMAN_B"]]
        adj_id = next((row["adjudication_assignment_id"] for row in escalations if row["dialogue_key"] == dialogue_key), None)
        cc = c_answers.get(adj_id) if adj_id else None
        scores: dict[str, float] = {}
        for dimension in DIMENSIONS:
            av, bv = aa["dimensions"][dimension], bb["dimensions"][dimension]
            scores[dimension] = float(median([av, bv, cc["dimensions"][dimension]])) if abs(av - bv) >= 2 else mean([av, bv])
        integrity = cc["transcript_integrity"] if cc and (aa["transcript_integrity"] != "PASS" or bb["transcript_integrity"] != "PASS") else "PASS"
        guards: dict[str, str] = {}
        for guardrail in GUARDRAILS:
            av, bv = aa["guardrails"][guardrail], bb["guardrails"][guardrail]
            needs_c = av != bv or av in {"FAIL", "UNCERTAIN"} or bv in {"FAIL", "UNCERTAIN"}
            guards[guardrail] = cc["guardrails"][guardrail] if needs_c and cc else av
        meta = dialogue_meta[dialogue_key]
        final_rows.append(
            {
                "dialogue_key": dialogue_key,
                "screen_id": meta["screen_id"],
                "card_key": meta["card_key"],
                "candidate_id": meta["candidate_id"],
                "official_scores": scores,
                "transcript_integrity": integrity,
                "project_guardrails": guards,
            }
        )
    packet_errors = [row for row in final_rows if row["transcript_integrity"] != "PASS"]
    candidate_summary: dict[str, Any] = {}
    for candidate in sorted({row["candidate_id"] for row in final_rows}):
        subset = [row for row in final_rows if row["candidate_id"] == candidate]
        candidate_summary[candidate] = {
            "dialogues": len(subset),
            "official_dimension_means": {
                dimension: mean(row["official_scores"][dimension] for row in subset)
                for dimension in DIMENSIONS
            },
            "project_guardrail_outcomes": {
                guardrail: dict(Counter(row["project_guardrails"][guardrail] for row in subset))
                for guardrail in GUARDRAILS
            },
        }
    (args.out_dir / "private_final_dialogue_scores.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in final_rows),
        encoding="utf-8",
    )
    base_report.update(
        {
            "status": "HUMAN_REVIEW_AGGREGATION_COMPLETE_READY_FOR_FROZEN_GENERATOR_DECISION" if not packet_errors else "PACKET_INTEGRITY_BLOCKS_GENERATOR_DECISION",
            "packet_integrity_blockers": len(packet_errors),
            "candidate_summary": candidate_summary,
            "generator_selected": False,
            "next": "Apply the predeclared ESC-Eval development decision contract; this aggregation script does not invent a winner.",
        }
    )
    (args.out_dir / "report.json").write_text(json.dumps(base_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(base_report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
