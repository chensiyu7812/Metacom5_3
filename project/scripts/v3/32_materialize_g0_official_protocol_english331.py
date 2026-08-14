#!/usr/bin/env python3
"""Freeze the identities of all 331 official English high-quality cards."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data" / "v3_authority"
CONTRACT = AUTHORITY / "g0_official_protocol_english331_contract_v1.json"
OUT = AUTHORITY / "g0_official_protocol_english331_manifest_v1.jsonl"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    head = subprocess.run(["git", "-C", str(args.esc_eval), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if head != contract["primary_sources"]["repository_commit"]:
        raise RuntimeError("ESC-Eval commit drift")
    evaluate_sha = hashlib.sha256((args.esc_eval / "evaluate.py").read_bytes()).hexdigest()
    if evaluate_sha != contract["primary_sources"]["official_evaluate_py_sha256"]:
        raise RuntimeError("official evaluate.py drift")
    cards = json.loads((args.esc_eval / "data" / "card_high_en.json").read_text(encoding="utf-8"))
    if len(cards) != 331:
        raise RuntimeError(f"expected 331 English cards, found {len(cards)}")
    rows = []
    for source_index, card in enumerate(cards):
        key = f"{card['language']}::{card['source']}::{card['id']}"
        rows.append({
            "protocol": "metacom-v3-g0-official-protocol-english331-manifest-v1",
            "official_file_index": source_index,
            "card_key": key,
            "screen_id": f"esc331_{sha(key)[:16]}",
            "source": card["source"],
            "role_card_sha256": sha(card["base"]),
            "annotation_sha256": sha(canonical(card.get("annotation")))
        })
    if len({row["card_key"] for row in rows}) != 331:
        raise RuntimeError("duplicate card identity")
    OUT.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"status": "PASS", "cards": len(rows), "contains_card_text": False, "output": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
