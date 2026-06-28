from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
import numpy as np

from .io import iter_jsonl


def load_response_pairs(path: str | Path) -> list[dict[str, Any]]:
    return [row for row in iter_jsonl(path) if row.get("training_eligible")]


def action_response_scores(path: str | Path, ridge: float = 0.10) -> dict[tuple[str, str], float]:
    """Fit a small regularized Bradley-Terry-style latent score per card.

    A plain win average is biased when actions face opponents of different
    strength in a sparse graph.  The connected pair graph lets us solve
    pairwise score differences and then convert each action to its expected win
    probability against all legal actions, yielding a comparable [0,1] value.
    """
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in load_response_pairs(path):
        by_card[str(row["card_id"])].append(row)
    result: dict[tuple[str, str], float] = {}
    for card_id, rows in by_card.items():
        actions = sorted({x["action_a"] for x in rows} | {x["action_b"] for x in rows})
        index = {action: i for i, action in enumerate(actions)}
        x = np.zeros((len(rows), len(actions)), dtype=float)
        y = np.zeros(len(rows), dtype=float)
        for r, row in enumerate(rows):
            x[r, index[row["action_a"]]] = 1.0
            x[r, index[row["action_b"]]] = -1.0
            pref = row["preference"]
            y[r] = 1.0 if pref == "A" else -1.0 if pref == "B" else 0.0
        gram = x.T @ x + ridge * np.eye(len(actions))
        scores = np.linalg.solve(gram, x.T @ y)
        scores -= scores.mean()
        for action, i in index.items():
            probs = [1.0 / (1.0 + np.exp(-(scores[i] - scores[j]))) for j in range(len(actions)) if j != i]
            result[(card_id, action)] = float(np.mean(probs)) if probs else 0.5
    return result




@dataclass(frozen=True)
class MemoryLabels:
    misuse_risk: dict[tuple[str, str], float]
    omission_risk: dict[tuple[str, str], float]
    decision_quality: dict[tuple[str, str], float]
    m2b_omission_keys: frozenset[tuple[str, str]] = frozenset()

    # Backward-compatible unpacking for older selection code:
    # risks, qualities = load_memory_labels(...)
    def __iter__(self) -> Iterator[dict[tuple[str, str], float]]:
        yield self.misuse_risk
        yield self.decision_quality


@dataclass(frozen=True)
class StrategyLabels:
    risk: dict[tuple[str, str], float]
    decision_quality: dict[tuple[str, str], float]

    def __iter__(self) -> Iterator[dict[tuple[str, str], float]]:
        yield self.risk
        yield self.decision_quality


def _as01(value: Any, *, max_value: float = 2.0) -> float:
    try:
        return float(value) / max_value
    except Exception:
        return 0.0


def load_memory_labels(
    m0_path: str | Path,
    m2_path: str | Path,
    m2b_path: str | Path | None = None,
) -> MemoryLabels:
    """Load action-level labels for memory safety and necessity.

    - misuse_risk: unsupported / stale / unnecessary personal-memory use.
    - omission_risk: high when an action omits needed memory.
    - decision_quality: high when the selected memory set is appropriate.

    The loader accepts both the V5 flat JSONL schema and older nested
    pilot rows, so legacy smoke outputs remain inspectable while confirmatory
    training uses the strict flat files produced by ``run_judging``.
    """
    misuse: dict[tuple[str, str], float] = {}
    omission: dict[tuple[str, str], float] = {}
    quality: dict[tuple[str, str], float] = {}

    for row in iter_jsonl(m0_path):
        key = (str(row["card_id"]), str(row["action_id"]))
        audit = row.get("memory_audit") if isinstance(row.get("memory_audit"), dict) else row
        unsupported = _as01(audit.get("unsupported_personal_claim", 0))
        missed = _as01(audit.get("missed_memory_opportunity_severity", 0))
        # In V3 legacy rows, omission_appropriateness was 0/1/2 but no explicit
        # missed severity existed.  Treat low appropriateness as a soft omission risk.
        appropriateness = _as01(audit.get("omission_appropriateness", 1))
        misuse[key] = unsupported
        omission[key] = max(missed, 1.0 - appropriateness)
        quality[key] = appropriateness

    for row in iter_jsonl(m2_path):
        key = (str(row["card_id"]), str(row["action_id"]))
        assessments = row.get("source_assessments")
        if assessments is None and isinstance(row.get("memory_audit"), dict):
            assessments = row["memory_audit"].get("source_assessments", [])
        assessments = assessments or []
        components = []
        for item in assessments:
            components.append(max(
                _as01(item.get("unnecessary_exposure", 0)),
                _as01(item.get("stale_or_conflicting_use", 0)),
                _as01(item.get("unsupported_personal_claim", 0)),
            ))
        misuse[key] = max(components, default=0.0)
        omission[key] = 0.0
        quality[key] = _as01(row.get("overall_source_set_appropriateness", 1))

    m2b_keys: set[tuple[str, str]] = set()
    if m2b_path is not None:
        for row in iter_jsonl(m2b_path):
            key = (str(row["card_id"]), str(row["action_id"]))
            severity = _as01(row.get("selected_set_omission_severity", 0))
            sufficiency = _as01(row.get("selected_set_sufficiency", 1))
            omission[key] = max(float(omission.get(key, 0.0)), severity)
            quality[key] = min(float(quality.get(key, 1.0)), sufficiency)
            m2b_keys.add(key)
    return MemoryLabels(misuse, omission, quality, frozenset(m2b_keys))


def load_strategy_labels(
    strategy_use_path: str | Path,
    strategy_omission_path: str | Path,
) -> StrategyLabels:
    """Load strategy-use and strategy-omission supervision.

    Risk is high for RS over-structuring/premature advice and for R0 missed
    strategy opportunities.  Decision quality is high when the strategy choice
    is appropriate for the current user state.
    """
    risk: dict[tuple[str, str], float] = {}
    quality: dict[tuple[str, str], float] = {}

    for row in iter_jsonl(strategy_use_path):
        key = (str(row["card_id"]), str(row["action_id"]))
        audit = row.get("strategy_audit") if isinstance(row.get("strategy_audit"), dict) else row
        risk[key] = max(
            _as01(audit.get("over_structuring", 0)),
            _as01(audit.get("premature_advice", 0)),
        )
        relevance = _as01(audit.get("strategy_relevance", 1))
        utilization = _as01(audit.get("strategy_utilization", 1))
        quality[key] = (relevance + utilization) / 2.0

    for row in iter_jsonl(strategy_omission_path):
        key = (str(row["card_id"]), str(row["action_id"]))
        missed = _as01(row.get("missed_strategy_opportunity_severity", 0))
        inappropriate = _as01(row.get("premature_or_overstructured_without_strategy", 0))
        appropriateness = _as01(row.get("strategy_omission_appropriateness", 1))
        risk[key] = max(missed, inappropriate, 1.0 - appropriateness)
        quality[key] = appropriateness
    return StrategyLabels(risk, quality)
