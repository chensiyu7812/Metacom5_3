from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import re

from sklearn.feature_extraction.text import HashingVectorizer
import numpy as np

from .contracts import (
    ACTION_MEMORY_MAP,
    MemoryBackendRecord,
    MemoryItem,
    MemorySource,
    RuntimeState,
    SourceCatalog,
    canonical_action_id,
    StrategyMode,
)
from .io import iter_jsonl, stable_hex, write_jsonl, write_json, sha256_file
from .text import clean_memory_text, estimate_tokens, lexical_score, normalize_space


def opaque_id(prefix: str, *parts: object) -> str:
    return f"{prefix}_{stable_hex(*parts, n=20)}"


def _fingerprint(texts: list[str], n_features: int = 64) -> list[float]:
    if not texts:
        return [0.0] * n_features
    vec = HashingVectorizer(
        n_features=n_features,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
    ).transform(["\n".join(texts)])
    dense = np.asarray(vec.toarray()[0], dtype=float)
    return [round(float(x), 8) for x in dense]


def _build_catalog(
    source: MemorySource,
    items: list[MemoryItem],
    session_index: int,
) -> SourceCatalog:
    ages = [max(0, session_index - item.created_session) for item in items]
    return SourceCatalog(
        available=bool(items),
        count=len(items),
        min_age_sessions=min(ages) if ages else None,
        max_age_sessions=max(ages) if ages else None,
        estimated_tokens=sum(estimate_tokens(item.text) for item in items),
        catalog_fingerprint=_fingerprint([item.text for item in items]),
    )


def _clean_source_item(
    user_id: str,
    original: dict[str, Any],
    source: MemorySource,
) -> MemoryItem:
    text = clean_memory_text(str(original.get("text") or ""))
    created = int(original.get("session_index") or 0)
    return MemoryItem(
        memory_id=opaque_id("mem", user_id, original.get("memory_id"), source.value, text, created),
        source=source,
        created_session=created,
        timestamp=None,
        text=text,
    )


def _derive_update_items(
    user_id: str,
    items: list[MemoryItem],
    max_session: int,
) -> list[MemoryItem]:
    """Create text-grounded update examples without exposing audit flags.

    These are synthetic memories, not labels.  The update relation is expressed
    entirely in timestamps and natural-language text so evaluators can infer it
    without hidden stale/conflict flags.
    """
    out: list[MemoryItem] = []
    mp = next((x for x in items if x.source is MemorySource.MP), None)
    if mp and max_session >= mp.created_session + 2:
        base = mp.text.rstrip(".")
        update_text = (
            f"Later update: the user said the earlier preference ({base.lower()}) "
            "is no longer reliable for every conversation and asked the supporter "
            "to follow the needs expressed in the current exchange instead."
        )
        created = min(max_session - 1, mp.created_session + 2)
        out.append(MemoryItem(
            memory_id=opaque_id("mem", user_id, "mp_update", update_text, created),
            source=MemorySource.MP,
            created_session=created,
            text=update_text,
        ))
    me = next((x for x in items if x.source is MemorySource.ME), None)
    if me and max_session >= me.created_session + 2:
        base = me.text.rstrip(".")
        update_text = (
            f"Later update: after {base.lower()}, the user reported that the "
            "situation had changed and should not be treated as their current state."
        )
        created = min(max_session - 1, me.created_session + 2)
        out.append(MemoryItem(
            memory_id=opaque_id("mem", user_id, "me_update", update_text, created),
            source=MemorySource.ME,
            created_session=created,
            text=update_text,
        ))
    return out


