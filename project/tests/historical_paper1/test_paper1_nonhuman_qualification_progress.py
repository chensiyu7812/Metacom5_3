import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
STATUS = PROJECT / "data/paper1_authority/paper1_nonhuman_qualification_progress_20260823_v1.json"


def test_nonhuman_progress_keeps_all_prohibited_execution_at_zero():
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    calls = status["calls_and_training_this_batch"]
    assert set(calls.values()) == {0}
    assert set(status["locks"].values()) == {"CLOSED"}
    assert status["completed"]["memory_v9_offline"]["full_401_compile"] is False
    assert status["completed"]["memory_v8_data_quality_audit"]["new_human_ratings"] == 0


def test_nonhuman_progress_does_not_hide_remaining_authorization_or_hardware_gates():
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    kinds = {row["kind"] for row in status["remaining_blockers"]}
    assert "HUMAN_REVIEW_REQUIRED" in kinds
    assert "RESEARCHER_API_AUTHORIZATION_REQUIRED" in kinds
    assert "GPU_REQUIRED" in kinds
    assert status["completed"]["ESC_RANK_cloud_readiness"]["runtime_evaluator_calls"] == 0
