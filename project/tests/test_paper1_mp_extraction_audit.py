"""B16: MP self-disclosure extraction audit -- diagnostic only, not adopted."""

import json
from pathlib import Path

import pytest

from metacom_pm.paper1.data.es_memeval import load_users
from metacom_pm.paper1.data.memory_source import (
    MemorySourceUser,
    Session,
    Turn,
    parse_memory_source_users,
)
from metacom_pm.paper1.features.mp_extraction_audit import (
    CATEGORY_PATTERNS,
    build_audit_report,
    category_scan,
    primary_compiler_hits,
)

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return parse_memory_source_users(load_users(EVO_PATH))


def test_primary_compiler_hits_matches_the_production_compiler_count(real_users):
    hits = primary_compiler_hits(real_users)
    assert len(hits) == 3
    owners = {h.owner_id for h in hits}
    assert len(owners) == 3
    for hit in hits:
        assert len(hit.source_record_ids) >= 1


def test_category_scan_never_reads_basic_info_or_gold_fields():
    # structural check: the module source never references basic_info or
    # any gold/answer/observation field
    import ast
    import inspect

    from metacom_pm.paper1.features import mp_extraction_audit

    tree = ast.parse(inspect.getsource(mp_extraction_audit))
    forbidden = {"basic_info", "answer", "gold", "observation", "evidence"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden:
            raise AssertionError(f"forbidden attribute access .{node.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in forbidden:
            raise AssertionError(f"forbidden string constant {node.value!r}")


@pytest.mark.parametrize(
    "category,text",
    [
        ("occupation", "I work as a nurse at the hospital downtown."),
        ("family_relationship", "My mother keeps calling me every day."),
        ("residence", "I live in Chicago with my roommate."),
        ("study", "I'm majoring in psychology this semester."),
        ("diagnosis", "I've been diagnosed with anxiety last year."),
        ("durable_trait", "I've always been the quiet type."),
    ],
)
def test_category_patterns_have_at_least_one_grounded_positive_example(category, text):
    patterns = CATEGORY_PATTERNS[category]
    assert any(p.search(text) for p in patterns)


def test_category_scan_finds_real_corpus_examples(real_users):
    hits = category_scan(real_users)
    by_category = {}
    for h in hits:
        by_category.setdefault(h.category, []).append(h)
    # grounded in a real prior scan of the corpus (see script 04's docstring)
    assert len(by_category.get("family_relationship", [])) > 50
    assert len(by_category.get("occupation", [])) >= 1
    assert len(by_category.get("diagnosis", [])) >= 1
    assert "residence" not in by_category or len(by_category["residence"]) == 0


def test_audit_report_never_adopts_new_categories_into_primary_compiler(real_users):
    report = build_audit_report(real_users)
    assert report["status"] == "DIAGNOSTIC_ONLY_NOT_WIRED_INTO_PRIMARY_COMPILER"
    assert report["outcome_calls"] == 0
    assert report["reads_basic_info"] is False
    assert report["reads_outcome_or_gold_fields"] is False
    # the primary compiler's own count must still be 3 -- this audit is
    # read-only with respect to memory/mp.py
    assert report["primary_compiler"]["unique_hit_count"] == 3


def test_audit_report_category_summary_distinguishes_covered_from_uncovered(real_users):
    report = build_audit_report(real_users)
    for category, row in report["category_coverage_audit"].items():
        assert row["total_matches"] == row["already_covered_by_primary_compiler"] + row[
            "not_covered_by_primary_compiler"
        ]
        assert row["owners_matched"] == len(row["owner_ids"])


def test_audit_report_json_serializable_and_contains_no_evidence_or_gold_tokens(real_users):
    # "reads_basic_info": false is a legitimate self-declaration field, not
    # a leak of actual basic_info content -- checked separately by
    # test_category_scan_never_reads_basic_info_or_gold_fields (AST-level).
    report = build_audit_report(real_users)
    assert report["reads_basic_info"] is False
    rendered = json.dumps(report).lower()
    for token in ("evidence", "\"gold\"", "\"answer\""):
        assert token not in rendered


def test_synthetic_user_with_no_matches_produces_empty_categories():
    session = Session(
        owner_id="synthetic",
        session_id="s1",
        timestamp="2024-01-01",
        chronological_rank=0,
        emotion="neutral",
        topic="test",
        turns=(Turn(idx=1, role="seeker", content="I feel okay today, just a bit tired."),),
    )
    user = MemorySourceUser(
        owner_id="synthetic", sessions=(session,), question_groups=(), summaries=(), subsequent_topics=()
    )
    report = build_audit_report((user,))
    assert report["primary_compiler"]["unique_hit_count"] == 0
    for row in report["category_coverage_audit"].values():
        assert row["total_matches"] == 0
