"""Zero-outcome candidate census over MP/MS/ME (B12/B17/B19/B25).

Reports two explicitly separate layers (B19.5):

1. **Eligible candidate pool** (``build_eligible_pool`` /
   ``es_memeval_public_candidate_eligible_pool_v1.jsonl``): per (owner,
   head), how many MP/MS/ME candidates exist at all. B17: this is now the
   *same* pool for every target of that owner, because the full
   ``dialog_history`` is strict-past for every target regardless of task
   type (verified against the official evaluation harness -- see
   ``metacom_pm.paper1.data.memory_source`` module docstring). This layer is
   target-invariant by construction.
2. **Per-target scoring** (``build_census`` / the existing
   ``TargetHeadCensusRow`` rows): outcome-blind lexical-overlap/age/
   retrieval-rank diagnostics computed against that target's own
   ``visible_query_text`` (QA/Summary's actual officially-asked question --
   not gold) where one exists. DG has no such text pre-generation, so all of
   those fields are reported as ``None`` (B19.4), never approximated from
   ``related_sessions``/``topic``.

B25 correction: the field previously named ``already_visible`` here was
never the authoritative ``mp_profile_already_visible``/
``ms_memory_already_visible``/``me_experience_already_visible`` construct
defined in ``docs/PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md``
sections 5.2-5.4 ("当前窗口是否已经明确包含该 fact") -- it is a much cruder
lowercase ``[a-z]{3,}`` word-set Jaccard overlap against the candidate,
thresholded at 0.6. Calling it ``already_visible`` implied it was that
authoritative feature; it is not, and is renamed
``lexical_candidate_query_jaccard_ge_0_6_proxy`` throughout this module and
every consumer to make that explicit. The authoritative already-visible
construct itself remains unimplemented (see
``metacom_pm.paper1.features.feature_readiness_audit``'s feature inventory,
status ``NOT_IMPLEMENTED_PENDING_MECHANICAL_DEFINITION`` -- no new heuristic
or threshold is invented for it this round).

The **final retrieved bundle / top-k / token cap** is a third, separate
concept this module does not compute at all -- that remains an M2-freeze
decision (``FINAL_BUNDLE_STATUS`` below), not something to self-select this
round.

No candidate is scored for usefulness, no PASS/FAIL judgment is made, and no
gold answer/summary/observation field is ever read. This module imports only
``MemorySourceUser``/``Target`` from ``metacom_pm.paper1.data.memory_source``,
the sanitized runtime module that never constructs an evidence-bearing type
in the first place; it never imports ``metacom_pm.paper1.data.es_memeval``,
``metacom_pm.paper1.data.materializer``, or ``metacom_pm.paper1.splits.
evidence`` at all.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from metacom_pm.paper1.candidates import compile_candidate_bundle
from metacom_pm.paper1.contracts import CandidateRecord, Head, TaskType
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Target
from metacom_pm.paper1.memory.me import extract_action_result_episodes
from metacom_pm.paper1.memory.mp import extract_profile_disclosures
from metacom_pm.paper1.memory.ms import extract_session_documents

LEXICAL_CANDIDATE_QUERY_JACCARD_GE_0_6_PROXY_THRESHOLD = 0.6
FINAL_BUNDLE_STATUS = "PENDING_M2_FREEZE_NOT_SELECTED_THIS_ROUND"

_WORD_PATTERN = re.compile(r"[a-z]{3,}")


@lru_cache(maxsize=4096)
def _word_set(text: str) -> frozenset[str]:
    return frozenset(_WORD_PATTERN.findall(text.lower()))


def _lexical_overlap(candidate_words: frozenset[str], context_words: frozenset[str]) -> float | None:
    if not context_words or not candidate_words:
        return None
    intersection = len(candidate_words & context_words)
    union = len(candidate_words | context_words)
    return intersection / union if union else None


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class CandidateFeatureSnapshot:
    candidate_id: str
    token_count: int
    age_days: int | None
    # B25: renamed from `already_visible` -- this is a lowercase [a-z]{3,}
    # word-set Jaccard overlap proxy thresholded at 0.6, NOT the
    # authoritative mp/ms/me_*_already_visible construct from the execution
    # blueprint. See module docstring.
    lexical_candidate_query_jaccard_ge_0_6_proxy: bool | None
    lexical_overlap: float | None
    retrieval_rank: int | None


@dataclass(frozen=True)
class TargetHeadCensusRow:
    target_id: str
    task_type: TaskType
    owner_id: str
    head: Head
    identity_anomaly: bool
    has_visible_query: bool
    candidate_count: int
    coverage: bool
    token_count_min: int | None
    token_count_mean: float | None
    token_count_max: int | None
    age_days_min: int | None
    age_days_mean: float | None
    age_days_max: int | None
    lexical_candidate_query_jaccard_ge_0_6_proxy_count: int
    top_candidate_lexical_overlap: float | None
    candidates: tuple[CandidateFeatureSnapshot, ...]

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-zero-outcome-census-row-v3",
            "target_id": self.target_id,
            "task_type": self.task_type.value,
            "owner_id": self.owner_id,
            "head": self.head.value,
            "identity_anomaly": self.identity_anomaly,
            "has_visible_query": self.has_visible_query,
            "candidate_count": self.candidate_count,
            "coverage": self.coverage,
            "token_count_min": self.token_count_min,
            "token_count_mean": self.token_count_mean,
            "token_count_max": self.token_count_max,
            "age_days_min": self.age_days_min,
            "age_days_mean": self.age_days_mean,
            "age_days_max": self.age_days_max,
            "lexical_candidate_query_jaccard_ge_0_6_proxy_count": (
                self.lexical_candidate_query_jaccard_ge_0_6_proxy_count
            ),
            "top_candidate_lexical_overlap": self.top_candidate_lexical_overlap,
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "token_count": c.token_count,
                    "age_days": c.age_days,
                    "lexical_candidate_query_jaccard_ge_0_6_proxy": (
                        c.lexical_candidate_query_jaccard_ge_0_6_proxy
                    ),
                    "lexical_overlap": c.lexical_overlap,
                    "retrieval_rank": c.retrieval_rank,
                }
                for c in self.candidates
            ],
        }


@dataclass(frozen=True)
class EligiblePoolRow:
    """Layer 1 (B19.5): the target-invariant candidate pool for one (owner, head).

    B17: every target of this owner draws on exactly this same pool -- the
    full ``dialog_history`` is strict-past regardless of task type -- so
    this is reported once per owner, not once per target.
    """

    owner_id: str
    head: Head
    eligible_candidate_count: int

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-zero-outcome-eligible-pool-row-v1",
            "owner_id": self.owner_id,
            "head": self.head.value,
            "eligible_candidate_count": self.eligible_candidate_count,
        }


def _anchor_date(user: MemorySourceUser) -> date | None:
    """B19.2: age is relative to the evaluation boundary -- the owner's last
    ``dialog_history`` timestamp -- the same anchor for every target of that
    owner (no more per-target "current session")."""

    if not user.sessions:
        return None
    return max(s.date for s in user.sessions)


def _query_words(target: Target) -> frozenset[str] | None:
    """B19.3/B19.4: the actual officially-asked question text for QA/Summary;
    ``None`` for DG (no static current-dialogue state exists pre-generation --
    never approximated from related_sessions/topic)."""

    if target.visible_query_text is None:
        return None
    return _word_set(target.visible_query_text)


def _score_candidates(
    candidates: tuple[CandidateRecord, ...],
    *,
    anchor: date | None,
    query_words: frozenset[str] | None,
) -> tuple[CandidateFeatureSnapshot, ...]:
    def _age_days(candidate: CandidateRecord) -> int | None:
        observed_at = candidate.lineage.observed_at
        if anchor is None or not observed_at:
            return None
        return (anchor - date.fromisoformat(observed_at)).days

    if query_words is None:
        # B19.4: no static query exists (DG pre-generation) -- overlap/rank
        # are null/N/A, never computed against related_sessions/topic.
        return tuple(
            CandidateFeatureSnapshot(
                candidate_id=c.candidate_id,
                token_count=c.token_count,
                age_days=_age_days(c),
                lexical_candidate_query_jaccard_ge_0_6_proxy=None,
                lexical_overlap=None,
                retrieval_rank=None,
            )
            for c in candidates
        )

    scored: list[tuple[float, int, str, CandidateFeatureSnapshot]] = []
    for candidate in candidates:
        candidate_words = _word_set(candidate.content)
        overlap = _lexical_overlap(candidate_words, query_words)
        jaccard_proxy = (
            overlap is not None and overlap >= LEXICAL_CANDIDATE_QUERY_JACCARD_GE_0_6_PROXY_THRESHOLD
        )
        chronological_rank = candidate.raw_descriptors.get("session_chronological_rank")
        recency_key = chronological_rank if isinstance(chronological_rank, int) else -1
        sort_key = (-(overlap if overlap is not None else -1.0), -recency_key, candidate.candidate_id)
        scored.append(
            (
                sort_key[0],
                sort_key[1],
                sort_key[2],
                CandidateFeatureSnapshot(
                    candidate_id=candidate.candidate_id,
                    token_count=candidate.token_count,
                    age_days=_age_days(candidate),
                    lexical_candidate_query_jaccard_ge_0_6_proxy=jaccard_proxy,
                    lexical_overlap=overlap,
                    retrieval_rank=0,
                ),
            )
        )
    scored.sort(key=lambda row: (row[0], row[1], row[2]))
    ranked = tuple(
        CandidateFeatureSnapshot(
            candidate_id=snap.candidate_id,
            token_count=snap.token_count,
            age_days=snap.age_days,
            lexical_candidate_query_jaccard_ge_0_6_proxy=(
                snap.lexical_candidate_query_jaccard_ge_0_6_proxy
            ),
            lexical_overlap=snap.lexical_overlap,
            retrieval_rank=rank,
        )
        for rank, (*_key, snap) in enumerate(scored, start=1)
    )
    return ranked


def _row_for_head(
    target: Target,
    head: Head,
    candidates: tuple[CandidateRecord, ...],
    *,
    anchor: date | None,
) -> TargetHeadCensusRow:
    query_words = _query_words(target)
    snapshots = _score_candidates(candidates, anchor=anchor, query_words=query_words)
    token_counts = [s.token_count for s in snapshots]
    ages = [s.age_days for s in snapshots if s.age_days is not None]
    jaccard_proxy_count = sum(
        1 for s in snapshots if s.lexical_candidate_query_jaccard_ge_0_6_proxy
    )
    top_overlap = snapshots[0].lexical_overlap if snapshots else None
    return TargetHeadCensusRow(
        target_id=target.target_id,
        task_type=target.task_type,
        owner_id=target.owner_id,
        head=head,
        identity_anomaly=target.identity_anomaly is not None,
        has_visible_query=target.visible_query_text is not None,
        candidate_count=len(snapshots),
        coverage=len(snapshots) > 0,
        token_count_min=min(token_counts) if token_counts else None,
        token_count_mean=statistics.fmean(token_counts) if token_counts else None,
        token_count_max=max(token_counts) if token_counts else None,
        age_days_min=min(ages) if ages else None,
        age_days_mean=statistics.fmean(ages) if ages else None,
        age_days_max=max(ages) if ages else None,
        lexical_candidate_query_jaccard_ge_0_6_proxy_count=jaccard_proxy_count,
        top_candidate_lexical_overlap=top_overlap,
        candidates=snapshots,
    )


def build_eligible_pool(users: tuple[MemorySourceUser, ...]) -> tuple[EligiblePoolRow, ...]:
    """Layer 1 (B19.5): the target-invariant MP/MS/ME pool size per owner."""

    rows: list[EligiblePoolRow] = []
    for user in users:
        rows.append(EligiblePoolRow(user.owner_id, Head.MP, len(extract_profile_disclosures(user))))
        rows.append(EligiblePoolRow(user.owner_id, Head.MS, len(extract_session_documents(user))))
        rows.append(EligiblePoolRow(user.owner_id, Head.ME, len(extract_action_result_episodes(user))))
    return tuple(rows)


def build_census(
    users: tuple[MemorySourceUser, ...], targets: tuple[Target, ...]
) -> tuple[TargetHeadCensusRow, ...]:
    """Layer 2 (B19.5): per-target scoring against ``visible_query_text``."""

    users_by_owner = {u.owner_id: u for u in users}
    # Extraction is per-user and target-independent (see `metacom_pm.paper1.memory`
    # docstring); precomputing once per owner avoids rescanning every session for
    # every one of that owner's ~85 targets.
    disclosures_by_owner = {u.owner_id: extract_profile_disclosures(u) for u in users}
    documents_by_owner = {u.owner_id: extract_session_documents(u) for u in users}
    episodes_by_owner = {u.owner_id: extract_action_result_episodes(u) for u in users}
    anchor_by_owner = {u.owner_id: _anchor_date(u) for u in users}

    rows: list[TargetHeadCensusRow] = []
    for target in targets:
        user = users_by_owner[target.owner_id]
        bundle = compile_candidate_bundle(
            user,
            target,
            disclosures=disclosures_by_owner[target.owner_id],
            documents=documents_by_owner[target.owner_id],
            episodes=episodes_by_owner[target.owner_id],
        )
        anchor = anchor_by_owner[target.owner_id]
        for head, candidates in bundle.items():
            rows.append(_row_for_head(target, head, candidates, anchor=anchor))
    return tuple(rows)


def _variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return statistics.pvariance(values)


def summarize_eligible_pool(rows: tuple[EligiblePoolRow, ...]) -> dict[str, Any]:
    per_head: dict[str, dict[str, Any]] = {}
    for head in (Head.MP, Head.MS, Head.ME):
        head_rows = [r for r in rows if r.head is head]
        counts = [r.eligible_candidate_count for r in head_rows]
        per_head[head.value] = {
            "owners_total": len(head_rows),
            "owners_with_any_candidate": sum(1 for c in counts if c > 0),
            "total_eligible_candidates": sum(counts),
            "eligible_candidate_count_mean": statistics.fmean(counts) if counts else None,
            "eligible_candidate_count_max": max(counts, default=None),
        }
    return {
        "protocol": "pm-paper1-zero-outcome-eligible-pool-summary-v1",
        "outcome_calls": 0,
        "note": (
            "Layer 1 of 2 (B19.5): the target-invariant candidate pool per owner. "
            "Every target of an owner draws on exactly this pool (B17: the full "
            "dialog_history is strict-past for every target regardless of task "
            "type). This is NOT the final retrieved bundle/top-k -- that layer "
            f"is {FINAL_BUNDLE_STATUS}."
        ),
        "per_head": per_head,
    }


def summarize_census(rows: tuple[TargetHeadCensusRow, ...]) -> dict[str, Any]:
    """Aggregate coverage/count/length/age/redundancy/variance per head and task."""

    targets_by_task: dict[str, int] = {}
    seen_targets: set[str] = set()
    for row in rows:
        if row.target_id not in seen_targets:
            seen_targets.add(row.target_id)
            targets_by_task[row.task_type.value] = targets_by_task.get(row.task_type.value, 0) + 1
    identity_anomalies = len({row.target_id for row in rows if row.identity_anomaly})

    def _aggregate(subset: list[TargetHeadCensusRow]) -> dict[str, Any]:
        covered = [r for r in subset if r.coverage]
        candidate_counts = [float(r.candidate_count) for r in subset]
        token_means = [r.token_count_mean for r in covered if r.token_count_mean is not None]
        age_means = [r.age_days_mean for r in covered if r.age_days_mean is not None]
        overlaps = [
            r.top_candidate_lexical_overlap for r in covered if r.top_candidate_lexical_overlap is not None
        ]
        jaccard_proxy_total = sum(
            r.lexical_candidate_query_jaccard_ge_0_6_proxy_count for r in subset
        )
        # target_candidate_edges: total (target, candidate) pairs -- i.e. how
        # many times some candidate was offered to some target. NOT the same
        # as the number of distinct underlying memories: the same MP/MS/ME
        # candidate is legitimately offered again to every later target it
        # remains strict-past-eligible for, so this number is always >=
        # unique_candidate_count and should never be read as a memory count.
        target_candidate_edges = sum(r.candidate_count for r in subset)
        unique_candidate_ids = {snap.candidate_id for r in subset for snap in r.candidates}
        owners_with_any_candidate = {r.owner_id for r in subset if r.candidate_count > 0}
        targets_with_visible_query = sum(1 for r in subset if r.has_visible_query)
        return {
            "targets_total": len(subset),
            "targets_with_coverage": len(covered),
            "targets_with_visible_query": targets_with_visible_query,
            "coverage_fraction": (len(covered) / len(subset)) if subset else None,
            "unique_candidate_count": len(unique_candidate_ids),
            "owners_with_any_candidate": len(owners_with_any_candidate),
            "target_candidate_edges": target_candidate_edges,
            "candidate_count_mean": statistics.fmean(candidate_counts) if candidate_counts else None,
            "candidate_count_max": max((r.candidate_count for r in subset), default=None),
            "candidate_count_variance": _variance(candidate_counts),
            "token_count_mean_of_means": statistics.fmean(token_means) if token_means else None,
            "token_count_variance_of_means": _variance(token_means),
            "age_days_mean_of_means": statistics.fmean(age_means) if age_means else None,
            "age_days_variance_of_means": _variance(age_means),
            # B25: renamed from already_visible_fraction_of_candidates -- see
            # module docstring, this is a lexical-overlap proxy, not the
            # authoritative already-visible construct.
            "lexical_candidate_query_jaccard_ge_0_6_proxy_fraction_of_candidates": (
                jaccard_proxy_total / target_candidate_edges if target_candidate_edges else None
            ),
            "top_candidate_lexical_overlap_mean": statistics.fmean(overlaps) if overlaps else None,
            "top_candidate_lexical_overlap_variance": _variance(overlaps),
        }

    per_head = {head.value: _aggregate([r for r in rows if r.head is head]) for head in Head if head is not Head.RS}
    per_head_per_task = {
        head.value: {
            task.value: _aggregate([r for r in rows if r.head is head and r.task_type is task])
            for task in TaskType
        }
        for head in Head
        if head is not Head.RS
    }

    return {
        "protocol": "pm-paper1-zero-outcome-census-summary-v3",
        "outcome_calls": 0,
        "targets_total": len(seen_targets),
        "targets_by_task": targets_by_task,
        "identity_anomalies": identity_anomalies,
        "final_retrieved_bundle_status": FINAL_BUNDLE_STATUS,
        "superseded_note": (
            "B19.7: this census supersedes all pre-B17 MP/MS/ME counts (the "
            "old MP=118/MS=1516/ME=239 edge counts assumed a per-target "
            "'current session' cutoff that the official ES-MemEval evaluation "
            "harness does not actually use -- see memory_source module "
            "docstring). Do not cite the old numbers as freeze evidence."
        ),
        "interpretation_note": (
            "This is layer 2 of 2 (B19.5) -- per-target scoring against "
            "visible_query_text (QA/Summary) or null (DG, no static query "
            "pre-generation). candidate_count/targets_with_coverage here are "
            "the eligible pool size restated per target (target-invariant per "
            "owner, B17); see features.build_eligible_pool for the pool layer "
            "reported once per owner. targets_with_coverage and "
            "target_candidate_edges count (target, candidate) pairs, not "
            "distinct memories -- see unique_candidate_count and "
            "owners_with_any_candidate for the distinct-memory view."
        ),
        "per_head": per_head,
        "per_head_per_task": per_head_per_task,
    }


def write_census_manifest(
    rows: tuple[TargetHeadCensusRow, ...], summary: dict[str, Any], out_dir: Path
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "es_memeval_public_candidate_census_v1.jsonl"
    rendered = "".join(_canonical(row.to_manifest_row()) + "\n" for row in rows)
    manifest_path.write_text(rendered, encoding="utf-8")

    summary_with_hash = dict(summary)
    # B10: portable -- record only the sibling filename, never an absolute
    # or worktree-specific path. The manifest and summary always live next
    # to each other in the same directory by construction.
    summary_with_hash["manifest_filename"] = manifest_path.name
    summary_with_hash["manifest_sha256"] = _sha_text(rendered)
    summary_with_hash["manifest_rows"] = len(rows)
    summary_path = out_dir / "es_memeval_public_candidate_census_summary_v1.json"
    summary_path.write_text(_canonical(summary_with_hash) + "\n", encoding="utf-8")
    return {"manifest": manifest_path, "summary": summary_path}


def write_eligible_pool_manifest(
    rows: tuple[EligiblePoolRow, ...], summary: dict[str, Any], out_dir: Path
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "es_memeval_public_candidate_eligible_pool_v1.jsonl"
    rendered = "".join(_canonical(row.to_manifest_row()) + "\n" for row in rows)
    manifest_path.write_text(rendered, encoding="utf-8")

    summary_with_hash = dict(summary)
    summary_with_hash["manifest_filename"] = manifest_path.name
    summary_with_hash["manifest_sha256"] = _sha_text(rendered)
    summary_with_hash["manifest_rows"] = len(rows)
    summary_path = out_dir / "es_memeval_public_candidate_eligible_pool_summary_v1.json"
    summary_path.write_text(_canonical(summary_with_hash) + "\n", encoding="utf-8")
    return {"manifest": manifest_path, "summary": summary_path}
