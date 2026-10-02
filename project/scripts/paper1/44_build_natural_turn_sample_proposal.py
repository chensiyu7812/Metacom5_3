#!/usr/bin/env python3
"""Build a public-only, zero-outcome Natural-turn sample proposal.

The proposal contains visible prefixes ending at a seeker turn, never the
target supporter response.  RS uses ordinary ESConv train/validation
dialogues outside the EvoEmo overlap and prior RS resource-review dialogues.
Memory uses ordinary EvoEmo historical-session response opportunities with
at least one complete strictly-past candidate for MP, ME and MS.  Sampling
strata are mechanical properties of runtime-visible text and candidate
availability, never gold capability or effect labels.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import read_json, sha256_file, sha256_text, stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.paper1.candidates import compile_multi_view_candidate_bundle  # noqa: E402
from metacom_pm.paper1.contracts import Head, TaskType  # noqa: E402
from metacom_pm.paper1.data.memory_source import Target, load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.llama_tokenizer import (  # noqa: E402
    LLAMA_TOKENIZER_JSON_SHA256,
    build_llama_token_counter,
)
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.rs.zero_outcome_census import build_rs_decision_states  # noqa: E402


PROTOCOL = "paper1-natural-turn-zero-outcome-sample-proposal-v1"
BASE_PER_HEAD = 20
REVERSE_PER_HEAD = 4
HEADS = (Head.RS, Head.MP, Head.ME, Head.MS)
_MEMORY_CUE = re.compile(r"\b(?:remember|mentioned|told you|last time|before|earlier)\b", re.I)
_ADVICE_CUE = re.compile(
    r"\b(?:what should i do|what can i do|any advice|how (?:do|can|should) i|suggest|recommend)\b",
    re.I,
)
_SOCIAL_CUE = re.compile(r"^\s*(?:hi|hello|hey|thanks?|thank you|bye|good ?night)\b", re.I)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument(
        "--esconv",
        type=Path,
        default=PROJECT / "data/external/ESConv.json",
    )
    parser.add_argument(
        "--esconv-splits",
        type=Path,
        default=PROJECT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    parser.add_argument(
        "--memory-source",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
    )
    parser.add_argument(
        "--session-results",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl",
    )
    parser.add_argument(
        "--candidate-census-summary",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_candidate_census_summary_v1.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT / "data/paper1_public_memory",
    )
    return parser.parse_args()


def _length_bin(tokens: int) -> str:
    if tokens < 16:
        return "short_lt16"
    if tokens < 48:
        return "medium_16_47"
    return "long_ge48"


def _depth_bin(turns: int) -> str:
    if turns < 4:
        return "early_lt4"
    if turns < 10:
        return "middle_4_9"
    return "late_ge10"


def _turn_type(text: str) -> str:
    if _MEMORY_CUE.search(text):
        return "explicit_memory_cue"
    if _ADVICE_CUE.search(text):
        return "advice_request_cue"
    if _SOCIAL_CUE.search(text):
        return "greeting_or_closing_cue"
    if "?" in text:
        return "other_question"
    return "statement"


def _balanced_select(
    rows: list[dict[str, Any]],
    *,
    n: int,
    seed: str,
    group_field: str,
    session_field: str,
) -> list[dict[str, Any]]:
    if len(rows) < n:
        raise RuntimeError(f"sampling frame has only {len(rows)} rows for requested n={n}")
    remaining = list(rows)
    selected: list[dict[str, Any]] = []
    group_counts: Counter[str] = Counter()
    session_counts: Counter[str] = Counter()
    stratum_counts: Counter[tuple[str, str, str]] = Counter()
    while len(selected) < n:
        eligible = [row for row in remaining if session_counts[row[session_field]] == 0]
        if not eligible:
            raise RuntimeError("not enough distinct source sessions/dialogues for sample")
        chosen = min(
            eligible,
            key=lambda row: (
                group_counts[row[group_field]],
                stratum_counts[
                    (row["turn_type"], row["current_user_length_bin"], row["turn_depth_bin"])
                ],
                stable_hex(seed, row["source_state_id"], n=32),
            ),
        )
        selected.append(chosen)
        remaining.remove(chosen)
        group_counts[chosen[group_field]] += 1
        session_counts[chosen[session_field]] += 1
        stratum_counts[
            (chosen["turn_type"], chosen["current_user_length_bin"], chosen["turn_depth_bin"])
        ] += 1
    return selected


def _rs_frame(*, args: argparse.Namespace, token_counter) -> list[dict[str, Any]]:
    review_key = read_json(
        PROJECT
        / "data/paper1_authority/paper1_rs_resource_semantics_blind_key_20260820_v1.json"
    )
    reviewed_dialogues = {row["source_dialogue_id"] for row in review_key["rows"]}
    states = build_rs_decision_states(
        esconv_path=args.esconv,
        split_manifest_path=args.esconv_splits,
        source_splits=("train", "validation"),
        exclude_evoemo_overlap=True,
    )
    rows = []
    for state in states:
        if state.source_dialogue_id in reviewed_dialogues:
            continue
        current_tokens = token_counter(state.current_user_text)
        rows.append(
            {
                "source_state_id": state.state_id,
                "source_lane": "public_ESConv_ordinary_response_opportunity",
                "source_group_id": state.source_dialogue_id,
                "source_session_id": state.source_dialogue_id,
                "source_split": state.source_split,
                "visible_context": state.visible_dialogue_text,
                "pm_query_text": state.query_text,
                "current_user_text": state.current_user_text,
                "visible_turn_count": state.visible_turn_count,
                "current_user_tokens": current_tokens,
                "current_user_length_bin": _length_bin(current_tokens),
                "turn_depth_bin": _depth_bin(state.visible_turn_count),
                "turn_type": _turn_type(state.current_user_text),
                "strict_past_candidate_counts": None,
                "target_supporter_response_included": False,
            }
        )
    return rows


def _render_memory_prefix(session, turn_index: int) -> tuple[str, str, int]:
    visible = session.turns[:turn_index]
    if not visible or visible[-1].role != "seeker":
        raise ValueError("memory natural-turn prefix must end at a seeker turn")
    current = []
    for turn in reversed(visible):
        if turn.role != "seeker":
            break
        current.append(turn.content)
    current.reverse()
    return (
        "\n".join(f"{turn.role}: {turn.content}" for turn in visible),
        "\n".join(current),
        len(visible),
    )


def _memory_frame(*, args: argparse.Namespace, token_counter) -> list[dict[str, Any]]:
    users = load_sanitized_runtime_users(args.memory_source)
    census = read_json(args.candidate_census_summary)
    if sha256_file(args.session_results) != census["source"]["promoted_session_results_sha256"]:
        raise RuntimeError("active Multi-View session artifact hash mismatch")
    units = load_accepted_multi_view_units(args.session_results, users=users)
    units_by_owner: dict[str, list[Any]] = defaultdict(list)
    for unit in units:
        units_by_owner[unit.owner_id].append(unit)

    rows: list[dict[str, Any]] = []
    for user in users:
        for session in user.sessions:
            if session.chronological_rank < 1:
                continue
            target = Target(
                target_id=f"natural::{user.owner_id}::{session.session_id}",
                task_type=TaskType.DIALOGUE_GENERATION,
                owner_id=user.owner_id,
                primary_group_key=f"natural::{user.owner_id}",
                cutoff_rank=session.chronological_rank,
                visible_query_text=None,
            )
            bundle = compile_multi_view_candidate_bundle(
                tuple(units_by_owner[user.owner_id]),
                user,
                target,
                token_counter=token_counter,
            )
            counts = {head.value: len(bundle[head]) for head in (Head.MP, Head.ME, Head.MS)}
            if not all(counts.values()):
                continue
            for turn_index, turn in enumerate(session.turns):
                if turn.role != "supporter" or not turn.content.strip():
                    continue
                if turn_index == 0 or session.turns[turn_index - 1].role != "seeker":
                    continue
                visible_context, current_user, visible_turns = _render_memory_prefix(
                    session, turn_index
                )
                current_tokens = token_counter(current_user)
                state_id = "memory_natural_" + stable_hex(
                    user.owner_id,
                    session.session_id,
                    turn_index,
                    sha256_text(visible_context),
                    n=24,
                )
                rows.append(
                    {
                        "source_state_id": state_id,
                        "source_lane": "public_EvoEmo_ordinary_historical_session_response_opportunity",
                        "source_group_id": user.owner_id,
                        "source_session_id": f"{user.owner_id}::{session.session_id}",
                        "source_split": "public_evoemo_history",
                        "visible_context": visible_context,
                        "pm_query_text": current_user,
                        "current_user_text": current_user,
                        "visible_turn_count": visible_turns,
                        "current_user_tokens": current_tokens,
                        "current_user_length_bin": _length_bin(current_tokens),
                        "turn_depth_bin": _depth_bin(visible_turns),
                        "turn_type": _turn_type(current_user),
                        "strict_past_candidate_counts": counts,
                        "strict_past_cutoff_rank": session.chronological_rank,
                        "target_supporter_response_included": False,
                    }
                )
    return rows


def _count(rows: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row[field]) for row in rows).items()))


def main() -> int:
    args = _args()
    assert_pre_outcome_locked(
        load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    )
    if sha256_file(args.tokenizer_json) != LLAMA_TOKENIZER_JSON_SHA256:
        raise RuntimeError("Generator tokenizer hash mismatch")
    token_counter = build_llama_token_counter(args.tokenizer_json)
    seed = sha256_text(
        "|".join(
            (
                PROTOCOL,
                sha256_file(PROJECT / "data/paper1_authority/paper1_natural_turn_appropriateness_rubric_v1.json"),
                sha256_file(args.esconv),
                sha256_file(args.memory_source),
                sha256_file(args.session_results),
            )
        )
    )

    rs_frame = _rs_frame(args=args, token_counter=token_counter)
    memory_frame = _memory_frame(args=args, token_counter=token_counter)
    rs_selected = _balanced_select(
        rs_frame,
        n=BASE_PER_HEAD,
        seed=f"{seed}:RS",
        group_field="source_group_id",
        session_field="source_session_id",
    )
    memory_selected = _balanced_select(
        memory_frame,
        n=BASE_PER_HEAD,
        seed=f"{seed}:MEMORY_SHARED",
        group_field="source_group_id",
        session_field="source_session_id",
    )

    base_rows = []
    for head in HEADS:
        selected = rs_selected if head is Head.RS else memory_selected
        for state in selected:
            base_item_id = "natural_base_" + stable_hex(
                PROTOCOL, head.value, state["source_state_id"], n=24
            )
            base_rows.append(
                {
                    "protocol": PROTOCOL,
                    "proposal_status": "ZERO_OUTCOME_PROPOSAL_RESEARCHER_REVIEW_REQUIRED",
                    "base_item_id": base_item_id,
                    "head": head.value,
                    **state,
                    "sampling_seed_sha256": seed,
                    "effect_or_capability_outcome_read": False,
                    "paid_api_calls": 0,
                }
            )

    review_rows = []
    for head in HEADS:
        head_rows = [row for row in base_rows if row["head"] == head.value]
        reverse_ids = {
            row["base_item_id"]
            for row in sorted(
                head_rows,
                key=lambda row: stable_hex(seed, "reverse", row["base_item_id"], n=32),
            )[:REVERSE_PER_HEAD]
        }
        for row in head_rows:
            pair_group = "natural_pair_" + stable_hex(row["base_item_id"], n=24)
            review_rows.append(
                {
                    "protocol": "paper1-natural-turn-review-slot-plan-v1",
                    "review_slot_id": "natural_review_" + stable_hex(pair_group, "primary", n=24),
                    "base_item_id": row["base_item_id"],
                    "pair_group_id": pair_group,
                    "reverse_duplicate": False,
                    "response_A": None,
                    "response_B": None,
                    "verdict": None,
                    "rationale": None,
                }
            )
            if row["base_item_id"] in reverse_ids:
                review_rows.append(
                    {
                        "protocol": "paper1-natural-turn-review-slot-plan-v1",
                        "review_slot_id": "natural_review_" + stable_hex(pair_group, "reverse", n=24),
                        "base_item_id": row["base_item_id"],
                        "pair_group_id": pair_group,
                        "reverse_duplicate": True,
                        "response_A": None,
                        "response_B": None,
                        "verdict": None,
                        "rationale": None,
                    }
                )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    base_path = args.out_dir / "paper1_natural_turn_base_sample_proposal_v1.jsonl"
    review_path = args.out_dir / "paper1_natural_turn_review_slot_plan_v1.jsonl"
    write_jsonl(base_path, base_rows)
    write_jsonl(review_path, review_rows)
    summary = {
        "protocol": "paper1-natural-turn-sample-proposal-summary-v1",
        "status": "ZERO_OUTCOME_SAMPLE_PROPOSAL_READY_RESEARCHER_REVIEW_REQUIRED",
        "sampling_protocol": PROTOCOL,
        "sampling_seed_sha256": seed,
        "base_pairs": len(base_rows),
        "base_pairs_per_head": BASE_PER_HEAD,
        "review_slots": len(review_rows),
        "reverse_duplicates": sum(row["reverse_duplicate"] for row in review_rows),
        "reverse_fraction_of_base": REVERSE_PER_HEAD / BASE_PER_HEAD,
        "memory_states_shared_across_MP_ME_MS": True,
        "future_generator_call_efficiency": (
            "one OFF response may be reused across MP/ME/MS only when the exact state, "
            "prompt, decoding and seed identity are identical"
        ),
        "future_generation_plan_not_authorized": {
            "RS_OFF_plus_ON": 40,
            "memory_shared_OFF": 20,
            "memory_head_specific_ON": 60,
            "total_logical_generator_outputs": 120,
            "reverse_duplicates_require_new_generation": 0,
            "paid_judge_calls": 0,
        },
        "frame": {
            "RS_states": len(rs_frame),
            "memory_states_with_all_three_strict_past_heads": len(memory_frame),
            "RS_groups": len({row["source_group_id"] for row in rs_frame}),
            "memory_owners": len({row["source_group_id"] for row in memory_frame}),
        },
        "selected": {
            "RS_dialogues": len({row["source_group_id"] for row in rs_selected}),
            "memory_owners": len({row["source_group_id"] for row in memory_selected}),
            "memory_sessions": len({row["source_session_id"] for row in memory_selected}),
            "RS_turn_type": _count(rs_selected, "turn_type"),
            "memory_turn_type": _count(memory_selected, "turn_type"),
            "RS_length_bin": _count(rs_selected, "current_user_length_bin"),
            "memory_length_bin": _count(memory_selected, "current_user_length_bin"),
            "RS_depth_bin": _count(rs_selected, "turn_depth_bin"),
            "memory_depth_bin": _count(memory_selected, "turn_depth_bin"),
        },
        "artifacts": {
            "base_sample": {
                "filename": base_path.name,
                "rows": len(base_rows),
                "sha256": sha256_file(base_path),
            },
            "review_slot_plan": {
                "filename": review_path.name,
                "rows": len(review_rows),
                "sha256": sha256_file(review_path),
            },
        },
        "boundaries": {
            "target_supporter_responses_read_into_sample": 0,
            "gold_capability_or_effect_outcomes_read": 0,
            "formal_outcome_calls": 0,
            "paid_api_calls": 0,
            "pm_training_runs": 0,
            "human_or_machine_verdicts": 0,
            "sample_size_is_final": False,
            "not_an_empirical_pass_gate": True,
            "paid_machine_judging_authorized": False,
        },
    }
    summary_path = args.out_dir / "paper1_natural_turn_sample_proposal_summary_v1.json"
    write_json(summary_path, summary)
    print(summary_path)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
