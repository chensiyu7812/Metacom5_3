#!/usr/bin/env python3
"""Freeze the local ESC-RANK scoring identity after exact generation closes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data" / "v3_authority"
GEN_PREFLIGHT = AUTHORITY / "rq0_llama31_8b_esc_eval_exact_preflight_v1.json"
SCORER = Path(__file__).with_name("48_score_rq0_llama31_8b_esc_eval_exact.py")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--out", type=Path,
        default=AUTHORITY / "rq0_llama31_8b_esc_eval_exact_score_preflight_v1.json",
    )
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError("score preflight exists; refusing overwrite")
    generation = json.loads((args.run_dir / "summary.json").read_text(encoding="utf-8"))
    source = json.loads(GEN_PREFLIGHT.read_text(encoding="utf-8"))
    if generation.get("run_identity") != source["run_identity"]:
        raise RuntimeError("generation identity mismatch")
    if generation.get("complete_official_dialogues") != 331 or generation.get("successful_turns") != 1655:
        raise RuntimeError("generation is incomplete")
    result = args.run_dir / "official_result_llama31_8b_en.json"
    result_data = json.loads(result.read_text(encoding="utf-8"))
    if len(result_data) != 331 or any(len(dialogue) != 11 for dialogue in result_data.values()):
        raise RuntimeError("official result shape must be 331 dialogues of 11 entries")
    measurement = {
        "esc_eval_commit": "9ad46e7b5e247e824dae4633910eaa82be668beb",
        "internlm2_revision": "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2",
        "esc_rank_revision": "450bf2eb5376c79e371aaf432925810243de1527",
        "score_py_sha256": _sha(args.esc_eval / "score.py"),
        "scorer_sha256": _sha(SCORER),
        "result_sha256": _sha(result),
        "dialogues": 331,
        "dimension_calls": 2317,
    }
    payload = {
        "protocol": "metacom-v3-rq0-llama31-8b-esc-eval-exact-score-v1",
        "source_generation_identity": source["run_identity"],
        "measurement": measurement,
    }
    identity = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    report = {
        "protocol": "metacom-v3-rq0-llama31-8b-esc-eval-exact-score-preflight-v1",
        "status": "LOCAL_OFFICIAL_SCORING_IDENTITY_FROZEN",
        "source_generation_identity": source["run_identity"],
        "score_identity": identity,
        "identity_payload": payload,
        "measurement": measurement,
        "result_sha256": measurement["result_sha256"],
        "paid_api_calls": 0,
        "estimated_usd": 0.0,
        "official_pass_line": None,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
