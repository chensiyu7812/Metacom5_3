from dataclasses import replace

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.memory_source import (
    MemorySourceUser,
    Session,
    Target,
    Turn,
)
from metacom_pm.paper1.execution.visible_state import (
    QueryTiming,
    VisibleStateProjection,
    VisibleStateSource,
    build_dg_visible_state,
    build_rs_visible_state,
    build_static_memory_visible_state,
)
from metacom_pm.paper1.rs.zero_outcome_census import RSDecisionState


def _user() -> MemorySourceUser:
    return MemorySourceUser(
        owner_id="p1",
        sessions=(
            Session(
                session_id="p1_conv_1",
                timestamp="2024-01-02",
                chronological_rank=1,
                turns=(
                    Turn(idx=0, role="seeker", content="I started a new job."),
                    Turn(idx=1, role="supporter", content="How has that felt?"),
                ),
            ),
        ),
        question_groups=(),
        summaries=(),
        subsequent_topics=(),
    )


def _target(task_type: TaskType, query: str | None) -> Target:
    return Target(
        target_id=f"p1::{task_type.value}::1",
        task_type=task_type,
        owner_id="p1",
        primary_group_key=f"p1::{task_type.value}",
        cutoff_rank=1,
        visible_query_text=query,
    )


def test_rs_projection_contains_only_pre_supporter_visible_state():
    state = RSDecisionState(
        state_id="rs_state_0123456789abcdef01234567",
        source_dialogue_id="esconv_0001",
        source_split="validation",
        decision_turn_index=2,
        visible_dialogue_text=(
            "seeker: I feel lost.\nsupporter: I hear you.\nseeker: What can I do?"
        ),
        query_text="supporter: I hear you.\nseeker: What can I do?",
        current_user_text="What can I do?",
        visible_turn_count=3,
        query_turn_count=2,
        current_user_turn_count=1,
    )
    projected = build_rs_visible_state(state)
    assert projected.task_type is TaskType.ESC_RESPONSE
    assert projected.current_user_text == "What can I do?"
    assert projected.model_text_fields == (
        "visible_context_text",
        "pm_query_text",
        "current_user_text",
    )
    assert projected.gold_reference_future_read is False


@pytest.mark.parametrize("task_type", [TaskType.QA, TaskType.SUMMARY])
def test_static_memory_projection_uses_exact_official_query_not_full_history(task_type):
    query = "What changed after the new job?"
    projected = build_static_memory_visible_state(_user(), _target(task_type, query))
    assert projected.pm_query_text == query
    assert projected.visible_context_text is None
    assert projected.history_text_in_pm_state is False
    assert projected.model_text_fields == ("pm_query_text", "current_user_text")
    assert projected.source_history_sha256 is not None


def test_dg_projection_is_exact_current_seeker_only():
    projected = build_dg_visible_state(
        _user(),
        _target(TaskType.DIALOGUE_GENERATION, None),
        round_index=3,
        live_dialogue_turns=(
            Turn(idx=0, role="seeker", content="Hello again."),
            Turn(idx=1, role="supporter", content="How are you doing?"),
            Turn(
                idx=2,
                role="seeker",
                content="  I am worried the same thing will happen again.  ",
            ),
        ),
    )
    expected = "I am worried the same thing will happen again."
    assert projected.pm_query_text == expected
    assert projected.current_user_text == expected
    assert projected.visible_context_text is None
    assert projected.dg_round_index == 3


def test_dg_static_pregeneration_query_is_rejected():
    with pytest.raises(ValueError, match="static pre-generation query"):
        build_dg_visible_state(
            _user(),
            _target(TaskType.DIALOGUE_GENERATION, "hidden topic"),
            round_index=1,
            live_dialogue_turns=(Turn(idx=0, role="seeker", content="Hello"),),
        )


def test_dg_projection_rejects_prefix_before_current_seeker_is_appended():
    with pytest.raises(ValueError, match="ending in a seeker"):
        build_dg_visible_state(
            _user(),
            _target(TaskType.DIALOGUE_GENERATION, None),
            round_index=1,
            live_dialogue_turns=(Turn(idx=0, role="supporter", content="Hello"),),
        )


def test_visible_state_forbids_gold_reference_or_future_fields():
    with pytest.raises(ValidationError):
        VisibleStateProjection(
            target_id="x",
            task_type=TaskType.QA,
            source=VisibleStateSource.ES_MEMEVAL_STATIC_OFFICIAL_QUERY,
            query_timing=QueryTiming.STATIC_OFFICIAL_QUERY,
            pm_query_text="question",
            current_user_text="question",
            model_text_fields=("pm_query_text", "current_user_text"),
            source_owner_id="p1",
            source_history_sha256="a" * 64,
            pm_query_sha256="b" * 64,
            current_user_sha256="b" * 64,
            gold_answer="forbidden",
        )


def test_memory_projection_rejects_wrong_owner_and_nonfull_cutoff():
    wrong_owner = replace(_target(TaskType.QA, "Question"), owner_id="p2")
    with pytest.raises(ValueError, match="owner"):
        build_static_memory_visible_state(_user(), wrong_owner)

    bad_cutoff = replace(_target(TaskType.QA, "Question"), cutoff_rank=0)
    with pytest.raises(ValueError, match="cutoff"):
        build_static_memory_visible_state(_user(), bad_cutoff)
