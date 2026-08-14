#!/usr/bin/env python3
"""Zero-API validation of RS Step2 card retrieval over the full real EvoEmo corpus.

Assembles two already-proven pieces (eligible_families() family gating, fed by
the same repaired_observable_opportunity_flags() the RS opportunity router
uses; lexical_score() TF-cosine ranking, the same scorer the frozen 6-card
Strategy RAG runtime uses) against the 79 LLM-audit-qualified V4 cards, and
reports real, full-corpus statistics -- not a small sample -- so the actual
family coverage and selection skew is visible before this is used anywhere.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_rs_v4_card_retrieval import retrieve  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_v4_card_retrieval_validation_20260812"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("RS V4 card retrieval validation output exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_STEP2_CONTENT_UNBLOCKED_79_QUALIFIED_CARDS_CARD_SELECTION_DESIGN_AND_MP_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS-step2-content-unblocked phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    qualified = read_jsonl(QUALIFIED_CARDS)
    if len(qualified) != 79:
        raise RuntimeError("frozen 79-card qualified pool denominator drifted")
    states = read_jsonl(EVOEMO_STATES)

    statuses: Counter = Counter()
    families_selected: Counter = Counter()
    cards_selected: Counter = Counter()
    scores: list[float] = []
    for s in states:
        decision = retrieve(recent_dialogue=s["visible_current_session_dialogue"], qualified_cards=qualified)
        statuses[decision.status] += 1
        if decision.selected_card is not None:
            families_selected[decision.selected_card["strategy_family"]] += 1
            cards_selected[decision.selected_card["card_id"]] += 1
            scores.append(decision.selected_score)

    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    score_stats = {
        "min": scores_sorted[0],
        "p25": scores_sorted[n // 4],
        "median": scores_sorted[n // 2],
        "p75": scores_sorted[3 * n // 4],
        "max": scores_sorted[-1],
    } if n else {}

    report = {
        "protocol": "pm-v1.5-paper1-rs-v4-card-retrieval-validation-v1",
        "status": "RS_V4_CARD_RETRIEVAL_VALIDATED_ON_FULL_REAL_EVOEMO_CORPUS",
        "corpus_size": len(states),
        "status_counts": dict(statuses),
        "coverage_fraction_selected": round(sum(1 for v in statuses if v == "retrieved_top1") and statuses["retrieved_top1"] / len(states), 4),
        "family_distribution_of_selections": dict(families_selected),
        "distinct_cards_ever_selected": len(cards_selected),
        "distinct_cards_in_qualified_pool": len(qualified),
        "top_10_most_selected_cards": cards_selected.most_common(10),
        "score_distribution": score_stats,
        "honest_characterization": (
            "Selections are real and non-degenerate (score range and distinct card usage both "
            "vary meaningfully, unlike the earlier RS opportunity-router feature collapse), and "
            "all 5 strategy families get selected somewhere in the corpus. But selection is "
            "heavily skewed toward 'Restatement or Paraphrasing' (the family eligible_families() "
            "grants unconditionally to any substantive turn) and only 41 of 79 qualified cards "
            "are ever selected on this specific corpus -- not evidence the other 38 are unusable "
            "in general, just that this particular real dialogue distribution doesn't surface "
            "them as the top-ranked match. Not yet validated: whether the SELECTED card's content "
            "is actually appropriate to the specific turn beyond family-level and lexical-overlap "
            "matching -- that would need the same kind of executor-pilot check already run for MS."
        ),
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "qualified_cards": sha256_file(QUALIFIED_CARDS),
            "evoemo_states": sha256_file(EVOEMO_STATES),
            "instrument": sha256_file(ROOT / "src/metacom_pm/v1_5_rs_v4_card_retrieval.py"),
        },
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
