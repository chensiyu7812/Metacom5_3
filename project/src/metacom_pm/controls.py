from __future__ import annotations

from typing import Any
from .contracts import (
    DialogueTurn,
    MemoryItem,
    MemorySource,
    RuntimeState,
    SourceCatalog,
    StrategyCard,
)
from .io import stable_hex
from .prompts import (
    memory_omission_messages,
    memory_use_messages,
    response_pair_messages,
    strategy_use_messages,
)


ZERO = [0.0] * 64

CONTROL_GATE_TIERS = {
    # Boundary diagnostics: these are intentionally reported, but they are not
    # used as hard pilot gates because they mix multiple subjective desiderata.
    "resp_authorized_unseen_neutral": "diagnostic",
    "m0_correct_optional": "diagnostic",
}

CONTROL_GATE_RATIONALES = {
    "resp_authorized_unseen_neutral": (
        "Boundary response control: it tests whether a blind response judge is "
        "neutral to an authorized but unseen memory reference, but it also "
        "confounds memory authorization with naturalness/non-intrusiveness."
    ),
    "m0_correct_optional": (
        "Boundary omission control: memory could personalize the response, but "
        "omitting it should not automatically invalidate an otherwise supportive "
        "reply."
    ),
}


def control_gate_tier(control_id: str) -> str:
    return CONTROL_GATE_TIERS.get(control_id, "hard")


def control_gate_rationale(control_id: str) -> str:
    return CONTROL_GATE_RATIONALES.get(
        control_id,
        "Hard calibration control with an intentionally clear expected judgment.",
    )


def control_state(tag: str, user_text: str, history: list[dict] | None = None) -> RuntimeState:
    return RuntimeState(
        state_id=f"state_{stable_hex('control', tag, n=20)}",
        card_id=f"card_{stable_hex('control-card', tag, n=20)}",
        user_id="control_user",
        split="development",
        semantic_family="heldout_control",
        current_user_text=user_text,
        current_session_history=history or [],
        current_session_summary="",
        session_index=5,
        inventory={
            source: SourceCatalog(
                available=False,
                count=0,
                estimated_tokens=0,
                catalog_fingerprint=ZERO,
            )
            for source in MemorySource
        },
        allowed_actions=["M0+R0", "M0+RS"],
    )


def heldout_controls() -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []

    def response(tag: str, user: str, a: str, b: str, expected: str):
        state = control_state(tag, user)
        controls.append({
            "control_id": tag,
            "kind": "response",
            "messages": response_pair_messages(state, a, b),
            "expected": {"preference": expected},
        })

    response(
        "resp_exact_tie",
        "I feel overwhelmed and unsure what to do next.",
        "That sounds overwhelming. We can slow down and take one part at a time.",
        "That sounds overwhelming. We can slow down and take one part at a time.",
        "tie",
    )
    response(
        "resp_clear_a",
        "I feel ashamed after making a mistake at work.",
        "It makes sense that this feels painful. One mistake does not define your reliability, and we can look at what would help tonight.",
        "You should stop overthinking and just work harder.",
        "A",
    )
    response(
        "resp_clear_b",
        "I cannot sleep because I keep replaying an argument.",
        "Calm down. There is no reason to keep thinking about it.",
        "Your mind sounds stuck on a painful moment. Would it help to name the part of the argument that keeps returning?",
        "B",
    )
    response(
        "resp_authorized_unseen_neutral",
        "Today has been heavy again.",
        "Given the work pressure you mentioned before, it makes sense that today feels heavy. We can stay with what is hardest right now.",
        "Today sounds heavy. We can stay with what is hardest right now.",
        "tie",
    )
    response(
        "resp_intrusive_reference",
        "I feel a little low today.",
        "Your breakup last September and your sister's engagement must be causing this.",
        "I hear that today feels low. Do you want company with the feeling, or help sorting out what is behind it?",
        "B",
    )

    # Memory-use controls use opaque IDs and text-grounded timestamps.
    state = control_state("m2_stale", "I am nervous about tomorrow's team meeting.")
    old = MemoryItem(
        memory_id=f"mem_{stable_hex('heldout', 'old', n=20)}",
        source=MemorySource.ME,
        created_session=1,
        text="The user once froze during a project update.",
    )
    controls.append({
        "control_id": "m2_stale_used",
        "kind": "memory_use",
        "messages": memory_use_messages(
            state, [old],
            "Because you always freeze in project updates, tomorrow will probably go the same way.",
        ),
        # This is an overgeneralization control, not a true stale-memory
        # control: the timeline contains no newer contradiction. The correct
        # failure mode is turning one event into an always/future-certainty
        # personal claim.
        "expected": {
            "unsupported_personal_claim_min": 1,
            "stale_or_conflicting_use_max": 1,
        },
        "selected_sources": ["ME"],
    })
    controls.append({
        "control_id": "m2_grounded",
        "kind": "memory_use",
        "messages": memory_use_messages(
            state, [old],
            "A previous project update was difficult, so it makes sense that tomorrow brings nerves. That one event does not predict how this meeting will go.",
        ),
        "expected": {"utilization_min": 1, "unsupported_personal_claim_max": 0},
        "selected_sources": ["ME"],
    })

    all_items = [
        MemoryItem(
            memory_id=f"mem_{stable_hex('heldout', 'pref', n=20)}",
            source=MemorySource.MP,
            created_session=2,
            text="The user prefers validation before practical planning.",
        )
    ]
    controls.append({
        "control_id": "m0_correct_optional",
        "kind": "memory_omission",
        "messages": memory_omission_messages(
            control_state("m0_optional", "I am tired after a long day."),
            all_items,
            "That sounds exhausting. You do not have to solve anything right now; we can simply slow down.",
        ),
        "expected": {"omission_appropriateness_min": 1, "missed_max": 1},
    })
    controls.append({
        "control_id": "m0_missed_critical",
        "kind": "memory_omission",
        "messages": memory_omission_messages(
            control_state("m0_critical", "I want advice, but please do it the way that usually works for me."),
            all_items,
            "Here are five steps you should follow immediately.",
        ),
        "expected": {"missed_min": 1},
    })

    strategy = StrategyCard(
        strategy_id=f"strat_{stable_hex('heldout', 'strategy', n=20)}",
        strategy_label="Reflection of feelings",
        retrieval_text="User is emotionally overwhelmed and needs reflection before advice.",
        guidance_text="Reflect the user's feeling before offering advice.",
        example_response="It sounds like you are carrying a lot right now.",
        source_dialogue_id="control",
        source_turn_index=0,
    )
    controls.append({
        "control_id": "strategy_good_use",
        "kind": "strategy",
        "messages": strategy_use_messages(
            control_state("strategy_good", "I feel completely overwhelmed."),
            [strategy],
            "It sounds like everything is piling up at once. We can slow down before deciding what to do.",
        ),
        "expected": {"relevance_min": 1, "utilization_min": 1, "premature_max": 0},
    })
    controls.append({
        "control_id": "strategy_premature",
        "kind": "strategy",
        "messages": strategy_use_messages(
            control_state("strategy_bad", "I feel completely overwhelmed."),
            [strategy],
            "Make a spreadsheet, call your manager, and complete these six steps tonight.",
        ),
        "expected": {"premature_min": 1},
    })
    for control in controls:
        control["gate_tier"] = control_gate_tier(control["control_id"])
        control["gate_rationale"] = control_gate_rationale(control["control_id"])
    return controls
