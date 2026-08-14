#!/usr/bin/env python3
"""Zero-API source/readiness audit for the three frozen V5.3 external tracks."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402


ESCONV = ROOT / "data/external/ESConv.json"
EVOEMO = ROOT / "data/external/evo_emo.json"
ESCONV_MANIFEST = ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl"
OLD_EVO_PANEL = ROOT / "outputs/pm_v1_5b_final_external_panel_v2/evoemo_panel_private.jsonl"
OLD_ESCONV_PANEL = ROOT / "outputs/pm_v1_5b_final_external_panel_v2/esconv_panel_private.jsonl"
OLD_QA_GOLD = ROOT / "outputs/pm_v1_5_v5_2_external_e2_plan_v1/qa_evaluator_only_gold_private.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_external_complementary_evidence_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_3_external_source_readiness_20260809"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _contains_key(value, denied: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in denied:
                found.add(str(key))
            found.update(_contains_key(item, denied))
    elif isinstance(value, list):
        for item in value:
            found.update(_contains_key(item, denied))
    return found


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    esconv_manifest = _jsonl(ESCONV_MANIFEST)
    split_counts = Counter(row["split"] for row in esconv_manifest)
    excluded_ids = {
        row["dialogue_id"] for row in esconv_manifest
        if row.get("excluded_for_evoemo_overlap")
    }
    test_ids = {
        row["dialogue_id"] for row in esconv_manifest
        if row["split"] == "test" and not row.get("excluded_for_evoemo_overlap")
    }

    users = json.loads(EVOEMO.read_text())
    user_ids = [str(user["id"]) for user in users]
    composite_sessions = set()
    global_session_owners: dict[str, set[str]] = defaultdict(set)
    question_counts = Counter()
    question_total = 0
    for user in users:
        user_id = str(user["id"])
        for session in user["dialog_history"]:
            session_id = str(session["id"])
            composite_sessions.add((user_id, session_id))
            global_session_owners[session_id].add(user_id)
        for group in user["questions"]:
            for question in group["questions"]:
                question_total += 1
                question_counts[str(question["capability"])] += 1

    old_evo_rows = _jsonl(OLD_EVO_PANEL)
    old_esconv_rows = _jsonl(OLD_ESCONV_PANEL)
    old_qa_rows = _jsonl(OLD_QA_GOLD)
    denied_runtime_keys = {
        "questions", "answer", "answers", "evidence", "capability",
        "question_group", "current_session_summary", "current_session_observation",
    }
    old_evo_denied = sorted(
        set().union(*(_contains_key(row.get("runtime_state"), denied_runtime_keys) for row in old_evo_rows))
    )

    source_checks = {
        "contract_is_three_track": set(contract["experiments"]) == {
            "ESConv_response", "EvoEmo_longitudinal_response", "ES_MemEval_QA",
        },
        "esconv_manifest_1300": len(esconv_manifest) == 1300,
        "esconv_split_counts": split_counts == Counter({"train": 934, "validation": 186, "test": 180}),
        "esconv_quarantine_84": len(excluded_ids) == 84,
        "esconv_final_test_169": len(test_ids) == 169,
        "evoemo_18_users": user_ids == [f"p{index}" for index in range(1, 19)],
        "evoemo_401_composite_sessions": len(composite_sessions) == 401,
        "known_shared_raw_session_bound": {
            key: sorted(value) for key, value in global_session_owners.items() if len(value) > 1
        } == {"esc1198": ["p13", "p18"]},
        "evoemo_existing_204_selection_states": (
            len(old_evo_rows) == 204
            and len({row["state_id"] for row in old_evo_rows}) == 204
            and len({row["user_id_private_analysis_only"] for row in old_evo_rows}) == 18
        ),
        "es_memeval_1427_questions": question_total == 1427,
        "es_memeval_five_capabilities": question_counts == Counter({
            "information extraction": 309,
            "user modeling": 306,
            "temporal reasoning": 284,
            "conflict detection": 267,
            "abstention": 261,
        }),
    }
    direct_reuse_checks = {
        "old_esconv_panel_is_not_full_v53_denominator": len(old_esconv_rows) == 122,
        "old_evo_runtime_contains_forbidden_current_summary": old_evo_denied == ["current_session_summary"],
        "old_qa_gold_is_not_full_v53_denominator": len(old_qa_rows) == 418,
    }
    if not all(source_checks.values()) or not all(direct_reuse_checks.values()):
        status = "FAIL_SOURCE_OR_EXPECTED_LEGACY_SHAPE_DRIFT"
    else:
        status = "SOURCE_PASS_V53_REMATERIALIZATION_REQUIRED"
    report = {
        "protocol": "pm-v1.5-v5.3-external-complementary-source-readiness-v1",
        "status": status,
        "source_checks": source_checks,
        "legacy_direct_reuse_findings": {
            "checks": direct_reuse_checks,
            "old_esconv_states": len(old_esconv_rows),
            "required_esconv_states": 169,
            "old_evo_states": len(old_evo_rows),
            "old_evo_forbidden_runtime_keys": old_evo_denied,
            "old_qa_gold_rows": len(old_qa_rows),
            "required_qa_rows": 1427,
        },
        "required_next_materialization": [
            "materialize all 169 ESConv test states without corpus-level situation",
            "reuse only the 204 frozen EvoEmo selection identities and rematerialize visible current prefixes plus strictly-prior private history; do not reuse old runtime_state.current_session_summary",
            "materialize all 1,427 QA questions into a generator-visible question plan and a physically separate evaluator-only answer/evidence/capability mapping",
            "run forbidden-field negative canaries and content-address all final messages before any external generation",
        ],
        "source_counts": {
            "esconv_splits": dict(split_counts),
            "esconv_quarantined": len(excluded_ids),
            "esconv_final_test": len(test_ids),
            "evoemo_users": len(users),
            "evoemo_sessions": len(composite_sessions),
            "evoemo_response_selection_states": len(old_evo_rows),
            "es_memeval_questions": question_total,
            "es_memeval_capabilities": dict(question_counts),
        },
        "source_hashes": {
            "esconv": sha256_file(ESCONV),
            "evoemo": sha256_file(EVOEMO),
            "esconv_manifest": sha256_file(ESCONV_MANIFEST),
            "external_contract": sha256_file(CONTRACT),
            "legacy_evo_selection_panel": sha256_file(OLD_EVO_PANEL),
        },
        "quality_risk_or_external_outcomes_read": False,
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "report.json", report)
    print({"status": status, "source_counts": report["source_counts"], "rematerialization_required": True})


if __name__ == "__main__":
    main()
