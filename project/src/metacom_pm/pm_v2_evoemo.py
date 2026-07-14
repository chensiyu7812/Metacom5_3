from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import time

from .api import Endpoint, OpenAICompatibleClient, request_log
from .artifacts import create_artifact_attestation, require_artifact_attestation
from .contracts import CostRecord, StrategyCard, StrategyMode, parse_action_id
from .evoemo import (
    NEUTRAL_INITIAL_GREETING,
    _fixed_context_before_turn,
    _load_fixed_tracks,
    _track_key,
    build_evo_memory,
    load_evoemo,
    make_evo_runtime_state,
)
from .io import (
    append_jsonl,
    canonical_json,
    ensure_run_manifest,
    iter_jsonl,
    load_done_keys,
    sha256_file,
    sha256_text,
    write_json,
)
from .pm_v2_data import runtime_to_pmv2_state
from .pm_v2_model import PMV2Model
from .prompts import OFFICIAL_ESMEM_SYSTEM, SELECTIVE_ESMEM_SYSTEM, generation_messages
from .retrieval import MemoryRetriever, StrategyRetriever, context_query
from .text import estimate_tokens, normalize_space


def run_pmv2_fixed_evoemo(
    evoemo_path: str | Path,
    strategy_bank_path: str | Path,
    checkpoint_path: str | Path,
    fixed_tracks_path: str | Path,
    out_dir: str | Path,
    *,
    generator_endpoint: Endpoint,
    simulator_id: str,
    fixed_tracks_attestation_path: str | Path | None = None,
    protocol: str = "selective",
    condition: str = "pm_v2",
    max_turns: int = 10,
    seeds: Sequence[int] = (101,),
    max_scenarios: int | None = None,
    overwrite: bool = False,
    strategy_action_tokens: int = 260,
    max_ood_fallback_rate: float = 0.25,
    study_freeze_sha256: str | None = None,
) -> dict[str, Any]:
    """Generate only the frozen PM-v2 condition on policy-independent tracks."""

    if protocol not in {"official", "selective"}:
        raise ValueError("protocol must be official or selective")
    if not (0.0 <= max_ood_fallback_rate <= 1.0):
        raise ValueError("max_ood_fallback_rate must be in [0, 1]")
    fixed_tracks_attestation_path = Path(
        fixed_tracks_attestation_path
        or Path(fixed_tracks_path).parent / "artifact_attestation.json"
    )
    fixed_verification = require_artifact_attestation(
        fixed_tracks_attestation_path,
        required_stage="evoemo_fixed_seeker_tracks",
        required_output_paths={"tracks": fixed_tracks_path},
    )
    users = load_evoemo(evoemo_path)
    strategy_cards = [
        StrategyCard.model_validate(row) for row in iter_jsonl(strategy_bank_path)
    ]
    if not strategy_cards:
        raise ValueError("strategy bank is empty")
    strategy_retriever = StrategyRetriever(strategy_cards, top_k=3)
    memory_retriever = MemoryRetriever()
    model = PMV2Model.load(checkpoint_path)
    tracks = _load_fixed_tracks(fixed_tracks_path)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dialogue_path = out_dir / "dialogues.jsonl"
    turn_path = out_dir / "turns.jsonl"
    raw_path = out_dir / "raw_api_calls.jsonl"
    summary_path = out_dir / "generation_summary.json"
    preflight_path = out_dir / "pm_v2_preflight.json"
    manifest_path = out_dir / "run_manifest.json"
    attestation_path = out_dir / "artifact_attestation.json"
    if overwrite:
        for path in (
            dialogue_path,
            turn_path,
            raw_path,
            summary_path,
            preflight_path,
            manifest_path,
            attestation_path,
        ):
            if path.exists():
                path.unlink()

    ensure_run_manifest(
        manifest_path,
        {
            "stage": "evoemo_pm_v2_generation",
            "evoemo_sha256": sha256_file(evoemo_path),
            "strategy_bank_sha256": sha256_file(strategy_bank_path),
            "checkpoint_sha256": sha256_file(checkpoint_path),
            "fixed_tracks_sha256": sha256_file(fixed_tracks_path),
            "fixed_tracks_attestation_sha256": fixed_verification["attestation_sha256"],
            "generator_model": generator_endpoint.model,
            "generator_family": generator_endpoint.family,
            "generator_base_url": generator_endpoint.base_url,
            "simulator_id": simulator_id,
            "protocol": protocol,
            "condition": condition,
            "max_turns": int(max_turns),
            "seeds": [int(seed) for seed in seeds],
            "max_scenarios": max_scenarios,
            "selection_config_hash": model.selection_config.digest(),
            "model_format_version": model.format_version,
            "strategy_action_tokens": int(strategy_action_tokens),
            "study_freeze_sha256": study_freeze_sha256,
        },
    )

    scenarios: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for user in users:
        for topic in user.get("subsequent_topics") or []:
            scenarios.append((user, topic))
    if max_scenarios is not None:
        scenarios = scenarios[:max_scenarios]

    preflight_rows: list[dict[str, Any]] = []
    for user, topic in scenarios:
        items, _ = build_evo_memory(user)
        for seed in seeds:
            key = _track_key(str(user["id"]), int(topic["idx"]), int(seed), simulator_id)
            track = tracks.get(key)
            if track is None:
                raise RuntimeError(f"missing fixed seeker track: {key}")
            if len(track.get("seeker_turns") or []) != max_turns:
                raise RuntimeError(f"fixed track turn count mismatch: {key}")
            for turn_index in range(1, max_turns + 1):
                seeker_message = normalize_space(track["seeker_turns"][turn_index - 1])
                state_context = _fixed_context_before_turn(track, turn_index)
                runtime = make_evo_runtime_state(
                    user,
                    topic,
                    state_context,
                    seeker_message,
                    items,
                    turn_index,
                    condition,
                    track_id=str(track["track_id"]),
                    fixed_open_loop=True,
                )
                pm_state = runtime_to_pmv2_state(
                    runtime,
                    strategy_catalog_count=len(strategy_cards),
                    strategy_estimated_tokens=strategy_action_tokens,
                )
                decision = model.choose(pm_state)
                preflight_rows.append(
                    {
                        "user_id": str(user["id"]),
                        "topic_index": int(topic["idx"]),
                        "seed": int(seed),
                        "turn_index": turn_index,
                        "chosen_action": decision.chosen_action,
                        "semantic_ood_score": decision.semantic_ood_score,
                        "metadata_ood_score": decision.metadata_ood_score,
                        "ood_fallback_used": decision.ood_fallback_used,
                    }
                )
    fallback_rate = (
        sum(bool(row["ood_fallback_used"]) for row in preflight_rows)
        / max(len(preflight_rows), 1)
    )
    preflight = {
        "status": "PASS" if fallback_rate <= max_ood_fallback_rate else "FAIL",
        "n_states": len(preflight_rows),
        "ood_fallback_rate": fallback_rate,
        "max_ood_fallback_rate": max_ood_fallback_rate,
        "action_distribution": dict(
            __import__("collections").Counter(row["chosen_action"] for row in preflight_rows)
        ),
        "examples": preflight_rows[:20],
    }
    write_json(preflight_path, preflight)
    if preflight["status"] != "PASS":
        raise RuntimeError(
            "PM-v2 external preflight failed before API calls: " + str(preflight)
        )

    done_fields = (
        "user_id",
        "topic_index",
        "condition",
        "seed",
        "simulator_id",
        "interaction_mode",
    )
    done = load_done_keys(dialogue_path, done_fields)
    generator = OpenAICompatibleClient(generator_endpoint)
    failures: list[dict[str, Any]] = []
    try:
        for user, topic in scenarios:
            items, _ = build_evo_memory(user)
            for seed in seeds:
                track_key = _track_key(
                    str(user["id"]), int(topic["idx"]), int(seed), simulator_id
                )
                fixed_track = tracks.get(track_key)
                if fixed_track is None:
                    raise RuntimeError(f"missing fixed seeker track: {track_key}")
                key = (
                    str(user["id"]),
                    int(topic["idx"]),
                    condition,
                    int(seed),
                    simulator_id,
                    "fixed",
                )
                if key in done:
                    continue
                conversation: list[dict[str, str]] = [
                    {"role": "supporter", "content": NEUTRAL_INITIAL_GREETING}
                ]
                turn_records: list[dict[str, Any]] = []
                evaluation_cases: list[dict[str, Any]] = []
                track_id = str(fixed_track["track_id"])
                try:
                    for turn_index in range(1, max_turns + 1):
                        seeker_message = normalize_space(
                            fixed_track["seeker_turns"][turn_index - 1]
                        )
                        state_conversation = _fixed_context_before_turn(
                            fixed_track, turn_index
                        )
                        state_start = time.perf_counter()
                        runtime = make_evo_runtime_state(
                            user,
                            topic,
                            state_conversation,
                            seeker_message,
                            items,
                            turn_index,
                            condition,
                            track_id=track_id,
                            fixed_open_loop=True,
                        )
                        pm_state = runtime_to_pmv2_state(
                            runtime,
                            strategy_catalog_count=len(strategy_cards),
                            strategy_estimated_tokens=strategy_action_tokens,
                        )
                        pre_evidence_ms = (time.perf_counter() - state_start) * 1000.0
                        query = context_query(
                            runtime.current_user_text,
                            [
                                row.model_dump(mode="json")
                                for row in runtime.current_session_history
                            ],
                            runtime.current_session_summary,
                        )
                        pm_start = time.perf_counter()
                        decision = model.choose(pm_state)
                        pm_ms = (time.perf_counter() - pm_start) * 1000.0
                        action_id = decision.chosen_action
                        sources, strategy = parse_action_id(action_id)
                        retrieval_start = time.perf_counter()
                        memory_view = memory_retriever.retrieve(query, items, sources)
                        strategy_view = (
                            strategy_retriever.retrieve(query)
                            if strategy is StrategyMode.RS
                            else []
                        )
                        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0
                        system = (
                            OFFICIAL_ESMEM_SYSTEM
                            if protocol == "official"
                            else SELECTIVE_ESMEM_SYSTEM
                        )
                        messages = generation_messages(
                            runtime, memory_view, strategy_view, system_prompt=system
                        )
                        result, _ = generator.chat(
                            messages,
                            temperature=0.0,
                            max_tokens=(60 if protocol == "official" else 100),
                            seed=int(seed) + turn_index,
                            response_schema=None,
                            retries=3,
                        )
                        append_jsonl(
                            raw_path,
                            request_log(
                                stage="evoemo_pm_v2_supporter",
                                endpoint=generator_endpoint,
                                messages=messages,
                                result=result,
                                parsed=None,
                                error=None,
                                prompt_hash=sha256_text(canonical_json(messages)),
                                record_ids={
                                    "user_id": str(user["id"]),
                                    "topic_index": int(topic["idx"]),
                                    "condition": condition,
                                    "seed": int(seed),
                                    "simulator_id": simulator_id,
                                    "turn_index": turn_index,
                                    "interaction_mode": "fixed",
                                    "track_id": track_id,
                                },
                            ),
                        )
                        supporter_message = normalize_space(result.text)
                        conversation.extend(
                            [
                                {"role": "seeker", "content": seeker_message},
                                {"role": "supporter", "content": supporter_message},
                            ]
                        )
                        evaluation_cases.append(
                            {
                                "turn_index": turn_index,
                                "context_before_turn": state_conversation,
                                "current_seeker_message": seeker_message,
                                "supporter_response": supporter_message,
                                "context_sha256": sha256_text(
                                    canonical_json(state_conversation)
                                ),
                            }
                        )
                        memory_tokens = sum(estimate_tokens(row.text) for row in memory_view)
                        strategy_tokens = sum(
                            estimate_tokens(row.guidance_text + row.example_response)
                            for row in strategy_view
                        )
                        base_tokens = estimate_tokens(
                            system
                            + runtime.current_user_text
                            + runtime.current_session_summary
                            + "\n".join(
                                row.content for row in runtime.current_session_history
                            )
                        )
                        cost = CostRecord(
                            pm_input_tokens_est=estimate_tokens(query)
                            + sum(len(cat.catalog_fingerprint) for cat in runtime.inventory.values()),
                            catalog_reads=len(runtime.inventory),
                            pre_evidence_compute_ms=pre_evidence_ms,
                            pm_inference_ms=pm_ms,
                            retrieval_latency_ms=retrieval_ms,
                            generation_latency_ms=result.latency_ms,
                            retrieval_calls=len(sources) + int(bool(strategy_view)),
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
                                or estimate_tokens(supporter_message)
                            ),
                            latency_ms=(
                                pre_evidence_ms + pm_ms + retrieval_ms + result.latency_ms
                            ),
                            api_cost_usd=None,
                        )
                        turn_record = {
                            "user_id": str(user["id"]),
                            "topic_index": int(topic["idx"]),
                            "condition": condition,
                            "protocol": protocol,
                            "interaction_mode": "fixed",
                            "trajectory_comparability": "causal_fixed_context_one_step",
                            "simulator_id": simulator_id,
                            "track_id": track_id,
                            "seed": int(seed),
                            "turn_index": turn_index,
                            "state_id": runtime.state_id,
                            "exogenous_state_id": runtime.provenance["exogenous_state_id"],
                            "card_id": runtime.card_id,
                            "context_before_turn": state_conversation,
                            "context_sha256": sha256_text(
                                canonical_json(state_conversation)
                            ),
                            "seeker_message": seeker_message,
                            "supporter_message": supporter_message,
                            "action_id": action_id,
                            "selected_memory": [
                                row.model_dump(mode="json") for row in memory_view
                            ],
                            "selected_strategy": [
                                row.model_dump(mode="json") for row in strategy_view
                            ],
                            "cost": cost.model_dump(mode="json"),
                            "input_tokens": cost.total_input_tokens,
                            "output_tokens": cost.output_tokens,
                            "latency_ms": cost.latency_ms,
                            "pm_v2_decision": decision.model_dump(mode="json"),
                        }
                        append_jsonl(turn_path, turn_record)
                        turn_records.append(turn_record)
                    append_jsonl(
                        dialogue_path,
                        {
                            "user_id": str(user["id"]),
                            "topic_index": int(topic["idx"]),
                            "condition": condition,
                            "protocol": protocol,
                            "interaction_mode": "fixed",
                            "trajectory_comparability": "causal_fixed_context_one_step",
                            "simulator_id": simulator_id,
                            "track_id": track_id,
                            "seed": int(seed),
                            "initial_greeting": NEUTRAL_INITIAL_GREETING,
                            "dialogue": conversation,
                            "dialogue_semantics": "display_only_stitched_open_loop_cases",
                            "evaluation_cases": evaluation_cases,
                            "turns": turn_records,
                        },
                    )
                except Exception as exc:
                    failures.append(
                        {
                            "user_id": str(user["id"]),
                            "topic_index": int(topic["idx"]),
                            "condition": condition,
                            "seed": int(seed),
                            "simulator_id": simulator_id,
                            "interaction_mode": "fixed",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
    finally:
        generator.close()

    expected = len(scenarios) * len(seeds)
    completed = len(load_done_keys(dialogue_path, done_fields))
    summary = {
        "status": "COMPLETE" if completed == expected and not failures else "INCOMPLETE",
        "condition": condition,
        "expected_dialogues": expected,
        "completed_dialogues": completed,
        "expected_turns": expected * max_turns,
        "completed_turns": sum(1 for _ in iter_jsonl(turn_path)),
        "failures": failures,
        "preflight": preflight,
    }
    write_json(summary_path, summary)
    if summary["status"] != "COMPLETE":
        raise RuntimeError("PM-v2 EvoEmo generation incomplete: " + str(summary))
    create_artifact_attestation(
        attestation_path,
        stage="evoemo_pm_v2_generation",
        inputs={
            "evoemo": evoemo_path,
            "strategy_bank": strategy_bank_path,
            "checkpoint": checkpoint_path,
            "fixed_tracks": fixed_tracks_path,
            "fixed_tracks_attestation": fixed_tracks_attestation_path,
            "run_manifest": manifest_path,
        },
        outputs={
            "dialogues": (dialogue_path, True),
            "turns": (turn_path, True),
            "raw_calls": (raw_path, True),
            "summary": (summary_path, False),
            "preflight": (preflight_path, False),
        },
        parameters={
            "condition": condition,
            "protocol": protocol,
            "max_turns": max_turns,
            "seeds": [int(seed) for seed in seeds],
            "selection_config_hash": model.selection_config.digest(),
        },
        expected={"dialogues": expected, "turns": expected * max_turns},
        study_freeze_sha256=study_freeze_sha256,
    )
    return summary