def prepare_synthetic_counterfactuals(
    source_cards_path: str | Path,
    out_runtime_path: str | Path,
    out_backend_path: str | Path,
    out_audit_path: str | Path,
    out_summary_path: str | Path,
    *,
    max_states: int | None = None,
    variant_mode: str = "balanced9",
) -> dict[str, Any]:
    rows = list(iter_jsonl(source_cards_path))
    if max_states is not None:
        rows = rows[:max_states]
    if not rows:
        raise ValueError("no synthetic source cards")

    # Collect every unique memory item per user, then add explicit natural-
    # language update memories.  Old flags and semantic IDs never leave this
    # preparation function.
    pool: dict[str, dict[str, MemoryItem]] = defaultdict(dict)
    max_session_by_user: dict[str, int] = defaultdict(int)
    for row in rows:
        user_id = str(row["user_id"])
        max_session_by_user[user_id] = max(
            max_session_by_user[user_id], int(row.get("session_depth") or 1)
        )
        store = row.get("memory_store") or {}
        for src in MemorySource:
            for original in store.get(src.value) or []:
                item = _clean_source_item(user_id, original, src)
                pool[user_id][item.memory_id] = item

    for user_id, mapping in list(pool.items()):
        for item in _derive_update_items(
            user_id, list(mapping.values()), max_session_by_user[user_id]
        ):
            mapping[item.memory_id] = item

    runtime_rows: list[dict[str, Any]] = []
    backend_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for source_row in rows:
        user_id = str(source_row["user_id"])
        session_index = int(source_row.get("session_depth") or 1)
        context = "\n".join([
            str(source_row.get("current_session_summary") or ""),
            str(source_row.get("current_user_text") or ""),
        ])
        causal = [
            item for item in pool[user_id].values()
            if item.created_session < session_index
        ]
        by_source: dict[MemorySource, list[MemoryItem]] = {
            src: sorted(
                [x for x in causal if x.source is src],
                key=lambda x: (x.created_session, x.memory_id),
            )
            for src in MemorySource
        }

        available_sources = [src for src in MemorySource if by_source[src]]
        base_variants: list[tuple[str, dict[MemorySource, list[MemoryItem]]]] = []

        def chosen_for(sources: tuple[MemorySource, ...], *, me_item: MemoryItem | None = None):
            return {
                src: (
                    ([me_item] if src is MemorySource.ME and me_item is not None else list(by_source[src]))
                    if src in sources else []
                )
                for src in MemorySource
            }

        if variant_mode == "all":
            for size in range(0, len(available_sources) + 1):
                for subset in combinations(available_sources, size):
                    label = "none" if not subset else "_".join(src.value.lower() for src in subset)
                    base_variants.append((label, chosen_for(tuple(subset))))
        elif variant_mode == "balanced9":
            # Nine scientifically useful inventory variants per dialogue state.
            # This covers the source lattice while avoiding a prohibitively
            # expensive 16-variant/action sweep. ME-high and ME-low have the
            # same availability and count, so a metadata-only lookup cannot
            # solve the relevance decision.
            ranked_me = sorted(
                by_source[MemorySource.ME],
                key=lambda x: (lexical_score(context, x.text), x.memory_id),
                reverse=True,
            )
            high_me = ranked_me[0] if ranked_me else None
            low_me = ranked_me[-1] if len(ranked_me) >= 2 else high_me
            plans: list[tuple[str, tuple[MemorySource, ...], MemoryItem | None]] = [
                ("none", tuple(), None),
                ("mp", (MemorySource.MP,), None),
                ("ms", (MemorySource.MS,), None),
                ("me_high", (MemorySource.ME,), high_me),
                ("me_low", (MemorySource.ME,), low_me),
                ("mp_ms", (MemorySource.MP, MemorySource.MS), None),
                ("mp_me", (MemorySource.MP, MemorySource.ME), high_me),
                ("ms_me", (MemorySource.MS, MemorySource.ME), low_me),
                ("mp_ms_me", (MemorySource.MP, MemorySource.MS, MemorySource.ME), high_me),
            ]
            for label, subset, me_item in plans:
                if all(by_source[src] for src in subset):
                    base_variants.append((label, chosen_for(subset, me_item=me_item)))
        else:
            raise ValueError("variant_mode must be balanced9 or all")
        # Dedupe variants by actual opaque IDs.
        seen_variants: set[tuple[tuple[str, ...], ...]] = set()
        for variant_name, selected in base_variants:
            signature = tuple(
                tuple(x.memory_id for x in selected[src])
                for src in MemorySource
            )
            if signature in seen_variants:
                continue
            seen_variants.add(signature)

            original_state_key = (
                source_row.get("sim_card_id"),
                user_id,
                source_row.get("current_user_text"),
                source_row.get("session_depth"),
            )
            state_id = opaque_id("state", *original_state_key)
            card_id = opaque_id("card", state_id, variant_name, signature)
            inventory = {
                src: _build_catalog(src, selected[src], session_index)
                for src in MemorySource
            }
            available = {src for src in MemorySource if selected[src]}
            actions = sorted(
                canonical_action_id(source_set, strategy)
                for source_set in ACTION_MEMORY_MAP.values()
                if source_set <= available
                for strategy in StrategyMode
            )
            history = [
                {"role": str(turn["role"]), "content": normalize_space(turn["content"])}
                for turn in (source_row.get("current_session_history") or [])
            ]
            semantic_family = str(
                source_row.get("semantic_family")
                or (source_row.get("private_seeker_state") or {}).get("semantic_family")
                or "unknown"
            )
            runtime = RuntimeState(
                state_id=state_id,
                card_id=card_id,
                user_id=user_id,
                split="development",
                semantic_family=semantic_family,
                current_user_text=normalize_space(source_row["current_user_text"]),
                current_session_history=history,
                current_session_summary=normalize_space(
                    source_row.get("current_session_summary") or ""
                ),
                session_index=session_index,
                inventory=inventory,
                allowed_actions=actions,
                provenance={
                    "dataset": "synthetic_counterfactual_v4",
                    "schema_version": "4",
                },
            )
            backend = MemoryBackendRecord(
                card_id=card_id,
                items=[
                    item
                    for src in MemorySource
                    for item in selected[src]
                ],
            )
            runtime_rows.append(runtime.model_dump(mode="json"))
            backend_rows.append(backend.model_dump(mode="json"))
            audit_rows.append({
                "card_id": card_id,
                "state_id": state_id,
                "variant": variant_name,
                "source_card_id": source_row.get("sim_card_id"),
                "construction_only": True,
                "not_visible_to_pm_or_generator": True,
            })

    write_jsonl(out_runtime_path, runtime_rows)
    write_jsonl(out_backend_path, backend_rows)
    write_jsonl(out_audit_path, audit_rows)
    summary = {
        "source_sha256": sha256_file(source_cards_path),
        "n_source_states": len(rows),
        "n_runtime_cards": len(runtime_rows),
        "n_users": len({x["user_id"] for x in runtime_rows}),
        "n_semantic_families": len({x["semantic_family"] for x in runtime_rows}),
        "n_unique_current_texts": len({x["current_user_text"] for x in runtime_rows}),
        "variant_mode": variant_mode,
        "action_count_distribution": dict(sorted(
            __import__("collections").Counter(
                len(x["allowed_actions"]) for x in runtime_rows
            ).items()
        )),
        "runtime_path": str(out_runtime_path),
        "backend_path": str(out_backend_path),
    }
    write_json(out_summary_path, summary)
    return summary
