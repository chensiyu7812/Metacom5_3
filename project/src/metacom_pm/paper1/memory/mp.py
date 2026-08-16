"""MP (Profile Memory): seeker-disclosed, text-traceable profile spans.

Design note: the corpus's ``basic_info`` block (name/age/gender/job/
education/nationality/location) looks like an obvious MP source, but it is
dataset-author persona metadata, not something the seeker is shown to have
said -- checking every field against every seeker turn in the corpus finds
zero literal occurrences. Using it as MP content would repeat this project's
own previously-found privileged-input leak (the ESConv ``situation`` field
fed into a PM-visible slot even though it was never actually said in-session).

Instead, MP candidates are built only from seeker turns that deterministically
match a small set of first-person self-disclosure patterns (occupation/role,
age, name, residence, study, family status, a stated diagnosis, or a stated
durable trait). This is intentionally sparse and precision-first: a handful of
mood-adjective false positives (e.g. "I'm a bit worried") are excluded via a
filler-word stoplist on the captured token, not by judging whether a match is
"useful" -- that judgment belongs to the future learned head, not this
compiler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from metacom_pm.paper1.data.es_memeval import Turn, UserRecord

_ROLE_STOPWORDS = frozenset(
    {
        "bit",
        "little",
        "lot",
        "mix",
        "few",
        "couple",
        "bunch",
        "ton",
        "sort",
        "kind",
        "part",
        "way",
    }
)

_ROLE_PATTERN = re.compile(r"\bi'?m\s+(?:a|an)\s+([a-z]+)", re.IGNORECASE)
_WORK_PATTERN = re.compile(r"\bi\s+work\s+(?:as|at|in|for)\s+\S+", re.IGNORECASE)
_AGE_PATTERN = re.compile(r"\b(?:i'?m|i\s+am)\s+\d{1,3}\s*(?:years?\s*old|yo)\b", re.IGNORECASE)
_NAME_PATTERN = re.compile(r"\bmy\s+name\s+is\s+[a-z]+", re.IGNORECASE)
_LIVE_PATTERN = re.compile(r"\bi\s+live\s+in\s+\S+", re.IGNORECASE)
_STUDY_PATTERN = re.compile(
    r"\bi\s+study\b|\bi'?m\s+studying\b|\bi\s+major\s+in\b", re.IGNORECASE
)
_FAMILY_PATTERN = re.compile(
    r"\bi'?m\s+married\b|\bi\s+have\s+(?:a|two|three)\s+(?:kids?|children)\b", re.IGNORECASE
)
_DIAGNOSIS_PATTERN = re.compile(r"\bi'?ve\s+been\s+diagnosed\s+with\s+\S+", re.IGNORECASE)

_ALL_SIMPLE_PATTERNS = (
    _WORK_PATTERN,
    _AGE_PATTERN,
    _NAME_PATTERN,
    _LIVE_PATTERN,
    _STUDY_PATTERN,
    _FAMILY_PATTERN,
    _DIAGNOSIS_PATTERN,
)


def is_profile_disclosure(text: str) -> bool:
    """True if ``text`` deterministically matches a self-disclosure pattern."""

    role_match = _ROLE_PATTERN.search(text)
    if role_match and role_match.group(1).lower() not in _ROLE_STOPWORDS:
        return True
    return any(pattern.search(text) for pattern in _ALL_SIMPLE_PATTERNS)


@dataclass(frozen=True)
class ProfileDisclosure:
    owner_id: str
    session_id: str
    session_chronological_rank: int
    turn: Turn
    observed_at: str

    @property
    def content(self) -> str:
        return self.turn.content

    @property
    def source_record_ids(self) -> tuple[str, ...]:
        return (f"{self.session_id}:{self.turn.idx}",)


def extract_profile_disclosures(user: UserRecord) -> tuple[ProfileDisclosure, ...]:
    """Every seeker turn across all of a user's sessions that self-discloses."""

    disclosures: list[ProfileDisclosure] = []
    for session in user.sessions:
        for turn in session.seeker_turns():
            if is_profile_disclosure(turn.content):
                disclosures.append(
                    ProfileDisclosure(
                        owner_id=user.owner_id,
                        session_id=session.session_id,
                        session_chronological_rank=session.chronological_rank,
                        turn=turn,
                        observed_at=session.timestamp,
                    )
                )
    return tuple(disclosures)
