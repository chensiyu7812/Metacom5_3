#!/usr/bin/env python3
"""Materialize the exact-code ESC-Eval Llama-only run identity."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY / "rq0_llama31_8b_esc_eval_exact_contract_v1.json"
RUNNER_PATH = Path(__file__).with_name("46_run_rq0_llama31_8b_esc_eval_exact.py")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize(esc_eval: Path) -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    official = contract["official_interaction"]
    head = subprocess.run(
        ["git", "-C", str(esc_eval), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if head != official["source_commit"]:
        raise RuntimeError("ESC-Eval checkout drifted")
    cards_path = esc_eval / "data" / "card_high_en.json"
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    if len(cards) != 331:
        raise RuntimeError("official English high-quality card count changed")
    if official["role_generation"] != {
        "model": "haidequanbu/ESC-Role",
        "revision": "2e2a4733d2e71da242f348aad165fe171acd5df7",
        "max_new_tokens": 512,
        "explicit_arguments_in_evaluate_py": "max_new_tokens only",
        "model_generation_config_effective": {
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "repetition_penalty": 1.05,
        },
        "project_seed": None,
    }:
        raise RuntimeError("official ESC-Role generation contract drifted")
    if official["generator_generation"]["max_new_tokens"] != 256:
        raise RuntimeError("official Llama 256-token condition drifted")
    input_hashes = {
        CONTRACT_PATH.name: _sha(CONTRACT_PATH),
        RUNNER_PATH.name: _sha(RUNNER_PATH),
        "ESC-Eval/evaluate.py": _sha(esc_eval / "evaluate.py"),
        "ESC-Eval/score.py": _sha(esc_eval / "score.py"),
        "ESC-Eval/data/card_high_en.json": _sha(cards_path),
    }
    payload = {
        "protocol": contract["protocol"],
        "candidate": contract["candidate"],
        "official_interaction": official,
        "provider_adaptation": contract["provider_adaptation"],
        "official_scoring": contract["official_scoring"],
        "interpretation": contract["interpretation"],
        "input_hashes": input_hashes,
    }
    identity = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {
        "protocol": "metacom-v3-rq0-llama31-8b-esc-eval-exact-preflight-v1",
        "status": "ZERO_CALL_EXACT_OFFICIAL_CODE_IDENTITY_FROZEN_USER_AUTHORIZED",
        "run_identity": identity,
        "identity_payload": payload,
        "identity_payload_sha256": identity,
        "input_hashes": input_hashes,
        "cards_text_sha256": hashlib.sha256(cards_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
        "call_accounting": {"cards": 331, "turns": 5, "llama_supporter_calls": 1655, "qwen_calls": 0},
        "official_conditions": {
            "role_max_new_tokens": 512,
            "role_other_generation_args": "MODEL_GENERATION_CONFIG",
            "role_project_seed": None,
            "llama_max_new_tokens": 256,
            "llama_temperature": 0.0,
            "supporter_prompt": "You are a helpful assistant!"
        },
        "budget": contract["budget"],
        "api_calls": 0,
        "authorization": contract["authorization"]
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=AUTHORITY / "rq0_llama31_8b_esc_eval_exact_preflight_v1.json")
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError("exact preflight exists; refusing overwrite")
    report = materialize(args.esc_eval)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
