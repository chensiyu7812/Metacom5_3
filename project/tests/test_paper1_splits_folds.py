from collections import defaultdict
from pathlib import Path

from metacom_pm.paper1.data.es_memeval import enumerate_targets, load_users, parse_users
from metacom_pm.paper1.splits import (
    build_fold_assignments,
    build_shared_session_sensitivity_components,
    canonical_evidence_fingerprint,
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
    a = canonical_evidence_fingerprint(("x:1", "y:2", "x:1"))
    b = canonical_evidence_fingerprint(("y:2", "x:1"))
    assert a == b
    assert canonical_evidence_fingerprint(()) is None


def test_every_target_within_a_primary_group_shares_one_fold_id():
    _users, targets, evidence_records = _load()
    assignments = build_fold_assignments(targets, evidence_records)

    fold_by_group: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        fold_by_group[assignment.primary_group_key].add(assignment.fold_id)
    assert all(len(fold_ids) == 1 for fold_ids in fold_by_group.values())


def test_qa_targets_in_the_same_session_group_share_a_fold():
    _users, targets, evidence_records = _load()
    assignments = {a.target_id: a for a in build_fold_assignments(targets, evidence_records)}

    p1_esc1024_targets = [t for t in targets if t.target_id.startswith("p1::esc1024::")]
    assert len(p1_esc1024_targets) >= 2
    fold_ids = {assignments[t.target_id].fold_id for t in p1_esc1024_targets}
    assert len(fold_ids) == 1


def test_cross_task_union_only_fires_on_byte_identical_evidence_sets():
    _users, targets, evidence_records = _load()
    assignments = build_fold_assignments(targets, evidence_records)
    evidence_by_target = {r.target_id: r.evidence_refs for r in evidence_records}

    fold_tasks: dict[str, set[str]] = defaultdict(set)
    fold_members: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        fold_tasks[assignment.fold_id].add(assignment.task_type.value)
        fold_members[assignment.fold_id].add(assignment.target_id)

    mixed_task_folds = {fid: tasks for fid, tasks in fold_tasks.items() if len(tasks) > 1}
    assert len(mixed_task_folds) > 0, "expected at least one real cross-task union in the corpus"

    for fold_id in mixed_task_folds:
        member_ids = fold_members[fold_id]
        fingerprints = {
            canonical_evidence_fingerprint(evidence_by_target[tid]) for tid in member_ids
        }
        # every member of a cross-task-unioned fold must share the identical
        # non-null evidence fingerprint that caused the union
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


def test_shared_session_sensitivity_components_are_strictly_broader_than_primary_folds():
    users, targets, evidence_records = _load()
    primary = build_fold_assignments(targets, evidence_records)
    sensitivity = build_shared_session_sensitivity_components(targets, users, evidence_records)

    n_primary_folds = len({a.fold_id for a in primary})
    n_sensitivity_components = len(sensitivity)
    assert n_sensitivity_components < n_primary_folds

    # every target appears in exactly one sensitivity component
    all_target_ids = {t.target_id for t in targets}
    covered = set()
    for component in sensitivity:
        covered.update(component.target_ids)
    assert covered == all_target_ids


def test_primary_fold_assignment_is_untouched_by_broad_shared_session_grouping():
    # rule 6: the broad sensitivity grouping must never influence fold_id.
    users, targets, evidence_records = _load()
    before = {a.target_id: a.fold_id for a in build_fold_assignments(targets, evidence_records)}
    build_shared_session_sensitivity_components(targets, users, evidence_records)
    after = {a.target_id: a.fold_id for a in build_fold_assignments(targets, evidence_records)}
    assert before == after
