"""Fail-closed projection of the state available to each Paper-1 head.

This module separates three things that must not be conflated:

* public history used to construct the memory candidate corpus;
* the exact current query/state text allowed to reach PM features;
* audit identities and hashes, which are never model features.

It contains no outcome, reference, future, utility or subjective labels.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import Field, model_validator

from ..contracts import StrictContract, TaskType
from ..data.memory_source import MemorySourceUser, Target, Turn
from ..rs.zero_outcome_census import RSDecisionState

VISIBLE_STATE_PROTOCOL = "pm-paper1-visible-state-projection-v1"
DG_DYNAMIC_QUERY_PROTOCOL = "pm-paper1-rq2-dg-dynamic-query-v1"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sanitized_history_sha256(user: MemorySourceUser) -> str:
    """Hash only fields carried by the public, sanitized runtime artifact."""

    payload = [
        {
            "timestamp": session.timestamp,
            "chronological_rank": session.chronological_rank,
            "turns": [
                {"idx": turn.idx, "role": turn.role, "content": turn.content}
                for turn in session.turns
            ],
        }
        for session in user.sessions
    ]
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return _sha256_text(rendered)


class VisibleStateSource(StrEnum):
    ESCONV_VISIBLE_PREFIX = "esconv_visible_prefix"
    ES_MEMEVAL_STATIC_OFFICIAL_QUERY = "es_memeval_static_official_query"
    ES_MEMEVAL_DG_CURRENT_SEEKER = "es_memeval_dg_current_seeker"


class QueryTiming(StrEnum):
    PRE_SUPPORTER_VISIBLE_PREFIX = "pre_supporter_visible_prefix"
    STATIC_OFFICIAL_QUERY = "static_official_query"
    AFTER_CURRENT_SEEKER_BEFORE_SUPPORTER = "after_current_seeker_before_supporter"


class VisibleStateProjection(StrictContract):
    """Exact model-text surface plus audit-only provenance.

    ``target_id``, source identities and hashes are retained for integrity and
    grouping only.  The only model-text fields are explicitly enumerated in
    ``model_text_fields`` and validated below.
    """

    protocol: str = VISIBLE_STATE_PROTOCOL
    target_id: str = Field(min_length=1, description="Audit only; never a model feature")
    task_type: TaskType
    source: VisibleStateSource
    query_timing: QueryTiming
    pm_query_text: str = Field(min_length=1)
    visible_context_text: str | None = None
    current_user_text: str = Field(min_length=1)
    model_text_fields: tuple[str, ...]
    source_owner_id: str | None = Field(
        default=None, description="Audit/grouping only; never a model feature"
    )
    source_dialogue_id: str | None = Field(
        default=None, description="Audit/leave-dialogue-out only"
    )
    source_history_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    dynamic_dialogue_prefix_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    pm_query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_user_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_context_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    dg_round_index: int | None = Field(default=None, ge=1, le=10)
    dynamic_query_protocol: str | None = None
    history_text_in_pm_state: bool = False
    owner_identity_in_model_features: bool = False
    gold_reference_future_read: bool = False

    @model_validator(mode="after")
    def validate_exact_surface(self) -> "VisibleStateProjection":
        if self.protocol != VISIBLE_STATE_PROTOCOL:
            raise ValueError("visible-state protocol identity mismatch")
        if _sha256_text(self.pm_query_text) != self.pm_query_sha256:
            raise ValueError("pm_query_sha256 does not match exact query text")
        if _sha256_text(self.current_user_text) != self.current_user_sha256:
            raise ValueError("current_user_sha256 does not match exact current-user text")
        if self.visible_context_text is None:
            if self.visible_context_sha256 is not None:
                raise ValueError("context hash cannot exist without context text")
        elif _sha256_text(self.visible_context_text) != self.visible_context_sha256:
            raise ValueError("visible_context_sha256 does not match exact context text")
        if self.owner_identity_in_model_features or self.gold_reference_future_read:
            raise ValueError("identity, gold, reference and future access are forbidden")

        if self.source is VisibleStateSource.ESCONV_VISIBLE_PREFIX:
            expected_fields = ("visible_context_text", "pm_query_text", "current_user_text")
            if self.task_type is not TaskType.ESC_RESPONSE:
                raise ValueError("ESConv state is only valid for ESC response generation")
            if self.query_timing is not QueryTiming.PRE_SUPPORTER_VISIBLE_PREFIX:
                raise ValueError("RS state must be projected before the target supporter turn")
            if not self.visible_context_text or not self.source_dialogue_id:
                raise ValueError("RS state requires visible context and dialogue provenance")
            if not self.visible_context_text.endswith(self.pm_query_text):
                raise ValueError("RS query must be an exact suffix of the visible dialogue prefix")
            if not self.pm_query_text.rstrip().endswith(
                self.current_user_text.splitlines()[-1].strip()
            ):
                raise ValueError("RS query must end at the exact current user turn")
            if self.source_owner_id is not None or self.source_history_sha256 is not None:
                raise ValueError("RS state cannot carry memory-owner/history fields")
            if self.dg_round_index is not None or self.dynamic_query_protocol is not None:
                raise ValueError("RS state cannot carry DG runtime fields")
            if self.dynamic_dialogue_prefix_sha256 is not None:
                raise ValueError("RS state cannot carry DG live-dialogue provenance")
        elif self.source is VisibleStateSource.ES_MEMEVAL_STATIC_OFFICIAL_QUERY:
            expected_fields = ("pm_query_text", "current_user_text")
            if self.task_type not in {TaskType.QA, TaskType.SUMMARY}:
                raise ValueError("static official query is only valid for QA/Summary")
            if self.query_timing is not QueryTiming.STATIC_OFFICIAL_QUERY:
                raise ValueError("QA/Summary must use the official static query timing")
            if self.visible_context_text is not None or self.history_text_in_pm_state:
                raise ValueError("full history is candidate-corpus input, not PM query state")
            if not self.source_owner_id or not self.source_history_sha256:
                raise ValueError("memory state requires audit-only owner/history provenance")
            if self.source_dialogue_id is not None:
                raise ValueError("memory state cannot carry an ESConv dialogue identity")
            if self.dg_round_index is not None or self.dynamic_query_protocol is not None:
                raise ValueError("static memory state cannot carry DG runtime fields")
            if self.dynamic_dialogue_prefix_sha256 is not None:
                raise ValueError("static memory state cannot carry DG live-dialogue provenance")
        else:
            expected_fields = ("pm_query_text", "current_user_text")
            if self.task_type is not TaskType.DIALOGUE_GENERATION:
                raise ValueError("dynamic seeker state is only valid for dialogue generation")
            if self.query_timing is not QueryTiming.AFTER_CURRENT_SEEKER_BEFORE_SUPPORTER:
                raise ValueError("DG query must be captured after seeker and before supporter")
            if self.pm_query_text != self.current_user_text:
                raise ValueError("DG retrieval query must be exactly the current seeker utterance")
            if self.visible_context_text is not None or self.history_text_in_pm_state:
                raise ValueError("DG PM query is current-seeker-only under the frozen protocol")
            if not self.source_owner_id or not self.source_history_sha256:
                raise ValueError("DG state requires audit-only owner/history provenance")
            if self.source_dialogue_id is not None:
                raise ValueError("DG state cannot carry an ESConv dialogue identity")
            if (
                self.dg_round_index is None
                or self.dynamic_query_protocol != DG_DYNAMIC_QUERY_PROTOCOL
            ):
                raise ValueError("DG state requires the frozen round/query protocol")
            if self.dynamic_dialogue_prefix_sha256 is None:
                raise ValueError("DG state requires exact live-dialogue-prefix provenance")

        if self.model_text_fields != expected_fields:
            raise ValueError("model_text_fields must equal the task-authorized text surface")
        return self


def build_rs_visible_state(state: RSDecisionState) -> VisibleStateProjection:
    return VisibleStateProjection(
        target_id=state.state_id,
        task_type=TaskType.ESC_RESPONSE,
        source=VisibleStateSource.ESCONV_VISIBLE_PREFIX,
        query_timing=QueryTiming.PRE_SUPPORTER_VISIBLE_PREFIX,
        pm_query_text=state.query_text,
        visible_context_text=state.visible_dialogue_text,
        current_user_text=state.current_user_text,
        model_text_fields=("visible_context_text", "pm_query_text", "current_user_text"),
        source_dialogue_id=state.source_dialogue_id,
        pm_query_sha256=_sha256_text(state.query_text),
        current_user_sha256=_sha256_text(state.current_user_text),
        visible_context_sha256=_sha256_text(state.visible_dialogue_text),
    )


def _validate_memory_owner_and_cutoff(user: MemorySourceUser, target: Target) -> None:
    if target.owner_id != user.owner_id:
        raise ValueError("target owner does not match sanitized runtime user")
    if target.cutoff_rank != len(user.sessions):
        raise ValueError("target cutoff must bind the full official public history")


def build_static_memory_visible_state(
    user: MemorySourceUser,
    target: Target,
) -> VisibleStateProjection:
    _validate_memory_owner_and_cutoff(user, target)
    if target.task_type not in {TaskType.QA, TaskType.SUMMARY}:
        raise ValueError("static memory projection only accepts QA/Summary targets")
    if target.visible_query_text is None or not target.visible_query_text.strip():
        raise ValueError("QA/Summary require the exact official query text")
    query = target.visible_query_text
    return VisibleStateProjection(
        target_id=target.target_id,
        task_type=target.task_type,
        source=VisibleStateSource.ES_MEMEVAL_STATIC_OFFICIAL_QUERY,
        query_timing=QueryTiming.STATIC_OFFICIAL_QUERY,
        pm_query_text=query,
        current_user_text=query,
        model_text_fields=("pm_query_text", "current_user_text"),
        source_owner_id=user.owner_id,
        source_history_sha256=_sanitized_history_sha256(user),
        pm_query_sha256=_sha256_text(query),
        current_user_sha256=_sha256_text(query),
    )


def build_dg_visible_state(
    user: MemorySourceUser,
    target: Target,
    *,
    round_index: int,
    live_dialogue_turns: tuple[Turn, ...],
) -> VisibleStateProjection:
    _validate_memory_owner_and_cutoff(user, target)
    if target.task_type is not TaskType.DIALOGUE_GENERATION:
        raise ValueError("dynamic DG projection requires a dialogue-generation target")
    if target.visible_query_text is not None:
        raise ValueError("DG static pre-generation query is forbidden")
    if not live_dialogue_turns or live_dialogue_turns[-1].role != "seeker":
        raise ValueError("DG query requires a live dialogue prefix ending in a seeker turn")
    if len({turn.idx for turn in live_dialogue_turns}) != len(live_dialogue_turns):
        raise ValueError("DG live dialogue turn indices must be unique")
    if tuple(turn.idx for turn in live_dialogue_turns) != tuple(
        sorted(turn.idx for turn in live_dialogue_turns)
    ):
        raise ValueError("DG live dialogue turns must be in increasing index order")
    seeker = live_dialogue_turns[-1].content.strip()
    if not seeker:
        raise ValueError("DG current seeker utterance cannot be empty")
    live_prefix = json.dumps(
        [
            {"idx": turn.idx, "role": turn.role, "content": turn.content}
            for turn in live_dialogue_turns
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return VisibleStateProjection(
        target_id=target.target_id,
        task_type=target.task_type,
        source=VisibleStateSource.ES_MEMEVAL_DG_CURRENT_SEEKER,
        query_timing=QueryTiming.AFTER_CURRENT_SEEKER_BEFORE_SUPPORTER,
        pm_query_text=seeker,
        current_user_text=seeker,
        model_text_fields=("pm_query_text", "current_user_text"),
        source_owner_id=user.owner_id,
        source_history_sha256=_sanitized_history_sha256(user),
        dynamic_dialogue_prefix_sha256=_sha256_text(live_prefix),
        pm_query_sha256=_sha256_text(seeker),
        current_user_sha256=_sha256_text(seeker),
        dg_round_index=round_index,
        dynamic_query_protocol=DG_DYNAMIC_QUERY_PROTOCOL,
    )
