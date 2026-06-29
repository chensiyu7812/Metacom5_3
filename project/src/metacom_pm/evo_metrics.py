from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .api import Endpoint, OpenAICompatibleClient
from .artifacts import create_artifact_attestation, require_artifact_attestation
from .contracts import (
    DialoguePairJudgment,
    MemoryItem,
    MemoryOmissionJudgment,
    MemoryUseJudgment,
    ObservationRelevance,
    ObservationUsage,
    OfficialDialogueScores,
    StrategyCard,
    StrategyOmissionJudgment,
    StrategyUseJudgment,
)
from .evoemo import build_evo_memory, evaluator_context, load_evoemo, make_evo_runtime_state
from .io import append_jsonl, iter_jsonl, load_done_keys, stable_hex, write_json
from .judging import _call_with_semantic_retry
from .prompts import (
    dialogue_pair_messages,
    fixed_context_pair_messages,
    fixed_context_score_messages,
    memory_omission_messages,
    memory_use_messages,
    observation_relevance_messages,
    observation_usage_messages,
    official_dialogue_score_messages,
    strategy_omission_messages,
    strategy_use_messages,
)
from .stats import hierarchical_bootstrap_ci, one_sample_cluster_signflip_test, paired_cluster_permutation_test


def _key_inventory(
    path: str | Path,
    fields: Sequence[str],
) -> tuple[set[tuple[Any, ...]], list[tuple[Any, ...]], int]:
    p = Path(path)
    if not p.exists():
        return set(), [], 0
    keys: set[tuple[Any, ...]] = set()
    duplicates: list[tuple[Any, ...]] = []
    rows = 0
    for row in iter_jsonl(p):
        rows += 1
        key = tuple(row.get(field) for field in fields)
        if key in keys:
            duplicates.append(key)
        keys.add(key)
    return keys, duplicates, rows


def _validate_exact_keys(
    path: str | Path,
    fields: Sequence[str],
    expected: set[tuple[Any, ...]],
    *,
    name: str,
    before_calls: bool,
) -> dict[str, Any]:
    actual, duplicates, rows = _key_inventory(path, fields)
    extras = actual - expected
    missing = expected - actual
    if duplicates or extras or (not before_calls and missing) or (
        not before_calls and rows != len(expected)
    ):
        raise RuntimeError(
            f"{name} output is incompatible with the immutable generation set: "
            f"duplicates={duplicates[:5]}, extras={sorted(extras)[:5]}, "
            f"missing={sorted(missing)[:5]}, rows={rows}, expected={len(expected)}. "
            "Use a fresh directory or --overwrite."
        )
    return {
        "name": name,
        "rows": rows,
        "unique": len(actual),
        "expected": len(expected),
        "missing": len(missing),
        "extra": len(extras),
        "duplicates": len(duplicates),
        "ok": not duplicates and not extras and not missing and rows == len(expected),
    }


def _topic_observations(user: dict[str, Any], topic: dict[str, Any]) -> list[dict[str, str]]:
    sessions = {str(row["id"]): row for row in user.get("dialog_history") or []}
    observations: list[dict[str, str]] = []
    for session_id in topic.get("related_sessions") or []:
        session = sessions.get(str(session_id))
        if not session:
            continue
        for observation in session.get("observation") or []:
            observations.append({
                "observation_id": f"{session_id}::{observation.get('idx')}",
                "content": observation.get("content") or "",
            })
    return observations


def _dialogue_key(row: dict[str, Any]) -> tuple[str, int, str, int, str, str]:
    return (
        str(row["user_id"]),
        int(row["topic_index"]),
        str(row["condition"]),
        int(row["seed"]),
        str(row.get("simulator_id") or "unspecified"),
        str(row.get("interaction_mode") or "legacy_interactive"),
    )


def _scenario_id(row: dict[str, Any]) -> str:
    return f"{row['user_id']}::{int(row['topic_index'])}::{row.get('simulator_id','unspecified')}::{row.get('interaction_mode','legacy')}"


def _ci(rows: Sequence[dict[str, Any]], value_key: str) -> dict[str, Any] | None:
    if not rows:
        return None
    enriched = [dict(row, scenario_id=_scenario_id(row)) for row in rows]
    try:
        return hierarchical_bootstrap_ci(
            enriched,
            user_key="user_id",
            scenario_key="scenario_id",
            value_key=value_key,
            n_resamples=5000,
        ).as_dict()
    except ValueError:
        return None


