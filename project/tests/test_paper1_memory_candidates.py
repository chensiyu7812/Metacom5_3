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
from metacom_pm.paper1.data.es_memeval import load_users
from metacom_pm.paper1.data.memory_source import (
    MemorySourceUser,
    Session,
    Turn,
    enumerate_targets,
    parse_memory_source_users,
)
from metacom_pm.paper1.memory.me import (
    ActionResultEpisode,
    extract_action_result_episodes,
    find_self_reported_action_result_spans,
)
from metacom_pm.paper1.memory.mp import ProfileDisclosure, is_profile_disclosure
from metacom_pm.paper1.memory.ms import SessionDocument

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return parse_memory_source_users(load_users(EVO_PATH))


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
    user = MemorySourceUser(
        owner_id="p1", sessions=(), question_groups=(), summaries=(), subsequent_topics=()
    )
    from metacom_pm.paper1.contracts import TaskType
    from metacom_pm.paper1.data.memory_source import Target

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


def _single_session_user(turns: tuple[Turn, ...]) -> MemorySourceUser:
    session = Session(
        owner_id="synthetic",
        session_id="s1",
        timestamp="2024-01-01",
        chronological_rank=0,
        emotion="neutral",
        topic="test",
        turns=turns,
    )
    return MemorySourceUser(
        owner_id="synthetic", sessions=(session,), question_groups=(), summaries=(), subsequent_topics=()
    )


def test_me_no_longer_treats_any_next_seeker_turn_as_the_result():
    # B7 regression: an earlier version accepted *any* next seeker turn as the
    # "observed result" of a preceding action-cue turn. B11 removed that
    # cross-turn pattern entirely (see memory/me.py docstring) -- a
    # supporter suggestion followed by an unrelated seeker turn must never
    # produce an episode, regardless of wording.
    user = _single_session_user(
        (
            Turn(idx=1, role="seeker", content="I can't sleep at all."),
            Turn(idx=2, role="supporter", content="You could try a warm bath before bed."),
            Turn(idx=3, role="seeker", content="Okay, thanks, I'll try that."),
        )
    )
    assert extract_action_result_episodes(user) == ()


def test_me_supporter_suggestion_never_pairs_with_a_later_seeker_turn():
    # B11: even a *qualifying* later seeker turn must not be paired with an
    # earlier supporter suggestion purely on temporal order -- there is no
    # cross-turn pattern left at all.
    user = _single_session_user(
        (
            Turn(idx=1, role="seeker", content="I can't sleep at all."),
            Turn(idx=2, role="supporter", content="You could try a warm bath before bed."),
            Turn(idx=3, role="seeker", content="Okay, I guess I could give that a go."),
            Turn(idx=4, role="seeker", content="I tried it and it helped a little."),
        )
    )
    episodes = extract_action_result_episodes(user)
    # only the self-contained turn-4 episode exists; nothing pairs turn 2 to turn 4
    assert len(episodes) == 1
    assert episodes[0].pattern == "self_reported_same_turn"
    assert episodes[0].action_turn.idx == episodes[0].result_turn.idx == 4


def test_me_real_corpus_false_positive_is_no_longer_matched():
    # The exact false positive found in the real corpus (p1, session
    # p1_conv_27, turns 15-16): "you might" used to trigger an action-cue
    # pattern that no longer exists; the next seeker turn only states an
    # intention, not an executed action or an observed result, so no
    # episode can be formed regardless.
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

    user = _single_session_user((Turn(idx=1, role="seeker", content=text),))
    assert extract_action_result_episodes(user) == ()


