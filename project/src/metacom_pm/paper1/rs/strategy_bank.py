"""Public ESConv source catalog and fold-exclusive RS retrieval.

This is deliberately a source catalog, not the final frozen Strategy-RAG
bundle.  Top-k, token caps, rendering and the final retrieval backend remain
M2 freeze items.  Retrieval keys use only dialogue turns that preceded the
source response.  ESConv's author-written ``situation`` and all response
quality, feedback, survey or downstream outcome fields are not read here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from ..contracts import StrictContract

EXPECTED_ESCONV_SHA256 = "aa0556c5b330562ba009c1cd5137486bfa2a7255f33225a6524cd58f7efdd9af"
EXPECTED_SPLIT_SHA256 = "0199fbe1cad5f42aacfd2ba52a92bc6530dfcb33a82bb7bb7e81e5abb6e63e63"
EXPECTED_SPLIT_COUNTS = {"train": 934, "validation": 186, "test": 180}

_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _normalize(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()


def _stable_id(*parts: Any) -> str:
    return hashlib.sha256(_canonical_json(parts).encode("utf-8")).hexdigest()


def _tokens(value: str) -> frozenset[str]:
    return frozenset(match.group(0).casefold() for match in _TOKEN_RE.finditer(value))


class StrategySourceCard(StrictContract):
    card_id: str = Field(pattern=r"^rs_src_[0-9a-f]{24}$")
    source_dialogue_id: str = Field(pattern=r"^esconv_[0-9]{4}$")
    source_turn_index: int = Field(ge=0)
    source_split: str = "train"
    strategy_label: str = Field(
        min_length=1,
        description="Source-card annotation; never the current state's gold label",
    )
    retrieval_text: str = Field(min_length=1)
    guidance_text: str = Field(min_length=1)
    example_response: str = Field(min_length=1)
    retrieval_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    example_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Every dialogue_id (including source_dialogue_id itself) whose supporter
    # turn produced the same normalized, case-folded (retrieval_text, response)
    # duplicate key -- this
    # card is the single kept representative of that whole equivalence
    # class, and leave-current-dialogue-out fold exclusion must exclude a
    # candidate built from this card for ANY of these dialogues, not just
    # source_dialogue_id, or a state in one of the collapsed-duplicate
    # dialogues could retrieve a card that is verbatim its own supporter's
    # words under a different dialogue_id's name.
    source_dialogue_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _dialogue_ids_include_self_sorted_unique(self) -> "StrategySourceCard":
        if self.source_dialogue_id not in self.source_dialogue_ids:
            raise ValueError("source_dialogue_ids must include source_dialogue_id")
        if len(set(self.source_dialogue_ids)) != len(self.source_dialogue_ids):
            raise ValueError("source_dialogue_ids must not contain duplicates")
        if tuple(sorted(self.source_dialogue_ids)) != self.source_dialogue_ids:
            raise ValueError("source_dialogue_ids must be sorted")
        return self


class StrategyRetrieval(StrictContract):
    card: StrategySourceCard
    rank: int = Field(ge=1)
    lexical_jaccard: float = Field(ge=0.0, le=1.0)


def _read_split_manifest(path: Path) -> dict[int, dict[str, Any]]:
    if _file_sha256(path) != EXPECTED_SPLIT_SHA256:
        raise ValueError("ESConv project split manifest SHA256 mismatch")
    rows: dict[int, dict[str, Any]] = {}
    counts = {name: 0 for name in EXPECTED_SPLIT_COUNTS}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        row = json.loads(line)
        index = row.get("index")
        split = row.get("split")
        dialogue_id = row.get("dialogue_id")
        if not isinstance(index, int) or index in rows:
            raise ValueError(f"invalid/duplicate split index at line {line_number}")
        if split not in counts:
            raise ValueError(f"unknown split at line {line_number}")
        if dialogue_id != f"esconv_{index:04d}":
            raise ValueError(f"dialogue identity mismatch at line {line_number}")
        if not isinstance(row.get("excluded_for_evoemo_overlap"), bool):
            raise ValueError(f"missing mechanical overlap flag at line {line_number}")
        rows[index] = row
        counts[split] += 1
    if counts != EXPECTED_SPLIT_COUNTS or len(rows) != sum(EXPECTED_SPLIT_COUNTS.values()):
        raise ValueError(f"unexpected ESConv project split counts: {counts}")
    return rows


def build_strategy_source_catalog(
    *,
    esconv_path: str | Path,
    split_manifest_path: str | Path,
    preceding_turns: int = 6,
    exclude_evoemo_overlap: bool = True,
) -> tuple[StrategySourceCard, ...]:
    """Extract train-only annotated supporter turns without outcome fields."""

    source_path = Path(esconv_path)
    if _file_sha256(source_path) != EXPECTED_ESCONV_SHA256:
        raise ValueError("ESConv artifact SHA256 mismatch")
    if preceding_turns < 1:
        raise ValueError("preceding_turns must be positive")
    split_rows = _read_split_manifest(Path(split_manifest_path))
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != len(split_rows):
        raise ValueError("ESConv must be a 1300-dialogue list aligned to the split manifest")

    # Pass 1: walk every candidate turn (no dedup yet) so the full set of
    # dialogue_ids sharing each (retrieval_text, response) duplicate_key is
    # known before any card is built -- a card built in pass 2 below must
    # record every dialogue in its equivalence class, not just whichever one
    # happened to be encountered first.
    Candidate = tuple[str, int, str, str, str]  # dialogue_id, turn_index, strategy, retrieval_text, response
    candidates_by_key: dict[tuple[str, str], list[Candidate]] = {}
    ordered_keys: list[tuple[str, str]] = []
    for dialogue_index, row in enumerate(data):
        split = split_rows[dialogue_index]
        if split["split"] != "train":
            continue
        if exclude_evoemo_overlap and split["excluded_for_evoemo_overlap"]:
            continue
        dialogue = row.get("dialog")
        if not isinstance(dialogue, list):
            raise ValueError(f"invalid dialogue at ESConv index {dialogue_index}")
        dialogue_id = split["dialogue_id"]
        for turn_index, turn in enumerate(dialogue):
            if turn.get("speaker") != "supporter":
                continue
            strategy = _normalize((turn.get("annotation") or {}).get("strategy") or "Others")
            response = _normalize(turn.get("content"))
            if not response:
                continue
            prior = dialogue[max(0, turn_index - preceding_turns) : turn_index]
            context = "\n".join(
                f"{_normalize(item.get('speaker'))}: {_normalize(item.get('content'))}"
                for item in prior
                if _normalize(item.get("content"))
            )
            retrieval_text = context
            if not retrieval_text:
                # A source response can be its own retrieval key when it has no
                # preceding dialogue.  This is candidate-side public text, not
                # target-state or outcome information.
                retrieval_text = response
            duplicate_key = (_normalize(retrieval_text).casefold(), response.casefold())
            if duplicate_key not in candidates_by_key:
                candidates_by_key[duplicate_key] = []
                ordered_keys.append(duplicate_key)
            candidates_by_key[duplicate_key].append(
                (dialogue_id, turn_index, strategy, retrieval_text, response)
            )

    # Pass 2: for each duplicate_key, keep the FIRST-encountered candidate as
    # the representative card (unchanged from the prior single-pass
    # behavior/card_id/content), but attach every dialogue_id in that key's
    # full equivalence class.
    cards: list[StrategySourceCard] = []
    for duplicate_key in ordered_keys:
        group = candidates_by_key[duplicate_key]
        dialogue_id, turn_index, strategy, retrieval_text, response = group[0]
        all_dialogue_ids = tuple(sorted({item[0] for item in group}))
        guidance = (
            f"Use the emotional-support strategy '{strategy}' only when it fits the visible "
            "dialogue. Adapt the move naturally and do not assume undisclosed facts."
        )
        identity = _stable_id(dialogue_id, turn_index, strategy, retrieval_text, response)
        cards.append(
            StrategySourceCard(
                card_id=f"rs_src_{identity[:24]}",
                source_dialogue_id=dialogue_id,
                source_dialogue_ids=all_dialogue_ids,
                source_turn_index=turn_index,
                strategy_label=strategy,
                retrieval_text=retrieval_text,
                guidance_text=guidance,
                example_response=response,
                retrieval_text_sha256=hashlib.sha256(retrieval_text.encode("utf-8")).hexdigest(),
                example_response_sha256=hashlib.sha256(response.encode("utf-8")).hexdigest(),
            )
        )
    return tuple(cards)


def rank_strategy_cards(
    *,
    cards: Sequence[StrategySourceCard],
    query_text: str,
    excluded_dialogue_ids: Iterable[str],
    top_k: int,
) -> tuple[StrategyRetrieval, ...]:
    """Deterministic lexical audit retrieval with fail-closed fold exclusion.

    This scorer is suitable for zero-outcome census.  It is not declared the
    final M2 retrieval backend merely by being implemented here.
    """

    if top_k < 1:
        raise ValueError("top_k must be positive")
    excluded = frozenset(excluded_dialogue_ids)
    query_tokens = _tokens(query_text)
    scored: list[tuple[float, str, StrategySourceCard]] = []
    for card in cards:
        if excluded.intersection(card.source_dialogue_ids):
            continue
        card_tokens = _tokens(card.retrieval_text)
        union = query_tokens | card_tokens
        score = len(query_tokens & card_tokens) / len(union) if union else 0.0
        scored.append((score, card.card_id, card))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = scored[:top_k]
    result = tuple(
        StrategyRetrieval(card=card, rank=rank, lexical_jaccard=score)
        for rank, (score, _card_id, card) in enumerate(selected, start=1)
    )
    leaked = excluded.intersection(
        dialogue_id
        for row in result
        for dialogue_id in row.card.source_dialogue_ids
    )
    if leaked:
        raise RuntimeError(f"fold-excluded Strategy Bank source leaked: {sorted(leaked)}")
    return result
