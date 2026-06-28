from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence
import time
import numpy as np

from .api import Endpoint, OpenAICompatibleClient
from .contracts import StrategyMode, parse_action_id
from .io import append_jsonl, iter_jsonl, load_done_keys, write_json
from .prompts import generation_messages
from .retrieval import MemoryRetriever, StrategyRetriever, context_query
from .sweep import load_backends, load_states, load_strategy_cards
from .text import token_set


def _jaccard_distance(a: str, b: str) -> float:
    sa, sb = token_set(a), token_set(b)
    if not sa and not sb:
        return 0.0
    return 1.0 - len(sa & sb) / max(len(sa | sb), 1)


def run_generation_variance_diagnostic(
    runtime_path: str | Path,
    backend_path: str | Path,
    strategy_bank_path: str | Path,
    out_jsonl: str | Path,
    out_report: str | Path,
    *,
    endpoint: Endpoint,
    card_ids: Sequence[str],
    action_ids: Sequence[str],
    seeds: Sequence[int] = (101, 202, 303),
    max_tokens: int = 320,
) -> dict[str, Any]:
    states = load_states(runtime_path)
    backends = load_backends(backend_path)
    strategy_cards = load_strategy_cards(strategy_bank_path)
    strategy_retriever = StrategyRetriever(strategy_cards, top_k=3)
    expected_keys = {
        (card_id, action_id, seed)
        for card_id in card_ids
        for action_id in action_ids
        if action_id in states[card_id].allowed_actions
        for seed in seeds
    }
    done: set[tuple[str, str, int]] = set()
    duplicates: list[tuple[str, str, int]] = []
    extras: list[tuple[Any, Any, Any]] = []
    if Path(out_jsonl).exists():
        for row in iter_jsonl(out_jsonl):
            key = (row.get("card_id"), row.get("action_id"), row.get("seed"))
            if key in done:
                duplicates.append(key)  # type: ignore[arg-type]
            done.add(key)  # type: ignore[arg-type]
            if key not in expected_keys:
                extras.append(key)
    if duplicates or extras:
        raise RuntimeError(
            "generator variance output is incompatible with the requested "
            f"card/action/seed set; duplicates={duplicates[:5]}, "
            f"extras={extras[:5]}. Use --overwrite or a new --out-dir."
        )
    client = OpenAICompatibleClient(endpoint)
    try:
        for card_id in card_ids:
            state = states[card_id]
            backend = backends[card_id]
            memory_retriever = MemoryRetriever()
            query = context_query(
                state.current_user_text,
                [x.model_dump(mode="json") for x in state.current_session_history],
                state.current_session_summary,
            )
            for action_id in action_ids:
                if action_id not in state.allowed_actions:
                    continue
                sources, strategy = parse_action_id(action_id)
                memory = memory_retriever.retrieve(query, backend.items, sources)
                cards = strategy_retriever.retrieve(query) if strategy is StrategyMode.RS else []
                messages = generation_messages(state, memory, cards)
                for seed in seeds:
                    key = (card_id, action_id, seed)
                    if key in done:
                        continue
                    result, _ = client.chat(
                        messages,
                        temperature=0.2,
                        max_tokens=max_tokens,
                        seed=seed,
                        retries=5,
                    )
                    time.sleep(1.5)  # polite inter-request delay to avoid 429
                    append_jsonl(out_jsonl, {
                        "card_id": card_id,
                        "action_id": action_id,
                        "seed": seed,
                        "response": result.text,
                        "usage": result.usage,
                        "latency_ms": result.latency_ms,
                    })
    finally:
        client.close()

    rows = [
        row for row in iter_jsonl(out_jsonl)
        if (row.get("card_id"), row.get("action_id"), row.get("seed")) in expected_keys
    ]
    completed_keys = {
        (row.get("card_id"), row.get("action_id"), row.get("seed"))
        for row in rows
    }
    missing = expected_keys - completed_keys
    if missing:
        raise RuntimeError(
            f"generator variance incomplete; missing rows={sorted(missing)[:5]}"
        )
    by_card_action: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_card: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_card_action[(row["card_id"], row["action_id"])].append(row["response"])
        by_card[row["card_id"]][row["action_id"]].append(row["response"])
    within: list[float] = []
    for responses in by_card_action.values():
        for i in range(len(responses)):
            for j in range(i + 1, len(responses)):
                within.append(_jaccard_distance(responses[i], responses[j]))
    between: list[float] = []
    for action_map in by_card.values():
        action_names = sorted(action_map)
        for i in range(len(action_names)):
            for j in range(i + 1, len(action_names)):
                # Matched seed position whenever possible.
                a, b = action_map[action_names[i]], action_map[action_names[j]]
                for k in range(min(len(a), len(b))):
                    between.append(_jaccard_distance(a[k], b[k]))
    within_mean = float(np.mean(within)) if within else None
    between_mean = float(np.mean(between)) if between else None
    ratio = (
        between_mean / within_mean
        if between_mean is not None and within_mean not in (None, 0.0)
        else None
    )
    report = {
        "n_rows": len(rows),
        "n_card_actions": len(by_card_action),
        "n_requested_cards": len(card_ids),
        "n_unique_base_states": len({states[card_id].state_id for card_id in card_ids}),
        "selected_card_ids": list(card_ids),
        "action_ids": list(action_ids),
        "seeds": list(seeds),
        "expected_rows": len(expected_keys),
        "within_action_mean_lexical_distance": within_mean,
        "between_action_mean_lexical_distance": between_mean,
        "between_to_within_ratio": ratio,
        "diagnostic_pass": bool(ratio is not None and ratio > 1.10),
        "note": "Lexical distance is a conservative variance diagnostic, not a quality metric.",
    }
    write_json(out_report, report)
    return report


def select_variance_card_ids(runtime_path: str | Path, n_states: int) -> list[str]:
    """Select one full-action card per independent state for variance tests.

    This avoids the old diagnostic's inventory-sibling inflation where the first
    N cards could all share the same base state/current text.
    """
    states = load_states(runtime_path)
    selected: list[str] = []
    seen_states: set[str] = set()
    for card_id in sorted(states):
        state = states[card_id]
        if state.state_id in seen_states:
            continue
        # Full 16-action states let the diagnostic compare every MP/MS/ME/RS toggle.
        if len(state.allowed_actions) < 16:
            continue
        selected.append(card_id)
        seen_states.add(state.state_id)
        if len(selected) >= n_states:
            break
    if len(selected) < n_states:
        raise ValueError(
            f"requested {n_states} independent full-action states, found {len(selected)}"
        )
    return selected
