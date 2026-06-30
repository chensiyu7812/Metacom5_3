from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Mapping, Sequence
import json

from pydantic import Field

from .api import Endpoint, make_client
from .artifacts import create_artifact_attestation, require_artifact_attestation
from .contracts import StrictModel
from .evoemo import evaluator_context, load_evoemo
from .io import (
    append_jsonl,
    canonical_json,
    iter_jsonl,
    load_done_keys,
    read_json,
    sha256_text,
    stable_hex,
    write_json,
)
from .judging import _call_with_semantic_retry


DEFAULT_RESPONSE_V4_CONDITIONS = (
    "pm",
    "strong_rule",
    "best_fixed",
    "session_rag_rs",
    "full_history_rs",
    "no_memory_r0",
)
DEFAULT_RESPONSE_V4_TURNS = (3, 8)
SCORE_FIELDS = (
    "emotional_support",
    "personalization",
    "memory_appropriateness",
    "factual_grounding",
    "temporal_consistency",
    "non_intrusiveness",
    "overall",
)


class EvoResponseV4CandidateScore(StrictModel):
    candidate_id: str
    emotional_support: int = Field(ge=1, le=5)
    personalization: int = Field(ge=1, le=5)
    memory_appropriateness: int = Field(ge=1, le=5)
    factual_grounding: int = Field(ge=1, le=5)
    temporal_consistency: int = Field(ge=1, le=5)
    non_intrusiveness: int = Field(ge=1, le=5)
    overall: int = Field(ge=1, le=5)
    reason: str = Field(min_length=1, max_length=700)


class EvoResponseV4Judgment(StrictModel):
    candidates: list[EvoResponseV4CandidateScore] = Field(min_length=1)


RESPONSE_V4_SYSTEM = """You are an evaluator-only judge for longitudinal emotional-support responses.
Each anonymous candidate answered the same single fixed-context seeker turn.
Score every candidate independently on 1-5 integer scales. Do not rank candidates,
do not reward mentioning more personal facts, and do not infer facts beyond the
authorized ground truth. Use the authorized profile/history/topic only to verify
factual grounding, useful personalization, temporal consistency, and whether
memory use is appropriate rather than intrusive. Return only JSON matching the
provided schema."""


RUBRIC = {
    "score_scale": {
        "1": "harmful, badly mismatched, or factually/temporally unsafe",
        "2": "weak or noticeably flawed",
        "3": "adequate but limited",
        "4": "good, supportive, and mostly well grounded",
        "5": "excellent, deeply supportive, well grounded, and non-intrusive",
    },
    "fields": {
        "emotional_support": "empathy, validation, warmth, and helpful emotional presence",
        "personalization": "uses relevant personal context when useful without overfitting",
        "memory_appropriateness": "uses or avoids memory in a way that fits the turn",
        "factual_grounding": "does not invent unsupported personal facts",
        "temporal_consistency": "respects current vs past events and avoids stale/conflicting claims",
        "non_intrusiveness": "does not over-probe, over-advise, or expose unnecessary private details",
        "overall": "holistic response quality for this fixed seeker input",
    },
}


def _dialogue_key(row: Mapping[str, Any]) -> tuple[str, int, str, int, str, str]:
    return (
        str(row["user_id"]),
        int(row["topic_index"]),
        str(row["condition"]),
        int(row["seed"]),
        str(row.get("simulator_id") or "unspecified"),
        str(row.get("interaction_mode") or "legacy_interactive"),
    )


def _topic_by_index(user: Mapping[str, Any], topic_index: int) -> dict[str, Any]:
    for topic in user.get("subsequent_topics") or []:
        if int(topic["idx"]) == topic_index:
            return topic
    raise KeyError(f"missing topic idx={topic_index} for user={user.get('id')}")


def _turn_by_index(dialogue: Mapping[str, Any], turn_index: int) -> dict[str, Any]:
    for turn in dialogue.get("turns") or []:
        if int(turn["turn_index"]) == turn_index:
            return dict(turn)
    raise KeyError(
        f"missing turn={turn_index} for condition={dialogue.get('condition')} "
        f"user={dialogue.get('user_id')} topic={dialogue.get('topic_index')}"
    )


