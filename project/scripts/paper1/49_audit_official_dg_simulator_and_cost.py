#!/usr/bin/env python3
"""Audit official ES-MemEval DG calls and compute a zero-outcome cost surface.

No model or evaluator is called.  Future unknown dialogue messages are
bounded by the official 60-token cap.  The report distinguishes the pinned
upstream implementation from project execution choices that still require a
pre-call freeze.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import tiktoken

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import read_json, sha256_file, sha256_text, write_json  # noqa: E402
from metacom_pm.paper1.execution.dg_official import (  # noqa: E402
    DG_OFFICIAL_MAX_OUTPUT_TOKENS,
    DG_OFFICIAL_ROUNDS,
    DG_OFFICIAL_SEEKER_MODEL_ALIAS,
    DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
    build_official_dg_seeker_system_prompt,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)

PROTOCOL = "paper1-official-dg-simulator-and-cost-audit-v1"
ES_MEMEVAL_COMMIT = "692624208acc077b8867698c1d6fcd998dee641a"
UPSTREAM_DG = PROJECT / "outputs/vendor_es_memeval/src/lib/dg/dg_experiment.py"
UPSTREAM_CONFIG = PROJECT / "outputs/vendor_es_memeval/src/exe/common_configurations.py"
DATA = PROJECT / "outputs/vendor_es_memeval/data/evo_emo.json"
INPUT_USD_PER_MTOK = 2.50
CACHED_INPUT_USD_PER_MTOK = 1.25
OUTPUT_USD_PER_MTOK = 10.00
SYSTEM_OVERHEAD_RESERVE_TOKENS = 32
PER_MESSAGE_OVERHEAD_RESERVE_TOKENS = 32


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_official_dg_simulator_call_cost_surface_20260904_v1.json",
    )
    return parser.parse_args()


def _cost(input_tokens: int, output_tokens: int, *, cached_input: bool = False) -> float:
    input_rate = CACHED_INPUT_USD_PER_MTOK if cached_input else INPUT_USD_PER_MTOK
    return input_tokens * input_rate / 1_000_000 + output_tokens * OUTPUT_USD_PER_MTOK / 1_000_000


def _nearest_rank(values: list[int], probability: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _distribution(values: list[int]) -> dict[str, int | float]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": (ordered[(len(ordered) - 1) // 2] + ordered[len(ordered) // 2]) / 2,
        "p95_nearest_rank": _nearest_rank(ordered, 0.95),
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
    }


def main() -> int:
    args = _args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    users: list[dict[str, Any]] = read_json(DATA)
    encoding = tiktoken.encoding_for_model(DG_REPRODUCIBLE_SEEKER_SNAPSHOT)

    source = UPSTREAM_DG.read_text(encoding="utf-8")
    upstream_config = UPSTREAM_CONFIG.read_text(encoding="utf-8")
    required_source_fragments = (
        "for turn in range(1, 11):",
        "self.__parameters.seeker.create_model(logger, max_tokens=60)",
        "for _ in range(3):",
        'finish_reason"].lower() == "stop"',
    )
    if any(fragment not in source for fragment in required_source_fragments):
        raise RuntimeError("pinned upstream DG control flow no longer matches the audited surface")
    dg_executables = sorted(
        (PROJECT / "outputs/vendor_es_memeval/src/exe/dg").glob("dg_*.py")
    )
    if len(dg_executables) != 15 or any(
        "seeker_model: ChatModelIndicator = common_configurations.gpt4o"
        not in path.read_text(encoding="utf-8")
        for path in dg_executables
    ):
        raise RuntimeError("not every pinned official DG executable binds its seeker to gpt4o")
    if 'gpt4o: _OpenaiModelIndicator = _OpenaiModelIndicator("gpt-4o"' not in upstream_config:
        raise RuntimeError("pinned official common configuration no longer names gpt-4o")

    per_request_reserves: list[int] = []
    prompt_content_tokens: list[int] = []
    scenario_rows: list[dict[str, Any]] = []
    total_observations = 0
    for user in users:
        first = f'Hi {user["basic_info"]["name"]}! How are you these days?'
        first_tokens = len(encoding.encode(first))
        sessions = {str(session["id"]): session for session in user["dialog_history"]}
        for topic in user["subsequent_topics"]:
            system = build_official_dg_seeker_system_prompt(user=user, topic=topic)
            system_tokens = len(encoding.encode(system))
            observations = sum(
                len(sessions[str(session_id)]["observation"])
                for session_id in topic["related_sessions"]
            )
            total_observations += observations
            turn_reserves = []
            for turn in range(1, DG_OFFICIAL_ROUNDS + 1):
                message_count = 2 + 2 * (turn - 1)
                known_content = system_tokens + first_tokens
                unknown_prior_content_max = 2 * (turn - 1) * DG_OFFICIAL_MAX_OUTPUT_TOKENS
                reserve = (
                    known_content
                    + unknown_prior_content_max
                    + SYSTEM_OVERHEAD_RESERVE_TOKENS
                    + message_count * PER_MESSAGE_OVERHEAD_RESERVE_TOKENS
                )
                prompt_content_tokens.append(known_content + unknown_prior_content_max)
                per_request_reserves.append(reserve)
                turn_reserves.append(reserve)
            scenario_rows.append(
                {
                    "owner_id": str(user["id"]),
                    "topic_index": int(topic["idx"]),
                    "system_prompt_sha256": sha256_text(system),
                    "system_prompt_tiktoken_tokens": system_tokens,
                    "related_session_count": len(topic["related_sessions"]),
                    "related_observation_count": observations,
                    "ten_turn_seeker_input_reserve_tokens": sum(turn_reserves),
                    "max_single_turn_seeker_input_reserve_tokens": max(turn_reserves),
                    "contains_prompt_text": False,
                }
            )

    scenario_count = len(scenario_rows)
    systems = 6
    logical_seeker_calls = systems * scenario_count * DG_OFFICIAL_ROUNDS
    one_attempt_input = systems * sum(per_request_reserves)
    one_attempt_output = logical_seeker_calls * DG_OFFICIAL_MAX_OUTPUT_TOKENS
    upstream_three_attempt_input = one_attempt_input * 3
    upstream_three_attempt_output = one_attempt_output * 3
    overall_calls = systems * scenario_count
    observation_relevance_calls = systems * total_observations * DG_OFFICIAL_ROUNDS
    observation_usage_calls = observation_relevance_calls

    report = {
        "protocol": PROTOCOL,
        "date": "2026-09-04",
        "status": "ZERO_OUTCOME_AUDIT_COMPLETE_EXECUTION_CHOICE_PENDING",
        "not_an_empirical_pass_gate": True,
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "paid_api_calls": 0,
        "upstream": {
            "repo": "slptongji/ES-MemEval",
            "commit": ES_MEMEVAL_COMMIT,
            "dg_executables_checked": len(dg_executables),
            "dg_source_sha256": sha256_file(UPSTREAM_DG),
            "common_config_source_sha256": sha256_file(UPSTREAM_CONFIG),
            "seeker_model_in_code": DG_OFFICIAL_SEEKER_MODEL_ALIAS,
            "seeker_rounds_per_scenario": DG_OFFICIAL_ROUNDS,
            "seeker_max_output_tokens": DG_OFFICIAL_MAX_OUTPUT_TOKENS,
            "non_stop_generation_attempts_in_code": 3,
            "seeker_is_conditioned_on_prior_supporter_responses": True,
            "seeker_hidden_scenario_fields": [
                "all session summaries",
                "all event summaries",
                "related-session transcripts",
                "topic",
                "psychological_condition",
                "physical_condition",
                "more_details",
            ],
            "hidden_fields_visible_to_supporter_or_PM": False,
            "mixtral_or_qwen_seeker_is_official_requirement": False,
        },
        "reproducible_route_candidate": {
            "model": DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
            "reason": "pin the latest GPT-4o snapshot predating the 2025-11-23 public repository commit instead of using a moving alias",
            "account_catalog_presence_checked_2026_09_04": True,
            "account_catalog_model_present": True,
            "source_fidelity": "official GPT-4o family and exact prompt/role sequence; snapshot pin is a reproducibility amendment",
            "batch_allowed_for_sequential_seeker_calls": False,
        },
        "public_population": {
            "owners": len(users),
            "scenarios": scenario_count,
            "related_observations_across_scenarios": total_observations,
            "scenario_prompt_tokens": _distribution(
                [int(row["system_prompt_tiktoken_tokens"]) for row in scenario_rows]
            ),
            "seeker_input_reserve_per_request_tokens": _distribution(per_request_reserves),
            "scenario_rows": scenario_rows,
        },
        "six_system_call_surface": {
            "seeker_logical_calls": logical_seeker_calls,
            "local_supporter_calls": logical_seeker_calls,
            "gpt4o_overall_judge_calls": overall_calls,
            "local_mistral24b_observation_relevance_calls": observation_relevance_calls,
            "local_mistral24b_observation_usage_calls": observation_usage_calls,
            "total_local_mistral24b_turn_judge_calls": observation_relevance_calls
            + observation_usage_calls,
            "correction_to_old_planning_arithmetic": (
                "official code scores every related observation at every one of ten turns; "
                "it does not make five observation-aggregation calls per trajectory"
            ),
        },
        "pricing_snapshot": {
            "source": "https://developers.openai.com/api/docs/models/gpt-4o",
            "checked_date": "2026-09-04",
            "input_usd_per_million_tokens": INPUT_USD_PER_MTOK,
            "cached_input_usd_per_million_tokens": CACHED_INPUT_USD_PER_MTOK,
            "output_usd_per_million_tokens": OUTPUT_USD_PER_MTOK,
            "prompt_cache_discount_counted_in_hard_reserve": False,
        },
        "seeker_cost_surface_six_systems": {
            "one_physical_attempt_per_logical_call": {
                "reserved_input_tokens": one_attempt_input,
                "reserved_output_tokens": one_attempt_output,
                "uncached_worst_case_usd": _cost(one_attempt_input, one_attempt_output),
                "all_input_cached_sensitivity_usd_not_a_reserve": _cost(
                    one_attempt_input, one_attempt_output, cached_input=True
                ),
            },
            "upstream_max_three_attempts_every_logical_call": {
                "reserved_input_tokens": upstream_three_attempt_input,
                "reserved_output_tokens": upstream_three_attempt_output,
                "uncached_worst_case_usd": _cost(
                    upstream_three_attempt_input, upstream_three_attempt_output
                ),
            },
            "estimator": {
                "encoding": encoding.name,
                "known_prompt_content_counted_exactly": True,
                "unknown_prior_seeker_and_supporter_content": "official 60-token cap per message",
                "per_message_serialization_reserve_tokens": PER_MESSAGE_OVERHEAD_RESERVE_TOKENS,
                "per_request_extra_reserve_tokens": SYSTEM_OVERHEAD_RESERVE_TOKENS,
                "actual_usage_must_replace_reservations_after_each_call": True,
            },
        },
        "decision_required_before_paid_dg": {
            "issue": (
                "The upstream non-stop behavior can spend up to three physical GPT-4o calls "
                "for one logical seeker turn and is incompatible with the current USD 22 RQ2 envelope."
            ),
            "options": [
                "retain bit-level upstream retry behavior and reduce DG systems/scenarios or increase budget",
                "freeze one physical attempt plus deterministic complete-sentence prefix handling as an explicit official-method cost amendment",
            ],
            "result_driven_choice_forbidden": True,
        },
        "locks": {
            "RQ1_RS_CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "RQ1_CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
            "RQ2_CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
        },
    }
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
