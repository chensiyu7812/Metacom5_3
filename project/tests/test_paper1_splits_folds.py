import dataclasses
from collections import defaultdict
from pathlib import Path

import pytest

from metacom_pm.paper1.data.es_memeval import load_users
from metacom_pm.paper1.data.es_memeval import parse_users as parse_evaluator_users
from metacom_pm.paper1.data.memory_source import enumerate_targets, parse_memory_source_users
from metacom_pm.paper1.splits import (
    GROUP_COMPONENT_STATUS,
    OUTER_FOLD_PACKING_STATUS,
    GroupComponent,
    GroupComponentAssignment,
    build_group_component_assignments,
    build_group_components,
    build_shared_session_sensitivity_components,
    canonical_evidence_fingerprint,
    pack_components_into_outer_folds,
    summarize_outer_fold_packing,
)
from metacom_pm.paper1.splits.evidence import enumerate_split_evidence

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


def _load():
    raw = load_users(EVO_PATH)
    # B12: targets come from the sanitized loader; evidence_records from the
    # fully independent evaluator/split-only loader -- never one object that
    # has both.
    users = parse_memory_source_users(raw)
    targets = enumerate_targets(users)
    evidence_records = enumerate_split_evidence(parse_evaluator_users(raw))
    return users, targets, evidence_records


def test_canonical_evidence_fingerprint_is_order_independent_and_deduplicated():
    a = canonical_evidence_fingerprint("p1", ("x:1", "y:2", "x:1"))
    b = canonical_evidence_fingerprint("p1", ("y:2", "x:1"))
    assert a == b
    assert canonical_evidence_fingerprint("p1", ()) is None


def test_canonical_evidence_fingerprint_is_owner_namespaced():
    # B9.4 regression: the public artifact has a real cross-owner literal
    # session-id collision (session "esc1198" belongs to both p13 and p18).
    # Two different owners citing byte-identical evidence refs must never
    # produce the same fingerprint, or their targets would be wrongly
    # unioned into one fold.
    same_refs = ("esc1198:4", "esc1198:6")
    fp_a = canonical_evidence_fingerprint("p13", same_refs)
    fp_b = canonical_evidence_fingerprint("p18", same_refs)
    assert fp_a != fp_b


def test_every_target_within_a_primary_group_shares_one_component():
    _users, targets, evidence_records = _load()
    assignments = build_group_component_assignments(targets, evidence_records)

    component_by_group: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        component_by_group[assignment.primary_group_key].add(assignment.group_component_id)
    assert all(len(ids) == 1 for ids in component_by_group.values())


def test_group_component_assignment_is_not_the_shared_fold_assignment_contract():
    # B14: GroupComponentAssignment must be a type this package owns, never
    # the shared contracts.FoldAssignment, and must carry no fold_id field.
    from metacom_pm.paper1 import contracts as shared_contracts

    assert GroupComponentAssignment is not shared_contracts.FoldAssignment
    assert GroupComponentAssignment.__module__.startswith("metacom_pm.paper1.splits")
    field_names = {f.name for f in dataclasses.fields(GroupComponentAssignment)}
    assert "fold_id" not in field_names
    assert "group_component_id" in field_names


def test_group_component_id_values_are_named_as_components_not_folds():
    _users, targets, evidence_records = _load()
    assignments = build_group_component_assignments(targets, evidence_records)
    assert all(a.group_component_id.startswith("component::") for a in assignments)
    assert all(not a.group_component_id.startswith("fold::") for a in assignments)
    assert all(not hasattr(a, "fold_id") for a in assignments)


def test_qa_targets_in_the_same_session_group_share_a_component():
    _users, targets, evidence_records = _load()
    assignments = {a.target_id: a for a in build_group_component_assignments(targets, evidence_records)}

    p1_esc1024_targets = [t for t in targets if t.target_id.startswith("p1::esc1024::")]
    assert len(p1_esc1024_targets) >= 2
    component_ids = {assignments[t.target_id].group_component_id for t in p1_esc1024_targets}
    assert len(component_ids) == 1


def test_cross_task_union_only_fires_on_byte_identical_owner_scoped_evidence():
    _users, targets, evidence_records = _load()
    assignments = build_group_component_assignments(targets, evidence_records)
    evidence_by_target = {r.target_id: (r.owner_id, r.evidence_refs) for r in evidence_records}

    component_tasks: dict[str, set[str]] = defaultdict(set)
    component_members: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        component_tasks[assignment.group_component_id].add(assignment.task_type.value)
        component_members[assignment.group_component_id].add(assignment.target_id)

    mixed_task_components = {cid: tasks for cid, tasks in component_tasks.items() if len(tasks) > 1}
    assert len(mixed_task_components) > 0, "expected at least one real cross-task union in the corpus"

    for component_id in mixed_task_components:
        member_ids = component_members[component_id]
        owners = {evidence_by_target[tid][0] for tid in member_ids}
        fingerprints = {
            canonical_evidence_fingerprint(*evidence_by_target[tid]) for tid in member_ids
        }
        # every member of a cross-task-unioned component must share the same
        # owner and the identical non-null owner-scoped evidence fingerprint
        assert len(owners) == 1
        assert len(fingerprints) == 1
        assert None not in fingerprints