def observation_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Official observation metric with short-term disclosure deconfounding.

    Backward-compatible rows without the new attribution field are accepted for
    unit tests and legacy diagnostics, but confirmatory output always records it.
    """
    fully = [x for x in rows if float(x["relevance"]) == 1.0]
    denominator = sum(float(x["relevance"]) for x in rows)

    def effective(row: dict[str, Any]) -> bool:
        return bool(row.get("attributable_to_long_term_memory", row.get("used", False)))

    return {
        "observation_recall": (
            sum(effective(x) for x in fully) / len(fully) if fully else 0.0
        ),
        "weighted_observation_use": (
            sum(float(x["relevance"]) * float(effective(x)) for x in rows)
            / denominator if denominator else 0.0
        ),
        "raw_usage_rate": (
            sum(bool(x.get("used")) for x in rows) / len(rows) if rows else 0.0
        ),
        "current_session_disclosure_rate": (
            sum(bool(x.get("already_disclosed_in_current_session")) for x in rows)
            / len(rows) if rows else 0.0
        ),
    }


def _require_generation(
    dialogues_path: str | Path,
    generation_attestation_path: str | Path | None,
    expected_freeze_sha256: str | None,
) -> dict[str, Any] | None:
    if generation_attestation_path is None:
        if expected_freeze_sha256 is not None:
            raise RuntimeError(
                "confirmatory EvoEmo metrics require a generation attestation"
            )
        return None
    return require_artifact_attestation(
        generation_attestation_path,
        required_stage="evoemo_generation",
        required_output_paths={"dialogues": dialogues_path},
        expected_freeze_sha256=expected_freeze_sha256,
    )


def run_official_evoemo_metrics(
    evoemo_path: str | Path,
    dialogues_path: str | Path,
    out_dir: str | Path,
    *,
    judge_endpoint: Endpoint,
    generation_attestation_path: str | Path | None = None,
    expected_freeze_sha256: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    generation_verification = _require_generation(
        dialogues_path, generation_attestation_path, expected_freeze_sha256
    )
    users = {str(x["id"]): x for x in load_evoemo(evoemo_path)}
    dialogues = list(iter_jsonl(dialogues_path))
    dialogue_keys = [_dialogue_key(row) for row in dialogues]
    if len(dialogue_keys) != len(set(dialogue_keys)):
        raise ValueError("duplicate EvoEmo dialogue keys")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    score_path = out_dir / "official_dialogue_scores.jsonl"
    obs_path = out_dir / "official_observation_scores.jsonl"
    raw_path = out_dir / "raw_official_judge_calls.jsonl"
    summary_path = out_dir / "official_summary.json"
    attestation_path = out_dir / "artifact_attestation.json"
    if overwrite:
        for path in (score_path, obs_path, raw_path, summary_path, attestation_path):
            if path.exists():
                path.unlink()
    expected_score_keys = set(dialogue_keys)
    observation_key_fields = (
        "user_id", "topic_index", "condition", "seed", "simulator_id",
        "interaction_mode", "turn_index", "observation_id",
    )
    expected_observation_keys: set[tuple[Any, ...]] = set()
    for dialogue in dialogues:
        key = _dialogue_key(dialogue)
        user = users[key[0]]
        topic = next(
            x for x in user["subsequent_topics"] if int(x["idx"]) == key[1]
        )
        for turn in dialogue.get("turns") or []:
            for observation in _topic_observations(user, topic):
                expected_observation_keys.add((
                    key[0], key[1], key[2], key[3], key[4], key[5],
                    int(turn["turn_index"]), observation["observation_id"],
                ))
    _validate_exact_keys(
        score_path,
        ("user_id", "topic_index", "condition", "seed", "simulator_id", "interaction_mode"),
        expected_score_keys,
        name="official dialogue scores",
        before_calls=True,
    )
    _validate_exact_keys(
        obs_path,
        observation_key_fields,
        expected_observation_keys,
        name="official observation scores",
        before_calls=True,
    )
    done_score = load_done_keys(
        score_path,
        ("user_id", "topic_index", "condition", "seed", "simulator_id", "interaction_mode"),
    )
    done_obs = load_done_keys(
        obs_path,
        (
            "user_id", "topic_index", "condition", "seed", "simulator_id",
            "interaction_mode", "turn_index", "observation_id",
        ),
    )
    client = OpenAICompatibleClient(judge_endpoint)
    try:
        for dialogue in dialogues:
            key = _dialogue_key(dialogue)
            user = users[key[0]]
            topic = next(x for x in user["subsequent_topics"] if int(x["idx"]) == key[1])
            gt = evaluator_context(user, topic)
            if key not in done_score:
                score_messages = (
                    fixed_context_score_messages(dialogue["turns"], gt)
                    if key[5] == "fixed"
                    else official_dialogue_score_messages(dialogue["dialogue"], gt)
                )
                parsed = _call_with_semantic_retry(
                    client,
                    judge_endpoint,
                    score_messages,
                    OfficialDialogueScores,
                    None,
                    stage="evoemo_official_dialogue",
                    record_ids={
                        "user_id": key[0],
                        "topic_index": key[1],
                        "condition": key[2],
                        "seed": key[3],
                        "simulator_id": key[4],
                        "interaction_mode": key[5],
                    },
                    raw_log_path=raw_path,
                    max_tokens=700,
                )
                append_jsonl(score_path, {
                    "user_id": key[0],
                    "topic_index": key[1],
                    "condition": key[2],
                    "seed": key[3],
                    "simulator_id": key[4],
                    "interaction_mode": key[5],
                    "track_id": dialogue.get("track_id"),
                    **parsed.model_dump(mode="json"),
                })

            observations = _topic_observations(user, topic)

            # The initial greeting is part of the observable current session.
            current_history: list[dict[str, str]] = []
            full_dialogue = dialogue.get("dialogue") or []
            if full_dialogue and full_dialogue[0].get("role") == "supporter":
                current_history.append(dict(full_dialogue[0]))
            for turn in dialogue["turns"]:
                turn_history = (
                    list(turn.get("context_before_turn") or [])
                    if key[5] == "fixed" else list(current_history)
                )
                for observation in observations:
                    obs_key = (
                        key[0], key[1], key[2], key[3], key[4], key[5],
                        int(turn["turn_index"]), observation["observation_id"],
                    )
                    if obs_key in done_obs:
                        continue
                    rel = _call_with_semantic_retry(
                        client,
                        judge_endpoint,
                        observation_relevance_messages(
                            turn["seeker_message"],
                            observation["content"],
                            turn_history,
                        ),
                        ObservationRelevance,
                        None,
                        stage="evoemo_observation_relevance",
                        record_ids={
                            "user_id": key[0],
                            "topic_index": key[1],
                            "condition": key[2],
                            "seed": key[3],
                            "simulator_id": key[4],
                            "interaction_mode": key[5],
                            "turn_index": turn["turn_index"],
                            "observation_id": observation["observation_id"],
                        },
                        raw_log_path=raw_path,
                        max_tokens=120,
                    )
                    used = _call_with_semantic_retry(
                        client,
                        judge_endpoint,
                        observation_usage_messages(
                            turn["seeker_message"],
                            turn["supporter_message"],
                            observation["content"],
                            turn_history,
                        ),
                        ObservationUsage,
                        None,
                        stage="evoemo_observation_usage",
                        record_ids={
                            "user_id": key[0],
                            "topic_index": key[1],
                            "condition": key[2],
                            "seed": key[3],
                            "simulator_id": key[4],
                            "interaction_mode": key[5],
                            "turn_index": turn["turn_index"],
                            "observation_id": observation["observation_id"],
                        },
                        raw_log_path=raw_path,
                        max_tokens=150,
                    )
                    append_jsonl(obs_path, {
                        "user_id": key[0],
                        "topic_index": key[1],
                        "condition": key[2],
                        "seed": key[3],
                        "simulator_id": key[4],
                        "interaction_mode": key[5],
                        "track_id": dialogue.get("track_id"),
                        "turn_index": int(turn["turn_index"]),
                        "observation_id": observation["observation_id"],
                        "relevance": rel.relevance,
                        "used": used.used,
                        "already_disclosed_in_current_session": used.already_disclosed_in_current_session,
                        "attributable_to_long_term_memory": used.attributable_to_long_term_memory,
                    })
                if key[5] != "fixed":
                    current_history.extend([
                        {"role": "seeker", "content": turn["seeker_message"]},
                        {"role": "supporter", "content": turn["supporter_message"]},
                    ])
    finally:
        client.close()

    validations = {
        "dialogue_scores": _validate_exact_keys(
            score_path,
            ("user_id", "topic_index", "condition", "seed", "simulator_id", "interaction_mode"),
            expected_score_keys,
            name="official dialogue scores",
            before_calls=False,
        ),
        "observation_scores": _validate_exact_keys(
            obs_path,
            observation_key_fields,
            expected_observation_keys,
            name="official observation scores",
            before_calls=False,
        ),
    }
    scores = list(iter_jsonl(score_path))
    observations = list(iter_jsonl(obs_path))
    result: dict[str, Any] = {}
    for condition in sorted({x["condition"] for x in scores}):
        srows = [x for x in scores if x["condition"] == condition]
        orows = [x for x in observations if x["condition"] == condition]
        obs_metrics = observation_metrics(orows)
        condition_result: dict[str, Any] = {
            "n_dialogues": len(srows),
            "n_users": len({x["user_id"] for x in srows}),
            **obs_metrics,
        }
        for metric in (
            "memory", "personalization", "emotional_support",
            "factual_grounding", "temporal_consistency",
        ):
            condition_result[metric] = float(np.mean([x[metric] for x in srows]))
            condition_result[f"{metric}_user_hierarchical_ci"] = _ci(srows, metric)
        result[condition] = condition_result

    summary = {
        "conditions": result,
        "generation_attestation_verification": generation_verification,
        "judge_model": judge_endpoint.model,
        "judge_family": judge_endpoint.family,
        "validations": validations,
        "metric_note": (
            "Long-term observation use counts only observation content not already "
            "disclosed in the current session. Confidence intervals resample users "
            "and nested scenarios rather than treating turns as independent."
        ),
    }
    write_json(summary_path, summary)
    create_artifact_attestation(
        attestation_path,
        stage="evoemo_official_metrics",
        inputs={
            "evoemo": evoemo_path,
            "dialogues": dialogues_path,
            **({"generation_attestation": generation_attestation_path} if generation_attestation_path else {}),
        },
        outputs={
            "dialogue_scores": (score_path, True),
            "observation_scores": (obs_path, True),
            "raw_calls": (raw_path, True),
            "summary": (summary_path, False),
        },
        parameters={"judge_model": judge_endpoint.model, "judge_family": judge_endpoint.family},
        expected={
            "dialogues": len(dialogues),
            "observation_rows": len(expected_observation_keys),
        },
        study_freeze_sha256=expected_freeze_sha256,
    )
    return summary


def run_selective_evoemo_metrics(
    evoemo_path: str | Path,
    dialogues_path: str | Path,
    out_dir: str | Path,
    *,
    judge_endpoint: Endpoint,
    baselines: Sequence[str] = (
        "strong_rule", "best_fixed", "session_rag_rs", "full_history_rs",
    ),
    generation_attestation_path: str | Path | None = None,
    expected_freeze_sha256: str | None = None,
    evaluation_freeze_sha256: str | None = None,
    overwrite: bool = False,
    min_orientation_consistency: float = 0.80,
    pairs_only: bool = False,
) -> dict[str, Any]:
    generation_verification = _require_generation(
        dialogues_path, generation_attestation_path, expected_freeze_sha256
    )
    users = {str(x["id"]): x for x in load_evoemo(evoemo_path)}
    dialogues = list(iter_jsonl(dialogues_path))
    by_key = {_dialogue_key(x): x for x in dialogues}
    if len(by_key) != len(dialogues):
        raise ValueError("duplicate EvoEmo dialogue keys")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pair_path = out_dir / "selective_dialogue_pairs.jsonl"
    memory_path = out_dir / "selective_memory_audits.jsonl"
    strategy_path = out_dir / "selective_strategy_audits.jsonl"
    raw_path = out_dir / "raw_selective_judge_calls.jsonl"
    summary_path = out_dir / "selective_summary.json"
    attestation_path = out_dir / "artifact_attestation.json"
    if overwrite:
        for path in (pair_path, memory_path, strategy_path, raw_path, summary_path, attestation_path):
            if path.exists():
                path.unlink()

    pair_key_fields = (
        "user_id", "topic_index", "seed", "simulator_id",
        "interaction_mode", "comparison", "orientation",
    )
    audit_key_fields = (
        "user_id", "topic_index", "condition", "seed", "simulator_id",
        "interaction_mode", "turn_index",
    )
    expected_audit_keys = {
        (
            str(dialogue["user_id"]), int(dialogue["topic_index"]),
            str(dialogue["condition"]), int(dialogue["seed"]),
            str(dialogue.get("simulator_id") or "unspecified"),
            str(dialogue.get("interaction_mode") or "legacy_interactive"),
            int(turn["turn_index"]),
        )
        for dialogue in dialogues
        for turn in (dialogue.get("turns") or [])
    }
    expected_pair_keys: set[tuple[Any, ...]] = set()
    missing_baseline_dialogues: list[tuple[Any, ...]] = []
    for pm_key in sorted(key for key in by_key if key[2] == "pm"):
        user_id, topic_index, _, seed, simulator_id, interaction_mode = pm_key
        for baseline in baselines:
            base_key = (
                user_id, topic_index, baseline, seed, simulator_id,
                interaction_mode,
            )
            if base_key not in by_key:
                missing_baseline_dialogues.append(base_key)
                continue
            comparison = f"pm_vs_{baseline}"
            for orientation in ("AB", "BA"):
                expected_pair_keys.add((
                    user_id, topic_index, seed, simulator_id,
                    interaction_mode, comparison, orientation,
                ))
    if expected_freeze_sha256 is not None and missing_baseline_dialogues:
        raise RuntimeError(
            "confirmatory selective evaluation lacks frozen baseline dialogues: "
            + str(missing_baseline_dialogues[:10])
        )
    _validate_exact_keys(
        pair_path, pair_key_fields, expected_pair_keys,
        name="selective dialogue pairs", before_calls=True,
    )
    if not pairs_only:
        _validate_exact_keys(
            memory_path, audit_key_fields, expected_audit_keys,
            name="selective memory audits", before_calls=True,
        )
        _validate_exact_keys(
            strategy_path, audit_key_fields, expected_audit_keys,
            name="selective strategy audits", before_calls=True,
        )

    done_pair = load_done_keys(
        pair_path,
        pair_key_fields,
    )
    done_memory = load_done_keys(memory_path, audit_key_fields)
    done_strategy = load_done_keys(strategy_path, audit_key_fields)
    client = OpenAICompatibleClient(judge_endpoint)
    try:
        # Full-dialogue comparisons are evaluated in both A/B orientations.
        pm_keys = [key for key in by_key if key[2] == "pm"]
        for pm_key in sorted(pm_keys):
            user_id, topic_index, _, seed, simulator_id, interaction_mode = pm_key
            pm_dialogue = by_key[pm_key]
            user = users[user_id]
            topic = next(x for x in user["subsequent_topics"] if int(x["idx"]) == topic_index)
            gt = evaluator_context(user, topic)
            for baseline in baselines:
                base_key = (user_id, topic_index, baseline, seed, simulator_id, interaction_mode)
                if base_key not in by_key:
                    continue
                base_dialogue = by_key[base_key]
                same_track = pm_dialogue.get("track_id") == base_dialogue.get("track_id")
                pm_turns = pm_dialogue.get("turns") or []
                base_turns = base_dialogue.get("turns") or []
                same_fixed_contexts = (
                    len(pm_turns) == len(base_turns)
                    and all(
                        int(left.get("turn_index")) == int(right.get("turn_index"))
                        and left.get("context_sha256") == right.get("context_sha256")
                        and left.get("seeker_message") == right.get("seeker_message")
                        and left.get("state_id") == right.get("state_id")
                        for left, right in zip(pm_turns, base_turns)
                    )
                )
                causal_eligible = (
                    interaction_mode == "fixed"
                    and same_track
                    and same_fixed_contexts
                )
                if interaction_mode == "fixed" and not causal_eligible:
                    raise RuntimeError(
                        f"fixed-context inputs differ for pm vs {baseline}: "
                        f"user={user_id}, topic={topic_index}, seed={seed}, "
                        f"simulator={simulator_id}"
                    )
                comparison = f"pm_vs_{baseline}"
                pair_unit_id = f"pair_{stable_hex(user_id, topic_index, seed, simulator_id, interaction_mode, comparison, n=20)}"
                for orientation in ("AB", "BA"):
                    done_key = (
                        user_id, topic_index, seed, simulator_id,
                        interaction_mode, comparison, orientation,
                    )
                    if done_key in done_pair:
                        continue
                    if orientation == "AB":
                        a_name, a_source = "pm", pm_dialogue
                        b_name, b_source = baseline, base_dialogue
                    else:
                        a_name, a_source = baseline, base_dialogue
                        b_name, b_source = "pm", pm_dialogue
                    if interaction_mode == "fixed":
                        pair_messages = fixed_context_pair_messages(
                            a_source["turns"], b_source["turns"], gt
                        )
                        a_dialogue = [
                            {
                                "turn_index": turn["turn_index"],
                                "context_before_turn": turn["context_before_turn"],
                                "current_seeker_message": turn["seeker_message"],
                                "supporter_response": turn["supporter_message"],
                            }
                            for turn in a_source["turns"]
                        ]
                        b_dialogue = [
                            {
                                "turn_index": turn["turn_index"],
                                "context_before_turn": turn["context_before_turn"],
                                "current_seeker_message": turn["seeker_message"],
                                "supporter_response": turn["supporter_message"],
                            }
                            for turn in b_source["turns"]
                        ]
                        candidate_semantics = "independent_fixed_context_bundle"
                    else:
                        a_dialogue = a_source["dialogue"]
                        b_dialogue = b_source["dialogue"]
                        pair_messages = dialogue_pair_messages(
                            a_dialogue, b_dialogue, gt
                        )
                        candidate_semantics = "interactive_full_dialogue"
                    parsed = _call_with_semantic_retry(
                        client,
                        judge_endpoint,
                        pair_messages,
                        DialoguePairJudgment,
                        None,
                        stage="evoemo_selective_dialogue_pair",
                        record_ids={
                            "user_id": user_id,
                            "topic_index": topic_index,
                            "seed": seed,
                            "simulator_id": simulator_id,
                            "interaction_mode": interaction_mode,
                            "comparison": comparison,
                            "orientation": orientation,
                        },
                        raw_log_path=raw_path,
                        max_tokens=900,
                    )
                    winner = (
                        a_name if parsed.preference == "A"
                        else b_name if parsed.preference == "B"
                        else "tie"
                    )
                    append_jsonl(pair_path, {
                        "pair_unit_id": pair_unit_id,
                        "user_id": user_id,
                        "topic_index": topic_index,
                        "seed": seed,
                        "simulator_id": simulator_id,
                        "interaction_mode": interaction_mode,
                        "track_id": pm_dialogue.get("track_id"),
                        "same_track": same_track,
                        "same_fixed_contexts": same_fixed_contexts,
                        "causal_eligible": causal_eligible,
                        "candidate_semantics": candidate_semantics,
                        "comparison": comparison,
                        "orientation": orientation,
                        "policy_a": a_name,
                        "policy_b": b_name,
                        "system_a": a_name,
                        "system_b": b_name,
                        "context": gt,
                        "dialogue_a": a_dialogue,
                        "dialogue_b": b_dialogue,
                        "winner_policy": winner,
                        "pm_score": 1.0 if winner == "pm" else 0.5 if winner == "tie" else 0.0,
                        **parsed.model_dump(mode="json"),
                    })

        # Per-turn memory and strategy audits use full evaluator-only memory
        # timelines, while keeping policy/action labels hidden from the judge.
        if not pairs_only:
            for dialogue in dialogues:
                user_id, topic_index, condition, seed, simulator_id, interaction_mode = _dialogue_key(dialogue)
                user = users[user_id]
                topic = next(x for x in user["subsequent_topics"] if int(x["idx"]) == topic_index)
                all_items, _ = build_evo_memory(user)
                conversation: list[dict[str, str]] = []
                full_dialogue = dialogue.get("dialogue") or []
                if full_dialogue and full_dialogue[0].get("role") == "supporter":
                    conversation.append(dict(full_dialogue[0]))
                for turn in dialogue["turns"]:
                    key = (
                        user_id, topic_index, condition, seed, simulator_id,
                        interaction_mode, int(turn["turn_index"]),
                    )
                    audit_context = (
                        list(turn.get("context_before_turn") or [])
                        if interaction_mode == "fixed" else list(conversation)
                    )
                    state = make_evo_runtime_state(
                        user,
                        topic,
                        audit_context,
                        turn["seeker_message"],
                        all_items,
                        int(turn["turn_index"]),
                        condition,
                        track_id=dialogue.get("track_id"),
                        fixed_open_loop=interaction_mode == "fixed",
                    )
                    if key not in done_memory:
                        selected = [MemoryItem.model_validate(x) for x in turn.get("selected_memory") or []]
                        if selected:
                            parsed_m = _call_with_semantic_retry(
                                client,
                                judge_endpoint,
                                memory_use_messages(
                                    state,
                                    selected,
                                    turn["supporter_message"],
                                    all_items=all_items,
                                ),
                                MemoryUseJudgment,
                                None,
                                stage="evoemo_selective_memory_use",
                                record_ids={
                                    "user_id": user_id,
                                    "topic_index": topic_index,
                                    "condition": condition,
                                    "seed": seed,
                                    "simulator_id": simulator_id,
                                    "interaction_mode": interaction_mode,
                                    "turn_index": turn["turn_index"],
                                },
                                raw_log_path=raw_path,
                                max_tokens=1000,
                            )
                            assessments = parsed_m.source_assessments
                            misuse = max([
                                max(
                                    x.unnecessary_exposure,
                                    x.stale_or_conflicting_use,
                                    x.unsupported_personal_claim,
                                ) / 2.0
                                for x in assessments
                            ], default=0.0)
                            # MemoryUseJudgment does not have missed_memory_opportunity_severity.
                            # For M2 actions (memory was used), omission_risk is derived from
                            # overall_source_set_appropriateness: low appropriateness signals
                            # that a sub-optimal or incomplete source set was selected.
                            m2_appropriateness = parsed_m.overall_source_set_appropriateness
                            m2_omission = max(0.0, (2 - m2_appropriateness) / 2.0)
                            memory_row = {
                                "audit_type": "memory_use",
                                **parsed_m.model_dump(mode="json"),
                                "misuse_risk": misuse,
                                "omission_risk": m2_omission,
                            }
                        else:
                            parsed_m0 = _call_with_semantic_retry(
                                client,
                                judge_endpoint,
                                memory_omission_messages(state, all_items, turn["supporter_message"]),
                                MemoryOmissionJudgment,
                                None,
                                stage="evoemo_selective_memory_omission",
                                record_ids={
                                    "user_id": user_id,
                                    "topic_index": topic_index,
                                    "condition": condition,
                                    "seed": seed,
                                    "simulator_id": simulator_id,
                                    "interaction_mode": interaction_mode,
                                    "turn_index": turn["turn_index"],
                                },
                                raw_log_path=raw_path,
                                max_tokens=900,
                            )
                            memory_row = {
                                "audit_type": "memory_omission",
                                **parsed_m0.model_dump(mode="json"),
                                "misuse_risk": parsed_m0.unsupported_personal_claim / 2.0,
                                "omission_risk": parsed_m0.missed_memory_opportunity_severity / 2.0,
                            }
                        append_jsonl(memory_path, {
                            "user_id": user_id,
                            "topic_index": topic_index,
                            "condition": condition,
                            "seed": seed,
                            "simulator_id": simulator_id,
                            "interaction_mode": interaction_mode,
                            "track_id": dialogue.get("track_id"),
                            "turn_index": int(turn["turn_index"]),
                            **memory_row,
                        })

                    if key not in done_strategy:
                        selected_strategy = [
                            StrategyCard.model_validate(x)
                            for x in turn.get("selected_strategy") or []
                        ]
                        if selected_strategy:
                            parsed_s = _call_with_semantic_retry(
                                client,
                                judge_endpoint,
                                strategy_use_messages(state, selected_strategy, turn["supporter_message"]),
                                StrategyUseJudgment,
                                None,
                                stage="evoemo_selective_strategy_use",
                                record_ids={
                                    "user_id": user_id,
                                    "topic_index": topic_index,
                                    "condition": condition,
                                    "seed": seed,
                                    "simulator_id": simulator_id,
                                    "interaction_mode": interaction_mode,
                                    "turn_index": turn["turn_index"],
                                },
                                raw_log_path=raw_path,
                                max_tokens=700,
                            )
                            strategy_row = {
                                "audit_type": "strategy_use",
                                **parsed_s.model_dump(mode="json"),
                                "strategy_risk": max(parsed_s.over_structuring, parsed_s.premature_advice) / 2.0,
                            }
                        else:
                            parsed_s0 = _call_with_semantic_retry(
                                client,
                                judge_endpoint,
                                strategy_omission_messages(state, turn["supporter_message"]),
                                StrategyOmissionJudgment,
                                None,
                                stage="evoemo_selective_strategy_omission",
                                record_ids={
                                    "user_id": user_id,
                                    "topic_index": topic_index,
                                    "condition": condition,
                                    "seed": seed,
                                    "simulator_id": simulator_id,
                                    "interaction_mode": interaction_mode,
                                    "turn_index": turn["turn_index"],
                                },
                                raw_log_path=raw_path,
                                max_tokens=500,
                            )
                            strategy_row = {
                                "audit_type": "strategy_omission",
                                **parsed_s0.model_dump(mode="json"),
                                "strategy_risk": parsed_s0.missed_strategy_opportunity_severity / 2.0,
                            }
                        append_jsonl(strategy_path, {
                            "user_id": user_id,
                            "topic_index": topic_index,
                            "condition": condition,
                            "seed": seed,
                            "simulator_id": simulator_id,
                            "interaction_mode": interaction_mode,
                            "track_id": dialogue.get("track_id"),
                            "turn_index": int(turn["turn_index"]),
                            **strategy_row,
                        })
                    if interaction_mode != "fixed":
                        conversation.extend([
                            {"role": "seeker", "content": turn["seeker_message"]},
                            {"role": "supporter", "content": turn["supporter_message"]},
                        ])
    finally:
        client.close()

    validations = {
        "dialogue_pairs": _validate_exact_keys(
            pair_path, pair_key_fields, expected_pair_keys,
            name="selective dialogue pairs", before_calls=False,
        )
    }
    if not pairs_only:
        validations.update({
            "memory_audits": _validate_exact_keys(
                memory_path, audit_key_fields, expected_audit_keys,
                name="selective memory audits", before_calls=False,
            ),
            "strategy_audits": _validate_exact_keys(
                strategy_path, audit_key_fields, expected_audit_keys,
                name="selective strategy audits", before_calls=False,
            ),
        })
    pair_rows = list(iter_jsonl(pair_path))
    memory_rows = [] if pairs_only else list(iter_jsonl(memory_path))
    strategy_rows = [] if pairs_only else list(iter_jsonl(strategy_path))

    # Collapse the two orientations before inference.
    pair_units: list[dict[str, Any]] = []
    grouped_pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pair_rows:
        grouped_pairs[row["pair_unit_id"]].append(row)
    for unit_id, rows in sorted(grouped_pairs.items()):
        if len(rows) != 2 or {x["orientation"] for x in rows} != {"AB", "BA"}:
            continue
        winners = [x["winner_policy"] for x in rows]
        representative = rows[0]
        pair_units.append({
            "pair_unit_id": unit_id,
            "user_id": representative["user_id"],
            "topic_index": representative["topic_index"],
            "seed": representative["seed"],
            "simulator_id": representative["simulator_id"],
            "interaction_mode": representative["interaction_mode"],
            "comparison": representative["comparison"],
            "causal_eligible": bool(representative["causal_eligible"]),
            "orientation_consistent": winners[0] == winners[1],
            "pm_score": float(np.mean([x["pm_score"] for x in rows])),
        })

    pair_summary: dict[str, Any] = {}
    for comparison in sorted({x["comparison"] for x in pair_units}):
        all_units = [x for x in pair_units if x["comparison"] == comparison]
        causal_units = [x for x in all_units if x["causal_eligible"]]
        primary = causal_units
        if primary:
            pref_scores = [x["pm_score"] for x in primary]
            inferential = {
                "user_hierarchical_ci": _ci(primary, "pm_score"),
                "user_cluster_permutation_vs_tie": one_sample_cluster_signflip_test(
                    primary,
                    cluster_key="user_id",
                    value_key="pm_score",
                    null_value=0.5,
                ),
            }
        else:
            pref_scores = []
            inferential = {
                "user_hierarchical_ci": None,
                "user_cluster_permutation_vs_tie": None,
            }
        pair_summary[comparison] = {
            "n_orientation_calls": sum(2 for _ in all_units),
            "n_pair_units": len(all_units),
            "n_causal_fixed_input_units": len(causal_units),
            "n_associational_interactive_units": len(all_units) - len(causal_units),
            "orientation_consistency": (
                sum(x["orientation_consistent"] for x in all_units) / len(all_units)
                if all_units else None
            ),
            "primary_fixed_input_preference_score": (
                float(np.mean(pref_scores)) if pref_scores else None
            ),
            "associational_interactive_preference_score": (
                float(np.mean([x["pm_score"] for x in all_units if not x["causal_eligible"]]))
                if any(not x["causal_eligible"] for x in all_units) else None
            ),
            **inferential,
        }

    fixed_modes_present = any(
        str(dialogue.get("interaction_mode")) == "fixed" for dialogue in dialogues
    )
    if expected_freeze_sha256 is not None and fixed_modes_present:
        failures = []
        expected_comparisons = {f"pm_vs_{baseline}" for baseline in baselines}
        for comparison in sorted(expected_comparisons):
            value = pair_summary.get(comparison)
            if value is None:
                failures.append(f"missing comparison {comparison}")
                continue
            if int(value["n_causal_fixed_input_units"]) <= 0:
                failures.append(f"{comparison} has no fixed-input causal units")
            consistency = value.get("orientation_consistency")
            if consistency is None or float(consistency) < min_orientation_consistency:
                failures.append(
                    f"{comparison} orientation consistency {consistency} < "
                    f"{min_orientation_consistency}"
                )
        if failures:
            raise RuntimeError(
                "confirmatory dialogue-pair judge gate failed:\n- "
                + "\n- ".join(failures)
            )

    condition_summary: dict[str, Any] = {}
    dialogue_cost_rows: list[dict[str, Any]] = []
    for dialogue in dialogues:
        total_cost = sum(float(turn.get("cost", {}).get("total_input_tokens", turn.get("input_tokens", 0))) for turn in dialogue["turns"])
        total_latency = sum(float(turn.get("cost", {}).get("latency_ms", turn.get("latency_ms", 0))) for turn in dialogue["turns"])
        dialogue_cost_rows.append({
            "user_id": dialogue["user_id"],
            "topic_index": dialogue["topic_index"],
            "condition": dialogue["condition"],
            "simulator_id": dialogue.get("simulator_id", "unspecified"),
            "interaction_mode": dialogue.get("interaction_mode", "legacy"),
            "total_input_tokens": total_cost,
            "total_latency_ms": total_latency,
        })
    conditions = sorted(
        {x["condition"] for x in memory_rows + strategy_rows}
        or {x["condition"] for x in dialogue_cost_rows}
    )
    for condition in conditions:
        mrows = [x for x in memory_rows if x["condition"] == condition]
        srows = [x for x in strategy_rows if x["condition"] == condition]
        crows = [x for x in dialogue_cost_rows if x["condition"] == condition]
        condition_summary[condition] = {
            "n_turns": len(mrows),
            "n_users": len({x["user_id"] for x in mrows}),
            "mean_misuse_risk": float(np.mean([x["misuse_risk"] for x in mrows])) if mrows else None,
            "mean_memory_omission_risk": float(np.mean([x["omission_risk"] for x in mrows])) if mrows else None,
            "mean_strategy_decision_risk": float(np.mean([x["strategy_risk"] for x in srows])) if srows else None,
            "mean_dialogue_input_tokens": float(np.mean([x["total_input_tokens"] for x in crows])) if crows else None,
            "mean_dialogue_latency_ms": float(np.mean([x["total_latency_ms"] for x in crows])) if crows else None,
            "misuse_user_hierarchical_ci": _ci(mrows, "misuse_risk"),
            "memory_omission_user_hierarchical_ci": _ci(mrows, "omission_risk"),
            "strategy_risk_user_hierarchical_ci": _ci(srows, "strategy_risk"),
            "input_tokens_user_hierarchical_ci": _ci(crows, "total_input_tokens"),
        }

    result = {
        "dialogue_pairwise": pair_summary,
        "resource_audits": condition_summary,
        "generation_attestation_verification": generation_verification,
        "judge_model": judge_endpoint.model,
        "judge_family": judge_endpoint.family,
        "generation_freeze_sha256": expected_freeze_sha256,
        "evaluation_freeze_sha256": evaluation_freeze_sha256,
        "pairs_only": pairs_only,
        "validations": validations,
        "minimum_orientation_consistency": min_orientation_consistency,
        "causal_note": (
            "Only same-track comparisons on identical full fixed contexts are "
            "primary one-step causal evidence. Evaluated replies are not fed "
            "forward. Interactive trajectories are secondary associational evidence."
        ),
    }
    write_json(summary_path, result)
    metric_outputs: dict[str, Any] = {
        "dialogue_pairs": (pair_path, True),
        "raw_calls": (raw_path, True),
        "summary": (summary_path, False),
    }
    if not pairs_only:
        metric_outputs.update({
            "memory_audits": (memory_path, True),
            "strategy_audits": (strategy_path, True),
        })
    create_artifact_attestation(
        attestation_path,
        stage="evoemo_selective_metrics",
        inputs={
            "evoemo": evoemo_path,
            "dialogues": dialogues_path,
            **({"generation_attestation": generation_attestation_path} if generation_attestation_path else {}),
        },
        outputs=metric_outputs,
        parameters={
            "judge_model": judge_endpoint.model,
            "judge_family": judge_endpoint.family,
            "baselines": list(baselines),
            "two_orientation_calls": True,
            "minimum_orientation_consistency": min_orientation_consistency,
            "pairs_only": pairs_only,
            "generation_freeze_sha256": expected_freeze_sha256,
            "evaluation_freeze_sha256": evaluation_freeze_sha256,
        },
        expected={
            "dialogues": len(dialogues),
            "dialogue_pair_rows": len(expected_pair_keys),
            "audit_rows_each": 0 if pairs_only else len(expected_audit_keys),
        },
        study_freeze_sha256=evaluation_freeze_sha256 or expected_freeze_sha256,
    )
    return result
