#!/usr/bin/env python3
"""Materialize a zero-inference ESC-RANK runtime-overlay preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from metacom_pm.esc_rank_runtime import (
    ESCRankRuntimeIdentity,
    repair_official_adapter_paths,
)


def _git_head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def materialize(esc_eval: Path) -> dict[str, object]:
    identity = ESCRankRuntimeIdentity()
    if _git_head(esc_eval) != identity.esc_eval_commit:
        raise ValueError("ESC-Eval checkout is not at the frozen commit")
    official_path = esc_eval / "score.py"
    official = official_path.read_text(encoding="utf-8")
    repaired = repair_official_adapter_paths(official)
    if len(repaired.encode("utf-8")) != len(official.encode("utf-8")) - 2:
        raise ValueError("bounded path repair changed an unexpected number of bytes")
    return {
        "protocol": "metacom-v3-esc-rank-runtime-preflight-v1",
        "date": "2026-08-13",
        "status": "STATIC_OVERLAY_PREFLIGHT_PASS_WEIGHTS_AND_INFERENCE_NOT_EXECUTED",
        "runtime_identity": identity.as_dict(),
        "official_score_py_sha256": _sha(official.encode("utf-8")),
        "path_repaired_score_py_sha256": _sha(repaired.encode("utf-8")),
        "bounded_source_changes": [
            "./ESC-RANK1/fluency -> ./ESC-RANK/fluency",
            "./ESC-RANK1/fluency_en -> ./ESC-RANK/fluency_en",
        ],
        "parser_overlay": "metacom_pm.esc_rank_runtime.parse_strict_ordinal",
        "strict_parser_contract": "trim whitespace, accept only a complete single digit 0..4, otherwise INVALID",
        "official_prompt_or_dialogue_text_embedded": False,
        "model_weights_downloaded": 0,
        "inference_calls": 0,
        "generated_tokens": 0,
        "remaining_p1_steps": [
            "create an isolated dependency environment and record package lock",
            "download the pinned InternLM2 base and ESC-RANK adapters after explicit approval",
            "run load and deterministic smoke checks",
            "bind the full scorer request/output ledger before benchmark inference",
        ],
        "authorization": "This preflight authorizes no download, inference, judge call, or benchmark verdict.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = materialize(args.esc_eval)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": payload["status"], "inference_calls": 0, "sha256": _sha(rendered.encode("utf-8"))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
