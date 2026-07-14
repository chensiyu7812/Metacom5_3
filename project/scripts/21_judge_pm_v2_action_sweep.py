#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.contracts import ActionOutcome
from metacom_pm.io import append_jsonl, iter_jsonl, write_json
from metacom_pm.pm_v2_data import load_states
from metacom_pm.pm_v2_judging import (
    JudgeResult,
    ResponseJudgeOutput,
    RiskJudgeOutput,
    build_action_label,
    judge_one,
    prompt_contract_hash,
    validate_judge_table,
)

ROOT = Path(__file__).resolve().parents[1]


def raw_key(row):
    return str(row["state_id"]), str(row["action_id"]), str(row["judge_family"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "experiment.yaml")
    parser.add_argument("--states", type=Path, default=ROOT / "data" / "pm_v2" / "pm_v2_states.jsonl")
    parser.add_argument("--outcomes", type=Path, default=ROOT / "outputs" / "pm_v2_sweep" / "action_outcomes.jsonl")
    parser.add_argument("--judge-endpoints", required=True, help="comma-separated endpoint names; at least two independent families")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "pm_v2_judging")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-outcomes", type=int)
    parser.add_argument("--max-api-calls", type=int, default=50000)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--seed", type=int, default=2701)
    args = parser.parse_args()

    states = load_states(args.states)
    state_by_card = {state.card_id: state for state in states}
    outcomes = [ActionOutcome.model_validate(row) for row in iter_jsonl(args.outcomes)]
    outcomes = [row for row in outcomes if row.card_id in state_by_card]
    if len({(row.card_id, row.action_id) for row in outcomes}) != len(outcomes):
        raise RuntimeError("duplicate state-action outcomes")
    if args.max_outcomes is not None:
        outcomes = outcomes[: args.max_outcomes]
    config = load_config(args.config)
    endpoint_names = [name.strip() for name in args.judge_endpoints.split(",") if name.strip()]
    endpoints = [endpoint_from_config(config, name) for name in endpoint_names]
    families = {endpoint.family for endpoint in endpoints}
    if None in families or len(families) < 2 or len(families) != len(endpoints):
        raise ValueError(
            "PM-v2 requires at least two endpoints from distinct, declared judge families"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    labels_path = args.out_dir / "action_labels.jsonl"
    raw_path = args.out_dir / "judge_results.jsonl"
    if args.overwrite:
        for path in (labels_path, raw_path, args.out_dir / "summary.json"):
            if path.exists():
                path.unlink()
    raw_rows = list(iter_jsonl(raw_path)) if raw_path.exists() else []
    raw_by_key = {}
    for row in raw_rows:
        key = raw_key(row)
        if key in raw_by_key:
            raise RuntimeError(f"duplicate judge result key: {key}")
        raw_by_key[key] = row
    required_keys = {
        (state_by_card[outcome.card_id].state_id, outcome.action_id, str(endpoint.family))
        for outcome in outcomes
        for endpoint in endpoints
    }
    unexpected = sorted(set(raw_by_key) - required_keys)
    if unexpected:
        raise RuntimeError(
            "existing raw judge file contains rows outside this frozen run: "
            + str(unexpected[:10])
        )
    missing_keys = required_keys - set(raw_by_key)
    remaining_calls = len(missing_keys) * 2
    full_calls = len(required_keys) * 2
    summary = {
        "status": "DRY_RUN" if not args.run else "STARTING",
        "outcomes": len(outcomes),
        "judge_endpoints": endpoint_names,
        "judge_families": sorted(str(value) for value in families),
        "full_expected_api_calls": full_calls,
        "completed_judge_pairs": len(raw_by_key),
        "remaining_judge_pairs": len(missing_keys),
        "remaining_api_calls": remaining_calls,
        "prompt_contract_hash": prompt_contract_hash(),
        "resumable": True,
    }
    print(summary)
    if remaining_calls > args.max_api_calls:
        raise RuntimeError(
            f"budget gate failed: remaining {remaining_calls} calls > {args.max_api_calls}"
        )
    if not args.run:
        return

    outcome_index = {
        (state_by_card[outcome.card_id].state_id, outcome.action_id): index
        for index, outcome in enumerate(outcomes)
    }
    for outcome in outcomes:
        state = state_by_card[outcome.card_id]
        authorized_context = str(state.provenance.get("authorized_user_context") or "")
        if not authorized_context:
            raise RuntimeError(f"state {state.card_id} lacks authorized_user_context")
        selected_context = "\n".join(
            [f"MEMORY[{item.source.value}]: {item.text}" for item in outcome.memory_view]
            + [
                f"STRATEGY[{card.strategy_label}]: {card.guidance_text}"
                for card in outcome.strategy_view
            ]
        )
        for endpoint_index, endpoint in enumerate(endpoints):
            key = (state.state_id, outcome.action_id, str(endpoint.family))
            if key in raw_by_key:
                continue
            index = outcome_index[(state.state_id, outcome.action_id)]
            result = judge_one(
                endpoint=endpoint,
                state=state,
                authorized_user_context=authorized_context,
                selected_context=selected_context,
                candidate_response=outcome.response,
                seed=args.seed + index * 10 + endpoint_index,
            )
            row = {
                "state_id": state.state_id,
                "card_id": state.card_id,
                "action_id": outcome.action_id,
                "judge_family": result.family,
                "judge_model": result.model,
                "response": result.response.model_dump(mode="json"),
                "risk": result.risk.model_dump(mode="json"),
                "response_request_hash": result.response_request_hash,
                "risk_request_hash": result.risk_request_hash,
            }
            append_jsonl(raw_path, row)
            raw_by_key[key] = row

    missing_after = sorted(required_keys - set(raw_by_key))
    if missing_after:
        report = {**summary, "status": "INCOMPLETE", "missing_keys": missing_after[:50]}
        write_json(args.out_dir / "summary.json", report)
        raise RuntimeError(f"judge run incomplete: {len(missing_after)} missing pairs")

    labels = []
    labels_path.write_text("", encoding="utf-8")
    for outcome in outcomes:
        state = state_by_card[outcome.card_id]
        results = []
        for endpoint in endpoints:
            row = raw_by_key[(state.state_id, outcome.action_id, str(endpoint.family))]
            if str(row["judge_model"]) != endpoint.model:
                raise RuntimeError(
                    f"judge model changed for {state.state_id}/{outcome.action_id}/"
                    f"{endpoint.family}: {row['judge_model']} != {endpoint.model}"
                )
            results.append(
                JudgeResult(
                    family=str(row["judge_family"]),
                    model=str(row["judge_model"]),
                    response=ResponseJudgeOutput.model_validate(row["response"]),
                    risk=RiskJudgeOutput.model_validate(row["risk"]),
                    response_request_hash=str(row["response_request_hash"]),
                    risk_request_hash=str(row["risk_request_hash"]),
                )
            )
        label = build_action_label(
            state=state,
            action_id=outcome.action_id,
            observed_input_tokens=outcome.cost.total_input_tokens,
            retrieval_calls=outcome.cost.retrieval_calls,
            results=results,
            provenance={
                "outcome_request_hash": outcome.request_hash,
                "outcome_prompt_hash": outcome.prompt_hash,
            },
        )
        labels.append(label)
        append_jsonl(labels_path, label.model_dump(mode="json"))
    quality_gate = validate_judge_table(labels)
    report = {
        **summary,
        "status": "COMPLETE",
        "completed_judge_pairs": len(required_keys),
        "remaining_judge_pairs": 0,
        "remaining_api_calls": 0,
        "label_rows": len(labels),
        "reliable_rows": sum(label.label_reliable for label in labels),
        "quality_gate": quality_gate,
        "labels_path": str(labels_path),
        "raw_path": str(raw_path),
    }
    write_json(args.out_dir / "summary.json", report)
    print(report)


if __name__ == "__main__":
    main()
