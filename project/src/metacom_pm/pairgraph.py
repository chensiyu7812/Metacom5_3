from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
import networkx as nx

from .contracts import (
    MemorySource,
    PairRecord,
    StrategyMode,
    parse_action_id,
)
from .io import stable_hex, iter_jsonl, write_jsonl, write_json


def _memory_distance(a: str, b: str) -> int:
    sa, _ = parse_action_id(a)
    sb, _ = parse_action_id(b)
    return len(sa ^ sb)


def _undirected_edges(actions: list[str]) -> list[tuple[str, str, str]]:
    action_set = set(actions)
    edges: set[tuple[str, str, str]] = set()

    # Same memory mask: R0 versus RS.
    by_sources: dict[frozenset[MemorySource], dict[StrategyMode, str]] = defaultdict(dict)
    for action in actions:
        sources, strategy = parse_action_id(action)
        by_sources[sources][strategy] = action
    for mapping in by_sources.values():
        if StrategyMode.R0 in mapping and StrategyMode.RS in mapping:
            a, b = sorted([mapping[StrategyMode.R0], mapping[StrategyMode.RS]])
            edges.add((a, b, "strategy"))

    # Memory subset lattice inside each strategy layer.
    by_strategy: dict[StrategyMode, list[str]] = defaultdict(list)
    for action in actions:
        _, strategy = parse_action_id(action)
        by_strategy[strategy].append(action)
    for strategy, layer in by_strategy.items():
        for i, a in enumerate(layer):
            sa, _ = parse_action_id(a)
            for b in layer[i + 1 :]:
                sb, _ = parse_action_id(b)
                if len(sa ^ sb) == 1 and (sa < sb or sb < sa):
                    x, y = sorted([a, b])
                    pair_type = "memory" if not sa or not sb else "combination"
                    edges.add((x, y, pair_type))

    # Deterministic chords between equal-size masks to improve identifiability.
    for strategy, layer in by_strategy.items():
        sorted_layer = sorted(layer)
        for i, a in enumerate(sorted_layer):
            sa, _ = parse_action_id(a)
            for b in sorted_layer[i + 1 :]:
                sb, _ = parse_action_id(b)
                if len(sa) == len(sb) and len(sa) > 0 and len(sa ^ sb) == 2:
                    x, y = sorted([a, b])
                    edges.add((x, y, "chord"))

    graph = nx.Graph()
    graph.add_nodes_from(actions)
    graph.add_edges_from((a, b) for a, b, _ in edges)
    if len(graph) and not nx.is_connected(graph):
        components = [sorted(x) for x in nx.connected_components(graph)]
        raise ValueError(f"pair graph disconnected; no fallback is allowed: {components}")
    if set(graph.nodes) != action_set:
        raise ValueError("pair graph omitted a legal action")
    return sorted(edges)


def build_pair_graph(
    runtime_path: str | Path,
    out_pairs_path: str | Path,
    out_audit_path: str | Path,
    *,
    reversal_fraction: float = 0.15,
    repeat_fraction: float = 0.10,
    seed: int = 3201,
    max_cards: int | None = None,
) -> dict[str, Any]:
    states = list(iter_jsonl(runtime_path))
    if max_cards is not None:
        states = states[:max_cards]
    canonical: list[dict[str, Any]] = []
    for state in states:
        edges = _undirected_edges(list(state["allowed_actions"]))
        for a, b, pair_type in edges:
            canonical_id = f"pair_{stable_hex(state['card_id'], a, b, pair_type, n=20)}"
            canonical.append({
                "canonical_pair_id": canonical_id,
                "card_id": state["card_id"],
                "action_left": a,
                "action_right": b,
                "pair_type": pair_type,
            })

    # Balance orientation separately by pair type. Alternation after a stable
    # hash sort guarantees imbalance <= 1 rather than merely hoping for it.
    oriented: list[PairRecord] = []
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in canonical:
        by_type[row["pair_type"]].append(row)
    for pair_type, group in sorted(by_type.items()):
        group = sorted(
            group,
            key=lambda x: stable_hex(seed, pair_type, x["canonical_pair_id"], n=32),
        )
        for index, row in enumerate(group):
            left, right = row["action_left"], row["action_right"]
            left_sources, left_strategy = parse_action_id(left)
            right_sources, right_strategy = parse_action_id(right)
            place_target_in_a = index % 2 == 0
            if pair_type == "strategy":
                # Explicitly balance RS between A and B.
                rs_action = left if left_strategy is StrategyMode.RS else right
                other = right if rs_action == left else left
                action_a, action_b = ((rs_action, other) if place_target_in_a else (other, rs_action))
            elif len(left_sources) != len(right_sources):
                # Explicitly balance the more-resource action between A and B.
                more = left if len(left_sources) > len(right_sources) else right
                less = right if more == left else left
                action_a, action_b = ((more, less) if place_target_in_a else (less, more))
            else:
                action_a, action_b = ((left, right) if place_target_in_a else (right, left))
            oriented.append(PairRecord(
                pair_id=f"pair_{stable_hex(row['canonical_pair_id'], 'base', n=20)}",
                canonical_pair_id=row["canonical_pair_id"],
                card_id=row["card_id"],
                action_a=action_a,
                action_b=action_b,
                pair_type=pair_type,
                training_eligible=True,
            ))

    # Audit repeats are selected by stable hash, never by old utility/judgment.
    audit_rows: list[PairRecord] = []
    ordered = sorted(
        oriented,
        key=lambda x: stable_hex(seed, "audit", x.canonical_pair_id, n=32),
    )
    n_reversal = round(len(ordered) * reversal_fraction)
    n_repeat = round(len(ordered) * repeat_fraction)
    for base in ordered[:n_reversal]:
        audit_rows.append(PairRecord(
            pair_id=f"pair_{stable_hex(base.canonical_pair_id, 'reversal', n=20)}",
            canonical_pair_id=base.canonical_pair_id,
            card_id=base.card_id,
            action_a=base.action_b,
            action_b=base.action_a,
            pair_type=base.pair_type,
            is_reversal=True,
            training_eligible=False,
        ))
    for base in ordered[n_reversal : n_reversal + n_repeat]:
        audit_rows.append(PairRecord(
            pair_id=f"pair_{stable_hex(base.canonical_pair_id, 'repeat', n=20)}",
            canonical_pair_id=base.canonical_pair_id,
            card_id=base.card_id,
            action_a=base.action_a,
            action_b=base.action_b,
            pair_type=base.pair_type,
            is_same_order_repeat=True,
            training_eligible=False,
        ))
    all_pairs = oriented + audit_rows
    write_jsonl(out_pairs_path, [x.model_dump(mode="json") for x in all_pairs])
    audit = graph_audit(states, [x.model_dump(mode="json") for x in all_pairs])
    write_json(out_audit_path, audit)
    if not audit["ok"]:
        raise ValueError("pair graph audit failed: " + "; ".join(audit["errors"]))
    return audit


