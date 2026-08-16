import dataclasses
import hashlib
from pathlib import Path

import pytest

from metacom_pm.paper1.candidates import (
    compile_candidate_bundle,
    compile_me_candidates,
    compile_mp_candidates,
    compile_ms_candidates,
)
from metacom_pm.paper1.contracts import CandidateRecord, Head
from metacom_pm.paper1.data.es_memeval import (
    Session,
    Turn,
    UserRecord,
    enumerate_targets,
    load_users,
    parse_users,
)
from metacom_pm.paper1.memory.me import (
    extract_action_result_episodes,
    find_executed_result_span,
    find_self_reported_action_result_spans,
    is_action_cue,
)
from metacom_pm.paper1.memory.mp import is_profile_disclosure

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return parse_users(load_users(EVO_PATH))


@pytest.fixture(scope="module")
def real_targets(real_users):
    return enumerate_targets(real_users)


def _find_target(targets, owner_id: str, prefix: str):
    return next(t for t in targets if t.owner_id == owner_id and t.target_id.startswith(prefix))


def test_candidate_bundle_conforms_to_the_shared_contract(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    bundle = compile_candidate_bundle(user, target)

    assert set(bundle.keys()) == {Head.MP, Head.MS, Head.ME}
    for head, candidates in bundle.items():
        for candidate in candidates:
            assert isinstance(candidate, CandidateRecord)
            assert candidate.head is head
            assert candidate.content.strip() != ""
            assert candidate.lineage.owner_id == "p1"
            assert candidate.lineage.strict_past is True
            assert candidate.lineage.content_sha256 == hashlib.sha256(
                candidate.content.encode("utf-8")
            ).hexdigest()


def test_mp_ms_candidates_never_include_the_current_or_later_session(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    bundle = compile_candidate_bundle(user, target)

    for head in (Head.MP, Head.MS):
        for candidate in bundle[head]:
            rank = candidate.raw_descriptors["session_chronological_rank"]
            session_id = candidate.raw_descriptors["session_id"]
            assert rank < target.cutoff_rank
            assert session_id not in target.context_session_ids


def test_me_candidates_check_both_action_and_result_sessions_for_strict_past(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    bundle = compile_candidate_bundle(user, target)

    for candidate in bundle[Head.ME]:
        d = candidate.raw_descriptors
        assert d["action_session_chronological_rank"] < target.cutoff_rank
        assert d["result_session_chronological_rank"] < target.cutoff_rank
        assert d["action_session_id"] not in target.context_session_ids
        assert d["result_session_id"] not in target.context_session_ids
        # action must not be temporally after its own result
        assert d["action_session_chronological_rank"] <= d["result_session_chronological_rank"]


def test_ms_candidate_pool_excludes_the_current_session_itself(real_users, real_targets):
    # Regression test: an earlier version's cutoff_rank allowed a target's own
    # current session to appear as its own "strict past" MS candidate.
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::esc1024::")  # p1's very first session
    ms_candidates = compile_ms_candidates(user, target)
    assert all(c.raw_descriptors["session_id"] != "esc1024" for c in ms_candidates)
    # the first session ever has no strict-past material at all
    assert ms_candidates == ()


def test_owner_mismatch_between_user_and_target_raises():
    user = UserRecord(owner_id="p1", sessions=(), question_groups=(), summaries=(), subsequent_topics=())
    from metacom_pm.paper1.data.es_memeval import Target
    from metacom_pm.paper1.contracts import TaskType

    mismatched_target = Target(
        target_id="p2::esc1024::1",
        task_type=TaskType.QA,
        owner_id="p2",
        primary_group_key="p2::qa::esc1024",
        cutoff_rank=1,
        context_session_ids=("esc1024",),
    )
    with pytest.raises(ValueError, match="owner mismatch"):
        compile_mp_candidates(user, mismatched_target)


def test_target_with_identity_anomaly_compiles_zero_candidates_for_every_head(real_users, real_targets):
    anomalous = next(t for t in real_targets if t.identity_anomaly is not None)
    user = next(u for u in real_users if u.owner_id == anomalous.owner_id)
    bundle = compile_candidate_bundle(user, anomalous)
    assert all(candidates == () for candidates in bundle.values())


@pytest.mark.parametrize(
    "text,expected",
    [
        ("i'm an alcoholic", True),
        ("I'm a perfectionist. I over-analyze things.", True),
        ("My name is John and I live in Seattle", True),
        ("I'm 17 years old", True),
        ("I'm a bit worried today and nervous", False),
        ("I'm a mix of relieved and anxious", False),
        ("I'm a little embarrassed to do so", False),
        ("thanks so much, that helps", False),
    ],
)
def test_mp_self_disclosure_pattern_excludes_mood_filler(text, expected):
    assert is_profile_disclosure(text) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("You could try journaling every night", True),
        ("Why don't you talk to your manager about it", True),
        ("I recommend taking a short walk", True),
        ("That sounds really hard, I'm sorry", False),
    ],
)
def test_me_action_cue_detection(text, expected):
    assert is_action_cue(text) is expected


def _single_session_user(turns: tuple[Turn, ...]) -> UserRecord:
    session = Session(
        owner_id="synthetic",
        session_id="s1",
        timestamp="2024-01-01",
        chronological_rank=0,
        emotion="neutral",
        topic="test",
        turns=turns,
    )
    return UserRecord(
        owner_id="synthetic", sessions=(session,), question_groups=(), summaries=(), subsequent_topics=()
    )


def test_me_no_longer_treats_any_next_seeker_turn_as_the_result():
    # B7 regression: an earlier version accepted *any* next seeker turn as the
    # "observed result" of a preceding action-cue turn. A merely-acknowledging
    # or intention-stating next turn must no longer produce an episode.
    user = _single_session_user(
        (
            Turn(idx=1, role="seeker", content="I can't sleep at all."),
            Turn(idx=2, role="supporter", content="You could try a warm bath before bed."),
            Turn(idx=3, role="seeker", content="Okay, thanks, I'll try that."),
        )
    )
    assert extract_action_result_episodes(user) == ()


def test_me_real_corpus_false_positive_is_no_longer_matched():
    # The exact false positive found in the real corpus (p1, session
    # p1_conv_27, turns 15-16): "you might" triggers the action-cue pattern,
    # but the next seeker turn only states an intention, not an executed
    # action or an observed result.
    user = _single_session_user(
        (
            Turn(
                idx=15,
                role="supporter",
                content=(
                    "Staying open sounds like a strong foundation to build on. And your "
                    "blog is such a great platform to share your experiences. Have you "
                    "already thought about what you might write next?"
                ),
            ),
            Turn(
                idx=16,
                role="seeker",
                content=(
                    "I'm thinking about exploring the theme of resilience and how art can "
                    "be healing, especially how painting has been for me. It's a topic I'm "
                    "passionate about."
                ),
            ),
        )
    )
    assert is_action_cue(user.sessions[0].turns[0].content) is True
    assert extract_action_result_episodes(user) == ()


def test_me_matches_explicit_tried_and_it_helped_or_did_not_help():
    positive = "I tried a warm bath before bed and it helped a lot."
    negative = "I tried a warm bath before bed but it didn't help at all."
    for text in (positive, negative):
        spans = find_self_reported_action_result_spans(text)
        assert spans is not None
        action_span, result_span = spans
        assert "tried" in text[action_span[0] : action_span[1]].lower()
        assert "help" in text[result_span[0] : result_span[1]].lower()


def test_me_action_with_no_stated_outcome_is_a_negative_example():
    # "tried" is present but no outcome is ever stated -- must not qualify.
    text = "I tried to just sit and let myself write without pressure, but the words still didn't come."
    assert find_self_reported_action_result_spans(text) is None
    assert find_executed_result_span(text) is None

    user = _single_session_user(
        (
            Turn(idx=1, role="supporter", content="You could try journaling for ten minutes."),
            Turn(idx=2, role="seeker", content=text),
        )
    )
    assert extract_action_result_episodes(user) == ()


def test_me_self_reported_same_turn_splits_into_two_char_spans():
    user = _single_session_user(
        (Turn(idx=1, role="seeker", content="I tried meditation and it helped a bit."),)
    )
    episodes = extract_action_result_episodes(user)
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.pattern == "self_reported_same_turn"
    assert episode.action_turn.idx == episode.result_turn.idx == 1
    assert episode.action_span != episode.result_span
    assert episode.action_span[1] == episode.result_span[0]
    assert "tried" in episode.action_text.lower()
    assert "help" in episode.result_text.lower()


def test_me_supporter_suggestion_then_qualifying_later_seeker_turn():
    user = _single_session_user(
        (
            Turn(idx=1, role="seeker", content="I can't sleep at all."),
            Turn(idx=2, role="supporter", content="You could try a warm bath before bed."),
            Turn(idx=3, role="seeker", content="Okay, I guess I could give that a go."),
            Turn(idx=4, role="seeker", content="I tried it and it helped a little."),
        )
    )
    episodes = extract_action_result_episodes(user)
    # turn 4 qualifies on its own (pattern 1) *and* as the nearest qualifying
    # result for the turn-2 suggestion (pattern 2) -- both are legitimate,
    # independently-constructed episodes, not a duplicate.
    by_pattern = {e.pattern: e for e in episodes}
    assert set(by_pattern) == {"self_reported_same_turn", "supporter_suggestion_then_reported_result"}

    cross_turn = by_pattern["supporter_suggestion_then_reported_result"]
    assert cross_turn.action_turn.idx == 2
    assert cross_turn.result_turn.idx == 4  # skips the non-qualifying turn 3

    same_turn = by_pattern["self_reported_same_turn"]
    assert same_turn.action_turn.idx == same_turn.result_turn.idx == 4


def test_me_lineage_carries_both_span_ids_and_offsets_or_hashes():
    user = _single_session_user(
        (Turn(idx=1, role="seeker", content="I tried meditation and it helped a bit."),)
    )
    episode = extract_action_result_episodes(user)[0]
    assert len(episode.source_record_ids) == 2
    assert episode.action_span_sha256 != episode.result_span_sha256
    assert all(len(h) == 64 for h in (episode.action_span_sha256, episode.result_span_sha256))


def test_session_dataclass_never_carries_gold_summary_or_observation_fields():
    field_names = {f.name for f in dataclasses.fields(Session)}
    assert "summary" not in field_names
    assert "observation" not in field_names


def test_me_compiler_never_reads_target_cutoff_none_as_unlimited(real_users, real_targets):
    anomalous = next(t for t in real_targets if t.identity_anomaly is not None)
    user = next(u for u in real_users if u.owner_id == anomalous.owner_id)
    assert compile_me_candidates(user, anomalous) == ()
