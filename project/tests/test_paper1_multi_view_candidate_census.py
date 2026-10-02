import json
from pathlib import Path

from metacom_pm.io import iter_jsonl, sha256_file
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory import (
    AcceptedEventExperienceUnit,
    AcceptedProfileViewUnit,
    load_accepted_multi_view_units,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "paper1_public_memory"
AUTHORITY = ROOT / "data" / "paper1_authority"


def _summary():
    return json.loads(
        (
            PUBLIC
            / "es_memeval_public_multi_view_candidate_census_summary_v1.json"
        ).read_text(encoding="utf-8")
    )


def test_promoted_401_result_is_complete_and_matches_closeout():
    source = PUBLIC / "es_memeval_public_sanitized_runtime_artifact_v1.json"
    results = PUBLIC / "es_memeval_public_multi_view_session_results_v1.jsonl"
    closeout = json.loads(
        (
            AUTHORITY / "paper1_multi_view_401_closeout_20260903_v1.json"
        ).read_text(encoding="utf-8")
    )
    users = load_sanitized_runtime_users(source)
    units = load_accepted_multi_view_units(results, users=users)
    assert sha256_file(results) == closeout["identity"]["session_results_sha256"]
    assert len(units) == 2236
    assert sum(isinstance(unit, AcceptedProfileViewUnit) for unit in units) == 713
    assert sum(isinstance(unit, AcceptedEventExperienceUnit) for unit in units) == 1523


def test_candidate_census_has_exact_population_hashes_and_no_selected_top_k():
    summary = _summary()
    assert summary["status"] == "ZERO_OUTCOME_MULTI_VIEW_CANDIDATE_CENSUS_COMPLETE"
    assert summary["population"] == {
        "owners": 18,
        "sessions": 401,
        "targets": 1586,
        "targets_by_task": {
            "dialogue_generation": 34,
            "qa": 1427,
            "summary": 125,
        },
    }
    assert {
        head: summary["eligible_pool"][head]["candidates"]
        for head in ("MP", "MS", "ME")
    } == {"MP": 388, "MS": 401, "ME": 1523}
    assert all(
        summary["target_coverage"]["per_head"][head]["coverage_fraction"] == 1.0
        for head in ("MP", "MS", "ME")
    )
    for artifact in summary["artifacts"].values():
        assert sha256_file(PUBLIC / artifact["filename"]) == artifact["sha256"]
    assert summary["method_boundary"]["top_k_or_final_bundle_selected"] is False
    assert summary["method_boundary"]["formal_outcome_calls"] == 0
    assert summary["method_boundary"]["pm_training_runs"] == 0
    assert summary["method_boundary"]["paid_api_calls"] == 0


def test_candidate_pool_is_text_free_and_lineage_complete():
    summary = _summary()
    pool_path = PUBLIC / summary["artifacts"]["candidate_pool"]["filename"]
    pool = list(iter_jsonl(pool_path))
    assert len(pool) == 388 + 401 + 1523
    assert len({row["candidate_id"] for row in pool}) == len(pool)
    assert all(row["strict_past"] is True for row in pool)
    assert all("content" not in row for row in pool)
    assert summary["source_lineage_census"]["distinct_source_sessions"]["MS"] == 401
    assert summary["source_lineage_census"]["MP_ME_shared_grounded_source_turns"] > 0


def test_profile_revision_and_generator_token_counts_are_explicit():
    summary = _summary()
    revision = summary["profile_exact_slot_revision_census"]
    assert revision["accepted_historical_MP_units"] == 713
    assert revision["exact_owner_slot_keys"] == 388
    assert revision["current_view_MP_candidates"] == 388
    assert revision["historical_units_not_in_current_view"] == 325
    assert revision["current_view_same_rank_distinct_value_collision_slots"] == 0
    assert summary["tokenizer"]["tokenizer_json_sha256"] == (
        "79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4"
    )
    assert summary["eligible_pool"]["MS"]["candidate_token_count"]["median"] == 592
    assert summary["eligible_pool"]["MS"]["owner_full_pool_token_count"]["median"] == 13177
