#!/usr/bin/env python3
"""Materialize a text-free row identity for ES-MemEval public v1.0.0."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalized_text(value: Any) -> str:
    text = value if isinstance(value, str) else _canonical(value)
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _digest(value: Any, *, normalized_text: bool = False) -> str:
    rendered = _normalized_text(value) if normalized_text else _canonical(value)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def materialize(input_path: Path) -> list[dict[str, Any]]:
    users = json.loads(input_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for user in users:
        owner = user["id"]
        for group in user["questions"]:
            group_id = str(group["id"])
            for item in group["questions"]:
                item_idx = str(item["idx"])
                evidence = item.get("evidence", [])
                rows.append(
                    {
                        "row_id": f"{owner}::{group_id}::{item_idx}",
                        "owner_id": owner,
                        "question_group_id": group_id,
                        "item_idx": item_idx,
                        "capability": item["capability"],
                        "question_normalized_sha256": _digest(item["question"], normalized_text=True),
                        "answer_canonical_sha256": _digest(item.get("answer")),
                        "evidence_canonical_sha256": _digest(evidence),
                        "evidence_count": len(evidence) if isinstance(evidence, list) else None,
                    }
                )
    rows.sort(key=lambda row: (row["owner_id"], row["question_group_id"], row["item_idx"]))
    if len({row["row_id"] for row in rows}) != len(rows):
        raise ValueError("ES-MemEval public row_id is not unique")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    rows = materialize(args.input)
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    capabilities: dict[str, int] = {}
    for row in rows:
        capabilities[row["capability"]] = capabilities.get(row["capability"], 0) + 1
    print(
        json.dumps(
            {
                "rows": len(rows),
                "owners": len({row["owner_id"] for row in rows}),
                "capabilities": capabilities,
                "manifest_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                "contains_question_or_answer_text": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
