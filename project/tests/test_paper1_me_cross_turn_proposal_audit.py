"""B29.3: high-precision cross-turn action->outcome proposal audit for ME."""

import json
from pathlib import Path

import pytest

from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session, Turn
from metacom_pm.paper1.features.me_cross_turn_proposal_audit import (
    MAX_ANAPHORA_TO_RESULT_GAP,
    MAX_TURN_IDX_WINDOW,
    build_me_cross_turn_proposal_report,
    build_me_cross_turn_proposal_rows,
    write_me_cross_turn_proposal_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return build_sanitized_runtime_users(load_raw_users(EVO_PATH))


def _user_with_sessions(*sessions: Session) -> MemorySourceUser:
    return MemorySourceUser(
        owner_id="synthetic", sessions=sessions, question_groups=(), summaries=(), subsequent_topics=()
    )


def _session(session_id: str, turns: tuple[Turn, ...], rank: int = 0) -> Session:
    return Session(session_id=session_id, timestamp="2024-01-01", chronological_rank=rank, turns=turns)


def test_real_corpus_yields_exactly_one_high_precision_candidate(real_users):
    rows = build_me_cross_turn_proposal_rows(real_users)
    assert len(rows) == 1
    row = rows[0]
    assert row.owner_id == "p16"
    assert "support" in row.shared_content_words


def test_primary_me_reported_unchanged_and_matches_real_compiler(real_users):
    report = build_me_cross_turn_proposal_report(real_users)
    assert report["primary_me_unchanged"]["unique_candidate_count"] == 3
    assert report["primary_me_unchanged"]["owners_with_candidates"] == 2


def test_synthetic_clean_candidate_passes_all_six_gates():
    session = _session(
        "s1",
        (
            Turn(idx=1, role="seeker", content="I've been so stressed about work lately."),
            Turn(idx=2, role="supporter", content="Have you considered seeking outside support?"),
            Turn(idx=3, role="seeker", content="Maybe."),
            Turn(idx=4, role="supporter", content="It could really make a difference."),
            Turn(idx=5, role="seeker", content="It helps knowing there's support available."),
        ),
    )
    user = _user_with_sessions(session)
    rows = build_me_cross_turn_proposal_rows((user,))
    assert len(rows) == 1
    row = rows[0]
    assert row.action_turn_idx == 2
    assert row.result_turn_idx == 5
    assert row.excluded_for_competing_antecedent is False
    assert "support" in row.shared_content_words


def test_synthetic_competing_antecedent_is_flagged_and_excluded():
    session = _session(
        "s1",
        (
            Turn(idx=1, role="supporter", content="Have you considered seeking outside support?"),
            Turn(idx=2, role="seeker", content="Not sure."),
            Turn(idx=3, role="supporter", content="Have you tried journaling about your support network?"),
            Turn(idx=4, role="seeker", content="It really helped, the support made a difference."),
        ),
    )
    user = _user_with_sessions(session)
    rows = build_me_cross_turn_proposal_rows((user,))
    assert len(rows) == 1
    row = rows[0]
    assert row.excluded_for_competing_antecedent is True
    assert len(row.competing_antecedent_turn_indices) >= 1

    report = build_me_cross_turn_proposal_report((user,))
    assert report["clean_proposal_count"] == 0
    assert report["competing_antecedent_excluded_count"] == 1


def test_synthetic_no_anaphora_is_rejected():
    session = _session(
        "s1",
        (
            Turn(idx=1, role="supporter", content="Have you considered seeking outside support?"),
            Turn(idx=2, role="seeker", content="Talking to my sister about support really helped this week."),
        ),
    )
    user = _user_with_sessions(session)
    rows = build_me_cross_turn_proposal_rows((user,))
    assert rows == ()


def test_synthetic_beyond_window_is_rejected():
    turns = [Turn(idx=1, role="supporter", content="Have you considered seeking outside support?")]
    for i in range(2, 2 + MAX_TURN_IDX_WINDOW + 2):
        turns.append(Turn(idx=i, role="seeker" if i % 2 == 0 else "supporter", content="Okay, noted."))
    turns.append(
        Turn(
            idx=2 + MAX_TURN_IDX_WINDOW + 2,
            role="seeker",
            content="It really helped, the support made a difference.",
        )
    )
    session = _session("s1", tuple(turns))
    user = _user_with_sessions(session)
    rows = build_me_cross_turn_proposal_rows((user,))
    assert rows == ()


def test_synthetic_anaphora_far_from_result_clause_is_rejected():
    # The anaphora word exists in the turn, but not immediately before the
    # result-relation clause -- must not qualify (the real precision gap
    # found and fixed during construction of this module).
    padding = "x" * (MAX_ANAPHORA_TO_RESULT_GAP + 50)
    session = _session(
        "s1",
        (
            Turn(idx=1, role="supporter", content="Have you considered seeking outside support?"),
            Turn(
                idx=2,
                role="seeker",
                content=f"That reminds me of something else. {padding} I guess support made things easier eventually.",
            ),
        ),
    )
    user = _user_with_sessions(session)
    rows = build_me_cross_turn_proposal_rows((user,))
    assert rows == ()


def test_synthetic_cross_session_pairing_is_never_attempted():
    session_a = _session(
        "s1", (Turn(idx=1, role="supporter", content="Have you considered seeking outside support?"),), rank=0
    )
    session_b = _session(
        "s2", (Turn(idx=1, role="seeker", content="It helps knowing there's support available."),), rank=1
    )
    user = _user_with_sessions(session_a, session_b)
    rows = build_me_cross_turn_proposal_rows((user,))
    assert rows == ()


def test_no_llm_judgment_or_pure_temporal_proximity_note_present(real_users):
    report = build_me_cross_turn_proposal_report(real_users)
    note = report["no_llm_judgment_note"].lower()
    assert "no llm" in note
    assert "temporal-proximity" in note or "temporal proximity" in note
    assert report["researcher_decision_required"] is True


def test_report_is_zero_outcome(real_users):
    report = build_me_cross_turn_proposal_report(real_users)
    assert report["outcome_calls"] == 0
    rendered = json.dumps(report).lower()
    for token in ("\"gold\"", "\"answer\":", "\"evidence\":"):
        assert token not in rendered


def test_manifest_write_roundtrip(tmp_path, real_users):
    rows = build_me_cross_turn_proposal_rows(real_users)
    report = build_me_cross_turn_proposal_report(real_users)
    paths = write_me_cross_turn_proposal_manifest(rows, report, tmp_path)

    lines = paths["rows"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(rows)
    for line in lines:
        parsed = json.loads(line)
        assert parsed["protocol"] == "pm-paper1-me-cross-turn-proposal-row-v1"

    written_report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert written_report["total_proposal_count"] == len(rows)
