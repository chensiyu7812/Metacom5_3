from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Literal, Mapping, Sequence
import json

from pydantic import Field

from .api import Endpoint, make_client
from .artifacts import create_artifact_attestation, require_artifact_attestation
from .contracts import StrictModel
from .evo_response_v4 import _count_message_tokens
from .evoemo import evaluator_context, load_evoemo
from .io import (
    append_jsonl,
    canonical_json,
    iter_jsonl,
    load_done_keys,
    read_json,
    sha256_text,
    stable_hex,
    utc_now,
    write_json,
    write_jsonl,
)
from .judging import _call_with_semantic_retry


AUDIT_SCORE_FIELDS = (
    "selected_evidence_misuse",
    "unnecessary_exposure",
    "stale_or_conflict",
    "unsupported_personal_claim",
    "source_set_appropriateness",
    "strategy_overuse",
    "strategy_omission",
    "omission_severity",
    "response_support_sufficiency",
    "overall_risk",
)


class EvoSampledAuditJudgment(StrictModel):
    audit_call_id: str = Field(min_length=1)
    verdict: Literal["acceptable", "minor_issue", "major_issue", "uncertain"]
    selected_evidence_misuse: int = Field(ge=0, le=3)
    unnecessary_exposure: int = Field(ge=0, le=3)
    stale_or_conflict: int = Field(ge=0, le=3)
    unsupported_personal_claim: int = Field(ge=0, le=3)
    source_set_appropriateness: int = Field(ge=1, le=5)
    strategy_overuse: int = Field(ge=0, le=3)
    strategy_omission: int = Field(ge=0, le=3)
    omission_severity: int = Field(ge=0, le=3)
    response_support_sufficiency: int = Field(ge=1, le=5)
    overall_risk: int = Field(ge=0, le=3)
    reason: str = Field(min_length=1, max_length=900)


AUDIT_SYSTEM = """You are an evaluator-only audit judge for longitudinal emotional-support responses.
Judge the target response against the visible fixed-context turn and the evidence/resources shown in the prompt.
For selected-resource audits, do not punish the system for missing facts that are not shown; focus on misuse, unnecessary exposure, stale/conflicting use, unsupported claims, and strategy overuse/omission.
For authorized-context omission audits, use the authorized profile/history/topic only to decide whether important available context was omitted.
Do not reward using more personal facts. Prefer supportive, grounded, non-intrusive responses. Return only JSON matching the schema."""


AUDIT_RUBRIC = {
    "0_to_3_risk_scale": {
        "0": "not observed",
        "1": "minor or ambiguous issue",
        "2": "clear issue that could affect quality/safety",
        "3": "severe issue or repeated issue",
    },
    "1_to_5_quality_scale": {
        "1": "poor",
        "2": "weak",
        "3": "adequate",
        "4": "good",
        "5": "excellent",
    },
    "fields": {
        "selected_evidence_misuse": "selected memory/strategy is used inaccurately, too literally, or out of context",
        "unnecessary_exposure": "response exposes or relies on personal details that are not needed for this turn",
        "stale_or_conflict": "response uses outdated or conflicting memory as if current",
        "unsupported_personal_claim": "response asserts personal facts not supported by the shown context/evidence",
        "source_set_appropriateness": "whether the selected source set is suitable and not excessive",
        "strategy_overuse": "Strategy RAG causes over-structured, premature, generic, or unnatural advice",
        "strategy_omission": "response lacks an obviously useful support strategy for the visible turn",
        "omission_severity": "only for authorized-context omission audits; severity of missing useful context",
        "response_support_sufficiency": "whether the response remains emotionally supportive and useful",
        "overall_risk": "holistic memory/strategy risk for this audit call",
    },
}


