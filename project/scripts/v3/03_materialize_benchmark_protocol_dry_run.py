#!/usr/bin/env python3
"""Materialize a text-free, zero-call ESC benchmark protocol manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ESC_EVAL_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
ESC_JUDGE_COMMIT = "1ad30da04f9d0a171b7e4c1d0f5edf55587b21a9"
ROLE_SELECTION_SALT = "metacom-v3-esc-judge-role-v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8"))


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _git_head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def materialize(esc_eval: Path, esc_judge: Path) -> dict[str, Any]:
    esc_eval_head = _git_head(esc_eval)
    esc_judge_head = _git_head(esc_judge)
    if esc_eval_head != ESC_EVAL_COMMIT:
        raise ValueError(f"unexpected ESC-Eval commit: {esc_eval_head}")
    if esc_judge_head != ESC_JUDGE_COMMIT:
        raise ValueError(f"unexpected ESC-Judge commit: {esc_judge_head}")

    card_files = [
        esc_eval / "data" / "card_high_en.json",
        esc_eval / "data" / "card_high_zh.json",
    ]
    cards: list[dict[str, Any]] = []
    for path in card_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for card in payload:
            cards.append(
                {
                    "card_key": f"{card['language']}::{card['source']}::{card['id']}",
                    "language": card["language"],
                    "source": card["source"],
                    "source_card_id": str(card["id"]),
                    "role_card_sha256": _sha_text(card["base"]),
                    "annotation_sha256": _sha_text(card["base_biaozhu"]),
                }
            )
    cards.sort(key=lambda row: row["card_key"])
    if len(cards) != 655 or len({row["card_key"] for row in cards}) != 655:
        raise ValueError("ESC-Eval card identity is not 655 unique rows")

    roles_path = esc_judge / "data" / "roles-v1.json"
    roles = _jsonl(roles_path)
    if len(roles) != 100 or len({role["pid"] for role in roles}) != 100:
        raise ValueError("ESC-Judge roles-v1 is not 100 unique roles")
    ranked_roles = sorted(
        roles,
        key=lambda role: _sha_text(f"{ROLE_SELECTION_SALT}|{role['pid']}"),
    )
    selected_roles = [
        {
            "role_id": role["pid"],
            "selection_rank": rank,
            "role_sha256": _sha_text(role["role"]),
        }
        for rank, role in enumerate(ranked_roles[:25], start=1)
    ]
    constructs = ["Exploration", "Insight", "Action"]
    judge_units = []
    for role in selected_roles:
        for construct in constructs:
            for orientation, model_a, model_b in (
                ("candidate_A", "CANDIDATE_MODEL_PENDING", "REFERENCE_MODEL_PENDING"),
                ("candidate_B", "REFERENCE_MODEL_PENDING", "CANDIDATE_MODEL_PENDING"),
            ):
                judge_units.append(
                    {
                        "unit_id": f"{role['selection_rank']:02d}::{construct}::{orientation}",
                        "role_id": role["role_id"],
                        "construct": construct,
                        "orientation": orientation,
                        "model_a": model_a,
                        "model_b": model_b,
                    }
                )

    prompt_files = [
        esc_judge / "data" / "ESEval-multidim-cot.txt",
        esc_judge / "data" / "exploration_rubric3.jsonl",
        esc_judge / "data" / "emotional_supporter_nodir.txt",
        esc_judge / "data" / "emotional_supporter_hill.txt",
    ]
    return {
        "protocol": "metacom-v3-benchmark-protocol-dry-run-manifest-v1",
        "contains_role_or_dialogue_text": False,
        "api_calls": 0,
        "execution_ready": False,
        "execution_blockers": [
            "candidate model revision and sampling settings are not bound",
            "same-stack reference is not bound",
            "ESC scorer and ESC-Judge model are not qualified",
        ],
        "ESC-Eval": {
            "repository_commit": esc_eval_head,
            "card_count": len(cards),
            "card_file_hashes": {path.name: _sha_file(path) for path in card_files},
            "cards": cards,
            "official_runner_sha256": _sha_file(esc_eval / "evaluate.py"),
            "official_scorer_sha256": _sha_file(esc_eval / "score.py"),
            "official_scorer_status": "UNQUALIFIED_STATIC_DEFECT_AND_CALIBRATION_PENDING",
        },
        "ESC-Judge": {
            "repository_commit": esc_judge_head,
            "public_role_count": len(roles),
            "paper_role_identity_reproduced": False,
            "selection_rule": f"lowest SHA256({ROLE_SELECTION_SALT}|pid), first 25",
            "selected_role_count": len(selected_roles),
            "selected_roles": selected_roles,
            "constructs": constructs,
            "judge_unit_count": len(judge_units),
            "judge_units": judge_units,
            "prompt_hashes": {path.name: _sha_file(path) for path in prompt_files},
            "position_policy": "both candidate_A and candidate_B are mandatory",
            "tie_invalid_policy": ["TIE", "INVALID", "REFUSAL", "POSITION_UNSTABLE"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--esc-judge", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    manifest = materialize(args.esc_eval, args.esc_judge)
    rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "esc_eval_cards": manifest["ESC-Eval"]["card_count"],
                "esc_judge_selected_roles": manifest["ESC-Judge"]["selected_role_count"],
                "esc_judge_units": manifest["ESC-Judge"]["judge_unit_count"],
                "api_calls": manifest["api_calls"],
                "manifest_sha256": _sha_text(rendered),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
