import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
FREEZE = PROJECT / "data/paper1_authority/paper1_rq2_dg_dynamic_query_freeze_20260823_v1.json"
MDR = PROJECT / "data/paper1_authority/paper1_master_decision_register_20260820_v1.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dg_dynamic_query_freeze_matches_pinned_official_audit():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    source = freeze["official_source"]
    assert _sha(PROJECT.parent / source["visibility_audit_path"]) == source["visibility_audit_sha256"]
    assert _sha(PROJECT.parent / source["surface_rows_path"]) == source["surface_rows_sha256"]
    audit = json.loads((PROJECT.parent / source["visibility_audit_path"]).read_text(encoding="utf-8"))
    query = audit["official_rag_contract"]["query_construction"]["dialogue_generation"]
    assert "session_history[-1].text()" in query
    assert "CURRENT seeker utterance" in query
    assert audit["dg_structure"]["interaction_rounds"] == 10


def test_dg_dynamic_query_freeze_is_per_round_current_only_and_outcome_blind():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    query = freeze["frozen_query_contract"]
    assert query["decision_and_retrieval_calls_per_dialogue"] == 10
    assert query["call_rounds"] == list(range(1, 11))
    assert query["history_window_in_query"] == "CURRENT_SEEKER_UTTERANCE_ONLY"
    assert query["re_retrieval_schedule"] == "EVERY_SUPPORTER_GENERATION_ROUND"
    assert query["static_pre_generation_query_forbidden"] is True
    integrity = freeze["research_integrity"]
    assert integrity["outcome_reads"] == integrity["outcome_calls"] == 0
    assert integrity["PM_training_runs"] == 0
    assert set(integrity["locks"].values()) == {"CLOSED"}
    assert freeze["responsibility_boundary"]["step2_utility_filter"] is False


def test_master_register_records_dg_freeze_but_not_bundle_amount_freeze():
    register = json.loads(MDR.read_text(encoding="utf-8"))
    decisions = {row["id"]: row for row in register["decisions"]}
    assert decisions["RQ2_DG_dynamic_query_window_schedule"]["status"] == "FROZEN"
    assert decisions["RQ2_task_specific_memory_bundles"]["status"] == "EXPERIMENT_REQUIRED"
