"""B20: per-candidate ME construct audit -- action span, result span, linkage
rule, owner/session/turn, for every surviving unique ME candidate.

This module never changes what ``metacom_pm.paper1.memory.me.
extract_action_result_episodes`` extracts; it is a transparent, read-only
disclosure of exactly what the production compiler currently accepts and
*why* each candidate qualifies under the mechanical linkage rule (see
``memory/me.py`` module docstring for the full B11/B20 repair history:
required action complement after "tried", same-sentence result-relation
match, question-context exclusion, no cross-turn supporter-suggestion
pairing, no candidate-id blacklist).

``pattern`` is currently always ``"self_reported_same_turn"`` -- ME has no
second pattern this round (the cross-turn supporter-suggestion pattern was
permanently removed in B11 for lacking a mechanical action-identity link).
This module reports whatever pattern each surviving episode actually carries
rather than hard-coding one, so a future properly-linked pattern would show
up here automatically without an edit to this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from metacom_pm.paper1.data.memory_source import MemorySourceUser
from metacom_pm.paper1.memory.me import ActionResultEpisode, extract_action_result_episodes

LINKAGE_RULE_DESCRIPTIONS: dict[str, str] = {
    "self_reported_same_turn": (
        "same seeker turn: a past-tense \"tried\"/\"tried\" self-report with a "
        "non-empty action complement immediately after it (not bare "
        "\"tried,\"), followed -- within the same sentence only (search never "
        "crosses a '.'/'!'/'?') -- by an explicit result-relation clause "
        "(a back-referring subject pronoun + helped/worked/helps/works/"
        "helpful, an explicit negation, \"ended in/up\", or \"made me/them/it "
        "...\"). Any match inside a question (containing sentence ends in "
        "'?') is discarded. No cross-turn supporter-suggestion pairing and no "
        "per-candidate ID blacklist are used anywhere in this rule."
    ),
}


@dataclass(frozen=True)
class MeCandidateAuditRow:
    """One surviving ME candidate, fully disclosed for manual review."""

    owner_id: str
    session_id: str
    turn_idx: int
    pattern: str
    linkage_rule: str
    action_span: tuple[int, int]
    action_text: str
    action_span_sha256: str
    result_span: tuple[int, int]
    result_text: str
    result_span_sha256: str

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-me-candidate-audit-row-v1",
            "owner_id": self.owner_id,
            "session_id": self.session_id,
            "turn_idx": self.turn_idx,
            "pattern": self.pattern,
            "linkage_rule": self.linkage_rule,
            "action_span": list(self.action_span),
            "action_text": self.action_text,
            "action_span_sha256": self.action_span_sha256,
            "result_span": list(self.result_span),
            "result_text": self.result_text,
            "result_span_sha256": self.result_span_sha256,
        }


def _audit_row(episode: ActionResultEpisode) -> MeCandidateAuditRow:
    return MeCandidateAuditRow(
        owner_id=episode.owner_id,
        session_id=episode.action_session_id,
        turn_idx=episode.action_turn.idx,
        pattern=episode.pattern,
        linkage_rule=LINKAGE_RULE_DESCRIPTIONS.get(
            episode.pattern, f"undocumented pattern {episode.pattern!r} -- add a LINKAGE_RULE_DESCRIPTIONS entry"
        ),
        action_span=episode.action_span,
        action_text=episode.action_text,
        action_span_sha256=episode.action_span_sha256,
        result_span=episode.result_span,
        result_text=episode.result_text,
        result_span_sha256=episode.result_span_sha256,
    )


def build_me_candidate_audit_rows(users: tuple[MemorySourceUser, ...]) -> tuple[MeCandidateAuditRow, ...]:
    """Every surviving unique ME candidate corpus-wide, one row each.

    "Unique" here means one row per (owner, session, turn, action_span,
    result_span) -- exactly the same identity the primary compiler treats as
    one candidate (see ``candidates/compilers.py``'s ME content-hash
    dedup); this function does not itself deduplicate further because
    ``extract_action_result_episodes`` already yields at most one episode per
    qualifying turn.
    """

    rows: list[MeCandidateAuditRow] = []
    for user in users:
        for episode in extract_action_result_episodes(user):
            rows.append(_audit_row(episode))
    return tuple(rows)


def build_me_candidate_audit_report(users: tuple[MemorySourceUser, ...]) -> dict[str, Any]:
    """The full B20 audit deliverable: every surviving candidate, fully disclosed.

    outcome_calls is always 0: this reads only seeker turn text already
    parsed by the sanitized loader, never any gold/answer/observation field.
    """

    rows = build_me_candidate_audit_rows(users)
    by_owner: dict[str, int] = {}
    for row in rows:
        by_owner[row.owner_id] = by_owner.get(row.owner_id, 0) + 1

    return {
        "protocol": "pm-paper1-me-candidate-audit-report-v1",
        "status": "B20_ME_CONSTRUCT_REPAIR_PER_CANDIDATE_AUDIT",
        "outcome_calls": 0,
        "reads_outcome_or_gold_fields": False,
        "construct_summary": (
            "B20: ME requires an explicit, self-contained seeker action (a "
            "past-tense 'tried' self-report with a real action complement), "
            "an explicit user-observed result, and an action->result link "
            "that is mechanical (same-sentence result-relation match, never a "
            "cross-turn temporal-only pairing, never a per-candidate ID "
            "blacklist). See memory/me.py module docstring for the full "
            "repair history, including the two counter-examples this round "
            "added as regression tests (bare 'tried,' with no action "
            "complement; a same-turn but different-sentence 'which helps' "
            "referring to a different subject)."
        ),
        "surviving_unique_candidate_count": len(rows),
        "surviving_candidates_by_owner": by_owner,
        "linkage_rule_descriptions": dict(LINKAGE_RULE_DESCRIPTIONS),
        "candidates": [row.to_manifest_row() for row in rows],
    }
