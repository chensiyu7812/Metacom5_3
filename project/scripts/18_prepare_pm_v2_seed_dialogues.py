#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from metacom_pm.io import append_jsonl, sha256_file, sha256_text, write_json


def iter_records(path: Path) -> Iterable[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"non-object row in {path}")
                yield row
        return
    data = json.loads(text)
    if isinstance(data, dict):
        for key in ("data", "dialogues", "conversations", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError(f"unsupported JSON structure in {path}")
    for row in data:
        if not isinstance(row, dict):
            raise ValueError(f"non-object record in {path}")
        yield row


def get_id(row: dict[str, Any]) -> str:
    for key in ("dialogue_id", "dialog_id", "conversation_id", "id"):
        if row.get(key) is not None:
            return str(row[key])
    return "row_" + sha256_text(json.dumps(row, sort_keys=True, ensure_ascii=False))[:20]


def get_split(row: dict[str, Any]) -> str | None:
    for key in ("split", "dataset_split", "partition", "set"):
        if row.get(key) is not None:
            return str(row[key]).strip().lower()
    return None


def get_dialogue_text(row: dict[str, Any]) -> str:
    for key in ("dialogue_text", "text", "content"):
        if isinstance(row.get(key), str) and row[key].strip():
            return row[key].strip()
    turns = row.get("dialogue") or row.get("turns") or row.get("messages")
    if isinstance(turns, list):
        lines = []
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role") or turn.get("speaker") or turn.get("participant") or "unknown"
            content = turn.get("content") or turn.get("text") or turn.get("utterance") or ""
            if str(content).strip():
                lines.append(f"{role}: {str(content).strip()}")
        if lines:
            return "\n".join(lines)
    raise ValueError(f"record {get_id(row)} does not contain dialogue text")


def read_id_file(path: Path | None) -> set[str]:
    if path is None:
        return set()
    values = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            values.add(line.strip())
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--train-ids",
        type=Path,
        help="optional explicit train dialogue IDs; required when source rows lack split",
    )
    parser.add_argument("--excluded-ids", type=Path)
    parser.add_argument("--minimum-seeds", type=int, default=100)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    train_ids = read_id_file(args.train_ids)
    excluded_ids = read_id_file(args.excluded_ids)
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_text: set[str] = set()
    source_hashes = {str(path): sha256_file(path) for path in args.inputs}
    split_counts: dict[str, int] = {}
    for path in args.inputs:
        for row in iter_records(path):
            dialogue_id = get_id(row)
            split = get_split(row)
            split_counts[split or "missing"] = split_counts.get(split or "missing", 0) + 1
            is_train = dialogue_id in train_ids if train_ids else split in {"train", "training"}
            if not is_train:
                continue
            if dialogue_id in excluded_ids:
                continue
            if dialogue_id in seen_ids:
                raise RuntimeError(f"duplicate train dialogue id: {dialogue_id}")
            dialogue_text = get_dialogue_text(row)
            normalized = " ".join(dialogue_text.lower().split())
            if normalized in seen_text:
                continue
            seen_ids.add(dialogue_id)
            seen_text.add(normalized)
            selected.append(
                {
                    "dialogue_id": dialogue_id,
                    "dialogue_text": dialogue_text,
                    "source_path": str(path),
                    "source_sha256": source_hashes[str(path)],
                    "source_split": split or "explicit_train_id",
                    "seed_text_sha256": sha256_text(dialogue_text),
                }
            )
    if not train_ids and split_counts.get("missing", 0):
        raise RuntimeError(
            "source contains rows without split metadata. Supply --train-ids; "
            "PM-v2 refuses to infer train membership."
        )
    if len(selected) < args.minimum_seeds:
        raise RuntimeError(
            f"only {len(selected)} unique train seeds selected; required {args.minimum_seeds}"
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists() and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite {args.out}; pass --overwrite")
    args.out.write_text("", encoding="utf-8")
    for row in selected:
        append_jsonl(args.out, row)
    report = {
        "status": "COMPLETE",
        "inputs": [str(path) for path in args.inputs],
        "input_sha256": source_hashes,
        "split_counts": split_counts,
        "explicit_train_id_count": len(train_ids),
        "excluded_id_count": len(excluded_ids),
        "selected_unique_train_seeds": len(selected),
        "output": str(args.out),
        "output_sha256": sha256_file(args.out),
        "test_or_validation_rows_in_output": 0,
    }
    write_json(args.out.with_suffix(args.out.suffix + ".audit.json"), report)
    print(report)


if __name__ == "__main__":
    main()
