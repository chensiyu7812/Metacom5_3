#!/usr/bin/env python3
"""Create a zero-API, text-free snapshot of pinned public benchmark surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _jsonl_count(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                json.loads(line)
                count += 1
    return count


def audit(esc_eval: Path, esc_judge: Path, es_memeval: Path) -> dict[str, Any]:
    en_path = esc_eval / "data" / "card_high_en.json"
    zh_path = esc_eval / "data" / "card_high_zh.json"
    en_cards = json.loads(en_path.read_text(encoding="utf-8"))
    zh_cards = json.loads(zh_path.read_text(encoding="utf-8"))

    roles_path = esc_judge / "data" / "roles-v1.json"
    judge_code = (esc_judge / "multidim_merge_and_judge.py").read_text(encoding="utf-8")
    requirements = [
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "environment.yml",
    ]

    mem_path = es_memeval / "data" / "evo_emo.json"
    mem = json.loads(mem_path.read_text(encoding="utf-8"))
    qa = sum(len(group["questions"]) for user in mem for group in user["questions"])

    return {
        "protocol": "metacom-v3-official-benchmark-surface-snapshot-v1",
        "contains_record_text": False,
        "ESC-Eval": {
            "commit": _git(esc_eval, "rev-parse", "HEAD"),
            "high_quality_cards": {
                "en": len(en_cards),
                "zh": len(zh_cards),
                "total": len(en_cards) + len(zh_cards),
            },
            "hashes": {"card_high_en": _sha256(en_path), "card_high_zh": _sha256(zh_path)},
            "license_file_present": (esc_eval / "LICENSE").is_file(),
            "dependency_lock_present": any((esc_eval / name).is_file() for name in requirements),
            "fluency_path_mismatch_present": "./ESC-RANK1/fluency" in (esc_eval / "score.py").read_text(encoding="utf-8"),
        },
        "ESC-Judge": {
            "commit": _git(esc_judge, "rev-parse", "HEAD"),
            "roles_v1_records": _jsonl_count(roles_path),
            "roles_v1_sha256": _sha256(roles_path),
            "license_file_present": (esc_judge / "LICENSE").is_file(),
            "dependency_lock_present": any((esc_judge / name).is_file() for name in requirements),
            "judge_temperature_1_present": "temperature=1.0" in judge_code,
            "explicit_bidirectional_order_aggregation_present": False,
        },
        "ES-MemEval": {
            "commit": _git(es_memeval, "rev-parse", "HEAD"),
            "public_git_commits": int(_git(es_memeval, "rev-list", "--count", "HEAD")),
            "evo_emo_sha256": _sha256(mem_path),
            "users": len(mem),
            "sessions": sum(len(user["dialog_history"]) for user in mem),
            "qa": qa,
            "summaries": sum(len(user["summaries"]) for user in mem),
            "generation_scenarios": sum(len(user["subsequent_topics"]) for user in mem),
            "license_file_present": (es_memeval / "LICENSE").is_file(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--esc-judge", required=True, type=Path)
    parser.add_argument("--es-memeval", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.esc_eval, args.esc_judge, args.es_memeval)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
