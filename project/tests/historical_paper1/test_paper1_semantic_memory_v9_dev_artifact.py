import json
from pathlib import Path

from metacom_pm.io import iter_jsonl, sha256_file


PROJECT = Path(__file__).resolve().parents[2]
AUTHORITY = PROJECT / "data/paper1_authority"


def test_v9_dev_materialized_evidence_is_exact_and_zero_outcome():
    sessions_path = AUTHORITY / "paper1_semantic_memory_v9_dev_session_results_20260902_v1.jsonl"
    matrix_path = AUTHORITY / "paper1_semantic_memory_v9_dev_matrix_20260902_v1.jsonl"
    results_path = AUTHORITY / "paper1_semantic_memory_v9_dev_results_20260902_v1.json"
    budget_path = AUTHORITY / "paper1_semantic_memory_v9_dev_budget_ledger_20260902_v1.jsonl"
    sessions = list(iter_jsonl(sessions_path))
    matrix = list(iter_jsonl(matrix_path))
    budget = list(iter_jsonl(budget_path))
    results = json.loads(results_path.read_text(encoding="utf-8"))

    assert sha256_file(sessions_path) == "11107e81c9acea4cc313d503915207952aa711776350448deebb5e94988013f7"
    assert sha256_file(matrix_path) == "149a5250f9f7f10ad75a654ae2f3b61d8231788fac83a41b9e21f9abd55f4d2d"
    assert sha256_file(results_path) == "7bcc0340bcc525fbede16e3321268b59581a07bb0f56172eec211b6723ef95a5"
    assert sha256_file(budget_path) == "c540021606949e453857563599508eda8d9bb56f55eb096d02d9eb3120622bf1"
    assert len(sessions) == 29
    assert len(matrix) == 32
    assert len(budget) == 58
    assert all(row["call_status"] == "SUCCEEDED" for row in sessions)
    assert all(row["outcome_calls"] == 0 for row in sessions + matrix)
    assert results["counts"]["old_pass_retention"] == 17
    assert results["counts"]["known_fail_or_review_rejection"] == 10
    assert results["counts"]["semantic_false_accept"] == 2
    assert results["counts"]["semantic_false_reject"] == 3
    assert results["outcome_calls"] == 0
    assert results["full_401_started"] is False


def test_v9_dev_closeout_does_not_promote_the_catalog():
    closeout = json.loads(
        (AUTHORITY / "paper1_semantic_memory_v9_dev_closeout_20260902_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert closeout["status"] == "DEV_DIAGNOSTIC_IMPROVED_BUT_NOT_QUALIFIED_STOP_BEFORE_401"
    assert len(closeout["five_disagreements"]) == 5
    assert closeout["decision"]["full_401_compile_authorized"] is False
    assert closeout["outcome_calls"] == 0
    assert closeout["PM_training_calls"] == 0
