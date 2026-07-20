"""Report-only calibration/comparison helpers for the Hybrid retriever diagnostic.

Called by ``scripts/v1_5/40_diagnose_hybrid_retrieval.py``, which writes the
JSON report. Every function here is report-only: results may inform a
future, separately-approved adoption decision but must never be treated as
a formal pipeline artifact, and this module must never be imported by any
real consumer (see ``tests/test_hybrid_retrieval_isolation.py``).

**Data-boundary rule (hard, per the approved plan):** ``calibrate_source_
floors`` fits floors using ONLY ``train``-split examples, then reports (never
refits against) ``calibration``-split recall/exclusion as an informational
check. Both splits are identified via the ``pmv2_{split}_u...`` user_id
convention established in
``scripts/v1_5/20_generate_pm_v2_development_data_v1_5.py``.
``internal_test``/``external_test`` rows are never loaded by
``iter_case_calibration_examples`` in the first place. Every EvoEmo-derived
number (``evoemo_topic_diagnostic_rows``, ``compare_fixed_top_k``,
``compare_fixed_token_budget``) is computed by a structurally separate path
and must never feed back into calibration -- these are report-only
comparisons, computed only after the floors/contract are already frozen.

The EvoEmo comparison deliberately uses each user's ``topic`` field (an
EvoEmo evaluator-only field, never real deployment input) as a query
stand-in, exactly as the earlier no-API sensitivity check
(``me_chunk_sensitivity.py``) already did -- this is the one place the plan
explicitly sanctions using evaluator-only text as if it were a query, for
this diagnostic purpose only. It is intentionally kept structurally
separate from ``observable_query_with_hash`` (the real query-construction
path). Comparison scope is intentionally limited to the ME memory source:
``related_sessions`` ground truth is meaningful for session-linked episodic
(ME) items, not for MP (session-independent profile facts) or MS
(whole-session summaries), so extending the comparison to those sources
would have no real ground truth to score against.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import MemoryItem, MemorySource
from .evoemo import build_evo_memory
from .hybrid_retrieval import HybridMemoryRetriever, retrieve_fixed_token_budget
from .io import sha256_text
from .retrieval import MemoryRetriever
from .text import lexical_score


_SPLIT_USER_ID_RE = re.compile(
    r"^pmv2_(?P<split>train|calibration|internal_test|external_test)_u\d+$"
)

MEMORY_POOL_FIELDS: dict[str, MemorySource] = {
    "profile_memories": MemorySource.MP,
    "event_memories": MemorySource.ME,
    "summary_memories": MemorySource.MS,
}

# calibrate_source_floors may fit floors using only this split -- see
# module docstring. CALIBRATION_SPLIT is loaded too, but only ever scored
# against the already-fit floor, never used to fit it.
FLOOR_FITTING_SPLIT = "train"
FLOOR_REPORTING_SPLIT = "calibration"
CALIBRATION_ALLOWED_SPLITS = frozenset({FLOOR_FITTING_SPLIT, FLOOR_REPORTING_SPLIT})


def split_of_user_id(user_id: str) -> str:
    match = _SPLIT_USER_ID_RE.match(str(user_id))
    if not match:
        raise ValueError(
            f"user_id does not match the pmv2 split-prefix convention: {user_id!r}"
        )
    return match.group("split")


def _is_positive_label(memory_row: Mapping[str, Any]) -> bool:
    """A candidate that is genuinely worth retrieving.

    Matches the definition already used elsewhere for this corpus
    (pm_v2_data.py): ``item_utility == "helpful"`` alone is not sufficient
    -- a helpful-topic item that is stale or conflicts with the current
    state is not actually a good retrieve target.
    """

    return (
        memory_row["item_utility"] == "helpful"
        and not memory_row["stale"]
        and not memory_row["conflicts_with_current_state"]
    )


@dataclass(frozen=True)
class CalibrationExample:
    split: str
    query_text: str
    source: MemorySource
    text: str
    label_positive: bool


def iter_case_calibration_examples(
    bundles: Sequence[Mapping[str, Any]],
    *,
    allowed_splits: frozenset[str] = CALIBRATION_ALLOWED_SPLITS,
) -> list[CalibrationExample]:
    """Flatten every case's memory candidates from users in ``allowed_splits``.

    ``bundles`` is the raw per-user structure produced by
    ``scripts/v1_5/20_generate_pm_v2_development_data_v1_5.py`` (one row per
    user, each with a ``cases`` list; each case has ``current_user_text``
    and the three memory pools in ``MEMORY_POOL_FIELDS``). Any split not in
    ``allowed_splits`` (in particular ``internal_test``/``external_test``)
    is skipped entirely -- never even flattened into memory.
    """

    examples: list[CalibrationExample] = []
    for bundle in bundles:
        split = split_of_user_id(bundle["user_id"])
        if split not in allowed_splits:
            continue
        for case in bundle.get("cases") or []:
            query_text = str(case["current_user_text"])
            for pool_field, source in MEMORY_POOL_FIELDS.items():
                for memory_row in case.get(pool_field) or []:
                    examples.append(
                        CalibrationExample(
                            split=split,
                            query_text=query_text,
                            source=source,
                            text=str(memory_row["text"]),
                            label_positive=_is_positive_label(memory_row),
                        )
                    )
    return examples


@dataclass(frozen=True)
class SourceFloorCalibration:
    lexical_min_score: float
    semantic_min_score: float
    train_positive_count: int
    train_negative_count: int
    calibration_positive_count: int
    calibration_negative_count: int
    calibration_recall: float | None
    calibration_negative_exclusion_rate: float | None


def _embed_all_texts(examples: Sequence[CalibrationExample], *, encoder) -> dict[str, Any]:
    distinct_texts = sorted({e.query_text for e in examples} | {e.text for e in examples})
    if not distinct_texts:
        return {}
    vectors = encoder.encode(distinct_texts)
    return dict(zip(distinct_texts, vectors))


def calibrate_source_floors(
    examples: Sequence[CalibrationExample],
    *,
    encoder,
) -> dict[MemorySource, SourceFloorCalibration]:
    """Fit one lexical+semantic floor per MemorySource from TRAIN examples only.

    Method (frozen, simple, and disclosed rather than hand-tuned): the floor
    is the minimum raw score observed among TRAIN-split *positive* examples
    for that source and scorer -- i.e. the loosest floor that would not have
    excluded a single known-good TRAIN example. The CALIBRATION split (never
    used to fit the floor) is then scored against that frozen floor purely
    to report its recall (fraction of calibration positives the floor would
    keep) and negative-exclusion rate (fraction of calibration negatives the
    floor would drop) -- informational only, not a second fitting pass.

    Raises if a source has zero TRAIN positive examples: a floor cannot be
    honestly fit from nothing, and silently defaulting would hide a real
    data problem rather than surface it.
    """

    vectors = _embed_all_texts(examples, encoder=encoder)
    scored = [
        (
            e,
            lexical_score(e.query_text, e.text),
            float(vectors[e.query_text] @ vectors[e.text]),
        )
        for e in examples
    ]
    result: dict[MemorySource, SourceFloorCalibration] = {}
    sources_present = sorted({e.source for e in examples}, key=lambda s: s.value)
    for source in sources_present:
        train_rows = [
            (lex, sem, e.label_positive)
            for e, lex, sem in scored
            if e.source is source and e.split == FLOOR_FITTING_SPLIT
        ]
        train_positives = [(lex, sem) for lex, sem, positive in train_rows if positive]
        train_negatives = [(lex, sem) for lex, sem, positive in train_rows if not positive]
        if not train_positives:
            raise RuntimeError(
                f"cannot calibrate a floor for {source.value}: zero TRAIN-split "
                "positive examples -- refusing to fabricate a floor from no data"
            )
        lexical_floor = min(lex for lex, _sem in train_positives)
        semantic_floor = min(sem for _lex, sem in train_positives)

        calibration_rows = [
            (lex, sem, e.label_positive)
            for e, lex, sem in scored
            if e.source is source and e.split == FLOOR_REPORTING_SPLIT
        ]
        calibration_positives = [
            (lex, sem) for lex, sem, positive in calibration_rows if positive
        ]
        calibration_negatives = [
            (lex, sem) for lex, sem, positive in calibration_rows if not positive
        ]
        recall = (
            sum(
                1
                for lex, sem in calibration_positives
                if lex > lexical_floor or sem > semantic_floor
            )
            / len(calibration_positives)
            if calibration_positives
            else None
        )
        exclusion_rate = (
            sum(
                1
                for lex, sem in calibration_negatives
                if lex <= lexical_floor and sem <= semantic_floor
            )
            / len(calibration_negatives)
            if calibration_negatives
            else None
        )
        result[source] = SourceFloorCalibration(
            lexical_min_score=lexical_floor,
            semantic_min_score=semantic_floor,
            train_positive_count=len(train_positives),
            train_negative_count=len(train_negatives),
            calibration_positive_count=len(calibration_positives),
            calibration_negative_count=len(calibration_negatives),
            calibration_recall=recall,
            calibration_negative_exclusion_rate=exclusion_rate,
        )
    return result


# ---------------------------------------------------------------------------
# Report-only EvoEmo comparisons (never feed back into calibration above).
# ---------------------------------------------------------------------------


def _session_id_by_created_session_index(user: Mapping[str, Any]) -> dict[int, str | None]:
    sessions = user.get("dialog_history") or []
    mapping: dict[int, str | None] = {0: None}
    for index, session in enumerate(sessions, 1):
        mapping[index] = str(session.get("id") or f"session_{index}")
    return mapping


def _me_related_session_topics(user: Mapping[str, Any]) -> list[tuple[str, set[str]]]:
    rows = []
    for topic in user.get("subsequent_topics") or []:
        query_text = str(topic.get("topic") or "")
        related = {str(s) for s in (topic.get("related_sessions") or [])}
        if query_text and related:
            rows.append((query_text, related))
    return rows


@dataclass(frozen=True)
class MethodComparisonSummary:
    topics_evaluated: int
    hit_rate: float | None
    mean_precision: float | None
    query_hashes: list[str]


def _summarize(
    *, hits: int, topics: int, precisions: list[float], query_hashes: list[str]
) -> MethodComparisonSummary:
    return MethodComparisonSummary(
        topics_evaluated=topics,
        hit_rate=(hits / topics) if topics else None,
        mean_precision=statistics.mean(precisions) if precisions else None,
        query_hashes=query_hashes,
    )


def compare_fixed_top_k(
    users: Sequence[Mapping[str, Any]],
    *,
    lexical_retriever: MemoryRetriever,
    hybrid_retriever: HybridMemoryRetriever,
) -> dict[str, MethodComparisonSummary]:
    """Report-only: ME retrieval hit-rate/precision, fixed top-k, both scorers.

    ``lexical_retriever``/``hybrid_retriever`` must both already be
    configured for MemorySource.ME with the same top_k so the comparison
    isolates the scoring method, not the budget. Uses each topic's
    evaluator-only text as a query stand-in (see module docstring) --
    ``query_hashes`` records a hash per topic, never the raw text.
    """

    selected = frozenset({MemorySource.ME})
    stats = {
        "lexical_only": {"hits": 0, "topics": 0, "precisions": [], "hashes": []},
        "hybrid": {"hits": 0, "topics": 0, "precisions": [], "hashes": []},
    }
    for user in users:
        items, _session_docs = build_evo_memory(user)
        session_id_by_index = _session_id_by_created_session_index(user)
        for query_text, related in _me_related_session_topics(user):
            query_hash = sha256_text(query_text)
            for name, retriever in (
                ("lexical_only", lexical_retriever),
                ("hybrid", hybrid_retriever),
            ):
                retrieved = retriever.retrieve(query_text, items, selected)
                retrieved_session_ids = {
                    session_id_by_index.get(item.created_session) for item in retrieved
                }
                bucket = stats[name]
                bucket["hits"] += int(bool(retrieved_session_ids & related))
                bucket["topics"] += 1
                bucket["hashes"].append(query_hash)
                if retrieved:
                    bucket["precisions"].append(
                        sum(
                            1
                            for item in retrieved
                            if session_id_by_index.get(item.created_session) in related
                        )
                        / len(retrieved)
                    )
    return {
        name: _summarize(
            hits=bucket["hits"],
            topics=bucket["topics"],
            precisions=bucket["precisions"],
            query_hashes=bucket["hashes"],
        )
        for name, bucket in stats.items()
    }


def _lexical_rank_all_me(query: str, items: Sequence[MemoryItem]) -> list[MemoryItem]:
    """Full ME ranking by raw lexical score, same tie-break as MemoryRetriever.

    Mirrors (does not modify) the real, frozen MemoryRetriever's per-source
    scoring and deterministic tie-break, just without slicing to top_k --
    needed so the fixed-token-budget comparison can rank the complete ME
    pool for the lexical-only baseline exactly as it does for hybrid's
    ``rank_all``.
    """

    candidates = [item for item in items if item.source is MemorySource.ME]
    scored = [(lexical_score(query, item.text), item) for item in candidates]
    ranked = sorted(
        scored,
        key=lambda pair: (pair[0], pair[1].created_session, pair[1].memory_id),
        reverse=True,
    )
    return [item for _score, item in ranked]


def compare_fixed_token_budget(
    users: Sequence[Mapping[str, Any]],
    *,
    hybrid_retriever: HybridMemoryRetriever,
    token_budget: int,
) -> dict[str, MethodComparisonSummary]:
    """Report-only: ME retrieval hit-rate/precision under a fixed evidence-token
    budget (whole items only, never truncated; an overflowing item is
    skipped, not a stopping point -- see retrieve_fixed_token_budget), both
    scorers, ranking the complete ME pool first via
    ``_lexical_rank_all_me``/``hybrid_retriever.rank_all``.
    """

    selected = frozenset({MemorySource.ME})
    stats = {
        "lexical_only": {"hits": 0, "topics": 0, "precisions": [], "hashes": []},
        "hybrid": {"hits": 0, "topics": 0, "precisions": [], "hashes": []},
    }
    for user in users:
        items, _session_docs = build_evo_memory(user)
        session_id_by_index = _session_id_by_created_session_index(user)
        for query_text, related in _me_related_session_topics(user):
            query_hash = sha256_text(query_text)
            lexical_ranked = _lexical_rank_all_me(query_text, items)
            hybrid_ranked = hybrid_retriever.rank_all(query_text, items, selected)
            for name, ranked in (
                ("lexical_only", lexical_ranked),
                ("hybrid", hybrid_ranked),
            ):
                retrieved = retrieve_fixed_token_budget(
                    ranked, token_budget=token_budget, text_of=lambda item: item.text
                )
                retrieved_session_ids = {
                    session_id_by_index.get(item.created_session) for item in retrieved
                }
                bucket = stats[name]
                bucket["hits"] += int(bool(retrieved_session_ids & related))
                bucket["topics"] += 1
                bucket["hashes"].append(query_hash)
                if retrieved:
                    bucket["precisions"].append(
                        sum(
                            1
                            for item in retrieved
                            if session_id_by_index.get(item.created_session) in related
                        )
                        / len(retrieved)
                    )
    return {
        name: _summarize(
            hits=bucket["hits"],
            topics=bucket["topics"],
            precisions=bucket["precisions"],
            query_hashes=bucket["hashes"],
        )
        for name, bucket in stats.items()
    }