def test_a_known_summary_and_dg_pair_unions_on_identical_evidence():
    _users, targets, evidence_records = _load()
    assignments = {a.target_id: a for a in build_group_component_assignments(targets, evidence_records)}
    evidence_by_target = {r.target_id: r.evidence_refs for r in evidence_records}

    summary_target_id = "p1::summary::5"
    dg_target_id = "p1::dg::1"
    assert evidence_by_target[summary_target_id] == evidence_by_target[dg_target_id]
    assert (
        assignments[summary_target_id].group_component_id
        == assignments[dg_target_id].group_component_id
    )


def test_group_component_id_is_deterministic_across_repeated_runs():
    _users, targets, evidence_records = _load()
    first = {
        a.target_id: a.group_component_id for a in build_group_component_assignments(targets, evidence_records)
    }
    second = {
        a.target_id: a.group_component_id for a in build_group_component_assignments(targets, evidence_records)
    }
    assert first == second


def test_group_component_assignment_always_excludes_target_outcome_from_fit():
    _users, targets, evidence_records = _load()
    targets = targets[:20]
    evidence_records = tuple(r for r in evidence_records if r.target_id in {t.target_id for t in targets})
    assignments = build_group_component_assignments(targets, evidence_records)
    assert all(a.target_outcome_excluded_from_fit for a in assignments)
    assert all(a.all_arms_seeds_repeats_bound for a in assignments)


def test_shared_session_sensitivity_components_are_strictly_broader_than_primary_components():
    users, targets, evidence_records = _load()
    primary = build_group_component_assignments(targets, evidence_records)
    sensitivity = build_shared_session_sensitivity_components(targets, users, evidence_records)

    n_primary_components = len({a.group_component_id for a in primary})
    n_sensitivity_components = len(sensitivity)
    assert n_sensitivity_components < n_primary_components

    all_target_ids = {t.target_id for t in targets}
    covered = set()
    for component in sensitivity:
        covered.update(component.target_ids)
    assert covered == all_target_ids


def test_primary_component_assignment_is_untouched_by_broad_shared_session_grouping():
    # rule 6: the broad sensitivity grouping must never influence group_component_id.
    users, targets, evidence_records = _load()
    before = {
        a.target_id: a.group_component_id for a in build_group_component_assignments(targets, evidence_records)
    }
    build_shared_session_sensitivity_components(targets, users, evidence_records)
    after = {
        a.target_id: a.group_component_id for a in build_group_component_assignments(targets, evidence_records)
    }
    assert before == after


def test_status_constants_are_exactly_the_required_strings():
    assert GROUP_COMPONENT_STATUS == "PREPACK_EXACT_EVIDENCE_COMPONENT"
    assert OUTER_FOLD_PACKING_STATUS == "OUTER_FOLD_PACKING_PENDING_M2_FREEZE"


def test_group_components_are_consistent_with_component_assignments():
    _users, targets, evidence_records = _load()
    assignments = build_group_component_assignments(targets, evidence_records)
    components = build_group_components(targets, evidence_records)

    assert len({c.component_id for c in components}) == len({a.group_component_id for a in assignments})
    assert sum(c.target_count for c in components) == len(targets)

    target_to_component = {a.target_id: a.group_component_id for a in assignments}
    for component in components:
        for target_id in component.target_ids:
            assert target_to_component[target_id] == component.component_id


def test_group_components_carry_outcome_blind_task_and_owner_aggregates():
    _users, targets, evidence_records = _load()
    components = build_group_components(targets, evidence_records)
    for component in components:
        assert sum(count for _task, count in component.task_type_counts) == component.target_count
        assert len(component.owner_ids) >= 1
        # every group component belongs to exactly one owner: primary group
        # keys are owner-prefixed, and cross-task union is owner-scoped (B9.4)
        assert len(component.owner_ids) == 1


def test_pack_components_into_outer_folds_never_splits_a_component():
    _users, targets, evidence_records = _load()
    components = build_group_components(targets, evidence_records)
    assignment = pack_components_into_outer_folds(components, n_outer_folds=5, seed=7)

    assert set(assignment) == {c.component_id for c in components}
    assert all(0 <= fold_index < 5 for fold_index in assignment.values())
    # trivially true (dict has one entry per component_id) -- the real
    # guarantee under test is that every *target* inside a component lands
    # in that component's single assigned fold, checked via the summary:
    summary = summarize_outer_fold_packing(components, assignment, n_outer_folds=5)
    assert sum(row["target_count"] for row in summary) == len(targets)


