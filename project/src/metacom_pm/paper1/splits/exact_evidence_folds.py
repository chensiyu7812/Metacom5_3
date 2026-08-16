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
kept out of ``fold_id``/``group_component_id`` and usable for sensitivity
analysis only (rule 6).

B9 terminology note (important -- do not conflate the two): the union-find
merge below produces **group components** (``group_component_id``,
status ``PREPACK_EXACT_EVIDENCE_COMPONENT``): atomic, unsplittable packing
units that must never be separated across an outer train/held-out split.
This is *not* the same thing as an outer cross-validation fold. 514 primary
group keys collapsing to 477 components is not "477-fold CV" -- it is 477
indivisible pre-pack units still waiting to be packed into whatever number
of actual outer folds the M2 freeze decides on. ``FoldAssignment.fold_id``
(the shared, frozen contract field) is populated with the group-component id
because the contract requires *some* string there pre-freeze; read it as
"which atomic component", not "which of N outer folds". Outer-fold packing
itself is implemented here (``pack_components_into_outer_folds``) but not
invoked by the M1-B manifest-generation script: this round does not choose
n_outer_folds or a seed (status ``OUTER_FOLD_PACKING_PENDING_M2_FREEZE``).

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

from metacom_pm.paper1.contracts import FoldAssignment
from metacom_pm.paper1.data.es_memeval import Target, UserRecord
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


def _group_key_components(
    targets: tuple[Target, ...], evidence_records: tuple[SplitEvidenceRecord, ...]
) -> tuple[dict[str, str | None], dict[str, tuple[str, ...]]]:
    """Shared core: fingerprint every target, union primary group keys on exact match.

    Returns (fingerprint_by_target_id, component_members_by_group_key), where
    the second dict maps every primary_group_key to the full sorted tuple of
    group keys in its component (including itself).
    """

    evidence_by_target = {r.target_id: r for r in evidence_records}
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


def build_fold_assignments(
    targets: tuple[Target, ...], evidence_records: tuple[SplitEvidenceRecord, ...]
) -> tuple[FoldAssignment, ...]:
    """One ``FoldAssignment`` per target. ``fold_id`` holds a group-component id.

    See the module docstring's B9 note: this is a ``PREPACK_EXACT_EVIDENCE_
    COMPONENT`` id, not an outer cross-validation fold index.
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
            FoldAssignment(
                target_id=target.target_id,
                task_type=target.task_type,
                fold_id=component_id_by_group_key[target.primary_group_key],
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
    field. ``seed`` only breaks ties among equally-sized components, so the
    result is reproducible for a given ``(components, n_outer_folds, seed)``
    and does not depend on dict/set iteration order.
    """

    if n_outer_folds < 1:
        raise ValueError("n_outer_folds must be >= 1")

    rng = random.Random(seed)
    shuffled = list(components)
    rng.shuffle(shuffled)
    ordered = sorted(shuffled, key=lambda c: (-c.target_count, c.component_id))

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

    Never feeds ``fold_id``/``primary_group_key``/``group_component_id`` --
    AGENTS.md rule 6 requires this connected-component notion stay strictly
    a sensitivity check.
    """

    component_id: str
    target_ids: tuple[str, ...]


def _session_footprint(
    context_session_ids: tuple[str, ...], evidence_refs: tuple[str, ...], known_session_ids: set[str]
) -> frozenset[str]:
    footprint = set(context_session_ids)
    for ref in evidence_refs:
        prefix = ref.split(":", 1)[0]
        if prefix in known_session_ids:
            footprint.add(prefix)
    return frozenset(footprint)


def build_shared_session_sensitivity_components(
    targets: tuple[Target, ...],
    users: tuple[UserRecord, ...],
    evidence_records: tuple[SplitEvidenceRecord, ...],
) -> tuple[SharedSessionSensitivityComponent, ...]:
    """Broad connected components of targets sharing any session, per owner.

    Already owner-scoped by construction (the union-find only ever links
    targets within the same ``owner_id``), so this one is not affected by
    the cross-owner fingerprint-collision risk that motivated namespacing
    ``canonical_evidence_fingerprint`` above. Sensitivity-only per AGENTS.md
    rule 6: reported separately, never used to compute the primary
    ``fold_id``/``group_component_id``. Reads evidence only via
    ``evidence_records`` (B8), joined by ``target_id``.
    """

    evidence_by_target = {r.target_id: r.evidence_refs for r in evidence_records}
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
            footprint = _session_footprint(
                target.context_session_ids, evidence_by_target[target.target_id], known_session_ids
            )
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
