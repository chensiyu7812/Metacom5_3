"""B10: committed manifests must be portable (repo-relative paths, no
absolute/worktree-specific paths) and the census summary must distinguish
edge-level coverage counts from distinct-memory counts."""

import json
import re
import subprocess
from pathlib import Path

import pytest

from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import enumerate_targets
from metacom_pm.paper1.features import build_census, summarize_census

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"
MEMORY_DIR = ROOT / "data" / "paper1_public_memory"

_ABSOLUTE_PATH_PATTERN = re.compile(r"/home/[a-zA-Z0-9_.-]+|" + re.escape(str(ROOT.parent)))


def _users():
    return build_sanitized_runtime_users(load_raw_users(EVO_PATH))


def test_committed_manifests_contain_no_absolute_or_worktree_specific_paths():
    for path in MEMORY_DIR.glob("*.json*"):
        text = path.read_text(encoding="utf-8")
        assert not _ABSOLUTE_PATH_PATTERN.search(text), f"{path} contains an absolute/worktree path"


def test_ripgrep_style_scan_finds_zero_hits_for_home_or_worktree_name():
    # mirrors the operator's own check: rg -n '/home/tokkio|metacom_paper1_rq2' ...
    hits = []
    for path in MEMORY_DIR.glob("*.json*"):
        text = path.read_text(encoding="utf-8")
        if "/home/tokkio" in text or "metacom_paper1_rq2" in text:
            hits.append(str(path))
    assert hits == []


def test_build_report_output_paths_are_repo_relative_posix():
    report = json.loads((MEMORY_DIR / "es_memeval_public_census_build_report_v1.json").read_text())
    for entry in report["outputs"].values():
        path = entry["path"]
        assert not path.startswith("/")
        assert "\\" not in path
        assert (ROOT.parent / path).exists()

    folds_report = json.loads((MEMORY_DIR / "es_memeval_public_folds_build_report_v1.json").read_text())
    for entry in folds_report["outputs"].values():
        path = entry["path"]
        assert not path.startswith("/")
        assert (ROOT.parent / path).exists()


def test_sanitized_artifact_build_report_path_and_hash_are_portable_and_correct():
    # B18: script 05's own build report -- must exist, must be repo-relative,
    # and its recorded sha256 must match the actual artifact bytes on disk.
    report = json.loads(
        (MEMORY_DIR / "es_memeval_public_sanitized_runtime_artifact_build_report_v1.json").read_text()
    )
    assert report["outcome_calls"] == 0
    entry = report["outputs"]["sanitized_runtime_artifact"]
    assert not entry["path"].startswith("/")
    artifact_path = ROOT.parent / entry["path"]
    assert artifact_path.exists()
    import hashlib

    assert entry["sha256"] == hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    assert report["forbidden_key_scan"]["found"] == []


def test_census_build_report_references_the_sanitized_artifact_source():
    # B18/B19: the census build report must record which sanitized artifact
    # it was built from (path + hash), not silently assume one.
    report = json.loads((MEMORY_DIR / "es_memeval_public_census_build_report_v1.json").read_text())
    source = report["sanitized_artifact_source"]
    assert not source["path"].startswith("/")
    assert (ROOT.parent / source["path"]).exists()
    assert len(source["sha256"]) == 64


def test_eligible_pool_manifest_and_summary_paths_are_portable():
    # B19.5 layer 1: the target-invariant pool manifest is a distinct pair of
    # files from the per-target census manifest below -- both must be portable.
    manifest_path = MEMORY_DIR / "es_memeval_public_candidate_eligible_pool_v1.jsonl"
    summary_path = MEMORY_DIR / "es_memeval_public_candidate_eligible_pool_summary_v1.json"
    assert manifest_path.exists()
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text())
    assert summary["manifest_filename"] == manifest_path.name
    assert "/" not in summary["manifest_filename"]
    assert summary["outcome_calls"] == 0


def test_census_summary_manifest_filename_is_not_a_path():
    summary = json.loads(
        (MEMORY_DIR / "es_memeval_public_candidate_census_summary_v1.json").read_text()
    )
    assert "manifest_path" not in summary
    assert summary["manifest_filename"] == "es_memeval_public_candidate_census_v1.jsonl"
    assert "/" not in summary["manifest_filename"]


