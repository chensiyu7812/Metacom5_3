from collections import defaultdict
from pathlib import Path

from metacom_pm.paper1.data.es_memeval import enumerate_targets, load_users, parse_users
from metacom_pm.paper1.splits import (
    GROUP_COMPONENT_STATUS,
    OUTER_FOLD_PACKING_STATUS,
    build_fold_assignments,
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
    users = parse_users(load_users(EVO_PATH))
    targets = enumerate_targets(users)
    evidence_records = enumerate_split_evidence(users)
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
    assignments = build_fold_assignments(targets, evidence_records)

    component_by_group: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        component_by_group[assignment.primary_group_key].add(assignment.fold_id)
    assert all(len(ids) == 1 for ids in component_by_group.values())


def test_fold_id_values_are_named_as_group_components_not_folds():
    # B9.1: FoldAssignment.fold_id (the shared frozen contract field) still
    # has to be populated, but its value must be legible as a group
    # component id, not something implying "the outer CV fold".
    _users, targets, evidence_records = _load()
    assignments = build_fold_assignments(targets, evidence_records)
    assert all(a.fold_id.startswith("component::") for a in assignments)
    assert all(not a.fold_id.startswith("fold::") for a in assignments)


def test_qa_targets_in_the_same_session_group_share_a_component():
    _users, targets, evidence_records = _load()
    assignments = {a.target_id: a for a in build_fold_assignments(targets, evidence_records)}

    p1_esc1024_targets = [t for t in targets if t.target_id.startswith("p1::esc1024::")]
    assert len(p1_esc1024_targets) >= 2
    component_ids = {assignments[t.target_id].fold_id for t in p1_esc1024_targets}
    assert len(component_ids) == 1


def test_cross_task_union_only_fires_on_byte_identical_owner_scoped_evidence():
    _users, targets, evidence_records = _load()
    assignments = build_fold_assignments(targets, evidence_records)
    evidence_by_target = {r.target_id: (r.owner_id, r.evidence_refs) for r in evidence_records}

    component_tasks: dict[str, set[str]] = defaultdict(set)
    component_members: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        component_tasks[assignment.fold_id].add(assignment.task_type.value)
        component_members[assignment.fold_id].add(assignment.target_id)

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
    assignments = {a.target_id: a for a in build_fold_assignments(targets, evidence_records)}
    evidence_by_target = {r.target_id: r.evidence_refs for r in evidence_records}

    summary_target_id = "p1::summary::5"
    dg_target_id = "p1::dg::1"
    assert evidence_by_target[summary_target_id] == evidence_by_target[dg_target_id]
    assert assignments[summary_target_id].fold_id == assignments[dg_target_id].fold_id


def test_fold_id_is_deterministic_across_repeated_runs():
    _users, targets, evidence_records = _load()
    first = {a.target_id: a.fold_id for a in build_fold_assignments(targets, evidence_records)}
    second = {a.target_id: a.fold_id for a in build_fold_assignments(targets, evidence_records)}
    assert first == second


def test_fold_assignment_always_excludes_target_outcome_from_fit():
    _users, targets, evidence_records = _load()
    targets = targets[:20]
    evidence_records = tuple(r for r in evidence_records if r.target_id in {t.target_id for t in targets})
    assignments = build_fold_assignments(targets, evidence_records)
    assert all(a.target_outcome_excluded_from_fit for a in assignments)
    assert all(a.all_arms_seeds_repeats_bound for a in assignments)


def test_shared_session_sensitivity_components_are_strictly_broader_than_primary_components():
    users, targets, evidence_records = _load()
    primary = build_fold_assignments(targets, evidence_records)
    sensitivity = build_shared_session_sensitivity_components(targets, users, evidence_records)

    n_primary_components = len({a.fold_id for a in primary})
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
    before = {a.target_id: a.fold_id for a in build_fold_assignments(targets, evidence_records)}
    build_shared_session_sensitivity_components(targets, users, evidence_records)
    after = {a.target_id: a.fold_id for a in build_fold_assignments(targets, evidence_records)}
    assert before == after


def test_status_constants_are_exactly_the_required_strings():
    assert GROUP_COMPONENT_STATUS == "PREPACK_EXACT_EVIDENCE_COMPONENT"
    assert OUTER_FOLD_PACKING_STATUS == "OUTER_FOLD_PACKING_PENDING_M2_FREEZE"


def test_group_components_are_consistent_with_fold_assignments():
    _users, targets, evidence_records = _load()
    assignments = build_fold_assignments(targets, evidence_records)
    components = build_group_components(targets, evidence_records)

    assert len({c.component_id for c in components}) == len({a.fold_id for a in assignments})
    assert sum(c.target_count for c in components) == len(targets)

    target_to_component = {a.target_id: a.fold_id for a in assignments}
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


def test_pack_components_into_outer_folds_rejects_invalid_fold_count():
    _users, targets, evidence_records = _load()
    components = build_group_components(targets, evidence_records)[:3]
    try:
        pack_components_into_outer_folds(components, n_outer_folds=0, seed=1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for n_outer_folds < 1")
