"""B30-FINAL Part A: stable-kinship MP recovery -- implementation blocker report.

Zero-outcome, Codex-B lane, diagnostic only. B30-FINAL's brief authorizes
adding new stable-kinship Profile Memory candidates only if an exact,
mechanical, reproducible rule for separating a stable relationship-existence
fact from situational relationship narration has already been
researcher-approved somewhere in tracked GitHub authority. This module
re-derives (never hand-copies, so it cannot silently drift from the live
compiler) the two already-committed zero-outcome findings that bear on that
question -- B21's ``mp_extraction_audit`` and B29's
``candidate_definition_decision_surface`` -- and confirms neither one
contains such a rule, then emits a formal ``IMPLEMENTATION BLOCKER --
RESEARCHER DECISION REQUIRED`` report per AGENTS.md's drift-prevention
clause.

This module never modifies ``memory/mp.py``, never adds a stable-kinship MP
candidate, and never reads any gold/answer/observation/reference-summary
field. The "one authorized stable-kinship MP rebuild" language quoted below
is transcribed for traceability only, from a Codex-A-owned draft packet on a
different branch this lane does not read or modify at build time -- this
module itself only inspects the two Codex-B artifacts above plus the live
compiler via ``mp_extraction_audit.build_audit_report``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metacom_pm.paper1.data.memory_source import MemorySourceUser, Target
from metacom_pm.paper1.features.candidate_definition_decision_surface import (
    build_candidate_definition_decision_surface,
)
from metacom_pm.paper1.features.mp_extraction_audit import build_audit_report

BLOCKER_ID = "b30_stable_kinship_mp_extraction_rule"


def build_stable_kinship_mp_blocker_report(
    users: tuple[MemorySourceUser, ...], targets: tuple[Target, ...], evo_path: Path
) -> dict[str, Any]:
    mp_audit = build_audit_report(users)
    surface = build_candidate_definition_decision_surface(users, targets, evo_path)

    family = mp_audit["expansion_diagnostic_proposal"]["family_relationship"]
    surface_family = surface["mp_conversation_proposal"]["category_summary"]["family_relationship"]
    primary_mp = mp_audit["primary_compiler"]

    return {
        "protocol": "pm-paper1-b30-stable-kinship-mp-blocker-v1",
        "status": "IMPLEMENTATION_BLOCKER_RESEARCHER_DECISION_REQUIRED",
        "blocker_id": BLOCKER_ID,
        "outcome_calls": 0,
        "task": "B30-FINAL Part A: stable-kinship MP recovery",
        "missing_exact_rule": (
            "No tracked authority file (the 9 files listed in AGENTS.md -- "
            "the execution-reconciliation override, the frozen research "
            "program, the official-evaluation-priority doc, the execution "
            "blueprint, the training contract, and their machine-readable "
            "JSON contracts) specifies an exact, mechanical, reproducible "
            "rule for separating a stable relationship-EXISTENCE profile "
            "fact ('has a mother') from a situational event narrated using "
            "a relationship term ('my parents just showed up unannounced'). "
            "The closest authority text is the execution blueprint's MP "
            "candidate description, which lists 'stable family/social role' "
            "as one illustrative example of profile-fact content -- that "
            "names a category, not an extraction rule."
        ),
        "prior_findings_confirming_no_rule_exists": {
            "B21_mp_extraction_audit": {
                "reason_no_rule": family["reason_no_rule"],
                "mechanical_precision_first_rule_available": family[
                    "mechanical_precision_first_rule_available"
                ],
                "family_relationship_total_matches": family["total_matches"],
                "identifiability_limitation": mp_audit["identifiability_limitation"],
            },
            "B29_candidate_definition_decision_surface": {
                "narrative_marker_note": surface["mp_conversation_proposal"]["narrative_marker_note"],
                "proposal_list_is_not_formal_coverage_note": surface["mp_conversation_proposal"][
                    "proposal_list_is_not_formal_coverage_note"
                ],
                "family_relationship_narrative_marker_present_count": surface_family[
                    "narrative_marker_present_count"
                ],
                "family_relationship_narrative_marker_absent_count": surface_family[
                    "narrative_marker_absent_count"
                ],
                "researcher_decisions_required_item": next(
                    (item for item in surface["researcher_decisions_required"] if "family_relationship" in item),
                    None,
                ),
            },
        },
        "primary_mp_unchanged": {
            "unique_hit_count": primary_mp["unique_hit_count"],
            "rule": primary_mp["rule"],
        },
        "m2_packet_conflict_note": (
            "project/data/paper1_authority/paper1_m2_decision_packet_draft_v1.json "
            "(Codex-A-owned, DRAFT status, present on "
            "origin/work/paper1-rq1-integration-20260816 -- not part of this "
            "branch's history and not read or modified by this build) records "
            "decision_id 'memory_census' as status "
            "ACTIVE_MEMORY_LANE_INTEGRATED_B30_FINAL_REBUILD_PENDING with "
            "researcher_approval_required=false, and its recommendation text "
            "refers to 'the one authorized stable-kinship MP rebuild'. That "
            "packet is a DRAFT integration proposal, not one of the 9 "
            "AGENTS.md authorities, and it does not itself state an exact "
            "extraction rule -- it assumes this B30-FINAL task supplies one. "
            "B21 and B29 (both already-committed, zero-outcome, Codex-B "
            "findings, reproduced above) instead explicitly and repeatedly "
            "conclude no such mechanical rule exists without semantic "
            "judgment. Per AGENTS.md's drift-prevention clause, this "
            "conflict is reported rather than silently resolved by "
            "inventing a rule to satisfy the draft packet's assumption."
        ),
        "affected": {
            "head": "MP",
            "RQ": "RQ2 (ES-MemEval typed-memory selection) and the -MP component-minus contribution claim",
            "claim": (
                "Any Paper-1 claim that MP mechanism evidence includes a "
                "stable-kinship/family_relationship profile-fact population "
                "beyond the current 3 unique / 3 owner primary-compiler "
                "candidates."
            ),
        },
        "why_132_row_proposal_not_directly_adoptable": (
            "B29.2's 132 family_relationship matches (of 139 total proposal "
            "rows) are explicitly disclosed as a high-recall candidate LIST "
            "for human review, not formal MP coverage. The narrative-marker "
            "flag is a WEAK, non-authoritative diagnostic signal -- absence "
            "means only 'no marker word found', never 'confirmed stable' -- "
            "and even the marker-absent subset "
            f"({surface_family['narrative_marker_absent_count']} of "
            f"{surface_family['total_matches']}) was never claimed to be "
            "precision-first stable: B21's own reading of a sample found "
            "the matched text is 'almost always' a situational narrative "
            "wrapped around a stable existence fact, i.e. high recall but "
            "not precision-first even before the marker heuristic is "
            "applied. Treating all 132 (or even the marker-absent subset) "
            "as adopted MP candidates would inject episodic narrative under "
            "the Profile head, which the MP eligibility rules (same owner, "
            "strict-past, target-time-valid, atomic profile fact) and the "
            "MP vs. MS/ME construct boundary both forbid, and would "
            "constitute exactly the 'invent a stable-vs-situational "
            "heuristic' and 'narrative_marker_absent == stable' moves this "
            "task's brief explicitly prohibits."
        ),
        "minimal_alternatives": [
            (
                "(a) Researcher hand-authors and freezes an explicit, "
                "precision-first lexical/structural rule (e.g. a fixed "
                "possessive-existence pattern set analogous to the existing "
                "'family status' pattern already in memory/mp.py, scoped to "
                "assert only relationship existence and structurally "
                "excluded from firing when the same clause narrates an "
                "event) as new authority text; this lane then re-runs the "
                "same B21/B29 category scan against that exact rule and "
                "reports its precision on the corpus before any candidate "
                "is added."
            ),
            (
                "(b) Researcher accepts the current primary MP compiler "
                "(3 unique / 3 owners) as final for Paper-1 and reports "
                "family_relationship's 132-match volume as a documented MP "
                "identifiability/coverage limitation (public natural "
                "evidence insufficient for a clean expansion -> not "
                "identifiable this round, no synthetic rescue), not an "
                "expansion."
            ),
            (
                "(c) Researcher requests a narrower, still-mechanical "
                "candidate rule restricted to matches judged, by a frozen "
                "and disclosed sampling protocol authored by the researcher "
                "(not this lane), to be pure existence assertions with no "
                "narrated event in the same clause -- viable only if such a "
                "subset can be defined without semantic/LLM judgment or a "
                "hand-curated per-example allowlist, both of which this "
                "task's brief and AGENTS.md forbid for candidate "
                "construction."
            ),
        ],
        "no_synthetic_rescue": True,
        "no_basic_info": True,
        "no_mp_preference": True,
        "no_me_cross_turn_expansion": True,
        "action_taken_this_round": (
            "None: memory/mp.py is unmodified, no stable-kinship MP "
            "candidate was added, and the primary MP candidate pool remains "
            "3 unique / 3 owners (recomputed above, not hardcoded)."
        ),
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_stable_kinship_mp_blocker_manifest(report: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "es_memeval_public_b30_stable_kinship_mp_blocker_v1.json"
    path.write_text(_canonical(report) + "\n", encoding="utf-8")
    return path