def _hash_record(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    out = dict(value)
    out[field] = sha256_text(canonical_json(out))
    return out


def _turn_key(row: Mapping[str, Any]) -> tuple[str, int, str, int, str, str, int]:
    return (
        str(row["user_id"]),
        int(row["topic_index"]),
        str(row["condition"]),
        int(row["seed"]),
        str(row.get("simulator_id") or "unspecified"),
        str(row.get("interaction_mode") or "legacy_interactive"),
        int(row["turn_index"]),
    )


def _item_unit_key(item: Mapping[str, Any], condition: str) -> tuple[str, int, str, int, str, str, int]:
    key = item["unit_key"]
    return (
        str(key["user_id"]),
        int(key["topic_index"]),
        condition,
        int(key["seed"]),
        str(key.get("simulator_id") or "unspecified"),
        str(key.get("interaction_mode") or "legacy_interactive"),
        int(key["turn_index"]),
    )


def _topic_by_index(user: Mapping[str, Any], topic_index: int) -> dict[str, Any]:
    for topic in user.get("subsequent_topics") or []:
        if int(topic["idx"]) == topic_index:
            return dict(topic)
    raise KeyError(f"missing topic idx={topic_index} for user={user.get('id')}")


def _compact_authorized_context(user: Mapping[str, Any], topic: Mapping[str, Any]) -> dict[str, Any]:
    full = evaluator_context(dict(user), dict(topic))
    related = []
    for session in full.get("detailed_related_sessions") or []:
        related.append(
            {
                "session_id": session.get("session_id"),
                "timestamp": session.get("timestamp"),
                "summary": session.get("summary"),
                "observations": session.get("observations") or [],
            }
        )
    return {
        "user_profile": full.get("user_profile") or {},
        "current_topic": full.get("current_topic") or {},
        "related_session_summaries": related,
        "evaluator_only": True,
        "ground_truth_mode": "compact_related",
    }


def _load_turns(path: str | Path) -> dict[tuple[str, int, str, int, str, str, int], dict[str, Any]]:
    rows: dict[tuple[str, int, str, int, str, str, int], dict[str, Any]] = {}
    for row in iter_jsonl(path):
        key = _turn_key(row)
        if key in rows:
            raise RuntimeError(f"duplicate turn key: {key}")
        rows[key] = row
    return rows


def _clip_text(value: Any, max_chars: int) -> dict[str, Any]:
    text = "" if value is None else str(value)
    if max_chars <= 0 or len(text) <= max_chars:
        return {
            "text": text,
            "original_chars": len(text),
            "truncated": False,
        }
    head = max_chars // 2
    tail = max_chars - head
    clipped = text[:head] + "\n...[TRUNCATED]...\n" + text[-tail:]
    return {
        "text": clipped,
        "original_chars": len(text),
        "truncated": True,
    }


def _compact_memory(item: Mapping[str, Any], *, max_chars: int) -> dict[str, Any]:
    return {
        "memory_id": item.get("memory_id"),
        "source": item.get("source"),
        "timestamp": item.get("timestamp"),
        "created_session": item.get("created_session"),
        **_clip_text(item.get("text"), max_chars),
    }


def _compact_strategy(item: Mapping[str, Any], *, max_chars: int) -> dict[str, Any]:
    fields = {
        "strategy_id": item.get("strategy_id"),
        "strategy_label": item.get("strategy_label"),
        "source_dialogue_id": item.get("source_dialogue_id"),
        "source_turn_index": item.get("source_turn_index"),
    }
    for key in ("guidance_text", "example_response", "retrieval_text"):
        fields[key] = _clip_text(item.get(key), max_chars)
    return fields


def _condition_payload(
    turn: Mapping[str, Any],
    *,
    max_memory_chars: int,
    max_strategy_chars: int,
) -> dict[str, Any]:
    cost = turn.get("cost") or {}
    return {
        "condition": turn.get("condition"),
        "action_id": turn.get("action_id"),
        "response": turn.get("supporter_message"),
        "input_tokens": turn.get("input_tokens"),
        "output_tokens": turn.get("output_tokens"),
        "cost": {
            "total_input_tokens": cost.get("total_input_tokens"),
            "memory_tokens": cost.get("memory_tokens"),
            "strategy_tokens": cost.get("strategy_tokens"),
            "retrieval_calls": cost.get("retrieval_calls"),
        },
        "selected_memory": [
            _compact_memory(x, max_chars=max_memory_chars)
            for x in (turn.get("selected_memory") or [])
        ],
        "selected_strategy": [
            _compact_strategy(x, max_chars=max_strategy_chars)
            for x in (turn.get("selected_strategy") or [])
        ],
    }


def _comparison_payload(turn: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "condition": turn.get("condition"),
        "action_id": turn.get("action_id"),
        "response": turn.get("supporter_message"),
    }


def _call_id(audit_item_id: str, audit_type: str, condition: str) -> str:
    suffix = stable_hex(audit_item_id, audit_type, condition, n=10)
    return f"{audit_item_id}::{audit_type}::{condition}::{suffix}"


def _selected_messages(
    *,
    call_id: str,
    item: Mapping[str, Any],
    target_turn: Mapping[str, Any],
    comparison_turns: Sequence[Mapping[str, Any]],
    max_memory_chars: int,
    max_strategy_chars: int,
) -> list[dict[str, str]]:
    modules = list(item.get("audit_modules") or [])
    payload = {
        "task": "selected_resource_memory_strategy_audit",
        "audit_call_id": call_id,
        "audit_modules": modules,
        "rubric": AUDIT_RUBRIC,
        "case": {
            "audit_item_id": item["audit_item_id"],
            "unit_id": item["unit_id"],
            "unit_key": item["unit_key"],
            "covered_strata": item.get("covered_strata") or [item.get("stratum")],
            "planner_reason": item.get("reason"),
            "context_before_turn": target_turn.get("context_before_turn") or [],
            "current_seeker_message": target_turn.get("seeker_message"),
        },
        "target": _condition_payload(
            target_turn,
            max_memory_chars=max_memory_chars,
            max_strategy_chars=max_strategy_chars,
        ),
        "comparison_responses": [_comparison_payload(x) for x in comparison_turns],
        "instructions": [
            "Audit the target condition only.",
            "Use comparison responses only to understand why this sample was selected.",
            "For selected-resource audits, do not assume omitted history that is not shown.",
            "Set omission_severity to 0 unless the prompt includes authorized context.",
        ],
        "output_json_shape": {
            "audit_call_id": call_id,
            "verdict": "acceptable",
            "selected_evidence_misuse": 0,
            "unnecessary_exposure": 0,
            "stale_or_conflict": 0,
            "unsupported_personal_claim": 0,
            "source_set_appropriateness": 3,
            "strategy_overuse": 0,
            "strategy_omission": 0,
            "omission_severity": 0,
            "response_support_sufficiency": 3,
            "overall_risk": 0,
            "reason": "brief evidence-based audit reason",
        },
    }
    return [
        {"role": "system", "content": AUDIT_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]


def _omission_messages(
    *,
    call_id: str,
    item: Mapping[str, Any],
    target_turn: Mapping[str, Any],
    comparison_turns: Sequence[Mapping[str, Any]],
    authorized_context: Mapping[str, Any],
    max_memory_chars: int,
    max_strategy_chars: int,
) -> list[dict[str, str]]:
    payload = {
        "task": "authorized_context_omission_audit",
        "audit_call_id": call_id,
        "audit_modules": list(item.get("audit_modules") or []),
        "rubric": AUDIT_RUBRIC,
        "authorized_ground_truth": authorized_context,
        "case": {
            "audit_item_id": item["audit_item_id"],
            "unit_id": item["unit_id"],
            "unit_key": item["unit_key"],
            "covered_strata": item.get("covered_strata") or [item.get("stratum")],
            "planner_reason": item.get("reason"),
            "context_before_turn": target_turn.get("context_before_turn") or [],
            "current_seeker_message": target_turn.get("seeker_message"),
        },
        "target": _condition_payload(
            target_turn,
            max_memory_chars=max_memory_chars,
            max_strategy_chars=max_strategy_chars,
        ),
        "comparison_responses": [_comparison_payload(x) for x in comparison_turns],
        "instructions": [
            "Audit whether the target response omitted important available context.",
            "Do not require memory use when a warm generic response is sufficient.",
            "Penalize omission only when the missing context is both authorized and useful for the current turn.",
            "Also score selected evidence misuse and unnecessary exposure if present.",
        ],
        "output_json_shape": {
            "audit_call_id": call_id,
            "verdict": "acceptable",
            "selected_evidence_misuse": 0,
            "unnecessary_exposure": 0,
            "stale_or_conflict": 0,
            "unsupported_personal_claim": 0,
            "source_set_appropriateness": 3,
            "strategy_overuse": 0,
            "strategy_omission": 0,
            "omission_severity": 0,
            "response_support_sufficiency": 3,
            "overall_risk": 0,
            "reason": "brief evidence-based audit reason",
        },
    }
    return [
        {"role": "system", "content": AUDIT_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]


def build_audit_calls(
    *,
    sample_plan_path: str | Path,
    turns_path: str | Path,
    evoemo_path: str | Path,
    mode: Literal["pilot", "full"],
    pilot_items: int,
    max_omission_calls: int,
    max_memory_chars: int,
    max_strategy_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plan = read_json(sample_plan_path)
    if plan.get("status") != "PLANNED_NO_API":
        raise RuntimeError(f"sample plan is not PLANNED_NO_API: {sample_plan_path}")
    all_items = list(plan.get("audit_items") or [])
    if not all_items:
        raise RuntimeError("sample plan contains no audit_items")
    items = all_items if mode == "full" else all_items[: int(pilot_items)]
    turns = _load_turns(turns_path)
    users = {str(user["id"]): user for user in load_evoemo(evoemo_path)}
    omission_used = 0
    calls: list[dict[str, Any]] = []
    for item in items:
        focus_conditions = [str(x) for x in item.get("focus_conditions") or []]
        focus_turns = {
            condition: turns[_item_unit_key(item, condition)]
            for condition in focus_conditions
            if _item_unit_key(item, condition) in turns
        }
        missing = sorted(set(focus_conditions) - set(focus_turns))
        if missing:
            raise RuntimeError(f"missing focus turns for {item['audit_item_id']}: {missing}")
        for condition in focus_conditions:
            if condition == "no_memory_r0":
                continue
            target = focus_turns[condition]
            comparisons = [
                focus_turns[other]
                for other in focus_conditions
                if other != condition
            ]
            call_id = _call_id(str(item["audit_item_id"]), "selected", condition)
            messages = _selected_messages(
                call_id=call_id,
                item=item,
                target_turn=target,
                comparison_turns=comparisons,
                max_memory_chars=max_memory_chars,
                max_strategy_chars=max_strategy_chars,
            )
            calls.append(
                {
                    "audit_call_id": call_id,
                    "audit_item_id": item["audit_item_id"],
                    "audit_type": "selected",
                    "condition": condition,
                    "unit_id": item["unit_id"],
                    "unit_key": item["unit_key"],
                    "focus_conditions": focus_conditions,
                    "audit_modules": list(item.get("audit_modules") or []),
                    "pm_action_id": item.get("pm_action_id"),
                    "baseline": item.get("baseline"),
                    "messages": messages,
                }
            )
        if (
            "omission_with_authorized_context" in (item.get("audit_modules") or [])
            and omission_used < max_omission_calls
        ):
            target = focus_turns.get("pm") or turns[_item_unit_key(item, "pm")]
            comparison_conditions = [x for x in focus_conditions if x != "pm" and x in focus_turns]
            comparisons = [focus_turns[x] for x in comparison_conditions]
            user = users[str(item["unit_key"]["user_id"])]
            topic = _topic_by_index(user, int(item["unit_key"]["topic_index"]))
            authorized = _compact_authorized_context(user, topic)
            call_id = _call_id(str(item["audit_item_id"]), "omission", "pm")
            messages = _omission_messages(
                call_id=call_id,
                item=item,
                target_turn=target,
                comparison_turns=comparisons,
                authorized_context=authorized,
                max_memory_chars=max_memory_chars,
                max_strategy_chars=max_strategy_chars,
            )
            calls.append(
                {
                    "audit_call_id": call_id,
                    "audit_item_id": item["audit_item_id"],
                    "audit_type": "omission",
                    "condition": "pm",
                    "unit_id": item["unit_id"],
                    "unit_key": item["unit_key"],
                    "focus_conditions": focus_conditions,
                    "audit_modules": list(item.get("audit_modules") or []),
                    "pm_action_id": item.get("pm_action_id"),
                    "baseline": item.get("baseline"),
                    "messages": messages,
                }
            )
            omission_used += 1
    metadata = {
        "source_sample_plan_status": plan.get("status"),
        "source_sample_plan_sha256": sha256_text(canonical_json(plan)),
        "mode": mode,
        "pilot_items": int(pilot_items),
        "selected_items_in_mode": len(items),
        "total_items_in_plan": len(all_items),
        "calls": len(calls),
        "call_type_counts": dict(Counter(str(call["audit_type"]) for call in calls)),
        "condition_counts": dict(Counter(str(call["condition"]) for call in calls)),
        "max_memory_chars": int(max_memory_chars),
        "max_strategy_chars": int(max_strategy_chars),
        "max_omission_calls": int(max_omission_calls),
    }
    return calls, metadata


def estimate_audit_cost(
    *,
    calls: Sequence[Mapping[str, Any]],
    model: str,
    estimated_output_tokens_per_call: int,
    input_usd_per_mtok: float,
    output_usd_per_mtok: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    token_counts = []
    for call in calls:
        messages = call["messages"]
        tokens = _count_message_tokens(messages, model)
        token_counts.append(tokens)
        rows.append(
            {
                "audit_call_id": call["audit_call_id"],
                "audit_item_id": call["audit_item_id"],
                "audit_type": call["audit_type"],
                "condition": call["condition"],
                "input_tokens_est": tokens,
                "prompt_hash": sha256_text(canonical_json(messages)),
            }
        )
    if not token_counts:
        raise RuntimeError("no audit calls to estimate")
    sorted_counts = sorted(token_counts)
    p95 = sorted_counts[min(len(sorted_counts) - 1, int(0.95 * (len(sorted_counts) - 1)))]
    total_input = sum(token_counts)
    total_output = len(token_counts) * int(estimated_output_tokens_per_call)
    estimate = {
        "status": "ESTIMATED",
        "protocol": "evoemo_sampled_memory_strategy_audit_v1",
        "api_calls": len(token_counts),
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
        "model": model,
    }
    return _hash_record(estimate, "cost_estimate_sha256"), rows


def _budget_gate(
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


def _finalize_estimate(
    estimate: Mapping[str, Any],
    *,
    mode: str,
    call_metadata: Mapping[str, Any],
    budget_gate: Mapping[str, Any],
    response_attestation_sha256: str | None,
    evaluation_freeze_sha256: str | None,
) -> dict[str, Any]:
    hashed = _hash_record(
        {
            **dict(estimate),
            "mode": mode,
            "call_metadata": dict(call_metadata),
            "budget_gate": dict(budget_gate),
            "response_attestation_sha256": response_attestation_sha256,
            "evaluation_freeze_sha256": evaluation_freeze_sha256,
        },
        "cost_estimate_sha256",
    )
    return hashed


def _require_cost_acceptance(estimate: Mapping[str, Any], accepted_sha256: str | None) -> None:
    expected = str(estimate["cost_estimate_sha256"])
    if not accepted_sha256:
        raise RuntimeError(
            "API mode is fail-closed: run --dry-run first and pass "
            f"--accept-cost-estimate-sha256 {expected}"
        )
    if accepted_sha256 != expected:
        raise RuntimeError(
            "accepted sampled-audit cost estimate hash does not match current parameters: "
            f"accepted={accepted_sha256}, current={expected}"
        )


def _require_saved_dry_run(path: Path, current_estimate: Mapping[str, Any]) -> None:
    if not path.is_file():
        raise RuntimeError(f"API mode requires a matching dry-run first: missing {path}")
    saved = read_json(path)
    if saved.get("cost_estimate_sha256") != current_estimate.get("cost_estimate_sha256"):
        raise RuntimeError(
            "saved dry-run estimate does not match current sampled-audit parameters: "
            f"saved={saved.get('cost_estimate_sha256')}, current={current_estimate.get('cost_estimate_sha256')}"
        )


def _validator(expected_call_id: str):
    def validate(parsed: EvoSampledAuditJudgment) -> None:
        if parsed.audit_call_id != expected_call_id:
            raise ValueError(
                f"audit_call_id mismatch: expected={expected_call_id}, actual={parsed.audit_call_id}"
            )

    return validate


def _prepare_outputs(out_dir: Path, paths: Sequence[Path], *, overwrite: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in paths:
            if path.exists():
                path.unlink()


def _write_audit_rows(
    *,
    score_path: Path,
    judgment_path: Path,
    call: Mapping[str, Any],
    parsed: EvoSampledAuditJudgment,
) -> None:
    dumped = parsed.model_dump(mode="json")
    base = {
        "audit_call_id": call["audit_call_id"],
        "audit_item_id": call["audit_item_id"],
        "audit_type": call["audit_type"],
        "condition": call["condition"],
        "unit_id": call["unit_id"],
        "unit_key": call["unit_key"],
        "focus_conditions": call["focus_conditions"],
        "audit_modules": call["audit_modules"],
        "pm_action_id": call.get("pm_action_id"),
        "baseline": call.get("baseline"),
    }
    append_jsonl(judgment_path, {**base, "judgment": dumped})
    append_jsonl(
        score_path,
        {
            **base,
            "verdict": dumped["verdict"],
            **{field: dumped[field] for field in AUDIT_SCORE_FIELDS},
            "reason": dumped["reason"],
        },
    )


def _load_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    return list(iter_jsonl(p))


def _validate_outputs(
    *,
    score_path: str | Path,
    judgment_path: str | Path,
    raw_path: str | Path,
    expected_calls: Sequence[Mapping[str, Any]],
    max_raw_rows_multiplier: float,
) -> dict[str, Any]:
    expected_ids = {str(call["audit_call_id"]) for call in expected_calls}
    errors: list[str] = []
    judgment_ids: set[str] = set()
    score_ids: set[str] = set()
    raw_success_ids: set[str] = set()
    dup_judgment = []
    dup_score = []
    dup_raw = []

    for row in iter_jsonl(judgment_path):
        call_id = str(row.get("audit_call_id"))
        if call_id in judgment_ids:
            dup_judgment.append(call_id)
        judgment_ids.add(call_id)
        judgment = row.get("judgment")
        if not isinstance(judgment, dict):
            errors.append(f"judgment row missing judgment object: {call_id}")
        elif judgment.get("audit_call_id") != call_id:
            errors.append(f"judgment call id mismatch: {call_id}")

    for row in iter_jsonl(score_path):
        call_id = str(row.get("audit_call_id"))
        if call_id in score_ids:
            dup_score.append(call_id)
        score_ids.add(call_id)
        for field in AUDIT_SCORE_FIELDS:
            value = row.get(field)
            if not isinstance(value, int):
                errors.append(f"score {call_id} has non-int {field}: {value!r}")

    raw_rows = 0
    for row in iter_jsonl(raw_path):
        raw_rows += 1
        if row.get("error") is not None or row.get("validated") is None:
            continue
        call_id = str(row.get("audit_call_id"))
        if call_id in raw_success_ids:
            dup_raw.append(call_id)
        raw_success_ids.add(call_id)

    if dup_judgment:
        errors.append(f"duplicate judgment rows: {dup_judgment[:5]}")
    if dup_score:
        errors.append(f"duplicate score rows: {dup_score[:5]}")
    if dup_raw:
        errors.append(f"duplicate successful raw calls: {dup_raw[:5]}")
    for label, actual in (
        ("judgment", judgment_ids),
        ("score", score_ids),
        ("successful raw", raw_success_ids),
    ):
        missing = expected_ids - actual
        extra = actual - expected_ids
        if missing:
            errors.append(f"missing {label} ids: {sorted(missing)[:5]}")
        if extra:
            errors.append(f"extra {label} ids: {sorted(extra)[:5]}")
    raw_limit = int(len(expected_ids) * float(max_raw_rows_multiplier))
    if raw_rows > raw_limit:
        errors.append(
            f"raw rows exceed retry gate: raw_rows={raw_rows}, limit={raw_limit}, "
            f"expected_calls={len(expected_ids)}"
        )

    return {
        "ok": not errors,
        "errors": errors,
        "expected_calls": len(expected_ids),
        "judgment_rows": len(judgment_ids),
        "score_rows": len(score_ids),
        "raw_rows": raw_rows,
        "successful_raw_calls": len(raw_success_ids),
        "raw_rows_limit": raw_limit,
        "max_raw_rows_multiplier": float(max_raw_rows_multiplier),
        "duplicate_judgment_rows": len(dup_judgment),
        "duplicate_score_rows": len(dup_score),
        "duplicate_successful_raw_calls": len(dup_raw),
    }


def _summarize_audit_scores(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_type: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    verdicts = Counter()
    for row in scores:
        by_condition[str(row["condition"])].append(row)
        by_type[str(row["audit_type"])].append(row)
        verdicts[str(row["verdict"])] += 1

    def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(rows),
            **{
                field: mean(float(row[field]) for row in rows)
                for field in AUDIT_SCORE_FIELDS
            },
        }

    return {
        "condition_summary": {
            condition: summarize(rows)
            for condition, rows in sorted(by_condition.items())
        },
        "audit_type_summary": {
            audit_type: summarize(rows)
            for audit_type, rows in sorted(by_type.items())
        },
        "verdict_counts": dict(verdicts.most_common()),
    }


def _require_pilot_summary(
    path: str | Path | None,
    *,
    judge_endpoint: Endpoint,
    response_attestation_sha256: str | None,
    evaluation_freeze_sha256: str | None,
    max_raw_rows_multiplier: float,
) -> dict[str, Any]:
    if path is None:
        raise RuntimeError("full sampled audit requires --pilot-summary with status PASS")
    summary = read_json(path)
    errors = []
    expected = {
        "protocol": "evoemo_sampled_memory_strategy_audit_v1",
        "mode": "pilot",
        "status": "PASS",
        "judge_model": judge_endpoint.model,
        "judge_family": judge_endpoint.family,
        "response_attestation_sha256": response_attestation_sha256,
        "evaluation_freeze_sha256": evaluation_freeze_sha256,
    }
    for key, expected_value in expected.items():
        if summary.get(key) != expected_value:
            errors.append(f"{key}: expected={expected_value!r}, actual={summary.get(key)!r}")
    if float(summary.get("max_raw_rows_multiplier", -1)) != float(max_raw_rows_multiplier):
        errors.append(
            "max_raw_rows_multiplier: "
            f"expected={float(max_raw_rows_multiplier)!r}, actual={summary.get('max_raw_rows_multiplier')!r}"
        )
    if errors:
        raise RuntimeError(
            "pilot summary is not compatible with current sampled-audit full run:\n- "
            + "\n- ".join(errors)
        )
    return summary


def run_evoemo_sampled_audit(
    *,
    sample_plan_path: str | Path,
    turns_path: str | Path,
    evoemo_path: str | Path,
    out_dir: str | Path,
    judge_endpoint: Endpoint,
    mode: Literal["dry_run", "pilot", "full"],
    dry_run_target: Literal["pilot", "full"] = "pilot",
    response_attestation_path: str | Path | None = None,
    evaluation_freeze_sha256: str | None = None,
    pilot_items: int = 8,
    max_omission_calls: int = 10,
    max_memory_chars: int = 1000,
    max_strategy_chars: int = 700,
    accept_cost_estimate_sha256: str | None = None,
    pilot_summary_path: str | Path | None = None,
    max_api_calls: int = 90,
    max_estimated_usd: float = 2.0,
    max_input_tokens_per_call: int = 8000,
    estimated_output_tokens_per_call: int = 450,
    input_usd_per_mtok: float = 2.50,
    output_usd_per_mtok: float = 10.0,
    max_tokens: int = 900,
    max_raw_rows_multiplier: float = 1.10,
    overwrite: bool = False,
) -> dict[str, Any]:
    if mode not in {"dry_run", "pilot", "full"}:
        raise ValueError("mode must be dry_run, pilot, or full")
    if dry_run_target not in {"pilot", "full"}:
        raise ValueError("dry_run_target must be pilot or full")
    response_verification = None
    response_attestation_sha256 = None
    if response_attestation_path is not None:
        response_verification = require_artifact_attestation(
            response_attestation_path,
            required_stage="evoemo_response_v4_full",
        )
        response_attestation_sha256 = response_verification.get("attestation_sha256")

    effective_mode: Literal["pilot", "full"] = dry_run_target if mode == "dry_run" else mode
    if effective_mode == "full" and mode == "full":
        pilot_summary = _require_pilot_summary(
            pilot_summary_path,
            judge_endpoint=judge_endpoint,
            response_attestation_sha256=response_attestation_sha256,
            evaluation_freeze_sha256=evaluation_freeze_sha256,
            max_raw_rows_multiplier=max_raw_rows_multiplier,
        )
    else:
        pilot_summary = None

    calls, call_metadata = build_audit_calls(
        sample_plan_path=sample_plan_path,
        turns_path=turns_path,
        evoemo_path=evoemo_path,
        mode=effective_mode,
        pilot_items=pilot_items,
        max_omission_calls=max_omission_calls,
        max_memory_chars=max_memory_chars,
        max_strategy_chars=max_strategy_chars,
    )
    estimate, cost_rows = estimate_audit_cost(
        calls=calls,
        model=judge_endpoint.model,
        estimated_output_tokens_per_call=estimated_output_tokens_per_call,
        input_usd_per_mtok=input_usd_per_mtok,
        output_usd_per_mtok=output_usd_per_mtok,
    )
    gate = _budget_gate(
        estimate,
        max_api_calls=max_api_calls,
        max_estimated_usd=max_estimated_usd,
        max_input_tokens_per_call=max_input_tokens_per_call,
    )
    estimate = _finalize_estimate(
        estimate,
        mode=effective_mode,
        call_metadata=call_metadata,
        budget_gate=gate,
        response_attestation_sha256=response_attestation_sha256,
        evaluation_freeze_sha256=evaluation_freeze_sha256,
    )

    out_dir = Path(out_dir)
    cost_estimate_path = out_dir / f"cost_estimate_{effective_mode}.json"
    cost_rows_path = out_dir / f"cost_estimate_{effective_mode}_calls.jsonl"
    call_plan_path = out_dir / f"audit_call_plan_{effective_mode}.jsonl"
    if gate["status"] != "PASS":
        if mode == "dry_run":
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(cost_estimate_path, estimate)
            write_jsonl(cost_rows_path, cost_rows)
            write_jsonl(
                call_plan_path,
                [
                    {k: v for k, v in call.items() if k != "messages"}
                    | {"prompt_hash": sha256_text(canonical_json(call["messages"]))}
                    for call in calls
                ],
            )
        raise RuntimeError("sampled audit budget gate failed: " + json.dumps(gate, ensure_ascii=False))

    if mode == "dry_run":
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(cost_estimate_path, estimate)
        write_jsonl(cost_rows_path, cost_rows)
        write_jsonl(
            call_plan_path,
            [
                {k: v for k, v in call.items() if k != "messages"}
                | {"prompt_hash": sha256_text(canonical_json(call["messages"]))}
                for call in calls
            ],
        )
        return {
            "status": "DRY_RUN_COMPLETE",
            "mode": effective_mode,
            "cost_estimate": str(cost_estimate_path),
            "cost_estimate_sha256": estimate["cost_estimate_sha256"],
            "api_calls": estimate["api_calls"],
            "estimated_cost_usd": estimate["estimated_cost_usd"],
            "input_tokens": estimate["input_tokens"],
            "budget_gate": gate,
            "call_metadata": call_metadata,
        }

    _require_cost_acceptance(estimate, accept_cost_estimate_sha256)
    _require_saved_dry_run(cost_estimate_path, estimate)

    if mode == "pilot":
        score_path = out_dir / "pilot_scores.jsonl"
        judgment_path = out_dir / "pilot_judgments.jsonl"
        raw_path = out_dir / "pilot_raw_calls.jsonl"
        summary_path = out_dir / "pilot_summary.json"
        attestation_path = out_dir / "pilot_artifact_attestation.json"
        stage = "evoemo_sampled_audit_pilot"
    else:
        score_path = out_dir / "audit_scores.jsonl"
        judgment_path = out_dir / "audit_judgments.jsonl"
        raw_path = out_dir / "audit_raw_calls.jsonl"
        summary_path = out_dir / "audit_summary.json"
        attestation_path = out_dir / "artifact_attestation.json"
        stage = "evoemo_sampled_audit_full"

    _prepare_outputs(
        out_dir,
        [score_path, judgment_path, raw_path, summary_path, attestation_path],
        overwrite=overwrite,
    )
    done = load_done_keys(judgment_path, ("audit_call_id",))
    client = make_client(judge_endpoint)
    try:
        for call in calls:
            done_key = (call["audit_call_id"],)
            if done_key in done:
                continue
            parsed = _call_with_semantic_retry(
                client,
                judge_endpoint,
                list(call["messages"]),
                EvoSampledAuditJudgment,
                _validator(str(call["audit_call_id"])),
                stage=stage,
                record_ids={
                    "audit_call_id": call["audit_call_id"],
                    "audit_item_id": call["audit_item_id"],
                    "audit_type": call["audit_type"],
                    "condition": call["condition"],
                    "unit_id": call["unit_id"],
                },
                raw_log_path=raw_path,
                max_tokens=max_tokens,
            )
            assert isinstance(parsed, EvoSampledAuditJudgment)
            _write_audit_rows(
                score_path=score_path,
                judgment_path=judgment_path,
                call=call,
                parsed=parsed,
            )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    output_validation = _validate_outputs(
        score_path=score_path,
        judgment_path=judgment_path,
        raw_path=raw_path,
        expected_calls=calls,
        max_raw_rows_multiplier=max_raw_rows_multiplier,
    )
    if not output_validation["ok"]:
        raise RuntimeError(
            "sampled audit output validation failed before summary/attestation:\n- "
            + "\n- ".join(output_validation["errors"])
        )
    scores = _load_rows(score_path)
    summary = {
        "status": "PASS" if mode == "pilot" else "COMPLETE",
        "protocol": "evoemo_sampled_memory_strategy_audit_v1",
        "mode": mode,
        "judge_model": judge_endpoint.model,
        "judge_family": judge_endpoint.family,
        "response_attestation_sha256": response_attestation_sha256,
        "evaluation_freeze_sha256": evaluation_freeze_sha256,
        "expected_calls": len(calls),
        "completed_calls": len(_load_rows(judgment_path)),
        "score_rows": len(scores),
        "output_validation": output_validation,
        "max_raw_rows_multiplier": float(max_raw_rows_multiplier),
        "cost_estimate_sha256": estimate["cost_estimate_sha256"],
        "cost_estimate": estimate,
        "call_metadata": call_metadata,
        "response_attestation_verification": response_verification,
        **_summarize_audit_scores(scores),
    }
    if mode == "full":
        summary["pilot_summary_sha256"] = sha256_text(canonical_json(pilot_summary)) if pilot_summary else None
        summary["pilot_compatibility_checked"] = bool(pilot_summary)
    write_json(summary_path, summary)

    inputs: dict[str, str | Path] = {
        "sample_plan": sample_plan_path,
        "turns": turns_path,
        "evoemo": evoemo_path,
        "cost_estimate": cost_estimate_path,
    }
    if response_attestation_path is not None:
        inputs["response_attestation"] = response_attestation_path
    if mode == "full" and pilot_summary_path is not None:
        inputs["pilot_summary"] = pilot_summary_path
    freeze_verification_path = out_dir / "freeze_verification.json"
    if freeze_verification_path.is_file():
        inputs["freeze_verification"] = freeze_verification_path
    create_artifact_attestation(
        attestation_path,
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
            "mode": mode,
            "pilot_items": pilot_items,
            "max_omission_calls": max_omission_calls,
            "max_memory_chars": max_memory_chars,
            "max_strategy_chars": max_strategy_chars,
            "max_tokens": max_tokens,
            "response_attestation_sha256": response_attestation_sha256,
            "evaluation_freeze_sha256": evaluation_freeze_sha256,
        },
        expected={
            "calls": len(calls),
            "score_rows": len(calls),
        },
        study_freeze_sha256=evaluation_freeze_sha256,
    )
    return summary
