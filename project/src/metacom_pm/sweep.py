from __future__ import annotations

from pathlib import Path
from typing import Any
import time

from .api import Endpoint, OpenAICompatibleClient, request_log
from .artifacts import create_artifact_attestation
from .contracts import (
    ActionOutcome,
    CostRecord,
    MemoryBackendRecord,
    RuntimeState,
    StrategyCard,
    StrategyMode,
    parse_action_id,
)
from .io import (
    append_jsonl,
    iter_jsonl,
    load_done_keys,
    sha256_file,
    sha256_text,
    canonical_json,
    write_json,
    utc_now,
    ensure_run_manifest,
)
from .prompts import generation_messages, BASE_SUPPORTER_SYSTEM
from .retrieval import MemoryRetriever, StrategyRetriever, context_query
from .text import estimate_tokens
from .sampling import select_stratified_card_ids


def load_states(path: str | Path) -> dict[str, RuntimeState]:
    return {
        row["card_id"]: RuntimeState.model_validate(row)
        for row in iter_jsonl(path)
    }


def load_backends(path: str | Path) -> dict[str, MemoryBackendRecord]:
    return {
        row["card_id"]: MemoryBackendRecord.model_validate(row)
        for row in iter_jsonl(path)
    }


def load_strategy_cards(path: str | Path) -> list[StrategyCard]:
    return [StrategyCard.model_validate(row) for row in iter_jsonl(path)]


