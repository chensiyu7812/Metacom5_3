#!/usr/bin/env python3
"""Materialize fresh G4B1 V2 controls and audit anchor/control disjointness."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_g4b_anchored_review_v2 import (  # noqa: E402
    WORKED_ANCHORS,
    build_fresh_v2_controls,
    prompt_messages,
)


DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4_nonexclusive_suitability_design_v1.json"
V1_PUBLIC = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_controls_20260811"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_controls_private_20260811"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def ngrams(texts: Iterable[str], n: int = 8) -> set[tuple[str, ...]]:
    result = set()
    for text in texts:
        values = tokens(text)
        result.update(tuple(values[i : i + n]) for i in range(len(values) - n + 1))
    return result


def content(rows_: Iterable[dict[str, Any]]) -> list[str]:
    result = []
    for row in rows_:
        result.extend(span["content"] for span in row["visible_spans"])
        result.extend(span["content"] for span in row["candidate_spans"])
    return result


def main() -> None:
    if OUT.exists() or PRIVATE.exists():
        raise RuntimeError("anchored V2 control output exists; refusing overwrite")
    design = read(DESIGN)
    a, b, gold = build_fresh_v2_controls(design)
    if len(a) != 36 or len(b) != 36 or len(gold) != 36:
        raise RuntimeError("V2 control denominator drifted")
    gold_counts = Counter((row["component"], row["gold_decision"]) for row in gold)
    expected = Counter(
        {
            (component, decision): count
            for component in ("MP", "MS", "ME")
            for decision, count in (
                ("SUITABLE", 5),
                ("NOT_SUITABLE", 5),
                ("SEMANTIC_ABSTAIN", 2),
            )
        }
    )
    if gold_counts != expected:
        raise RuntimeError(f"V2 control class balance drifted: {gold_counts}")

    historical = content(rows(V1_PUBLIC / "reviewer_a_controls.jsonl"))
    public = content(rows(V1_PUBLIC / "reviewer_a_packet.jsonl"))
    fresh = content(a)
    anchor_text = [
        value
        for examples in WORKED_ANCHORS.values()
        for example in examples
        for value in (example["visible"], example["candidate"])
    ]
    overlap = {
        "fresh_vs_v1_controls": len(ngrams(fresh) & ngrams(historical)),
        "fresh_vs_public_507": len(ngrams(fresh) & ngrams(public)),
        "anchors_vs_fresh_controls": len(ngrams(anchor_text) & ngrams(fresh)),
        "anchors_vs_public_507": len(ngrams(anchor_text) & ngrams(public)),
    }
    if any(overlap.values()):
        raise RuntimeError(f"V2 anchor/control normalized 8-gram overlap: {overlap}")
    prompt = prompt_messages(a[0], "REVIEWER_A")[0]["content"]
    if "WORKED TRAINING ANCHORS" not in prompt or "SEMANTIC_ABSTAIN" not in prompt:
        raise RuntimeError("worked anchors are not provider-visible")

    OUT.mkdir(parents=True)
    PRIVATE.mkdir(parents=True)
    write_jsonl(OUT / "reviewer_a_controls.jsonl", a)
    write_jsonl(OUT / "reviewer_b_controls.jsonl", b)
    write_jsonl(PRIVATE / "control_gold_key.jsonl", gold)
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b1-anchored-v2-controls-report-v1",
        "status": "G4B1_ANCHORED_V2_FRESH_CONTROLS_PASS_EXECUTION_NOT_AUTHORIZED",
        "controls": {"total": 36, "per_reviewer": 36, "per_component": 12},
        "distribution_per_component": {
            "SUITABLE": 5,
            "NOT_SUITABLE": 5,
            "SEMANTIC_ABSTAIN": 2,
        },
        "worked_anchors": {"per_component": 3, "provider_visible": True},
        "normalized_8gram_overlap": overlap,
        "reviewer_a": {
            "path": str((OUT / "reviewer_a_controls.jsonl").relative_to(ROOT)),
            "sha256": sha256_file(OUT / "reviewer_a_controls.jsonl"),
        },
        "reviewer_b": {
            "path": str((OUT / "reviewer_b_controls.jsonl").relative_to(ROOT)),
            "sha256": sha256_file(OUT / "reviewer_b_controls.jsonl"),
        },
        "private_gold": {
            "path": str((PRIVATE / "control_gold_key.jsonl").relative_to(ROOT)),
            "sha256": sha256_file(PRIVATE / "control_gold_key.jsonl"),
            "review_execution_access": False,
        },
        "v1_failure_preserved": True,
        "reviewers_decisions_composition_and_gates_unchanged": True,
        "api_calls": 0,
        "reviews_created": 0,
        "labels_created": 0,
        "next_gate": "G4B1_ANCHORED_V2_ZERO_API_EXECUTION_PREFLIGHT",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
