from pydantic import ValidationError
import pytest

from metacom_pm.paper1.data.memory_source import Session, Turn
from metacom_pm.paper1.semantic_memory.contracts import (
    CandidateSourceUse,
    MSContinuityType,
    MemoryClass,
    PriorAcceptedMemory,
    SessionCompileInput,
    SessionTurnInput,
)
from metacom_pm.paper1.semantic_memory.input_projection import (
    assert_compiler_input_firewall,
    build_session_compile_input,
)


def test_session_only_projection_has_no_enclosing_target_or_annotation_fields() -> None:
    session = Session(
        session_id="esc1",
        timestamp="2024-01-02",
        chronological_rank=1,
        turns=(Turn(idx=2, role="seeker", content="I moved to Kyoto."),),
    )
    projected = build_session_compile_input(owner_id="u1", session=session)
    payload = projected.model_dump(mode="json")
    assert payload["turns"][0]["turn_id"] == "esc1:turn:2"
    assert set(payload) == {
        "schema_version",
        "owner_id",
        "session_id",
        "timestamp",
        "chronological_rank",
        "turns",
        "strictly_past_memory_table",
    }


@pytest.mark.parametrize(
    "forbidden",
    ["question", "gold_answer", "reference", "evidence", "basic_info", "summary", "related_sessions"],
)
def test_input_firewall_rejects_privileged_keys_at_any_depth(forbidden: str) -> None:
    with pytest.raises(ValueError, match="forbidden key"):
        assert_compiler_input_firewall({"safe": [{forbidden: "leak"}]})


def test_prior_memory_must_be_same_owner_and_strictly_past() -> None:
    bad = PriorAcceptedMemory(
        memory_id="m0",
        owner_id="other",
        source_session_id="esc0",
        source_session_rank=0,
        memory_class=MemoryClass.MS,
        memory_subtype="ms_state",
        normalized_memory="Prior fact.",
        timestamp_status="ongoing",
        candidate_source_use=CandidateSourceUse.CANDIDATE_SOURCE,
        continuity_type=MSContinuityType.STATE,
    )
    with pytest.raises(ValidationError, match="same owner"):
        SessionCompileInput(
            owner_id="u1",
            session_id="esc1",
            timestamp="2024-01-02",
            chronological_rank=1,
            turns=(
                SessionTurnInput(
                    turn_id="esc1:turn:0",
                    turn_index=0,
                    role="seeker",
                    content="Hello",
                ),
            ),
            strictly_past_memory_table=(bad,),
        )
