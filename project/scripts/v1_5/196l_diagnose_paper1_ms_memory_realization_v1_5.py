#!/usr/bin/env python3
"""Zero-API diagnosis of Rank-1 session -> exact MS evidence realization.

This is a read-only system-feasibility diagnostic.  It does not create a new
PM label, refit the PM, select a threshold, call a generator/reviewer, or read
future/event/summary/QA fields.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from metacom_pm.io import sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_memory_realization_v2 import (  # noqa: E402
    current_seeker_query,
    is_low_information_turn,
    normalized_tokens,
    parse_raw_ms_session,
    select_ms_exact_span,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_session_aligned_materialization_phase_v2.json"
STATES = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_public_20260810/ms_checkpoint_states_unlabeled.jsonl"
CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_public_20260810/ms_raw_session_candidates_unlabeled.jsonl"
RANK1 = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_public_20260810/ms_actual_rank1_unlabeled.jsonl"
OOF = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_final_oof_private_20260810/ms_grouped_oof_predictions.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_memory_realization_diagnostic_20260810"
SELECTION_PROTOCOL = "pm-v1.5-paper1-borderline-ms-same-stack-feasibility-candidate-v1"


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
                texts[start : start + 64],
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            batch = {key: value.to(device) for key, value in batch.items()}
            vectors = model(**batch).last_hidden_state[:, 0]
            vectors = torch.nn.functional.normalize(vectors.float(), p=2, dim=1)
            pieces.append(vectors.cpu().numpy())
    return np.concatenate(pieces, axis=0)


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p10": None, "median": None, "p90": None, "max": None}
    ordered = sorted(float(value) for value in values)
    def pick(q: float) -> float:
        return ordered[round(q * (len(ordered) - 1))]
    return {
        "min": ordered[0],
        "p10": pick(0.10),
        "median": statistics.median(ordered),
        "p90": pick(0.90),
        "max": ordered[-1],
    }


def fixed_hash(state_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_PROTOCOL}\x1f{state_id}".encode()).hexdigest()


def main() -> None:
    authority = read(AUTHORITY)
    current = authority["current_phase"]
    if current["status"] != "FINAL_OOF_CONSUMED_PRIMARY_FAIL_NO_FURTHER_PM_FIT":
        raise RuntimeError("diagnostic requires the immutable terminal V2 OOF")
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite existing diagnostic: {OUT}")

    phase = read(PHASE)
    snapshot = Path(phase["local_semantic_encoder"]["snapshot_path"])
    states = rows(STATES)
    candidates = rows(CANDIDATES)
    rank1 = rows(RANK1)
    oof = rows(OOF)
    state_by_id = {row["state_id"]: row for row in states}
    candidate_by_id = {row["candidate_id"]: row for row in candidates}
    rank_by_state = {row["state_id"]: row for row in rank1 if row["candidate_present"]}
    oof_by_state = {row["state_id"]: row for row in oof}

    runtime_rows = []
    unique_texts: list[str] = []
    for state_id, selected in rank_by_state.items():
        state = state_by_id[state_id]
        candidate = candidate_by_id[selected["actual_rank1_id"]]
        query = current_seeker_query(state["visible_current_session_dialogue"])
        turns = parse_raw_ms_session(candidate["literal_text"])
        runtime_rows.append((state, candidate, selected, query, turns))
        unique_texts.append(query)
        unique_texts.extend(turns)
    unique_texts = list(dict.fromkeys(unique_texts))
    vectors = encode_bge(snapshot, unique_texts)
    vector_by_text = dict(zip(unique_texts, vectors, strict=True))

    diagnostics: list[dict[str, Any]] = []
    for state, candidate, rank, query, turns in runtime_rows:
        query_vector = vector_by_text[query]
        scores = {turn: float(query_vector @ vector_by_text[turn]) for turn in turns}
        unfiltered_index, unfiltered_turn = max(
            enumerate(turns), key=lambda item: (scores[item[1]], item[0])
        )
        selected = select_ms_exact_span(candidate["literal_text"], scores)
        current_normalized = " ".join(normalized_tokens(state["visible_text"]))
        if selected is None:
            selected_span = None
            selected_words = 0
            selected_score = None
            exact_current_redundant = False
        else:
            selected_span = selected.exact_span
            selected_words = len(normalized_tokens(selected_span))
            selected_score = selected.semantic_score
            exact_current_redundant = " ".join(normalized_tokens(selected_span)) in current_normalized
        diagnostics.append(
            {
                "state_id": state["state_id"],
                "group": state["split_group_key"],
                "current_query": query,
                "candidate_id": candidate["candidate_id"],
                "candidate_source_session_id": candidate["source_session_id"],
                "raw_session_words": candidate["raw_word_count"],
                "raw_turns": len(turns),
                "low_information_turns": sum(is_low_information_turn(turn) for turn in turns),
                "unfiltered_top_span": unfiltered_turn,
                "unfiltered_top_source_turn_index": unfiltered_index,
                "unfiltered_top_score": scores[unfiltered_turn],
                "unfiltered_top_is_low_information": is_low_information_turn(unfiltered_turn),
                "selected_exact_span": selected_span,
                "selected_words": selected_words,
                "selected_score": selected_score,
                "selector_abstained": selected is None,
                "selected_exactly_present_in_raw_rank1": bool(selected_span and selected_span in candidate["literal_text"]),
                "selected_exactly_redundant_in_visible_current": exact_current_redundant,
                "rank1_session_score": rank["selection_score"],
                "oof_decision": oof_by_state[state["state_id"]]["decision"],
                "oof_probability": oof_by_state[state["state_id"]]["prior_corrected_probability"],
            }
        )

    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in diagnostics:
        by_group[row["group"]].append(row)
    selected68 = []
    for group, group_rows in sorted(by_group.items()):
        selected68.extend(
            sorted(group_rows, key=lambda row: (fixed_hash(row["state_id"]), row["state_id"]))[:4]
        )

    phatic_examples = [
        {
            "state_id": row["state_id"],
            "current_query": row["current_query"],
            "unfiltered_top_span": row["unfiltered_top_span"],
            "unfiltered_top_score": row["unfiltered_top_score"],
            "filtered_selected_span": row["selected_exact_span"],
            "filtered_selected_score": row["selected_score"],
        }
        for row in diagnostics
        if row["unfiltered_top_is_low_information"]
    ][:12]
    selected_actions = Counter(
        "MS+R0" if int(row["oof_decision"]) else "M0+R0" for row in selected68
    )
    physical_calls = sum(
        len({"M0+R0", "MS+R0", "MS+R0" if row["oof_decision"] else "M0+R0"})
        for row in selected68
    )
    report = {
        "protocol": "pm-v1.5-paper1-ms-memory-realization-diagnostic-v1",
        "status": "ZERO_API_REALIZATION_DIAGNOSTIC_PASS" if not any(row["selector_abstained"] for row in diagnostics) else "ZERO_API_REALIZATION_DIAGNOSTIC_HAS_ABSTENTIONS",
        "scope": "read-only post-OOF system-feasibility diagnosis; no PM refit or label change",
        "finding": (
            "Session-level Rank-1 is a retrieval object, not generator-ready evidence. "
            "A separate outcome-blind selector can bind one informative exact seeker span "
            "and exclude phatic turns before typed composition."
        ),
        "all_rank1_rows": {
            "n": len(diagnostics),
            "groups": len(by_group),
            "raw_sessions_containing_at_least_one_low_information_turn": sum(row["low_information_turns"] > 0 for row in diagnostics),
            "unfiltered_semantic_top_is_low_information": sum(row["unfiltered_top_is_low_information"] for row in diagnostics),
            "selector_abstentions": sum(row["selector_abstained"] for row in diagnostics),
            "selected_low_information": sum(bool(row["selected_exact_span"]) and is_low_information_turn(row["selected_exact_span"]) for row in diagnostics),
            "selected_exactly_present_in_raw_rank1": sum(row["selected_exactly_present_in_raw_rank1"] for row in diagnostics),
            "selected_exactly_redundant_in_visible_current": sum(row["selected_exactly_redundant_in_visible_current"] for row in diagnostics),
            "raw_session_word_distribution": quantiles([row["raw_session_words"] for row in diagnostics]),
            "selected_span_word_distribution": quantiles([row["selected_words"] for row in diagnostics if row["selected_words"]]),
            "selected_to_raw_word_ratio_distribution": quantiles([row["selected_words"] / row["raw_session_words"] for row in diagnostics if row["selected_words"]]),
            "unfiltered_top_score_distribution": quantiles([row["unfiltered_top_score"] for row in diagnostics]),
            "filtered_selected_score_distribution": quantiles([row["selected_score"] for row in diagnostics if row["selected_score"] is not None]),
        },
        "fixed_hash_68_state_feasibility_design": {
            "states": len(selected68),
            "groups": len({row["group"] for row in selected68}),
            "learned_policy_actions": dict(selected_actions),
            "logical_policy_observations": len(selected68) * 3,
            "deduplicated_physical_generator_calls_one_seed": physical_calls,
            "selector_abstentions": sum(row["selector_abstained"] for row in selected68),
            "unfiltered_semantic_top_is_low_information": sum(row["unfiltered_top_is_low_information"] for row in selected68),
            "selected_exactly_redundant_in_visible_current": sum(row["selected_exactly_redundant_in_visible_current"] for row in selected68),
        },
        "examples_where_unfiltered_turn_ranking_would_choose_phatic_text": phatic_examples,
        "invariants": {
            "current_query_seeker_only": True,
            "strictly_past_actual_rank1_unchanged": True,
            "selected_span_is_exact_source_text": all(row["selected_exactly_present_in_raw_rank1"] for row in diagnostics if not row["selector_abstained"]),
            "summary_event_timeline_qa_or_future_read": False,
            "author_ancestry_or_suitability_label_read": False,
            "oof_predictions_immutable_and_not_refit": True,
            "response_generation_or_review": False,
            "api_calls": 0,
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "states": sha256_file(STATES),
            "candidates": sha256_file(CANDIDATES),
            "rank1": sha256_file(RANK1),
            "oof": sha256_file(OOF),
        },
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
