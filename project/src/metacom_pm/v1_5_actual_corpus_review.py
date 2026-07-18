from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import require_artifact_attestation
from .contracts import MemoryBackendRecord, StrategyCard
from .io import iter_jsonl, read_json, sha256_file
from .pm_v2_data import load_bundles, load_evaluator_context_index, load_states
from .retrieval import StrategyRetriever, context_query


ACTUAL_CORPUS_REVIEW_PROTOCOL = "pm-v1.5-actual-468-semantic-review-v1"
ACTUAL_CORPUS_REVIEW_STAGE = "pm_v1_5_actual_corpus_semantic_review"


def _surface_fallback_report(
    *,
    bundles_path: str | Path,
    split_by_user: Mapping[str, str],
    maximum_fallback_rate_by_split: Mapping[str, float],
) -> dict[str, Any]:
    counts = {
        split: {"cases": 0, "fallback_cases": 0}
        for split in ("train", "calibration", "internal_test")
    }
    for bundle in load_bundles(bundles_path):
        split = str(split_by_user[bundle.user_id])
        selection = bundle.provenance.get("surface_selection") or {}
        fallback_cases = list(selection.get("fallback_cases") or [])
        counts[split]["cases"] += len(bundle.cases)
        counts[split]["fallback_cases"] += len(fallback_cases)
    checks = {}
    for split, row in counts.items():
        rate = row["fallback_cases"] / max(row["cases"], 1)
        row["fallback_rate"] = rate
        row["provider_surface_rate"] = 1.0 - rate
        row["maximum_fallback_rate"] = float(maximum_fallback_rate_by_split[split])
        checks[split] = rate <= float(maximum_fallback_rate_by_split[split])
    return {
        "protocol": "pm-v1.5-provider-surface-fallback-gate-v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "splits": counts,
        "checks": checks,
    }