def test_pack_components_into_outer_folds_is_deterministic_given_the_same_seed():
    _users, targets, evidence_records = _load()
    components = build_group_components(targets, evidence_records)
    first = pack_components_into_outer_folds(components, n_outer_folds=4, seed=11)
    second = pack_components_into_outer_folds(components, n_outer_folds=4, seed=11)
    assert first == second


def test_pack_components_into_outer_folds_balances_target_counts_reasonably():
    _users, targets, evidence_records = _load()
    components = build_group_components(targets, evidence_records)
    assignment = pack_components_into_outer_folds(components, n_outer_folds=5, seed=3)
    summary = summarize_outer_fold_packing(components, assignment, n_outer_folds=5)
    counts = [row["target_count"] for row in summary]
    # no fold should be wildly out of balance relative to the ideal even split
    ideal = len(targets) / 5
    assert all(count > 0 for count in counts)
    assert max(counts) < ideal * 1.5


# --- B15: the packer's determinism/seed-sensitivity contract ---------------


def _equal_sized_synthetic_components(n: int) -> tuple[GroupComponent, ...]:
    return tuple(
        GroupComponent(
            component_id=f"component::c{i:02d}",
            primary_group_keys=(f"g{i}",),
            target_ids=(f"t{i}",),
            task_type_counts=(("qa", 1),),
            owner_ids=frozenset({f"p{i}"}),
        )
        for i in range(n)
    )


def test_pack_components_same_seed_is_fully_deterministic():
    components = _equal_sized_synthetic_components(8)
    first = pack_components_into_outer_folds(components, n_outer_folds=3, seed=42)
    second = pack_components_into_outer_folds(components, n_outer_folds=3, seed=42)
    assert first == second


def test_pack_components_different_seed_changes_tie_order_for_equal_sized_components():
    # B15 regression: the old implementation shuffled by seed and then
    # re-sorted by (-target_count, component_id) -- since component_id
    # alone is already a full order, the seed had zero effect. With eight
    # equal-sized (target_count=1) components, different seeds must be able
    # to produce different assignments.
    components = _equal_sized_synthetic_components(8)
    assignments = {
        seed: tuple(sorted(pack_components_into_outer_folds(components, n_outer_folds=3, seed=seed).items()))
        for seed in range(12)
    }
    distinct = set(assignments.values())
    assert len(distinct) > 1, "expected different seeds to produce different tie-break assignments"


def test_pack_components_every_component_always_atomic():
    components = _equal_sized_synthetic_components(10)
    for seed in range(5):
        assignment = pack_components_into_outer_folds(components, n_outer_folds=4, seed=seed)
        # one and only one fold index per component_id -- a component can
        # never be split, by construction of the dict return type, but
        # assert the full coverage invariant explicitly here too
        assert set(assignment.keys()) == {c.component_id for c in components}


def test_pack_components_rejects_empty_components():
    with pytest.raises(ValueError, match="must not be empty"):
        pack_components_into_outer_folds((), n_outer_folds=2, seed=1)


def test_pack_components_rejects_duplicate_component_id():
    a = _equal_sized_synthetic_components(1)[0]
    duplicate = GroupComponent(
        component_id=a.component_id,
        primary_group_keys=("gX",),
        target_ids=("tX",),
        task_type_counts=(("qa", 1),),
        owner_ids=frozenset({"pX"}),
    )
    with pytest.raises(ValueError, match="duplicate component_id"):
        pack_components_into_outer_folds((a, duplicate), n_outer_folds=2, seed=1)


def test_pack_components_rejects_fewer_than_two_outer_folds():
    components = _equal_sized_synthetic_components(3)
    with pytest.raises(ValueError, match="n_outer_folds must be >= 2"):
        pack_components_into_outer_folds(components, n_outer_folds=1, seed=1)
    with pytest.raises(ValueError, match="n_outer_folds must be >= 2"):
        pack_components_into_outer_folds(components, n_outer_folds=0, seed=1)


def test_pack_components_rejects_more_outer_folds_than_components():
    components = _equal_sized_synthetic_components(3)
    with pytest.raises(ValueError, match="must not exceed the number of components"):
        pack_components_into_outer_folds(components, n_outer_folds=4, seed=1)


def test_pack_components_assignment_never_missing_or_extra_relative_to_input():
    components = _equal_sized_synthetic_components(9)
    assignment = pack_components_into_outer_folds(components, n_outer_folds=3, seed=5)
    expected_ids = {c.component_id for c in components}
    assert set(assignment.keys()) == expected_ids
    assert len(assignment) == len(components)
