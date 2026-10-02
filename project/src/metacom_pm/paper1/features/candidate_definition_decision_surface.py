"""B29.4: MP/ME candidate-definition decision surface.

Combines the three B29 diagnostic audits (MP source ontology A vs B,
conversation-derived MP high-recall proposal, ME cross-turn high-precision
proposal) into one report. Diagnostic only -- exactly like the B26 outer-
fold packing surface, this is a *surface*, not a decision:

- no winner is selected between MP ontology A and B;
- no PASS/FAIL verdict is declared for any proposal category or candidate;
- no minimum-N sufficiency gate is applied to MP or ME;
- no synthetic rescue is performed for either sparse head;
- every open question this surface raises is explicitly listed as
  requiring a researcher decision, not resolved here.

``outcome_calls`` is 0 throughout -- nothing in this module or its inputs
reads gold/answer/observation/reference-summary/evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metacom_pm.paper1.data.memory_source import MemorySourceUser, Target
from metacom_pm.paper1.features.me_cross_turn_proposal_audit import (
    build_me_cross_turn_proposal_report,
    build_me_cross_turn_proposal_rows,
)
from metacom_pm.paper1.features.mp_conversation_proposal_audit import (
    build_mp_conversation_proposal_report,
    build_mp_conversation_proposal_rows,
)
from metacom_pm.paper1.features.mp_source_ontology_audit import build_mp_source_ontology_report

RESEARCHER_DECISIONS_REQUIRED: tuple[str, ...] = (
    "Whether MP should ever incorporate a persistent-profile-store "
    "ontology (basic_info) at all, given it is unprovable for strict-past "
    "availability and source-side-privileged relative to the official "
    "harness (see mp_source_ontology_audit's ontology B row) -- this "
    "audit does not decide, only documents the tradeoff.",
    "Whether any conversation-derived MP category beyond the current "
    "primary compiler's 7 patterns (occupation/age/name/residence/study/"
    "family status/diagnosis) should be adopted, and if so, how to "
    "mechanically separate stable disclosure from situational narration "
    "for family_relationship specifically (B21's open finding, "
    "unresolved by this round's narrative-marker weak signal).",
    "Whether the ME cross-turn proposal construct (explicit anaphora + "
    "lexical linkage + result clause + bounded window + no competing "
    "antecedent) should ever be promoted into the primary ME compiler, "
    "given it currently surfaces only 1 clean candidate corpus-wide.",
    "What MAX_TURN_IDX_WINDOW and MAX_ANAPHORA_TO_RESULT_GAP values (this "
    "round: 8 and 15) are appropriate if the ME cross-turn proposal is "
    "ever pursued further -- both are this round's own unreviewed choices, "
    "not frozen constants.",
)


def build_candidate_definition_decision_surface(
    users: tuple[MemorySourceUser, ...], targets: tuple[Target, ...], evo_path: Path
) -> dict[str, Any]:
    mp_ontology_report = build_mp_source_ontology_report(users, targets, evo_path)
    mp_proposal_rows = build_mp_conversation_proposal_rows(users)
    mp_proposal_report = build_mp_conversation_proposal_report(users)
    me_proposal_rows = build_me_cross_turn_proposal_rows(users)
    me_proposal_report = build_me_cross_turn_proposal_report(users)

    return {
        "protocol": "pm-paper1-candidate-definition-decision-surface-v1",
        "status": "B29_CANDIDATE_DEFINITION_DECISION_SURFACE_NO_WINNER",
        "outcome_calls": 0,
        "no_winner_note": (
            "No winner is selected between MP source ontology A "
            "(conversation-derived, primary) and B (persistent-profile-"
            "store, proposed) -- both are reported side by side with their "
            "own tradeoffs; ontology B is not adopted by this audit."
        ),
        "no_pass_fail_note": (
            "No PASS/FAIL verdict is declared for any proposal category, "
            "any individual candidate, or either head as a whole."
        ),
        "no_minimum_n_note": (
            "No minimum-N sufficiency gate is applied to MP or ME -- the "
            "execution-reconciliation override already retired every such "
            "gate this project used to have."
        ),
        "no_synthetic_rescue_note": (
            "Neither MP's 3-candidate sparsity nor ME's 3-candidate "
            "sparsity is rescued by loosening a construct, adopting a "
            "proposal wholesale, or using a per-candidate blacklist/"
            "allowlist to hit a target number."
        ),
        "researcher_decisions_required": list(RESEARCHER_DECISIONS_REQUIRED),
        "mp_source_ontology": mp_ontology_report,
        "mp_conversation_proposal": mp_proposal_report,
        "mp_conversation_proposal_row_count": len(mp_proposal_rows),
        "me_cross_turn_proposal": me_proposal_report,
        "me_cross_turn_proposal_row_count": len(me_proposal_rows),
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_candidate_definition_decision_surface(report: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "es_memeval_public_candidate_definition_decision_surface_v1.json"
    path.write_text(_canonical(report) + "\n", encoding="utf-8")
    return path
