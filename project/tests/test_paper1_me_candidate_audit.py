"""B20: per-candidate ME construct audit deliverable."""

import json
from pathlib import Path

import pytest

from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session, Turn
from metacom_pm.paper1.features.me_candidate_audit import (
    LINKAGE_RULE_DESCRIPTIONS,
    MeCandidateAuditRow,
    build_me_candidate_audit_report,
    build_me_candidate_audit_rows,
)

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return build_sanitized_runtime_users(load_raw_users(EVO_PATH))


def test_audit_rows_match_the_production_compilers_surviving_candidate_count(real_users):
    rows = build_me_candidate_audit_rows(real_users)
    assert len(rows) == 3
    owners = sorted(r.owner_id for r in rows)
    assert owners == ["p12", "p12", "p4"]


def test_every_row_carries_action_span_result_span_linkage_rule_and_identity(real_users):
    rows = build_me_candidate_audit_rows(real_users)
    for row in rows:
        assert isinstance(row, MeCandidateAuditRow)
        assert row.owner_id
        assert row.session_id
        assert isinstance(row.turn_idx, int)
        assert row.pattern == "self_reported_same_turn"
        assert row.linkage_rule == LINKAGE_RULE_DESCRIPTIONS["self_reported_same_turn"]
        assert row.action_span[0] < row.action_span[1]
        assert row.result_span[0] < row.result_span[1]
        assert row.action_text.strip() != ""
        assert row.result_text.strip() != ""
        assert len(row.action_span_sha256) == 64
        assert len(row.result_span_sha256) == 64
        # action and result must not be the exact same span
        assert row.action_span != row.result_span


def test_audit_report_never_changes_what_the_primary_compiler_extracts(real_users):
    from metacom_pm.paper1.memory.me import extract_action_result_episodes

    rows = build_me_candidate_audit_rows(real_users)
    total_episodes = sum(len(extract_action_result_episodes(u)) for u in real_users)
    assert len(rows) == total_episodes


def test_audit_report_shape_and_zero_outcome(real_users):
    report = build_me_candidate_audit_report(real_users)
    assert report["outcome_calls"] == 0
    assert report["reads_outcome_or_gold_fields"] is False
    assert report["status"] == "B20_ME_CONSTRUCT_REPAIR_PER_CANDIDATE_AUDIT"
    assert report["surviving_unique_candidate_count"] == 3
    assert report["surviving_candidates_by_owner"] == {"p4": 1, "p12": 2}
    assert len(report["candidates"]) == 3
    assert "self_reported_same_turn" in report["linkage_rule_descriptions"]


def test_audit_report_is_json_serializable_and_carries_no_gold_or_evidence_tokens(real_users):
    report = build_me_candidate_audit_report(real_users)
    rendered = json.dumps(report).lower()
    for token in ("evidence", "\"gold\"", "\"answer\"", "observation"):
        assert token not in rendered


def test_manifest_row_shape_matches_the_dataclass():
    row = MeCandidateAuditRow(
        owner_id="synthetic",
        session_id="s1",
        turn_idx=1,
        pattern="self_reported_same_turn",
        linkage_rule=LINKAGE_RULE_DESCRIPTIONS["self_reported_same_turn"],
        action_span=(0, 5),
        action_text="tried",
        action_span_sha256="0" * 64,
        result_span=(5, 10),
        result_text="helps",
        result_span_sha256="1" * 64,
    )
    manifest = row.to_manifest_row()
    assert manifest["protocol"] == "pm-paper1-me-candidate-audit-row-v1"
    assert manifest["action_span"] == [0, 5]
    assert manifest["result_span"] == [5, 10]


def test_synthetic_user_with_no_qualifying_episodes_produces_zero_rows():
    session = Session(
        session_id="s1",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(Turn(idx=1, role="seeker", content="I feel okay today, just a bit tired."),),
    )
    user = MemorySourceUser(
        owner_id="synthetic", sessions=(session,), question_groups=(), summaries=(), subsequent_topics=()
    )
    report = build_me_candidate_audit_report((user,))
    assert report["surviving_unique_candidate_count"] == 0
    assert report["candidates"] == []


def test_synthetic_user_with_one_qualifying_episode_is_fully_disclosed():
    session = Session(
        session_id="s1",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(Turn(idx=1, role="seeker", content="I tried meditation and it helped a bit."),),
    )
    user = MemorySourceUser(
        owner_id="synthetic", sessions=(session,), question_groups=(), summaries=(), subsequent_topics=()
    )
    rows = build_me_candidate_audit_rows((user,))
    assert len(rows) == 1
    row = rows[0]
    assert row.owner_id == "synthetic"
    assert row.session_id == "s1"
    assert row.turn_idx == 1
    assert "tried" in row.action_text.lower()
    assert "help" in row.result_text.lower()
