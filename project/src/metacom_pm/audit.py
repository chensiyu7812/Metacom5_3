from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import json
import re

from .contracts import MemoryBackendRecord, RuntimeState
from .io import iter_jsonl, sha256_file, write_json
from .text import normalize_for_hash


FORBIDDEN_RUNTIME_KEYS = {
    "gold", "expected", "oracle", "private", "need_type", "audit",
    "stale", "conflict", "sensitive", "retrieval_score", "judge",
}
FORBIDDEN_MEMORY_MARKERS = (
    "unrelated prior event",
    "outdated note",
    "conflicting note",
    "score=",
    "stale=",
    "conflict=",
    "[me;",
    "[mp;",
    "[ms;",
)


def _scan_keys(obj: Any, path: str = "") -> list[str]:
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = key.lower()
            if any(token in lowered for token in FORBIDDEN_RUNTIME_KEYS):
                found.append(path + "/" + key)
            found.extend(_scan_keys(value, path + "/" + key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found.extend(_scan_keys(value, path + f"/{index}"))
    return found


def audit_synthetic_release(
    runtime_path: str | Path,
    backend_path: str | Path,
    out_path: str | Path,
) -> dict[str, Any]:
    runtime_rows = list(iter_jsonl(runtime_path))
    backend_rows = list(iter_jsonl(backend_path))
    states = {
        row["card_id"]: RuntimeState.model_validate(row)
        for row in runtime_rows
    }
    backends = {
        row["card_id"]: MemoryBackendRecord.model_validate(row)
        for row in backend_rows
    }
    errors: list[str] = []
    warnings: list[str] = []
    if set(states) != set(backends):
        errors.append("runtime and backend card IDs differ")
    key_violations = []
    memory_marker_violations = []
    future_violations = []
    by_state = defaultdict(list)
    inventory_signature_to_states = defaultdict(set)
    for raw in runtime_rows:
        key_violations.extend(
            f"{raw.get('card_id')}:{path}" for path in _scan_keys(raw)
        )
        by_state[raw["state_id"]].append(raw)
        signature = tuple(
            (source, raw["inventory"][source]["count"])
            for source in ("MP", "MS", "ME")
        )
        inventory_signature_to_states[signature].add(raw["state_id"])
    for card_id, backend in backends.items():
        state = states[card_id]
        for item in backend.items:
            if item.created_session >= state.session_index:
                future_violations.append(
                    f"{card_id}:{item.memory_id}:{item.created_session}>={state.session_index}"
                )
            lowered = item.text.lower()
            if any(marker in lowered for marker in FORBIDDEN_MEMORY_MARKERS):
                memory_marker_violations.append(f"{card_id}:{item.memory_id}")
    if key_violations:
        errors.append(f"forbidden runtime keys: {len(key_violations)}")
    if memory_marker_violations:
        errors.append(f"forbidden memory markers: {len(memory_marker_violations)}")
    if future_violations:
        errors.append(f"future memory violations: {len(future_violations)}")
    state_variant_counts = [len(rows) for rows in by_state.values()]
    if min(state_variant_counts, default=0) < 2:
        errors.append("some state has fewer than two counterfactual inventories")
    reusable_signatures = sum(
        len(state_ids) >= 2 for state_ids in inventory_signature_to_states.values()
    )
    if reusable_signatures < 2:
        errors.append("inventory profiles do not cross multiple dialogue states")
    exact_text_counts = Counter(
        normalize_for_hash(row["current_user_text"]) for row in runtime_rows
    )
    report = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "hashes": {
            "runtime": sha256_file(runtime_path),
            "backend": sha256_file(backend_path),
        },
        "counts": {
            "runtime_cards": len(runtime_rows),
            "states": len(by_state),
            "users": len({row["user_id"] for row in runtime_rows}),
            "semantic_families": len({
                row["semantic_family"] for row in runtime_rows
            }),
            "unique_current_texts": len(exact_text_counts),
            "min_variants_per_state": min(state_variant_counts, default=0),
            "max_variants_per_state": max(state_variant_counts, default=0),
            "reused_inventory_signatures": reusable_signatures,
        },
        "violations": {
            "runtime_key_paths": key_violations[:100],
            "memory_markers": memory_marker_violations[:100],
            "future_memory": future_violations[:100],
        },
        "interpretation": (
            "Repeated text across counterfactual inventory variants is intentional; "
            "confirmatory evidence must come from ESConv/EvoEmo rather than this development set."
        ),
    }
    write_json(out_path, report)
    if errors:
        raise ValueError("synthetic release audit failed: " + "; ".join(errors))
    return report
