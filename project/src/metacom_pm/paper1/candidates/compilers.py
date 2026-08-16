"""Deterministic MP/MS/ME candidate compilers.

Each compiler takes a parsed ``UserRecord`` and a ``Target`` (see
``metacom_pm.paper1.data.es_memeval``) and returns zero or more frozen
``CandidateRecord`` contract objects (``metacom_pm.paper1.contracts``),
restricted to memory items whose owning session is strictly past relative to
the target's ``cutoff_rank``.

No candidate is ever excluded here for being low-value, off-topic, or
semantically unlikely to help -- that judgment is out of scope for
construction (AGENTS.md: "not because of semantic non-use, worse adoption, or
a negative effect"). The only exclusion mechanisms are the strict-past cutoff
and the owner-identity check, both mechanical and required by the contract
itself (``CandidateLineage.strict_past``).
"""

from __future__ import annotations

import hashlib

from metacom_pm.paper1.contracts import CandidateLineage, CandidateRecord, Head
from metacom_pm.paper1.data.es_memeval import Target, UserRecord
from metacom_pm.paper1.memory.me import ActionResultEpisode, extract_action_result_episodes
from metacom_pm.paper1.memory.mp import ProfileDisclosure, extract_profile_disclosures
from metacom_pm.paper1.memory.ms import SessionDocument, extract_session_documents

SOURCE_MP = "es_memeval_public_v1_0_0_1427:mp_self_disclosure"
SOURCE_MS = "es_memeval_public_v1_0_0_1427:ms_session_document"
SOURCE_ME = "es_memeval_public_v1_0_0_1427:me_action_result_episode"


def _content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _token_count(content: str) -> int:
    """Whitespace-split word count: a deterministic structural-cost proxy.

    Not the frozen Generator's real tokenizer count (that belongs to Cost
    accounting in ``core/``); this is only used for outcome-blind candidate
    census/feature purposes (AGENTS.md's allowed "structural token cost").
    """

    return len(content.split())


def _require_owner_match(user: UserRecord, target: Target) -> None:
    if user.owner_id != target.owner_id:
        raise ValueError(
            f"owner mismatch: user {user.owner_id!r} does not own target {target.target_id!r} "
            f"(target owner {target.owner_id!r})"
        )


def _build_candidate(
    *,
    head: Head,
    candidate_id: str,
    content: str,
    source: str,
    owner_id: str,
    source_record_ids: tuple[str, ...],
    observed_at: str,
    raw_descriptors: dict[str, str | int | float | bool | None],
) -> CandidateRecord:
    lineage = CandidateLineage(
        source=source,
        owner_id=owner_id,
        source_record_ids=source_record_ids,
        strict_past=True,
        observed_at=observed_at,
        content_sha256=_content_sha256(content),
    )
    return CandidateRecord(
        candidate_id=candidate_id,
        head=head,
        content=content,
        token_count=_token_count(content),
        lineage=lineage,
        raw_descriptors=raw_descriptors,
    )


def _mp_candidate(disclosure: ProfileDisclosure) -> CandidateRecord:
    return _build_candidate(
        head=Head.MP,
        candidate_id=f"mp::{disclosure.owner_id}::{disclosure.session_id}:{disclosure.turn.idx}",
        content=disclosure.content,
        source=SOURCE_MP,
        owner_id=disclosure.owner_id,
        source_record_ids=disclosure.source_record_ids,
        observed_at=disclosure.observed_at,
        raw_descriptors={
            "session_id": disclosure.session_id,
            "session_chronological_rank": disclosure.session_chronological_rank,
            "turn_idx": disclosure.turn.idx,
        },
    )