@pytest.mark.parametrize(
    "owner,session_id,turn_idx,text",
    [
        (
            "p1",
            "esc1172",
            4,
            "I've tried to bring it up with her indirectly, but it's an uncomfortable issue, "
            "you know? She is really upset, and I don't know whether it's my place to handle "
            "this kind of thing. It's more of an HR issue, but should I go to HR? Will that "
            "help, or just get me in trouble? I don't know.",
        ),
        (
            "p9",
            "p9_conv_13",
            7,
            "No, it's not. I tried to help, gave first aid until the ambulance came. But I "
            "keep replaying it in my head.",
        ),
        (
            "p14",
            "p14_conv_6",
            7,
            "I tried, but he seems so wrapped up in his work. We end up fighting instead of "
            "supporting each other.",
        ),
        (
            "p16",
            "p16_conv_7",
            5,
            "Well, I tried to bring up how I've been feeling undervalued and how it's "
            "affecting my motivation at work.",
        ),
    ],
)
def test_me_bare_help_or_work_word_regressions(owner, session_id, turn_idx, text):
    # B11 requirement 4: real corpus turns that must never become an ME
    # outcome -- a question ("Will that help?"), "help" as the infinitive
    # object of "tried to" (not a result clause), "work" as a possessed
    # noun ("his work"), and "work" as a location noun phrase ("at work").
    assert find_self_reported_action_result_spans(text) is None

    user = _single_session_user((Turn(idx=turn_idx, role="seeker", content=text),))
    assert extract_action_result_episodes(user) == ()


def test_me_esc1024_suggestions_never_pair_with_the_esc1172_hr_turn():
    # The exact real cross-session mispairing this project found and must
    # not reproduce: four sleep/relationship suggestions from session
    # esc1024 were previously paired to an unrelated HR-workplace turn in
    # session esc1172 purely because it was the nearest later qualifying
    # turn. With the cross-turn pattern removed, no pairing across any two
    # sessions can happen at all.
    esc1024 = Session(
        owner_id="p1",
        session_id="esc1024",
        timestamp="2024-06-30",
        chronological_rank=0,
        emotion="depression",
        topic="sleep",
        turns=(
            Turn(idx=1, role="seeker", content="please am not able to get sleep like 6 months now"),
            Turn(idx=14, role="supporter", content="Let try to ask them to be friends."),
            Turn(idx=15, role="supporter", content="or try sleeping piles to sleep ."),
        ),
    )
    esc1172 = Session(
        owner_id="p1",
        session_id="esc1172",
        timestamp="2024-07-10",
        chronological_rank=1,
        emotion="anxiety",
        topic="workplace harassment",
        turns=(
            Turn(
                idx=4,
                role="seeker",
                content=(
                    "I've tried to bring it up with her indirectly, but it's an uncomfortable "
                    "issue. Will that help, or just get me in trouble?"
                ),
            ),
        ),
    )
    user = MemorySourceUser(
        owner_id="p1",
        sessions=(esc1024, esc1172),
        question_groups=(),
        summaries=(),
        subsequent_topics=(),
    )
    episodes = extract_action_result_episodes(user)
    assert episodes == ()


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


# --- B13: candidate cache identity validation must fail closed -------------
#
# compile_mp/ms/me_candidates' optional disclosures/documents/episodes
# parameters may be a cache built elsewhere (features.build_census
# precomputes one per owner). A wrong cache -- built for a different owner,
# referencing a session that owner doesn't have, or stale against the
# user's current session data -- must raise immediately, not silently
# compile a plausible-looking but wrong candidate. `_require_owner_match`
# alone does not catch this: it only checks user.owner_id == target.owner_id,
# never the individual cache items.


