#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import json

from metacom_pm.api import OpenAICompatibleClient
from metacom_pm.artifacts import create_artifact_attestation, require_artifact_attestation
from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.contracts import ActionOutcome, ResponsePairJudgment, RuntimeState
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import append_jsonl, iter_jsonl, load_done_keys, read_json, stable_hex, write_json
from metacom_pm.judging import _call_with_semantic_retry
from metacom_pm.prompts import response_pair_messages
from metacom_pm.stats import cluster_bootstrap_ci


ROOT = Path(__file__).resolve().parents[1]
ACTION_R0 = "M0+R0"
ACTION_RS = "M0+RS"


def _load_outcomes(path: Path) -> dict[tuple[str, str], ActionOutcome]:
    result: dict[tuple[str, str], ActionOutcome] = {}
    for row in iter_jsonl(path):
        outcome = ActionOutcome.model_validate(row)
        result[(outcome.card_id, outcome.action_id)] = outcome
    return result


def _mean(values: list[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def _build_pending(
    states: dict[str, RuntimeState],
    outcomes: dict[tuple[str, str], ActionOutcome],
    audit: dict[str, dict],
) -> list[dict]:
    pending = []
    for index, card_id in enumerate(
        sorted(states, key=lambda cid: stable_hex("esconv-strategy-only", cid, n=32))
    ):
        if (card_id, ACTION_R0) not in outcomes or (card_id, ACTION_RS) not in outcomes:
            raise RuntimeError(f"missing required ESConv outcomes for {card_id}")
        if card_id not in audit:
            raise RuntimeError(f"missing ESConv audit row for {card_id}")
        if index % 2 == 0:
            action_a, action_b = ACTION_RS, ACTION_R0
        else:
            action_a, action_b = ACTION_R0, ACTION_RS
        pending.append({
            "card_id": card_id,
            "dialogue_id": audit[card_id]["dialogue_id"],
            "turn_index": audit[card_id]["turn_index"],
            "gold_strategy": audit[card_id].get("gold_strategy"),
            "action_a": action_a,
            "action_b": action_b,
        })
    return pending


def _summarize(
    rows: list[dict],
    outcomes: dict[tuple[str, str], ActionOutcome],
) -> dict:
    wins = sum(row["winner_action"] == ACTION_RS for row in rows)
    losses = sum(row["winner_action"] == ACTION_R0 for row in rows)
    ties = sum(row["winner_action"] == "tie" for row in rows)
    n = len(rows)
    bootstrap = cluster_bootstrap_ci(
        rows,
        cluster_key="dialogue_id",
        value_key="rs_score",
        seed=20260628,
        n_resamples=10000,
    ).as_dict() if rows else None

    by_dialogue: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_dialogue[str(row["dialogue_id"])].append(float(row["rs_score"]))

    cost_by_action: dict[str, dict[str, float | None]] = {}
    for action in (ACTION_R0, ACTION_RS):
        selected = [outcome for (card_id, aid), outcome in outcomes.items() if aid == action]
        cost_by_action[action] = {
            "n": len(selected),
            "mean_total_input_tokens": _mean([float(x.cost.total_input_tokens) for x in selected]),
            "mean_output_tokens": _mean([float(x.cost.output_tokens) for x in selected]),
            "mean_retrieval_calls": _mean([float(x.cost.retrieval_calls) for x in selected]),
            "mean_strategy_tokens": _mean([float(x.cost.strategy_tokens) for x in selected]),
        }

    strategy_recall_rows = [
        row for row in rows
        if isinstance(row.get("gold_strategy"), str) and row.get("gold_strategy")
    ]
    strategy_hits = 0
    for row in strategy_recall_rows:
        rs = outcomes[(row["card_id"], ACTION_RS)]
        labels = {card.strategy_label for card in rs.strategy_view}
        strategy_hits += row["gold_strategy"] in labels

    return {
        "comparison": f"{ACTION_RS}_vs_{ACTION_R0}",
        "n": n,
        "dialogue_clusters": len(by_dialogue),
        "rs_wins": wins,
        "ties": ties,
        "r0_wins": losses,
        "rs_preference_score": (wins + 0.5 * ties) / n if n else None,
        "rs_preference_dialogue_cluster_bootstrap": bootstrap,
        "strategy_recall_at_retrieved_k": (
            strategy_hits / len(strategy_recall_rows) if strategy_recall_rows else None
        ),
        "strategy_recall_denominator": len(strategy_recall_rows),
        "cost_by_action": cost_by_action,
        "interpretation": (
            "ESConv is single-session and has no long-term memory. This evaluation "
            "only tests whether Strategy RAG (RS) helps or hurts ordinary ESC "
            "responses under fixed generated outcomes."
        ),
    }


def run_strategy_only_eval(
    *,
    runtime_path: Path,
    audit_path: Path,
    outcomes_path: Path,
    out_dir: Path,
    endpoint_name: str,
    config_path: Path,
    freeze_path: Path,
    outcomes_attestation_path: Path,
    overwrite: bool,
    dry_run: bool,
) -> dict:
    freeze = require_study_freeze(
        freeze_path,
        release_root=ROOT,
        config_path=config_path,
        required_files=[runtime_path, audit_path],
    )
    outcomes_verification = require_artifact_attestation(
        outcomes_attestation_path,
        required_stage="action_sweep",
        required_output_paths={"action_outcomes": outcomes_path},
        # The ESConv sweep may have been generated under an earlier freeze that
        # differs only by this evaluation entrypoint. We bind that attestation as
        # an input below instead of pretending it was generated by this script.
        expected_freeze_sha256=None,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    response_path = out_dir / "strategy_pair_judgments.jsonl"
    raw_path = out_dir / "raw_judge_calls.jsonl"
    summary_path = out_dir / "summary.json"
    attestation_path = out_dir / "artifact_attestation.json"
    if overwrite:
        for path in (response_path, raw_path, summary_path, attestation_path):
            if path.exists():
                path.unlink()

    states = {row["card_id"]: RuntimeState.model_validate(row) for row in iter_jsonl(runtime_path)}
    audit = {row["card_id"]: row for row in iter_jsonl(audit_path)}
    outcomes = _load_outcomes(outcomes_path)
    pending = _build_pending(states, outcomes, audit)

    if dry_run:
        result = {
            "status": "DRY_RUN",
            "expected_pairs": len(pending),
            "dialogue_clusters": len({row["dialogue_id"] for row in pending}),
            "endpoint": endpoint_name,
            "freeze_sha256": freeze.get("freeze_sha256"),
            "outcomes_attestation_verification": outcomes_verification,
        }
        write_json(summary_path, result)
        return result

    endpoint = endpoint_from_config(load_config(config_path), endpoint_name)
    client = OpenAICompatibleClient(endpoint)
    done = load_done_keys(response_path, ("card_id",))
    try:
        for row in pending:
            if (row["card_id"],) in done:
                continue
            state = states[row["card_id"]]
            outcome_a = outcomes[(row["card_id"], row["action_a"])]
            outcome_b = outcomes[(row["card_id"], row["action_b"])]
            parsed = _call_with_semantic_retry(
                client,
                endpoint,
                response_pair_messages(state, outcome_a.response, outcome_b.response),
                ResponsePairJudgment,
                None,
                stage="esconv_strategy_pair",
                record_ids={"card_id": row["card_id"]},
                raw_log_path=raw_path,
            )
            winner_action = (
                row["action_a"] if parsed.preference == "A"
                else row["action_b"] if parsed.preference == "B"
                else "tie"
            )
            append_jsonl(response_path, {
                **row,
                **parsed.model_dump(mode="json"),
                "winner_action": winner_action,
                "rs_score": 1.0 if winner_action == ACTION_RS else 0.5 if winner_action == "tie" else 0.0,
                "r0_total_input_tokens": outcomes[(row["card_id"], ACTION_R0)].cost.total_input_tokens,
                "rs_total_input_tokens": outcomes[(row["card_id"], ACTION_RS)].cost.total_input_tokens,
            })
    finally:
        client.close()

    rows = list(iter_jsonl(response_path))
    expected = {row["card_id"] for row in pending}
    observed = {row["card_id"] for row in rows}
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing or extra:
        raise RuntimeError(
            "ESConv strategy-only evaluation incomplete or stale: "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )

    summary = _summarize(rows, outcomes)
    summary.update({
        "status": "COMPLETE",
        "judge_model": endpoint.model,
        "judge_family": endpoint.family,
        "endpoint_base_url": endpoint.base_url,
        "freeze_sha256": freeze.get("freeze_sha256"),
        "outcomes_attestation_verification": outcomes_verification,
    })
    write_json(summary_path, summary)
    raw_path.touch(exist_ok=True)
    create_artifact_attestation(
        attestation_path,
        stage="esconv_strategy_only_evaluation",
        inputs={
            "runtime": runtime_path,
            "audit": audit_path,
            "action_outcomes": outcomes_path,
            "action_sweep_attestation": outcomes_attestation_path,
            "study_freeze": freeze_path,
        },
        outputs={
            "strategy_pair_judgments": (response_path, True),
            "raw_calls": (raw_path, True),
            "summary": (summary_path, False),
        },
        parameters={
            "comparison": f"{ACTION_RS}_vs_{ACTION_R0}",
            "judge_endpoint": endpoint_name,
            "judge_model": endpoint.model,
            "judge_family": endpoint.family,
            "judge_base_url": endpoint.base_url,
        },
        expected={
            "pairs": len(pending),
            "dialogue_clusters": len({row["dialogue_id"] for row in pending}),
        },
        study_freeze_sha256=freeze.get("freeze_sha256"),
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiment.yaml")
    parser.add_argument("--endpoint", default="final_judge")
    parser.add_argument("--freeze", type=Path, default=ROOT / "outputs/study_freeze.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs/esconv_strategy_eval")
    parser.add_argument("--outcomes-attestation", type=Path, default=ROOT / "outputs/esconv_sweep/artifact_attestation.json")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run_strategy_only_eval(
        runtime_path=ROOT / "data/esconv_test/runtime_states.jsonl",
        audit_path=ROOT / "data/esconv_test/audit_only.jsonl",
        outcomes_path=ROOT / "outputs/esconv_sweep/action_outcomes.jsonl",
        out_dir=args.out_dir,
        endpoint_name=args.endpoint,
        config_path=args.config,
        freeze_path=args.freeze,
        outcomes_attestation_path=args.outcomes_attestation,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
