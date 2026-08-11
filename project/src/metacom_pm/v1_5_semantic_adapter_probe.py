from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


PHASE_LABELS: dict[str, str] = {
    "EXPLORATION": "exploration of the problem and feelings",
    "COMFORT": "emotional comforting and validation",
    "ACTION_PLANNING": "action planning or decision making",
    "RELIEF_CLOSURE": "relief and conversation closure",
}

GOAL_LABELS: dict[str, str] = {
    "EXPRESS_OR_UNDERSTAND": "express or understand feelings and the problem",
    "RECEIVE_VALIDATION": "receive emotional validation without a new task",
    "CLARIFY_OWN_PREFERENCE": "clarify the user's own preference or meaning",
    "CHOOSE_SMALL_ACTION": "choose one manageable next action",
    "CONSOLIDATE_AND_CLOSE": "consolidate progress and gently close",
}

RELATION_LABELS: dict[str, str] = {
    "DISTINCT_HELPFUL": "adds distinct information that could help the immediate response",
    "REDUNDANT_CURRENT": "repeats information already present in the current dialogue",
    "STALE_OR_CONFLICTING": "may be stale or conflict with the current situation",
    "LOW_INFORMATION": "contains too little information to affect the response",
    "DISTRACTING": "would distract from the user's immediate support need",
}


def latest_dialogue_window(text: str, *, max_chars: int = 3200) -> str:
    """Preserve the latest turns rather than silently truncating them away."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    chosen: list[str] = []
    used = 0
    for line in reversed(lines):
        extra = len(line) + (1 if chosen else 0)
        if chosen and used + extra > max_chars:
            break
        chosen.append(line)
        used += extra
    return "\n".join(reversed(chosen))


def candidate_relation_premise(current_context: str, exact_source: str) -> str:
    return (
        "CURRENT EMOTIONAL-SUPPORT DIALOGUE:\n"
        + latest_dialogue_window(current_context, max_chars=2500)
        + "\n\nSTRICTLY PAST USER STATEMENT:\n"
        + exact_source.strip()
    )


def forced_choice_scores(
    classifier: Callable[..., Mapping[str, Any]],
    *,
    sequence: str,
    labels: Mapping[str, str],
    hypothesis_template: str,
) -> dict[str, Any]:
    """Return stable code-keyed scores from a zero-shot NLI classifier."""

    description_to_code = {description: code for code, description in labels.items()}
    result = classifier(
        sequence,
        list(labels.values()),
        multi_label=False,
        hypothesis_template=hypothesis_template,
    )
    scores = {
        description_to_code[description]: float(score)
        for description, score in zip(result["labels"], result["scores"], strict=True)
    }
    ordered = sorted(scores, key=scores.get, reverse=True)
    return {
        "top_label": ordered[0],
        "margin_top1_top2": scores[ordered[0]] - scores[ordered[1]],
        "scores": {code: scores[code] for code in labels},
    }


def classify_semantic_state(
    classifier: Callable[..., Mapping[str, Any]],
    *,
    current_context: str,
    exact_source: str,
) -> dict[str, Any]:
    current = latest_dialogue_window(current_context)
    return {
        "support_phase": forced_choice_scores(
            classifier,
            sequence=current,
            labels=PHASE_LABELS,
            hypothesis_template="The emotional-support stage is {}.",
        ),
        "immediate_support_goal": forced_choice_scores(
            classifier,
            sequence=current,
            labels=GOAL_LABELS,
            hypothesis_template="The user's immediate support goal is to {}.",
        ),
        "candidate_relation_to_current": forced_choice_scores(
            classifier,
            sequence=candidate_relation_premise(current_context, exact_source),
            labels=RELATION_LABELS,
            hypothesis_template="The past statement {}.",
        ),
    }


def validate_oracle_plans(
    plans: Sequence[Mapping[str, Any]],
    *,
    expected_case_ids: set[str],
) -> dict[str, bool]:
    required = {
        "qualification_case_id",
        "oracle_disposition",
        "material_increment_assessment",
        "entity_link_status",
        "support_phase",
        "immediate_goal",
        "candidate_increment",
        "good_use",
        "forbidden_focus_shift",
        "nonuse_condition",
    }
    ids = [str(plan.get("qualification_case_id")) for plan in plans]
    return {
        "exactly_eight_unique_plans": len(plans) == len(set(ids)) == 8,
        "exact_frozen_teacher_suitable_case_set": set(ids) == expected_case_ids,
        "all_required_fields_nonempty": all(
            required.issubset(plan)
            and all(isinstance(plan[field], str) and plan[field].strip() for field in required)
            for plan in plans
        ),
        "each_plan_has_explicit_safe_nonuse": all(
            "Leave the memory unused" in str(plan.get("nonuse_condition", ""))
            for plan in plans
        ),
        "no_plan_forces_literal_copy": all(
            "exact wording" not in " ".join(map(str, plan.values())).lower()
            and "quote the" not in " ".join(map(str, plan.values())).lower()
            for plan in plans
        ),
        "use_and_nonuse_controls_both_present": {
            str(plan.get("oracle_disposition")) for plan in plans
        }
        == {"USE_IF_NATURAL", "SAFE_NONUSE"},
        "exactly_six_use_two_nonuse": sum(
            plan.get("oracle_disposition") == "USE_IF_NATURAL" for plan in plans
        )
        == 6
        and sum(plan.get("oracle_disposition") == "SAFE_NONUSE" for plan in plans)
        == 2,
    }
