from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from metacom_pm.contracts import StrategyCard
from metacom_pm.v1_5_paper1_rank1 import (
    rank_me,
    rank_mp,
    rank_ms_from_vectors,
    rank_rs,
    validate_rank1_rows,
)


ROOT = Path(__file__).resolve().parents[1]
CARDS = [
    StrategyCard(**json.loads(line))
    for line in (ROOT / "data/strategy/strategy_cards_v1_5_minimal.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip()
]


def _state(text: str = "My manager makes work difficult.") -> dict:
    return {
        "dataset": "EvoEmo",
        "state_id": "evo::p1::s2::seeker_turn::1",
        "runtime_owner_key": "evo::p1",
        "split_group_key": "evo_component::p1",
        "outer_fold": 1,
        "source_session_index": 2,
        "current_user_text": text,
        "visible_current_session_dialogue": [
            {"speaker": "seeker", "content": text, "raw_turn_index": 1}
        ],
    }


def _candidate(
    candidate_id: str,
    component: str,
    text: str,
    *,
    session: int = 1,
    owner: str = "evo::p1",
    field: str | None = None,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "component": component,
        "runtime_owner_key": owner,
        "available_after_session_index": session,
        "literal_text": text,
        "source_session_id": f"s{session}",
        "source_turn_index": 1,
        "profile_field": field,
    }


def test_mp_uses_applicability_scope_not_hidden_value_repetition() -> None:
    rows = [
        _candidate("mp_job", "MP", "job: office worker", session=0, field="job"),
        _candidate("mp_age", "MP", "age: 33", session=0, field="age"),
    ]
    selected = rank_mp(_state(), rows)
    assert selected["candidate_present"] is True
    assert selected["actual_rank1_id"] == "mp_job"
    assert selected["retrieval_observations"]["profile_field"] == "job"


def test_mp_has_natural_off_when_no_profile_scope_matches() -> None:
    rows = [_candidate("mp_job", "MP", "job: teacher", session=0, field="job")]
    selected = rank_mp(_state("I feel lonely tonight."), rows)
    assert selected["candidate_present"] is False
    assert selected["hard_off_reason"] == "no_profile_scope_match"


def test_ms_bge_rank1_is_strict_past_same_owner_and_deterministic() -> None:
    state = _state("I am worried about my exams.")
    candidates = [
        _candidate("ms_old", "MS", "Old school stress", session=1),
        _candidate("ms_future", "MS", "Future school stress", session=2),
        _candidate("ms_other", "MS", "Other owner", session=1, owner="evo::p2"),
    ]
    selected = rank_ms_from_vectors(
        state,
        candidates,
        query_vector=np.array([1.0, 0.0]),
        candidate_vectors={
            "ms_old": np.array([0.8, 0.2]),
            "ms_future": np.array([1.0, 0.0]),
            "ms_other": np.array([1.0, 0.0]),
        },
    )
    assert selected["actual_rank1_id"] == "ms_old"
    assert selected["strict_past_pool_count"] == 1


def test_me_never_promotes_rank2_after_invalid_actual_rank1() -> None:
    state = _state("Writing helped me again.")
    candidates = [
        _candidate("me_invalid", "ME", "Writing helped me", session=1),
        _candidate(
            "me_valid",
            "ME",
            "I tried writing and it helped me feel calmer.",
            session=1,
        ),
    ]
    selected = rank_me(state, candidates)
    assert selected["candidate_present"] is False
    assert selected["hard_off_reason"] == "actual_rank1_compiler_invalid_no_rank2"
    assert selected["retrieval_observations"]["rank2_promoted"] is False


def test_rs_returns_shared_candidate_or_explicit_hard_off() -> None:
    normal = rank_rs(_state("I don't know where to start, something bothers me."), CARDS)
    assert normal["candidate_present"] is True
    assert normal["retrieval_observations"]["move_id"] == (
        "AM01_invite_open_expression"
    )

    stopped = rank_rs(_state("Please stop this conversation now."), CARDS)
    assert stopped["candidate_present"] is False
    assert stopped["hard_off_reason"] == "explicit_stop"


def test_validator_rejects_future_or_wrong_owner_candidate() -> None:
    state = _state()
    candidate = _candidate("mp_job", "MP", "job: teacher", session=2, field="job")
    row = rank_mp(state, [{**candidate, "available_after_session_index": 0}])
    # Point the result at a structurally future catalog row.
    report = validate_rank1_rows(
        esconv_states=[],
        evo_states=[state],
        candidates=[candidate],
        rows=[
            row,
            {**row, "component": "MS", "candidate_present": False, "actual_rank1_id": None},
            {**row, "component": "ME", "candidate_present": False, "actual_rank1_id": None},
            {**row, "component": "RS", "candidate_present": False, "actual_rank1_id": None},
        ],
    )
    assert report["checks"]["present_memory_candidates_are_strictly_past"] is False


def test_completed_p1b_materializer_fails_closed_before_rerun() -> None:
    script = (
        ROOT
        / "scripts/v1_5/179l_materialize_paper1_p1b_actual_rank1_v1_5.py"
    )
    phase = (
        ROOT
        / "data/pm_v1_5_contracts/paper1_p1b_actual_rank1_materialization_phase_v1.json"
    )
    result = subprocess.run(
        [sys.executable, str(script), "--phase-manifest", str(phase)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "P1B actual Rank-1 materialization is not active" in result.stderr
