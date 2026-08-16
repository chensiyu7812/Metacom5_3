"""Zero-outcome candidate census over MP/MS/ME.

Reports coverage, candidate count, token length, age, already-visible
redundancy, retrieval rank, and feature variance per (target, head) -- and
nothing else. No candidate is scored for usefulness, no PASS/FAIL judgment is
made, and no gold answer/summary/observation field is ever read. This module
only consumes ``Target.context_session_ids`` (task-premise sessions, safe at
decision time) for the current-context features; it never touches
``Target.evidence_refs`` (reserved for the splits layer's exact-evidence fold
fingerprint -- see ``metacom_pm.paper1.data.es_memeval.Target`` docstring).
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
from metacom_pm.paper1.data.es_memeval import Target, UserRecord
from metacom_pm.paper1.memory.me import extract_action_result_episodes
from metacom_pm.paper1.memory.mp import extract_profile_disclosures
from metacom_pm.paper1.memory.ms import extract_session_documents

ALREADY_VISIBLE_LEXICAL_OVERLAP_THRESHOLD = 0.6

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
    already_visible: bool
    lexical_overlap: float | None
    retrieval_rank: int


@dataclass(frozen=True)
class TargetHeadCensusRow:
    target_id: str
    task_type: TaskType
    owner_id: str
    head: Head
    identity_anomaly: bool
    candidate_count: int
    coverage: bool
    token_count_min: int | None
    token_count_mean: float | None
    token_count_max: int | None
    age_days_min: int | None
    age_days_mean: float | None
    age_days_max: int | None
    already_visible_count: int
    top_candidate_lexical_overlap: float | None
    candidates: tuple[CandidateFeatureSnapshot, ...]

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-zero-outcome-census-row-v1",
            "target_id": self.target_id,
            "task_type": self.task_type.value,
            "owner_id": self.owner_id,
            "head": self.head.value,
            "identity_anomaly": self.identity_anomaly,
            "candidate_count": self.candidate_count,
            "coverage": self.coverage,
            "token_count_min": self.token_count_min,
            "token_count_mean": self.token_count_mean,
            "token_count_max": self.token_count_max,
            "age_days_min": self.age_days_min,
            "age_days_mean": self.age_days_mean,
            "age_days_max": self.age_days_max,
            "already_visible_count": self.already_visible_count,
            "top_candidate_lexical_overlap": self.top_candidate_lexical_overlap,
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "token_count": c.token_count,
                    "age_days": c.age_days,
                    "already_visible": c.already_visible,
                    "lexical_overlap": c.lexical_overlap,
                    "retrieval_rank": c.retrieval_rank,
                }
                for c in self.candidates
            ],
        }


def _anchor_date(user: UserRecord, target: Target) -> date | None:
    if not target.context_session_ids:
        return None
    dates = [user.session_by_id(sid).date for sid in target.context_session_ids]
    return max(dates)


def _context_words(user: UserRecord, target: Target) -> frozenset[str]:
    if not target.context_session_ids:
        return frozenset()
    text_parts = []
    for session_id in target.context_session_ids:
        session = user.session_by_id(session_id)
        text_parts.extend(turn.content for turn in session.turns)
    return _word_set(" ".join(text_parts))


def _score_candidates(
    candidates: tuple[CandidateRecord, ...],
    *,
    anchor: date | None,
    context_words: frozenset[str],
) -> tuple[CandidateFeatureSnapshot, ...]:
    scored: list[tuple[float, int, str, CandidateFeatureSnapshot]] = []
    for candidate in candidates:
        candidate_words = _word_set(candidate.content)
        overlap = _lexical_overlap(candidate_words, context_words)
        already_visible = overlap is not None and overlap >= ALREADY_VISIBLE_LEXICAL_OVERLAP_THRESHOLD
        observed_at = candidate.lineage.observed_at
        age_days: int | None = None
        chronological_rank = candidate.raw_descriptors.get("session_chronological_rank")
        if anchor is not None and observed_at:
            age_days = (anchor - date.fromisoformat(observed_at)).days
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
                    age_days=age_days,
                    already_visible=already_visible,
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
            already_visible=snap.already_visible,
            lexical_overlap=snap.lexical_overlap,
            retrieval_rank=rank,
        )
        for rank, (*_key, snap) in enumerate(scored, start=1)
    )
    return ranked


def _row_for_head(
    user: UserRecord,
    target: Target,
    head: Head,
    candidates: tuple[CandidateRecord, ...],
    *,
    anchor: date | None,
    context_words: frozenset[str],
) -> TargetHeadCensusRow:
    snapshots = _score_candidates(candidates, anchor=anchor, context_words=context_words)
    token_counts = [s.token_count for s in snapshots]
    ages = [s.age_days for s in snapshots if s.age_days is not None]
    already_visible_count = sum(1 for s in snapshots if s.already_visible)
    top_overlap = snapshots[0].lexical_overlap if snapshots else None
    return TargetHeadCensusRow(
        target_id=target.target_id,
        task_type=target.task_type,
        owner_id=target.owner_id,
        head=head,
        identity_anomaly=target.identity_anomaly is not None,
        candidate_count=len(snapshots),
        coverage=len(snapshots) > 0,
        token_count_min=min(token_counts) if token_counts else None,
        token_count_mean=statistics.fmean(token_counts) if token_counts else None,
        token_count_max=max(token_counts) if token_counts else None,
        age_days_min=min(ages) if ages else None,
        age_days_mean=statistics.fmean(ages) if ages else None,
        age_days_max=max(ages) if ages else None,
        already_visible_count=already_visible_count,
        top_candidate_lexical_overlap=top_overlap,
        candidates=snapshots,
    )


def build_census(
    users: tuple[UserRecord, ...], targets: tuple[Target, ...]
) -> tuple[TargetHeadCensusRow, ...]:
    """Build one census row per (target, head) with zero outcome reads."""

    users_by_owner = {u.owner_id: u for u in users}
    # Extraction is per-user and target-independent (see `metacom_pm.paper1.memory`
    # docstring); precomputing once per owner avoids rescanning every session for
    # every one of that owner's ~85 targets.
    disclosures_by_owner = {u.owner_id: extract_profile_disclosures(u) for u in users}
    documents_by_owner = {u.owner_id: extract_session_documents(u) for u in users}
    episodes_by_owner = {u.owner_id: extract_action_result_episodes(u) for u in users}

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
        anchor = _anchor_date(user, target)
        context_words = _context_words(user, target)
        for head, candidates in bundle.items():
            rows.append(
                _row_for_head(
                    user, target, head, candidates, anchor=anchor, context_words=context_words
                )
            )
    return tuple(rows)


def _variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return statistics.pvariance(values)


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
        already_visible_total = sum(r.already_visible_count for r in subset)
        candidate_total = sum(r.candidate_count for r in subset)
        return {
            "targets_total": len(subset),
            "targets_with_coverage": len(covered),
            "coverage_fraction": (len(covered) / len(subset)) if subset else None,
            "candidate_count_mean": statistics.fmean(candidate_counts) if candidate_counts else None,
            "candidate_count_max": max((r.candidate_count for r in subset), default=None),
            "candidate_count_variance": _variance(candidate_counts),
            "token_count_mean_of_means": statistics.fmean(token_means) if token_means else None,
            "token_count_variance_of_means": _variance(token_means),
            "age_days_mean_of_means": statistics.fmean(age_means) if age_means else None,
            "age_days_variance_of_means": _variance(age_means),
            "already_visible_fraction_of_candidates": (
                already_visible_total / candidate_total if candidate_total else None
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
        "protocol": "pm-paper1-zero-outcome-census-summary-v1",
        "outcome_calls": 0,
        "targets_total": len(seen_targets),
        "targets_by_task": targets_by_task,
        "identity_anomalies": identity_anomalies,
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
    summary_with_hash["manifest_path"] = str(manifest_path)
    summary_with_hash["manifest_sha256"] = _sha_text(rendered)
    summary_with_hash["manifest_rows"] = len(rows)
    summary_path = out_dir / "es_memeval_public_candidate_census_summary_v1.json"
    summary_path.write_text(_canonical(summary_with_hash) + "\n", encoding="utf-8")
    return {"manifest": manifest_path, "summary": summary_path}
