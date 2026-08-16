"""B16: transparent MP self-disclosure extraction audit -- diagnostic only.

This module never changes what the primary compiler
(``metacom_pm.paper1.memory.mp.extract_profile_disclosures``) extracts. It
exists to answer, honestly and mechanically: what does the current strict
pattern hit exactly, and what other seeker self-disclosure might plausibly
exist in the corpus that a future, deliberately-reviewed rule change could
consider? "3 unique candidates" is this round's *current compiler regression
count*, not an asserted ceiling on how much MP-worthy material exists in the
corpus -- this audit is how that gap gets measured without silently loosening
the primary compiler to chase a bigger number.

Two hard rules, same as the primary compiler:

- Never read ``basic_info`` (dataset-author persona metadata -- not
  something the seeker is shown saying; see memory/mp.py docstring for the
  ESConv-``situation``-leak precedent this project already hit once) as
  candidate content.
- Never read any outcome/gold field. This audit only scans seeker turn text
  that is already legitimately visible to the memory-construction pipeline.

The category patterns below are deliberately *broader/more exploratory* than
the primary compiler's precision-first pattern -- that is the point: they
are not proposed as the new primary rule, they are a census of what a looser
rule *would* catch, for a future round to review before freezing anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from metacom_pm.paper1.data.memory_source import MemorySourceUser
from metacom_pm.paper1.memory.mp import ProfileDisclosure, extract_profile_disclosures

# Broader, exploratory per-category patterns -- NOT used by the primary
# compiler (metacom_pm.paper1.memory.mp.is_profile_disclosure). Grounded by
# scanning the real corpus for each category before writing these (see the
# audit script's report for actual hit counts/examples, not invented from
# intuition).
CATEGORY_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "occupation": (
        re.compile(r"\bi\s+work\s+as\s+(?:a|an)\s+\w+", re.IGNORECASE),
        re.compile(r"\bi\s+work\s+(?:at|for)\s+\w+", re.IGNORECASE),
        re.compile(r"\bmy\s+job\s+is\b", re.IGNORECASE),
        re.compile(r"\bi'?m\s+employed\s+as\b", re.IGNORECASE),
    ),
    "family_relationship": (
        re.compile(
            r"\bmy\s+(?:mother|father|mom|dad|sister|brother|husband|wife|son|daughter|"
            r"parents|grandmother|grandfather|aunt|uncle|fianc[ée])\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bi\s+have\s+(?:a|an|two|three)\s+(?:sister|brother|son|daughter|kid|child|children)\b",
            re.IGNORECASE,
        ),
    ),
    "residence": (
        re.compile(r"\bi\s+live\s+in\s+\w+", re.IGNORECASE),
        re.compile(r"\bi'?m\s+from\s+\w+", re.IGNORECASE),
        re.compile(r"\bi\s+moved\s+to\s+\w+", re.IGNORECASE),
        re.compile(r"\bi'?m\s+based\s+in\s+\w+", re.IGNORECASE),
    ),
    "study": (
        re.compile(r"\bi\s+study\b", re.IGNORECASE),
        re.compile(r"\bi'?m\s+(?:a\s+)?(?:studying|majoring)\s+in\b", re.IGNORECASE),
        re.compile(r"\bi'?m\s+a\s+(?:student|freshman|sophomore|junior|senior)\b", re.IGNORECASE),
        re.compile(r"\bi\s+go\s+to\s+\w+\s+(?:university|college)\b", re.IGNORECASE),
    ),
    "diagnosis": (
        re.compile(r"\bi'?ve\s+been\s+diagnosed\s+with\s+\w+", re.IGNORECASE),
        re.compile(r"\bi\s+have\s+(?:anxiety|depression|adhd|ptsd|ocd|bipolar|insomnia)\b", re.IGNORECASE),
        re.compile(r"\bmy\s+(?:therapist|doctor|psychiatrist)\s+(?:said|told\s+me)\b", re.IGNORECASE),
    ),
    "durable_trait": (
        re.compile(r"\bi'?ve\s+always\s+been\b", re.IGNORECASE),
        re.compile(r"\bi\s+tend\s+to\s+be\b", re.IGNORECASE),
        re.compile(r"\bi'?m\s+(?:such\s+)?(?:a|an)\s+\w+\s+person\b", re.IGNORECASE),
    ),
}


@dataclass(frozen=True)
class CategoryHit:
    category: str
    owner_id: str
    session_id: str
    turn_idx: int
    matched_text: str


@dataclass(frozen=True)
class PrimaryCompilerHit:
    owner_id: str
    session_id: str
    turn_idx: int
    content: str
    source_record_ids: tuple[str, ...]


def primary_compiler_hits(users: tuple[MemorySourceUser, ...]) -> tuple[PrimaryCompilerHit, ...]:
    """The exact spans the production compiler currently extracts, for full disclosure."""

    hits: list[PrimaryCompilerHit] = []
    for user in users:
        for d in extract_profile_disclosures(user):
            hits.append(
                PrimaryCompilerHit(
                    owner_id=d.owner_id,
                    session_id=d.session_id,
                    turn_idx=d.turn.idx,
                    content=d.content,
                    source_record_ids=d.source_record_ids,
                )
            )
    return tuple(hits)


def _first_category_match(text: str) -> tuple[str, re.Match[str]] | None:
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match is not None:
                return category, match
    return None


def category_scan(users: tuple[MemorySourceUser, ...]) -> tuple[CategoryHit, ...]:
    """Every seeker turn matching one of the broader exploratory category patterns.

    Deliberately scans *every* seeker turn in every session (not just
    strict-past-eligible ones relative to some target): this is a
    corpus-level coverage audit, not a per-target candidate compiler.
    """

    hits: list[CategoryHit] = []
    for user in users:
        for session in user.sessions:
            for turn in session.seeker_turns():
                found = _first_category_match(turn.content)
                if found is None:
                    continue
                category, match = found
                hits.append(
                    CategoryHit(
                        category=category,
                        owner_id=user.owner_id,
                        session_id=session.session_id,
                        turn_idx=turn.idx,
                        matched_text=turn.content[max(0, match.start() - 10) : match.end() + 40],
                    )
                )
    return tuple(hits)


def build_audit_report(users: tuple[MemorySourceUser, ...], *, examples_per_category: int = 5) -> dict:
    """The full audit: primary compiler's exact hits + per-category coverage counts/examples.

    outcome_calls is always 0: this reads only seeker turn text already
    parsed by the sanitized loader, never basic_info, never any gold/answer/
    observation field.
    """

    primary_hits = primary_compiler_hits(users)
    primary_hit_keys = {(h.owner_id, h.session_id, h.turn_idx) for h in primary_hits}

    category_hits = category_scan(users)
    by_category: dict[str, list[CategoryHit]] = {cat: [] for cat in CATEGORY_PATTERNS}
    for hit in category_hits:
        by_category[hit.category].append(hit)

    category_summary = {}
    for category, hits in by_category.items():
        owners = sorted({h.owner_id for h in hits})
        already_in_primary = sum(
            1 for h in hits if (h.owner_id, h.session_id, h.turn_idx) in primary_hit_keys
        )
        category_summary[category] = {
            "total_matches": len(hits),
            "owners_matched": len(owners),
            "owner_ids": owners,
            "already_covered_by_primary_compiler": already_in_primary,
            "not_covered_by_primary_compiler": len(hits) - already_in_primary,
            "example_hits": [
                {
                    "owner_id": h.owner_id,
                    "session_id": h.session_id,
                    "turn_idx": h.turn_idx,
                    "matched_text": h.matched_text,
                }
                for h in hits[:examples_per_category]
            ],
        }

    return {
        "protocol": "pm-paper1-mp-self-disclosure-extraction-audit-v1",
        "status": "DIAGNOSTIC_ONLY_NOT_WIRED_INTO_PRIMARY_COMPILER",
        "outcome_calls": 0,
        "reads_basic_info": False,
        "reads_outcome_or_gold_fields": False,
        "primary_compiler": {
            "rule": (
                "seeker turn matches a past-tense 'tried' self-report OR one of the "
                "fixed patterns in metacom_pm.paper1.memory.mp (occupation/work, age, "
                "name, residence, study, family status, stated diagnosis) -- see "
                "is_profile_disclosure() for the exact patterns"
            ),
            "unique_hit_count": len(primary_hits),
            "hits": [
                {
                    "owner_id": h.owner_id,
                    "session_id": h.session_id,
                    "turn_idx": h.turn_idx,
                    "source_record_ids": list(h.source_record_ids),
                    "content": h.content,
                }
                for h in primary_hits
            ],
        },
        "category_coverage_audit": category_summary,
        "next_step_note": (
            "This audit deliberately does not change memory/mp.py this round. "
            "family_relationship in particular has a much larger raw match count "
            "than the other categories (mentioning 'my mother/father/parents' is "
            "common in support-seeking dialogue) -- whether that indicates a stable "
            "profile fact or just situational context is a construct question for "
            "a future rule-freezing round, not something this audit resolves by "
            "itself."
        ),
    }
