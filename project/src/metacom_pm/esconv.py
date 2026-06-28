from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any
import numpy as np

from .api import Endpoint, OpenAICompatibleClient
from .artifacts import create_artifact_attestation, require_artifact_attestation
from .contracts import (
    ActionOutcome,
    MemoryBackendRecord,
    MemorySource,
    ResponsePairJudgment,
    RuntimeState,
    SourceCatalog,
    StrategyCard,
    StrategyMode,
)
from .io import (
    append_jsonl, canonical_json, iter_jsonl, load_done_keys, read_json,
    sha256_file, sha256_text, stable_hex, write_json, write_jsonl,
)
from .judging import _call_with_semantic_retry
from .policies import (
    FixedPolicy, LearnedPMPolicy, RuleConfig, StrongRulePolicy
)
from .prompts import response_pair_messages
from .retrieval import StrategyRetriever, context_query
from .strategy_bank import esconv_turn_states
from .training import PMModel


ZERO_FP = [0.0] * 64


def build_esconv_test_runtime(
    esconv_path: str | Path,
    split_manifest_path: str | Path,
    out_runtime_path: str | Path,
    out_backend_path: str | Path,
    out_audit_path: str | Path,
) -> dict[str, Any]:
    turns = esconv_turn_states(esconv_path, split_manifest_path, "test")
    runtime_rows = []
    backend_rows = []
    audit_rows = []
    for turn in turns:
        state_id = f"state_{stable_hex('esconv', turn['dialogue_id'], turn['turn_index'], n=20)}"
        card_id = f"card_{stable_hex(state_id, 'test', n=20)}"
        state = RuntimeState(
            state_id=state_id,
            card_id=card_id,
            user_id=turn["dialogue_id"],
            split="esconv_test",
            semantic_family="esconv_strategy_routing",
            current_user_text=turn["current_user_text"],
            current_session_history=turn["history"],
            current_session_summary=turn["situation"],
            session_index=1,
            inventory={
                source: SourceCatalog(
                    available=False, count=0, estimated_tokens=0,
                    catalog_fingerprint=ZERO_FP,
                )
                for source in MemorySource
            },
            allowed_actions=["M0+R0", "M0+RS"],
            provenance={
                "dialogue_id": turn["dialogue_id"],
                "turn_index": turn["turn_index"],
            },
        )
        runtime_rows.append(state.model_dump(mode="json"))
        backend_rows.append(
            MemoryBackendRecord(card_id=card_id, items=[]).model_dump(mode="json")
        )
        audit_rows.append({
            "card_id": card_id,
            "dialogue_id": turn["dialogue_id"],
            "turn_index": turn["turn_index"],
            "gold_response": turn["gold_response"],
            "gold_strategy": turn["gold_strategy"],
            "evaluator_only": True,
        })
    write_jsonl(out_runtime_path, runtime_rows)
    write_jsonl(out_backend_path, backend_rows)
    write_jsonl(out_audit_path, audit_rows)
    return {
        "n_test_turns": len(runtime_rows),
        "n_dialogues": len({x["dialogue_id"] for x in audit_rows}),
    }


def _load_outcomes(path: str | Path) -> dict[tuple[str, str], ActionOutcome]:
    result = {}
    for row in iter_jsonl(path):
        item = ActionOutcome.model_validate(row)
        result[(item.card_id, item.action_id)] = item
    return result


def _policy_choices(
    runtime_path: str | Path,
    checkpoint_path: str | Path,
    selection_path: str | Path,
    strategy_bank_path: str | Path,
) -> dict[str, dict[str, str]]:
    states = {
        row["card_id"]: RuntimeState.model_validate(row)
        for row in iter_jsonl(runtime_path)
    }
    model = PMModel.load(checkpoint_path)
    selection = read_json(selection_path)
    cards = [StrategyCard.model_validate(x) for x in iter_jsonl(strategy_bank_path)]
    retriever = StrategyRetriever(cards)
    policies = {
        "pm": LearnedPMPolicy(
            model,
            epsilon=float(selection["pm"]["epsilon"]),
            tau_misuse=float(selection["pm"]["tau_misuse"]),
            tau_omission=float(selection["pm"]["tau_omission"]),
            tau_strategy=float(selection["pm"]["tau_strategy"]),
        ),
        "always_r0": FixedPolicy("M0+R0", name="always_r0"),
        "always_rs": FixedPolicy("M0+RS", name="always_rs"),
        "best_fixed": FixedPolicy(
            selection["best_fixed_action"], name="best_fixed"
        ),
        "strong_rule": StrongRulePolicy(
            RuleConfig(**selection["strong_rule"]["config"]),
            retriever,
        ),
    }
    return {
        name: {card_id: policy.choose(state) for card_id, state in states.items()}
        for name, policy in policies.items()
    }


