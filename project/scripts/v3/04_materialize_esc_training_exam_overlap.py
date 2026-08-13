#!/usr/bin/env python3
"""Materialize source, normalized, lexical, and local-embedding ESC overlap."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm(text: str) -> str:
    return " ".join(TOKEN_RE.findall(unicodedata.normalize("NFKC", text).casefold()))


def _problem(card_text: str) -> str:
    match = re.search(r"(?im)^problem:\s*", card_text)
    return card_text[match.end():].strip() if match else card_text.strip()


def _tokens(text: str) -> set[str]:
    return set(_norm(text).split())


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _source_docs(esconv_path: Path, extes_path: Path) -> dict[str, list[dict[str, str]]]:
    esconv = json.loads(esconv_path.read_text(encoding="utf-8"))
    extes = json.loads(extes_path.read_text(encoding="utf-8"))
    esconv_docs = []
    for index, row in enumerate(esconv):
        seeker = [turn["content"] for turn in row["dialog"] if turn.get("speaker") == "seeker"]
        text = "\n".join([row.get("situation", ""), *seeker]).strip()
        esconv_docs.append({"id": f"esconv::{index:04d}", "text": text})
    extes_docs = []
    for index, row in enumerate(extes):
        user_turns = []
        for turn in row.get("content", []):
            if isinstance(turn, dict) and "User" in turn:
                user_turns.append(turn["User"])
        text = "\n".join([row.get("description", ""), *user_turns]).strip()
        extes_docs.append({"id": f"extes::{index:05d}", "text": text})
    return {"ESconv": esconv_docs, "ExTES": extes_docs}


def _encode(texts: list[str], model_path: Path, batch_size: int) -> Any:
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModel.from_pretrained(model_path, local_files_only=True).to("cpu").eval()
    chunks = []
    for start in range(0, len(texts), batch_size):
        batch = tokenizer(
            texts[start:start + batch_size],
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        with torch.no_grad():
            output = model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1)
            pooled = (output * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        chunks.append(pooled.cpu())
    return torch.cat(chunks, dim=0)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def materialize(
    card_en_path: Path,
    card_zh_path: Path,
    esconv_path: Path,
    extes_path: Path,
    model_path: Path,
    model_revision: str,
    batch_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cards = json.loads(card_en_path.read_text(encoding="utf-8")) + json.loads(card_zh_path.read_text(encoding="utf-8"))
    scoped_cards = [card for card in cards if card["source"] in {"ESconv", "ExTES"}]
    docs_by_source = _source_docs(esconv_path, extes_path)
    rows: list[dict[str, Any]] = []

    for source in ("ESconv", "ExTES"):
        source_cards = [card for card in scoped_cards if card["source"] == source]
        docs = docs_by_source[source]
        queries = [_problem(card["base"]) for card in source_cards]
        doc_norms = [_norm(doc["text"]) for doc in docs]
        doc_tokens = [set(text.split()) for text in doc_norms]
        query_embeddings = _encode(queries, model_path, batch_size)
        doc_embeddings = _encode([doc["text"] for doc in docs], model_path, batch_size)
        semantic = query_embeddings @ doc_embeddings.T

        for query_index, (card, query) in enumerate(zip(source_cards, queries)):
            query_norm = _norm(query)
            query_tokens = set(query_norm.split())
            lexical_scores = [_jaccard(query_tokens, tokens) for tokens in doc_tokens]
            lexical_index = max(range(len(docs)), key=lambda index: lexical_scores[index])
            semantic_values = semantic[query_index]
            top_semantic = semantic_values.topk(k=min(3, len(docs)))
            semantic_neighbors = [
                {"source_item_id": docs[int(index)]["id"], "cosine": round(float(score), 6)}
                for score, index in zip(top_semantic.values, top_semantic.indices)
            ]
            exact_indices = [index for index, value in enumerate(doc_norms) if value == query_norm]
            containment_indices = [
                index
                for index, value in enumerate(doc_norms)
                if min(len(value), len(query_norm)) >= 40 and (query_norm in value or value in query_norm)
            ]
            rows.append(
                {
                    "card_key": f"{card['language']}::{card['source']}::{card['id']}",
                    "source": source,
                    "language": card["language"],
                    "source_level_overlap": True,
                    "card_problem_normalized_sha256": _sha_text(query_norm),
                    "exact_normalized_match_ids": [docs[index]["id"] for index in exact_indices],
                    "normalized_containment_match_ids": [docs[index]["id"] for index in containment_indices[:10]],
                    "best_lexical_neighbor": {
                        "source_item_id": docs[lexical_index]["id"],
                        "token_jaccard": round(lexical_scores[lexical_index], 6),
                    },
                    "semantic_neighbors": semantic_neighbors,
                }
            )

    rows.sort(key=lambda row: row["card_key"])
    semantic_scores = [row["semantic_neighbors"][0]["cosine"] for row in rows]
    lexical_scores = [row["best_lexical_neighbor"]["token_jaccard"] for row in rows]
    english_cards = [card for card in cards if card["language"] == "english"]
    excluded_keys = {
        source: sorted(
            f"{card['language']}::{card['source']}::{card['id']}"
            for card in english_cards
            if card["source"] == source
        )
        for source in ("ESconv", "ExTES")
    }
    clean_if_both = sorted(
        f"{card['language']}::{card['source']}::{card['id']}"
        for card in english_cards
        if card["source"] not in {"ESconv", "ExTES"}
    )
    summary = {
        "protocol": "metacom-v3-esc-training-exam-overlap-summary-v1",
        "status": "SOURCE_AND_LOCAL_SEMANTIC_SCREEN_COMPLETE",
        "scope": "ESC-Eval cards sourced from ESConv or ExTES versus the complete pinned public source artifacts.",
        "decision_rule": "Source-level overlap is dispositive: if ESConv or ExTES is used for generator training, all ESC-Eval cards from that source are excluded from the primary qualification exam. Semantic neighbors are diagnostic mappings, not proof of exact provenance.",
        "cards_total": len(cards),
        "cards_in_known_training_source_scope": len(rows),
        "source_counts": dict(Counter(row["source"] for row in rows)),
        "source_item_counts": {source: len(docs) for source, docs in docs_by_source.items()},
        "qualification_identity_policy": {
            "pre_sft_primary_english_cards": len(english_cards),
            "excluded_card_keys_by_training_source": excluded_keys,
            "clean_english_holdout_if_esconv_and_extes_train": {
                "cards": len(clean_if_both),
                "card_keys": clean_if_both,
            },
            "rule": "The pre-SFT current generator may be located on all 331 English cards. Any post-SFT confirmation excludes every card whose declared source was used for SFT; if both ESConv and ExTES are used, the primary contamination-aware English holdout contains 103 cards.",
        },
        "exact_normalized_matches": sum(bool(row["exact_normalized_match_ids"]) for row in rows),
        "normalized_containment_matches": sum(bool(row["normalized_containment_match_ids"]) for row in rows),
        "lexical_best_score": {"p50": round(_quantile(lexical_scores, 0.5), 6), "p90": round(_quantile(lexical_scores, 0.9), 6), "max": round(max(lexical_scores), 6)},
        "semantic_best_score": {
            "p50": round(_quantile(semantic_scores, 0.5), 6),
            "p90": round(_quantile(semantic_scores, 0.9), 6),
            "max": round(max(semantic_scores), 6),
            "ge_0_80": sum(score >= 0.80 for score in semantic_scores),
            "ge_0_90": sum(score >= 0.90 for score in semantic_scores),
            "ge_0_95": sum(score >= 0.95 for score in semantic_scores),
        },
        "embedding_model": {
            "id": "BAAI/bge-small-en-v1.5",
            "revision": model_revision,
            "local_path_name": model_path.name,
            "pooling": "attention-mask mean pooling; L2 normalized; no retrieval instruction",
            "max_length": 256,
        },
        "input_hashes": {
            "card_high_en.json": _sha_file(card_en_path),
            "card_high_zh.json": _sha_file(card_zh_path),
            "ESConv.json": _sha_file(esconv_path),
            "ExTES.json": _sha_file(extes_path),
        },
        "contains_source_or_card_text": False,
        "api_calls": 0,
    }
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card-en", required=True, type=Path)
    parser.add_argument("--card-zh", required=True, type=Path)
    parser.add_argument("--esconv", required=True, type=Path)
    parser.add_argument("--extes", required=True, type=Path)
    parser.add_argument("--embedding-model", required=True, type=Path)
    parser.add_argument("--embedding-revision", required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    rows, summary = materialize(
        args.card_en,
        args.card_zh,
        args.esconv,
        args.extes,
        args.embedding_model,
        args.embedding_revision,
        args.batch_size,
    )
    rendered_rows = "".join(_canonical(row) + "\n" for row in rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered_rows, encoding="utf-8")
    summary["row_manifest"] = {
        "path": args.out.name,
        "rows": len(rows),
        "sha256": hashlib.sha256(rendered_rows.encode("utf-8")).hexdigest(),
    }
    rendered_summary = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    args.summary.write_text(rendered_summary, encoding="utf-8")
    print(rendered_summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
