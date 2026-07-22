"""Repair-content generation for the 25 DATA_DEFECT states found in
data/pm_v1_5_contracts/context_grounding_defect_classification_v1.jsonl.

Two isolated repair modes, matching the classification's repair_mode field:

- FIELD_ONLY_REPAIR (19 states): current_user_text and current_session_
  history are internally consistent. Only authorized_user_context and/or
  session_summary are regenerated, strictly grounded in the frozen visible
  dialogue -- never touching current_user_text or history.

- VISIBLE_SURFACE_REPAIR (6 states): the visible dialogue itself names two
  different people/relations across turns (or an unresolved two-move
  narrative). Only the specific conflicting history turn(s) are
  regenerated -- current_user_text, regime, semantic_family, turn count,
  and role order are all frozen -- then authorized_user_context/
  session_summary are regenerated from the corrected dialogue.

VISIBLE_SURFACE_REPAIR_TURN_INDICES below is a hand-verified, disclosed
specification of exactly which turn indices are inconsistent with the
current_user_text anchor for each of the 6 states -- re-derived by reading
every turn's text directly (not just the turn the judges happened to
complain about), including pronoun cascades a shallower read would miss
(e.g. state_d0eee004b44a562c57a0e6c6 needs turns 0, 2, 3, 4, 5 -- not just
turn 0 -- because "her"/"her memory" recurs in four separate turns after
the initial grandmother/grandfather mismatch).
"""

from __future__ import annotations

from typing import Annotated, Any, Mapping, Sequence

from pydantic import Field

from .io import canonical_json, sha256_text
from .pm_v2_contracts import StrictModel
from .text import estimate_tokens
from .v1_5_context_grounding_repair import ContextGroundingClassificationRecord

# Every state/evaluator_context field NOT in these two sets must be
# byte-identical before and after repair -- checked explicitly, field by
# field, rather than trusting the repair call to only touch what it was
# asked to. context_payload_sha256 is a hash DERIVED from every other
# evaluator_context field (evaluator_context_payload_sha256 in
# pm_v2_data.py) -- it is expected to change when authorized_user_context
# changes, but is separately verified to be the correct recomputed hash,
# never just allowed to be anything.
STATE_FIELDS_ALLOWED_TO_CHANGE = frozenset({"current_session_summary"})
STATE_FIELDS_ALLOWED_TO_CHANGE_VISIBLE_SURFACE = frozenset(
    {"current_session_summary", "current_session_history"}
)
EVALUATOR_CONTEXT_FIELDS_ALLOWED_TO_CHANGE = frozenset(
    {"authorized_user_context", "context_payload_sha256"}
)

REPAIR_GENERATION_PROTOCOL = "pm-v1.5-context-grounding-data-repair-v1"

MAX_CONTEXT_FIELD_CHARS = 250

# Hand-verified per-state specification: which current_session_history
# turn indices (0-based) are inconsistent with the current_user_text
# anchor and must be regenerated. Every other turn, and current_user_text
# itself, is frozen. Re-derive by reading every turn if this ever needs to
# change -- a shallow read (fixing only the turn a judge complained about)
# will under-count pronoun cascades, as it did on the first pass here.
VISIBLE_SURFACE_REPAIR_TURN_INDICES: dict[str, tuple[int, ...]] = {
    "state_44550214bf7c9fa22284a731": (0, 1),  # manager -> coworker (turn 1 replies "your manager")
    "state_481fdb962d3774c3e0d720bb": (0,),  # grandfather -> grandmother
    "state_7d1e36f110bdacbd2a0545f2": (0,),  # brother -> friend
    "state_9e0c7dd3b2e6081857a7d19f": (0, 3),  # grandfather -> grandmother; "him" -> "her"
    "state_d0eee004b44a562c57a0e6c6": (0, 2, 3, 4, 5),  # grandmother -> grandfather; "her"(x4) -> "his"
    "state_ba1e526156d1cf3810fa8e98": (0,),  # remove "since I moved here" -- conflicts with current turn's prospective move
}


