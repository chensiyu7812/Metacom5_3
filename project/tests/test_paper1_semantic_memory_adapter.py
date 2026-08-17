from __future__ import annotations

import pytest

from metacom_pm.io import sha256_text
from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.memory_source import (
    MemorySourceUser,
    Session,
    Target,
    Turn,
)
from metacom_pm.paper1.features.zero_outcome_census import (
    build_semantic_census,
    build_semantic_eligible_pool,
)
from metacom_pm.paper1.features.feature_readiness_audit import (
    SEMANTIC_FEATURE_INVENTORY,
    build_semantic_feature_readiness_rows,
    summarize_semantic_feature_readiness,
)
from metacom_pm.paper1.semantic_memory.candidate_adapter import (
    materialize_memory_candidates,
)
from metacom_pm.paper1.semantic_memory.contracts import (
    AcceptedSemanticMemoryUnit,
    CandidateSourceUse,
    GroundedSupportingSpan,
    LinkedPriorMemoryRelation,
    MEHistoricalOutcomeType,
    MPProfileFieldType,
    MSContinuityType,
    MemoryClass,
    MemorySubtype,
    PriorMemoryRelationType,
    TemporalStatus,
)
from metacom_pm.paper1.semantic_memory.renderer import (
    RENDERER_CODE_SHA256,
    RENDERER_SHA256,
    RENDERER_VERSION,
)
from metacom_pm.paper1.semantic_memory.versioning import resolve_memory_versions

HASH = "1" * 64


def _mp_unit(
    memory_id: str,
    *,
    rank: int,
    links: tuple[LinkedPriorMemoryRelation, ...] = (),
) -> AcceptedSemanticMemoryUnit:
    content = "Profile fact [location]: The seeker lives in Kyoto."
    return AcceptedSemanticMemoryUnit(
        memory_id=memory_id,
        owner_id="u1",
        source_session_id=f"s{rank}",
        source_session_rank=rank,
        source_turn_ids=(f"s{rank}:turn:1",),
        memory_class=MemoryClass.MP,
        memory_subtype=MemorySubtype.MP_LOCATION,
        normalized_memory="The seeker lives in Kyoto.",
        supporting_spans=(
            GroundedSupportingSpan(
                span_id=f"span-{memory_id}",
                turn_id=f"s{rank}:turn:1",
                exact_text="I live in Kyoto.",
                start_char=0,
                end_char=16,
            ),
        ),
        entities=("Kyoto",),
        timestamp=f"2024-01-{rank + 1:02d}",
        timestamp_status=TemporalStatus.CURRENT_STATE,
        candidate_source_use=CandidateSourceUse.CANDIDATE_SOURCE,
        linked_prior_memory_ids=tuple(link.memory_id for link in links),
        linked_prior_relations=links,
        profile_field_type=MPProfileFieldType.LOCATION,
        rendered_candidate_content=content,
        rendered_candidate_content_sha256=sha256_text(content),
        compiler_version="compiler-v6-test",
        renderer_version=RENDERER_VERSION,
        renderer_sha256=RENDERER_SHA256,
        renderer_code_sha256=RENDERER_CODE_SHA256,
        verifier_method="test-verifier",
        provider="test-provider",
        region="test-region",
        model="test-model",
        enable_thinking=False,
        extractor_prompt_sha256=HASH,
        verifier_prompt_sha256=HASH,
        extractor_schema_sha256=HASH,
        verifier_schema_sha256=HASH,
        source_sha256=HASH,
        prior_memory_table_sha256=HASH,
        extractor_request_sha256=HASH,
        extractor_response_sha256=HASH,
        verifier_request_sha256=HASH,
        verifier_response_sha256=HASH,
    )


def _uncertain_ms_unit(memory_id: str, *, rank: int) -> AcceptedSemanticMemoryUnit:
    content = "Continuity fact [state; source_status=uncertain]: The seeker felt uneasy."
    return AcceptedSemanticMemoryUnit(
        memory_id=memory_id,
        owner_id="u1",
        source_session_id=f"s{rank}",
        source_session_rank=rank,
        source_turn_ids=(f"s{rank}:turn:1",),
        memory_class=MemoryClass.MS,
        memory_subtype=MemorySubtype.MS_STATE,
        normalized_memory="The seeker felt uneasy.",
        supporting_spans=(
            GroundedSupportingSpan(
                span_id=f"span-{memory_id}",
                turn_id=f"s{rank}:turn:1",
                exact_text="I may still feel uneasy.",
                start_char=0,
                end_char=23,
            ),
        ),
        timestamp=f"2024-01-{rank + 1:02d}",
        timestamp_status=TemporalStatus.UNCERTAIN,
        candidate_source_use=CandidateSourceUse.STATE_TABLE_ONLY,
        continuity_type=MSContinuityType.STATE,
        rendered_candidate_content=content,
        rendered_candidate_content_sha256=sha256_text(content),
        compiler_version="compiler-v6-test",
        renderer_version=RENDERER_VERSION,
        renderer_sha256=RENDERER_SHA256,
        renderer_code_sha256=RENDERER_CODE_SHA256,
        verifier_method="test-verifier",
        provider="test-provider",
        region="test-region",
        model="test-model",
        enable_thinking=False,
        extractor_prompt_sha256=HASH,
        verifier_prompt_sha256=HASH,
        extractor_schema_sha256=HASH,
        verifier_schema_sha256=HASH,
        source_sha256=HASH,
        prior_memory_table_sha256=HASH,
        extractor_request_sha256=HASH,
        extractor_response_sha256=HASH,
        verifier_request_sha256=HASH,
        verifier_response_sha256=HASH,
    )


