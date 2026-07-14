from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Sequence

import numpy as np

from .api import Endpoint, make_client, request_log
from .evoemo import evaluator_context, load_evoemo
from .io import (
    append_jsonl,
    canonical_json,
    iter_jsonl,
    load_done_keys,
    sha256_text,
    write_json,
)
from .pm_v2_contracts import CompositeSpec, ResponseDimensions
from .pm_v2_judging import ResponseJudgeOutput, build_response_messages


DIMENSIONS = tuple(ResponseDimensions.model_fields)


def _unit_key(row: dict[str, Any]) -> tuple[str, int, int, str, int]:
    return (
        str(row["user_id"]),
        int(row["topic_index"]),
        int(row["seed"]),
        str(row["simulator_id"]),
        int(row["turn_index"]),
    )


def load_fixed_turns(
    paths: Sequence[str | Path],
    *,
    conditions: Sequence[str],
    turn_indices: Sequence[int],
) -> dict[tuple[str, int, int, str, int, str], dict[str, Any]]:
    requested = set(conditions)
    turns = set(int(value) for value in turn_indices)
    rows: dict[tuple[str, int, int, str, int, str], dict[str, Any]] = {}
    for path in paths:
        for row in iter_jsonl(path):
            condition = str(row.get("condition"))
            if condition not in requested or int(row.get("turn_index", -1)) not in turns:
                continue
            if row.get("interaction_mode") != "fixed":
                raise ValueError("PM-v2 external evaluation requires fixed-input turns")
            key = (*_unit_key(row), condition)
            if key in rows:
                raise ValueError(f"duplicate external turn key: {key}")
            rows[key] = row
    expected_units = sorted({key[:-1] for key in rows})
    missing = [
        (*unit, condition)
        for unit in expected_units
        for condition in requested
        if (*unit, condition) not in rows
    ]
    if missing:
        raise RuntimeError(f"external turn matrix is incomplete: {missing[:10]}")
    for unit in expected_units:
        unit_rows = [rows[(*unit, condition)] for condition in requested]
        context_hashes = {str(row.get("context_sha256")) for row in unit_rows}
        seeker_messages = {str(row.get("seeker_message")) for row in unit_rows}
        if len(context_hashes) != 1 or len(seeker_messages) != 1:
            raise RuntimeError(
                f"fixed-input mismatch for unit {unit}: "
                f"context_hashes={context_hashes}, seeker_messages={seeker_messages}"
            )
    return rows


def _authorized_context_map(evoemo_path: str | Path) -> dict[tuple[str, int], str]:
    mapping: dict[tuple[str, int], str] = {}
    for user in load_evoemo(evoemo_path):
        for topic in user.get("subsequent_topics") or []:
            key = (str(user["id"]), int(topic["idx"]))
            mapping[key] = canonical_json(evaluator_context(user, topic))
    return mapping


def _median_response(outputs: Sequence[ResponseJudgeOutput]) -> ResponseDimensions:
    return ResponseDimensions(
        **{
            name: float(median(float(getattr(output, name)) for output in outputs))
            for name in DIMENSIONS
        }
    )


def _mad_response(outputs: Sequence[ResponseJudgeOutput]) -> dict[str, float]:
    result: dict[str, float] = {}
    for name in DIMENSIONS:
        values = np.asarray([float(getattr(output, name)) for output in outputs])
        result[name] = float(np.median(np.abs(values - np.median(values))))
    return result


