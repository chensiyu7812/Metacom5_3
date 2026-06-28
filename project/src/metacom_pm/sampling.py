from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

from .contracts import RuntimeState
from .io import stable_hex


def inventory_signature(state: RuntimeState) -> tuple[int, int, int]:
    return tuple(state.inventory[source].count for source in state.inventory)  # enum order MP/MS/ME


def select_stratified_card_ids(
    states: Mapping[str, RuntimeState],
    n: int,
    *,
    seed: int = 20260621,
    eligible: set[str] | None = None,
) -> list[str]:
    if n <= 0:
        return []
    pool = [state for card_id, state in states.items() if eligible is None or card_id in eligible]
    if n >= len(pool):
        return sorted(state.card_id for state in pool)
    ordered = sorted(pool, key=lambda x: stable_hex(seed, x.card_id, n=32))
    selected: list[RuntimeState] = []
    seen: set[str] = set()

    def add(state: RuntimeState) -> None:
        if state.card_id not in seen and len(selected) < n:
            selected.append(state); seen.add(state.card_id)

    groups = [
        lambda s: s.semantic_family,
        lambda s: inventory_signature(s),
        lambda s: len(s.allowed_actions),
        lambda s: s.user_id,
    ]
    for key_fn in groups:
        by_group: dict[object, list[RuntimeState]] = defaultdict(list)
        for state in ordered:
            by_group[key_fn(state)].append(state)
        for key in sorted(by_group, key=str):
            add(by_group[key][0])
    for state in ordered:
        add(state)
    return [state.card_id for state in selected]
