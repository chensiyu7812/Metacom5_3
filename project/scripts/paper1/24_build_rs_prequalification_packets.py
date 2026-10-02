#!/usr/bin/env python3
"""Build outcome-free RS semantics packet/rubric and uptake schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, sha256_file, sha256_text  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.rs.zero_outcome_census import build_rs_decision_states  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.canonicalization import ExactTreatmentAlias  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.qualification import (  # noqa: E402
    BlindAdherenceReview,
    QualificationState,
    UptakeAssignment,
    UptakeExecutionRecord,
    UptakeRuntimeManifest,
    render_step2_prompt,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _schema_hash(model: type) -> str:
    return sha256_text(canonical_json(model.model_json_schema()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--canonical-catalog",
        type=Path,
        default=PROJECT / "data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl",
    )
    parser.add_argument(
        "--top8",
        type=Path,
        default=PROJECT / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_v1.jsonl",
    )
    parser.add_argument(
        "--top8-report",
        type=Path,
        default=PROJECT / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_report_v1.json",
    )
    args = parser.parse_args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    report = json.loads(args.top8_report.read_text(encoding="utf-8"))
    if sha256_file(args.canonical_catalog) != report["identities"]["canonical_catalog_sha256"]:
        raise RuntimeError("canonical catalog hash mismatch")
    if sha256_file(args.top8) != report["identities"]["canonical_top8_sha256"]:
        raise RuntimeError("canonical Top-8 hash mismatch")

    aliases = {
        raw["treatment_id"]: ExactTreatmentAlias.model_validate(raw)
        for raw in _read_jsonl(args.canonical_catalog)
    }
    ranked_rows = _read_jsonl(args.top8)
    ranked_by_state = {row["state_id"]: row for row in ranked_rows}
    states = build_rs_decision_states(
        esconv_path=PROJECT / "data/external/ESConv.json",
        split_manifest_path=PROJECT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
        source_splits=("train", "validation"),
        exclude_evoemo_overlap=True,
        query_preceding_turns=6,
    )
    state_by_id = {state.state_id: state for state in states}

    # Four ranks x eight families x two items is the intended 64-item grid.
    # Exact-treatment aliases may carry more than one historical family; the
    # lexicographically first family is only a transparent sampling stratum,
    # while the row preserves the complete family union.
    seed = "paper1-rs-resource-semantics-dev-seed-20260820-v1"
    buckets: dict[tuple[int, str], list[tuple[str, dict[str, Any], Any]]] = defaultdict(list)
    for row in ranked_rows:
        if row["source_split"] != "validation":
            continue
        state = state_by_id[row["state_id"]]
        for rank in (1, 2, 4, 8):
            selected = row["ranked_treatments"][rank - 1]
            alias = aliases[selected["treatment_id"]]
            primary_family = sorted(alias.atomic_move_families)[0]
            key = hashlib.sha256(
                f"{seed}|{rank}|{primary_family}|{row['state_id']}|{alias.treatment_id}".encode()
            ).hexdigest()
            buckets[(rank, primary_family)].append((key, selected, state))

    selected_items: list[tuple[int, str, dict[str, Any], Any]] = []
    used: set[tuple[str, str]] = set()
    for (rank, family), values in sorted(buckets.items()):
        for _key, selected, state in sorted(values)[:2]:
            identity = (state.state_id, selected["treatment_id"])
            if identity in used:
                continue
            used.add(identity)
            selected_items.append((rank, family, selected, state))
    # Fill to 64 deterministically if a rare family/rank cell has <2 natural rows.
    pool = []
    for (rank, family), values in buckets.items():
        for key, selected, state in values:
            pool.append((key, rank, family, selected, state))
    for _key, rank, family, selected, state in sorted(pool):
        if len(selected_items) >= 64:
            break
        identity = (state.state_id, selected["treatment_id"])
        if identity not in used:
            used.add(identity)
            selected_items.append((rank, family, selected, state))
    if len(selected_items) != 64:
        raise RuntimeError(f"could not construct 64-item RS semantics packet: {len(selected_items)}")

    packet_rows = []
    for rank, family, selected, state in selected_items:
        alias = aliases[selected["treatment_id"]]
        if state.source_dialogue_id in alias.source_dialogue_ids:
            raise RuntimeError("qualification row violates leave-dialogue-out")
        packet_rows.append(
            {
                "qualification_item_id": "rs_semq_" + sha256_text(
                    f"{seed}|{state.state_id}|{rank}|{alias.treatment_id}"
                )[:24],
                "source_dataset": "ESConv",
                "qualification_pool": "ESConv_validation_isolated_from_all_future_ESC_role_cards",
                "source_dialogue_id": state.source_dialogue_id,
                "source_split": state.source_split,
                "decision_turn_index": state.decision_turn_index,
                "visible_state": state.query_text,
                "current_user_text": state.current_user_text,
                "query_text": state.query_text,
                "rank": rank,
                "cosine_similarity": selected["cosine_similarity"],
                "canonical_treatment_id": alias.treatment_id,
                "exact_rendered_treatment": alias.rendered_card_text,
                "rendered_card_text_sha256": alias.rendered_card_text_sha256,
                "sampling_primary_family": family,
                "atomic_move_family_union": list(alias.atomic_move_families),
                "provenance_union": {
                    "atomic_card_ids": list(alias.atomic_card_ids),
                    "source_card_ids": list(alias.source_card_ids),
                    "source_dialogue_ids": list(alias.source_dialogue_ids),
                    "representative_atomic_card_id": alias.representative_atomic_card_id,
                    "representative_source_card_id": alias.representative_source_card_id,
                },
                "human_review": None,
            }
        )

    rubric = {
        "atomicity": {
            "question": "Does the treatment express one executable supporter move rather than a bundle?",
            "labels": ["PASS", "MULTI_MOVE", "VAGUE", "UNCERTAIN"],
        },
        "state_appropriateness": {
            "question": "Is this move semantically appropriate to the visible state without using hidden facts?",
            "labels": ["PASS", "TOPIC_MISMATCH", "UNSUPPORTED_ASSUMPTION", "UNCERTAIN"],
        },
        "boundary_compatibility": {
            "question": "Does it respect explicit listen-only, no-advice and no-probing boundaries?",
            "labels": ["PASS", "BOUNDARY_CONFLICT", "NO_EXPLICIT_BOUNDARY", "UNCERTAIN"],
        },
        "executability": {
            "question": "Can frozen Step2/Generator act on the move without extra retrieval or hidden interpretation?",
            "labels": ["PASS", "NOT_EXECUTABLE", "UNDERSPECIFIED", "UNCERTAIN"],
        },
        "leakage": {
            "question": "Does the exact rendered move expose source-specific names, facts, dialogue wording or outcome?",
            "labels": ["PASS", "SOURCE_SPECIFIC_LEAKAGE", "OUTCOME_LEAKAGE", "UNCERTAIN"],
        },
        "redundancy_near_duplicate": {
            "question": "Is it redundant with the visible supporter behavior or a near-duplicate of another reviewed ticket?",
            "labels": ["DISTINCT", "VISIBLE_REDUNDANCY", "NEAR_DUPLICATE", "UNCERTAIN"],
            "note": "near-duplicate label is diagnostic only and never deletes a ticket by threshold",
        },
        "final_semantics_label": ["QUALIFIED", "NOT_QUALIFIED", "UNCERTAIN"],
        "LLM_may_replace_human": False,
        "blind_to": ["PM identity", "future ESC arm", "Generator outcome", "evaluator score"],
    }
    packet = {
        "protocol": "pm-paper1-rs-resource-semantics-qualification-packet-v1",
        "status": "AUDIT_REQUIRED",
        "scope": "DEV_RESOURCE_SEMANTICS_PACKET_ONLY_NO_GENERATOR_NO_OUTCOME",
        "sampling": {
            "seed": seed,
            "target_N": 64,
            "actual_N": len(packet_rows),
            "rank_distribution": dict(Counter(str(row["rank"]) for row in packet_rows)),
            "family_distribution": dict(Counter(row["sampling_primary_family"] for row in packet_rows)),
            "isolation": "ESConv validation decision states; no ESC-Eval role cards read or used",
        },
        "source_identity": {
            "canonical_catalog_sha256": sha256_file(args.canonical_catalog),
            "canonical_top8_sha256": sha256_file(args.top8),
            "canonical_top8_report_sha256": sha256_file(args.top8_report),
        },
        "rubric": rubric,
        "rows": packet_rows,
        "human_judgments_completed": 0,
        "LLM_judgments_completed": 0,
        "outcome_calls": 0,
    }
    packet_path = PROJECT / "data/paper1_authority/paper1_rs_resource_semantics_qualification_packet_20260820_v1.json"
    _write(packet_path, packet)

    import inspect

    step2_code = inspect.getsource(render_step2_prompt)
    uptake = {
        "protocol": "pm-paper1-rs-treatment-uptake-qualification-protocol-v1",
        "status": "READY",
        "scope": "OFFLINE_HARNESS_AND_SCHEMA_ONLY_NO_GENERATOR_CALL",
        "isolated_pool": {
            "source": "the same ESConv validation qualification pool",
            "future_ESC_role_cards_forbidden": True,
        },
        "matched_design": {
            "OFF": "same visible state, no RS block",
            "ON": "same visible state, exactly one assigned canonical exact treatment",
            "other_optional_resources": "OFF",
            "utility_filter": False,
            "step2": "deterministic validity and typed rendering only",
        },
        "recorded_fields": [
            "exact treatment and hashes",
            "exact prompt and response hashes",
            "treatment-delivery trace",
            "intended-move reflection",
            "additional unassigned moves",
            "mechanical failure",
            "input/output tokens and latency",
        ],
        "blind_adherence_review": {
            "judges execution/adherence only": True,
            "judges quality_or_utility": False,
            "correct_delivery_then_nonuse_or_harm_is_valid_effect_later": True,
        },
        "schema_sha256": {
            model.__name__: _schema_hash(model)
            for model in (
                QualificationState,
                UptakeAssignment,
                UptakeRuntimeManifest,
                UptakeExecutionRecord,
                BlindAdherenceReview,
            )
        },
        "schemas": {
            model.__name__: model.model_json_schema()
            for model in (
                QualificationState,
                UptakeAssignment,
                UptakeRuntimeManifest,
                UptakeExecutionRecord,
                BlindAdherenceReview,
            )
        },
        "step2_render_function_sha256": sha256_text(step2_code),
        "generator_calls": 0,
        "outcome_calls": 0,
        "locks": {key: config[key]["status"] for key in config if key.endswith("OUTCOME_LOCK")},
    }
    uptake_path = PROJECT / "data/paper1_authority/paper1_rs_treatment_uptake_qualification_protocol_20260820_v1.json"
    _write(uptake_path, uptake)
    print(json.dumps({"semantics_packet": str(packet_path), "uptake_protocol": str(uptake_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