def _ms_candidate(document: SessionDocument) -> CandidateRecord:
    return _build_candidate(
        head=Head.MS,
        candidate_id=f"ms::{document.owner_id}::{document.session_id}",
        content=document.content,
        source=SOURCE_MS,
        owner_id=document.owner_id,
        source_record_ids=document.source_record_ids,
        observed_at=document.observed_at,
        raw_descriptors={
            "session_id": document.session_id,
            "session_chronological_rank": document.session_chronological_rank,
            "emotion": document.emotion,
            "topic": document.topic,
            "turn_count": document.turn_count,
        },
    )


def _me_candidate(episode: ActionResultEpisode) -> CandidateRecord:
    return _build_candidate(
        head=Head.ME,
        candidate_id=(
            f"me::{episode.owner_id}::{episode.session_id}:"
            f"{episode.action_turn.idx}-{episode.result_turn.idx}"
        ),
        content=episode.content,
        source=SOURCE_ME,
        owner_id=episode.owner_id,
        source_record_ids=episode.source_record_ids,
        observed_at=episode.observed_at,
        raw_descriptors={
            "session_id": episode.session_id,
            "session_chronological_rank": episode.session_chronological_rank,
            "action_turn_idx": episode.action_turn.idx,
            "result_turn_idx": episode.result_turn.idx,
        },
    )


def _is_strict_past(session_id: str, session_rank: int, target: Target) -> bool:
    """Strict past = before the cutoff rank AND not one of the target's own
    premise/context sessions.

    The rank check alone is not enough: ``cutoff_rank`` is defined as
    ``max(context session rank) + 1`` so that every context session's own
    rank is ``< cutoff_rank``. Without the explicit membership exclusion, a
    target's own current/premise session would qualify as its own "strict
    past" MS/ME candidate -- i.e. the current session would be offered back
    to the PM as if it were retrieved memory, which is not memory at all.
    """

    assert target.cutoff_rank is not None
    return session_rank < target.cutoff_rank and session_id not in target.context_session_ids


def compile_mp_candidates(
    user: UserRecord,
    target: Target,
    disclosures: tuple[ProfileDisclosure, ...] | None = None,
) -> tuple[CandidateRecord, ...]:
    _require_owner_match(user, target)
    if target.cutoff_rank is None:
        return ()
    items = disclosures if disclosures is not None else extract_profile_disclosures(user)
    eligible = [d for d in items if _is_strict_past(d.session_id, d.session_chronological_rank, target)]
    return tuple(_mp_candidate(d) for d in eligible)


def compile_ms_candidates(
    user: UserRecord,
    target: Target,
    documents: tuple[SessionDocument, ...] | None = None,
) -> tuple[CandidateRecord, ...]:
    _require_owner_match(user, target)
    if target.cutoff_rank is None:
        return ()
    items = documents if documents is not None else extract_session_documents(user)
    eligible = [d for d in items if _is_strict_past(d.session_id, d.session_chronological_rank, target)]
    return tuple(_ms_candidate(d) for d in eligible)


def compile_me_candidates(
    user: UserRecord,
    target: Target,
    episodes: tuple[ActionResultEpisode, ...] | None = None,
) -> tuple[CandidateRecord, ...]:
    _require_owner_match(user, target)
    if target.cutoff_rank is None:
        return ()
    items = episodes if episodes is not None else extract_action_result_episodes(user)
    eligible = [e for e in items if _is_strict_past(e.session_id, e.session_chronological_rank, target)]
    return tuple(_me_candidate(e) for e in eligible)


def compile_candidate_bundle(
    user: UserRecord,
    target: Target,
    *,
    disclosures: tuple[ProfileDisclosure, ...] | None = None,
    documents: tuple[SessionDocument, ...] | None = None,
    episodes: tuple[ActionResultEpisode, ...] | None = None,
) -> dict[Head, tuple[CandidateRecord, ...]]:
    """All three memory heads' eligible candidates for one target, in one call."""

    return {
        Head.MP: compile_mp_candidates(user, target, disclosures),
        Head.MS: compile_ms_candidates(user, target, documents),
        Head.ME: compile_me_candidates(user, target, episodes),
    }
