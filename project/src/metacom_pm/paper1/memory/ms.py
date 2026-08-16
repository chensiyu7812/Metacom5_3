"""MS (Session/document memory): a strictly-past complete session transcript.

Content is the raw ``role: content`` turn transcript only. The session's
``summary`` (evaluator/dataset-authored) and ``observation`` (evaluator
annotation) fields are never read here -- MS must be the document itself, not
someone else's account of it. ``emotion``/``topic`` corpus labels are exposed
only as non-content descriptors (``raw_descriptors`` on the compiled
candidate), never spliced into the candidate text.
"""

from __future__ import annotations

from dataclasses import dataclass

from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session


@dataclass(frozen=True)
class SessionDocument:
    owner_id: str
    session_id: str
    session_chronological_rank: int
    observed_at: str
    emotion: str
    topic: str
    transcript: str
    turn_count: int

    @property
    def content(self) -> str:
        return self.transcript

    @property
    def source_record_ids(self) -> tuple[str, ...]:
        return (self.session_id,)


def _compile_transcript(session: Session) -> str:
    return "\n".join(f"{turn.role}: {turn.content}" for turn in session.turns)


def extract_session_documents(user: MemorySourceUser) -> tuple[SessionDocument, ...]:
    """One ``SessionDocument`` per session, in chronological order."""

    return tuple(
        SessionDocument(
            owner_id=user.owner_id,
            session_id=session.session_id,
            session_chronological_rank=session.chronological_rank,
            observed_at=session.timestamp,
            emotion=session.emotion,
            topic=session.topic,
            transcript=_compile_transcript(session),
            turn_count=len(session.turns),
        )
        for session in user.sessions
    )
