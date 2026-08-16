"""B24: Phase-1 memory feature-readiness / identifiability audit.

Diagnostic only, built entirely from the already-materialized sanitized
runtime artifact and the already-built zero-outcome census
(``metacom_pm.paper1.features.zero_outcome_census``). This module computes
no new candidates, reads no evidence/gold/observation field, and does not
widen ``memory/mp.py``'s or ``memory/me.py``'s primary compiler -- it is a
read-only report over ``build_census``'s output.

What this audit deliberately does NOT do (AGENTS.md / B24 instruction):

- It never declares a per-head PASS/FAIL verdict -- Paper-1's capability
  verdict is official-benchmark-only (AGENTS.md "Evaluation authority"),
  and this round is still zero-outcome, so no capability claim is possible
  at all yet.
- It never sets a minimum-N gate for any head.
- It never selects ``n_outer_folds``, an outer-fold seed, a memory top-k, or
  a token cap -- those remain explicit M2-freeze decisions.
- It never folds the B21 ``family_relationship`` expansion diagnostic into
  the primary MP compiler, and never loosens the B20 ME construct.
- It never treats an opaque ``target_id``/``candidate_id``/``owner_id``/
  ``group_component_id`` as anything other than an audit/grouping key
  (``contracts.CandidateRecord.candidate_id`` and
  ``CandidateLineage.owner_id`` are already documented "forbidden as a model
  feature" in the shared, Codex-A-owned contract this module never edits).

Feature-readiness axes reported per (head, task): candidate availability
(unique candidates / owners / target coverage / target-candidate edges --
edges are explicitly *not* a count of independent memories, since the same
candidate is legitimately offered again to every later strict-past-eligible
target), and, for the outcome-blind features already computable in
``zero_outcome_census`` (candidate count, token length, relative age,
lexical overlap, already-visible, retrieval rank): missingness, distinct-
value count, and variance where defined. A feature with zero variance
corpus-wide (every computed value identical) is flagged
``ZERO_VARIANCE_NOT_FEATURE_READY`` rather than silently reported as if it
were a working discriminative signal -- readiness is a description, not an
automatic go/no-go. Embedding similarity is reported ``NOT_IMPLEMENTED``:
no code path in this project computes it yet, so it is honestly reported as
absent rather than guessed at.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Target
from metacom_pm.paper1.features.zero_outcome_census import (
    FINAL_BUNDLE_STATUS,
    TargetHeadCensusRow,
    build_census,
)

_MEMORY_TASK_TYPES = (TaskType.QA, TaskType.SUMMARY, TaskType.DIALOGUE_GENERATION)

EDGES_NOT_INDEPENDENT_MEMORIES_NOTE = (
    "target_candidate_edges counts (target, candidate) pairs, not distinct "
    "memories -- the same underlying candidate is legitimately offered "
    "again to every later target it remains strict-past-eligible for. See "
    "unique_candidate_count/owners_with_candidates for the distinct-memory "
    "view."
)

DG_STATIC_SIMILARITY_NOTE = (
    "DG has no static current-dialogue state pre-generation (B17.4/B19.4): "
    "there is no seeker utterance to compute lexical/embedding similarity, "
    "already-visible, or retrieval rank against until a turn is actually "
    "generated. This is reported N/A, never approximated from "
    "related_sessions/topic. Making this computable requires either (a) a "
    "future generation runner that injects the real per-turn seeker "
    "utterance as dynamic state (out of scope this round -- no generation "
    "is authorized), or (b) a researcher decision to treat DG's memory "
    "features as held-out/downstream-only (scored after the fact against "
    "whatever the runner produces, never as a pre-generation candidate "
    "feature). Neither option is selected here."
)


def _pvariance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return statistics.pvariance(values)


@dataclass(frozen=True)
class FeatureAxisReadiness:
    """Missingness/variance readiness for one outcome-blind feature axis.

    ``measured_over`` disambiguates what one "value" is: ``candidate_count``
    is measured per *target* (one value = how many candidates that target
    got); every other axis (token length, age, lexical overlap, already-
    visible, retrieval rank) is measured per compiled *candidate item*
    (one value per (target, candidate) edge). ``total_values`` /
    ``present_values`` are counted in whichever of those two units applies.
    """

    computable: bool
    measured_over: str
    total_values: int
    present_values: int
    missingness_fraction: float | None
    distinct_value_count: int
    mean: float | None
    variance: float | None
    zero_variance: bool | None
    readiness_status: str

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "computable": self.computable,
            "measured_over": self.measured_over,
            "total_values": self.total_values,
            "present_values": self.present_values,
            "missingness_fraction": self.missingness_fraction,
            "distinct_value_count": self.distinct_value_count,
            "mean": self.mean,
            "variance": self.variance,
            "zero_variance": self.zero_variance,
            "readiness_status": self.readiness_status,
        }


def _axis_readiness(
    values: list[float | None], *, measured_over: str, na_reason: str | None
) -> FeatureAxisReadiness:
    total = len(values)
    if na_reason is not None:
        return FeatureAxisReadiness(
            computable=False,
            measured_over=measured_over,
            total_values=total,
            present_values=0,
            missingness_fraction=1.0 if total else None,
            distinct_value_count=0,
            mean=None,
            variance=None,
            zero_variance=None,
            readiness_status=na_reason,
        )
    present = [v for v in values if v is not None]
    distinct = len({round(v, 9) if isinstance(v, float) else v for v in present})
    if total == 0:
        status = "NOT_COMPUTABLE_NO_CANDIDATES"
    elif not present:
        status = "NOT_COMPUTABLE_ALL_MISSING"
    elif distinct <= 1:
        status = "ZERO_VARIANCE_NOT_FEATURE_READY"
    else:
        status = "COMPUTABLE_WITH_VARIANCE"
    return FeatureAxisReadiness(
        computable=bool(present),
        measured_over=measured_over,
        total_values=total,
        present_values=len(present),
        missingness_fraction=((total - len(present)) / total) if total else None,
        distinct_value_count=distinct,
        mean=statistics.fmean(present) if present else None,
        variance=_pvariance(present),
        zero_variance=(distinct <= 1) if present else None,
        readiness_status=status,
    )


@dataclass(frozen=True)
class HeadTaskFeatureReadinessRow:
    head: Head
    task_type: TaskType
    unique_candidate_count: int
    owners_with_candidates: int
    targets_total: int
    targets_with_coverage: int
    coverage_fraction: float | None
    target_candidate_edges: int
    static_visible_query_present: bool
    candidate_count: FeatureAxisReadiness
    token_length: FeatureAxisReadiness
    relative_age_days: FeatureAxisReadiness
    lexical_similarity: FeatureAxisReadiness
    already_visible: FeatureAxisReadiness
    retrieval_rank: FeatureAxisReadiness

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-memory-feature-readiness-row-v1",
            "head": self.head.value,
            "task_type": self.task_type.value,
            "unique_candidate_count": self.unique_candidate_count,
            "owners_with_candidates": self.owners_with_candidates,
            "targets_total": self.targets_total,
            "targets_with_coverage": self.targets_with_coverage,
            "coverage_fraction": self.coverage_fraction,
            "target_candidate_edges": self.target_candidate_edges,
            "target_candidate_edges_note": EDGES_NOT_INDEPENDENT_MEMORIES_NOTE,
            "static_visible_query_present": self.static_visible_query_present,
            "embedding_similarity": {
                "computable": False,
                "readiness_status": "NOT_IMPLEMENTED",
                "note": (
                    "No code path in this project computes an embedding "
                    "similarity feature yet -- reported absent, not guessed."
                ),
            },
            "candidate_count": self.candidate_count.to_manifest_row(),
            "token_length": self.token_length.to_manifest_row(),
            "relative_age_days": self.relative_age_days.to_manifest_row(),
            "lexical_similarity": self.lexical_similarity.to_manifest_row(),
            "already_visible": self.already_visible.to_manifest_row(),
            "retrieval_rank": self.retrieval_rank.to_manifest_row(),
        }


def _row_for_head_task(
    head: Head, task: TaskType, subset: list[TargetHeadCensusRow]
) -> HeadTaskFeatureReadinessRow:
    is_dg = task is TaskType.DIALOGUE_GENERATION
    na_reason = "N_A_NO_STATIC_QUERY_PRE_GENERATION" if is_dg else None

    all_candidates = [c for r in subset for c in r.candidates]
    covered = [r for r in subset if r.coverage]
    owners_with_candidates = len({r.owner_id for r in subset if r.candidate_count > 0})
    unique_candidate_ids = {c.candidate_id for r in subset for c in r.candidates}
    static_visible_query_present = any(r.has_visible_query for r in subset) if subset else False

    token_values: list[float | None] = [float(c.token_count) for c in all_candidates]
    age_values: list[float | None] = [
        float(c.age_days) if c.age_days is not None else None for c in all_candidates
    ]
    lex_values: list[float | None] = [c.lexical_overlap for c in all_candidates]
    already_visible_values: list[float | None] = [
        (1.0 if c.already_visible else 0.0) if c.already_visible is not None else None
        for c in all_candidates
    ]
    rank_values: list[float | None] = [
        float(c.retrieval_rank) if c.retrieval_rank is not None else None for c in all_candidates
    ]
    candidate_count_values: list[float | None] = [float(r.candidate_count) for r in subset]

    return HeadTaskFeatureReadinessRow(
        head=head,
        task_type=task,
        unique_candidate_count=len(unique_candidate_ids),
        owners_with_candidates=owners_with_candidates,
        targets_total=len(subset),
        targets_with_coverage=len(covered),
        coverage_fraction=(len(covered) / len(subset)) if subset else None,
        target_candidate_edges=sum(r.candidate_count for r in subset),
        static_visible_query_present=static_visible_query_present,
        candidate_count=_axis_readiness(
            candidate_count_values, measured_over="per_target", na_reason=None
        ),
        token_length=_axis_readiness(token_values, measured_over="per_candidate_item", na_reason=None),
        relative_age_days=_axis_readiness(
            age_values, measured_over="per_candidate_item", na_reason=None
        ),
        lexical_similarity=_axis_readiness(
            lex_values, measured_over="per_candidate_item", na_reason=na_reason
        ),
        already_visible=_axis_readiness(
            already_visible_values, measured_over="per_candidate_item", na_reason=na_reason
        ),
        retrieval_rank=_axis_readiness(
            rank_values, measured_over="per_candidate_item", na_reason=na_reason
        ),
    )


def build_feature_readiness_rows(
    users: tuple[MemorySourceUser, ...], targets: tuple[Target, ...]
) -> tuple[HeadTaskFeatureReadinessRow, ...]:
    census_rows = build_census(users, targets)
    rows: list[HeadTaskFeatureReadinessRow] = []
    for head in (Head.MP, Head.MS, Head.ME):
        for task in _MEMORY_TASK_TYPES:
            subset = [r for r in census_rows if r.head is head and r.task_type is task]
            rows.append(_row_for_head_task(head, task, subset))
    return tuple(rows)


def summarize_feature_readiness(rows: tuple[HeadTaskFeatureReadinessRow, ...]) -> dict[str, Any]:
    """Aggregate/summary-level report over already-built rows (no gold, outcome-blind).

    Mirrors ``zero_outcome_census.summarize_census``'s layering: this
    function takes rows already produced by ``build_feature_readiness_rows``
    rather than raw users/targets, so the row-level and summary-level
    outputs can be written to separate manifest files without duplicating
    the row data inline in both.
    """

    by_key = {(r.head, r.task_type): r for r in rows}

    zero_variance_axes = []
    already_visible_zero_variance_head_tasks = []
    for r in rows:
        for axis_name in (
            "candidate_count",
            "token_length",
            "relative_age_days",
            "lexical_similarity",
            "already_visible",
            "retrieval_rank",
        ):
            axis: FeatureAxisReadiness = getattr(r, axis_name)
            if axis.readiness_status == "ZERO_VARIANCE_NOT_FEATURE_READY":
                zero_variance_axes.append(f"{r.head.value}/{r.task_type.value}/{axis_name}")
                if axis_name == "already_visible":
                    already_visible_zero_variance_head_tasks.append(f"{r.head.value}/{r.task_type.value}")

    mp_qa = by_key[(Head.MP, TaskType.QA)]
    me_qa = by_key[(Head.ME, TaskType.QA)]
    ms_qa = by_key[(Head.MS, TaskType.QA)]

    return {
        "protocol": "pm-paper1-memory-feature-readiness-audit-report-v1",
        "status": "PHASE1_FEATURE_READINESS_IDENTIFIABILITY_AUDIT",
        "outcome_calls": 0,
        "scope_note": (
            "Built entirely from the already-materialized sanitized runtime "
            "artifact and the already-built zero-outcome census. No new "
            "candidates are computed; primary MP/ME compilers are not "
            "widened or loosened."
        ),
        "no_verdict_policy": {
            "per_head_pass_fail": "NOT_DECLARED_THIS_ROUND",
            "minimum_n_gate": None,
            "note": (
                "Paper-1's capability verdict is official-benchmark-only "
                "(AGENTS.md 'Evaluation authority'); this is a zero-outcome "
                "phase, so no capability claim -- and no minimum-N "
                "sufficiency gate for any head -- is made here."
            ),
        },
        "unselected_freeze_decisions": {
            "n_outer_folds": None,
            "outer_fold_seed": None,
            "memory_top_k": None,
            "memory_token_cap": None,
            "final_retrieved_bundle_status": FINAL_BUNDLE_STATUS,
            "note": "M2-freeze decisions; not self-selected by this diagnostic audit.",
        },
        "opaque_id_usage_note": (
            "target_id/candidate_id/owner_id/group_component_id are "
            "audit/grouping identifiers only. candidate_id and "
            "CandidateLineage.owner_id are already documented 'forbidden as "
            "a model feature' in the shared contracts.py this lane does not "
            "own or edit; this audit reports them only for row identity, "
            "never as a computed feature value."
        ),
        "mp_identifiability_limitation": {
            "unique_candidates": mp_qa.unique_candidate_count,
            "owners_with_candidates": mp_qa.owners_with_candidates,
            "note": (
                "MP is genuinely sparse under the strict self-disclosure "
                "construct (memory/mp.py): 3 unique candidates from 3 "
                "owners corpus-wide. The B21 diagnostic audit "
                "(features/mp_extraction_audit.py) found no fully-"
                "enumerable, mechanical, precision-first expansion rule for "
                "family_relationship or any other audited category this "
                "round -- family_relationship's 132 matches conflate a "
                "stable existence fact with situational narration in a way "
                "this project cannot mechanically separate without "
                "semantic judgment. Not expanded here either; this is an "
                "honest identifiability limitation, not a synthetic rescue."
            ),
        },
        "me_identifiability_limitation": {
            "unique_candidates": me_qa.unique_candidate_count,
            "owners_with_candidates": me_qa.owners_with_candidates,
            "note": (
                "ME requires an explicit self-reported action with a real "
                "complement, an explicit same-sentence observed result, and "
                "no cross-turn temporal-only pairing (B11/B20 repair "
                "history in memory/me.py) -- 3 unique candidates from 2 "
                "owners corpus-wide survive. This construct is not loosened "
                "here to manufacture more coverage."
            ),
        },
        "ms_availability_note": (
            f"MS coverage_fraction={ms_qa.coverage_fraction} (QA slice) "
            "reflects that every target draws on its owner's full "
            "strict-past session history (B17) -- this is candidate "
            "*availability*, not a claim that MS is a working/successful "
            "head. Availability says nothing about whether any MS feature "
            "built on this pool is discriminative; see the per-axis "
            "readiness_status fields for that."
        ),
        "dg_static_similarity_note": DG_STATIC_SIMILARITY_NOTE,
        "zero_variance_axes": zero_variance_axes,
        "zero_variance_axes_note": (
            "Every 'head/task/axis' entry above has readiness_status "
            "ZERO_VARIANCE_NOT_FEATURE_READY -- every computed value for "
            "that axis, corpus-wide, is identical (e.g. MP/qa's "
            "retrieval_rank is always 1, because MP almost never offers "
            "more than one candidate to a target). Listed for disclosure "
            "only; none of these axes are auto-frozen into the feature "
            "schema on this basis."
        ),
        "already_visible_zero_variance_head_tasks": already_visible_zero_variance_head_tasks,
        "already_visible_zero_variance_summary": (
            "already-visible is zero-variance (uniformly False/0) for every "
            "head/task pair with any candidate at all this round -- see "
            "already_visible_zero_variance_head_tasks for the exact list. "
            "This is reported as ZERO_VARIANCE_NOT_FEATURE_READY on each "
            "affected row, not auto-frozen into the feature schema."
        ),
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_feature_readiness_manifest(
    rows: tuple[HeadTaskFeatureReadinessRow, ...], summary: dict[str, Any], out_dir: Path
) -> dict[str, Path]:
    """Write the row-level manifest (jsonl) and the summary report (json)."""

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "es_memeval_public_feature_readiness_audit_rows_v1.jsonl"
    rendered_rows = "".join(_canonical(r.to_manifest_row()) + "\n" for r in rows)
    manifest_path.write_text(rendered_rows, encoding="utf-8")

    summary_with_hash = dict(summary)
    summary_with_hash["rows_manifest_filename"] = manifest_path.name
    summary_with_hash["rows_manifest_sha256"] = _sha_text(rendered_rows)
    summary_with_hash["rows_manifest_count"] = len(rows)
    summary_path = out_dir / "es_memeval_public_feature_readiness_audit_v1.json"
    summary_path.write_text(_canonical(summary_with_hash) + "\n", encoding="utf-8")

    return {"rows_manifest": manifest_path, "summary": summary_path}