class FieldOnlyRepairOutput(StrictModel):
    authorized_user_context: str = Field(min_length=1, max_length=MAX_CONTEXT_FIELD_CHARS)
    session_summary: str = Field(min_length=0, max_length=MAX_CONTEXT_FIELD_CHARS)


# Real corpus max observed history-turn length is 180 chars (checked
# directly against every turn in data/pm_v1_5_formal_v8_18_duplicate_
# repair_candidate); 400 gives real margin without being unbounded --
# an unbounded per-item string here would repeat the exact
# output_token_limit crash class this project already root-caused once
# for SingleFieldDiagnosticOutput.
MAX_REPAIRED_TURN_CONTENT_CHARS = 400


class VisibleSurfaceRepairOutput(StrictModel):
    repaired_turn_contents: list[
        Annotated[str, Field(max_length=MAX_REPAIRED_TURN_CONTENT_CHARS)]
    ] = Field(min_length=1, max_length=8)
    authorized_user_context: str = Field(min_length=1, max_length=MAX_CONTEXT_FIELD_CHARS)
    session_summary: str = Field(min_length=0, max_length=MAX_CONTEXT_FIELD_CHARS)


def maximum_legal_field_only_repair_output_tokens() -> int:
    """Computed (not eyeballed) worst-case token estimate for a maximally-
    sized, schema-legal FieldOnlyRepairOutput."""

    worst_case = FieldOnlyRepairOutput(
        authorized_user_context="x" * MAX_CONTEXT_FIELD_CHARS,
        session_summary="x" * MAX_CONTEXT_FIELD_CHARS,
    )
    return estimate_tokens(canonical_json(worst_case.model_dump(mode="json")))


def maximum_legal_visible_surface_repair_output_tokens() -> int:
    """Computed (not eyeballed) worst-case token estimate for a maximally-
    sized, schema-legal VisibleSurfaceRepairOutput (all 8 turns at the cap)."""

    worst_case = VisibleSurfaceRepairOutput(
        repaired_turn_contents=["x" * MAX_REPAIRED_TURN_CONTENT_CHARS] * 8,
        authorized_user_context="x" * MAX_CONTEXT_FIELD_CHARS,
        session_summary="x" * MAX_CONTEXT_FIELD_CHARS,
    )
    return estimate_tokens(canonical_json(worst_case.model_dump(mode="json")))


_COMMON_REPAIR_SYSTEM = (
    "You repair one field of a frozen synthetic support-conversation record. "
    "The current_user_text and every history turn not explicitly listed as "
    "repairable are FROZEN and must never be referenced as needing a change "
    "-- you are only asked to produce replacement text for the specific "
    "field(s) named in this task. "
    "authorized_user_context and session_summary may summarize ONLY facts "
    "that are explicitly stated or unambiguously implied by the visible "
    "dialogue given to you -- never invent an identity attribute (gender, "
    "marital status, age), a relationship duration, or a third party's "
    "belief that is not actually present in the dialogue. "
    "If the visible dialogue does not support a substantive session_summary "
    "beyond what authorized_user_context already says, return an empty "
    "string for session_summary rather than inventing content."
)


def build_field_only_repair_messages(
    *,
    current_user_text: str,
    history: Sequence[Mapping[str, Any]],
    defect_note: str,
) -> list[dict[str, str]]:
    payload = {
        "task": "field_only_repair",
        "defect_note": defect_note,
        "frozen_current_user_text": current_user_text,
        "frozen_history": list(history),
        "instruction": (
            "Produce authorized_user_context and session_summary, each "
            "grounded only in frozen_current_user_text and frozen_history "
            "above. Do not reproduce the defect described in defect_note."
        ),
    }
    return [
        {"role": "system", "content": _COMMON_REPAIR_SYSTEM},
        {"role": "user", "content": canonical_json(payload)},
    ]