def _bootstrap_cluster_delta(
    rows: Sequence[dict[str, Any]],
    *,
    cluster_field: str,
    n_resamples: int = 10000,
    seed: int = 17,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot bootstrap empty paired rows")
    clusters: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        clusters[str(row[cluster_field])].append(float(row["delta"]))
    cluster_ids = sorted(clusters)
    rng = np.random.default_rng(seed)
    samples = np.empty(n_resamples, dtype=float)
    for index in range(n_resamples):
        sampled = rng.choice(cluster_ids, size=len(cluster_ids), replace=True)
        values = [value for cluster in sampled for value in clusters[str(cluster)]]
        samples[index] = float(np.mean(values))
    estimate = float(np.mean([row["delta"] for row in rows]))
    return {
        "estimate": estimate,
        "lower": float(np.quantile(samples, 0.025)),
        "upper": float(np.quantile(samples, 0.975)),
        "p_delta_lt_0": float(np.mean(samples < 0.0)),
        "n_clusters": len(cluster_ids),
        "n_resamples": n_resamples,
    }


def validate_external_score_table(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("empty external score table")
    matrix = np.asarray([[float(row[name]) for name in DIMENSIONS] for row in rows])
    duplicate_pairs: list[dict[str, Any]] = []
    for left in range(len(DIMENSIONS)):
        for right in range(left + 1, len(DIMENSIONS)):
            rate = float(np.mean(matrix[:, left] == matrix[:, right]))
            if rate >= 0.98:
                duplicate_pairs.append(
                    {
                        "left": DIMENSIONS[left],
                        "right": DIMENSIONS[right],
                        "exact_match_rate": rate,
                    }
                )
    constants = [
        DIMENSIONS[index]
        for index in range(len(DIMENSIONS))
        if float(np.std(matrix[:, index])) < 1e-9
    ]
    reliable_rate = float(np.mean([bool(row["label_reliable"]) for row in rows]))
    report = {
        "n": len(rows),
        "duplicate_dimension_pairs": duplicate_pairs,
        "constant_dimensions": constants,
        "reliable_rate": reliable_rate,
        "status": "PASS",
    }
    if duplicate_pairs or constants or reliable_rate < 0.80:
        report["status"] = "FAIL"
        raise RuntimeError("PM-v2 external judge gate failed: " + canonical_json(report))
    return report


def run_external_response_evaluation(
    *,
    evoemo_path: str | Path,
    turn_paths: Sequence[str | Path],
    conditions: Sequence[str],
    treatment: str,
    turn_indices: Sequence[int],
    endpoints: Sequence[Endpoint],
    out_dir: str | Path,
    run: bool,
    max_api_calls: int,
    seed: int = 3701,
    reliable_mad_threshold: float = 0.75,
) -> dict[str, Any]:
    if treatment not in conditions:
        raise ValueError("treatment must be included in conditions")
    families = {endpoint.family for endpoint in endpoints}
    if None in families or len(families) < 2:
        raise ValueError("external evaluation requires two independent judge families")
    matrix = load_fixed_turns(
        turn_paths, conditions=conditions, turn_indices=turn_indices
    )
    units = sorted({key[:-1] for key in matrix})
    expected_calls = len(units) * len(conditions) * len(endpoints)
    dry = {
        "status": "DRY_RUN" if not run else "STARTING",
        "n_units": len(units),
        "conditions": list(conditions),
        "treatment": treatment,
        "judge_families": sorted(str(value) for value in families),
        "expected_api_calls": expected_calls,
        "single_candidate_pointwise": True,
        "llm_overall_requested": False,
    }
    if expected_calls > max_api_calls:
        raise RuntimeError(
            f"budget gate failed: expected {expected_calls} > max {max_api_calls}"
        )
    if not run:
        return dry

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "raw_judge_calls.jsonl"
    score_path = out_dir / "response_scores.jsonl"
    raw_done = load_done_keys(raw_path, ("unit_id", "condition", "judge_family"))
    authorized = _authorized_context_map(evoemo_path)
    clients = {endpoint.family: make_client(endpoint) for endpoint in endpoints}
    try:
        for unit_index, unit in enumerate(units):
            user_id, topic_index, unit_seed, simulator_id, turn_index = unit
            unit_id = sha256_text(canonical_json(unit))[:24]
            context = authorized[(user_id, topic_index)]
            for condition in conditions:
                row = matrix[(*unit, condition)]
                from .pm_v2_data import runtime_to_pmv2_state
                from .contracts import RuntimeState

                runtime = RuntimeState(
                    state_id=str(row["state_id"]),
                    card_id=str(row["card_id"]),
                    user_id=user_id,
                    split="evoemo_test",
                    semantic_family="evoemo_dialogue_generation",
                    current_user_text=str(row["seeker_message"]),
                    current_session_history=[
                        {
                            "role": "user" if turn["role"] == "seeker" else "assistant",
                            "content": turn["content"],
                        }
                        for turn in row["context_before_turn"][-8:]
                    ],
                    current_session_summary="",
                    session_index=1,
                    inventory={
                        "MP": {"available": False, "count": 0, "estimated_tokens": 0},
                        "MS": {"available": False, "count": 0, "estimated_tokens": 0},
                        "ME": {"available": False, "count": 0, "estimated_tokens": 0},
                    },
                    allowed_actions=["M0+R0", "M0+RS"],
                )
                state = runtime_to_pmv2_state(runtime)
                messages = build_response_messages(
                    state=state,
                    authorized_user_context=context,
                    candidate_response=str(row["supporter_message"]),
                )
                for family_index, endpoint in enumerate(endpoints):
                    key = (unit_id, condition, str(endpoint.family))
                    if key in raw_done:
                        continue
                    client = clients[endpoint.family]
                    result, parsed = client.chat(
                        messages,
                        temperature=0.0,
                        max_tokens=600,
                        seed=seed + unit_index * 100 + family_index,
                        response_schema=ResponseJudgeOutput,
                    )
                    assert parsed is not None
                    append_jsonl(
                        raw_path,
                        {
                            "unit_id": unit_id,
                            "user_id": user_id,
                            "topic_index": topic_index,
                            "seed": unit_seed,
                            "simulator_id": simulator_id,
                            "turn_index": turn_index,
                            "condition": condition,
                            "judge_family": endpoint.family,
                            "judge_model": endpoint.model,
                            "scores": parsed.model_dump(mode="json"),
                            "request_log": request_log(
                                stage="pm_v2_external_response_judge",
                                endpoint=endpoint,
                                messages=messages,
                                result=result,
                                parsed=parsed,
                                error=None,
                                prompt_hash=sha256_text(canonical_json(messages)),
                                record_ids={
                                    "unit_id": unit_id,
                                    "condition": condition,
                                },
                            ),
                        },
                    )
    finally:
        for client in clients.values():
            client.close()

    grouped: dict[tuple[str, str], list[ResponseJudgeOutput]] = defaultdict(list)
    metadata: dict[tuple[str, str], dict[str, Any]] = {}
    families_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in iter_jsonl(raw_path):
        key = (str(row["unit_id"]), str(row["condition"]))
        grouped[key].append(ResponseJudgeOutput.model_validate(row["scores"]))
        metadata[key] = row
        families_by_key[key].add(str(row["judge_family"]))
    score_path.write_text("", encoding="utf-8")
    score_rows: list[dict[str, Any]] = []
    composite = CompositeSpec()
    for key in sorted(grouped):
        outputs = grouped[key]
        output_families = families_by_key[key]
        if len(output_families) < 2:
            raise RuntimeError(f"missing independent judges for {key}")
        dimensions = _median_response(outputs)
        mad = _mad_response(outputs)
        base = metadata[key]
        row = {
            "unit_id": key[0],
            "condition": key[1],
            "user_id": str(base["user_id"]),
            "topic_index": int(base["topic_index"]),
            "scenario_cluster": f"{base['user_id']}::{base['topic_index']}",
            "user_cluster": str(base["user_id"]),
            "seed": int(base["seed"]),
            "turn_index": int(base["turn_index"]),
            **dimensions.model_dump(),
            "quality_composite": composite.score(dimensions),
            "dimension_mad": mad,
            "max_dimension_mad": max(mad.values(), default=0.0),
            "label_reliable": max(mad.values(), default=0.0)
            <= reliable_mad_threshold,
            "judge_families": sorted(output_families),
        }
        score_rows.append(row)
        append_jsonl(score_path, row)
    gate = validate_external_score_table(score_rows)

    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in score_rows:
        by_condition[row["condition"]].append(row)
    condition_summary = {
        condition: {
            "n": len(rows),
            **{
                name: float(np.mean([row[name] for row in rows]))
                for name in (*DIMENSIONS, "quality_composite")
            },
        }
        for condition, rows in sorted(by_condition.items())
    }
    treatment_rows = {row["unit_id"]: row for row in by_condition[treatment]}
    comparisons: dict[str, Any] = {}
    for baseline in conditions:
        if baseline == treatment:
            continue
        baseline_rows = {row["unit_id"]: row for row in by_condition[baseline]}
        metric_results: dict[str, Any] = {}
        for metric in (*DIMENSIONS, "quality_composite"):
            paired = []
            for unit_id in sorted(set(treatment_rows) & set(baseline_rows)):
                left = treatment_rows[unit_id]
                right = baseline_rows[unit_id]
                paired.append(
                    {
                        "unit_id": unit_id,
                        "scenario_cluster": left["scenario_cluster"],
                        "user_cluster": left["user_cluster"],
                        "delta": float(left[metric]) - float(right[metric]),
                    }
                )
            metric_results[metric] = {
                "n": len(paired),
                "scenario_cluster_ci": _bootstrap_cluster_delta(
                    paired, cluster_field="scenario_cluster", seed=seed
                ),
                "user_cluster_ci": _bootstrap_cluster_delta(
                    paired, cluster_field="user_cluster", seed=seed + 1
                ),
                "wins": sum(row["delta"] > 0 for row in paired),
                "ties": sum(row["delta"] == 0 for row in paired),
                "losses": sum(row["delta"] < 0 for row in paired),
            }
        comparisons[baseline] = metric_results
    summary = {
        **dry,
        "status": "COMPLETE",
        "score_rows": len(score_rows),
        "judge_gate": gate,
        "condition_summary": condition_summary,
        "paired_treatment_deltas": comparisons,
        "scores_path": str(score_path),
        "raw_path": str(raw_path),
    }
    write_json(out_dir / "summary.json", summary)
    return summary
