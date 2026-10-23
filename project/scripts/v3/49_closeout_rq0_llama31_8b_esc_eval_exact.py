#!/usr/bin/env python3
"""Close out exact-protocol Llama generation and operational evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data" / "v3_authority"
PREFLIGHT = AUTHORITY / "rq0_llama31_8b_esc_eval_exact_preflight_v1.json"


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--out", type=Path,
        default=AUTHORITY / "rq0_llama31_8b_esc_eval_exact_generation_closeout_v1.json",
    )
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError("generation closeout exists; refusing overwrite")
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    ledger_path = args.run_dir / "private_turn_ledger.jsonl"
    rows = _rows(ledger_path)
    if any(row.get("run_identity") != preflight["run_identity"] for row in rows):
        raise RuntimeError("generation ledger identity mismatch")
    success = [row for row in rows if row.get("event") == "supporter_succeeded"]
    terminal = [row for row in rows if row.get("event") == "trajectory_terminal_failure"]
    physical_failures = [row for row in rows if row.get("event") == "supporter_failed"]
    keys = [(row["card_key"], row["turn"]) for row in success]
    complete_cards = {
        card for card in {row["card_key"] for row in success}
        if sum(row["card_key"] == card for row in success) == 5
    }
    result_path = args.run_dir / "official_result_llama31_8b_en.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    valid = (
        len(success) == 1655 and len(keys) == len(set(keys))
        and len(complete_cards) == 331 and len(result) == 331 and not terminal
    )
    usage = [row.get("usage") or {} for row in success]
    latency = [float(row["latency_ms"]) for row in success]
    report = {
        "protocol": "metacom-v3-rq0-llama31-8b-esc-eval-exact-generation-closeout-v1",
        "status": "GENERATION_COMPLETE_READY_FOR_OFFICIAL_SCORING" if valid else "GENERATION_INCOMPLETE",
        "run_identity": preflight["run_identity"],
        "cards": 331,
        "complete_dialogues": len(complete_cards),
        "successful_turns": len(success),
        "expected_turns": 1655,
        "physical_failed_attempts": len(physical_failures),
        "terminal_trajectories": len(terminal),
        "provider_length_finishes": sum(row.get("normalized_finish_reason") == "length" for row in success),
        "official_generator_max_new_tokens": 256,
        "input_tokens": sum(int(row.get("prompt_tokens", 0)) for row in usage),
        "output_tokens": sum(int(row.get("completion_tokens", 0)) for row in usage),
        "total_tokens": sum(int(row.get("total_tokens", 0)) for row in usage),
        "latency_ms": {
            "median": median(latency) if latency else None,
            "p90": _percentile(latency, 0.9) if latency else None,
            "p95": _percentile(latency, 0.95) if latency else None,
        },
        "qwen_calls": 0,
        "observed_usd": 0.0,
        "official_result_dialogues": len(result),
        "official_result_entries_each": sorted({len(value) for value in result.values()}),
        "evidence_hashes": {
            "private_turn_ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            "official_result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        },
        "official_pass_line": None,
        "next": "Run the pinned ESC-Eval score.py / ESC-RANK seven-dimension profile."
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
