#!/usr/bin/env python3
"""Compare provisional RS retrievers without outcomes or winner selection.

The surface uses the current dialogue-only ESConv Bank and visible-prefix
decision states.  It records only identities, hashes, source-side strategy
annotations, and retrieval scores.  It never reads target supporter responses
or formal benchmark outcomes.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median, pvariance
from typing import Any

from metacom_pm.paper1.rs.retriever_audit import (
    REQUIRED_RETRIEVER_METHODS,
    RSRetrieverComparisonRow,
    build_retriever_comparison_rows,
)
from metacom_pm.paper1.rs.strategy_bank import (
    StrategySourceCard,
    build_strategy_source_catalog,
)
from metacom_pm.paper1.rs.zero_outcome_census import (
    RSDecisionState,
    build_rs_decision_states,
    build_rs_zero_outcome_census,
)

PROTOCOL = "pm-paper1-esconv-rs-retriever-comparison-v1"
STATUS = "ZERO_OUTCOME_DECISION_SURFACE_NO_WINNER_NOT_RETRIEVER_FREEZE"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(_canonical(row) + "\n" for row in rows), encoding="utf-8")


def _distribution(values: list[float | int]) -> dict[str, float | int]:
    if not values:
        raise ValueError("distribution requires at least one value")
    ordered = sorted(values)

    def percentile(fraction: float) -> float | int:
        return ordered[round((len(ordered) - 1) * fraction)]

    return {
        "min": ordered[0],
        "p25": percentile(0.25),
        "median": median(ordered),
        "p75": percentile(0.75),
        "p90": percentile(0.90),
        "p95": percentile(0.95),
        "max": ordered[-1],
        "population_variance": pvariance(ordered),
    }


def _lexical_rankings(
    states: tuple[RSDecisionState, ...],
    cards: tuple[StrategySourceCard, ...],
    *,
    top_k: int,
    max_document_frequency: float,
) -> dict[str, tuple[tuple[str, float], ...]]:
    rows = build_rs_zero_outcome_census(
        states=states,
        cards=cards,
        diagnostic_top_k=top_k,
        diagnostic_max_document_frequency=max_document_frequency,
    )
    return {
        row.state_id: tuple(
            zip(row.diagnostic_candidate_ids, row.diagnostic_lexical_jaccards, strict=True)
        )
        for row in rows
    }


def _encode_texts(
    *,
    texts: list[str],
    tokenizer: Any,
    model: Any,
    device: str,
    batch_size: int,
) -> Any:
    import torch

    vectors = []
    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start : start + batch_size]
        encoded = tokenizer(
            batch_texts,
            padding=True,
            truncation=True,
            return_tensors="pt",
        ).to(device)
        with torch.inference_mode():
            vector = model(**encoded).last_hidden_state[:, 0]
            vector = torch.nn.functional.normalize(vector.float(), p=2, dim=1)
        vectors.append(vector.cpu())
    return torch.cat(vectors, dim=0)


def _dense_rankings(
    *,
    states: tuple[RSDecisionState, ...],
    cards: tuple[StrategySourceCard, ...],
    model_dir: Path,
    top_k: int,
    card_batch_size: int,
    query_batch_size: int,
    require_cuda: bool,
) -> tuple[dict[str, tuple[tuple[str, float], ...]], dict[str, Any]]:
    import torch
    from transformers import AutoModel, AutoTokenizer

    cuda_available = torch.cuda.is_available()
    if require_cuda and not cuda_available:
        raise RuntimeError("CUDA is required for the full RS retrieval audit")
    device = "cuda" if cuda_available else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = AutoModel.from_pretrained(model_dir, local_files_only=True).to(device).eval()

    ordered_cards = tuple(sorted(cards, key=lambda card: card.card_id))
    card_vectors = _encode_texts(
        texts=[card.retrieval_text for card in ordered_cards],
        tokenizer=tokenizer,
        model=model,
        device=device,
        batch_size=card_batch_size,
    ).to(device)
    by_dialogue: dict[str, list[int]] = {}
    for index, card in enumerate(ordered_cards):
        for dialogue_id in card.source_dialogue_ids:
            by_dialogue.setdefault(dialogue_id, []).append(index)

    rankings: dict[str, tuple[tuple[str, float], ...]] = {}
    for start in range(0, len(states), query_batch_size):
        state_batch = states[start : start + query_batch_size]
        query_vectors = _encode_texts(
            texts=[state.query_text for state in state_batch],
            tokenizer=tokenizer,
            model=model,
            device=device,
            batch_size=query_batch_size,
        ).to(device)
        scores = query_vectors @ card_vectors.T
        for row_index, state in enumerate(state_batch):
            excluded = by_dialogue.get(state.source_dialogue_id, ())
            if excluded:
                scores[row_index, list(excluded)] = -torch.inf
        top_scores, top_indices = torch.topk(scores, k=top_k, dim=1)
        for row_index, state in enumerate(state_batch):
            selected = sorted(
                (
                    (
                        ordered_cards[int(card_index)].card_id,
                        float(score),
                    )
                    for score, card_index in zip(
                        top_scores[row_index].cpu().tolist(),
                        top_indices[row_index].cpu().tolist(),
                        strict=True,
                    )
                ),
                key=lambda item: (-item[1], item[0]),
            )
            rankings[state.state_id] = tuple(selected)
        del scores, query_vectors, top_scores, top_indices

    metadata = {
        "model_class": type(model).__name__,
        "tokenizer_class": type(tokenizer).__name__,
        "device": device,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
        "pooling": "last_hidden_state_cls_token",
        "normalization": "l2_float32",
        "similarity": "exact_dense_cosine_via_normalized_dot_product",
        "query_instruction": None,
        "truncation": "tokenizer_model_max_length_if_needed",
        "card_batch_size": card_batch_size,
        "query_batch_size": query_batch_size,
        "top_k_tie_order": "score_desc_then_card_id_within_torch_topk_result",
    }
    del card_vectors, model, tokenizer
    gc.collect()
    if cuda_available:
        torch.cuda.empty_cache()
    return rankings, metadata


def _summarize_rows(rows: tuple[RSRetrieverComparisonRow, ...]) -> dict[str, Any]:
    method_rankings = {
        method: [
            next(ranking for ranking in row.rankings if ranking.method == method)
            for row in rows
        ]
        for method in REQUIRED_RETRIEVER_METHODS
    }
    method_summary: dict[str, Any] = {}
    for method, rankings in method_rankings.items():
        top1_ids = [ranking.candidate_ids[0] for ranking in rankings]
        top1_strategies = [ranking.source_strategy_annotations[0] for ranking in rankings]
        top1_scores = [ranking.scores[0] for ranking in rankings]
        margins = [
            ranking.scores[0] - ranking.scores[1]
            for ranking in rankings
            if len(ranking.scores) > 1
        ]
        method_summary[method] = {
            "top1_unique_card_count": len(set(top1_ids)),
            "top1_max_card_reuse_count": max(Counter(top1_ids).values()),
            "top1_source_strategy_annotation_counts": dict(
                sorted(Counter(top1_strategies).items())
            ),
            "top1_score_distribution": _distribution(top1_scores),
            "top1_minus_top2_margin_distribution": _distribution(margins),
        }

    pairwise: dict[str, Any] = {}
    for left_index, left in enumerate(REQUIRED_RETRIEVER_METHODS):
        for right in REQUIRED_RETRIEVER_METHODS[left_index + 1 :]:
            left_rows = method_rankings[left]
            right_rows = method_rankings[right]
            top1_equal = sum(
                left_row.candidate_ids[0] == right_row.candidate_ids[0]
                for left_row, right_row in zip(left_rows, right_rows, strict=True)
            )
            overlaps = []
            jaccards = []
            for left_row, right_row in zip(left_rows, right_rows, strict=True):
                left_set = set(left_row.candidate_ids)
                right_set = set(right_row.candidate_ids)
                overlap = len(left_set & right_set)
                overlaps.append(overlap)
                jaccards.append(overlap / len(left_set | right_set))
            pairwise[f"{left}__vs__{right}"] = {
                "top1_same_card_count": top1_equal,
                "top1_same_card_rate": top1_equal / len(rows),
                "topk_intersection_size_distribution": _distribution(overlaps),
                "topk_set_jaccard_distribution": _distribution(jaccards),
            }
    return {"by_method": method_summary, "pairwise_method_agreement": pairwise}


def main() -> int:
    project = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--esconv", type=Path, default=project / "data/external/ESConv.json")
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=project / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    parser.add_argument(
        "--environment-attestation",
        type=Path,
        default=project / "data/paper1_authority/paper1_local_environment_attestation_v1.json",
    )
    parser.add_argument("--bge-small-dir", type=Path, required=True)
    parser.add_argument("--bge-m3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=project / "data/paper1_public_rs")
    parser.add_argument("--query-preceding-turns", type=int, default=6)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--lexical-max-document-frequency", type=float, default=0.2)
    parser.add_argument("--small-batch-size", type=int, default=128)
    parser.add_argument("--m3-batch-size", type=int, default=32)
    parser.add_argument("--query-batch-size", type=int, default=64)
    parser.add_argument("--require-cuda", action="store_true")
    args = parser.parse_args()

    environment = json.loads(args.environment_attestation.read_text(encoding="utf-8"))
    expected_dirs = {
        "bge_small": environment["bge_small_encoder_candidate"],
        "bge_m3": environment["bge_m3_encoder_candidate"],
    }
    actual_dirs = {"bge_small": args.bge_small_dir, "bge_m3": args.bge_m3_dir}
    for name, attested in expected_dirs.items():
        model_dir = actual_dirs[name]
        if model_dir.name != attested["revision"]:
            raise ValueError(f"{name} snapshot revision does not match attestation")
        if _sha256(model_dir / "config.json") != attested["files"]["config.json"]:
            raise ValueError(f"{name} config hash does not match attestation")

    cards = build_strategy_source_catalog(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
        preceding_turns=args.query_preceding_turns,
    )
    states = build_rs_decision_states(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
        source_splits=("train", "validation"),
        exclude_evoemo_overlap=True,
        query_preceding_turns=args.query_preceding_turns,
    )
    lexical = _lexical_rankings(
        states,
        cards,
        top_k=args.top_k,
        max_document_frequency=args.lexical_max_document_frequency,
    )
    small, small_metadata = _dense_rankings(
        states=states,
        cards=cards,
        model_dir=args.bge_small_dir,
        top_k=args.top_k,
        card_batch_size=args.small_batch_size,
        query_batch_size=args.query_batch_size,
        require_cuda=args.require_cuda,
    )
    m3, m3_metadata = _dense_rankings(
        states=states,
        cards=cards,
        model_dir=args.bge_m3_dir,
        top_k=args.top_k,
        card_batch_size=args.m3_batch_size,
        query_batch_size=args.query_batch_size,
        require_cuda=args.require_cuda,
    )
    rows = build_retriever_comparison_rows(
        states=states,
        cards=cards,
        rankings_by_method={
            "lexical_jaccard": lexical,
            "bge_small": small,
            "bge_m3": m3,
        },
    )

    surface_path = args.out_dir / "esconv_rs_retriever_comparison_surface_v1.jsonl"
    summary_path = args.out_dir / "esconv_rs_retriever_comparison_summary_v1.json"
    _write_jsonl(
        surface_path,
        [
            {"protocol": PROTOCOL, **row.model_dump(mode="json")}
            for row in rows
        ],
    )
    summary = {
        "protocol": PROTOCOL,
        "status": STATUS,
        "scientific_scope": {
            "what_this_can_show": [
                "retriever_behavior_and_method_agreement",
                "score_and_margin_variation",
                "source_card_reuse_and_strategy_annotation_mix",
            ],
            "what_this_cannot_show": [
                "candidate_applicability_gold",
                "positive_marginal_effect",
                "PM_learnability",
                "official_ESC_Eval_or_ES_MemEval_performance",
                "retriever_winner",
            ],
            "winner_selected": False,
            "formal_outcome_calls": 0,
        },
        "universe": {
            "status": "CURRENT_CONSERVATIVE_PROJECT_UNIVERSE_NOT_OVERLAP_POLICY_FREEZE",
            "strategy_bank": "ESConv_train_dialogue_only_cards",
            "effect_states": "ESConv_train_validation_visible_prefixes",
            "evoemo_overlap_excluded": True,
            "leave_current_dialogue_out": True,
            "query_preceding_visible_turns": args.query_preceding_turns,
            "top_k": args.top_k,
            "source_card_count": len(cards),
            "decision_state_count": len(states),
        },
        "methods": {
            "lexical_jaccard": {
                "role": "PHASE1_BASELINE_DIAGNOSTIC_NOT_RETRIEVER_FREEZE",
                "max_card_document_frequency": args.lexical_max_document_frequency,
            },
            "bge_small": {
                "role": environment["bge_small_encoder_candidate"]["role"],
                "repo": environment["bge_small_encoder_candidate"]["repo"],
                "revision": environment["bge_small_encoder_candidate"]["revision"],
                "runtime": small_metadata,
            },
            "bge_m3": {
                "role": environment["bge_m3_encoder_candidate"]["role"],
                "repo": environment["bge_m3_encoder_candidate"]["repo"],
                "revision": environment["bge_m3_encoder_candidate"]["revision"],
                "runtime": m3_metadata,
            },
        },
        "contract_status": {
            "pooling_and_normalization": "PROVISIONAL_SHARED_SYMMETRIC_CONTRACT_NOT_M2_FREEZE",
            "query_instruction": "NONE_FOR_ALL_DENSE_METHODS_TO_AVOID_ASYMMETRIC_PROMPT_ADVANTAGE",
            "target_supporter_response_read": False,
            "target_strategy_annotation_read": False,
            "situation_read": False,
            "future_turns_read": False,
        },
        "diagnostics": _summarize_rows(rows),
        "provenance": {
            "esconv_sha256": _sha256(args.esconv),
            "split_manifest_sha256": _sha256(args.split_manifest),
            "environment_attestation_sha256": _sha256(args.environment_attestation),
            "script_sha256": _sha256(Path(__file__).resolve()),
            "surface_path": str(surface_path.relative_to(project)),
            "surface_sha256": _sha256(surface_path),
        },
        "pending_m2_freeze": [
            "effect_state_overlap_policy",
            "retriever_encoder_revision_and_runtime_contract",
            "query_construction_and_optional_instruction",
            "candidate_bundle_top_k",
            "candidate_applicability_measurement",
        ],
    }
    _write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
