from __future__ import annotations

import json
from pathlib import Path

import pytest

from pydantic import ValidationError

from metacom_pm.v1_5_context_grounding_data_repair import (
    MAX_REPAIRED_TURN_CONTENT_CHARS,
    FieldOnlyRepairOutput,
    VISIBLE_SURFACE_REPAIR_TURN_INDICES,
    VisibleSurfaceRepairOutput,
    apply_field_only_repair,
    apply_visible_surface_repair,
    build_field_only_repair_messages,
    build_visible_surface_repair_messages,
    maximum_legal_field_only_repair_output_tokens,
    maximum_legal_visible_surface_repair_output_tokens,
    repair_call_plan_row,
    validate_repair_allowlist_diff,
)
from metacom_pm.v1_5_context_grounding_repair import (
    DEFAULT_CLASSIFICATION_PATH,
    data_defect_state_ids,
    field_only_repair_state_ids,
    load_context_grounding_defect_classification,
    visible_surface_repair_state_ids,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "pm_v1_5_formal_v8_18_duplicate_repair_candidate"


def _load_real_state_and_context(state_id: str) -> tuple[dict, dict]:
    state = None
    with open(DATA_DIR / "pm_v2_states.jsonl") as f:
        for line in f:
            row = json.loads(line)
            if row["state_id"] == state_id:
                state = row
                break
    context = None
    with open(DATA_DIR / "evaluator_contexts.jsonl") as f:
        for line in f:
            row = json.loads(line)
            if row["state_id"] == state_id:
                context = row
                break
    assert state is not None and context is not None
    return state, context


@pytest.fixture(scope="module")
def classification_records():
    return load_context_grounding_defect_classification(DEFAULT_CLASSIFICATION_PATH)


def test_visible_surface_turn_indices_exactly_match_the_classification(classification_records) -> None:
    expected = visible_surface_repair_state_ids(classification_records)
    assert set(VISIBLE_SURFACE_REPAIR_TURN_INDICES) == expected
    assert len(expected) == 6


def test_field_only_and_visible_surface_partition_the_25_defects(classification_records) -> None:
    field_only = field_only_repair_state_ids(classification_records)
    surface = visible_surface_repair_state_ids(classification_records)
    assert len(field_only) == 19
    assert len(surface) == 6
    assert field_only | surface == data_defect_state_ids(classification_records)


def test_repair_call_plan_row_builds_for_every_data_defect_record(classification_records) -> None:
    defects = [r for r in classification_records if r.classification == "DATA_DEFECT"]
    assert len(defects) == 25
    for record in defects:
        row = repair_call_plan_row(record)
        assert row["state_id"] == record.state_id
        assert row["raw_estimated_input_tokens"] > 0
        if record.repair_mode == "FIELD_ONLY_REPAIR":
            assert row["response_schema"] == "FieldOnlyRepairOutput"
        else:
            assert row["response_schema"] == "VisibleSurfaceRepairOutput"


def test_field_only_repair_messages_never_mention_turn_indices() -> None:
    messages = build_field_only_repair_messages(
        current_user_text="text", history=[{"role": "user", "content": "hi"}], defect_note="note"
    )
    serialized = json.dumps(messages)
    assert "turn_indices_to_repair" not in serialized


def test_apply_field_only_repair_only_changes_summary_and_context() -> None:
    state, context = _load_real_state_and_context("state_032737f91e3c332227f04942")
    repair = FieldOnlyRepairOutput(
        authorized_user_context="The user is navigating adult friendships.",
        session_summary="",
    )
    repaired_state, repaired_context = apply_field_only_repair(
        state=state, evaluator_context=context, repair=repair
    )
    validate_repair_allowlist_diff(
        original_state=state,
        original_evaluator_context=context,
        repaired_state=repaired_state,
        repaired_evaluator_context=repaired_context,
        repair_mode="FIELD_ONLY_REPAIR",
    )
    assert repaired_context["authorized_user_context"] == repair.authorized_user_context
    assert repaired_state["current_session_history"] == state["current_session_history"]


def test_apply_field_only_repair_rejects_if_history_also_changed() -> None:
    state, context = _load_real_state_and_context("state_032737f91e3c332227f04942")
    repair = FieldOnlyRepairOutput(authorized_user_context="fixed.", session_summary="")
    repaired_state, repaired_context = apply_field_only_repair(
        state=state, evaluator_context=context, repair=repair
    )
    tampered_history = list(repaired_state["current_session_history"])
    tampered_history[0] = {**tampered_history[0], "content": "a sneaky rewrite"}
    repaired_state = {**repaired_state, "current_session_history": tampered_history}
    with pytest.raises(RuntimeError, match="frozen state field: 'current_session_history'"):
        validate_repair_allowlist_diff(
            original_state=state,
            original_evaluator_context=context,
            repaired_state=repaired_state,
            repaired_evaluator_context=repaired_context,
            repair_mode="FIELD_ONLY_REPAIR",
        )


def test_apply_visible_surface_repair_replaces_only_specified_turns() -> None:
    state_id = "state_481fdb962d3774c3e0d720bb"
    state, context = _load_real_state_and_context(state_id)
    turn_indices = VISIBLE_SURFACE_REPAIR_TURN_INDICES[state_id]
    assert turn_indices == (0,)
    repair = VisibleSurfaceRepairOutput(
        repaired_turn_contents=["I've been struggling with the loss of my grandmother. It's been really tough on my family and me."],
        authorized_user_context="The user has recently lost their grandmother.",
        session_summary="",
    )
    repaired_state, repaired_context = apply_visible_surface_repair(
        state=state, evaluator_context=context, turn_indices=turn_indices, repair=repair
    )
    validate_repair_allowlist_diff(
        original_state=state,
        original_evaluator_context=context,
        repaired_state=repaired_state,
        repaired_evaluator_context=repaired_context,
        repair_mode="VISIBLE_SURFACE_REPAIR",
    )
    assert repaired_state["current_session_history"][0]["content"] == repair.repaired_turn_contents[0]
    # The untouched turn must be byte-identical.
    assert (
        repaired_state["current_session_history"][1]
        == state["current_session_history"][1]
    )


def test_validate_rejects_a_changed_current_user_text() -> None:
    state, context = _load_real_state_and_context("state_032737f91e3c332227f04942")
    tampered_state = {**state, "current_user_text": "a completely different turn"}
    with pytest.raises(RuntimeError, match="current_user_text"):
        validate_repair_allowlist_diff(
            original_state=state,
            original_evaluator_context=context,
            repaired_state=tampered_state,
            repaired_evaluator_context=context,
            repair_mode="FIELD_ONLY_REPAIR",
        )


def test_validate_rejects_a_changed_semantic_family() -> None:
    state, context = _load_real_state_and_context("state_032737f91e3c332227f04942")
    tampered_state = {**state, "semantic_family": "some_other_family"}
    with pytest.raises(RuntimeError, match="frozen state field"):
        validate_repair_allowlist_diff(
            original_state=state,
            original_evaluator_context=context,
            repaired_state=tampered_state,
            repaired_evaluator_context=context,
            repair_mode="FIELD_ONLY_REPAIR",
        )


def test_validate_rejects_a_changed_regime() -> None:
    state, context = _load_real_state_and_context("state_032737f91e3c332227f04942")
    tampered_context = {**context, "regime": "some_other_regime"}
    with pytest.raises(RuntimeError, match="frozen evaluator_context field"):
        validate_repair_allowlist_diff(
            original_state=state,
            original_evaluator_context=context,
            repaired_state=state,
            repaired_evaluator_context=tampered_context,
            repair_mode="FIELD_ONLY_REPAIR",
        )


def test_validate_rejects_a_stale_context_payload_sha256() -> None:
    state, context = _load_real_state_and_context("state_032737f91e3c332227f04942")
    repair = FieldOnlyRepairOutput(authorized_user_context="a new real context.", session_summary="")
    repaired_state, repaired_context = apply_field_only_repair(
        state=state, evaluator_context=context, repair=repair
    )
    stale_context = {**repaired_context, "context_payload_sha256": context["context_payload_sha256"]}
    with pytest.raises(RuntimeError, match="does not match its own recomputed hash"):
        validate_repair_allowlist_diff(
            original_state=state,
            original_evaluator_context=context,
            repaired_state=repaired_state,
            repaired_evaluator_context=stale_context,
            repair_mode="FIELD_ONLY_REPAIR",
        )


def test_validate_rejects_a_turn_count_change_for_visible_surface_repair() -> None:
    state_id = "state_481fdb962d3774c3e0d720bb"
    state, context = _load_real_state_and_context(state_id)
    repaired_state = {
        **state,
        "current_session_history": list(state["current_session_history"]) + [
            {"role": "user", "content": "an extra turn"}
        ],
    }
    with pytest.raises(RuntimeError, match="number of history turns"):
        validate_repair_allowlist_diff(
            original_state=state,
            original_evaluator_context=context,
            repaired_state=repaired_state,
            repaired_evaluator_context=context,
            repair_mode="VISIBLE_SURFACE_REPAIR",
        )


def test_validate_rejects_a_role_change_for_visible_surface_repair() -> None:
    state_id = "state_481fdb962d3774c3e0d720bb"
    state, context = _load_real_state_and_context(state_id)
    new_history = [dict(t) for t in state["current_session_history"]]
    new_history[0]["role"] = "assistant"
    repaired_state = {**state, "current_session_history": new_history}
    with pytest.raises(RuntimeError, match="changed the role"):
        validate_repair_allowlist_diff(
            original_state=state,
            original_evaluator_context=context,
            repaired_state=repaired_state,
            repaired_evaluator_context=context,
            repair_mode="VISIBLE_SURFACE_REPAIR",
        )


def test_visible_surface_output_rejects_a_turn_over_the_length_cap() -> None:
    with pytest.raises(ValidationError):
        VisibleSurfaceRepairOutput(
            repaired_turn_contents=["x" * (MAX_REPAIRED_TURN_CONTENT_CHARS + 1)],
            authorized_user_context="fine.",
            session_summary="",
        )


def test_worst_case_token_preflight_functions_are_real_and_positive() -> None:
    field_only = maximum_legal_field_only_repair_output_tokens()
    visible_surface = maximum_legal_visible_surface_repair_output_tokens()
    assert field_only > 0
    assert visible_surface > field_only  # 8 bounded turns dominate the payload
    # Corpus's real observed max history-turn length is 180 chars; the 400-char
    # cap must clear it with real margin -- if this ever regresses, the cap
    # itself (not just this test) needs revisiting.
    assert MAX_REPAIRED_TURN_CONTENT_CHARS > 180
