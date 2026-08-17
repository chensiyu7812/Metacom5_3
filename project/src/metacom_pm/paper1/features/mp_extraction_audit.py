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
            # B21.1: corrected. This previously (incorrectly) said the rule
            # includes a past-tense "tried" self-report -- that pattern
            # belongs to metacom_pm.paper1.memory.me (ME), not mp.py. MP's
            # is_profile_disclosure() never checks for "tried" at all.
            "rule": (
                "seeker turn matches the role pattern \"I'm a/an <word>\" (word not in "
                "a filler-word stoplist: bit/little/lot/mix/few/couple/bunch/ton/sort/"
                "kind/part/way) OR one of seven fixed patterns in "
                "metacom_pm.paper1.memory.mp: occupation (\"I work as/at/in/for\"), age "
                "(\"I'm/I am <N> years old\"), name (\"my name is\"), residence (\"I "
                "live in\"), study (\"I study\"/\"I'm studying\"/\"I major in\"), family "
                "status (\"I'm married\"/\"I have a/two/three kids\"), or a stated "
                "diagnosis (\"I've been diagnosed with\") -- see is_profile_disclosure() "
                "for the exact regexes"
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
        "expansion_diagnostic_proposal": {
            "status": "DIAGNOSTIC_PROPOSAL_ONLY_NOT_ADOPTED",
            "family_relationship": {
                "total_matches": category_summary["family_relationship"]["total_matches"],
                "finding": (
                    "Reading a sample of real hits (see category_coverage_audit."
                    "family_relationship.example_hits and the corpus scan behind this "
                    "report) shows the pattern reliably finds a stable existence fact "
                    "(\"has parents\"/\"has a mother\"), but the matched text is almost "
                    "always a *situational* narrative wrapped around that fact -- e.g. "
                    "\"My parents just showed up unannounced, and it's really stressing "
                    "me out\" or \"My parents visited recently, and they didn't make it "
                    "easier\" -- not a standalone durable attribute comparable to "
                    "occupation/residence/diagnosis. Adopting the raw match as MP content "
                    "would inject an episodic narrative under the Profile head, blurring "
                    "the MP vs. MS/ME construct boundary rather than adding a genuine "
                    "profile fact."
                ),
                "mechanical_precision_first_rule_available": False,
                "reason_no_rule": (
                    "Distinguishing \"stable relationship-existence disclosure\" from "
                    "\"situational event narrated using a relationship term\" requires "
                    "judging whether the surrounding clause states a fact about the "
                    "relationship itself vs. narrates a transient event -- that is a "
                    "semantic judgment, not a lexical pattern this project can express "
                    "precision-first without an LLM or hand-curated per-example "
                    "blacklist, both forbidden for candidate construction."
                ),
            },
            "occupation_diagnostic": {
                "total_matches": category_summary["occupation"]["total_matches"],
                "finding": (
                    "Only 2 matches corpus-wide, both from the same owner (p10), both "
                    "narrating the same ongoing work-stress situation rather than a bare "
                    "occupation statement (\"I work hard at my job in an office... my job "
                    "is now twice the work\"). Too sparse and too situational to propose "
                    "as an expansion on its own."
                ),
                "mechanical_precision_first_rule_available": False,
            },
            "diagnosis_diagnostic": {
                "total_matches": category_summary["diagnosis"]["total_matches"],
                "finding": (
                    "1 match corpus-wide (\"My therapist said something about self-worth "
                    "the other day\"), and it reports what the *therapist* said, not a "
                    "self-disclosed diagnosis -- would not actually qualify as a stated "
                    "diagnosis even under a looser reading."
                ),
                "mechanical_precision_first_rule_available": False,
            },
        },
        "identifiability_limitation": (
            "B21.3: no fully-enumerable, mechanical, precision-first expansion rule was "
            "found for any of the six audited categories this round. residence and study "
            "have zero corpus matches at all (support-seeking dialogue in this corpus "
            "essentially never states a city or school). occupation and diagnosis are too "
            "sparse and situational to generalize from. family_relationship has real "
            "volume but conflates a stable existence fact with situational narration in a "
            "way this project cannot mechanically separate without semantic judgment. "
            "This is reported as an honest MP identifiability/coverage limitation, not "
            "resolved by loosening the primary compiler -- per AGENTS.md, no synthetic "
            "rescue for a sparse head."
        ),
        "next_step_note": (
            "This audit deliberately does not change memory/mp.py this round. If a "
            "future round wants to pursue family_relationship, the open question is "
            "specifically how to mechanically separate 'stable relationship fact' from "
            "'situational event narrated via a relationship term' -- not whether the "
            "raw match count is large enough to bother with."
        ),
    }
