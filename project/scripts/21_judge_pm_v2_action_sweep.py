#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.contracts import ActionOutcome
from metacom_pm.io import append_jsonl, iter_jsonl, write_json
from metacom_pm.pm_v2_data import load_states
from metacom_pm.pm_v2_judging import (
    build_action_label,
    judge_one,
    prompt_contract_hash,
    validate_judge_table,
)

ROOT = Path(__file__).resolve().parents[1]


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
    parser.add_argument("--seed", type=int, default=2701)
    args = parser.parse_args()

    states = load_states(args.states)
    state_by_card = {state.card_id: state for state in states}
    outcomes = [ActionOutcome.model_validate(row) for row in iter_jsonl(args.outcomes)]
    outcomes = [row for row in outcomes if row.card_id in state_by_card]
    if args.max_outcomes is not None:
        outcomes = outcomes[: args.max_outcomes]
    config = load_config(args.config)
    endpoint_names = [name.strip() for name in args.judge_endpoints.split(",") if name.strip()]
    endpoints = [endpoint_from_config(config, name) for name in endpoint_names]
    families = {endpoint.family for endpoint in endpoints}
    if None in families or len(families) < 2:
        raise ValueError("PM-v2 requires at least two declared, independent judge families")
    expected_calls = len(outcomes) * len(endpoints) * 2
    summary = {
        "status": "DRY_RUN" if not args.run else "STARTING",
        "outcomes": len(outcomes),
        "judge_endpoints": endpoint_names,
        "judge_families": sorted(str(x) for x in families),
        "expected_api_calls": expected_calls,
        "prompt_contract_hash": prompt_contract_hash(),
    }
    print(summary)
    if expected_calls > args.max_api_calls:
        raise RuntimeError(
            f"budget gate failed: expected {expected_calls} calls > {args.max_api_calls}"
        )
    if not args.run:
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    labels_path = args.out_dir / "action_labels.jsonl"
    raw_path = args.out_dir / "judge_results.jsonl"
    labels_path.write_text("", encoding="utf-8")
    raw_path.write_text("", encoding="utf-8")
    labels = []
    for index, outcome in enumerate(outcomes):
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
        results = []
        for endpoint_index, endpoint in enumerate(endpoints):
            result = judge_one(
                endpoint=endpoint,
                state=state,
                authorized_user_context=authorized_context,
                selected_context=selected_context,
                candidate_response=outcome.response,
                seed=args.seed + index * 10 + endpoint_index,
            )
            results.append(result)
            append_jsonl(
                raw_path,
                {
                    "state_id": state.state_id,
                    "card_id": state.card_id,
                    "action_id": outcome.action_id,
                    "judge_family": result.family,
                    "judge_model": result.model,
                    "response": result.response.model_dump(mode="json"),
                    "risk": result.risk.model_dump(mode="json"),
                    "response_request_hash": result.response_request_hash,
                    "risk_request_hash": result.risk_request_hash,
                },
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
