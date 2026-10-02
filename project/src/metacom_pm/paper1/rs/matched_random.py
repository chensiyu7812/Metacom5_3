"""Deterministic matched-random schedules without outcome access."""

from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from collections.abc import Sequence

from pydantic import Field, model_validator

from ..contracts import StrictContract, TreatmentAssignment


class RandomizationUnit(StrictContract):
    unit_id: str = Field(min_length=1)
    eligible: bool
    stratum: str = Field(min_length=1)
    injected_tokens_if_on: int = Field(ge=0)
    learned_assignment: TreatmentAssignment

    @model_validator(mode="after")
    def learned_policy_respects_eligibility(self) -> "RandomizationUnit":
        if not self.eligible and self.learned_assignment is TreatmentAssignment.ON:
            raise ValueError("ineligible unit cannot be learned-ON")
        return self


class MatchedRandomAssignment(StrictContract):
    unit_id: str
    stratum: str
    assignment: TreatmentAssignment
    injected_tokens_if_on: int = Field(ge=0)


class MatchedRandomSchedule(StrictContract):
    seed: int = Field(ge=0)
    proposals: int = Field(ge=1)
    assignments: tuple[MatchedRandomAssignment, ...]
    learned_on_count_by_stratum: dict[str, int]
    random_on_count_by_stratum: dict[str, int]
    learned_injected_token_budget: int = Field(ge=0)
    random_injected_token_budget: int = Field(ge=0)
    absolute_token_budget_difference: int = Field(ge=0)
    exact_token_budget_matched: bool


def _proposal_seed(seed: int, proposal: int, stratum: str) -> int:
    payload = f"paper1-matched-random-v1\0{seed}\0{proposal}\0{stratum}".encode()
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


def build_matched_random_schedule(
    units: Sequence[RandomizationUnit],
    *,
    seed: int,
    proposals: int = 1024,
    require_exact_token_budget: bool = True,
) -> MatchedRandomSchedule:
    """Match realized ON counts exactly and token budget as closely as sampled.

    Strata must be frozen before outcomes (for example benchmark slice and a
    structural token bin).  Among deterministic random proposals, the
    schedule with the smallest absolute injected-token difference is kept.
    By default a nonzero difference is rejected: M2 must then freeze fixed
    padded caps or finer pre-outcome strata rather than report a falsely
    cost-matched control.  This is a control-construction constraint, not a
    performance PASS gate.
    """

    if not units:
        raise ValueError("matched-random requires at least one unit")
    if seed < 0 or proposals < 1:
        raise ValueError("seed must be non-negative and proposals positive")
    ids = [unit.unit_id for unit in units]
    if len(ids) != len(set(ids)):
        raise ValueError("randomization unit IDs must be unique")

    by_stratum: dict[str, list[RandomizationUnit]] = defaultdict(list)
    for unit in units:
        by_stratum[unit.stratum].append(unit)
    learned_counts = Counter(
        unit.stratum for unit in units if unit.learned_assignment is TreatmentAssignment.ON
    )
    learned_budget = sum(
        unit.injected_tokens_if_on
        for unit in units
        if unit.learned_assignment is TreatmentAssignment.ON
    )

    best: tuple[int, int, frozenset[str]] | None = None
    for proposal in range(proposals):
        selected: set[str] = set()
        for stratum in sorted(by_stratum):
            eligible = sorted(
                (unit for unit in by_stratum[stratum] if unit.eligible),
                key=lambda unit: unit.unit_id,
            )
            needed = learned_counts[stratum]
            if needed > len(eligible):
                raise ValueError(f"learned ON count exceeds eligible units in stratum {stratum}")
            rng = random.Random(_proposal_seed(seed, proposal, stratum))
            selected.update(unit.unit_id for unit in rng.sample(eligible, needed))
        budget = sum(unit.injected_tokens_if_on for unit in units if unit.unit_id in selected)
        candidate = (abs(budget - learned_budget), proposal, frozenset(selected))
        if best is None or candidate[:2] < best[:2]:
            best = candidate

    assert best is not None
    _, _proposal, selected_ids = best
    assignments = tuple(
        MatchedRandomAssignment(
            unit_id=unit.unit_id,
            stratum=unit.stratum,
            assignment=(
                TreatmentAssignment.ON
                if unit.unit_id in selected_ids
                else TreatmentAssignment.OFF
            ),
            injected_tokens_if_on=unit.injected_tokens_if_on,
        )
        for unit in sorted(units, key=lambda item: item.unit_id)
    )
    random_counts = Counter(
        row.stratum for row in assignments if row.assignment is TreatmentAssignment.ON
    )
    random_budget = sum(
        row.injected_tokens_if_on
        for row in assignments
        if row.assignment is TreatmentAssignment.ON
    )
    if dict(random_counts) != dict(learned_counts):
        raise RuntimeError("matched-random failed exact stratum-level ON-count matching")
    budget_difference = abs(random_budget - learned_budget)
    if require_exact_token_budget and budget_difference:
        raise ValueError(
            "no exactly token-matched random proposal; freeze fixed padded caps or "
            "finer outcome-blind strata before formal evaluation"
        )

    return MatchedRandomSchedule(
        seed=seed,
        proposals=proposals,
        assignments=assignments,
        learned_on_count_by_stratum=dict(sorted(learned_counts.items())),
        random_on_count_by_stratum=dict(sorted(random_counts.items())),
        learned_injected_token_budget=learned_budget,
        random_injected_token_budget=random_budget,
        absolute_token_budget_difference=budget_difference,
        exact_token_budget_matched=budget_difference == 0,
    )
