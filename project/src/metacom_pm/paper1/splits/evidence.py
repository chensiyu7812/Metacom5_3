"""The only module in the paper1 namespace allowed to read QA/Summary evidence.

``QuestionItem.evidence`` and ``SummaryItem.evidence`` encode which sessions
justify the *correct answer* -- gold-adjacent information that must never
reach a candidate feature or a current-context anchor (see
``metacom_pm.paper1.data.memory_source.Target``'s docstring for why: it would
be a backdoor peek at what the gold answer needs). B8/B18 physically isolate
this: ``Target``, the object handed to ``candidates/`` and ``features/``,
carries no evidence field at all -- and, as of B17, no ``context_session_ids``
or any other group/related-session field either, since the full
``dialog_history`` is now known to be strict-past for every target
regardless of task type (verified against the official evaluation harness).
This module is the sole place that reads QA/Summary ``evidence`` or DG
``related_sessions``, and only for exact-evidence fold-fingerprint
construction in ``metacom_pm.paper1.splits`` -- neither ever reaches
``Target``, a candidate, or a feature.

DG's ``related_sessions`` is not gold-adjacent in the same sense as QA/
Summary ``evidence`` -- it is simulator/evaluator-only hidden background
(confirmed by reading the official DG harness's seeker-simulator
construction code; the supporter under test never receives it at all) -- but
it is read here too, unchanged, purely so the fold-fingerprint step has one
evidence-like reference source per task type to union on.
"""

from __future__ import annotations

from dataclasses import dataclass

from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.es_memeval import (
    UserRecord,
    dg_primary_group_key,
    dg_target_id,
    qa_primary_group_key,
    qa_target_id,
    summary_primary_group_key,
    summary_target_id,
)


@dataclass(frozen=True)
class SplitEvidenceRecord:
    """Splits-only: target identity + owner-namespaced evidence, nothing else.

    ``target_id`` is audit-only linkage back to the matching ``Target``, not
    a candidate/feature input. ``owner_id`` is carried explicitly (not just
    folded into the fingerprint as a prefix) so callers can namespace the
    fingerprint themselves -- see ``canonical_evidence_fingerprint`` in
    ``exact_evidence_folds.py`` for why an owner-scoped fingerprint matters:
    without it, two different owners whose targets happen to cite the same
    literal ESConv-origin session id (e.g. ``esc1024``) could be incorrectly
    unioned into the same fold.
    """

    target_id: str
    task_type: TaskType
    owner_id: str
    primary_group_key: str
    evidence_refs: tuple[str, ...]


def enumerate_split_evidence(users: tuple[UserRecord, ...]) -> tuple[SplitEvidenceRecord, ...]:
    """One ``SplitEvidenceRecord`` per QA/Summary/DG target, evidence-only.

    Independently walks the same raw structure ``enumerate_targets`` walks
    (sharing only the pure ID-formatting helpers, never a parsed ``Target``),
    so this module is the sole reader of ``.evidence`` in the whole package.
    """

    records: list[SplitEvidenceRecord] = []
    for user in users:
        for group in user.question_groups:
            for item in group.items:
                records.append(
                    SplitEvidenceRecord(
                        target_id=qa_target_id(user.owner_id, group.question_group_id, item.idx),
                        task_type=TaskType.QA,
                        owner_id=user.owner_id,
                        primary_group_key=qa_primary_group_key(
                            user.owner_id, group.question_group_id
                        ),
                        evidence_refs=item.evidence,
                    )
                )
        for summary in user.summaries:
            records.append(
                SplitEvidenceRecord(
                    target_id=summary_target_id(user.owner_id, summary.idx),
                    task_type=TaskType.SUMMARY,
                    owner_id=user.owner_id,
                    primary_group_key=summary_primary_group_key(user.owner_id, summary.idx),
                    evidence_refs=summary.evidence,
                )
            )
        for topic in user.subsequent_topics:
            records.append(
                SplitEvidenceRecord(
                    target_id=dg_target_id(user.owner_id, topic.idx),
                    task_type=TaskType.DIALOGUE_GENERATION,
                    owner_id=user.owner_id,
                    primary_group_key=dg_primary_group_key(user.owner_id, topic.idx),
                    evidence_refs=topic.related_sessions,
                )
            )
    return tuple(records)


__all__ = ["SplitEvidenceRecord", "enumerate_split_evidence"]