def graph_audit(states: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    canonical = [x for x in pairs if x.get("training_eligible")]
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in canonical:
        by_card[row["card_id"]].append(row)
    per_card = {}
    for state in states:
        card_id = state["card_id"]
        graph = nx.Graph()
        graph.add_nodes_from(state["allowed_actions"])
        rows = by_card.get(card_id, [])
        graph.add_edges_from((x["action_a"], x["action_b"]) for x in rows)
        components = nx.number_connected_components(graph) if graph.number_of_nodes() else 0
        isolated = list(nx.isolates(graph))
        seen = {
            tuple(sorted((x["action_a"], x["action_b"])))
            for x in rows
        }
        if len(seen) != len(rows):
            errors.append(f"{card_id}: duplicate canonical pair")
        if components != 1:
            errors.append(f"{card_id}: {components} connected components")
        if isolated:
            errors.append(f"{card_id}: isolated actions {isolated}")
        per_card[card_id] = {
            "n_actions": len(state["allowed_actions"]),
            "n_pairs": len(rows),
            "connected_components": components,
            "isolated_actions": isolated,
            "min_degree": min((degree for _, degree in graph.degree()), default=0),
            "max_degree": max((degree for _, degree in graph.degree()), default=0),
        }

    orientation = {}
    for pair_type in sorted({x["pair_type"] for x in canonical}):
        rows = [x for x in canonical if x["pair_type"] == pair_type]
        left_rs = sum(parse_action_id(x["action_a"])[1] is StrategyMode.RS for x in rows)
        right_rs = sum(parse_action_id(x["action_b"])[1] is StrategyMode.RS for x in rows)
        left_more = sum(
            len(parse_action_id(x["action_a"])[0]) > len(parse_action_id(x["action_b"])[0])
            for x in rows
        )
        right_more = sum(
            len(parse_action_id(x["action_b"])[0]) > len(parse_action_id(x["action_a"])[0])
            for x in rows
        )
        if abs(left_rs - right_rs) > 1:
            errors.append(f"{pair_type}: RS position imbalance {left_rs} vs {right_rs}")
        if abs(left_more - right_more) > 1:
            errors.append(
                f"{pair_type}: memory-count position imbalance {left_more} vs {right_more}"
            )
        orientation[pair_type] = {
            "n": len(rows),
            "a_is_rs": left_rs,
            "b_is_rs": right_rs,
            "a_has_more_memory": left_more,
            "b_has_more_memory": right_more,
        }

    return {
        "ok": not errors,
        "errors": errors,
        "n_states": len(states),
        "n_training_pairs": len(canonical),
        "n_reversal_pairs": sum(x.get("is_reversal", False) for x in pairs),
        "n_same_order_repeats": sum(x.get("is_same_order_repeat", False) for x in pairs),
        "orientation": orientation,
        "per_card": per_card,
    }
