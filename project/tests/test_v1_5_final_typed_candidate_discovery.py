from metacom_pm.contracts import MemoryItem, MemorySource
from metacom_pm.v1_5_candidate_discovery import (
    FINAL_TYPED_CANDIDATE_DISCOVERY_PROTOCOL,
    discover_final_typed_memory_candidates,
    final_typed_content_match_level,
)
from metacom_pm.v1_5_strategy_rag_repair import (
    pre_pm_strategy_candidate_family,
    pre_pm_strategy_retrieval_query,
    effect_study_observable_flags,
    rank_pre_pm_strategy_candidates,
    repair_v2_rank_applicable_cards,
)
from metacom_pm.io import iter_jsonl
from pathlib import Path


def _queries(text: str):
    return {source: text for source in MemorySource}


def test_final_typed_discovery_filters_function_word_only_matches() -> None:
    ids = {
        MemorySource.MP: "mem_aaaaaaaaaaaaaaaaaaaa",
        MemorySource.MS: "mem_bbbbbbbbbbbbbbbbbbbb",
        MemorySource.ME: "mem_cccccccccccccccccccc",
    }
    items = [
        MemoryItem(
            memory_id=ids[source],
            source=source,
            created_session=1,
            text="The user was there and it was something they had.",
        )
        for source in MemorySource
    ]
    result = discover_final_typed_memory_candidates(
        queries=_queries("I am here and I want to talk about deadlines."),
        items=items,
        source_metadata={
            "mem_aaaaaaaaaaaaaaaaaaaa": {"mp_subtype": "MP_PROFILE"},
            "mem_bbbbbbbbbbbbbbbbbbbb": {
                "summary_origin": "supplied_strictly_prior_summary"
            },
            "mem_cccccccccccccccccccc": {
                "me_subtype_hint": "ME_CONTEXT_EVENT"
            },
        },
        session_index=2,
    )
    assert all(not candidate.selected_items for candidate in result.values())
    assert all(
        candidate.descriptor["protocol"]
        == FINAL_TYPED_CANDIDATE_DISCOVERY_PROTOCOL
        for candidate in result.values()
    )


def test_final_typed_discovery_prefers_reusable_me_within_content_tier() -> None:
    items = [
        MemoryItem(
            memory_id="mem_11111111111111111111",
            source=MemorySource.ME,
            created_session=2,
            text="The team deadline felt uncertain and difficult.",
        ),
        MemoryItem(
            memory_id="mem_22222222222222222222",
            source=MemorySource.ME,
            created_session=1,
            text="I wrote one team deadline question and it helped.",
        ),
    ]
    result = discover_final_typed_memory_candidates(
        queries=_queries("The team deadline is difficult."),
        items=items,
        source_metadata={
            "mem_11111111111111111111": {
                "me_subtype_hint": "ME_CONTEXT_EVENT"
            },
            "mem_22222222222222222222": {
                "me_subtype_hint": "ME_REUSABLE_OUTCOME"
            },
        },
        session_index=3,
    )
    assert (
        result[MemorySource.ME].selected_items[0].memory_id
        == "mem_22222222222222222222"
    )


def test_final_typed_content_match_ignores_support_boilerplate() -> None:
    assert (
        final_typed_content_match_level(
            "I want to talk about my deadlines.",
            "The user discussed feelings about exercise.",
        )
        == 0.0
    )


def _strategy_cards():
    root = Path(__file__).resolve().parents[1]
    return list(
        iter_jsonl(
            root
            / "outputs/pm_v1_5_strategy_bank_v4_final_v1"
            / "strategy_cards_v4_final.jsonl"
        )
    )


def test_final_rs_recognizes_optional_single_idea_request() -> None:
    current = "Can you give me one small optional idea for dealing with social anxiety?"
    dialogue = [{"speaker": "seeker", "content": current}]
    flags = effect_study_observable_flags(
        current_user_text=current,
        recent_user_text=current,
        visible_dialogue=dialogue,
    )
    assert flags["advice_welcome"] is True
    assert flags["low_burden"] is True
    ranked = repair_v2_rank_applicable_cards(
        query=current,
        current_user_text=current,
        recent_user_text=current,
        visible_dialogue=dialogue,
        cards=_strategy_cards(),
    )
    assert ranked
    assert ranked[0]["strategy_family"] == "Providing Suggestions"


def test_final_rs_reflection_request_resolves_recent_explicit_feeling() -> None:
    current = "Help me put this feeling into words."
    recent = "I'm still struggling to find inspiration. It's just so hard. " + current
    dialogue = [
        {
            "speaker": "seeker",
            "content": "I'm still struggling to find inspiration. It's just so hard.",
        },
        {"speaker": "seeker", "content": current},
    ]
    flags = effect_study_observable_flags(
        current_user_text=current,
        recent_user_text=recent,
        visible_dialogue=dialogue,
    )
    assert flags["reflection_welcome"] is True
    assert flags["emotion_visible"] is True
    ranked = repair_v2_rank_applicable_cards(
        query=recent,
        current_user_text=current,
        recent_user_text=recent,
        visible_dialogue=dialogue,
        cards=_strategy_cards(),
    )
    assert ranked
    assert ranked[0]["strategy_family"] == "Reflection of feelings"


def test_pre_pm_ranker_defers_applicability_but_keeps_state_hard_off() -> None:
    current = "I am overwhelmed. I only want you to listen; no advice."
    dialogue = [{"speaker": "seeker", "content": current}]
    ranked = rank_pre_pm_strategy_candidates(
        query=current,
        current_user_text=current,
        recent_user_text=current,
        visible_dialogue=dialogue,
        cards=_strategy_cards(),
    )
    assert ranked
    assert all(
        row["applicability_reasons"] == ["DEFERRED_TO_STEP1_PM"]
        for row in ranked
    )

    closing = "Thanks for listening."
    assert rank_pre_pm_strategy_candidates(
        query=closing,
        current_user_text=closing,
        recent_user_text=closing,
        visible_dialogue=[{"speaker": "seeker", "content": closing}],
        cards=_strategy_cards(),
    ) == []


def test_pre_pm_query_expansion_identifies_move_type_without_deciding_use() -> None:
    cases = {
        "Several parts feel tangled, and I cannot tell which one is driving the pressure.": "focused question",
        "The reaction is hard to name, and I want help finding accurate words for it.": "reflect",
        "I want something manageable and am open to advice.": "optional concrete microstep",
        "I need space to say what this is like before deciding what to do.": "open invitation",
        "The last focused question already identified it, so do not repeat it.": "focused question",
    }
    for current, expected in cases.items():
        expanded = pre_pm_strategy_retrieval_query(
            query="base query",
            current_user_text=current,
            recent_user_text=current,
        ).lower()
        assert expected in expanded
        assert "applicable" not in expanded
        assert "benefit" not in expanded


def test_pre_pm_family_selection_is_content_routing_not_on_off() -> None:
    assert (
        pre_pm_strategy_candidate_family(
            "Several parts feel tangled, and I cannot tell which one drives the pressure."
        )
        == "Question"
    )
    assert (
        pre_pm_strategy_candidate_family(
            "The reaction is hard to name, and I need accurate words for it."
        )
        == "Reflection of feelings"
    )
    assert (
        pre_pm_strategy_candidate_family(
            "I need space to say what this is like before deciding what to do."
        )
        == "Restatement or Paraphrasing"
    )
    # Redundant cases deliberately still retrieve the already-used family;
    # Step 1, not retrieval, must turn that candidate off.
    assert (
        pre_pm_strategy_candidate_family(
            "That focused question already identified it, so do not repeat it."
        )
        == "Question"
    )