def build_actual_corpus_review_items(
    *,
    states_path: str | Path,
    evaluator_contexts_path: str | Path,
    backend_path: str | Path,
    bundles_path: str | Path,
    strategy_bank_path: str | Path,
    strategy_top_k: int,
    strategy_min_score: float,
    maximum_fallback_rate_by_split: Mapping[str, float],
    control_seed: int,
    n_controls: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    states = load_states(states_path)
    if len(states) != 468:
        raise RuntimeError("actual-corpus semantic review requires all 468 states")
    evaluator = load_evaluator_context_index(
        evaluator_contexts_path, states=states, require_exact=True
    )
    backend_by_card = {}
    for row in iter_jsonl(backend_path):
        backend = MemoryBackendRecord.model_validate(row)
        if backend.card_id in backend_by_card:
            raise RuntimeError("actual-corpus backend repeats card_id")
        backend_by_card[backend.card_id] = backend
    cards = [StrategyCard.model_validate(row) for row in iter_jsonl(strategy_bank_path)]
    if not cards:
        raise RuntimeError("actual-corpus review requires the frozen Strategy Bank")
    strategy = StrategyRetriever(
        cards, top_k=int(strategy_top_k), minimum_score=float(strategy_min_score)
    )
    split_by_user = {state.user_id: state.split.value for state in states}
    fallback = _surface_fallback_report(
        bundles_path=bundles_path,
        split_by_user=split_by_user,
        maximum_fallback_rate_by_split=maximum_fallback_rate_by_split,
    )
    if fallback["status"] != "PASS":
        raise RuntimeError("actual corpus failed the provider-surface fallback gate")
    items = []
    for state in sorted(states, key=lambda value: value.state_id):
        context = evaluator.by_state[state.state_id]
        backend = backend_by_card.get(state.card_id)
        if backend is None:
            raise RuntimeError(f"actual-corpus backend missing {state.card_id}")
        annotations = {
            str(row["memory_id"]): row for row in context["memory_annotations"]
        }
        query = context_query(
            state.current_user_text,
            [turn.model_dump(mode="json") for turn in state.current_session_history],
            state.current_session_summary,
        )
        retrieved_cards = strategy.retrieve(query)
        lines = [
            f"Candidate semantic family: {state.semantic_family}",
            f"Candidate regime: {context['regime']}",
            "Candidate materially-useful memory sources: "
            + repr(context["needed_memory_sources"]),
            f"Data split: {state.split.value}",
            "",
            "Dialogue before current turn:",
            *[
                f"  {turn.role}: {turn.content}"
                for turn in state.current_session_history
            ],
            f"Current user message: {state.current_user_text}",
            f"Session summary: {state.current_session_summary}",
            f"Authorized user context: {context['authorized_user_context']}",
            f"Coverage rationale: {context['coverage_rationale']}",
            "",
            "Memory evidence:",
        ]
        for memory in backend.items:
            annotation = annotations[memory.memory_id]
            lines.append(
                "  - source={source}, utility={utility}, age={age}, stale={stale}, "
                "conflict={conflict}: {text}".format(
                    source=memory.source.value,
                    utility=annotation["item_utility"],
                    age=state.session_index - memory.created_session,
                    stale=annotation["stale"],
                    conflict=annotation["conflicts_with_current_state"],
                    text=memory.text,
                )
            )
        strategy_direction = {
            "strategy_helpful": "Strategy RAG should add material value",
            "strategy_harmful": "Strategy RAG is likely to encourage over-advice",
        }.get(str(context["regime"]), "No directional Strategy oracle is asserted")
        lines.extend(["", f"Strategy target: {strategy_direction}", "Retrieved Strategy cards:"])
        for card in retrieved_cards:
            lines.append(
                f"  - {card.strategy_label}: {card.guidance_text} | "
                f"example={card.example_response} | source={card.source_dialogue_id}"
            )
        items.append(
            {
                "kind": "real",
                "item_id": state.state_id,
                "split": state.split.value,
                "regime": str(context["regime"]),
                "text": "\n".join(lines),
            }
        )
    rng = random.Random(int(control_seed))
    sample = rng.sample(items, k=min(int(n_controls), len(items)))
    controls = []
    for index, item in enumerate(sample):
        field = "regime_match" if index % 2 == 0 else "semantic_family_match"
        marker = "Candidate regime:" if field == "regime_match" else "Candidate semantic family:"
        corrupted_lines = []
        for line in str(item["text"]).splitlines():
            corrupted_lines.append(
                f"{marker} deliberately_unrelated_control"
                if line.startswith(marker)
                else line
            )
        controls.append(
            {
                "item_id": f"{item['item_id']}__control_{field}",
                "case_item_id": item["item_id"],
                "corrupted_field": field,
                "rating_field": field,
                "override": {field: "deliberately_unrelated_control"},
                "case_text": "\n".join(corrupted_lines),
            }
        )
    report = {
        "protocol": ACTUAL_CORPUS_REVIEW_PROTOCOL,
        "states": len(items),
        "states_by_split": {
            split: sum(item["split"] == split for item in items)
            for split in ("train", "calibration", "internal_test")
        },
        "fallback_gate": fallback,
        "input_hashes": {
            "states": sha256_file(states_path),
            "evaluator_contexts": sha256_file(evaluator_contexts_path),
            "backend": sha256_file(backend_path),
            "bundles": sha256_file(bundles_path),
            "strategy_bank": sha256_file(strategy_bank_path),
        },
    }
    return items, controls, report


def require_actual_corpus_semantic_review_pass(
    report_path: str | Path,
    attestation_path: str | Path,
    *,
    expected_states_path: str | Path,
) -> dict[str, Any]:
    verification = require_artifact_attestation(
        attestation_path,
        required_stage=ACTUAL_CORPUS_REVIEW_STAGE,
        required_output_paths={"gate_report": report_path},
    )
    report = read_json(report_path)
    if (
        report.get("protocol") != ACTUAL_CORPUS_REVIEW_PROTOCOL
        or report.get("status") != "PASS"
        or int(report.get("n_real_cases") or 0) != 468
        or (report.get("corpus_audit") or {}).get("fallback_gate", {}).get("status")
        != "PASS"
        or (report.get("corpus_audit") or {}).get("input_hashes", {}).get("states")
        != sha256_file(expected_states_path)
    ):
        raise RuntimeError("actual 468-state semantic/fallback gate did not PASS")
    return {
        "status": "PASS",
        "report": report,
        "report_sha256": sha256_file(report_path),
        "attestation_sha256": verification["attestation_sha256"],
    }
