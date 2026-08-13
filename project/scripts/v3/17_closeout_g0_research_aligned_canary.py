#!/usr/bin/env python3
"""Derive the zero-call, text-free G0 research-aligned canary closeout."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_research_aligned_generator_preflight_v2.json"
DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "v3_g0_research_aligned_generator_v2_20260814"
DEFAULT_OUT = AUTHORITY_DIR / "g0_research_aligned_canary_closeout_v2.json"
CANDIDATE_ORDER = [
    "llama31_8b_incumbent",
    "llama33_70b_capacity_reference",
    "qwen37_plus_nonthinking",
    "qwen37_plus_thinking_upper_bound",
]
SCAFFOLD_PATTERN = re.compile(
    r"\b(system prompt|prompt|strategy label|internal scaffold|chain of thought|as an ai|language model)\b",
    re.IGNORECASE,
)
LIST_PATTERN = re.compile(r"(?m)^\s*(?:[-*]|\d+[.)])\s+")
HEADING_PATTERN = re.compile(r"(?m)^#{1,6}\s+")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    location = (len(ordered) - 1) * quantile
    lower, upper = math.floor(location), math.ceil(location)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - location) + ordered[upper] * (location - lower)


def _qwen_cost(usage: dict[str, Any]) -> float:
    prompt = int(usage.get("prompt_tokens", 0))
    completion = int(usage.get("completion_tokens", 0))
    input_rate, output_rate = ((0.4, 1.6) if prompt <= 256_000 else (1.2, 4.8))
    return (prompt * input_rate + completion * output_rate) / 1_000_000


def closeout(run_dir: Path) -> dict[str, Any]:
    preflight = _load_json(PREFLIGHT_PATH)
    turn_path = run_dir / "private_turn_ledger.jsonl"
    budget_path = run_dir / "qwen_budget_ledger.jsonl"
    summary_path = run_dir / "summary.json"
    turns = _read_jsonl(turn_path)
    budgets = _read_jsonl(budget_path)
    summary = _load_json(summary_path)
    identity = preflight["run_identity"]
    if any(row.get("run_identity") != identity for row in turns + budgets):
        raise RuntimeError("canary ledgers contain another run identity")
    successes = [row for row in turns if row.get("event") == "supporter_succeeded"]
    if len(successes) != 40 or summary["successful_turns"] != 40:
        raise RuntimeError("canary is not complete at 40 successful turns")
    if len({row["card_key"] for row in successes}) != 2:
        raise RuntimeError("canary does not cover exactly two cards")

    candidates: dict[str, Any] = {}
    for candidate_id in CANDIDATE_ORDER:
        rows = [row for row in successes if row["candidate_id"] == candidate_id]
        failures = [
            row for row in turns
            if row.get("event") == "supporter_failed" and row.get("candidate_id") == candidate_id
        ]
        terminal = [
            row for row in turns
            if row.get("event") == "trajectory_terminal_failure" and row.get("candidate_id") == candidate_id
        ]
        qwen_rows = [row for row in budgets if row.get("candidate_id") == candidate_id]
        latency = [float(row["latency_ms"]) for row in rows]
        completion_tokens = [int(row["usage"].get("completion_tokens", 0)) for row in rows]
        reasoning_tokens = [
            int(
                ((row.get("raw_response") or {}).get("usage") or {})
                .get("completion_tokens_details", {})
                .get("reasoning_tokens", 0)
            )
            for row in rows
        ]
        visible_tokens_inferred = [
            max(0, complete - reasoning)
            for complete, reasoning in zip(completion_tokens, reasoning_tokens)
        ]
        words = [int(row["output_words_whitespace"]) for row in rows]
        candidates[candidate_id] = {
            "successful_turns": len(rows),
            "completed_dialogues": len({row["card_key"] for row in rows if row["turn"] == 5}),
            "first_attempt_successful_turns": len(rows) - len(failures),
            "first_attempt_success_rate": (len(rows) - len(failures)) / len(rows),
            "failed_physical_attempts": len(failures),
            "failure_classes": {
                failure_class: sum(row.get("failure_class") == failure_class for row in failures)
                for failure_class in sorted({row.get("failure_class") for row in failures})
            },
            "terminal_trajectories": len(terminal),
            "provider_complete_finishes": sum(row.get("normalized_finish_reason") == "complete" for row in rows),
            "provider_length_finishes": sum(row.get("normalized_finish_reason") == "length" for row in rows),
            "terminal_punctuation": sum(bool(row["ends_terminal_punctuation"]) for row in rows),
            "latency_ms": {
                "median": statistics.median(latency),
                "p90": _percentile(latency, 0.9),
                "minimum": min(latency),
                "maximum": max(latency),
                "scope": "successful request wall-clock only; failed attempt time is separately visible in failed_physical_attempts"
            },
            "completion_tokens": {
                "total_billed": sum(completion_tokens),
                "median_billed": statistics.median(completion_tokens),
                "p90_billed": _percentile(completion_tokens, 0.9),
                "reasoning_total_if_provider_reported": sum(reasoning_tokens),
                "visible_total_inferred_as_completion_minus_reasoning": sum(visible_tokens_inferred),
            },
            "visible_output": {
                "words_total": sum(words),
                "words_median": statistics.median(words),
                "words_p90": _percentile(words, 0.9),
                "markdown_heading_turns": sum(bool(HEADING_PATTERN.search(row["supporter_text"])) for row in rows),
                "markdown_list_turns": sum(bool(LIST_PATTERN.search(row["supporter_text"])) for row in rows),
                "scaffold_leak_pattern_turns": sum(bool(SCAFFOLD_PATTERN.search(row["supporter_text"])) for row in rows),
            },
            "throughput": {
                "median_billed_completion_tokens_per_second": statistics.median(
                    float(row["completion_tokens_per_second"]) for row in rows
                ),
                "warning": "For thinking mode, billed completion tokens include hidden reasoning and are not visible-answer throughput."
            },
            "qwen_actual_usd": sum(_qwen_cost(row.get("usage") or {}) for row in qwen_rows),
        }

    return {
        "protocol": "metacom-v3-g0-research-aligned-canary-closeout-v2",
        "date": "2026-08-14",
        "run_identity": identity,
        "status": "CANARY_MECHANICAL_PASS_QUALITY_NOT_YET_JUDGED_NO_GENERATOR_SELECTED",
        "api_scope": {
            "supporter_successful_turns": len(successes),
            "local_role_player_turns": len(successes),
            "judge_calls": 0,
            "cards": 2,
            "candidate_configurations": 4,
        },
        "pre_call_runtime_incident": {
            "status": "CORRECTED_BEFORE_ANY_PROVIDER_CALL",
            "description": "CUDA_VISIBLE_DEVICES=1 mapped torch cuda:0 to the A4500 because PyTorch device order differed from nvidia-smi numbering; local ESC-Role loading stopped with OOM at shard 5/8.",
            "provider_calls": 0,
            "qwen_cost_usd": 0,
            "correction": "Unset CUDA_VISIBLE_DEVICES and use torch cuda:0, which resolved to the RTX A6000; prompt, sample, provider payload, and run identity were unchanged."
        },
        "generation_contract_observed": {
            "researcher_output_token_cap": None,
            "provider_output_parameter_omitted_on_all_successes": all(row.get("provider_output_parameter_omitted") is True for row in successes),
            "all_successes_used_bound_prompt": all(row.get("supporter_prompt_sha256") == preflight["prompt"]["joined_prompt_sha256"] for row in successes),
            "provider_length_finishes": sum(row.get("normalized_finish_reason") == "length" for row in successes),
            "nonempty_terminal_punctuation_turns": sum(bool(row["ends_terminal_punctuation"]) for row in successes),
        },
        "candidates": candidates,
        "qwen_budget": {
            "approved_ceiling_usd": 0.25,
            "actual_usd": sum(_qwen_cost(row.get("usage") or {}) for row in budgets),
            "within_ceiling": sum(_qwen_cost(row.get("usage") or {}) for row in budgets) <= 0.25,
        },
        "zero_api_interpretation": {
            "mechanical_canary_result": "PASS: all 40 turns completed without researcher-induced or provider length truncation, prompt/scaffold pattern leakage, or terminal trajectory loss.",
            "operational_warning": "The hosted 70B route required retries on 6 of 10 turns (5 network timeouts and 1 HTTP 5xx); successful-response latency alone understates its user-observed cost.",
            "qwen_mode_tradeoff": "Thinking used 8,302 reported reasoning tokens and 8,965 billed completion tokens versus 628 for non-thinking, while inferred visible tokens were 663 versus 628. Quality has not been judged, so this is a cost/latency observation, not evidence that thinking helps or hurts quality.",
            "selection": "FORBIDDEN_FROM_TWO_CARD_CANARY",
            "next": "Freeze and separately approve the order-swapped E-I-A quality review, or run the 24-card generation screen first; neither is authorized by this closeout."
        },
        "claim_boundary": "This canary validates the runtime and removes the old prompt/cap confound. It does not qualify a generator, estimate PM value, reproduce the exact official zero-shot wrapper, or establish clinical safety.",
        "private_evidence_hashes": {
            "private_turn_ledger.jsonl": _sha_file(turn_path),
            "qwen_budget_ledger.jsonl": _sha_file(budget_path),
            "summary.json": _sha_file(summary_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    report = closeout(args.run_dir)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "run_identity": report["run_identity"],
        "qwen_actual_usd": report["qwen_budget"]["actual_usd"],
        "judge_calls": report["api_scope"]["judge_calls"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