def run_action_sweep(
    runtime_path: str | Path,
    backend_path: str | Path,
    strategy_bank_path: str | Path,
    out_outcomes_path: str | Path,
    out_raw_calls_path: str | Path,
    out_summary_path: str | Path,
    *,
    endpoint: Endpoint,
    max_cards: int | None = None,
    action_filter: set[str] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 300,
    seed: int | None = 4311,
    strategy_top_k: int = 3,
    overwrite: bool = False,
    system_prompt: str = BASE_SUPPORTER_SYSTEM,
    study_freeze_sha256: str | None = None,
) -> dict[str, Any]:
    runtime_path = Path(runtime_path)
    backend_path = Path(backend_path)
    strategy_bank_path = Path(strategy_bank_path)
    out_outcomes_path = Path(out_outcomes_path)
    out_raw_calls_path = Path(out_raw_calls_path)

    manifest_path = Path(out_summary_path).parent / "run_manifest.json"
    if overwrite:
        for path in (out_outcomes_path, out_raw_calls_path, manifest_path):
            if path.exists():
                path.unlink()
    run_metadata = {
        "stage": "action_sweep",
        "runtime_sha256": sha256_file(runtime_path),
        "backend_sha256": sha256_file(backend_path),
        "strategy_bank_sha256": sha256_file(strategy_bank_path),
        "endpoint_model": endpoint.model,
        "endpoint_base_url": endpoint.base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
        "strategy_top_k": strategy_top_k,
        "action_filter": sorted(action_filter) if action_filter else None,
        "system_prompt_sha256": sha256_text(system_prompt),
    }
    if study_freeze_sha256 is not None:
        run_metadata["study_freeze_sha256"] = study_freeze_sha256
    ensure_run_manifest(manifest_path, run_metadata, overwrite=False)

    states = load_states(runtime_path)
    backends = load_backends(backend_path)
    if set(states) != set(backends):
        raise ValueError("runtime/backend card IDs differ")
    cards = list(states)
    if max_cards is not None:
        cards = select_stratified_card_ids(states, max_cards)
    expected_keys = {
        (card_id, action_id)
        for card_id in cards
        for action_id in states[card_id].allowed_actions
        if action_filter is None or action_id in action_filter
    }

    strategies = load_strategy_cards(strategy_bank_path)
    if not strategies:
        raise ValueError("strategy bank is empty")
    strategy_retriever = StrategyRetriever(strategies, top_k=strategy_top_k)
    memory_retriever = MemoryRetriever()

    done: set[tuple[Any, Any]] = set()
    duplicates: list[tuple[Any, Any]] = []
    extras: list[tuple[Any, Any]] = []
    if out_outcomes_path.exists():
        for row in iter_jsonl(out_outcomes_path):
            key = (row.get("card_id"), row.get("action_id"))
            if key in done:
                duplicates.append(key)
            done.add(key)
            if key not in expected_keys:
                extras.append(key)
    if duplicates or extras:
        raise RuntimeError(
            "action sweep output is incompatible with immutable run manifest; "
            f"duplicates={duplicates[:5]}, extras={extras[:5]}. "
            "Use a new directory or --overwrite."
        )
    client = OpenAICompatibleClient(endpoint)
    n_calls = 0
    failures: list[dict[str, Any]] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    try:
        for card_id in cards:
            state = states[card_id]
            backend = backends[card_id]
            query = context_query(
                state.current_user_text,
                [x.model_dump(mode="json") for x in state.current_session_history],
                state.current_session_summary,
            )
            for action_id in state.allowed_actions:
                if action_filter is not None and action_id not in action_filter:
                    continue
                if (card_id, action_id) in done:
                    continue
                sources, strategy_mode = parse_action_id(action_id)
                memory_view = memory_retriever.retrieve(query, backend.items, sources)
                strategy_view = (
                    strategy_retriever.retrieve(query)
                    if strategy_mode is StrategyMode.RS
                    else []
                )
                messages = generation_messages(
                    state, memory_view, strategy_view, system_prompt=system_prompt
                )
                prompt_hash = sha256_text(canonical_json(messages))
                started = time.perf_counter()
                result = None
                try:
                    result, _ = client.chat(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        seed=seed,
                        response_schema=None,
                        retries=3,
                    )
                    n_calls += 1
                    for key in total_usage:
                        total_usage[key] += result.usage[key]
                    base_tokens = estimate_tokens(
                        state.current_user_text
                        + state.current_session_summary
                        + "\n".join(x.content for x in state.current_session_history)
                        + system_prompt
                    )
                    memory_tokens = sum(estimate_tokens(x.text) for x in memory_view)
                    strategy_tokens = sum(
                        estimate_tokens(x.guidance_text + x.example_response)
                        for x in strategy_view
                    )
                    cost = CostRecord(
                        pm_input_tokens_est=estimate_tokens(query) + sum(
                            len(cat.catalog_fingerprint)
                            for cat in state.inventory.values()
                        ),
                        retrieval_calls=len(sources)
                        + (1 if strategy_mode is StrategyMode.RS else 0),
                        reranker_calls=0,
                        memory_tokens=memory_tokens,
                        strategy_tokens=strategy_tokens,
                        base_prompt_tokens=base_tokens,
                        total_input_tokens=(
                            result.usage["prompt_tokens"]
                            or base_tokens + memory_tokens + strategy_tokens
                        ),
                        output_tokens=(
                            result.usage["completion_tokens"]
                            or estimate_tokens(result.text)
                        ),
                        latency_ms=result.latency_ms,
                        api_cost_usd=None,
                    )
                    outcome = ActionOutcome(
                        card_id=card_id,
                        state_id=state.state_id,
                        user_id=state.user_id,
                        action_id=action_id,
                        response=result.text,
                        selected_memory_ids=[x.memory_id for x in memory_view],
                        selected_strategy_ids=[x.strategy_id for x in strategy_view],
                        memory_view=memory_view,
                        strategy_view=strategy_view,
                        cost=cost,
                        model_name=endpoint.model,
                        prompt_hash=prompt_hash,
                        request_hash=result.request_hash,
                        provenance={
                            "runtime_sha256": sha256_file(runtime_path),
                            "backend_sha256": sha256_file(backend_path),
                            "strategy_bank_sha256": sha256_file(strategy_bank_path),
                            "generated_at": utc_now(),
                            "temperature": temperature,
                            "seed": seed,
                        },
                    )
                    append_jsonl(out_outcomes_path, outcome.model_dump(mode="json"))
                    append_jsonl(
                        out_raw_calls_path,
                        request_log(
                            stage="generation",
                            endpoint=endpoint,
                            messages=messages,
                            result=result,
                            parsed=None,
                            error=None,
                            prompt_hash=prompt_hash,
                            record_ids={"card_id": card_id, "action_id": action_id},
                        ),
                    )
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    failures.append({
                        "card_id": card_id,
                        "action_id": action_id,
                        "error": error,
                    })
                    append_jsonl(
                        out_raw_calls_path,
                        request_log(
                            stage="generation",
                            endpoint=endpoint,
                            messages=messages,
                            result=result,
                            parsed=None,
                            error=error,
                            prompt_hash=prompt_hash,
                            record_ids={"card_id": card_id, "action_id": action_id},
                        ),
                    )
    finally:
        client.close()

    expected = len(expected_keys)
    completed = len(load_done_keys(out_outcomes_path, ("card_id", "action_id")) & expected_keys)
    summary = {
        "status": "COMPLETE" if completed >= expected and not failures else "INCOMPLETE",
        "n_cards": len(cards),
        "expected_outcomes": expected,
        "completed_outcomes": completed,
        "new_api_calls": n_calls,
        "failures": failures,
        "usage": total_usage,
        "endpoint_model": endpoint.model,
        "runtime_sha256": sha256_file(runtime_path),
        "backend_sha256": sha256_file(backend_path),
        "strategy_bank_sha256": sha256_file(strategy_bank_path),
    }
    write_json(out_summary_path, summary)
    if summary["status"] != "COMPLETE":
        raise RuntimeError(f"action sweep incomplete: {len(failures)} failures")
    create_artifact_attestation(
        Path(out_summary_path).parent / "artifact_attestation.json",
        stage="action_sweep",
        inputs={
            "runtime": runtime_path,
            "backend": backend_path,
            "strategy_bank": strategy_bank_path,
            "run_manifest": manifest_path,
        },
        outputs={
            "action_outcomes": (out_outcomes_path, True),
            "raw_calls": (out_raw_calls_path, True),
            "summary": (out_summary_path, False),
        },
        parameters={
            "endpoint_model": endpoint.model,
            "endpoint_family": endpoint.family,
            "endpoint_base_url": endpoint.base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "seed": seed,
            "strategy_top_k": strategy_top_k,
            "action_filter": sorted(action_filter) if action_filter else None,
            "max_cards": max_cards,
        },
        expected={
            "cards": len(cards),
            "outcomes": expected,
        },
        study_freeze_sha256=study_freeze_sha256,
    )
    return summary