def build_visible_surface_repair_messages(
    *,
    current_user_text: str,
    history: Sequence[Mapping[str, Any]],
    turn_indices_to_repair: Sequence[int],
    defect_note: str,
) -> list[dict[str, str]]:
    indexed_history = [
        {"index": index, "role": turn["role"], "content": turn["content"]}
        for index, turn in enumerate(history)
    ]
    payload = {
        "task": "visible_surface_repair",
        "defect_note": defect_note,
        "frozen_current_user_text": current_user_text,
        "indexed_history": indexed_history,
        "turn_indices_to_repair": list(turn_indices_to_repair),
        "instruction": (
            "Every history turn NOT listed in turn_indices_to_repair is "
            "frozen and must stay conceptually identical (do not restate "
            "it). Produce replacement content ONLY for the turns listed in "
            "turn_indices_to_repair, in that exact order, each rewritten to "
            "be consistent with frozen_current_user_text's topic/referent "
            "and with every frozen turn around it -- preserve each turn's "
            "role and natural conversational flow. Then produce "
            "authorized_user_context and session_summary grounded in the "
            "corrected full conversation (frozen_current_user_text plus "
            "every history turn, repaired or not)."
        ),
    }
    return [
        {"role": "system", "content": _COMMON_REPAIR_SYSTEM},
        {"role": "user", "content": canonical_json(payload)},
    ]


def repair_call_plan_row(
    record: ContextGroundingClassificationRecord,
) -> dict[str, Any]:
    """Build one (unpriced) call-plan row for a single DATA_DEFECT record."""

    if record.repair_mode == "FIELD_ONLY_REPAIR":
        messages = build_field_only_repair_messages(
            current_user_text=record.current_user_text,
            history=record.history,
            defect_note=record.rationale,
        )
        response_schema_name = FieldOnlyRepairOutput.__name__
    elif record.repair_mode == "VISIBLE_SURFACE_REPAIR":
        turn_indices = VISIBLE_SURFACE_REPAIR_TURN_INDICES[record.state_id]
        messages = build_visible_surface_repair_messages(
            current_user_text=record.current_user_text,
            history=record.history,
            turn_indices_to_repair=turn_indices,
            defect_note=record.rationale,
        )
        response_schema_name = VisibleSurfaceRepairOutput.__name__
    else:
        raise RuntimeError(
            f"unsupported repair_mode for {record.state_id}: {record.repair_mode}"
        )
    payload_text = canonical_json(messages)
    return {
        "state_id": record.state_id,
        "repair_mode": record.repair_mode,
        "defect_type": record.defect_type,
        "response_schema": response_schema_name,
        "messages": messages,
        "raw_estimated_input_tokens": estimate_tokens(payload_text),
    }


def _evaluator_context_payload_sha256(evaluator_context: Mapping[str, Any]) -> str:
    from .pm_v2_data import EVALUATOR_CONTEXT_FIELDS

    payload = {
        key: evaluator_context[key]
        for key in sorted(EVALUATOR_CONTEXT_FIELDS - {"context_payload_sha256"})
    }
    return sha256_text(canonical_json(payload))


