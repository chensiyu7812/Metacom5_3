#!/usr/bin/env python3
"""Derive a fail-closed ESC-RANK format-compatibility sensitivity result.

The frozen primary scorer accepts only a complete ordinal.  The pinned public
adapters instead emit a stable labelled sentence (for example, ``The empathy
score is 3.``).  This zero-inference derivative preserves the primary result
and accepts only either its strict ordinal or the exact adapter-specific
labelled sentence.  It deliberately does not use the public script's broad
"contains any digit" parser.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


LABELS = {
    "fluency": "fluecy",
    "diversity": "diversity",
    "empathic": "empathy",
    "suggestion": "suggection effectiveness",
    "human": "humanoid",
    "tech": "emotional knowledge",
    "overall": "human preference",
}


def parse_anchored_ordinal(raw: str, adapter: str) -> int | None:
    """Accept only an ordinal or the pinned adapter's exact labelled form."""

    normalized = raw.strip()
    if re.fullmatch(r"[0-4]", normalized):
        return int(normalized)
    label = LABELS.get(adapter)
    if label is None:
        return None
    match = re.fullmatch(rf"The {re.escape(label)} score is ([0-4])\.?", normalized)
    return int(match.group(1)) if match else None


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score-ledger", required=True, type=Path)
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    raw_bytes = args.score_ledger.read_bytes()
    rows = [json.loads(line) for line in raw_bytes.decode("utf-8").splitlines() if line]
    if not rows:
        raise RuntimeError("score ledger is empty")
    if any(row.get("run_identity") != args.approved_identity for row in rows):
        raise RuntimeError("score ledger contains a different run identity")

    derived = []
    for row in rows:
        anchored = parse_anchored_ordinal(row["raw_output"], row["adapter"])
        derived.append(
            {
                "run_identity": args.approved_identity,
                "screen_id": row["screen_id"],
                "candidate_id": row["candidate_id"],
                "adapter": row["adapter"],
                "primary_strict_ordinal": row.get("ordinal"),
                "anchored_ordinal": anchored,
                "raw_output_sha256": hashlib.sha256(row["raw_output"].encode()).hexdigest(),
            }
        )

    by_candidate: dict[str, Any] = defaultdict(dict)
    for candidate_id in sorted({row["candidate_id"] for row in derived}):
        candidate_rows = [row for row in derived if row["candidate_id"] == candidate_id]
        by_candidate[candidate_id] = {
            "dialogues": len({row["screen_id"] for row in candidate_rows}),
            "dimension_calls": len(candidate_rows),
            "primary_strict_valid": sum(row["primary_strict_ordinal"] is not None for row in candidate_rows),
            "anchored_valid": sum(row["anchored_ordinal"] is not None for row in candidate_rows),
            "dimension_distributions": {
                adapter: {
                    str(value): sum(
                        row["adapter"] == adapter and row["anchored_ordinal"] == value
                        for row in candidate_rows
                    )
                    for value in range(5)
                }
                for adapter in LABELS
            },
        }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "private_anchored_score_ledger.jsonl").write_text(
        "".join(_canonical(row) + "\n" for row in derived), encoding="utf-8"
    )
    summary = {
        "protocol": "metacom-v3-g0-esc-rank-anchored-format-derivative-v1",
        "run_identity": args.approved_identity,
        "source_ledger_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "inference_calls": 0,
        "primary_measurement_preserved": True,
        "primary_interpretation": "FORMAT_INCOMPATIBLE_WHEN_ALL_OUTPUTS_FAIL_FULL_STRING_ORDINAL",
        "sensitivity_parser": "exact adapter-specific labelled sentence or full-string ordinal",
        "broad_digit_search_forbidden": True,
        "candidates": dict(by_candidate),
        "formal_generator_qualification": False,
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