def _compact_evaluator_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Smaller response-quality context for V4 dry-run experiments.

    It keeps current topic, profile, related session summaries and observations,
    but drops full historical dialogue text and the all-session timeline.
    """
    related = []
    for session in context.get("detailed_related_sessions") or []:
        related.append(
            {
                "session_id": session.get("session_id"),
                "timestamp": session.get("timestamp"),
                "summary": session.get("summary"),
                "observations": session.get("observations") or [],
            }
        )
    return {
        "user_profile": context.get("user_profile") or {},
        "related_session_summaries": related,
        "current_topic": context.get("current_topic") or {},
        "evaluator_only": True,
        "ground_truth_mode": "compact_related",
    }


def _ground_truth(
    user: Mapping[str, Any],
    topic: Mapping[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    full = evaluator_context(dict(user), dict(topic))
    if mode == "full":
        return full
    if mode == "compact_related":
        return _compact_evaluator_context(full)
    raise ValueError(f"unsupported ground_truth_mode: {mode}")


def balanced_candidate_order(
    conditions: Sequence[str],
    *,
    unit_ordinal: int,
    order_variant: int,
) -> list[str]:
    """Return a deterministic candidate order with full-run position balance."""
    values = list(conditions)
    if len(values) != len(set(values)):
        raise ValueError("conditions must be unique")
    if not values:
        raise ValueError("conditions must be non-empty")
    if order_variant % 2:
        values = list(reversed(values))
    offset = (unit_ordinal + order_variant) % len(values)
    return values[offset:] + values[:offset]


def _candidate_id(position: int) -> str:
    return f"C{position + 1}"


def _messages_for_unit(
    unit: Mapping[str, Any],
    *,
    condition_order: Sequence[str],
    candidate_by_condition: Mapping[str, Mapping[str, Any]],
    authorized_ground_truth: Mapping[str, Any],
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    mapping: dict[str, dict[str, Any]] = {}
    for position, condition in enumerate(condition_order):
        candidate_id = _candidate_id(position)
        turn = candidate_by_condition[condition]
        candidates.append(
            {
                "candidate_id": candidate_id,
                "response": turn["supporter_message"],
            }
        )
        mapping[candidate_id] = {
            "condition": condition,
            "position": position + 1,
            "action_id": turn.get("action_id"),
            "input_tokens": turn.get("input_tokens"),
            "output_tokens": turn.get("output_tokens"),
        }
    payload = {
        "task": "score independent fixed-context emotional-support responses",
        "rubric": RUBRIC,
        "authorized_ground_truth": authorized_ground_truth,
        "case": {
            "unit_id": unit["unit_id"],
            "turn_index": unit["turn_index"],
            "context_before_turn": unit["context_before_turn"],
            "current_seeker_message": unit["seeker_message"],
        },
        "candidates": candidates,
        "output_json_shape": {
            "candidates": [
                {
                    "candidate_id": "C1",
                    "emotional_support": 1,
                    "personalization": 1,
                    "memory_appropriateness": 1,
                    "factual_grounding": 1,
                    "temporal_consistency": 1,
                    "non_intrusiveness": 1,
                    "overall": 1,
                    "reason": "brief evidence-based reason",
                }
            ]
        },
    }
    return (
        [
            {"role": "system", "content": RESPONSE_V4_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
        mapping,
    )


def _count_message_tokens(messages: Sequence[Mapping[str, str]], model: str) -> int:
    try:
        import tiktoken  # type: ignore

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        # OpenAI chat framing approximation; good enough for fail-closed budget gates.
        return sum(4 + len(enc.encode(m.get("content", ""))) for m in messages) + 2
    except Exception:
        return max(1, sum(len(m.get("content", "")) for m in messages) // 4)


def _hash_record(value: dict[str, Any], field: str) -> dict[str, Any]:
    out = dict(value)
    out[field] = sha256_text(canonical_json(out))
    return out


def _load_dialogues(dialogues_path: str | Path) -> dict[tuple[str, int, str, int, str, str], dict[str, Any]]:
    by_key: dict[tuple[str, int, str, int, str, str], dict[str, Any]] = {}
    for row in iter_jsonl(dialogues_path):
        key = _dialogue_key(row)
        if key in by_key:
            raise ValueError(f"duplicate dialogue key: {key}")
        by_key[key] = row
    return by_key


def build_response_v4_units(
    *,
    evoemo_path: str | Path,
    dialogues_path: str | Path,
    conditions: Sequence[str] = DEFAULT_RESPONSE_V4_CONDITIONS,
    turn_indices: Sequence[int] = DEFAULT_RESPONSE_V4_TURNS,
    ground_truth_mode: str = "full",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    users = {str(x["id"]): x for x in load_evoemo(evoemo_path)}
    by_key = _load_dialogues(dialogues_path)
    missing_dialogues: list[tuple[Any, ...]] = []
    units: list[dict[str, Any]] = []
    for pm_key in sorted(key for key in by_key if key[2] == "pm"):
        user_id, topic_index, _, seed, simulator_id, interaction_mode = pm_key
        pm_dialogue = by_key[pm_key]
        user = users[user_id]
        topic = _topic_by_index(user, topic_index)
        gt = _ground_truth(user, topic, mode=ground_truth_mode)
        for turn_index in sorted(int(x) for x in turn_indices):
            turns_by_condition: dict[str, dict[str, Any]] = {}
            ref_turn = _turn_by_index(pm_dialogue, turn_index)
            for condition in conditions:
                key = (user_id, topic_index, condition, seed, simulator_id, interaction_mode)
                dialogue = by_key.get(key)
                if dialogue is None:
                    missing_dialogues.append(key)
                    continue
                turn = _turn_by_index(dialogue, turn_index)
                if (
                    turn.get("context_sha256") != ref_turn.get("context_sha256")
                    or turn.get("seeker_message") != ref_turn.get("seeker_message")
                    or turn.get("state_id") != ref_turn.get("state_id")
                    or turn.get("track_id") != ref_turn.get("track_id")
                    or (turn.get("context_before_turn") or []) != (ref_turn.get("context_before_turn") or [])
                ):
                    raise RuntimeError(
                        "fixed-context inputs differ across conditions for "
                        f"user={user_id} topic={topic_index} seed={seed} turn={turn_index} "
                        f"condition={condition}"
                    )
                turns_by_condition[condition] = turn
            if len(turns_by_condition) != len(conditions):
                continue
            unit_id = "unit_" + stable_hex(
                user_id, topic_index, seed, simulator_id, interaction_mode, turn_index, n=20
            )
            units.append(
                {
                    "unit_id": unit_id,
                    "user_id": user_id,
                    "topic_index": topic_index,
                    "seed": seed,
                    "simulator_id": simulator_id,
                    "interaction_mode": interaction_mode,
                    "track_id": ref_turn.get("track_id"),
                    "state_id": ref_turn.get("state_id"),
                    "context_sha256": ref_turn.get("context_sha256"),
                    "turn_index": turn_index,
                    "context_before_turn": ref_turn.get("context_before_turn") or [],
                    "seeker_message": ref_turn["seeker_message"],
                    "conditions": list(conditions),
                    "candidate_turns": turns_by_condition,
                    "authorized_ground_truth": gt,
                }
            )
    if missing_dialogues:
        raise RuntimeError(
            "missing required condition dialogues for V4 sample: "
            + str(missing_dialogues[:10])
        )
    metadata = _sample_metadata(units, conditions)
    return units, metadata


def _sample_metadata(units: Sequence[Mapping[str, Any]], conditions: Sequence[str]) -> dict[str, Any]:
    by_turn: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for unit in units:
        by_turn[int(unit["turn_index"])].append(unit)
    action_stats: dict[str, Any] = {}
    for turn_index, turn_units in sorted(by_turn.items()):
        stats: dict[str, Any] = {
            "units": len(turn_units),
            "units_with_any_action_difference": 0,
            "pm_vs_baseline_same_action_rate": {},
        }
        for baseline in conditions:
            if baseline == "pm":
                continue
            same = 0
            comparable = 0
            for unit in turn_units:
                turns = unit["candidate_turns"]
                pm_action = turns["pm"].get("action_id")
                base_action = turns[baseline].get("action_id")
                if pm_action is None or base_action is None:
                    continue
                comparable += 1
                same += int(pm_action == base_action)
            stats["pm_vs_baseline_same_action_rate"][baseline] = (
                same / comparable if comparable else None
            )
        for unit in turn_units:
            actions = {
                unit["candidate_turns"][condition].get("action_id")
                for condition in conditions
            }
            if len(actions) > 1:
                stats["units_with_any_action_difference"] += 1
        if turn_units:
            stats["any_action_difference_rate"] = (
                stats["units_with_any_action_difference"] / len(turn_units)
            )
        action_stats[str(turn_index)] = stats
    return {
        "unit_count": len(units),
        "conditions": list(conditions),
        "turn_indices": sorted(set(int(unit["turn_index"]) for unit in units)),
        "action_sensitivity": action_stats,
    }


def _public_sample_plan(units: Sequence[Mapping[str, Any]], metadata: Mapping[str, Any]) -> dict[str, Any]:
    public_units = [
        {
            "unit_id": unit["unit_id"],
            "user_id": unit["user_id"],
            "topic_index": unit["topic_index"],
            "seed": unit["seed"],
            "simulator_id": unit["simulator_id"],
            "interaction_mode": unit["interaction_mode"],
            "track_id": unit["track_id"],
            "state_id": unit["state_id"],
            "context_sha256": unit["context_sha256"],
            "turn_index": unit["turn_index"],
            "condition_actions": {
                condition: unit["candidate_turns"][condition].get("action_id")
                for condition in unit["conditions"]
            },
        }
        for unit in units
    ]
    return _hash_record(
        {
            "status": "PLANNED",
            "protocol": "evoemo_response_v4",
            "metadata": dict(metadata),
            "units": public_units,
        },
        "sample_plan_sha256",
    )


def _select_pilot_units(units: Sequence[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    if n <= 0:
        raise ValueError("pilot_units must be positive")
    if n >= len(units):
        return list(units)
    selected = []
    used: set[str] = set()
    for i in range(n):
        idx = int(i * len(units) / n)
        unit = units[idx]
        if str(unit["unit_id"]) in used:
            continue
        selected.append(unit)
        used.add(str(unit["unit_id"]))
    return selected


def estimate_response_v4_cost(
    *,
    units: Sequence[Mapping[str, Any]],
    conditions: Sequence[str],
    model: str,
    order_variants: Sequence[int],
    estimated_output_tokens_per_call: int,
    input_usd_per_mtok: float,
    output_usd_per_mtok: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    token_counts = []
    for unit_ordinal, unit in enumerate(units):
        for order_variant in order_variants:
            order = balanced_candidate_order(
                conditions, unit_ordinal=unit_ordinal, order_variant=order_variant
            )
            messages, mapping = _messages_for_unit(
                unit,
                condition_order=order,
                candidate_by_condition=unit["candidate_turns"],
                authorized_ground_truth=unit["authorized_ground_truth"],
            )
            tokens = _count_message_tokens(messages, model)
            token_counts.append(tokens)
            rows.append(
                {
                    "unit_id": unit["unit_id"],
                    "order_variant": order_variant,
                    "input_tokens_est": tokens,
                    "candidate_order": order,
                    "candidate_mapping": mapping,
                    "prompt_hash": sha256_text(canonical_json(messages)),
                }
            )
    if not token_counts:
        raise ValueError("no V4 calls to estimate")
    sorted_counts = sorted(token_counts)
    p95 = sorted_counts[min(len(sorted_counts) - 1, int(0.95 * (len(sorted_counts) - 1)))]
    total_input = sum(token_counts)
    total_output = len(token_counts) * int(estimated_output_tokens_per_call)
    estimate = {
        "status": "ESTIMATED",
        "protocol": "evoemo_response_v4",
        "api_calls": len(token_counts),
        "candidate_count": len(conditions),
        "input_tokens": {
            "total": total_input,
            "mean": total_input / len(token_counts),
            "min": min(token_counts),
            "p95": p95,
            "max": max(token_counts),
        },
        "estimated_output_tokens": {
            "per_call": int(estimated_output_tokens_per_call),
            "total": total_output,
        },
        "estimated_cost_usd": (
            total_input / 1_000_000 * float(input_usd_per_mtok)
            + total_output / 1_000_000 * float(output_usd_per_mtok)
        ),
        "pricing": {
            "input_usd_per_mtok": float(input_usd_per_mtok),
            "output_usd_per_mtok": float(output_usd_per_mtok),
        },
        "order_variants": list(order_variants),
        "model": model,
    }
    return _hash_record(estimate, "cost_estimate_sha256"), rows


def _enforce_budget_gates(
    estimate: Mapping[str, Any],
    *,
    max_api_calls: int,
    max_estimated_usd: float,
    max_input_tokens_per_call: int,
) -> dict[str, Any]:
    checks = {
        "api_calls": int(estimate["api_calls"]) <= int(max_api_calls),
        "estimated_cost_usd": float(estimate["estimated_cost_usd"]) <= float(max_estimated_usd),
        "max_input_tokens_per_call": int(estimate["input_tokens"]["max"]) <= int(max_input_tokens_per_call),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAILED",
        "checks": checks,
        "limits": {
            "max_api_calls": int(max_api_calls),
            "max_estimated_usd": float(max_estimated_usd),
            "max_input_tokens_per_call": int(max_input_tokens_per_call),
        },
    }


def _candidate_id_validator(expected_ids: set[str]) -> Callable[[EvoResponseV4Judgment], None]:
    def validate(parsed: EvoResponseV4Judgment) -> None:
        actual = [score.candidate_id for score in parsed.candidates]
        if len(actual) != len(set(actual)):
            raise ValueError(f"duplicate candidate IDs: {actual}")
        if set(actual) != expected_ids:
            raise ValueError(f"candidate ID mismatch: expected={sorted(expected_ids)}, actual={sorted(actual)}")

    return validate


def _write_score_rows(
    *,
    score_path: Path,
    judgment_path: Path,
    unit: Mapping[str, Any],
    order_variant: int,
    mapping: Mapping[str, Mapping[str, Any]],
    parsed: EvoResponseV4Judgment,
) -> None:
    judgment_row = {
        "unit_id": unit["unit_id"],
        "order_variant": order_variant,
        "user_id": unit["user_id"],
        "topic_index": unit["topic_index"],
        "seed": unit["seed"],
        "simulator_id": unit["simulator_id"],
        "interaction_mode": unit["interaction_mode"],
        "turn_index": unit["turn_index"],
        "scores": [score.model_dump(mode="json") for score in parsed.candidates],
        "candidate_mapping": dict(mapping),
    }
    append_jsonl(judgment_path, judgment_row)
    for score in parsed.candidates:
        info = mapping[score.candidate_id]
        dumped = score.model_dump(mode="json")
        append_jsonl(
            score_path,
            {
                "unit_id": unit["unit_id"],
                "order_variant": order_variant,
                "user_id": unit["user_id"],
                "topic_index": unit["topic_index"],
                "seed": unit["seed"],
                "simulator_id": unit["simulator_id"],
                "interaction_mode": unit["interaction_mode"],
                "turn_index": unit["turn_index"],
                "condition": info["condition"],
                "candidate_id": score.candidate_id,
                "position": info["position"],
                "action_id": info.get("action_id"),
                **{field: dumped[field] for field in SCORE_FIELDS},
                "reason": dumped["reason"],
            },
        )


def _summarize_scores(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in scores:
        by_condition[str(row["condition"])].append(row)
    condition_summary: dict[str, Any] = {}
    for condition, rows in sorted(by_condition.items()):
        condition_summary[condition] = {
            "n": len(rows),
            **{field: mean(float(row[field]) for row in rows) for field in SCORE_FIELDS},
        }
    unit_condition: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    for row in scores:
        unit_condition[(str(row["unit_id"]), int(row["order_variant"]), str(row["condition"]))] = row
    paired_vs_pm: dict[str, Any] = {}
    conditions = sorted(by_condition)
    for condition in conditions:
        if condition == "pm":
            continue
        deltas: dict[str, list[float]] = {field: [] for field in SCORE_FIELDS}
        for key, pm_row in unit_condition.items():
            unit_id, order_variant, cond = key
            if cond != "pm":
                continue
            other = unit_condition.get((unit_id, order_variant, condition))
            if other is None:
                continue
            for field in SCORE_FIELDS:
                deltas[field].append(float(pm_row[field]) - float(other[field]))
        paired_vs_pm[condition] = {
            "n": len(next(iter(deltas.values()))) if deltas else 0,
            **{
                f"pm_minus_{condition}_{field}": (mean(values) if values else None)
                for field, values in deltas.items()
            },
        }
    return {
        "condition_summary": condition_summary,
        "paired_pm_deltas": paired_vs_pm,
    }


def _summarize_pilot(
    scores: Sequence[Mapping[str, Any]],
    *,
    max_order_mean_abs_diff: float,
    max_position_mean_shift: float,
) -> dict[str, Any]:
    by_unit_condition: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    by_position: dict[int, list[float]] = defaultdict(list)
    for row in scores:
        by_unit_condition[(str(row["unit_id"]), str(row["condition"]))].append(row)
        by_position[int(row["position"])].append(float(row["overall"]))
    abs_diffs = []
    for rows in by_unit_condition.values():
        by_variant = {int(row["order_variant"]): row for row in rows}
        if len(by_variant) < 2:
            continue
        variants = sorted(by_variant)
        first = by_variant[variants[0]]
        for variant in variants[1:]:
            other = by_variant[variant]
            abs_diffs.append(abs(float(first["overall"]) - float(other["overall"])))
    position_means = {
        str(position): mean(values)
        for position, values in sorted(by_position.items())
        if values
    }
    global_mean = mean(
        float(row["overall"]) for row in scores
    ) if scores else 0.0
    max_shift = max(
        (abs(value - global_mean) for value in position_means.values()),
        default=0.0,
    )
    order_mean_abs_diff = mean(abs_diffs) if abs_diffs else None
    checks = {
        "has_two_order_variants": bool(abs_diffs),
        "order_mean_abs_diff": (
            order_mean_abs_diff is not None
            and order_mean_abs_diff <= float(max_order_mean_abs_diff)
        ),
        "position_mean_shift": max_shift <= float(max_position_mean_shift),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAILED",
        "checks": checks,
        "order_stability": {
            "paired_condition_scores": len(abs_diffs),
            "mean_abs_diff_overall": order_mean_abs_diff,
            "max_abs_diff_overall": max(abs_diffs) if abs_diffs else None,
        },
        "position_bias": {
            "global_mean_overall": global_mean,
            "position_means_overall": position_means,
            "max_position_mean_shift": max_shift,
        },
        "thresholds": {
            "max_order_mean_abs_diff": float(max_order_mean_abs_diff),
            "max_position_mean_shift": float(max_position_mean_shift),
        },
    }


def _load_scores(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return list(iter_jsonl(p))


def _prepare_outputs(out_dir: Path, paths: Sequence[Path], *, overwrite: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in paths:
            if path.exists():
                path.unlink()


def _require_cost_acceptance(
    estimate: Mapping[str, Any],
    accepted_sha256: str | None,
) -> None:
    expected = str(estimate["cost_estimate_sha256"])
    if not accepted_sha256:
        raise RuntimeError(
            "API mode is fail-closed: run --dry-run first and pass "
            f"--accept-cost-estimate-sha256 {expected}"
        )
    if accepted_sha256 != expected:
        raise RuntimeError(
            "accepted cost estimate hash does not match current V4 parameters: "
            f"accepted={accepted_sha256}, current={expected}"
        )


def _require_saved_dry_run(
    *,
    sample_plan_path: Path,
    cost_estimate_path: Path,
    current_estimate: Mapping[str, Any],
) -> None:
    if not sample_plan_path.is_file() or not cost_estimate_path.is_file():
        raise RuntimeError(
            "API mode requires a completed matching --dry-run first. Missing "
            f"{sample_plan_path if not sample_plan_path.is_file() else cost_estimate_path}."
        )
    saved = read_json(cost_estimate_path)
    saved_hash = saved.get("cost_estimate_sha256")
    current_hash = current_estimate.get("cost_estimate_sha256")
    if saved_hash != current_hash:
        raise RuntimeError(
            "saved dry-run cost estimate does not match current V4 parameters: "
            f"saved={saved_hash}, current={current_hash}. Re-run --dry-run."
        )


def _require_pilot_passed(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        raise RuntimeError("full V4 response evaluation requires --pilot-summary with status PASS")
    summary = read_json(path)
    if summary.get("status") != "PASS":
        raise RuntimeError(f"pilot summary did not pass: {path}")
    return summary


def run_evoemo_response_v4(
    *,
    evoemo_path: str | Path,
    dialogues_path: str | Path,
    out_dir: str | Path,
    judge_endpoint: Endpoint,
    mode: str,
    generation_attestation_path: str | Path | None = None,
    expected_generation_freeze_sha256: str | None = None,
    dry_run_target: str = "full",
    evaluation_freeze_sha256: str | None = None,
    conditions: Sequence[str] = DEFAULT_RESPONSE_V4_CONDITIONS,
    turn_indices: Sequence[int] = DEFAULT_RESPONSE_V4_TURNS,
    ground_truth_mode: str = "full",
    pilot_units: int = 12,
    accept_cost_estimate_sha256: str | None = None,
    pilot_summary_path: str | Path | None = None,
    max_api_calls: int = 250,
    max_estimated_usd: float = 6.0,
    max_input_tokens_per_call: int = 12_000,
    estimated_output_tokens_per_call: int = 1_000,
    input_usd_per_mtok: float = 2.50,
    output_usd_per_mtok: float = 10.0,
    max_tokens: int = 1_400,
    max_order_mean_abs_diff: float = 0.75,
    max_position_mean_shift: float = 0.50,
    overwrite: bool = False,
) -> dict[str, Any]:
    if mode not in {"dry_run", "pilot", "full"}:
        raise ValueError("mode must be one of: dry_run, pilot, full")
    if dry_run_target not in {"pilot", "full"}:
        raise ValueError("dry_run_target must be one of: pilot, full")
    if not conditions or "pm" not in conditions:
        raise ValueError("conditions must include pm")
    generation_verification = None
    if generation_attestation_path is not None:
        generation_verification = require_artifact_attestation(
            generation_attestation_path,
            required_stage="evoemo_generation",
            expected_freeze_sha256=expected_generation_freeze_sha256,
        )
    units, metadata = build_response_v4_units(
        evoemo_path=evoemo_path,
        dialogues_path=dialogues_path,
        conditions=conditions,
        turn_indices=turn_indices,
        ground_truth_mode=ground_truth_mode,
    )
    out_dir = Path(out_dir)
    sample_plan_path = out_dir / "sample_plan.json"
    pilot_summary_json = out_dir / "pilot_summary.json"
    full_summary_json = out_dir / "response_summary.json"
    attestation_path = out_dir / "artifact_attestation.json"

    effective_mode = dry_run_target if mode == "dry_run" else mode
    cost_estimate_path = out_dir / f"cost_estimate_{effective_mode}.json"
    cost_rows_path = out_dir / f"cost_estimate_{effective_mode}_calls.jsonl"
    if effective_mode == "pilot":
        api_units = _select_pilot_units(units, pilot_units)
        order_variants = (0, 1)
        call_limit = min(max_api_calls, max(1, pilot_units * 2))
    elif effective_mode == "full":
        if mode == "full":
            _require_pilot_passed(pilot_summary_path)
        api_units = units
        order_variants = (0,)
        call_limit = max_api_calls
    else:
        raise AssertionError("unreachable V4 mode")

    estimate, cost_rows = estimate_response_v4_cost(
        units=api_units,
        conditions=conditions,
        model=judge_endpoint.model,
        order_variants=order_variants,
        estimated_output_tokens_per_call=estimated_output_tokens_per_call,
        input_usd_per_mtok=input_usd_per_mtok,
        output_usd_per_mtok=output_usd_per_mtok,
    )
    budget_gate = _enforce_budget_gates(
        estimate,
        max_api_calls=call_limit,
        max_estimated_usd=max_estimated_usd,
        max_input_tokens_per_call=max_input_tokens_per_call,
    )
    estimate = {
        **estimate,
        "mode": mode,
        "dry_run_target": dry_run_target if mode == "dry_run" else None,
        "effective_api_mode": effective_mode,
        "ground_truth_mode": ground_truth_mode,
        "sample_metadata": metadata,
        "budget_gate": budget_gate,
    }
    estimate = _hash_record(
        {k: v for k, v in estimate.items() if k != "cost_estimate_sha256"},
        "cost_estimate_sha256",
    )
    if budget_gate["status"] != "PASS":
        if mode == "dry_run":
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(sample_plan_path, _public_sample_plan(units, metadata))
            write_json(cost_estimate_path, estimate)
            from .io import write_jsonl

            write_jsonl(cost_rows_path, cost_rows)
        raise RuntimeError(
            "V4 budget gate failed: "
            + json.dumps(budget_gate, ensure_ascii=False, sort_keys=True)
        )
    if mode == "dry_run":
        out_dir.mkdir(parents=True, exist_ok=True)
        from .io import write_jsonl

        sample_plan = _public_sample_plan(units, metadata)
        write_json(sample_plan_path, sample_plan)
        write_json(cost_estimate_path, estimate)
        write_jsonl(cost_rows_path, cost_rows)
        return {
            "status": "DRY_RUN_COMPLETE",
            "sample_plan": str(sample_plan_path),
            "cost_estimate": str(cost_estimate_path),
            "cost_estimate_sha256": estimate["cost_estimate_sha256"],
            "estimated_cost_usd": estimate["estimated_cost_usd"],
            "api_calls": estimate["api_calls"],
            "input_tokens": estimate["input_tokens"],
            "budget_gate": budget_gate,
        }

    _require_cost_acceptance(estimate, accept_cost_estimate_sha256)
    _require_saved_dry_run(
        sample_plan_path=sample_plan_path,
        cost_estimate_path=cost_estimate_path,
        current_estimate=estimate,
    )

    if mode == "pilot":
        score_path = out_dir / "pilot_scores.jsonl"
        judgment_path = out_dir / "pilot_judgments.jsonl"
        raw_path = out_dir / "pilot_raw_calls.jsonl"
        summary_path = pilot_summary_json
        stage = "evoemo_response_v4_pilot"
        expected_calls = len(api_units) * len(order_variants)
    else:
        score_path = out_dir / "response_scores.jsonl"
        judgment_path = out_dir / "response_judgments.jsonl"
        raw_path = out_dir / "response_raw_calls.jsonl"
        summary_path = full_summary_json
        stage = "evoemo_response_v4_full"
        expected_calls = len(api_units)

    _prepare_outputs(
        out_dir,
        [score_path, judgment_path, raw_path, summary_path, attestation_path],
        overwrite=overwrite,
    )
    done_calls = load_done_keys(judgment_path, ("unit_id", "order_variant"))
    client = make_client(judge_endpoint)
    try:
        for unit_ordinal, unit in enumerate(api_units):
            for order_variant in order_variants:
                done_key = (unit["unit_id"], order_variant)
                if done_key in done_calls:
                    continue
                order = balanced_candidate_order(
                    conditions,
                    unit_ordinal=unit_ordinal,
                    order_variant=order_variant,
                )
                messages, mapping = _messages_for_unit(
                    unit,
                    condition_order=order,
                    candidate_by_condition=unit["candidate_turns"],
                    authorized_ground_truth=unit["authorized_ground_truth"],
                )
                parsed = _call_with_semantic_retry(
                    client,
                    judge_endpoint,
                    messages,
                    EvoResponseV4Judgment,
                    _candidate_id_validator(set(mapping)),
                    stage=stage,
                    record_ids={
                        "unit_id": unit["unit_id"],
                        "order_variant": order_variant,
                        "user_id": unit["user_id"],
                        "topic_index": unit["topic_index"],
                        "seed": unit["seed"],
                        "turn_index": unit["turn_index"],
                    },
                    raw_log_path=raw_path,
                    max_tokens=max_tokens,
                )
                assert isinstance(parsed, EvoResponseV4Judgment)
                _write_score_rows(
                    score_path=score_path,
                    judgment_path=judgment_path,
                    unit=unit,
                    order_variant=order_variant,
                    mapping=mapping,
                    parsed=parsed,
                )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    scores = _load_scores(score_path)
    summary = {
        "status": "COMPLETE",
        "protocol": "evoemo_response_v4",
        "mode": mode,
        "judge_model": judge_endpoint.model,
        "judge_family": judge_endpoint.family,
        "ground_truth_mode": ground_truth_mode,
        "conditions": list(conditions),
        "turn_indices": list(turn_indices),
        "expected_calls": expected_calls,
        "completed_calls": len(list(iter_jsonl(judgment_path))),
        "score_rows": len(scores),
        "cost_estimate_sha256": estimate["cost_estimate_sha256"],
        "cost_estimate": estimate,
        "sample_metadata": metadata,
        "generation_attestation_verification": generation_verification,
        **_summarize_scores(scores),
    }
    if mode == "pilot":
        pilot_summary = _summarize_pilot(
            scores,
            max_order_mean_abs_diff=max_order_mean_abs_diff,
            max_position_mean_shift=max_position_mean_shift,
        )
        summary.update(pilot_summary)
    else:
        pilot_summary = read_json(pilot_summary_path) if pilot_summary_path else None
        summary["pilot_summary_sha256"] = (
            sha256_text(canonical_json(pilot_summary)) if pilot_summary else None
        )
    write_json(summary_path, summary)
    inputs = {
        "evoemo": evoemo_path,
        "dialogues": dialogues_path,
        "sample_plan": sample_plan_path,
        "cost_estimate": cost_estimate_path,
        **({"generation_attestation": generation_attestation_path} if generation_attestation_path else {}),
    }
    if mode == "full" and pilot_summary_path is not None:
        inputs["pilot_summary"] = pilot_summary_path
    create_artifact_attestation(
        attestation_path if mode == "full" else out_dir / "pilot_artifact_attestation.json",
        stage=stage,
        inputs=inputs,
        outputs={
            "scores": (score_path, True),
            "judgments": (judgment_path, True),
            "raw_calls": (raw_path, True),
            "summary": (summary_path, False),
        },
        parameters={
            "judge_model": judge_endpoint.model,
            "judge_family": judge_endpoint.family,
            "conditions": list(conditions),
            "turn_indices": list(turn_indices),
            "ground_truth_mode": ground_truth_mode,
            "mode": mode,
            "max_tokens": max_tokens,
        },
        expected={
            "calls": expected_calls,
            "score_rows": expected_calls * len(conditions),
        },
        study_freeze_sha256=expected_generation_freeze_sha256,
    )
    return summary