def apply_field_only_repair(
    *,
    state: Mapping[str, Any],
    evaluator_context: Mapping[str, Any],
    repair: FieldOnlyRepairOutput,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repaired_state = dict(state)
    repaired_state["current_session_summary"] = repair.session_summary
    repaired_context = dict(evaluator_context)
    repaired_context["authorized_user_context"] = repair.authorized_user_context
    repaired_context["context_payload_sha256"] = _evaluator_context_payload_sha256(
        repaired_context
    )
    return repaired_state, repaired_context


def apply_visible_surface_repair(
    *,
    state: Mapping[str, Any],
    evaluator_context: Mapping[str, Any],
    turn_indices: Sequence[int],
    repair: VisibleSurfaceRepairOutput,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(repair.repaired_turn_contents) != len(turn_indices):
        raise RuntimeError(
            "repaired_turn_contents length does not match turn_indices_to_repair"
        )
    new_history = [dict(turn) for turn in state["current_session_history"]]
    for index, content in zip(turn_indices, repair.repaired_turn_contents):
        new_history[index] = {**new_history[index], "content": content}
    repaired_state = dict(state)
    repaired_state["current_session_history"] = new_history
    repaired_state["current_session_summary"] = repair.session_summary
    repaired_context = dict(evaluator_context)
    repaired_context["authorized_user_context"] = repair.authorized_user_context
    repaired_context["context_payload_sha256"] = _evaluator_context_payload_sha256(
        repaired_context
    )
    return repaired_state, repaired_context


def validate_repair_allowlist_diff(
    *,
    original_state: Mapping[str, Any],
    original_evaluator_context: Mapping[str, Any],
    repaired_state: Mapping[str, Any],
    repaired_evaluator_context: Mapping[str, Any],
    repair_mode: str,
) -> None:
    """Fail closed (raise) if any field outside the allowed set changed.

    This is the zero-API post-hoc check: it never trusts that a repair call
    "only touched what it was asked to" -- every state/evaluator_context
    field is compared explicitly, field by field, against its pre-repair
    value.
    """

    if repair_mode not in ("FIELD_ONLY_REPAIR", "VISIBLE_SURFACE_REPAIR"):
        raise RuntimeError(f"unsupported repair_mode: {repair_mode}")

    if str(original_state["current_user_text"]) != str(
        repaired_state["current_user_text"]
    ):
        raise RuntimeError(
            "repair changed current_user_text, which must always be frozen"
        )

    allowed_state_fields = (
        STATE_FIELDS_ALLOWED_TO_CHANGE_VISIBLE_SURFACE
        if repair_mode == "VISIBLE_SURFACE_REPAIR"
        else STATE_FIELDS_ALLOWED_TO_CHANGE
    )
    for key in set(original_state) | set(repaired_state):
        if key in allowed_state_fields:
            continue
        if original_state.get(key) != repaired_state.get(key):
            raise RuntimeError(f"repair changed a frozen state field: {key!r}")

    for key in set(original_evaluator_context) | set(repaired_evaluator_context):
        if key in EVALUATOR_CONTEXT_FIELDS_ALLOWED_TO_CHANGE:
            continue
        if original_evaluator_context.get(key) != repaired_evaluator_context.get(key):
            raise RuntimeError(
                f"repair changed a frozen evaluator_context field: {key!r}"
            )

    expected_hash = _evaluator_context_payload_sha256(repaired_evaluator_context)
    if repaired_evaluator_context.get("context_payload_sha256") != expected_hash:
        raise RuntimeError(
            "repaired evaluator_context's context_payload_sha256 does not "
            "match its own recomputed hash"
        )

    # FIELD_ONLY_REPAIR already fails closed on any current_session_history
    # change via the generic per-field loop above (history is not in
    # STATE_FIELDS_ALLOWED_TO_CHANGE for that mode). Only VISIBLE_SURFACE_
    # REPAIR needs the additional structural checks below, since history IS
    # allowed to change there -- but only at the turn level (role and
    # ordering must still be preserved).
    if repair_mode == "VISIBLE_SURFACE_REPAIR":
        original_history = list(original_state["current_session_history"])
        repaired_history = list(repaired_state["current_session_history"])
        if len(original_history) != len(repaired_history):
            raise RuntimeError("repair changed the number of history turns")
        for index, (old_turn, new_turn) in enumerate(
            zip(original_history, repaired_history)
        ):
            if str(old_turn["role"]) != str(new_turn["role"]):
                raise RuntimeError(
                    f"repair changed the role of history turn {index}"
                )
