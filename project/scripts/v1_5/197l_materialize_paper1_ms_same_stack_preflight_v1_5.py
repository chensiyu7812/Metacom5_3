#!/usr/bin/env python3
"""Materialize the frozen 68-state / 136-call MS same-stack preflight."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.pm_v1_5_semantic import semantic_snapshot_tree_sha256  # noqa: E402
from metacom_pm.v1_5_memory_realization_v2 import (  # noqa: E402
    build_joint_composition_plan,
    current_seeker_query,
    parse_raw_ms_session,
    select_ms_exact_span,
)
from metacom_pm.v1_5_memory_response_plan_v2 import (  # noqa: E402
    build_memory_response_plan,
    memory_response_generation_messages,
)
from metacom_pm.v1_5_ms_same_stack_feasibility import (  # noqa: E402
    POLICIES,
    PROTOCOL,
    SameStackGeneratorOutput,
    arm_order,
    paired_seed,
    select_fixed_states,
    stable_hex,
    validate_frozen_plan,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_same_stack_preflight_materialization_phase_v1.json"
STATES = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_public_20260810/ms_checkpoint_states_unlabeled.jsonl"
CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_public_20260810/ms_raw_session_candidates_unlabeled.jsonl"
RANK1 = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_public_20260810/ms_actual_rank1_unlabeled.jsonl"
OOF = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_final_oof_private_20260810/ms_grouped_oof_predictions.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_same_stack_preflight_20260811"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def encode_bge(snapshot: Path, texts: list[str]) -> np.ndarray:
    import torch
    from transformers import AutoModel, AutoTokenizer

    device = torch.device(
        "cuda:1" if torch.cuda.device_count() > 1
        else "cuda:0" if torch.cuda.is_available()
        else "cpu"
    )
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    model = AutoModel.from_pretrained(snapshot, local_files_only=True).to(device)
    model.eval()
    pieces = []
    with torch.inference_mode():
        for start in range(0, len(texts), 64):
            batch = tokenizer(
                texts[start : start + 64], padding=True, truncation=True,
                max_length=512, return_tensors="pt",
            )
            batch = {key: value.to(device) for key, value in batch.items()}
            vector = model(**batch).last_hidden_state[:, 0]
            pieces.append(torch.nn.functional.normalize(vector.float(), p=2, dim=1).cpu().numpy())
    return np.concatenate(pieces, axis=0)


def main() -> None:
    authority = read(AUTHORITY)
    design = authority["current_phase"]["system_feasibility_design_candidate"]
    materialization = design.get("preflight_materialization") or {}
    if materialization.get("path") != str(PHASE.relative_to(ROOT)):
        raise RuntimeError("same-stack preflight materialization phase is not authority-bound")
    if materialization.get("sha256") != sha256_file(PHASE):
        raise RuntimeError("same-stack materialization phase hash drifted")
    phase = read(PHASE)
    for binding in phase["input_bindings"] + phase["implementation_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"phase binding drifted: {binding['path']}")
    snapshot = Path(phase["local_semantic_encoder"]["snapshot_path"])
    if semantic_snapshot_tree_sha256(snapshot) != phase["local_semantic_encoder"]["snapshot_tree_sha256"]:
        raise RuntimeError("frozen BGE snapshot drifted")
    if OUT.exists():
        raise RuntimeError("preflight output already exists; refusing overwrite")

    states = rows(STATES)
    candidates = rows(CANDIDATES)
    ranks = rows(RANK1)
    oof = rows(OOF)
    candidate_by_id = {row["candidate_id"]: row for row in candidates}
    rank_by_state = {row["state_id"]: row for row in ranks if row["candidate_present"]}
    oof_by_state = {row["state_id"]: row for row in oof}
    eligible_states = [row for row in states if row["state_id"] in rank_by_state]
    selected_states = select_fixed_states(eligible_states)

    query_and_turns = []
    unique_texts = []
    for state in selected_states:
        rank = rank_by_state[state["state_id"]]
        candidate = candidate_by_id[rank["actual_rank1_id"]]
        query = current_seeker_query(state["visible_current_session_dialogue"])
        turns = parse_raw_ms_session(candidate["literal_text"])
        query_and_turns.append((state, rank, candidate, query, turns))
        unique_texts.extend((query, *turns))
    unique_texts = list(dict.fromkeys(unique_texts))
    vectors = encode_bge(snapshot, unique_texts)
    vector_by_text = dict(zip(unique_texts, vectors, strict=True))

    physical: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    for state, rank, candidate, query, turns in query_and_turns:
        query_vector = vector_by_text[query]
        scores = {turn: float(query_vector @ vector_by_text[turn]) for turn in turns}
        selected = select_ms_exact_span(candidate["literal_text"], scores)
        if selected is None:
            raise RuntimeError(f"selected feasibility state has no informative MS span: {state['state_id']}")
        evidence_id = "msx_" + stable_hex(
            state["state_id"], candidate["candidate_id"], selected.exact_span, length=24
        )
        seed = paired_seed(state["state_id"])
        decision = int(oof_by_state[state["state_id"]]["decision"])
        call_ids: dict[str, str] = {}
        contexts = state["visible_text"]
        for arm_index, arm in enumerate(arm_order(state["state_id"]), start=1):
            on = arm == "ON"
            requested_action = "MS+R0" if on else "M0+R0"
            composition = build_joint_composition_plan(
                requested_action_id=requested_action,
                realized_content={"MS": selected.exact_span} if on else {},
            )
            plan = build_memory_response_plan(
                composition=composition,
                current_goal="Respond supportively to the latest visible user message with one coherent low-burden reply.",
                current_user_id=state["runtime_owner_key"],
                evidence_ids={"MS": evidence_id} if on else {},
            )
            messages = memory_response_generation_messages(current_context=contexts, plan=plan)
            call_id = "mssf_" + stable_hex(PROTOCOL, state["state_id"], requested_action, seed, length=24)
            call_ids[requested_action] = call_id
            physical.append(
                {
                    "protocol": PROTOCOL,
                    "physical_call_id": call_id,
                    "state_id": state["state_id"],
                    "split_group_key": state["split_group_key"],
                    "runtime_owner_key": state["runtime_owner_key"],
                    "source_session_id": state["source_session_id"],
                    "source_session_index": state["source_session_index"],
                    "raw_current_turn_index": state["raw_current_turn_index"],
                    "visible_current_session_dialogue": state["visible_current_session_dialogue"],
                    "current_context": contexts,
                    "actual_rank1_id": candidate["candidate_id"],
                    "actual_rank1_source_session_id": candidate["source_session_id"],
                    "actual_rank1_session_score": rank["selection_score"],
                    "selected_exact_span": selected.exact_span if on else None,
                    "selected_exact_span_source_turn_index": selected.source_turn_index if on else None,
                    "selected_exact_span_score": selected.semantic_score if on else None,
                    "evidence_id": evidence_id if on else None,
                    "requested_action_id": requested_action,
                    "feasible_action_id": plan.feasible_action_id,
                    "arm": arm,
                    "within_state_call_order": arm_index,
                    "seed": seed,
                    "temperature": 0.7,
                    "max_output_tokens": 512,
                    "messages": messages,
                    "messages_sha256": sha256_text(canonical_json(messages)),
                    "response_schema": SameStackGeneratorOutput.model_json_schema(),
                    "response_schema_sha256": sha256_text(canonical_json(SameStackGeneratorOutput.model_json_schema())),
                    "injected_exact_span_word_count": len(selected.exact_span.split()) if on else 0,
                    "injected_exact_span_token_proxy": math.ceil(len(selected.exact_span) / 4) if on else 0,
                }
            )
        learned_action = "MS+R0" if decision else "M0+R0"
        for policy, action in (
            ("always_off", "M0+R0"),
            ("fixed_high_MS", "MS+R0"),
            ("cross_fitted_learned_MS", learned_action),
        ):
            aliases.append(
                {
                    "protocol": PROTOCOL,
                    "logical_observation_id": "msslo_" + stable_hex(state["state_id"], policy, length=24),
                    "state_id": state["state_id"],
                    "split_group_key": state["split_group_key"],
                    "policy": policy,
                    "policy_action_id": action,
                    "physical_call_id": call_ids[action],
                    "immutable_oof_decision": decision if policy == "cross_fitted_learned_MS" else None,
                }
            )

    validation = validate_frozen_plan(physical, aliases)
    extra_checks = {
        "17_groups": len({row["split_group_key"] for row in physical}) == 17,
        "exact_span_only_on": all(bool(row["selected_exact_span"]) == (row["arm"] == "ON") for row in physical),
        "span_exact_in_frozen_rank1": all(
            row["arm"] == "OFF" or row["selected_exact_span"] in candidate_by_id[row["actual_rank1_id"]]["literal_text"]
            for row in physical
        ),
        "prompt_hash_unique_per_state_action": len({row["messages_sha256"] for row in physical}) == 136,
        "learned_on_off_37_31": Counter(
            row["policy_action_id"] for row in aliases if row["policy"] == "cross_fitted_learned_MS"
        ) == Counter({"MS+R0": 37, "M0+R0": 31}),
        "raw_session_not_in_messages": all(
            candidate_by_id[row["actual_rank1_id"]]["literal_text"] not in canonical_json(row["messages"])
            for row in physical if row["arm"] == "ON"
        ),
        "labels_and_outcomes_physically_absent": all(
            not ({"label", "quality", "risk", "function", "outcome", "response_or_outcome"} & set(row))
            for row in physical
        ),
    }
    if validation["status"] != "PASS" or not all(extra_checks.values()):
        raise RuntimeError(f"same-stack preflight validation failed: {validation} {extra_checks}")

    OUT.mkdir(parents=True)
    physical_path = OUT / "physical_call_plan_private.jsonl"
    alias_path = OUT / "logical_policy_aliases_private.jsonl"
    write_jsonl(physical_path, physical)
    write_jsonl(alias_path, aliases)
    report = {
        "protocol": PROTOCOL,
        "status": "MS_SAME_STACK_PREFLIGHT_PASS_LIVE_EXECUTION_MAY_BE_SEPARATELY_AUTHORIZED",
        "validation": validation,
        "extra_checks": extra_checks,
        "counts": {
            "states": 68,
            "connected_owner_groups": 17,
            "physical_generator_calls": 136,
            "logical_policy_observations": 204,
            "learned_on": 37,
            "learned_off": 31,
            "on_first_states": sum(row["arm"] == "ON" and row["within_state_call_order"] == 1 for row in physical),
            "off_first_states": sum(row["arm"] == "OFF" and row["within_state_call_order"] == 1 for row in physical),
        },
        "generator": {
            "config": "configs/experiment.yaml:endpoints.generator",
            "model": "meta/llama-3.1-8b-instruct",
            "temperature": 0.7,
            "paired_seed_per_state": 1,
            "maximum_transport_attempts": 2,
            "semantic_rewrite_attempts": 0,
            "raw_provider_output_persisted_before_guard": True,
        },
        "artifacts": {
            "physical": {"path": str(physical_path.relative_to(ROOT)), "sha256": sha256_file(physical_path)},
            "aliases": {"path": str(alias_path.relative_to(ROOT)), "sha256": sha256_file(alias_path)},
        },
        "source_hashes": {name: sha256_file(path) for name, path in {
            "authority": AUTHORITY, "phase": PHASE, "states": STATES,
            "candidates": CANDIDATES, "rank1": RANK1, "oof": OOF,
        }.items()},
        "api_calls": 0,
        "PM_refit_or_threshold_change": False,
        "labels_or_response_outcomes_read": False,
        "live_execution_allowed_by_this_report": False,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
