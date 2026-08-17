"""B29.2: conversation-derived MP high-recall proposal audit.

Diagnostic only -- builds on ``mp_extraction_audit.py``'s already-existing,
already-verified ``CATEGORY_PATTERNS``/``category_scan`` (occupation, family_
relationship, residence, study, diagnosis, durable_trait -- exactly the
"occupation、stable family/social role、durable education/residence/
diagnosis" categories this audit round asks for) and adds, per hit:

- the **exact character span** (start, end) within the turn, not just the
  10-before/40-after display window ``category_scan`` already reports;
- a **narrative-marker** weak signal: whether an explicit situational-event
  connective ("just", "recently", "today", "this time", "again", "lately",
  "now") appears anywhere in the same turn.

The narrative-marker signal is deliberately NOT a stable-vs-situational
classifier. B21's diagnostic audit already established that no mechanical,
precision-first rule separates "stable relationship-existence disclosure"
from "situational event narrated using a relationship term" -- that finding
stands; this module does not attempt to overturn it with a new heuristic
(AGENTS.md: no synthetic rescue). The marker is reported purely so a human
reviewer has one more (weak, non-authoritative) cue when reading the
candidate list -- never to auto-classify, auto-adopt, or auto-exclude any
candidate.

This module never modifies ``memory/mp.py``: the primary MP compiler's own
count (3 unique candidates / 3 owners) is unaffected and is not
recomputed here as if it were a competing number -- it is reported
separately, unchanged, for contrast (see ``build_mp_conversation_proposal_
report``'s ``primary_mp_unchanged`` field). ``family_relationship``'s raw
match count (132, expected, verified against the real corpus) is never
treated as if it were 132 additional MP candidates -- proposal-list size is
explicitly not formal coverage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metacom_pm.paper1.data.memory_source import MemorySourceUser
from metacom_pm.paper1.features.mp_extraction_audit import CATEGORY_PATTERNS, category_scan
from metacom_pm.paper1.memory.mp import extract_profile_disclosures

_NARRATIVE_MARKER_PATTERN = re.compile(
    r"\b(?:just|recently|today|this time|again|lately|now)\b", re.IGNORECASE
)

NARRATIVE_MARKER_NOTE = (
    "WEAK, non-authoritative diagnostic signal only -- presence of an "
    "explicit situational-event connective word anywhere in the same turn. "
    "This is NOT a stable-vs-situational classifier: B21 already "
    "established no mechanical, precision-first rule exists to separate "
    "the two for family_relationship (or any other category) without "
    "semantic judgment, and this module does not attempt to overturn that "
    "finding with a new heuristic. A False value here means only 'no "
    "marker word was found', never 'confirmed stable'."
)


def _exact_span_for_category(turn_content: str, category: str) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    for pattern in CATEGORY_PATTERNS[category]:
        match = pattern.search(turn_content)
        if match is not None and (best is None or match.start() < best[0]):
            best = (match.start(), match.end())
    return best


@dataclass(frozen=True)
class MpProposalSpanRow:
    category: str
    owner_id: str
    session_id: str
    turn_idx: int
    span_start: int
    span_end: int
    exact_span_text: str
    narrative_marker_present: bool

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-mp-conversation-proposal-row-v1",
            "category": self.category,
            "owner_id": self.owner_id,
            "session_id": self.session_id,
            "turn_idx": self.turn_idx,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "exact_span_text": self.exact_span_text,
            "narrative_marker_present": self.narrative_marker_present,
        }


def build_mp_conversation_proposal_rows(
    users: tuple[MemorySourceUser, ...],
) -> tuple[MpProposalSpanRow, ...]:
    users_by_owner = {u.owner_id: u for u in users}
    hits = category_scan(users)

    rows: list[MpProposalSpanRow] = []
    for hit in hits:
        user = users_by_owner[hit.owner_id]
        session = user.session_by_id(hit.session_id)
        turn = next(t for t in session.turns if t.idx == hit.turn_idx)
        span = _exact_span_for_category(turn.content, hit.category)
        if span is None:
            # Defensive: category_scan already matched this turn/category,
            # so this should be unreachable -- skip rather than fabricate.
            continue
        start, end = span
        rows.append(
            MpProposalSpanRow(
                category=hit.category,
                owner_id=hit.owner_id,
                session_id=hit.session_id,
                turn_idx=hit.turn_idx,
                span_start=start,
                span_end=end,
                exact_span_text=turn.content[start:end],
                narrative_marker_present=bool(_NARRATIVE_MARKER_PATTERN.search(turn.content)),
            )
        )
    return tuple(rows)


def build_mp_conversation_proposal_report(users: tuple[MemorySourceUser, ...]) -> dict[str, Any]:
    rows = build_mp_conversation_proposal_rows(users)

    primary_unique = len(
        {f"{d.owner_id}:{d.session_id}:{d.turn.idx}" for u in users for d in extract_profile_disclosures(u)}
    )
    primary_owners = len({u.owner_id for u in users if extract_profile_disclosures(u)})

    by_category: dict[str, dict[str, Any]] = {}
    for category in CATEGORY_PATTERNS:
        category_rows = [r for r in rows if r.category == category]
        marker_present = sum(1 for r in category_rows if r.narrative_marker_present)
        by_category[category] = {
            "total_matches": len(category_rows),
            "owners_matched": len({r.owner_id for r in category_rows}),
            "narrative_marker_present_count": marker_present,
            "narrative_marker_absent_count": len(category_rows) - marker_present,
        }

    return {
        "protocol": "pm-paper1-mp-conversation-proposal-report-v1",
        "status": "B29_2_DIAGNOSTIC_PROPOSAL_ONLY_NOT_ADOPTED",
        "outcome_calls": 0,
        "primary_mp_unchanged": {
            "unique_candidate_count": primary_unique,
            "owners_with_candidates": primary_owners,
            "note": (
                "The primary MP compiler (memory/mp.py) is not modified by "
                "this audit -- recomputed here directly for contrast, not "
                "hardcoded."
            ),
        },
        "proposal_list_is_not_formal_coverage_note": (
            "The proposal rows below are a high-recall candidate LIST for "
            "human review, not formal MP coverage. family_relationship's "
            "132 matches (or any other category's count) must never be "
            "read as '132 additional MP candidates' -- see B21's "
            "expansion_diagnostic_proposal (features/mp_extraction_audit.py) "
            "for why no category was mechanically adoptable this round, a "
            "finding this module does not overturn."
        ),
        "narrative_marker_note": NARRATIVE_MARKER_NOTE,
        "category_summary": by_category,
        "proposal_row_count": len(rows),
        "researcher_decision_required": True,
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_mp_conversation_proposal_manifest(
    rows: tuple[MpProposalSpanRow, ...], report: dict[str, Any], out_dir: Path
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "es_memeval_public_mp_conversation_proposal_rows_v1.jsonl"
    rendered_rows = "".join(_canonical(r.to_manifest_row()) + "\n" for r in rows)
    rows_path.write_text(rendered_rows, encoding="utf-8")

    report_path = out_dir / "es_memeval_public_mp_conversation_proposal_audit_v1.json"
    report_path.write_text(_canonical(report) + "\n", encoding="utf-8")

    return {"rows": rows_path, "report": report_path}
