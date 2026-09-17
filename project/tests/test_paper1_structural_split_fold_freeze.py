import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "data" / "paper1_authority"
MEMORY = ROOT / "data" / "paper1_public_memory"


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_approved_structural_freeze_is_exact_and_does_not_unlock_outcomes():
    manifest = json.loads(
        (AUTHORITY / "paper1_structural_split_fold_freeze_20260820_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "FROZEN"
    assert manifest["ESC"]["decision"] == "ESC_large_52"
    assert manifest["ESC"]["seed"] == 0
    assert manifest["RQ2"]["n_outer_folds"] == 5
    assert manifest["RQ2"]["seed"] == 0
    assert manifest["formal_unlock"] is False
    assert manifest["formal_outcome_calls"] == 0
    assert manifest["PM_training_runs"] == 0
    assert set(manifest["outcome_locks"].values()) == {"CLOSED"}


def test_esc_large52_assignments_cover_the_frozen_population_exactly_once():
    rows = _rows(AUTHORITY / "paper1_esc_split_large52_frozen_v1.jsonl")
    assert len(rows) == 173
    assert len({row["card_key"] for row in rows}) == 173
    assert sum(row["split"] == "calibration" for row in rows) == 52
    assert sum(row["split"] == "confirmatory" for row in rows) == 121
    assert {row["seed"] for row in rows} == {0}
    assert {row["overlap_slice"] for row in rows} == {"primary_non_esconv_transfer"}


def test_rq2_k5_seed0_assignments_are_complete_and_component_atomic():
    rows = _rows(MEMORY / "es_memeval_public_outer_fold_assignments_k5_seed0_v1.jsonl")
    assert len(rows) == 1586
    assert len({row["target_id"] for row in rows}) == 1586
    assert {row["n_outer_folds"] for row in rows} == {5}
    assert {row["seed"] for row in rows} == {0}
    assert sorted(sum(row["outer_fold"] == fold for row in rows) for fold in range(5)) == [
        317,
        317,
        317,
        317,
        318,
    ]
    component_to_folds: dict[str, set[int]] = {}
    for row in rows:
        component_to_folds.setdefault(row["group_component_id"], set()).add(
            row["outer_fold"]
        )
        assert row["target_outcome_excluded_from_fit"] is True
    assert len(component_to_folds) == 477
    assert all(len(folds) == 1 for folds in component_to_folds.values())


def test_master_register_records_both_researcher_approvals_as_frozen():
    register = json.loads(
        (AUTHORITY / "paper1_master_decision_register_20260820_v1.json").read_text(
            encoding="utf-8"
        )
    )
    decisions = {row["id"]: row for row in register["decisions"]}
    assert decisions["ESC_split_large_52"]["status"] == "FROZEN"
    assert decisions["RQ2_outer_folds_K5_seed0"]["status"] == "FROZEN"
    assert "seed changes forbidden" in decisions["ESC_split_large_52"]["evidence"]
    assert "seed changes forbidden" in decisions["RQ2_outer_folds_K5_seed0"]["evidence"]
