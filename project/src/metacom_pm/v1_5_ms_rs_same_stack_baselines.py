"""Outcome-blind policies for the bounded V3 RS+MS same-stack panel.

This module does not fit a model or read response outcomes.  It maps one frozen
MS probability and one frozen four-arm prompt-cost surface per state to policy
actions that already have generated responses.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Mapping, Sequence


ACTIONS = ("M0+R0", "MS+R0", "M0+RS", "MS+RS")


def transparent_ms_on(*, low_information_rank1: bool, current_echo: bool) -> bool:
    """Strong transparent nuisance guard; it deliberately cannot judge meaning."""

    return not low_information_rank1 and not current_echo


def action_for(*, ms_on: bool, rs_on: bool) -> str:
    if rs_on:
        return "MS+RS" if ms_on else "M0+RS"
    return "MS+R0" if ms_on else "M0+R0"


def choose_cost_matched_fixed(
    *,
    state_ids: Sequence[str],
    learned_actions: Mapping[str, str],
    estimated_input_tokens: Mapping[tuple[str, str], int],
) -> dict:
    """Choose one fixed action using prompt cost only, never response outcomes."""

    if not state_ids:
        raise ValueError("state_ids must be non-empty")
    target = sum(estimated_input_tokens[(state, learned_actions[state])] for state in state_ids)
    candidates = []
    for action in ACTIONS:
        total = sum(estimated_input_tokens[(state, action)] for state in state_ids)
        candidates.append((abs(total - target), action, total))
    difference, action, total = min(candidates, key=lambda row: (row[0], row[1]))
    relative = difference / max(target, 1)
    return {
        "action": action,
        "target_total_estimated_input_tokens": target,
        "fixed_total_estimated_input_tokens": total,
        "absolute_difference": difference,
        "relative_mismatch": relative,
        "qualified_at_5_percent": relative <= 0.05,
    }


def choose_on_rate_matched_random(
    *,
    state_ids: Sequence[str],
    learned_ms_on: Mapping[str, bool],
    estimated_input_tokens: Mapping[tuple[str, str], int],
    seed: str,
    minimum_changed_fraction: float = 0.25,
) -> dict:
    """Permute MS bits, preserving RS=ON and the learned MS ON count exactly."""

    if not state_ids or not seed:
        raise ValueError("state_ids and seed must be non-empty")
    ordered = sorted(
        state_ids,
        key=lambda state: (
            sha256(f"{seed}\x1f{state}".encode("utf-8")).hexdigest(),
            state,
        ),
    )
    learned_actions = {
        state: action_for(ms_on=learned_ms_on[state], rs_on=True) for state in ordered
    }
    target_cost = sum(estimated_input_tokens[(state, learned_actions[state])] for state in ordered)
    candidates = []
    for shift in range(1, len(ordered)):
        assignment = {
            recipient: bool(learned_ms_on[ordered[(index + shift) % len(ordered)]])
            for index, recipient in enumerate(ordered)
        }
        changed = sum(assignment[state] != learned_ms_on[state] for state in ordered)
        changed_fraction = changed / len(ordered)
        if changed_fraction < minimum_changed_fraction:
            continue
        actions = {
            state: action_for(ms_on=assignment[state], rs_on=True) for state in ordered
        }
        cost = sum(estimated_input_tokens[(state, actions[state])] for state in ordered)
        tie = sha256(f"{seed}\x1f{shift}".encode("utf-8")).hexdigest()
        candidates.append((abs(cost - target_cost), -changed, tie, shift, assignment, actions, cost))
    if not candidates:
        raise ValueError("no nontrivial matched-random permutation exists")
    difference, neg_changed, _tie, shift, assignment, actions, cost = min(
        candidates, key=lambda row: row[:3]
    )
    return {
        "shift": shift,
        "ms_on": assignment,
        "actions": actions,
        "learned_ms_on_count": sum(learned_ms_on.values()),
        "random_ms_on_count": sum(assignment.values()),
        "changed_states": -neg_changed,
        "changed_fraction": (-neg_changed) / len(ordered),
        "target_total_estimated_input_tokens": target_cost,
        "random_total_estimated_input_tokens": cost,
        "relative_cost_mismatch": difference / max(target_cost, 1),
        "qualified_at_5_percent": difference / max(target_cost, 1) <= 0.05,
    }

