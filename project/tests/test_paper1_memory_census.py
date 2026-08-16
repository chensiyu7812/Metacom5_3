import json
from pathlib import Path

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import enumerate_targets
from metacom_pm.paper1.features import (
    build_census,
    build_eligible_pool,
    summarize_census,
    summarize_eligible_pool,
    write_census_manifest,
    write_eligible_pool_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"

FORBIDDEN_OUTCOME_TOKENS = ("gold", "pass", "fail", "useful", "quality", "worth_opening")


def _users():
    return build_sanitized_runtime_users(load_raw_users(EVO_PATH))


def test_full_corpus_census_covers_every_target_and_head():
    users = _users()
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    assert len(rows) == len(targets) * 3  # MP, MS, ME
    assert {row.head for row in rows} == {Head.MP, Head.MS, Head.ME}
    assert {row.target_id for row in rows} == {t.target_id for t in targets}


def test_census_row_reports_only_outcome_blind_axes_no_gold_no_pass_fail():
    users = _users()
    targets = enumerate_targets(users)[:40]
    rows = build_census(users, targets)
    rendered = json.dumps([row.to_manifest_row() for row in rows]).lower()
    for token in FORBIDDEN_OUTCOME_TOKENS:
        assert token not in rendered


def test_census_row_covers_the_required_axes():
    users = _users()
    targets = [t for t in enumerate_targets(users) if t.task_type is TaskType.QA][:5]
    rows = build_census(users, targets)
    ms_row = next(r for r in rows if r.head is Head.MS and r.candidate_count > 0)
    assert isinstance(ms_row.coverage, bool)
    assert ms_row.candidate_count == len(ms_row.candidates)
    assert ms_row.token_count_mean is not None
    assert all(c.retrieval_rank >= 1 for c in ms_row.candidates)
    ranks = sorted(c.retrieval_rank for c in ms_row.candidates)
    assert ranks == list(range(1, len(ranks) + 1))


def test_dg_rows_report_null_query_dependent_features_never_related_sessions_or_topic():
    # B19.4: DG has no static current-dialogue state pre-generation -- overlap/
    # the lexical already-visible proxy/retrieval_rank must be None for every
    # DG candidate, never approximated from related_sessions/topic.
    # age_days/token_count are still concrete (they don't depend on a query
    # at all).
    users = _users()
    dg_targets = [t for t in enumerate_targets(users) if t.task_type is TaskType.DIALOGUE_GENERATION]
    rows = build_census(users, dg_targets)
    assert rows
    for row in rows:
        assert row.has_visible_query is False
        assert row.top_candidate_lexical_overlap is None
        for candidate in row.candidates:
            assert candidate.lexical_candidate_query_jaccard_ge_0_6_proxy is None
            assert candidate.lexical_overlap is None
            assert candidate.retrieval_rank is None
        if row.candidate_count > 0:
            assert all(c.age_days is not None for c in row.candidates)
            assert all(c.token_count is not None for c in row.candidates)


def test_summary_reports_coverage_count_length_age_variance_per_head():
    users = _users()
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    summary = summarize_census(rows)

    assert summary["outcome_calls"] == 0
    assert summary["targets_total"] == len(targets)
    assert summary["targets_by_task"] == {"qa": 1427, "summary": 125, "dialogue_generation": 34}
    assert summary["identity_anomalies"] == 5
    assert summary["final_retrieved_bundle_status"] == "PENDING_M2_FREEZE_NOT_SELECTED_THIS_ROUND"
    assert "supersedes" in summary["superseded_note"].lower()

    for head in ("MP", "MS", "ME"):
        per_head = summary["per_head"][head]
        assert per_head["targets_total"] == len(targets)
        assert 0.0 <= per_head["coverage_fraction"] <= 1.0
        assert "candidate_count_variance" in per_head
        assert "token_count_variance_of_means" in per_head
        assert "age_days_variance_of_means" in per_head
        assert "lexical_candidate_query_jaccard_ge_0_6_proxy_fraction_of_candidates" in per_head
        assert "targets_with_visible_query" in per_head

    # B17: every target now draws on the owner's full session history, so MS
    # coverage is total -- there is no more per-target "current session"
    # exclusion that would leave the very first session's target uncovered.
    assert summary["per_head"]["MS"]["coverage_fraction"] == 1.0
    # QA + Summary targets carry a visible question; DG targets never do.
    assert summary["per_head"]["MS"]["targets_with_visible_query"] == 1427 + 125


def test_mp_coverage_is_honestly_sparse_not_inflated():
    # MP is expected to be genuinely sparse under a strict self-disclosure
    # construct (see memory/mp.py) -- this test guards against silently
    # loosening the pattern set to manufacture higher coverage.
    users = _users()
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    summary = summarize_census(rows)
    mp_coverage = summary["per_head"]["MP"]["coverage_fraction"]
    assert 0.0 < mp_coverage < 0.2


def test_me_coverage_is_honestly_sparse_after_the_b20_construct_repair():
    # B20 tightened ME to require an explicit action complement and a
    # same-clause result with no subject/topic shift; only 2 owners (p4, p12)
    # have any surviving ME material corpus-wide.
    users = _users()
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    summary = summarize_census(rows)
    me_coverage = summary["per_head"]["ME"]["coverage_fraction"]
    assert 0.0 < me_coverage < 0.2
    assert summary["per_head"]["ME"]["owners_with_any_candidate"] == 2


def test_eligible_pool_is_the_target_invariant_layer_reported_once_per_owner():
    # B19.5 layer 1: distinct from the per-target census (layer 2) below --
    # one row per (owner, head), not per (target, head).
    users = _users()
    pool_rows = build_eligible_pool(users)
    assert len(pool_rows) == len(users) * 3  # MP, MS, ME per owner
    summary = summarize_eligible_pool(pool_rows)
    assert summary["outcome_calls"] == 0
    assert summary["per_head"]["MS"]["owners_with_any_candidate"] == len(users)
    assert summary["per_head"]["MP"]["owners_with_any_candidate"] == 3
    assert summary["per_head"]["ME"]["owners_with_any_candidate"] == 2
    assert "PENDING_M2_FREEZE" in summary["note"]


def test_manifest_write_roundtrip_and_hash(tmp_path):
    users = _users()
    targets = [t for t in enumerate_targets(users) if t.owner_id == "p1"]
    rows = build_census(users, targets)
    summary = summarize_census(rows)
    paths = write_census_manifest(rows, summary, tmp_path)

    manifest_lines = paths["manifest"].read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == len(rows)
    for line in manifest_lines:
        parsed = json.loads(line)
        assert parsed["protocol"] == "pm-paper1-zero-outcome-census-row-v3"

    written_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert written_summary["manifest_rows"] == len(rows)
    assert written_summary["outcome_calls"] == 0

    import hashlib

    rendered = paths["manifest"].read_text(encoding="utf-8")
    assert written_summary["manifest_sha256"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def test_eligible_pool_manifest_write_roundtrip_and_hash(tmp_path):
    users = [u for u in _users() if u.owner_id == "p1"]
    pool_rows = build_eligible_pool(users)
    summary = summarize_eligible_pool(pool_rows)
    paths = write_eligible_pool_manifest(pool_rows, summary, tmp_path)

    manifest_lines = paths["manifest"].read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == len(pool_rows)
    for line in manifest_lines:
        parsed = json.loads(line)
        assert parsed["protocol"] == "pm-paper1-zero-outcome-eligible-pool-row-v1"

    written_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert written_summary["manifest_rows"] == len(pool_rows)
    assert written_summary["outcome_calls"] == 0

    import hashlib

    rendered = paths["manifest"].read_text(encoding="utf-8")
    assert written_summary["manifest_sha256"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()
