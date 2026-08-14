#!/usr/bin/env python3
"""Materialize the outcome-blind V5.4 paired current-state authoring plan."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-state-variant-authoring-plan-v1"
ANCHORS = ROOT / "outputs/pm_v1_5_v5_4_semantic_development_anchors_20260809/anchors_private.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_factorial_outcome_oracle_learning_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_state_variant_authoring_20260810"
AUTHORS = ("anthropic_claude_haiku_4_5", "openai_gpt_5_mini")
LOW_MODES = {
    "MP": (
        "ALREADY_VISIBLE: the current user turn naturally paraphrases the candidate's material fact, so reopening it would add no specific information",
        "CURRENT_GOAL_UNRELATED: the current need is coherent and emotionally adjacent but the candidate fact cannot materially personalize or constrain the next response",
    ),
    "MS": (
        "ALREADY_VISIBLE: the current user turn naturally restates the specific prior observation, making the observation nonincremental",
        "SELF_CONTAINED: the current turn supplies everything needed for the next response and does not require a continuity bridge",
    ),
    "ME": (
        "ALREADY_VISIBLE: the current user turn naturally states the relevant past action and result, making the episode nonincremental",
        "RESOLVED_OR_DECLINED: the user is reflecting or listening-only and does not currently invite another action, warning, or option based on the episode",
    ),
    "RS": (
        "MOVE_ALREADY_PERFORMED: the shared prefix has already completed the selected card's atomic response move, so repeating it would be redundant",
        "FUNCTION_BOUNDARY: the current user explicitly but naturally sets a boundary incompatible with the selected card's response act",
    ),
}
HIGH_MODES = {
    "MP": "INCREMENTAL: the current user turn leaves a concrete personalization or constraint slot that this exact verified profile/relationship fact can fill without restating the fact",
    "MS": "INCREMENTAL: the current turn has a specific continuity gap that this exact prior observation can bridge without the user restating it",
    "ME": "INCREMENTAL: the current turn leaves a present action, warning, or option whose framing can change because of this exact past episode/action-result, without restating that episode",
    "RS": "INCREMENTAL: the selected card's one atomic response move fits the current dialogue phase, has not already occurred, and is not declined",
}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    authorization = contract["current_authorization"]
    if not authorization["state_variant_authoring"] or authorization["new_response_effect_calls"]:
        raise RuntimeError("contract does not authorize authoring-only execution")
    anchors = _jsonl(ANCHORS)
    if len(anchors) != 48 or Counter(row["component"] for row in anchors) != Counter({component: 12 for component in LOW_MODES}):
        raise RuntimeError("expected 12 frozen anchors per component")
    packet = []
    private = []
    audit: dict[str, Counter[str]] = defaultdict(Counter)
    for row in anchors:
        component = str(row["component"])
        ordinal = int(row["family_ordinal"])
        author_index = (ordinal - 1) % 2
        author = AUTHORS[author_index]
        low_mode = LOW_MODES[component][((ordinal - 1) // 2) % len(LOW_MODES[component])]
        # Four-position Latin pattern: within each component and each author,
        # incremental appears in A exactly three times and in B three times.
        high_in_a = (ordinal - 1) % 4 in {0, 3}
        roles = {
            "A": HIGH_MODES[component] if high_in_a else low_mode,
            "B": low_mode if high_in_a else HIGH_MODES[component],
        }
        pair_id = "v54pair_" + stable_hex(PROTOCOL, row["semantic_family_id"], n=20)
        author_item = {
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "semantic_family_id": row["semantic_family_id"],
            "component": component,
            "assigned_author_endpoint": author,
            "source_dataset": row["source_dataset"],
            "source_owner_id": row.get("user_id") or row["candidate"].get("owner_id") or "PUBLIC_DIALOGUE",
            "anchor_visible_dialogue_for_tone_and_world_fidelity": row["visible_dialogue"],
            "anchor_current_user_text": row["anchor_current_user_text"],
            "frozen_candidate": row["candidate"],
            "frozen_candidate_text": row["candidate_text"],
            "variant_role_A_private_author_instruction": roles["A"],
            "variant_role_B_private_author_instruction": roles["B"],
            "output_task": {
                "shared_prefix": "Write 2-4 short natural turns, alternating user/assistant, ending with assistant. It must fit the public anchor's user/world but must not state the frozen candidate's material contribution.",
                "variant_A_current_user_turn": "Write only the next user turn satisfying role A.",
                "variant_B_current_user_turn": "Write only the next user turn satisfying role B.",
                "minimal_pair": "A and B must share topic, entities, tone, approximate length, and response situation; change only the assigned response-need/boundary factor.",
            },
            "forbidden": [
                "copying a source response",
                "inventing a new past event, diagnosis, identity, owner, result, or future fact",
                "component names or route labels in user-visible text",
                "resource ids, construction labels, evaluator terms, or expected outcomes",
                "an assistant response after the variant current user turn",
                "post-generation concatenation or locked clauses",
            ],
            "effect_quality_risk_function_oracle_outcome_visible": False,
            "development_only": True,
        }
        packet.append(author_item)
        private.append({
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "semantic_family_id": row["semantic_family_id"],
            "component": component,
            "variant_A_assignment": "INCREMENTAL" if high_in_a else "LOW_OPPORTUNITY",
            "variant_B_assignment": "LOW_OPPORTUNITY" if high_in_a else "INCREMENTAL",
            "low_mode": low_mode.split(":", 1)[0],
            "assigned_author_endpoint": author,
            "construction_assignment_is_not_value_gold": True,
            "exclude_from_pm_features_generator_and_effect_judges": True,
        })
        audit[component][author] += 1
        audit[component]["high_in_A" if high_in_a else "high_in_B"] += 1
        audit[component][low_mode.split(":", 1)[0]] += 1
    if len({row["pair_id"] for row in packet}) != 48:
        raise RuntimeError("pair ids are not unique")
    if any(audit[component][author] != 6 for component in LOW_MODES for author in AUTHORS):
        raise RuntimeError("author is not balanced within component")
    if any(
        audit[component][position] != 6
        for component in LOW_MODES
        for position in ("high_in_A", "high_in_B")
    ):
        raise RuntimeError("variant order is not balanced within component")
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "authoring_packet_private.jsonl", packet)
    write_jsonl(OUT / "construction_assignment_private_do_not_join_to_pm_features.jsonl", private)
    report = {
        "protocol": PROTOCOL,
        "status": "AUTHORING_PLAN_COMPLETE_OUTCOME_BLIND",
        "pairs": 48,
        "planned_variants": 96,
        "components": dict(Counter(row["component"] for row in packet)),
        "audit": {key: dict(value) for key, value in audit.items()},
        "anchor_sha256": sha256_file(ANCHORS),
        "contract_sha256": sha256_file(CONTRACT),
        "construction_assignment_physically_separate": True,
        "construction_assignment_is_value_gold": False,
        "actual_rank1_must_be_recomputed_and_refrozen_after_variant_text": True,
        "response_effect_or_judge_calls": 0,
        "api_calls": 0,
    }
    write_json(OUT / "authoring_plan_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
