#!/usr/bin/env python3
"""Audit grain, blinding, balance, exact evidence, and UI completeness."""

from __future__ import annotations

from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/v1_5/169l_build_v5_4_human_measurement_calibration_packet_v1_5.py"
OUT = ROOT / "outputs/pm_v1_5_v5_4_human_measurement_calibration_v2_20260810"
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import canonical_json, sha256_text, write_json  # noqa: E402
REVIEWERS = ("HUMAN_A", "HUMAN_B")
TASK_COUNTS = {"QUALITY": 24, "FUNCTION": 24, "RISK": 48}
FORBIDDEN_PUBLIC_KEYS = {
    "effect_group_id", "replicate_id", "seed", "arm", "construction_kind",
    "intended_family", "intended_severity", "injected_span", "llm_judgment",
    "reviewer_a", "reviewer_b", "preferred_response", "functional",
}


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def keys_recursive(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(value)
        for child in value.values():
            found.update(keys_recursive(child))
    elif isinstance(value, list):
        for child in value:
            found.update(keys_recursive(child))
    return found


def main() -> None:
    spec = importlib.util.spec_from_file_location("human_packet_builder", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load packet builder")
    builder = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = builder
    spec.loader.exec_module(builder)
    canary, generation, lookup = builder.grouped()
    underlying = builder.build_underlying(canary, generation, lookup)
    source_by_token = {item["token"]: item for task in underlying.values() for item in task}

    private = rows(OUT / "private_blinding_and_construction_key_do_not_share.jsonl")
    private_by_id = {row["blind_item_id"]: row for row in private}
    public_by_reviewer: dict[str, list[dict]] = {}
    template_by_reviewer: dict[str, list[dict]] = {}
    checks: dict[str, bool] = {}
    diagnostics: dict[str, Any] = {}

    all_blind_ids: list[str] = []
    all_public_keys: set[str] = set()
    for reviewer in REVIEWERS:
        public = rows(OUT / f"{reviewer.lower()}_blind_packet.jsonl")
        templates = rows(OUT / f"{reviewer.lower()}_annotation_template.jsonl")
        public_by_reviewer[reviewer] = public
        template_by_reviewer[reviewer] = templates
        ids = [row["blind_item_id"] for row in public]
        all_blind_ids.extend(ids)
        for row in public:
            all_public_keys.update(keys_recursive(row))
        checks[f"{reviewer.lower()}_96_unique_items"] = len(public) == len(set(ids)) == 96
        checks[f"{reviewer.lower()}_task_counts"] = Counter(row["task"] for row in public) == Counter(TASK_COUNTS)
        checks[f"{reviewer.lower()}_template_alignment"] = [row["blind_item_id"] for row in templates] == ids
        checks[f"{reviewer.lower()}_templates_blank"] = all(
            not row["completed"] and row["decision"] == {} and not row["annotator_id"] and not row["notes"]
            for row in templates
        )
        html_text = (OUT / f"{reviewer.lower()}_review.html").read_text()
        checks[f"{reviewer.lower()}_html_embeds_all_items"] = all(item_id in html_text for item_id in ids)
        checks[f"{reviewer.lower()}_html_no_network_dependency"] = not any(token in html_text.lower() for token in ("https://", "http://", "<script src=", "<link rel="))
        checks[f"{reviewer.lower()}_html_has_anchored_rubric_and_ack"] = all(
            token in html_text for token in ("V2 行为锚点", "0 也必须明确选择", "V2_ANCHORED_RUBRIC_READ")
        )
        checks[f"{reviewer.lower()}_risk_has_no_default_zero"] = "if(d[k]===undefined)d[k]=0" not in html_text and '<option value="">明确选择</option>' in html_text

    checks["blind_ids_unique_across_reviewers"] = len(all_blind_ids) == len(set(all_blind_ids)) == 192
    checks["private_key_exactly_one_per_public_item"] = len(private) == len(private_by_id) == 192 and set(private_by_id) == set(all_blind_ids)
    checks["forbidden_public_keys_absent"] = not (all_public_keys & FORBIDDEN_PUBLIC_KEYS)
    diagnostics["forbidden_public_key_intersection"] = sorted(all_public_keys & FORBIDDEN_PUBLIC_KEYS)

    underlying_counts = Counter((row["task"], row["underlying_token"]) for row in private)
    checks["each_underlying_item_has_two_human_views"] = len(underlying_counts) == 96 and set(underlying_counts.values()) == {2}
    reviewer_underlying = {
        reviewer: [private_by_id[row["blind_item_id"]]["underlying_token"] for row in public_by_reviewer[reviewer]]
        for reviewer in REVIEWERS
    }
    same_position = sum(a == b for a, b in zip(reviewer_underlying["HUMAN_A"], reviewer_underlying["HUMAN_B"]))
    checks["reviewer_orders_differ"] = reviewer_underlying["HUMAN_A"] != reviewer_underlying["HUMAN_B"] and same_position <= 5
    diagnostics["same_underlying_item_at_same_position"] = same_position

    literal_failures = []
    hash_failures = []
    for reviewer in REVIEWERS:
        for row in public_by_reviewer[reviewer]:
            key = private_by_id[row["blind_item_id"]]
            source = source_by_token[key["underlying_token"]]
            if sha256_text(source["response"]) != key["response_sha256"]:
                hash_failures.append(row["blind_item_id"])
            for span_id, text in row["response_spans"].items():
                if text not in source["response"]:
                    literal_failures.append((row["blind_item_id"], span_id))
            if row["task"] == "RISK":
                evidence_source = "\n".join(turn["content"] for turn in source["visible_dialogue"])
                if source["authorized_candidate_text"]:
                    evidence_source += "\n" + source["authorized_candidate_text"] + "\n" + canonical_json({key: value for key, value in source["authorized_candidate"].items() if key not in {"resource_id", "owner_id"}})
                for span_id, text in row["authorized_evidence_spans"].items():
                    if text not in evidence_source:
                        literal_failures.append((row["blind_item_id"], span_id))
            if row["task"] == "FUNCTION":
                candidate_source = source["candidate_text"] + "\n" + canonical_json(builder.sanitized_candidate({"actual_rank1_candidate": source["candidate"]}))
                for span_id, text in row["candidate_spans"].items():
                    if text not in candidate_source:
                        literal_failures.append((row["blind_item_id"], span_id))
    checks["response_hash_binding_exact"] = not hash_failures
    checks["all_evidence_spans_literal"] = not literal_failures
    diagnostics["hash_failures"] = hash_failures
    diagnostics["literal_failures"] = literal_failures

    quality_private = [row for row in private if row["task"] == "QUALITY" and row["reviewer_role"] == "HUMAN_A"]
    q_pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in quality_private:
        q_pairs[(row["effect_group_id"], row["replicate_id"])].add(row["arm"])
    checks["quality_exactly_12_complete_pairs"] = len(q_pairs) == 12 and all(arms == {"ON", "OFF"} for arms in q_pairs.values())
    checks["quality_component_balance"] = Counter(row["component"] for row in quality_private) == Counter({component: 6 for component in builder.COMPONENTS})

    function_private = [row for row in private if row["task"] == "FUNCTION" and row["reviewer_role"] == "HUMAN_A"]
    checks["function_all_24_on_and_balanced"] = len(function_private) == 24 and {row["arm"] for row in function_private} == {"ON"} and Counter(row["component"] for row in function_private) == Counter({component: 6 for component in builder.COMPONENTS})

    risk_private = [row for row in private if row["task"] == "RISK" and row["reviewer_role"] == "HUMAN_A"]
    risk_sources = [(row["effect_group_id"], row["replicate_id"], row["arm"]) for row in risk_private]
    controls = [row for row in risk_private if row["construction_kind"] == "ORIGINAL_CONTROL"]
    enriched = [row for row in risk_private if row["construction_kind"] == "SINGLE_RISK_ENRICHMENT"]
    checks["risk_48_unique_source_surfaces"] = len(risk_sources) == len(set(risk_sources)) == 48
    checks["risk_control_enrichment_balance"] = len(controls) == len(enriched) == 24
    checks["risk_family_balance"] = Counter(row["intended_family"] for row in enriched) == Counter({family: 4 for family in builder.RISK_FAMILIES})
    checks["risk_component_balance"] = Counter(row["component"] for row in risk_private) == Counter({component: 12 for component in builder.COMPONENTS})
    checks["risk_arm_balance"] = Counter(row["arm"] for row in risk_private) == Counter({"ON": 24, "OFF": 24})
    checks["risk_injection_spans_exact_once"] = all(source_by_token[row["underlying_token"]]["response"].count(row["injected_span"]) == 1 for row in enriched)

    checks["no_human_annotations_present"] = all(row["completed"] is False for reviewer in REVIEWERS for row in template_by_reviewer[reviewer])
    passed = all(checks.values())
    severity = []
    for name, ok in checks.items():
        if not ok:
            severity.append({"severity": "critical" if name in {"private_key_exactly_one_per_public_item", "forbidden_public_keys_absent", "response_hash_binding_exact", "all_evidence_spans_literal"} else "high", "check": name})
    report = {
        "protocol": "pm-v1.5-v5.4-dual-human-measurement-calibration-audit-v2-anchored",
        "status": "HUMAN_CALIBRATION_PACKET_QA_PASS_READY_FOR_TWO_INDEPENDENT_HUMANS" if passed else "HUMAN_CALIBRATION_PACKET_QA_FAIL_DO_NOT_REVIEW",
        "intended_use": "qualify Q/R/F measurement instruments; never PM training or external evaluation",
        "grain": {
            "underlying_items": 96, "reviewer_views": 192,
            "primary_key": ["reviewer_role", "task", "blind_item_id"],
            "human_reviewers": 2,
        },
        "checks": checks, "diagnostics": diagnostics, "failures": severity,
        "quality": {"underlying_responses": 24, "paired_effects": 12, "component_responses": 6},
        "function": {"underlying_on_responses": 24, "component_responses": 6},
        "risk": {"underlying_responses": 48, "controls": 24, "single_risk_enrichments": 24, "per_family_enrichments": 4},
        "human_annotations_present": False,
        "next": "two humans independently complete their HTML packet and export JSONL; aggregate only after both files are frozen",
    }
    write_json(OUT / "qa_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
