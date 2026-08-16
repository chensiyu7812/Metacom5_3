"""Primary fold construction: mechanical grouping + exact-evidence-only union.

Primary grouping keys (frozen, AGENTS.md / execution reconciliation):

- QA: ``owner + question_group_id`` (every question in one session's group,
  or the per-owner ``timeline`` group, shares one fold).
- Summary: one target per summary item; unioned with other targets only via
  the exact-evidence-fingerprint step below.
- DG: one target per subsequent-topic scenario; same union-only-by-fingerprint
  treatment.

Cross-task/cross-group union happens *only* when two targets' canonical
evidence-set fingerprints are byte-identical (rule 5 in the execution
reconciliation doc). This module never unions targets just because they touch
overlapping sessions -- that broader connected-component notion exists only
as ``build_shared_session_sensitivity_components``, explicitly kept out of
``fold_id`` and usable for sensitivity analysis only (rule 6).

B8: gold-adjacent evidence is consumed here exclusively via
``metacom_pm.paper1.splits.evidence.SplitEvidenceRecord`` -- this module
never reads ``Target.evidence_refs`` (that field no longer exists on
``Target`` at all) or any raw ``.evidence``/``.related_sessions`` field
directly; everything is joined in by ``target_id`` from records built by
``enumerate_split_evidence``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from metacom_pm.paper1.contracts import FoldAssignment
from metacom_pm.paper1.data.es_memeval import Target, UserRecord
from metacom_pm.paper1.splits.evidence import SplitEvidenceRecord


def canonical_evidence_fingerprint(refs: tuple[str, ...]) -> str | None:
    """Sha256 of the sorted, deduplicated evidence/reference-id set, or None if empty."""

    deduped = sorted(set(refs))
    if not deduped:
        return None
    return hashlib.sha256("|".join(deduped).encode("utf-8")).hexdigest()


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


def _fold_id_for_component(members: tuple[str, ...]) -> str:
    digest = hashlib.sha256("|".join(members).encode("utf-8")).hexdigest()
    return f"fold::{digest}"


def build_fold_assignments(
    targets: tuple[Target, ...], evidence_records: tuple[SplitEvidenceRecord, ...]
) -> tuple[FoldAssignment, ...]:
    """One ``FoldAssignment`` per target, with exact-evidence-only cross-group union.

    ``evidence_records`` must come from
    ``metacom_pm.paper1.splits.evidence.enumerate_split_evidence`` over the
    same ``users``/``targets`` -- joined here by ``target_id``, never read
    off ``Target`` itself (B8: ``Target`` carries no evidence field).
    """

    uf = _UnionFind()
    all_group_keys = {t.primary_group_key for t in targets}
    for key in all_group_keys:
        uf.find(key)

    evidence_by_target = {r.target_id: r for r in evidence_records}
    fingerprint_by_target = {
        target.target_id: canonical_evidence_fingerprint(
            evidence_by_target[target.target_id].evidence_refs
        )
        for target in targets
    }
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
    fold_id_by_group_key = {
        group_key: _fold_id_for_component(members)
        for root, members in components.items()
        for group_key in members
    }

    assignments = []
    for target in targets:
        assignments.append(
            FoldAssignment(
                target_id=target.target_id,
                task_type=target.task_type,
                fold_id=fold_id_by_group_key[target.primary_group_key],
                primary_group_key=target.primary_group_key,
                exact_evidence_fingerprint=fingerprint_by_target[target.target_id],
                all_arms_seeds_repeats_bound=True,
                target_outcome_excluded_from_fit=True,
            )
        )
    return tuple(assignments)


@dataclass(frozen=True)
class SharedSessionSensitivityComponent:
    """Sensitivity-only broad grouping: any shared session, not exact evidence match.

    Never feeds ``fold_id``/``primary_group_key`` -- AGENTS.md rule 6 requires
    this connected-component notion stay strictly a sensitivity check.
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

    Sensitivity-only per AGENTS.md rule 6: reported separately, never used to
    compute the primary ``fold_id``. Reads evidence only via
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
            component_id=_fold_id_for_component(members),
            target_ids=members,
        )
        for members in sorted(components.values())
    )
