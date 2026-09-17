"""Outcome-blind RS state construction and source-card availability audit.

The state surface is limited to dialogue text visible before a supporter
response opportunity.  It never reads the ESConv situation, feedback, survey,
questionnaire or target supporter response as a state feature.  Lexical ranks
are diagnostics for Phase 1 only; they do not freeze the M2 retriever or bundle.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from ..contracts import StrictContract
from .strategy_bank import (
    EXPECTED_ESCONV_SHA256,
    StrategySourceCard,
    _file_sha256,
    _normalize,
    _read_split_manifest,
    _stable_id,
    _tokens,
)

_ADVICE_REQUEST_RE = re.compile(
    r"\b(?:what should i do|what can i do|any advice|"
    r"how (?:do|can|should) i|suggestions?|recommend)\b",
    re.IGNORECASE,
)
_LISTEN_ONLY_RE = re.compile(
    r"\b(?:just (?:need|want) (?:you )?to listen|"
    r"do not want advice|don't want advice|no advice)\b",
    re.IGNORECASE,
)
_NO_PROBING_RE = re.compile(
    r"\b(?:do not ask|don't ask|no questions)\b",
    re.IGNORECASE,
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _word_count(value: str) -> int:
    return len(value.split())


class RSDecisionState(StrictContract):
    """One pre-response opportunity with an outcome-blind visible prefix."""

    state_id: str = Field(pattern=r"^rs_state_[0-9a-f]{24}$")
    source_dialogue_id: str = Field(pattern=r"^esconv_[0-9]{4}$")
    source_split: str
    decision_turn_index: int = Field(ge=1)
    visible_dialogue_text: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    current_user_text: str = Field(min_length=1)
    visible_turn_count: int = Field(ge=1)
    query_turn_count: int = Field(ge=1)
    current_user_turn_count: int = Field(ge=1)


class RSCensusRow(StrictContract):
    state_id: str
    source_dialogue_id: str
    source_split: str
    decision_turn_index: int = Field(ge=1)
    visible_dialogue_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_user_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_turn_count: int = Field(ge=1)
    query_turn_count: int = Field(ge=1)
    current_user_turn_count: int = Field(ge=1)
    query_word_count: int = Field(ge=1)
    current_user_word_count: int = Field(ge=1)
    candidate_count_after_leave_dialogue_out: int = Field(ge=1)
    nonzero_lexical_overlap_candidate_count: int = Field(ge=0)
    diagnostic_candidate_ids: tuple[str, ...]
    diagnostic_lexical_jaccards: tuple[float, ...]
    diagnostic_injected_word_counts: tuple[int, ...]
    advice_request_visible: bool
    listen_only_visible: bool
    no_probing_visible: bool


def _render_turn(turn: dict[str, Any]) -> str:
    speaker = _normalize(turn.get("speaker"))
    content = _normalize(turn.get("content"))
    return f"{speaker}: {content}" if content else ""


def build_rs_decision_states(
    *,
    esconv_path: str | Path,
    split_manifest_path: str | Path,
    source_splits: Iterable[str] = ("train", "validation"),
    exclude_evoemo_overlap: bool = True,
    query_preceding_turns: int = 6,
) -> tuple[RSDecisionState, ...]:
    """Build one state per supporter run after at least one visible seeker turn.

    Consecutive supporter utterances form a single response opportunity.  The
    query ends at the immediately preceding seeker run and contains neither the
    target supporter response nor any future turn.
    """

    source_path = Path(esconv_path)
    if _file_sha256(source_path) != EXPECTED_ESCONV_SHA256:
        raise ValueError("ESConv artifact SHA256 mismatch")
    if query_preceding_turns < 1:
        raise ValueError("query_preceding_turns must be positive")
    allowed_splits = frozenset(source_splits)
    if not allowed_splits or not allowed_splits <= {"train", "validation", "test"}:
        raise ValueError("source_splits must be a non-empty ESConv split subset")

    split_rows = _read_split_manifest(Path(split_manifest_path))
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != len(split_rows):
        raise ValueError("ESConv must align one-to-one with the split manifest")

    states: list[RSDecisionState] = []
    for dialogue_index, row in enumerate(data):
        split = split_rows[dialogue_index]
        if split["split"] not in allowed_splits:
            continue
        if exclude_evoemo_overlap and split["excluded_for_evoemo_overlap"]:
            continue
        dialogue = row.get("dialog")
        if not isinstance(dialogue, list):
            raise ValueError(f"invalid dialogue at ESConv index {dialogue_index}")
        dialogue_id = split["dialogue_id"]
        for turn_index, turn in enumerate(dialogue):
            if turn.get("speaker") != "supporter" or not _normalize(turn.get("content")):
                continue
            if turn_index and dialogue[turn_index - 1].get("speaker") == "supporter":
                continue

            visible = [item for item in dialogue[:turn_index] if _normalize(item.get("content"))]
            if not visible or visible[-1].get("speaker") != "seeker":
                # Initial supporter greetings have no user state and are not a
                # resource-allocation opportunity.
                continue
            current_user: list[dict[str, Any]] = []
            for item in reversed(visible):
                if item.get("speaker") != "seeker":
                    break
                current_user.append(item)
            current_user.reverse()

            query_turns = visible[-query_preceding_turns:]
            visible_text = "\n".join(filter(None, (_render_turn(item) for item in visible)))
            query_text = "\n".join(filter(None, (_render_turn(item) for item in query_turns)))
            current_user_text = "\n".join(
                _normalize(item.get("content")) for item in current_user
            )
            identity = _stable_id(
                dialogue_id,
                turn_index,
                _sha256_text(visible_text),
                _sha256_text(query_text),
            )
            states.append(
                RSDecisionState(
                    state_id=f"rs_state_{identity[:24]}",
                    source_dialogue_id=dialogue_id,
                    source_split=split["split"],
                    decision_turn_index=turn_index,
                    visible_dialogue_text=visible_text,
                    query_text=query_text,
                    current_user_text=current_user_text,
                    visible_turn_count=len(visible),
                    query_turn_count=len(query_turns),
                    current_user_turn_count=len(current_user),
                )
            )
    if len({state.state_id for state in states}) != len(states):
        raise RuntimeError("RS state identities are not unique")
    return tuple(states)


class _LexicalAuditIndex:
    def __init__(
        self,
        cards: Sequence[StrategySourceCard],
        *,
        max_document_frequency: float,
    ) -> None:
        if not cards or len({card.card_id for card in cards}) != len(cards):
            raise ValueError("lexical audit requires unique non-empty cards")
        if not 0.0 < max_document_frequency <= 1.0:
            raise ValueError("max_document_frequency must be in (0, 1]")
        self.cards = tuple(cards)
        raw_tokens = tuple(_tokens(card.retrieval_text) for card in cards)
        document_frequency = Counter(token for tokens in raw_tokens for token in tokens)
        active_tokens = {
            token
            for token, count in document_frequency.items()
            if count / len(cards) <= max_document_frequency
        }
        self.card_tokens = tuple(tokens & active_tokens for tokens in raw_tokens)
        self.active_tokens = frozenset(active_tokens)
        self.by_token: dict[str, set[int]] = defaultdict(set)
        self.by_dialogue: Counter[str] = Counter()
        for index, (card, tokens) in enumerate(zip(self.cards, self.card_tokens, strict=True)):
            self.by_dialogue[card.source_dialogue_id] += 1
            for token in tokens:
                self.by_token[token].add(index)

    def rank(
        self,
        *,
        query_text: str,
        excluded_dialogue_id: str,
        top_k: int,
    ) -> tuple[int, int, tuple[tuple[StrategySourceCard, float, int], ...]]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        candidate_count = len(self.cards) - self.by_dialogue[excluded_dialogue_id]
        if candidate_count < top_k:
            raise ValueError("fewer fold-exclusive cards than diagnostic top_k")
        query_tokens = _tokens(query_text) & self.active_tokens
        overlapping_indices: set[int] = set()
        for token in query_tokens:
            overlapping_indices.update(self.by_token.get(token, ()))
        overlapping_indices = {
            index
            for index in overlapping_indices
            if self.cards[index].source_dialogue_id != excluded_dialogue_id
        }
        def scored_rows() -> Iterable[tuple[float, str, int]]:
            for index in overlapping_indices:
                card_tokens = self.card_tokens[index]
                intersection_count = len(query_tokens & card_tokens)
                union_count = len(query_tokens) + len(card_tokens) - intersection_count
                score = intersection_count / union_count if union_count else 0.0
                if score:
                    yield score, self.cards[index].card_id, index

        scored = heapq.nsmallest(
            top_k,
            scored_rows(),
            key=lambda item: (-item[0], item[1]),
        )

        if len(scored) < top_k:
            already = {index for _score, _card_id, index in scored}
            zero_indices = sorted(
                (
                    index
                    for index, card in enumerate(self.cards)
                    if index not in already and card.source_dialogue_id != excluded_dialogue_id
                ),
                key=lambda index: self.cards[index].card_id,
            )
            scored.extend((0.0, self.cards[index].card_id, index) for index in zero_indices)

        selected = tuple(
            (
                self.cards[index],
                score,
                _word_count(self.cards[index].guidance_text)
                + _word_count(self.cards[index].example_response),
            )
            for score, _card_id, index in scored[:top_k]
        )
        return candidate_count, len(overlapping_indices), selected


def build_rs_zero_outcome_census(
    *,
    states: Sequence[RSDecisionState],
    cards: Sequence[StrategySourceCard],
    diagnostic_top_k: int = 4,
    diagnostic_max_document_frequency: float = 0.2,
) -> tuple[RSCensusRow, ...]:
    """Audit leave-dialogue-out availability without generating outcomes."""

    if not states:
        raise ValueError("RS census requires states")
    index = _LexicalAuditIndex(
        cards,
        max_document_frequency=diagnostic_max_document_frequency,
    )
    rows: list[RSCensusRow] = []
    for state in states:
        candidate_count, nonzero_count, selected = index.rank(
            query_text=state.query_text,
            excluded_dialogue_id=state.source_dialogue_id,
            top_k=diagnostic_top_k,
        )
        current = state.current_user_text
        rows.append(
            RSCensusRow(
                state_id=state.state_id,
                source_dialogue_id=state.source_dialogue_id,
                source_split=state.source_split,
                decision_turn_index=state.decision_turn_index,
                visible_dialogue_sha256=_sha256_text(state.visible_dialogue_text),
                query_text_sha256=_sha256_text(state.query_text),
                current_user_text_sha256=_sha256_text(current),
                visible_turn_count=state.visible_turn_count,
                query_turn_count=state.query_turn_count,
                current_user_turn_count=state.current_user_turn_count,
                query_word_count=_word_count(state.query_text),
                current_user_word_count=_word_count(current),
                candidate_count_after_leave_dialogue_out=candidate_count,
                nonzero_lexical_overlap_candidate_count=nonzero_count,
                diagnostic_candidate_ids=tuple(card.card_id for card, _score, _words in selected),
                diagnostic_lexical_jaccards=tuple(score for _card, score, _words in selected),
                diagnostic_injected_word_counts=tuple(
                    words for _card, _score, words in selected
                ),
                advice_request_visible=bool(_ADVICE_REQUEST_RE.search(current)),
                listen_only_visible=bool(_LISTEN_ONLY_RE.search(current)),
                no_probing_visible=bool(_NO_PROBING_RE.search(current)),
            )
        )
    return tuple(rows)
