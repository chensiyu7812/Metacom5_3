import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT / "data/paper1_authority"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_official_esc_rank_closeout_hash_binds_zero_outcome_evidence():
    closeout = json.loads(
        (AUTHORITY / "paper1_official_esc_rank_qualification_closeout_20260902_v1.json")
        .read_text(encoding="utf-8")
    )
    assert closeout["status"].startswith("OFFICIAL_ESC_RANK_QUALIFIED")
    assert closeout["runtime"]["official_valid_parses"] == 42
    assert closeout["blind_human_qualification"]["valid_dimension_parses"] == 168
    for key in ("agreement", "trace", "judge_rows"):
        section = closeout["blind_human_qualification"]
        assert _sha(AUTHORITY / section[f"{key}_artifact"]) == section[f"{key}_sha256"]
    assert _sha(AUTHORITY / closeout["runtime"]["artifact"]) == closeout["runtime"]["sha256"]
    assert closeout["research_status"]["formal_outcome_calls"] == 0
    assert closeout["research_status"]["PM_training_runs"] == 0
    assert set(closeout["research_status"]["locks"].values()) == {"CLOSED"}


def test_master_register_marks_official_anchor_ready_without_claiming_proxy_winner():
    register = json.loads(
        (AUTHORITY / "paper1_master_decision_register_20260820_v1.json").read_text(
            encoding="utf-8"
        )
    )
    decisions = {row["id"]: row for row in register["decisions"]}
    assert decisions["ESC_RANK_official_runtime_qualification"]["status"] == "READY"
    assert decisions["ESC_evaluator_winner"]["status"] == "EXPERIMENT_REQUIRED"
    assert "cannot replace official main scoring" in decisions["ESC_evaluator_winner"]["evidence"]
