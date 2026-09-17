#!/usr/bin/env python3
"""Freeze the outcome-blind 80-pair / 96-presentation teacher preflight.

This script selects only from runtime-visible text and frozen retrieval
identities.  It does not call a Generator or evaluator and does not inspect
gold/reference fields until *after* the target identities have been selected.
The ON amounts are qualification probes spanning low/middle/high values, not
the later resource-amount calibration decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, iter_jsonl, read_json, sha256_file, sha256_text, stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.paper1.candidates import compile_multi_view_candidate_bundle  # noqa: E402
from metacom_pm.paper1.contracts import CandidateLineage, CandidateRecord, Head, TaskType  # noqa: E402
from metacom_pm.paper1.data.memory_source import enumerate_targets, load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.execution import GeneratorMessage, build_esc_supporter_request, build_static_rq2_request  # noqa: E402
from metacom_pm.paper1.execution.dg_official import build_official_dg_seeker_system_prompt, official_dg_seeker_messages  # noqa: E402
from metacom_pm.paper1.execution.packing import RankedCandidate, pack_ranked_prefix  # noqa: E402
from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256, build_llama_token_counter  # noqa: E402
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.rs.zero_outcome_census import build_rs_decision_states  # noqa: E402


PROTOCOL = "paper1-pairwise-teacher-base-pair-preflight-v1"
SEED = "paper1-pairwise-teacher-80-base-20260904-v1"
PROBE_K = (1, 2, 4)
TASK_BASE = {"ESC": 27, "QA": 13, "Summary": 13, "DG": 27}
TASK_REVERSE = {"ESC": 5, "QA": 3, "Summary": 3, "DG": 5}
MEMORY_HEADS = (Head.MP, Head.ME, Head.MS)


def _openai_chat_input_token_estimate(messages: tuple[dict[str, str], ...]) -> int:
    """Conservative, reproducible chat-framing estimate for budget reservation."""

    import tiktoken

    encoder = tiktoken.encoding_for_model("gpt-4o-2024-11-20")
    return sum(4 + len(encoder.encode(message.get("content", ""))) for message in messages) + 2


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=PROJECT / "data/paper1_authority")
    return parser.parse_args()


def _length_bin(value: str) -> str:
    n = len(value.split())
    return "short" if n < 12 else "medium" if n < 32 else "long"


def _request_payload(request: Any) -> dict[str, Any]:
    return request.model_dump(mode="json")


def _rs_candidate(row: dict[str, Any], *, token_counter) -> CandidateRecord:
    content = str(row["rendered_card_text"])
    return CandidateRecord(
        candidate_id=str(row["treatment_id"]),
        head=Head.RS,
        content=content,
        token_count=token_counter(content),
        lineage=CandidateLineage(
            source="paper1_public_rs_exact_canonical_treatment_v1",
            owner_id="public_rs_catalog",
            source_record_ids=tuple(
                [str(row["treatment_id"])]
                + [str(value) for value in row["atomic_card_ids"]]
            ),
            strict_past=None,
            content_sha256=sha256_text(content),
        ),
        raw_descriptors={
            "families": ",".join(str(value) for value in row["atomic_move_families"])
        },
    )


def _visible_messages(state: Any) -> tuple[GeneratorMessage, ...]:
    messages = []
    for line in state.visible_dialogue_text.splitlines():
        role, separator, content = line.partition(": ")
        if not separator or role not in {"seeker", "supporter"} or not content:
            raise RuntimeError(f"cannot project ESConv visible turn: {line!r}")
        messages.append(
            GeneratorMessage(
                role="user" if role == "seeker" else "assistant", content=content
            )
        )
    return tuple(messages)


def _choose_balanced(
    candidates: list[Any],
    *,
    n: int,
    identity,
    group,
    owner,
    stratum,
    seed: str,
) -> list[Any]:
    selected: list[Any] = []
    remaining = list(candidates)
    used_groups: set[str] = set()
    owner_counts: Counter[str] = Counter()
    stratum_counts: Counter[str] = Counter()
    while len(selected) < n:
        eligible = [row for row in remaining if group(row) not in used_groups]
        if not eligible:
            raise RuntimeError(f"only {len(selected)} distinct groups available for n={n}")
        chosen = min(
            eligible,
            key=lambda row: (
                owner_counts[owner(row)],
                stratum_counts[stratum(row)],
                stable_hex(seed, identity(row), n=32),
            ),
        )
        selected.append(chosen)
        remaining.remove(chosen)
        used_groups.add(group(chosen))
        owner_counts[owner(chosen)] += 1
        stratum_counts[stratum(chosen)] += 1
    return selected


def _slots(counts: dict[Head, int]) -> list[tuple[Head, int]]:
    rows: list[tuple[Head, int]] = []
    for head, count in counts.items():
        for index in range(count):
            rows.append((head, PROBE_K[index % len(PROBE_K)]))
    return rows


def _raw_reference_lookup(raw_users: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    qa: dict[str, str] = {}
    summary: dict[str, str] = {}
    dg: dict[str, str] = {}
    for user in raw_users:
        owner = str(user["id"])
        for group in user["questions"]:
            for item in group["questions"]:
                qa[f"{owner}::{group['id']}::{item['idx']}"] = str(item["answer"])
        for item in user["summaries"]:
            summary[f"{owner}::summary::{item['idx']}"] = str(item["answer"])
        sessions = {str(row["id"]): row for row in user["dialog_history"]}
        for topic in user["subsequent_topics"]:
            related = [sessions[str(value)] for value in topic["related_sessions"]]
            dg[f"{owner}::dg::{topic['idx']}"] = "\n\n".join(
                "Prior session [" + str(session["timestamp"]) + "]:\n" + "\n".join(
                    f"{turn['role']}: {turn['content']}" for turn in session["dialogue"]
                )
                for session in related
            )
    return qa, summary, dg


def main() -> int:
    args = _args()
    assert_pre_outcome_locked(load_public_only_config(PROJECT / "configs/paper1_public_only.yaml"))
    if sha256_file(args.tokenizer_json) != LLAMA_TOKENIZER_JSON_SHA256:
        raise RuntimeError("frozen Generator tokenizer hash mismatch")
    token_counter = build_llama_token_counter(args.tokenizer_json)

    esconv = PROJECT / "data/external/ESConv.json"
    splits = PROJECT / "data/strategy/esconv_split_manifest_v1_5.jsonl"
    rs_top8_path = PROJECT / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_v1.jsonl"
    treatments_path = PROJECT / "data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl"
    natural_path = PROJECT / "data/paper1_public_memory/paper1_natural_turn_base_sample_proposal_v1.jsonl"
    old_rs_key = PROJECT / "data/paper1_authority/paper1_rs_resource_semantics_blind_key_20260820_v1.json"
    memory_source = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
    session_results = PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl"
    memory_top8_path = PROJECT / "data/paper1_public_memory/es_memeval_public_active_multi_view_bge_top8_v1.jsonl"
    raw_memory = PROJECT / "data/external/evo_emo.json"

    # ESC / RS: choose before reading any target response or quality field.
    rs_states = {row.state_id: row for row in build_rs_decision_states(esconv_path=esconv, split_manifest_path=splits)}
    rs_top8 = {str(row["state_id"]): row for row in iter_jsonl(rs_top8_path)}
    treatment_rows = {str(row["treatment_id"]): row for row in iter_jsonl(treatments_path)}
    natural_ids = {str(row["source_state_id"]) for row in iter_jsonl(natural_path) if row["head"] == "RS"}
    prior_review_dialogues = {str(row["source_dialogue_id"]) for row in read_json(old_rs_key)["rows"]}
    rs_frame = [
        state for state_id, state in rs_states.items()
        if state_id in rs_top8
        and state_id not in natural_ids
        and state.source_dialogue_id not in prior_review_dialogues
    ]
    selected_rs = _choose_balanced(
        rs_frame,
        n=TASK_BASE["ESC"],
        identity=lambda row: row.state_id,
        group=lambda row: row.source_dialogue_id,
        owner=lambda row: row.source_split,
        stratum=lambda row: _length_bin(row.current_user_text),
        seed=SEED + "|ESC",
    )

    base_rows: list[dict[str, Any]] = []
    for index, state in enumerate(selected_rs):
        k = PROBE_K[index % len(PROBE_K)]
        ranked = tuple(
            RankedCandidate(
                candidate=_rs_candidate(treatment_rows[item["treatment_id"]], token_counter=token_counter),
                similarity=float(item["cosine_similarity"]),
            )
            for item in rs_top8[state.state_id]["ranked_treatments"]
        )
        packed = pack_ranked_prefix(head=Head.RS, ranked=ranked, k=k, target_owner_id=None, token_counter=token_counter)
        turns = _visible_messages(state)
        off = build_esc_supporter_request(visible_turns=turns)
        on = build_esc_supporter_request(visible_turns=turns, resource=packed.envelope)
        base_rows.append({
            "protocol": PROTOCOL,
            "base_pair_id": "teacher_base_" + stable_hex(SEED, "ESC", state.state_id, Head.RS.value, k, n=24),
            "task": "ESC",
            "target_id": state.state_id,
            "primary_group_key": state.source_dialogue_id,
            "owner_or_dialogue_group": state.source_dialogue_id,
            "head": Head.RS.value,
            "qualification_probe_k": k,
            "qualification_probe_is_final_amount": False,
            "task_input": state.visible_dialogue_text,
            "reference_material": None,
            "off_request": _request_payload(off),
            "on_request": _request_payload(on),
            "dg_seeker_request": None,
            "responses_generated": False,
            "effect_or_capability_outcome_read_for_sampling": False,
        })

    # Static QA/Summary: compile current candidates and bind frozen Top8.
    users = load_sanitized_runtime_users(memory_source)
    targets = enumerate_targets(users)
    user_by_id = {user.owner_id: user for user in users}
    targets_by_owner: dict[str, list[Any]] = defaultdict(list)
    for target in targets:
        targets_by_owner[target.owner_id].append(target)
    units = load_accepted_multi_view_units(session_results, users=users)
    units_by_owner: dict[str, list[Any]] = defaultdict(list)
    for unit in units:
        units_by_owner[unit.owner_id].append(unit)
    bundles = {
        user.owner_id: compile_multi_view_candidate_bundle(
            tuple(units_by_owner[user.owner_id]), user, targets_by_owner[user.owner_id][0], token_counter=token_counter
        )
        for user in users
    }
    by_id = {
        (owner, head, candidate.candidate_id): candidate
        for owner, bundle in bundles.items()
        for head, candidates in bundle.items()
        for candidate in candidates
    }
    memory_top8 = {
        (str(row["target_id"]), Head(row["head"])): row
        for row in iter_jsonl(memory_top8_path)
    }

    static_allocations = {
        "QA": _slots({Head.MP: 5, Head.ME: 4, Head.MS: 4}),
        "Summary": _slots({Head.MP: 4, Head.ME: 5, Head.MS: 4}),
    }
    selected_static: dict[str, list[tuple[Any, Head, int]]] = {}
    for task_name, task_type in (("QA", TaskType.QA), ("Summary", TaskType.SUMMARY)):
        task_targets = [target for target in targets if target.task_type is task_type and target.visible_query_text]
        chosen: list[tuple[Any, Head, int]] = []
        used_targets: set[str] = set()
        used_groups: set[str] = set()
        owner_counts: Counter[str] = Counter()
        length_counts: Counter[str] = Counter()
        for slot_index, (head, k) in enumerate(static_allocations[task_name]):
            eligible = [
                target for target in task_targets
                if target.target_id not in used_targets
                and target.primary_group_key not in used_groups
                and (target.target_id, head) in memory_top8
            ]
            target = min(
                eligible,
                key=lambda row: (
                    owner_counts[row.owner_id],
                    length_counts[_length_bin(row.visible_query_text or "")],
                    stable_hex(SEED, task_name, slot_index, head.value, k, row.target_id, n=32),
                ),
            )
            chosen.append((target, head, k))
            used_targets.add(target.target_id)
            used_groups.add(target.primary_group_key)
            owner_counts[target.owner_id] += 1
            length_counts[_length_bin(target.visible_query_text or "")] += 1
        selected_static[task_name] = chosen

    # Only after target identity freeze above, expose scorer-side references.
    raw_users = json.loads(raw_memory.read_text(encoding="utf-8"))
    qa_reference, summary_reference, dg_reference = _raw_reference_lookup(raw_users)
    for task_name, rows in selected_static.items():
        for target, head, k in rows:
            ranked = tuple(
                RankedCandidate(
                    candidate=by_id[(target.owner_id, head, item["candidate_id"])],
                    similarity=float(item["bge_cosine_similarity"]),
                )
                for item in memory_top8[(target.target_id, head)]["ranked_candidates"]
            )
            packed = pack_ranked_prefix(
                head=head, ranked=ranked, k=k, target_owner_id=target.owner_id, token_counter=token_counter
            )
            off = build_static_rq2_request(task_type=target.task_type, question=target.visible_query_text or "")
            on = build_static_rq2_request(task_type=target.task_type, question=target.visible_query_text or "", resources=(packed.envelope,))
            references = qa_reference if task_name == "QA" else summary_reference
            base_rows.append({
                "protocol": PROTOCOL,
                "base_pair_id": "teacher_base_" + stable_hex(SEED, task_name, target.target_id, head.value, k, n=24),
                "task": task_name,
                "target_id": target.target_id,
                "primary_group_key": target.primary_group_key,
                "owner_or_dialogue_group": target.owner_id,
                "head": head.value,
                "qualification_probe_k": k,
                "qualification_probe_is_final_amount": False,
                "task_input": target.visible_query_text,
                "reference_material": references[target.target_id],
                "off_request": _request_payload(off),
                "on_request": _request_payload(on),
                "dg_seeker_request": None,
                "responses_generated": False,
                "effect_or_capability_outcome_read_for_sampling": False,
            })

    # DG: nine scenario clusters, each shared across MP/ME/MS.  This gives 27
    # base pairs while holding the seeker utterance and OFF response fixed
    # within a scenario.  p7::dg::1 is reused from the already-completed,
    # identity-matched compatibility pilot; selection is based on cached
    # availability, never the trajectory's response quality.
    dg_targets = [target for target in targets if target.task_type is TaskType.DIALOGUE_GENERATION]
    cached_target = next(target for target in dg_targets if target.target_id == "p7::dg::1")
    selected_dg = [cached_target] + _choose_balanced(
        [target for target in dg_targets if target.target_id != cached_target.target_id],
        n=8,
        identity=lambda row: row.target_id,
        group=lambda row: row.primary_group_key,
        owner=lambda row: row.owner_id,
        stratum=lambda row: "scenario",
        seed=SEED + "|DG",
    )
    raw_by_owner = {str(user["id"]): user for user in raw_users}
    dg_pending_call_estimates: list[dict[str, Any]] = []
    for scenario_index, target in enumerate(selected_dg):
        raw_user = raw_by_owner[target.owner_id]
        topic_idx = int(target.target_id.rsplit("::", 1)[1])
        topic = next(row for row in raw_user["subsequent_topics"] if int(row["idx"]) == topic_idx)
        system = build_official_dg_seeker_system_prompt(user=raw_user, topic=topic)
        greeting = f"Hi {raw_user['basic_info']['name']}! How are you these days?"
        seeker_messages = official_dg_seeker_messages(system_prompt=system, first_supporter_message=greeting, prior_turns=())
        if target.target_id != "p7::dg::1":
            dg_pending_call_estimates.append({
                "target_id": target.target_id,
                "request_messages_sha256": sha256_text(canonical_json(seeker_messages)),
                "estimated_input_tokens": _openai_chat_input_token_estimate(seeker_messages),
                "maximum_output_tokens": 60,
            })
        for head_index, head in enumerate(MEMORY_HEADS):
            k = PROBE_K[(scenario_index + head_index) % len(PROBE_K)]
            base_rows.append({
                "protocol": PROTOCOL,
                "base_pair_id": "teacher_base_" + stable_hex(SEED, "DG", target.target_id, head.value, k, n=24),
                "task": "DG",
                "target_id": target.target_id,
                "primary_group_key": target.primary_group_key,
                "owner_or_dialogue_group": target.owner_id,
                "head": head.value,
                "qualification_probe_k": k,
                "qualification_probe_is_final_amount": False,
                "task_input": None,
                "reference_material": dg_reference[target.target_id],
                "off_request": None,
                "on_request": None,
                "dg_seeker_request": {
                    "provider": "OpenAI",
                    "model": "gpt-4o-2024-11-20",
                    "temperature": "provider_default_omitted",
                    "max_completion_tokens": 60,
                    "messages_reconstructed_from_pinned_raw_source": True,
                    "request_messages_sha256": sha256_text(canonical_json(seeker_messages)),
                    "hidden_scenario_for_seeker_only": True,
                    "supporter_or_pm_may_read_this_request": False,
                    "existing_success_reused": target.target_id == "p7::dg::1",
                },
                "responses_generated": False,
                "effect_or_capability_outcome_read_for_sampling": False,
            })

    if Counter(row["task"] for row in base_rows) != Counter(TASK_BASE):
        raise RuntimeError("base-pair task allocation drifted")
    if len(base_rows) != 80 or len({row["base_pair_id"] for row in base_rows}) != 80:
        raise RuntimeError("teacher base-pair identity is not exactly 80 unique rows")

    presentation_rows: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for task in TASK_BASE:
        task_rows = [row for row in base_rows if row["task"] == task]
        reverse_ids = {
            row["base_pair_id"]
            for row in sorted(task_rows, key=lambda row: stable_hex(SEED, "reverse", row["base_pair_id"], n=32))[:TASK_REVERSE[task]]
        }
        for row in task_rows:
            primary_a = "ON" if int(stable_hex(SEED, "side", row["base_pair_id"], n=2), 16) % 2 else "OFF"
            for reverse in (False, True) if row["base_pair_id"] in reverse_ids else (False,):
                a_arm = ("OFF" if primary_a == "ON" else "ON") if reverse else primary_a
                b_arm = "OFF" if a_arm == "ON" else "ON"
                presentation_id = "teacher_present_" + stable_hex(SEED, row["base_pair_id"], "reverse" if reverse else "primary", n=24)
                presentation_rows.append({
                    "protocol": "paper1-pairwise-teacher-presentation-plan-v1",
                    "presentation_id": presentation_id,
                    "base_pair_id": row["base_pair_id"],
                    "task": task,
                    "reverse_duplicate": reverse,
                    "response_A": None,
                    "response_B": None,
                    "human_verdict": None,
                    "human_rationale": None,
                })
                key_rows.append({
                    "protocol": "paper1-pairwise-teacher-blind-key-v1",
                    "presentation_id": presentation_id,
                    "base_pair_id": row["base_pair_id"],
                    "A_arm": a_arm,
                    "B_arm": b_arm,
                    "reverse_duplicate": reverse,
                })
    presentation_rows.sort(key=lambda row: stable_hex(SEED, "presentation-order", row["presentation_id"], n=32))
    key_rows.sort(key=lambda row: row["presentation_id"])
    if len(presentation_rows) != 96 or sum(row["reverse_duplicate"] for row in presentation_rows) != 16:
        raise RuntimeError("teacher presentation denominator drifted")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    base_path = args.out_dir / "paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl"
    presentation_path = args.out_dir / "paper1_pairwise_teacher_presentation_plan_20260904_v1.jsonl"
    key_path = args.out_dir / "paper1_pairwise_teacher_blind_key_20260904_v1.jsonl"
    summary_path = args.out_dir / "paper1_pairwise_teacher_preflight_20260904_v1.json"
    write_jsonl(base_path, base_rows)
    write_jsonl(presentation_path, presentation_rows)
    write_jsonl(key_path, key_rows)
    dg_pending_input_tokens = sum(row["estimated_input_tokens"] for row in dg_pending_call_estimates)
    dg_pending_output_tokens = sum(row["maximum_output_tokens"] for row in dg_pending_call_estimates)
    dg_budget_usd = (
        dg_pending_input_tokens * 2.50 / 1_000_000
        + dg_pending_output_tokens * 10.00 / 1_000_000
    )
    summary = {
        "protocol": PROTOCOL,
        "status": "ZERO_OUTCOME_PREFLIGHT_READY_DG_SEEKER_AND_LOCAL_RESPONSES_NOT_RUN",
        "sampling_seed_sha256": sha256_text(SEED),
        "base_semantic_pairs": len(base_rows),
        "base_by_task": dict(sorted(Counter(row["task"] for row in base_rows).items())),
        "base_by_head": dict(sorted(Counter(row["head"] for row in base_rows).items())),
        "probe_k_by_task": {
            task: dict(sorted(Counter(str(row["qualification_probe_k"]) for row in base_rows if row["task"] == task).items()))
            for task in TASK_BASE
        },
        "presentations": len(presentation_rows),
        "reverse_presentations": sum(row["reverse_duplicate"] for row in presentation_rows),
        "independent_primary_raters": 2,
        "primary_rater_pair_judgements_after_completion": 192,
        "selection_fields": "runtime-visible task/head/query length/group plus frozen retrieval identities only",
        "reference_loaded_only_after_target_identity_selection": True,
        "qualification_probe_k_is_not_final_resource_amount": True,
        "dg_scenario_clusters": 9,
        "dg_existing_first_turn_seeker_success_reused": 1,
        "dg_first_turn_seeker_calls_pending": 8,
        "dg_first_turn_seeker_budget": {
            "physical_attempts_per_logical_turn": 1,
            "estimated_input_tokens": dg_pending_input_tokens,
            "maximum_output_tokens": dg_pending_output_tokens,
            "input_usd_per_million_tokens": 2.50,
            "output_usd_per_million_tokens": 10.00,
            "worst_case_estimated_usd": round(dg_budget_usd, 8),
            "authorization_ceiling_usd": 0.11,
            "paid_calls_authorized": False,
            "token_estimator": "sum(4 + encoded_content_tokens_per_message) + 2",
            "tiktoken_version": package_version("tiktoken"),
            "official_pricing_url": "https://developers.openai.com/api/docs/models/gpt-4o",
            "calls": dg_pending_call_estimates,
        },
        "local_generator_outputs_pending": 142,
        "local_generator_output_accounting": "ESC 54 + QA 26 + Summary 26 + DG 9 shared OFF plus 27 head-specific ON",
        "reverse_duplicates_require_new_generation": 0,
        "paid_api_calls": 0,
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "artifacts": {
            base_path.name: {"rows": 80, "sha256": sha256_file(base_path)},
            presentation_path.name: {"rows": 96, "sha256": sha256_file(presentation_path)},
            key_path.name: {"rows": 96, "sha256": sha256_file(key_path)},
        },
        "source_sha256": {
            "ESConv.json": sha256_file(esconv),
            "ES-MemEval-sanitized": sha256_file(memory_source),
            "ES-MemEval-raw": sha256_file(raw_memory),
            "RS-Top8": sha256_file(rs_top8_path),
            "Multi-View-Top8": sha256_file(memory_top8_path),
            "Multi-View-session-results": sha256_file(session_results),
            "Generator-tokenizer": sha256_file(args.tokenizer_json),
        },
        "next_step": "authorize at most 8 frozen GPT-4o first-turn seeker calls; then bind dynamic DG retrieval and generate 142 local A6000 outputs without inspecting quality",
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
