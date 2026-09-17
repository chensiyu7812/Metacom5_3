from pathlib import Path

from metacom_pm.io import sha256_text
from metacom_pm.paper1.candidates import compile_multi_view_candidate_bundle
from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session, Target, Turn
from metacom_pm.paper1.multi_view_memory import (
    AcceptedEventExperienceUnit,
    AcceptedProfileViewUnit,
    EventExperienceType,
    EventTemporalStatus,
    GroundedSourceSpan,
    ProfileFieldType,
)


ROOT = Path(__file__).resolve().parents[1]


def _span(
    span_id: str = "s1",
    *,
    text: str = "I moved to Tokyo after changing jobs.",
    session_id: str = "session-1",
) -> GroundedSourceSpan:
    return GroundedSourceSpan(
        span_id=span_id,
        turn_id=f"{session_id}:0",
        turn_index=0,
        exact_text=text,
        start_char=0,
        end_char=len(text),
        exact_text_sha256=sha256_text(text),
    )


def _user() -> MemorySourceUser:
    return MemorySourceUser(
        owner_id="u1",
        sessions=(
            Session(
                session_id="session-0",
                timestamp="2025-01-01",
                chronological_rank=0,
                turns=(Turn(idx=0, role="seeker", content="I used to live in Osaka."),),
            ),
            Session(
                session_id="session-1",
                timestamp="2025-02-01",
                chronological_rank=1,
                turns=(
                    Turn(idx=0, role="seeker", content="I moved to Tokyo after changing jobs."),
                    Turn(idx=1, role="supporter", content="That is a major transition."),
                ),
            ),
        ),
        question_groups=(),
        summaries=(),
        subsequent_topics=(),
    )


def _target(cutoff_rank: int = 2) -> Target:
    return Target(
        target_id="u1::qa::1",
        task_type=TaskType.QA,
        owner_id="u1",
        primary_group_key="u1::qa::x",
        cutoff_rank=cutoff_rank,
        visible_query_text="Where does the user live now?",
    )


def _profile(memory_id: str, rank: int, value: str) -> AcceptedProfileViewUnit:
    source_text = (
        "I used to live in Osaka."
        if rank == 0
        else "I moved to Tokyo after changing jobs."
    )
    return AcceptedProfileViewUnit(
        memory_id=memory_id,
        owner_id="u1",
        source_session_id=f"session-{rank}",
        source_session_rank=rank,
        timestamp=f"2025-0{rank + 1}-01",
        profile_field_type=ProfileFieldType.LOCATION,
        profile_slot_key="residence.current_city",
        normalized_value=value,
        rendered_candidate_content=f"Current residence: {value}",
        supporting_spans=(
            _span(f"span-{memory_id}", text=source_text, session_id=f"session-{rank}"),
        ),
        compiler_identity_sha256="a" * 64,
    )


def test_current_profile_view_keeps_history_but_materializes_latest_slot_only():
    bundle = compile_multi_view_candidate_bundle(
        (_profile("old", 0, "Osaka"), _profile("new", 1, "Tokyo")),
        _user(),
        _target(),
    )
    assert [candidate.content for candidate in bundle[Head.MP]] == [
        "Current residence: Tokyo"
    ]


def test_me_is_broad_timeline_and_action_outcome_is_only_one_subtype():
    common = dict(
        owner_id="u1",
        source_session_id="session-1",
        source_session_rank=1,
        timestamp="2025-02-01",
        temporal_status=EventTemporalStatus.OCCURRED,
        supporting_spans=(_span(),),
        compiler_identity_sha256="b" * 64,
    )
    moved = AcceptedEventExperienceUnit(
        memory_id="event-moved",
        event_experience_type=EventExperienceType.LIFE_EVENT,
        normalized_event="Moved to Tokyo",
        rendered_candidate_content="[2025-02-01] Moved to Tokyo",
        **common,
    )
    coping = AcceptedEventExperienceUnit(
        memory_id="event-coping",
        event_experience_type=EventExperienceType.ACTION_OBSERVED_OUTCOME,
        normalized_event="Walking reduced stress",
        rendered_candidate_content="[2025-02-01] Walking reduced stress",
        action_text="walked",
        observed_outcome_text="felt less stressed",
        **common,
    )
    bundle = compile_multi_view_candidate_bundle((moved, coping), _user(), _target())
    assert len(bundle[Head.ME]) == 2
    assert {
        row.raw_descriptors["me_event_experience_type"] for row in bundle[Head.ME]
    } == {"life_event", "action_observed_outcome"}


def test_ms_is_one_complete_raw_session_and_never_a_semantic_atom():
    bundle = compile_multi_view_candidate_bundle((), _user(), _target())
    assert len(bundle[Head.MS]) == 2
    latest = bundle[Head.MS][1]
    assert latest.raw_descriptors["complete_raw_session_transcript"] is True
    assert latest.content == (
        "seeker: I moved to Tokyo after changing jobs.\n"
        "supporter: That is a major transition."
    )


def test_same_user_span_can_project_to_profile_and_event_views():
    event = AcceptedEventExperienceUnit(
        memory_id="event",
        owner_id="u1",
        source_session_id="session-1",
        source_session_rank=1,
        timestamp="2025-02-01",
        event_experience_type=EventExperienceType.LIFE_EVENT,
        temporal_status=EventTemporalStatus.OCCURRED,
        normalized_event="Moved to Tokyo",
        rendered_candidate_content="[2025-02-01] Moved to Tokyo",
        supporting_spans=(_span("shared"),),
        compiler_identity_sha256="c" * 64,
    )
    profile = _profile("profile", 1, "Tokyo").model_copy(
        update={"supporting_spans": (_span("shared"),)}
    )
    bundle = compile_multi_view_candidate_bundle((profile, event), _user(), _target())
    assert bundle[Head.MP][0].lineage.source_record_ids[-1] == "shared"
    assert bundle[Head.ME][0].lineage.source_record_ids[-1] == "shared"


def test_active_authority_does_not_regress_to_the_historical_ontology():
    active_paths = (
        ROOT.parent / "AGENTS.md",
        ROOT / "configs/paper1_public_only.yaml",
        ROOT / "docs/PM_PAPER1_EXECUTION_CHECKLIST_20260903_ZH.md",
        ROOT / "docs/PM_PAPER1_V2_1_CONSISTENCY_AMENDMENT_20260903_ZH.md",
        ROOT
        / "data/paper1_authority/paper1_v2_1_consistency_amendment_20260903_v1.json",
        ROOT / "src/metacom_pm/paper1/multi_view_memory/prompts.py",
    )
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)
    for stale_definition in (
        "MS/cross-session continuity",
        "MS = cross-session continuity",
        "ME/action→observed-outcome",
        "ME = action→observed outcome",
        "ME requires action+outcome",
        "MS_EVENT",
        "MS_STATE",
        "MS_CHANGE",
    ):
        assert stale_definition not in active_text
