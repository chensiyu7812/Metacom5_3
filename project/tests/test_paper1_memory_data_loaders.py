import dataclasses
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.es_memeval import load_users
from metacom_pm.paper1.data.es_memeval import parse_users as parse_evaluator_users
from metacom_pm.paper1.data.materializer import (
    PAPER_QA_COUNT,
    PUBLIC_QA_COUNT,
    build_sanitized_runtime_users,
    load_raw_users,
    validate_es_memeval_identity,
)
from metacom_pm.paper1.data.memory_source import enumerate_targets

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
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
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
    raw = load_raw_users(EVO_PATH)
    raw_p3 = next(u for u in raw if u["id"] == "p3")
    raw_timestamps = [s["timestamp"] for s in raw_p3["dialog_history"]]
    assert raw_timestamps != sorted(raw_timestamps), "expected p3 to be a known out-of-order case"

    users = build_sanitized_runtime_users(raw)
    p3 = next(u for u in users if u.owner_id == "p3")
    dates = [s.date for s in p3.sessions]
    assert dates == sorted(dates)
    ranks = [s.chronological_rank for s in p3.sessions]
    assert ranks == list(range(len(p3.sessions)))


def test_session_never_carries_emotion_or_topic_even_for_a_known_list_typed_raw_case():
    # B23: session-level emotion/topic are dataset-author labels the official
    # harness's room/document-store construction never reads (verified
    # against ChatRoomBuilder.fill_chat_room/fill_session) -- Session must
    # not carry them regardless of the raw shape. p1_conv_24 is a known case
    # where raw "topic" is list-typed (not just string-typed), so this
    # exercises the same raw record the old normalize-shape test used,
    # confirming the field is dropped rather than merely reformatted.
    raw = load_raw_users(EVO_PATH)
    raw_p1 = next(u for u in raw if u["id"] == "p1")
    raw_session = next(s for s in raw_p1["dialog_history"] if s["id"] == "p1_conv_24")
    assert isinstance(raw_session["topic"], list), "expected a known list-typed topic case"
    assert "emotion" in raw_session and "topic" in raw_session

    users = build_sanitized_runtime_users(raw)
    p1 = next(u for u in users if u.owner_id == "p1")
    session = p1.session_by_id("p1_conv_24")
    field_names = {f.name for f in dataclasses.fields(session)}
    assert "emotion" not in field_names
    assert "topic" not in field_names


def test_question_group_with_unresolvable_owner_is_flagged_not_guessed():
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    targets = enumerate_targets(users)
    anomalies = [t for t in targets if t.identity_anomaly is not None]
    assert len(anomalies) == 5
    assert all(t.owner_id == "p6" for t in anomalies)
    assert all("p7_conv_17" in t.identity_anomaly for t in anomalies)
    # B17.5: the anomaly is audit-only -- it must NOT empty the candidate
    # pool or zero out cutoff_rank any more (the full dialog_history is
    # strict-past for every target regardless of question_group_id
    # resolvability).
    owner_sessions = {u.owner_id: len(u.sessions) for u in users}
    assert all(t.cutoff_rank == owner_sessions[t.owner_id] for t in anomalies)
    assert all(t.cutoff_rank > 0 for t in anomalies)
    # the anomalous group is still counted, preserving the 1427 public total
    assert sum(1 for t in targets if t.task_type is TaskType.QA) == PUBLIC_QA_COUNT


def test_target_never_carries_gold_answer_text():
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    targets = enumerate_targets(users)
    rendered = json.dumps([t.__dict__ for t in targets[:50]], default=str)
    assert "answer" not in rendered


def test_sanitized_and_evaluator_parses_agree_on_session_identity():
    # B12: two fully independent parsers read the same raw JSON. They must
    # never silently diverge on session identity/order, or the strict-past
    # cutoff computed from one would not match the evidence read from the
    # other.
    raw = load_raw_users(EVO_PATH)
    sanitized = build_sanitized_runtime_users(raw)
    evaluator = parse_evaluator_users(load_users(EVO_PATH))
    assert {u.owner_id for u in sanitized} == {u.owner_id for u in evaluator}
    sanitized_by_owner = {u.owner_id: u for u in sanitized}
    evaluator_by_owner = {u.owner_id: u for u in evaluator}
    for owner_id in sanitized_by_owner:
        s_sessions = [(s.session_id, s.chronological_rank) for s in sanitized_by_owner[owner_id].sessions]
        e_sessions = [(s.session_id, s.chronological_rank) for s in evaluator_by_owner[owner_id].sessions]
        assert s_sessions == e_sessions


def test_every_target_cutoff_rank_is_the_owners_full_session_count():
    # B17: verified against the official ES-MemEval evaluation harness --
    # the complete dialog_history is strict-past for every target of every
    # task type, no per-target restriction.
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    targets = enumerate_targets(users)
    session_count_by_owner = {u.owner_id: len(u.sessions) for u in users}
    assert all(t.cutoff_rank == session_count_by_owner[t.owner_id] for t in targets)


def test_qa_and_summary_targets_carry_the_officially_visible_question_text():
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    targets = enumerate_targets(users)
    qa_and_summary = [t for t in targets if t.task_type in (TaskType.QA, TaskType.SUMMARY)]
    assert qa_and_summary
    assert all(isinstance(t.visible_query_text, str) and t.visible_query_text for t in qa_and_summary)


def test_dg_targets_have_no_static_visible_query():
    # B17.4: no static current-dialogue state exists pre-generation for DG.
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    targets = enumerate_targets(users)
    dg_targets = [t for t in targets if t.task_type is TaskType.DIALOGUE_GENERATION]
    assert len(dg_targets) == 34
    assert all(t.visible_query_text is None for t in dg_targets)


def test_materializer_never_reads_forbidden_raw_fields():
    # B17/B18 structural check: the materializer's own parsing logic must
    # never index the forbidden raw JSON keys.
    import ast
    import inspect

    from metacom_pm.paper1.data import materializer

    tree = ast.parse(inspect.getsource(materializer))
    forbidden_subscripts = {
        "evidence",
        "answer",
        "theme",
        "group",
        "related_sessions",
        "more_details",
        "physical_condition",
        "psychological_condition",
        "basic_info",
        "observation",
        "emotion",
        "topic",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            value = node.slice.value
            if isinstance(value, str) and value in forbidden_subscripts:
                raise AssertionError(f"materializer.py indexes forbidden raw key {value!r}")


def test_sanitized_session_schema_carries_exactly_the_runtime_visible_fields():
    # B23.4: the sanitized runtime Session must carry only what the official
    # harness's room/document-store construction actually reads --
    # session_id/timestamp/chronological_rank/turns. No owner_id field either
    # (every Session only ever exists inside its owning MemorySourceUser.
    # sessions, so owner identity is bound structurally by the parent
    # container/type, never duplicated per-session) -- and no evaluator/
    # dataset annotation of any kind (emotion/topic/summary/observation).
    from metacom_pm.paper1.data.memory_source import Session

    field_names = {f.name for f in dataclasses.fields(Session)}
    assert field_names == {"session_id", "timestamp", "chronological_rank", "turns"}


def test_sanitized_session_owner_is_reachable_only_through_the_containing_user():
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    user = next(u for u in users if u.owner_id == "p1")
    session = user.sessions[0]
    assert not hasattr(session, "owner_id")
    # the only way to attribute a session to an owner is via the parent
    # MemorySourceUser it was enumerated from
    assert session in user.sessions
