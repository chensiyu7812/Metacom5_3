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
from metacom_pm.paper1.memory.me import extract_action_result_episodes, is_action_cue
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


def test_ms_and_me_candidates_never_include_the_current_or_later_session(real_users, real_targets):
    user = next(u for u in real_users if u.owner_id == "p1")
    target = _find_target(real_targets, "p1", "p1::p1_conv_10::")
    bundle = compile_candidate_bundle(user, target)

    for head in (Head.MP, Head.MS, Head.ME):
        for candidate in bundle[head]:
            rank = candidate.raw_descriptors["session_chronological_rank"]
            session_id = candidate.raw_descriptors["session_id"]
            assert rank < target.cutoff_rank
            assert session_id not in target.context_session_ids


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
        evidence_refs=(),
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


def test_me_pairs_action_with_the_next_seeker_turn_in_the_same_session():
    session = Session(
        owner_id="synthetic",
        session_id="s1",
        timestamp="2024-01-01",
        chronological_rank=0,
        emotion="neutral",
        topic="test",
        turns=(
            Turn(idx=1, role="seeker", content="I can't sleep at all."),
            Turn(idx=2, role="supporter", content="You could try a warm bath before bed."),
            Turn(idx=3, role="seeker", content="I tried that and it helped a little."),
            Turn(idx=4, role="supporter", content="That's great to hear."),
        ),
    )
    user = UserRecord(
        owner_id="synthetic", sessions=(session,), question_groups=(), summaries=(), subsequent_topics=()
    )
    episodes = extract_action_result_episodes(user)
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.action_turn.idx == 2
    assert episode.result_turn.idx == 3


def test_session_dataclass_never_carries_gold_summary_or_observation_fields():
    field_names = {f.name for f in dataclasses.fields(Session)}
    assert "summary" not in field_names
    assert "observation" not in field_names


def test_me_compiler_never_reads_target_cutoff_none_as_unlimited(real_users, real_targets):
    anomalous = next(t for t in real_targets if t.identity_anomaly is not None)
    user = next(u for u in real_users if u.owner_id == anomalous.owner_id)
    assert compile_me_candidates(user, anomalous) == ()