def test_census_summary_reports_unique_candidate_and_owner_counts_per_head():
    users = _users()
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    summary = summarize_census(rows)

    for head in ("MP", "MS", "ME"):
        per_head = summary["per_head"][head]
        for key in (
            "unique_candidate_count",
            "owners_with_any_candidate",
            "target_candidate_edges",
            "targets_with_coverage",
        ):
            assert key in per_head
        # edge-level counts must never be smaller than the distinct-memory view
        assert per_head["target_candidate_edges"] >= per_head["unique_candidate_count"]
        assert per_head["owners_with_any_candidate"] <= 18


def test_mp_unique_candidates_and_owners_are_exactly_three_edges_are_214():
    # B16/B21: unique-memory count (3) and owner count (3) are the current
    # compiler regression count for memory/mp.py -- unchanged by B21 (which
    # only corrected the audit's *description*, never the compiler itself).
    # B17 changed the *edge* count from 118 to 214: every target now draws
    # on the owner's full session history (no more per-target "current
    # session" exclusion), so each of the 3 disclosures is now offered to
    # more strict-past-eligible targets than before -- see memory_source
    # module docstring. If any of these counts ever changes, it must be a
    # deliberate, reviewed change, not silent drift.
    users = _users()
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    summary = summarize_census(rows)
    mp = summary["per_head"]["MP"]

    assert mp["unique_candidate_count"] == 3
    assert mp["owners_with_any_candidate"] == 3
    assert mp["target_candidate_edges"] == 214
    assert mp["targets_with_coverage"] == 214
    # 214 target-coverage edges from only 3 distinct memories: the edge
    # count must not be mistaken for "214 different things the user disclosed"
    assert mp["target_candidate_edges"] > mp["unique_candidate_count"]


def test_me_unique_candidates_and_owners_after_the_b20_construct_repair():
    # B20 tightened ME (explicit action complement + same-clause result, no
    # subject/topic shift) -- 3 unique candidates survive corpus-wide, from
    # 2 owners (p4, p12), offered across 281 strict-past-eligible edges.
    users = _users()
    targets = enumerate_targets(users)
    rows = build_census(users, targets)
    summary = summarize_census(rows)
    me = summary["per_head"]["ME"]

    assert me["unique_candidate_count"] == 3
    assert me["owners_with_any_candidate"] == 2
    assert me["target_candidate_edges"] == 281
    assert me["target_candidate_edges"] > me["unique_candidate_count"]


def test_census_summary_interpretation_note_is_present_and_non_empty():
    users = _users()
    targets = enumerate_targets(users)[:10]
    rows = build_census(users, targets)
    summary = summarize_census(rows)
    assert isinstance(summary["interpretation_note"], str)
    assert len(summary["interpretation_note"]) > 20


def test_folds_build_report_states_group_component_and_outer_fold_status():
    report = json.loads((MEMORY_DIR / "es_memeval_public_folds_build_report_v1.json").read_text())
    assert report["group_component_status"] == "PREPACK_EXACT_EVIDENCE_COMPONENT"
    assert report["outer_fold_packing_status"] == "OUTER_FOLD_PACKING_PENDING_M2_FREEZE"
    assert report["outcome_calls"] == 0
    assert "evidence_usage" in report


def test_census_build_report_declares_it_never_reads_evidence():
    report = json.loads((MEMORY_DIR / "es_memeval_public_census_build_report_v1.json").read_text())
    assert report["outcome_calls"] == 0
    assert "evidence_usage" in report
    assert "NEVER_READS" in report["evidence_usage"]


def test_operator_rg_command_reports_zero_matches():
    # Runs the literal command the operator specified, so this test fails
    # the same way a manual re-check would if it ever regresses. Skipped
    # (not failed) when no real `rg` binary is on PATH -- e.g. a shell
    # function/alias-only environment -- since the equivalent pure-Python
    # scan above already covers the actual correctness requirement.
    try:
        result = subprocess.run(
            ["rg", "-n", "/home/tokkio|metacom_paper1_rq2", str(MEMORY_DIR)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("no rg binary on PATH in this environment")
    # rg exit code 1 == "no matches" (success for this test); 0 == matches found
    assert result.returncode == 1, f"rg found matches:\n{result.stdout}"