def _cluster_bootstrap(
    rows: list[dict[str, Any]],
    cluster_key: str,
    seed: int = 42,
    n_boot: int = 5000,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    clusters = defaultdict(list)
    for row in rows:
        clusters[row[cluster_key]].append(row["score"])
    keys = sorted(clusters)
    observed = float(np.mean([x["score"] for x in rows])) if rows else 0.5
    if not keys:
        return {"mean": observed, "ci_low": observed, "ci_high": observed}
    values = []
    for _ in range(n_boot):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        scores = [score for key in sampled for score in clusters[key]]
        values.append(float(np.mean(scores)))
    return {
        "mean": observed,
        "ci_low": float(np.quantile(values, 0.025)),
        "ci_high": float(np.quantile(values, 0.975)),
    }


def run_esconv_policy_evaluation(
    runtime_path: str | Path,
    audit_path: str | Path,
    outcomes_path: str | Path,
    strategy_bank_path: str | Path,
    checkpoint_path: str | Path,
    selection_path: str | Path,
    out_dir: str | Path,
    *,
    judge_endpoint: Endpoint,
    overwrite: bool = False,
    outcomes_attestation_path: str | Path | None = None,
    study_freeze_sha256: str | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    response_path = out_dir / "policy_pair_judgments.jsonl"
    raw_path = out_dir / "raw_judge_calls.jsonl"
    summary_path = out_dir / "summary.json"
    attestation_path = out_dir / "artifact_attestation.json"
    if overwrite:
        for p in (response_path, raw_path, summary_path, attestation_path):
            if p.exists(): p.unlink()
    outcomes_attestation_path = Path(
        outcomes_attestation_path or Path(outcomes_path).parent / "artifact_attestation.json"
    ).resolve()
    outcomes_verification = require_artifact_attestation(
        outcomes_attestation_path,
        required_stage="action_sweep",
        required_output_paths={"action_outcomes": outcomes_path},
        expected_freeze_sha256=study_freeze_sha256,
    )

    states = {
        row["card_id"]: RuntimeState.model_validate(row)
        for row in iter_jsonl(runtime_path)
    }
    audit = {row["card_id"]: row for row in iter_jsonl(audit_path)}
    outcomes = _load_outcomes(outcomes_path)
    choices = _policy_choices(
        runtime_path, checkpoint_path, selection_path, strategy_bank_path
    )
    comparisons = ["always_r0", "always_rs", "best_fixed", "strong_rule"]

    # Build orientation-balanced comparison rows.
    pending = []
    for baseline in comparisons:
        card_ids = sorted(states, key=lambda cid: stable_hex("esconv-eval", baseline, cid, n=32))
        for index, card_id in enumerate(card_ids):
            pm_action = choices["pm"][card_id]
            base_action = choices[baseline][card_id]
            if index % 2 == 0:
                policy_a, action_a = "pm", pm_action
                policy_b, action_b = baseline, base_action
            else:
                policy_a, action_a = baseline, base_action
                policy_b, action_b = "pm", pm_action
            pending.append({
                "comparison": f"pm_vs_{baseline}",
                "card_id": card_id,
                "policy_a": policy_a,
                "policy_b": policy_b,
                "action_a": action_a,
                "action_b": action_b,
            })

    done = load_done_keys(response_path, ("comparison", "card_id"))
    client = OpenAICompatibleClient(judge_endpoint)
    try:
        for row in pending:
            if (row["comparison"], row["card_id"]) in done:
                continue
            card_id = row["card_id"]
            state = states[card_id]
            oa = outcomes[(card_id, row["action_a"])]
            ob = outcomes[(card_id, row["action_b"])]
            if row["action_a"] == row["action_b"]:
                parsed = ResponsePairJudgment(
                    preference="tie", empathy="tie", contextual_fit="tie",
                    guidance_fit="tie", non_intrusiveness="tie",
                    coherence="tie", reason="Both policies selected the same response."
                )
            else:
                parsed = _call_with_semantic_retry(
                    client, judge_endpoint,
                    response_pair_messages(state, oa.response, ob.response),
                    ResponsePairJudgment, None,
                    stage="esconv_policy_pair",
                    record_ids={
                        "comparison": row["comparison"],
                        "card_id": card_id,
                    },
                    raw_log_path=raw_path,
                )
            winner_policy = (
                row["policy_a"] if parsed.preference == "A"
                else row["policy_b"] if parsed.preference == "B"
                else "tie"
            )
            pm_score = 1.0 if winner_policy == "pm" else 0.5 if winner_policy == "tie" else 0.0
            append_jsonl(response_path, {
                **row,
                **parsed.model_dump(mode="json"),
                "winner_policy": winner_policy,
                "pm_score": pm_score,
                "dialogue_id": audit[card_id]["dialogue_id"],
                "pm_cost": outcomes[(card_id, choices["pm"][card_id])].cost.model_dump(mode="json"),
                "baseline_cost": outcomes[(card_id, choices[row["policy_b"] if row["policy_a"] == "pm" else row["policy_a"]][card_id])].cost.model_dump(mode="json"),
            })
    finally:
        client.close()

    judged = list(iter_jsonl(response_path))
    expected_keys = {(row["comparison"], row["card_id"]) for row in pending}
    judged_keys = {(row["comparison"], row["card_id"]) for row in judged}
    missing = expected_keys - judged_keys
    extra = judged_keys - expected_keys
    if missing or extra:
        raise RuntimeError(
            "ESConv policy evaluation incomplete or stale: "
            f"missing={sorted(missing)[:10]}, extra={sorted(extra)[:10]}"
        )
    results = {}
    for comparison in sorted({x["comparison"] for x in judged}):
        rows = [
            {"dialogue_id": x["dialogue_id"], "score": x["pm_score"]}
            for x in judged if x["comparison"] == comparison
        ]
        w = sum(x["score"] == 1 for x in rows)
        t = sum(x["score"] == 0.5 for x in rows)
        l = sum(x["score"] == 0 for x in rows)
        results[comparison] = {
            "n": len(rows), "wins": w, "ties": t, "losses": l,
            "preference_score": (w + 0.5 * t) / len(rows) if rows else None,
            "dialogue_cluster_bootstrap": _cluster_bootstrap(rows, "dialogue_id"),
        }

    # Auxiliary retrieval-to-gold-strategy Recall@k.
    strategy_cards = [
        StrategyCard.model_validate(x) for x in iter_jsonl(strategy_bank_path)
    ]
    retriever = StrategyRetriever(strategy_cards)
    hits = 0
    for card_id, state in states.items():
        query = context_query(
            state.current_user_text,
            [x.model_dump(mode="json") for x in state.current_session_history],
            state.current_session_summary,
        )
        labels = {x.strategy_label for x in retriever.retrieve(query)}
        hits += audit[card_id]["gold_strategy"] in labels
    result = {
        "policy_comparisons": results,
        "strategy_recall_at_k": hits / len(states) if states else None,
        "n_test_turns": len(states),
        "outcomes_attestation_verification": outcomes_verification,
        "judge_model": judge_endpoint.model,
        "judge_family": judge_endpoint.family,
        "interpretation": (
            "ESConv contains no cross-session memory; this evaluates R0/RS "
            "strategy routing and false-memory abstention only."
        ),
    }
    write_json(summary_path, result)
    response_path.touch(exist_ok=True)
    raw_path.touch(exist_ok=True)
    create_artifact_attestation(
        attestation_path,
        stage="esconv_policy_evaluation",
        inputs={
            "runtime": runtime_path,
            "audit": audit_path,
            "action_outcomes": outcomes_path,
            "strategy_bank": strategy_bank_path,
            "checkpoint": checkpoint_path,
            "selection": selection_path,
            "action_sweep_attestation": outcomes_attestation_path,
        },
        outputs={
            "policy_pair_judgments": (response_path, True),
            "raw_calls": (raw_path, True),
            "summary": (summary_path, False),
        },
        parameters={
            "judge_model": judge_endpoint.model,
            "judge_family": judge_endpoint.family,
            "judge_base_url": judge_endpoint.base_url,
        },
        expected={
            "test_turns": len(states),
            "comparisons": len(expected_keys),
        },
        study_freeze_sha256=study_freeze_sha256,
    )
    return result