def test_mp_compiler_rejects_a_cache_item_from_the_wrong_owner(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    bad_item = ProfileDisclosure(
        owner_id="p2",  # wrong owner
        session_id="esc1024",
        session_chronological_rank=0,
        turn=Turn(idx=1, role="seeker", content="i'm an alcoholic"),
        observed_at="2024-06-30",
    )
    with pytest.raises(ValueError, match="does not match user"):
        compile_mp_candidates(user, target, disclosures=(bad_item,))


def test_mp_compiler_rejects_a_cache_item_referencing_an_unknown_session(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    bad_item = ProfileDisclosure(
        owner_id="p1",
        session_id="this_session_does_not_exist",
        session_chronological_rank=0,
        turn=Turn(idx=1, role="seeker", content="i'm an alcoholic"),
        observed_at="2024-06-30",
    )
    with pytest.raises(ValueError, match="not one of"):
        compile_mp_candidates(user, target, disclosures=(bad_item,))


def test_mp_compiler_rejects_a_stale_rank_cache_item(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    real_session = user.session_by_id("esc1024")
    bad_item = ProfileDisclosure(
        owner_id="p1",
        session_id="esc1024",
        session_chronological_rank=real_session.chronological_rank + 7,  # stale
        turn=Turn(idx=1, role="seeker", content="i'm an alcoholic"),
        observed_at=real_session.timestamp,
    )
    with pytest.raises(ValueError, match="stale chronological_rank"):
        compile_mp_candidates(user, target, disclosures=(bad_item,))


def test_ms_compiler_rejects_a_cache_item_from_the_wrong_owner(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    bad_item = SessionDocument(
        owner_id="p2",
        session_id="esc1024",
        session_chronological_rank=0,
        observed_at="2024-06-30",
        emotion="neutral",
        topic="test",
        transcript="seeker: hello",
        turn_count=1,
    )
    with pytest.raises(ValueError, match="does not match user"):
        compile_ms_candidates(user, target, documents=(bad_item,))


def test_ms_compiler_rejects_a_stale_observed_at_cache_item(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    real_session = user.session_by_id("esc1024")
    bad_item = SessionDocument(
        owner_id="p1",
        session_id="esc1024",
        session_chronological_rank=real_session.chronological_rank,
        observed_at="1999-01-01",  # stale timestamp
        emotion="neutral",
        topic="test",
        transcript="seeker: hello",
        turn_count=1,
    )
    with pytest.raises(ValueError, match="stale observed_at"):
        compile_ms_candidates(user, target, documents=(bad_item,))


def _make_episode(**overrides) -> ActionResultEpisode:
    turn = Turn(idx=1, role="seeker", content="I tried meditation and it helped a bit.")
    defaults = dict(
        pattern="self_reported_same_turn",
        owner_id="p1",
        action_session_id="esc1024",
        action_session_chronological_rank=0,
        action_observed_at="2024-06-30",
        action_turn=turn,
        action_span=(0, 20),
        result_session_id="esc1024",
        result_session_chronological_rank=0,
        result_observed_at="2024-06-30",
        result_turn=turn,
        result_span=(20, len(turn.content)),
    )
    defaults.update(overrides)
    return ActionResultEpisode(**defaults)


def test_me_compiler_rejects_wrong_owner_on_the_action_side(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    with pytest.raises(ValueError, match="does not match user"):
        compile_me_candidates(user, target, episodes=(_make_episode(owner_id="p9"),))


def test_me_compiler_rejects_unknown_session_on_the_result_side(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    bad_episode = _make_episode(result_session_id="not_a_real_session")
    with pytest.raises(ValueError, match="not one of"):
        compile_me_candidates(user, target, episodes=(bad_episode,))


def test_me_compiler_rejects_stale_rank_on_the_action_side(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    real_session = user.session_by_id("esc1024")
    bad_episode = _make_episode(action_session_chronological_rank=real_session.chronological_rank + 3)
    with pytest.raises(ValueError, match="stale chronological_rank"):
        compile_me_candidates(user, target, episodes=(bad_episode,))


def test_candidate_cache_validation_applies_to_freshly_extracted_items_too(real_users, real_targets):
    # a sanity check that the validation logic itself does not reject
    # legitimate, freshly-extracted items -- it should be silent on the
    # normal path, only firing on genuine mismatches.
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    compile_mp_candidates(user, target)  # freshly extracted, no cache passed
    compile_ms_candidates(user, target)
    compile_me_candidates(user, target)