def _me_unit(memory_id: str, *, rank: int) -> AcceptedSemanticMemoryUnit:
    content = (
        "Past action: The seeker tried journaling. "
        "User-observed outcome [negative]: The seeker felt worse afterward."
    )
    action_span = GroundedSupportingSpan(
        span_id=f"action-{memory_id}",
        turn_id=f"s{rank}:turn:1",
        exact_text="I tried journaling",
        start_char=0,
        end_char=18,
    )
    outcome_span = GroundedSupportingSpan(
        span_id=f"outcome-{memory_id}",
        turn_id=f"s{rank}:turn:1",
        exact_text="but I felt worse afterward",
        start_char=19,
        end_char=45,
    )
    return AcceptedSemanticMemoryUnit(
        memory_id=memory_id,
        owner_id="u1",
        source_session_id=f"s{rank}",
        source_session_rank=rank,
        source_turn_ids=(f"s{rank}:turn:1",),
        memory_class=MemoryClass.ME,
        memory_subtype=MemorySubtype.ME_NEGATIVE,
        normalized_memory="The seeker tried journaling and felt worse afterward.",
        supporting_spans=(action_span, outcome_span),
        timestamp=f"2024-01-{rank + 1:02d}",
        timestamp_status=TemporalStatus.COMPLETED,
        candidate_source_use=CandidateSourceUse.CANDIDATE_SOURCE,
        historical_outcome_type=MEHistoricalOutcomeType.NEGATIVE,
        action="The seeker tried journaling.",
        observed_outcome="The seeker felt worse afterward.",
        rendered_candidate_content=content,
        rendered_candidate_content_sha256=sha256_text(content),
        action_span_ids=(action_span.span_id,),
        observed_outcome_span_ids=(outcome_span.span_id,),
        compiler_version="compiler-v6-test",
        renderer_version=RENDERER_VERSION,
        renderer_sha256=RENDERER_SHA256,
        renderer_code_sha256=RENDERER_CODE_SHA256,
        verifier_method="test-verifier",
        provider="test-provider",
        region="test-region",
        model="test-model",
        enable_thinking=False,
        extractor_prompt_sha256=HASH,
        verifier_prompt_sha256=HASH,
        extractor_schema_sha256=HASH,
        verifier_schema_sha256=HASH,
        source_sha256=HASH,
        prior_memory_table_sha256=HASH,
        extractor_request_sha256=HASH,
        extractor_response_sha256=HASH,
        verifier_request_sha256=HASH,
        verifier_response_sha256=HASH,
    )


def test_newer_superseding_unit_mechanically_deactivates_old_version() -> None:
    old = _mp_unit("m-old", rank=0)
    new = _mp_unit(
        "m-new",
        rank=1,
        links=(
            LinkedPriorMemoryRelation(
                memory_id="m-old", relation=PriorMemoryRelationType.SUPERSEDES
            ),
        ),
    )
    states = {
        row.memory_id: row
        for row in resolve_memory_versions(
            (old, new), target_owner_id="u1", target_session_rank=2
        )
    }
    assert states["m-old"].active_for_candidate is False
    assert states["m-old"].invalidated_by_memory_id == "m-new"
    assert states["m-old"].mechanical_reasons == ("newer_supersedes",)
    assert states["m-new"].active_for_candidate is True


def test_coreference_does_not_change_candidate_activity() -> None:
    old = _mp_unit("m-old", rank=0)
    new = _mp_unit(
        "m-new",
        rank=1,
        links=(
            LinkedPriorMemoryRelation(
                memory_id="m-old", relation=PriorMemoryRelationType.COREFERS_WITH
            ),
        ),
    )
    states = resolve_memory_versions(
        (old, new), target_owner_id="u1", target_session_rank=2
    )
    assert all(row.active_for_candidate for row in states)


def test_version_relation_must_point_to_strictly_earlier_memory() -> None:
    earlier = _mp_unit(
        "m-earlier",
        rank=0,
        links=(
            LinkedPriorMemoryRelation(
                memory_id="m-later", relation=PriorMemoryRelationType.UPDATES
            ),
        ),
    )
    later = _mp_unit("m-later", rank=1)
    with pytest.raises(ValueError, match="not strictly earlier"):
        resolve_memory_versions(
            (earlier, later), target_owner_id="u1", target_session_rank=2
        )


