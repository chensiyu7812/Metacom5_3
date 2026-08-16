import hashlib
import json
from pathlib import Path

import pytest
import yaml

from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.es_memeval import PAPER_QA_COUNT, PUBLIC_QA_COUNT, load_users
from metacom_pm.paper1.data.memory_source import (
    enumerate_targets,
    parse_memory_source_users,
    validate_es_memeval_identity,
)

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_public_artifact_matches_pinned_config_hash():
    config = yaml.safe_load((ROOT / "configs/paper1_public_only.yaml").read_text(encoding="utf-8"))
    assert _sha(EVO_PATH) == config["public_sources"]["es_memeval"]["artifact_sha256"]


def test_paper_vs_public_qa_boundary_is_documented_and_distinct():
    assert PAPER_QA_COUNT == 1209
    assert PUBLIC_QA_COUNT == 1427
    assert PUBLIC_QA_COUNT - PAPER_QA_COUNT == 218


def test_parsed_counts_match_es_memeval_public_1427_shape():
    users = parse_memory_source_users(load_users(EVO_PATH))
    assert len(users) == 18
    assert sum(len(u.sessions) for u in users) == 401
    targets = enumerate_targets(users)
    assert sum(1 for t in targets if t.task_type is TaskType.QA) == PUBLIC_QA_COUNT
    assert sum(1 for t in targets if t.task_type is TaskType.SUMMARY) == 125
    assert sum(1 for t in targets if t.task_type is TaskType.DIALOGUE_GENERATION) == 34


def test_identity_validation_matches_frozen_authority_row_manifest():
    report = validate_es_memeval_identity(ROOT)
    assert report["derived_counts"]["qa"] == PUBLIC_QA_COUNT
    assert report["outcome_calls"] == 0
    assert report["authority_manifest_present"] is True
    assert report["authority_row_count"] == PUBLIC_QA_COUNT
    assert report["row_ids_match_authority_manifest"] is True


def test_identity_validation_rejects_a_drifted_source_hash(tmp_path):
    config_path = ROOT / "configs/paper1_public_only.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["public_sources"]["es_memeval"]["artifact_sha256"] = "0" * 64

    fake_root = tmp_path / "fake_project"
    (fake_root / "configs").mkdir(parents=True)
    (fake_root / "configs" / "paper1_public_only.yaml").write_text(
        yaml.safe_dump(config), encoding="utf-8"
    )
    (fake_root / "data" / "external").mkdir(parents=True)
    (fake_root / "data" / "external" / "evo_emo.json").write_bytes(EVO_PATH.read_bytes())

    with pytest.raises(ValueError, match="no longer matches the pinned"):
        validate_es_memeval_identity(fake_root)


def test_sessions_are_resorted_into_true_chronological_order_even_when_raw_order_is_not():
    raw = load_users(EVO_PATH)
    raw_p3 = next(u for u in raw if u["id"] == "p3")
    raw_timestamps = [s["timestamp"] for s in raw_p3["dialog_history"]]
    assert raw_timestamps != sorted(raw_timestamps), "expected p3 to be a known out-of-order case"

    users = parse_memory_source_users(raw)
    p3 = next(u for u in users if u.owner_id == "p3")
    dates = [s.date for s in p3.sessions]
    assert dates == sorted(dates)
    ranks = [s.chronological_rank for s in p3.sessions]
    assert ranks == list(range(len(p3.sessions)))


def test_topic_and_emotion_normalize_list_or_string_shapes():
    raw = load_users(EVO_PATH)
    raw_p1 = next(u for u in raw if u["id"] == "p1")
    raw_session = next(s for s in raw_p1["dialog_history"] if s["id"] == "p1_conv_24")
    assert isinstance(raw_session["topic"], list), "expected a known list-typed topic case"

    users = parse_memory_source_users(raw)
    p1 = next(u for u in users if u.owner_id == "p1")
    session = p1.session_by_id("p1_conv_24")
    assert isinstance(session.topic, str)
    assert session.topic == ", ".join(raw_session["topic"])


def test_question_group_with_unresolvable_owner_is_flagged_not_guessed():
    users = parse_memory_source_users(load_users(EVO_PATH))
    targets = enumerate_targets(users)
    anomalies = [t for t in targets if t.identity_anomaly is not None]
    assert len(anomalies) == 5
    assert all(t.owner_id == "p6" for t in anomalies)
    assert all(t.cutoff_rank is None for t in anomalies)
    assert all("p7_conv_17" in t.identity_anomaly for t in anomalies)
    # the anomalous group is still counted, preserving the 1427 public total
    assert sum(1 for t in targets if t.task_type is TaskType.QA) == PUBLIC_QA_COUNT


def test_target_never_carries_gold_answer_text():
    users = parse_memory_source_users(load_users(EVO_PATH))
    targets = enumerate_targets(users)
    rendered = json.dumps([t.__dict__ for t in targets[:50]], default=str)
    assert "answer" not in rendered


def test_sanitized_and_evaluator_parses_agree_on_session_identity():
    # B12: two fully independent parsers read the same raw JSON. They must
    # never silently diverge on session identity/order, or the strict-past
    # cutoff computed from one would not match the evidence read from the
    # other.
    from metacom_pm.paper1.data.es_memeval import parse_users as parse_evaluator_users

    raw = load_users(EVO_PATH)
    sanitized = parse_memory_source_users(raw)
    evaluator = parse_evaluator_users(raw)
    assert {u.owner_id for u in sanitized} == {u.owner_id for u in evaluator}
    sanitized_by_owner = {u.owner_id: u for u in sanitized}
    evaluator_by_owner = {u.owner_id: u for u in evaluator}
    for owner_id in sanitized_by_owner:
        s_sessions = [(s.session_id, s.chronological_rank) for s in sanitized_by_owner[owner_id].sessions]
        e_sessions = [(s.session_id, s.chronological_rank) for s in evaluator_by_owner[owner_id].sessions]
        assert s_sessions == e_sessions
