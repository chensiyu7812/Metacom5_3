import json
from pathlib import Path

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.es_memeval import enumerate_targets, load_users, parse_users
from metacom_pm.paper1.features import build_census, summarize_census, write_census_manifest

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"

FORBIDDEN_OUTCOME_TOKENS = ("gold", "pass", "fail", "useful", "quality", "worth_opening")


def test_full_corpus_census_covers_every_target_and_head():
    users = parse_users(load_users(EVO_PATH))
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    assert len(rows) == len(targets) * 3  # MP, MS, ME
    assert {row.head for row in rows} == {Head.MP, Head.MS, Head.ME}
    assert {row.target_id for row in rows} == {t.target_id for t in targets}


def test_census_row_reports_only_outcome_blind_axes_no_gold_no_pass_fail():
    users = parse_users(load_users(EVO_PATH))
    targets = enumerate_targets(users)[:40]
    rows = build_census(users, targets)
    rendered = json.dumps([row.to_manifest_row() for row in rows]).lower()
    for token in FORBIDDEN_OUTCOME_TOKENS:
        assert token not in rendered


def test_census_row_covers_the_required_axes():
    users = parse_users(load_users(EVO_PATH))
    targets = [t for t in enumerate_targets(users) if t.task_type is TaskType.QA][:5]
    rows = build_census(users, targets)
    ms_row = next(r for r in rows if r.head is Head.MS and r.candidate_count > 0)
    assert isinstance(ms_row.coverage, bool)
    assert ms_row.candidate_count == len(ms_row.candidates)
    assert ms_row.token_count_mean is not None
    assert all(c.retrieval_rank >= 1 for c in ms_row.candidates)
    ranks = sorted(c.retrieval_rank for c in ms_row.candidates)
    assert ranks == list(range(1, len(ranks) + 1))


def test_summary_reports_coverage_count_length_age_variance_per_head():
    users = parse_users(load_users(EVO_PATH))
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    summary = summarize_census(rows)

    assert summary["outcome_calls"] == 0
    assert summary["targets_total"] == len(targets)
    assert summary["targets_by_task"] == {"qa": 1427, "summary": 125, "dialogue_generation": 34}
    assert summary["identity_anomalies"] == 5

    for head in ("MP", "MS", "ME"):
        per_head = summary["per_head"][head]
        assert per_head["targets_total"] == len(targets)
        assert 0.0 <= per_head["coverage_fraction"] <= 1.0
        assert "candidate_count_variance" in per_head
        assert "token_count_variance_of_means" in per_head
        assert "age_days_variance_of_means" in per_head
        assert "already_visible_fraction_of_candidates" in per_head


def test_mp_coverage_is_honestly_sparse_not_inflated():
    # MP is expected to be genuinely sparse under a strict self-disclosure
    # construct (see memory/mp.py) -- this test guards against silently
    # loosening the pattern set to manufacture higher coverage.
    users = parse_users(load_users(EVO_PATH))
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    summary = summarize_census(rows)
    mp_coverage = summary["per_head"]["MP"]["coverage_fraction"]
    assert 0.0 < mp_coverage < 0.2


def test_manifest_write_roundtrip_and_hash(tmp_path):
    users = parse_users(load_users(EVO_PATH))
    targets = [t for t in enumerate_targets(users) if t.owner_id == "p1"]
    rows = build_census(users, targets)
    summary = summarize_census(rows)
    paths = write_census_manifest(rows, summary, tmp_path)

    manifest_lines = paths["manifest"].read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == len(rows)
    for line in manifest_lines:
        parsed = json.loads(line)
        assert parsed["protocol"] == "pm-paper1-zero-outcome-census-row-v1"

    written_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert written_summary["manifest_rows"] == len(rows)
    assert written_summary["outcome_calls"] == 0

    import hashlib

    rendered = paths["manifest"].read_text(encoding="utf-8")
    assert written_summary["manifest_sha256"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()
