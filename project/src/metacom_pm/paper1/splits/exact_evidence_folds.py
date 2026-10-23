"""Primary group-component construction + a deterministic outer-fold packer.

Primary grouping keys (frozen, AGENTS.md / execution reconciliation):

- QA: ``owner + question_group_id`` (every question in one session's group,
  or the per-owner ``timeline`` group, shares one group).
- Summary: one target per summary item; unioned with other targets only via
  the exact-evidence-fingerprint step below.
- DG: one target per subsequent-topic scenario; same union-only-by-fingerprint
  treatment.

Cross-task/cross-group union happens *only* when two targets' canonical,
owner-namespaced evidence-set fingerprints are byte-identical (rule 5 in the
execution reconciliation doc). This module never unions targets just because
they touch overlapping sessions -- that broader connected-component notion
exists only as ``build_shared_session_sensitivity_components``, explicitly
kept out of ``group_component_id`` and usable for sensitivity
analysis only (rule 6).

B9/B14 terminology note (important -- do not conflate the two): the
union-find merge below produces **group components**
(``GroupComponentAssignment.group_component_id``, status
``PREPACK_EXACT_EVIDENCE_COMPONENT``): atomic, unsplittable packing units
that must never be separated across an outer train/held-out split. This is
*not* the same thing as an outer cross-validation fold. 514 primary group
keys collapsing to 477 components is not "477-fold CV" -- it is 477
indivisible pre-pack units still waiting to be packed into whatever number
of actual outer folds the M2 freeze decides on. B14: this is no longer
expressed by writing the component id into the shared, frozen
``contracts.FoldAssignment.fold_id`` field -- a field literally named
``fold_id`` invited exactly the "is this the outer fold" confusion the B9
docstring caveat was trying to prevent. ``GroupComponentAssignment`` is a
type this module owns outright, with a field named ``group_component_id``
and no ``fold_id`` field at all; ``contracts.py`` is not modified. Outer-fold
packing itself is implemented here (``pack_components_into_outer_folds``)
but not invoked by the M1-B manifest-generation script: this round does not
choose n_outer_folds or a seed (status
``OUTER_FOLD_PACKING_PENDING_M2_FREEZE``).

B8: gold-adjacent evidence is consumed here exclusively via
``metacom_pm.paper1.splits.evidence.SplitEvidenceRecord`` -- this module
never reads ``Target.evidence_refs`` (that field no longer exists on
``Target`` at all) or any raw ``.evidence``/``.related_sessions`` field
directly; everything is joined in by ``target_id`` from records built by
``enumerate_split_evidence``.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Target
from metacom_pm.paper1.splits.evidence import SplitEvidenceRecord

GROUP_COMPONENT_STATUS = "PREPACK_EXACT_EVIDENCE_COMPONENT"
OUTER_FOLD_PACKING_STATUS = "OUTER_FOLD_PACKING_PENDING_M2_FREEZE"


def canonical_evidence_fingerprint(owner_id: str, refs: tuple[str, ...]) -> str | None:
    """Sha256 of the owner-namespaced, sorted, deduplicated evidence/reference-id set.

    Owner-namespaced because the public artifact has at least one real
    cross-owner literal session-id collision: session id ``esc1198``
    belongs to both owner ``p13`` and owner ``p18`` (verified directly
    against ``data/external/evo_emo.json``). Without namespacing by owner,
    two different owners whose targets happened to cite an identical
    evidence-ref *set* would be unioned into the same fold -- a real
    cross-owner leak risk, not merely a hypothetical one.
    """

    deduped = sorted(set(refs))
    if not deduped:
        return None
    payload = owner_id + "||" + "|".join(deduped)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        self._parent.setdefault(key, key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return
        # Deterministic merge direction so the resulting tree (and therefore
        # the final component membership) never depends on call order.
        if root_a < root_b:
            self._parent[root_b] = root_a
        else:
            self._parent[root_a] = root_b

    def components(self, keys: set[str]) -> dict[str, tuple[str, ...]]:
        buckets: dict[str, list[str]] = {}
        for key in keys:
            buckets.setdefault(self.find(key), []).append(key)
        return {root: tuple(sorted(members)) for root, members in buckets.items()}


def _group_component_id(members: tuple[str, ...]) -> str:
    digest = hashlib.sha256("|".join(members).encode("utf-8")).hexdigest()
    return f"component::{digest}"


def _join_targets_with_evidence(
    targets: tuple[Target, ...], evidence_records: tuple[SplitEvidenceRecord, ...]
) -> dict[str, SplitEvidenceRecord]:
    """B22: fail-closed target<->evidence join.

    A silent join bug here (a missing/duplicate/extra evidence record, or one
    whose owner/task/group-key metadata quietly disagrees with the target it
    is keyed to) would corrupt the fold-fingerprint computation without ever
    raising -- exactly the kind of error the rest of this module's owner-
    namespacing and identity-validation work is meant to prevent. Every one
    of the following is checked and raises immediately, rather than trusting
    a bare dict lookup:

    - no duplicate ``target_id`` across ``evidence_records``;
    - the set of ``target_id`` values in ``evidence_records`` exactly equals
      the set in ``targets`` (no missing, no extra);
    - for every target, its evidence record's ``owner_id``, ``task_type``,
      and ``primary_group_key`` all match the target's own.
    """

    evidence_ids = [r.target_id for r in evidence_records]
    if len(evidence_ids) != len(set(evidence_ids)):
        duplicates = sorted({t for t in evidence_ids if evidence_ids.count(t) > 1})
        raise ValueError(f"duplicate target_id in evidence_records: {duplicates}")

    evidence_by_target = {r.target_id: r for r in evidence_records}
    target_ids = {t.target_id for t in targets}
    evidence_target_ids = set(evidence_by_target)

    missing = target_ids - evidence_target_ids
    if missing:
        raise ValueError(f"{len(missing)} target(s) have no matching evidence record: {sorted(missing)[:5]}...")
    extra = evidence_target_ids - target_ids
    if extra:
        raise ValueError(f"{len(extra)} evidence record(s) reference unknown target_id: {sorted(extra)[:5]}...")

    for target in targets:
        record = evidence_by_target[target.target_id]
        if record.owner_id != target.owner_id:
            raise ValueError(
                f"evidence/target owner mismatch for {target.target_id!r}: "
                f"evidence owner {record.owner_id!r} != target owner {target.owner_id!r}"
            )
        if record.task_type is not target.task_type:
            raise ValueError(
                f"evidence/target task_type mismatch for {target.target_id!r}: "
                f"evidence {record.task_type!r} != target {target.task_type!r}"
            )
        if record.primary_group_key != target.primary_group_key:
            raise ValueError(
                f"evidence/target primary_group_key mismatch for {target.target_id!r}: "
                f"evidence {record.primary_group_key!r} != target {target.primary_group_key!r}"
            )

    return evidence_by_target


def _group_key_components(
    targets: tuple[Target, ...], evidence_records: tuple[SplitEvidenceRecord, ...]
) -> tuple[dict[str, str | None], dict[str, tuple[str, ...]]]:
    """Shared core: fingerprint every target, union primary group keys on exact match.

    Returns (fingerprint_by_target_id, component_members_by_group_key), where
    the second dict maps every primary_group_key to the full sorted tuple of
    group keys in its component (including itself).
    """

    evidence_by_target = _join_targets_with_evidence(targets, evidence_records)
    fingerprint_by_target = {
        target.target_id: canonical_evidence_fingerprint(
            target.owner_id, evidence_by_target[target.target_id].evidence_refs
        )
        for target in targets
    }

    uf = _UnionFind()
    all_group_keys = {t.primary_group_key for t in targets}
    for key in all_group_keys:
        uf.find(key)

    groups_by_fingerprint: dict[str, set[str]] = {}
    for target in targets:
        fingerprint = fingerprint_by_target[target.target_id]
        if fingerprint is None:
            continue
        groups_by_fingerprint.setdefault(fingerprint, set()).add(target.primary_group_key)

    for group_keys in groups_by_fingerprint.values():
        ordered = sorted(group_keys)
        for other in ordered[1:]:
            uf.union(ordered[0], other)

    components = uf.components(all_group_keys)
    members_by_group_key = {
        group_key: members for members in components.values() for group_key in members
    }
    return fingerprint_by_target, members_by_group_key


@dataclass(frozen=True)
class GroupComponentAssignment:
    """One target's group-component identity. B14: owned entirely by
    ``metacom_pm.paper1.splits``, not the shared ``contracts.FoldAssignment``.

    B9 found that writing the group-component id into
    ``FoldAssignment.fold_id`` (a field name owned by Codex A's shared,
    frozen contract) invited exactly the confusion it was trying to
    document away: a field literally named ``fold_id`` reads as "the outer
    CV fold", no matter how much docstring disclaims that. B14 removes the
    ambiguity structurally instead of by caveat: this type is defined here,
    has no field named ``fold_id`` at all, and is never constructed from or
    coerced into ``contracts.FoldAssignment``. ``contracts.py`` itself is
    untouched -- this is a new, independent type, not a change to the
    shared contract.

    ``group_component_id`` is the same value the old ``fold_id`` held
    (identical hashes, identical grouping) -- only the field name and type
    changed, not the semantics. Status is always ``PREPACK_EXACT_EVIDENCE_
    COMPONENT`` (``GROUP_COMPONENT_STATUS``): this is *not* an outer
    cross-validation fold index, see the module docstring.
    """

    target_id: str
    task_type: TaskType
    group_component_id: str
    primary_group_key: str
    exact_evidence_fingerprint: str | None
    all_arms_seeds_repeats_bound: bool
    target_outcome_excluded_from_fit: bool


def build_group_component_assignments(
    targets: tuple[Target, ...], evidence_records: tuple[SplitEvidenceRecord, ...]
) -> tuple[GroupComponentAssignment, ...]:
    """One ``GroupComponentAssignment`` per target (B14, replaces the old
    ``FoldAssignment``-based ``build_fold_assignments``).

    Deliberately a *different function* from actual outer-fold packing
    (``pack_components_into_outer_folds``): this only assigns each target to
    its atomic pre-pack component, never to one of N outer folds.
    ``evidence_records`` must come from
    ``metacom_pm.paper1.splits.evidence.enumerate_split_evidence`` over the
    same ``users``/``targets`` -- joined here by ``target_id``, never read
    off ``Target`` itself (B8: ``Target`` carries no evidence field).
    """

    fingerprint_by_target, members_by_group_key = _group_key_components(targets, evidence_records)
    component_id_by_group_key = {
        group_key: _group_component_id(members) for group_key, members in members_by_group_key.items()
    }

    assignments = []
    for target in targets:
        assignments.append(
            GroupComponentAssignment(
                target_id=target.target_id,
                task_type=target.task_type,
                group_component_id=component_id_by_group_key[target.primary_group_key],
                primary_group_key=target.primary_group_key,
                exact_evidence_fingerprint=fingerprint_by_target[target.target_id],
                all_arms_seeds_repeats_bound=True,
                target_outcome_excluded_from_fit=True,
            )
        )
    return tuple(assignments)


@dataclass(frozen=True)
class GroupComponent:
    """One atomic, unsplittable exact-evidence group component.

    Aggregated purely from outcome-blind identity fields (target counts,
    task-type counts, owner set) -- exactly what
    ``pack_components_into_outer_folds`` needs to balance, and nothing that
    could leak a gold answer.
    """

    component_id: str
    primary_group_keys: tuple[str, ...]
    target_ids: tuple[str, ...]
    task_type_counts: tuple[tuple[str, int], ...]
    owner_ids: frozenset[str]

    @property
    def target_count(self) -> int:
        return len(self.target_ids)


def build_group_components(
    targets: tuple[Target, ...], evidence_records: tuple[SplitEvidenceRecord, ...]
) -> tuple[GroupComponent, ...]:
    """The full per-component aggregation used by the outer-fold packer."""

    _fingerprint_by_target, members_by_group_key = _group_key_components(targets, evidence_records)
    targets_by_group_key: dict[str, list[Target]] = {}
    for target in targets:
        targets_by_group_key.setdefault(target.primary_group_key, []).append(target)

    seen_component_ids: dict[str, GroupComponent] = {}
    for group_key, members in members_by_group_key.items():
        component_id = _group_component_id(members)
        if component_id in seen_component_ids:
            continue
        component_targets = [t for gk in members for t in targets_by_group_key.get(gk, ())]
        task_counts: dict[str, int] = {}
        for t in component_targets:
            task_counts[t.task_type.value] = task_counts.get(t.task_type.value, 0) + 1
        seen_component_ids[component_id] = GroupComponent(
            component_id=component_id,
            primary_group_keys=members,
            target_ids=tuple(sorted(t.target_id for t in component_targets)),
            task_type_counts=tuple(sorted(task_counts.items())),
            owner_ids=frozenset(t.owner_id for t in component_targets),
        )
    return tuple(sorted(seen_component_ids.values(), key=lambda c: c.component_id))


def pack_components_into_outer_folds(
    components: tuple[GroupComponent, ...], n_outer_folds: int, seed: int
) -> dict[str, int]:
    """Deterministically pack whole components into ``n_outer_folds`` outer folds.

    A component is always assigned in full to exactly one outer fold (never
    split), so every arm/seed/repeat of every target inside it lands in the
    same outer fold once this mapping is applied. Outcome-blind: balances on
    target count (primary objective, largest-first greedy bin-balancing) and
    reports -- and lets the caller inspect -- the resulting task-type and
    owner distribution per fold, but never reads any answer/gold/outcome
    field.

    B15 fix: an earlier version shuffled by ``seed`` and then re-sorted by
    ``(-target_count, component_id)`` -- since every component already has a
    globally unique ``component_id``, that secondary sort key was a full
    total order on its own, so the seeded shuffle changed nothing; the same
    tie order came out for every seed. Fixed by sorting on ``-target_count``
    *alone* (Python's ``sorted`` is stable, so components with equal
    ``target_count`` keep whatever relative order the seeded shuffle put
    them in) -- ``component_id`` never enters the comparison. The shuffle's
    own input order is itself deterministic (components sorted by
    ``component_id`` first), so the same ``(components, n_outer_folds,
    seed)`` always reproduces the same assignment, and a different ``seed``
    can change the tie order -- and therefore the final fold assignment --
    for equally-sized components.
    """

    if not components:
        raise ValueError("components must not be empty")
    component_ids = [c.component_id for c in components]
    if len(component_ids) != len(set(component_ids)):
        raise ValueError("components must not contain duplicate component_id values")
    if n_outer_folds < 2:
        raise ValueError("n_outer_folds must be >= 2")
    if n_outer_folds > len(components):
        raise ValueError("n_outer_folds must not exceed the number of components")

    deterministic_base_order = sorted(components, key=lambda c: c.component_id)
    shuffled = list(deterministic_base_order)
    random.Random(seed).shuffle(shuffled)
    # Stable sort: ties (equal target_count) keep the seeded shuffle's
    # relative order instead of falling back to a seed-independent key.
    ordered = sorted(shuffled, key=lambda c: -c.target_count)

    fold_target_counts = [0] * n_outer_folds
    fold_task_counts: list[dict[str, int]] = [dict() for _ in range(n_outer_folds)]
    assignment: dict[str, int] = {}

    for component in ordered:
        dominant_task = max(dict(component.task_type_counts).items(), key=lambda kv: kv[1])[0]
        best_fold = min(
            range(n_outer_folds),
            key=lambda i: (
                fold_target_counts[i],
                fold_task_counts[i].get(dominant_task, 0),
                i,
            ),
        )
        assignment[component.component_id] = best_fold
        fold_target_counts[best_fold] += component.target_count
        for task_name, count in component.task_type_counts:
            fold_task_counts[best_fold][task_name] = (
                fold_task_counts[best_fold].get(task_name, 0) + count
            )

    if set(assignment) != set(component_ids):
        raise AssertionError(
            "internal error: outer-fold assignment does not exactly cover every component"
        )
    return assignment


def summarize_outer_fold_packing(
    components: tuple[GroupComponent, ...], assignment: dict[str, int], n_outer_folds: int
) -> list[dict[str, object]]:
    """Per-outer-fold target/task/owner counts, for balance reporting/tests."""

    by_component = {c.component_id: c for c in components}
    summaries: list[dict[str, object]] = [
        {"outer_fold": i, "target_count": 0, "task_type_counts": {}, "owner_ids": set()}
        for i in range(n_outer_folds)
    ]
    for component_id, fold_index in assignment.items():
        component = by_component[component_id]
        row = summaries[fold_index]
        row["target_count"] += component.target_count
        for task_name, count in component.task_type_counts:
            row["task_type_counts"][task_name] = row["task_type_counts"].get(task_name, 0) + count
        row["owner_ids"] |= component.owner_ids
    for row in summaries:
        row["owner_count"] = len(row["owner_ids"])
        row["owner_ids"] = sorted(row["owner_ids"])
    return summaries


@dataclass(frozen=True)
class SharedSessionSensitivityComponent:
    """Sensitivity-only broad grouping: any shared session, not exact evidence match.

    Never feeds ``group_component_id``/``primary_group_key`` --
    AGENTS.md rule 6 requires this connected-component notion stay strictly
    a sensitivity check.
    """

    component_id: str
    target_ids: tuple[str, ...]


def _session_footprint(evidence_refs: tuple[str, ...], known_session_ids: set[str]) -> frozenset[str]:
    """Session ids referenced by an evidence/related-session ref list.

    B17: no longer combined with ``Target.context_session_ids`` (removed --
    the full ``dialog_history`` is strict-past for every target regardless
    of task type, so there is no more per-target "premise session" concept
    at all). This footprint is evidence-only, exactly like the primary
    exact-evidence fingerprint above -- the broader notion here is just
    "any shared session", not "exact identical evidence set".
    """

    footprint: set[str] = set()
    for ref in evidence_refs:
        prefix = ref.split(":", 1)[0]
        if prefix in known_session_ids:
            footprint.add(prefix)
    return frozenset(footprint)


def build_shared_session_sensitivity_components(
    targets: tuple[Target, ...],
    users: tuple[MemorySourceUser, ...],
    evidence_records: tuple[SplitEvidenceRecord, ...],
) -> tuple[SharedSessionSensitivityComponent, ...]:
    """Broad connected components of targets sharing any session, per owner.

    Already owner-scoped by construction (the union-find only ever links
    targets within the same ``owner_id``), so this one is not affected by
    the cross-owner fingerprint-collision risk that motivated namespacing
    ``canonical_evidence_fingerprint`` above. Sensitivity-only per AGENTS.md
    rule 6: reported separately, never used to compute the primary
    ``group_component_id``. Reads evidence only via ``evidence_records``
    (B8), joined by ``target_id`` through the same fail-closed join (B22) as
    the primary component construction.
    """

    evidence_by_record = _join_targets_with_evidence(targets, evidence_records)
    evidence_by_target = {target_id: r.evidence_refs for target_id, r in evidence_by_record.items()}
    sessions_by_owner = {u.owner_id: {s.session_id for s in u.sessions} for u in users}
    uf = _UnionFind()
    targets_by_owner: dict[str, list[Target]] = {}
    for target in targets:
        targets_by_owner.setdefault(target.owner_id, []).append(target)
        uf.find(target.target_id)

    for owner_id, owner_targets in targets_by_owner.items():
        known_session_ids = sessions_by_owner.get(owner_id, set())
        session_to_targets: dict[str, list[str]] = {}
        for target in owner_targets:
            footprint = _session_footprint(evidence_by_target[target.target_id], known_session_ids)
            for session_id in footprint:
                session_to_targets.setdefault(session_id, []).append(target.target_id)
        for target_ids in session_to_targets.values():
            ordered = sorted(target_ids)
            for other in ordered[1:]:
                uf.union(ordered[0], other)

    all_target_ids = {t.target_id for t in targets}
    components = uf.components(all_target_ids)
    return tuple(
        SharedSessionSensitivityComponent(
            component_id=_group_component_id(members),
            target_ids=members,
        )
        for members in sorted(components.values())
    )
