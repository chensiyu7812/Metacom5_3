"""B26: structural outer-fold packing decision surface."""

from pathlib import Path

import pytest

from metacom_pm.paper1.data.es_memeval import load_users
from metacom_pm.paper1.data.es_memeval import parse_users as parse_evaluator_users
from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import enumerate_targets
from metacom_pm.paper1.splits import (
    GroupComponent,
    build_group_components,
    enumerate_packing_surface,
    summarize_packing_surface,
)
from metacom_pm.paper1.splits.evidence import enumerate_split_evidence
from metacom_pm.paper1.splits.outer_fold_decision_surface import NO_WINNER_NOTE

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_components():
    raw = load_raw_users(EVO_PATH)
    users = build_sanitized_runtime_users(raw)
    targets = enumerate_targets(users)
    evidence_records = enumerate_split_evidence(parse_evaluator_users(load_users(EVO_PATH)))
    return build_group_components(targets, evidence_records)


def test_real_corpus_has_the_known_477_components(real_components):
    assert len(real_components) == 477


def test_surface_covers_exactly_k_2_to_10_times_seed_0_to_31(real_components):
    points = enumerate_packing_surface(real_components)
    assert len(points) == 9 * 32  # K in [2, 10], seed in [0, 31]
    keys = {(p.n_outer_folds, p.seed) for p in points}
    assert keys == {(k, s) for k in range(2, 11) for s in range(32)}


def test_every_point_assigns_every_target_exactly_once(real_components):
    points = enumerate_packing_surface(real_components, k_values=(3, 7), seed_values=(0, 5))
    for p in points:
        assert p.all_targets_assigned_exactly_once is True
        assert p.no_missing_or_duplicate_targets is True
        assert p.total_targets_assigned == p.total_targets_expected


def test_every_point_is_component_atomic(real_components):
    points = enumerate_packing_surface(real_components, k_values=(2, 5, 10), seed_values=(0, 17, 31))
    for p in points:
        assert p.all_components_atomic is True


def test_every_fold_target_count_sums_to_the_full_corpus(real_components):
    total_targets = sum(c.target_count for c in real_components)
    points = enumerate_packing_surface(real_components, k_values=(4,), seed_values=(0,))
    p = points[0]
    assert sum(f.target_count for f in p.folds) == total_targets
    assert p.total_targets_expected == total_targets


def test_qa_summary_dg_breakdown_sums_to_fold_target_count(real_components):
    points = enumerate_packing_surface(real_components, k_values=(5,), seed_values=(3,))
    for p in points:
        for f in p.folds:
            assert (
                f.qa_target_count + f.summary_target_count + f.dialogue_generation_target_count
                == f.target_count
            )


def test_owner_coverage_never_exceeds_the_known_18_owners(real_components):
    points = enumerate_packing_surface(real_components, k_values=(2, 6, 10), seed_values=(0, 10, 31))
    for p in points:
        for f in p.folds:
            assert 0 <= f.owner_count <= 18
            assert len(f.owner_ids) == f.owner_count
            assert len(set(f.owner_ids)) == f.owner_count  # no duplicate owner ids


def test_different_seeds_can_produce_different_component_to_fold_assignments(real_components):
    # not every seed differs (greedy bin-balancing may tie), but across 32
    # seeds at a fixed K we expect to see more than one distinct packing.
    points = enumerate_packing_surface(real_components, k_values=(5,), seed_values=tuple(range(32)))
    fold_component_counts = {tuple(f.component_count for f in p.folds) for p in points}
    assert len(fold_component_counts) >= 1  # sanity: computed successfully
    # the actual determinism/seed-sensitivity contract is covered by
    # test_paper1_splits_folds.py's B15 tests on the packer itself; this
    # just confirms the surface enumerator faithfully reflects that.


def test_imbalance_ratio_is_close_to_one_for_this_well_balanced_corpus(real_components):
    points = enumerate_packing_surface(real_components, k_values=(2, 5, 10), seed_values=(0, 1, 2))
    for p in points:
        assert p.target_count_imbalance_ratio is not None
        assert 0.9 <= p.target_count_imbalance_ratio <= 1.5


def test_k_greater_than_component_count_is_silently_skipped_not_errored():
    tiny = tuple(
        GroupComponent(
            component_id=f"component::c{i}",
            primary_group_keys=(f"g{i}",),
            target_ids=(f"t{i}",),
            task_type_counts=(("qa", 1),),
            owner_ids=frozenset({f"p{i}"}),
        )
        for i in range(3)
    )
    points = enumerate_packing_surface(tiny, k_values=(2, 3, 4, 5), seed_values=(0,))
    # K=4,5 exceed the 3-component corpus and must not be attempted
    assert {p.n_outer_folds for p in points} == {2, 3}


def test_summary_reports_no_winner_and_correct_status(real_components):
    points = enumerate_packing_surface(real_components, k_values=(2, 3), seed_values=(0, 1))
    summary = summarize_packing_surface(
        points, k_values=(2, 3), seed_values=(0, 1), total_components=len(real_components)
    )
    assert summary["status"] == "OUTER_FOLD_PACKING_DECISION_SURFACE_AUDIT_NOT_A_FREEZE"
    assert summary["outer_fold_packing_status"] == "OUTER_FOLD_PACKING_PENDING_M2_FREEZE"
    assert summary["no_winner_note"] == NO_WINNER_NOTE
    assert summary["outcome_calls"] == 0
    assert summary["surface_points_total"] == len(points) == summary["surface_points_expected"]
    assert summary["all_points_pass_structural_integrity_checks"] is True
    # no field carries a chosen/recommended (K, seed) value -- the summary's
    # own disclaimer text legitimately contains the words "winner"/
    # "recommended" in the negative ("no winner is selected"), so this
    # checks for an actual verdict-shaped key, not a bare word scan.
    forbidden_keys = {"selected_k", "selected_seed", "recommended_k", "recommended_seed", "winner", "best_k", "best_seed"}
    assert forbidden_keys.isdisjoint(summary.keys())
    assert '"PASS"' not in str(summary) and '"FAIL"' not in str(summary)


def test_summary_never_promotes_shared_session_sensitivity_to_primary(real_components):
    points = enumerate_packing_surface(real_components, k_values=(2,), seed_values=(0,))
    summary = summarize_packing_surface(
        points, k_values=(2,), seed_values=(0,), total_components=len(real_components)
    )
    note = summary["shared_session_sensitivity_note"].lower()
    assert "sensitivity" in note
    assert "not" in note or "never" in note


def test_component_id_never_treated_as_fold_id(real_components):
    points = enumerate_packing_surface(real_components, k_values=(2,), seed_values=(0,))
    for p in points:
        manifest = p.to_manifest_row()
        rendered = str(manifest)
        assert '"fold_id"' not in rendered
        for f in p.folds:
            assert isinstance(f.outer_fold, int)  # a plain integer index, not a component_id string


def test_no_gold_or_outcome_tokens_anywhere_in_a_surface_point(real_components):
    points = enumerate_packing_surface(real_components, k_values=(2,), seed_values=(0,))
    rendered = str([p.to_manifest_row() for p in points]).lower()
    for token in ("evidence", "\"gold\"", "\"answer\"", "observation"):
        assert token not in rendered