def test_candidate_adapter_uses_rendered_content_and_direct_raw_field() -> None:
    old = _mp_unit("m-old", rank=0)
    new = _mp_unit(
        "m-new",
        rank=1,
        links=(
            LinkedPriorMemoryRelation(
                memory_id="m-old", relation=PriorMemoryRelationType.UPDATES
            ),
        ),
    )
    candidates = materialize_memory_candidates(
        (old, new),
        target_owner_id="u1",
        target_session_rank=2,
        token_counter=lambda text: len(text.split()),
    )
    assert candidates[Head.MS] == () and candidates[Head.ME] == ()
    assert len(candidates[Head.MP]) == 1
    candidate = candidates[Head.MP][0]
    assert candidate.candidate_id == "semantic_m-new"
    assert candidate.content == new.rendered_candidate_content
    assert candidate.raw_descriptors == {
        "session_chronological_rank": 1,
        "mp_profile_field_type": "location",
    }
    assert candidate.lineage.strict_past is True
    assert "m-old" not in candidate.lineage.source_record_ids


def test_me_adapter_materializes_outcome_type_without_reparsing_prose() -> None:
    unit = _me_unit("me1", rank=0)
    candidate = materialize_memory_candidates(
        (unit,),
        target_owner_id="u1",
        target_session_rank=1,
        token_counter=lambda text: len(text.split()),
    )[Head.ME][0]
    assert candidate.content == unit.rendered_candidate_content
    assert candidate.raw_descriptors == {
        "session_chronological_rank": 0,
        "me_historical_outcome_type": "negative",
    }


def test_uncertain_ms_is_retained_for_state_table_but_not_candidate() -> None:
    unit = _uncertain_ms_unit("m-uncertain", rank=0)
    states = resolve_memory_versions(
        (unit,), target_owner_id="u1", target_session_rank=1
    )
    assert states[0].active_for_candidate is False
    candidates = materialize_memory_candidates(
        (unit,),
        target_owner_id="u1",
        target_session_rank=1,
        token_counter=lambda text: len(text.split()),
    )
    assert all(not rows for rows in candidates.values())


def test_accepted_unit_rejects_rendered_content_hash_mismatch() -> None:
    payload = _mp_unit("m1", rank=0).model_dump(mode="json")
    payload["rendered_candidate_content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="content hash mismatch"):
        AcceptedSemanticMemoryUnit.model_validate(payload)


def test_semantic_census_uses_formal_adapter_not_legacy_regex_compiler() -> None:
    user = MemorySourceUser(
        owner_id="u1",
        sessions=(
            Session(
                session_id="s0",
                timestamp="2024-01-01",
                chronological_rank=0,
                turns=(Turn(idx=1, role="seeker", content="I live in Kyoto."),),
            ),
            Session(
                session_id="s1",
                timestamp="2024-01-02",
                chronological_rank=1,
                turns=(Turn(idx=1, role="seeker", content="I still live there."),),
            ),
        ),
        question_groups=(),
        summaries=(),
        subsequent_topics=(),
    )
    target = Target(
        target_id="t1",
        task_type=TaskType.QA,
        owner_id="u1",
        primary_group_key="u1::qa::t1",
        cutoff_rank=2,
        visible_query_text="Where does the user live?",
    )
    unit = _mp_unit("m1", rank=0)
    pool = build_semantic_eligible_pool((user,), (unit,))
    assert [(row.head, row.eligible_candidate_count) for row in pool] == [
        (Head.MP, 1),
        (Head.MS, 0),
        (Head.ME, 0),
    ]
    rows = build_semantic_census((user,), (target,), (unit,))
    by_head = {row.head: row for row in rows}
    assert by_head[Head.MP].candidate_count == 1
    assert by_head[Head.MS].candidate_count == 0
    assert by_head[Head.ME].candidate_count == 0

    readiness = build_semantic_feature_readiness_rows((user,), (target,), (unit,))
    summary = summarize_semantic_feature_readiness(
        readiness,
        users=(user,),
        accepted_units=(unit,),
        artifact_name="offline-test.jsonl",
        artifact_sha256=HASH,
    )
    assert summary["protocol"].endswith("v3")
    assert summary["outcome_calls"] == 0
    inventory = {item["canonical_name"]: item for item in SEMANTIC_FEATURE_INVENTORY}
    assert inventory["mp_profile_field_type"]["status"] == "IMPLEMENTED"
    assert inventory["me_historical_outcome_type"]["status"] == "IMPLEMENTED"
    assert inventory["embedding_similarity"]["status"] == "NOT_IMPLEMENTED"
    assert summary["semantic_compiler_source"]["artifact_sha256"] == HASH
    assert summary["categorical_feature_coverage"]["mp_profile_field_type"][
        "missing_values"
    ] == 0
    semantic_rows = [row.to_manifest_row() for row in readiness]
    assert {row["candidate_source"] for row in semantic_rows} == {
        "accepted_semantic_memory_v6"
    }
    assert {row["protocol"] for row in semantic_rows} == {
        "pm-paper1-semantic-memory-feature-readiness-row-v3"
    }
