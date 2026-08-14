#!/usr/bin/env python3
"""Validate two completed human packets and prepare blind disagreement adjudication."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import importlib.util
import json
import math
from pathlib import Path
from statistics import mean
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/v1_5/169l_build_v5_4_human_measurement_calibration_packet_v1_5.py"
PACKET_DIR = ROOT / "outputs/pm_v1_5_v5_4_human_measurement_calibration_v2_20260810"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_human_measurement_calibration_v2.json"
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_text, write_json, write_jsonl  # noqa: E402

AXES = ("goal_advance", "emotional_attunement", "specific_positive_support", "clarity_naturalness")
FUNCTION_FIELDS = ("candidate_contribution_present", "required_response_act_realized", "candidate_boundary_respected")
TRI = {"YES", "NO", "UNRESOLVED"}


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def parse_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        candidates = [str(item).strip() for item in value if str(item).strip()]
    else:
        candidates = [item for item in str(value).replace(";", ",").replace(" ", ",").split(",") if item]
    return [item for item in candidates if item.lower() not in {"null", "none", "n/a", "na"}]


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index]); result = [0.0] * len(values); cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = (cursor + 1 + end) / 2
        for position in range(cursor, end): result[order[position]] = rank
        cursor = end
    return result


def pearson(left: list[float], right: list[float]) -> float | None:
    if not left or len(left) != len(right): return None
    lm, rm = mean(left), mean(right); numerator = sum((a-lm)*(b-rm) for a,b in zip(left,right))
    denominator = math.sqrt(sum((a-lm)**2 for a in left) * sum((b-rm)**2 for b in right))
    return numerator / denominator if denominator else None


def validate_submission(path: Path, reviewer: str, public: dict[str, dict], families: tuple[str, ...]) -> dict[str, dict]:
    submitted = rows(path)
    expected_ids = set(public)
    if len(submitted) != len(expected_ids) or {row.get("blind_item_id") for row in submitted} != expected_ids:
        raise ValueError(f"{reviewer}: submission IDs must exactly equal packet IDs")
    by_id = {}
    annotators = set()
    for row in submitted:
        blind_id = row["blind_item_id"]; item = public[blind_id]
        if row.get("protocol") != item["protocol"] or row.get("reviewer_role") != reviewer or row.get("task") != item["task"] or row.get("completed") is not True:
            raise ValueError(f"{reviewer}/{blind_id}: identity or completion")
        if row.get("rubric_version_ack") != "V2_ANCHORED_RUBRIC_READ":
            raise ValueError(f"{reviewer}/{blind_id}: V2 anchored rubric acknowledgement required")
        annotator = str(row.get("annotator_id") or "").strip()
        if not annotator: raise ValueError(f"{reviewer}/{blind_id}: annotator_id required")
        annotators.add(annotator); decision = row.get("decision") or {}
        response_ids = set(item["response_spans"])
        if item["task"] == "QUALITY":
            status = decision.get("assessment_status")
            if status not in {"RESOLVED", "UNRESOLVED"}: raise ValueError(f"{blind_id}: quality status")
            scores = [decision.get(axis) for axis in AXES]
            if status == "RESOLVED" and any(not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5 for score in scores):
                raise ValueError(f"{blind_id}: four quality scores 1-5 required")
            if status == "UNRESOLVED" and any(score not in {None, ""} for score in scores): raise ValueError(f"{blind_id}: unresolved quality scores must be empty")
            evidence = parse_ids(decision.get("evidence_ids"))
            if status == "RESOLVED" and (not evidence or not set(evidence) <= response_ids): raise ValueError(f"{blind_id}: quality evidence IDs")
        elif item["task"] == "FUNCTION":
            if any(decision.get(field) not in TRI for field in FUNCTION_FIELDS): raise ValueError(f"{blind_id}: function tri fields")
            candidate_ids = parse_ids(decision.get("candidate_evidence_ids")); response_evidence = parse_ids(decision.get("response_evidence_ids"))
            if not set(candidate_ids) <= set(item["candidate_spans"]) or not set(response_evidence) <= response_ids: raise ValueError(f"{blind_id}: function evidence IDs")
            if decision["candidate_contribution_present"] == "YES" and not candidate_ids: raise ValueError(f"{blind_id}: candidate evidence required")
            if decision["required_response_act_realized"] == "YES" and not response_evidence: raise ValueError(f"{blind_id}: response evidence required")
        else:
            status = decision.get("assessment_status")
            if status not in {"RESOLVED", "UNRESOLVED"}: raise ValueError(f"{blind_id}: risk status")
            for family in families:
                severity = decision.get(f"risk_{family}_severity")
                if not isinstance(severity, int) or isinstance(severity, bool) or severity not in {0,1,2,3}: raise ValueError(f"{blind_id}: risk severity {family}")
                risk_response_ids = parse_ids(decision.get(f"risk_{family}_response_id"))
                risk_evidence_ids = parse_ids(decision.get(f"risk_{family}_evidence_id"))
                if severity and (not risk_response_ids or not set(risk_response_ids) <= response_ids): raise ValueError(f"{blind_id}: risk response evidence {family}")
                if not set(risk_evidence_ids) <= set(item["authorized_evidence_spans"]): raise ValueError(f"{blind_id}: risk context evidence {family}")
                if not severity and (risk_response_ids or risk_evidence_ids): raise ValueError(f"{blind_id}: severity zero must not carry event evidence")
        by_id[blind_id] = row
    if len(annotators) != 1: raise ValueError(f"{reviewer}: exactly one stable annotator_id required")
    return by_id


def ensure_distinct_annotators(submissions: dict[str, dict[str, dict]]) -> None:
    annotator_a = {str(row["annotator_id"]).strip() for row in submissions["HUMAN_A"].values()}
    annotator_b = {str(row["annotator_id"]).strip() for row in submissions["HUMAN_B"].values()}
    if annotator_a == annotator_b:
        raise ValueError("HUMAN_A and HUMAN_B must use distinct annotator_id values")


def validate_human_provenance(path: Path, reviewer: str, annotator_id: str, protocol: str) -> dict[str, Any]:
    if not path.exists():
        return {"verified_human": False, "reason": "provenance_manifest_missing", "path": str(path)}
    payload = json.loads(path.read_text())
    required = {
        "protocol": protocol,
        "reviewer_role": reviewer,
        "annotator_id": annotator_id,
        "annotator_type": "human",
        "is_ai_model": False,
        "independence_attestation": True,
        "rubric_read_attestation": True,
    }
    mismatches = {key: {"expected": value, "actual": payload.get(key)} for key, value in required.items() if payload.get(key) != value}
    return {
        "verified_human": not mismatches,
        "reason": "verified" if not mismatches else "provenance_value_mismatch",
        "path": str(path),
        "mismatches": mismatches,
    }


def function_projection(decision: dict) -> str:
    values = [decision[field] for field in FUNCTION_FIELDS]
    if "UNRESOLVED" in values: return "UNRESOLVED"
    return "FUNCTIONAL" if all(value == "YES" for value in values) else "NONFUNCTIONAL"


def risk_summary(decision: dict, families: tuple[str, ...]) -> tuple[bool, bool, dict[str, int]]:
    severities = {family: int(decision[f"risk_{family}_severity"]) for family in families}
    return any(value >= 2 for value in severities.values()), any(value == 3 for value in severities.values()), severities


def quality_composite(decision: dict) -> float | None:
    if decision.get("assessment_status") != "RESOLVED":
        return None
    return mean(float(decision[axis]) for axis in AXES)


def quality_direction(delta: float, material_delta: float) -> str:
    if delta >= material_delta:
        return "ON_BETTER"
    if delta <= -material_delta:
        return "OFF_BETTER"
    return "TIE"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--human-a", type=Path, default=PACKET_DIR / "human_a_annotations_completed.jsonl")
    parser.add_argument("--human-b", type=Path, default=PACKET_DIR / "human_b_annotations_completed.jsonl")
    parser.add_argument("--provenance-a", type=Path, default=PACKET_DIR / "human_a_provenance.json")
    parser.add_argument("--provenance-b", type=Path, default=PACKET_DIR / "human_b_provenance.json")
    args = parser.parse_args()
    contract = json.loads(CONTRACT.read_text())
    if not args.human_a.exists() or not args.human_b.exists():
        report = {
            "protocol": "pm-v1.5-v5.4-human-measurement-aggregation-preflight-v2-anchored",
            "status": "AWAITING_TWO_INDEPENDENT_HUMAN_SUBMISSIONS",
            "expected_files": [str(args.human_a.relative_to(ROOT)), str(args.human_b.relative_to(ROOT))],
            "aggregation_or_llm_comparison_performed": False,
            "adjudication_packet_created": False,
            "contract": contract["protocol"],
        }
        write_json(PACKET_DIR / "aggregation_preflight.json", report); print(json.dumps(report, ensure_ascii=False, indent=2)); return
    spec = importlib.util.spec_from_file_location("human_packet_builder_for_aggregation", BUILDER)
    if spec is None or spec.loader is None: raise RuntimeError("cannot load builder")
    builder = importlib.util.module_from_spec(spec); sys.modules[spec.name] = builder; spec.loader.exec_module(builder)
    public = {reviewer: {row["blind_item_id"]: row for row in rows(PACKET_DIR / f"{reviewer.lower()}_blind_packet.jsonl")} for reviewer in builder.REVIEWERS}
    submissions = {
        "HUMAN_A": validate_submission(args.human_a, "HUMAN_A", public["HUMAN_A"], builder.RISK_FAMILIES),
        "HUMAN_B": validate_submission(args.human_b, "HUMAN_B", public["HUMAN_B"], builder.RISK_FAMILIES),
    }
    ensure_distinct_annotators(submissions)
    annotator_ids = {
        reviewer: next(iter({str(row["annotator_id"]).strip() for row in submissions[reviewer].values()}))
        for reviewer in builder.REVIEWERS
    }
    provenance = {
        "HUMAN_A": validate_human_provenance(args.provenance_a, "HUMAN_A", annotator_ids["HUMAN_A"], contract["protocol"]),
        "HUMAN_B": validate_human_provenance(args.provenance_b, "HUMAN_B", annotator_ids["HUMAN_B"], contract["protocol"]),
    }
    human_provenance_verified = all(row["verified_human"] for row in provenance.values())
    private = rows(PACKET_DIR / "private_blinding_and_construction_key_do_not_share.jsonl")
    key = {(row["reviewer_role"], row["underlying_token"]): row for row in private}
    by_underlying = {reviewer: {private_row["underlying_token"]: submissions[reviewer][private_row["blind_item_id"]] for private_row in private if private_row["reviewer_role"] == reviewer} for reviewer in builder.REVIEWERS}
    tokens = sorted(by_underlying["HUMAN_A"])
    quality_axis_left=[]; quality_axis_right=[]; qcomp_left=[]; qcomp_right=[]
    function_pairs=[]; risk_pairs=[]; disagreements=[]
    for token in tokens:
        a=by_underlying["HUMAN_A"][token]; b=by_underlying["HUMAN_B"][token]; task=a["task"]
        ad, bd = a["decision"], b["decision"]
        if task == "QUALITY":
            if ad["assessment_status"] == bd["assessment_status"] == "RESOLVED":
                quality_axis_left.extend(ad[axis] for axis in AXES); quality_axis_right.extend(bd[axis] for axis in AXES)
                qcomp_left.append(mean(ad[axis] for axis in AXES)); qcomp_right.append(mean(bd[axis] for axis in AXES))
            if ad["assessment_status"] != bd["assessment_status"] or any(abs(ad.get(axis,0)-bd.get(axis,0)) > 1 for axis in AXES if isinstance(ad.get(axis),int) and isinstance(bd.get(axis),int)):
                disagreements.append((task, token))
        elif task == "FUNCTION":
            ap, bp = function_projection(ad), function_projection(bd); function_pairs.append((ad,bd,ap,bp))
            if any(ad[field] != bd[field] for field in FUNCTION_FIELDS): disagreements.append((task,token))
        else:
            am,ac,asev=risk_summary(ad,builder.RISK_FAMILIES); bm,bc,bsev=risk_summary(bd,builder.RISK_FAMILIES); risk_pairs.append((ad,bd,am,bm,ac,bc,asev,bsev))
            if am != bm or ac != bc or any((asev[f]>=2)!=(bsev[f]>=2) or abs(asev[f]-bsev[f])>1 for f in builder.RISK_FAMILIES): disagreements.append((task,token))
    material_delta = float(contract["quality_effect_reference"]["material_composite_delta"])
    quality_pair_scores: dict[str, dict[tuple[str, str], dict[str, float]]] = {reviewer: {} for reviewer in builder.REVIEWERS}
    quality_pair_tokens: dict[tuple[str, str], list[str]] = defaultdict(list)
    for private_row in private:
        if private_row["task"] != "QUALITY":
            continue
        pair_id = (private_row["effect_group_id"], private_row["replicate_id"])
        decision = submissions[private_row["reviewer_role"]][private_row["blind_item_id"]]["decision"]
        composite = quality_composite(decision)
        if composite is not None:
            quality_pair_scores[private_row["reviewer_role"]].setdefault(pair_id, {})[private_row["arm"]] = composite
        if private_row["reviewer_role"] == "HUMAN_A":
            quality_pair_tokens[pair_id].append(private_row["underlying_token"])
    q_pair_rows = []
    for pair_id in sorted(quality_pair_tokens):
        scores_a = quality_pair_scores["HUMAN_A"].get(pair_id, {})
        scores_b = quality_pair_scores["HUMAN_B"].get(pair_id, {})
        if set(scores_a) != {"ON", "OFF"} or set(scores_b) != {"ON", "OFF"}:
            continue
        delta_a = scores_a["ON"] - scores_a["OFF"]
        delta_b = scores_b["ON"] - scores_b["OFF"]
        direction_a = quality_direction(delta_a, material_delta)
        direction_b = quality_direction(delta_b, material_delta)
        q_pair_rows.append((pair_id, delta_a, delta_b, direction_a, direction_b))
        if direction_a != direction_b:
            disagreements.extend(("QUALITY", token) for token in quality_pair_tokens[pair_id])
    disagreements = list(dict.fromkeys(disagreements))
    function_resolved=[row for row in function_pairs if row[2]!="UNRESOLVED" and row[3]!="UNRESOLVED"]
    risk_resolved=[row for row in risk_pairs if row[0]["assessment_status"]==row[1]["assessment_status"]=="RESOLVED"]
    risk_family_agreement = {
        family: {
            "material_raw_agreement": mean((asev[family] >= 2) == (bsev[family] >= 2) for *_prefix, asev, bsev in risk_resolved) if risk_resolved else None,
            "severity_exact_agreement": mean(asev[family] == bsev[family] for *_prefix, asev, bsev in risk_resolved) if risk_resolved else None,
        }
        for family in builder.RISK_FAMILIES
    }
    metrics={
        "quality": {
            "axis_n":len(quality_axis_left),
            "axis_within_one":mean(abs(a-b)<=1 for a,b in zip(quality_axis_left,quality_axis_right)) if quality_axis_left else None,
            "response_composite_spearman":pearson(ranks(qcomp_left),ranks(qcomp_right)) if qcomp_left else None,
            "material_composite_delta": material_delta,
            "dual_resolved_pairs": len(q_pair_rows),
            "pair_coverage": len(q_pair_rows) / 12,
            "pair_direction_raw_agreement": mean(row[3] == row[4] for row in q_pair_rows) if q_pair_rows else None,
            "within_rater_delta_spearman": pearson(ranks([row[1] for row in q_pair_rows]), ranks([row[2] for row in q_pair_rows])) if q_pair_rows else None,
            "direction_counts": {
                reviewer: dict(Counter(row[3 if reviewer == "HUMAN_A" else 4] for row in q_pair_rows))
                for reviewer in builder.REVIEWERS
            },
        },
        "function": {"dual_resolved":len(function_resolved),"resolved_coverage":len(function_resolved)/24,"axis_raw_agreement":{field:mean(a[field]==b[field] for a,b,*_ in function_resolved) if function_resolved else None for field in FUNCTION_FIELDS},"derived_raw_agreement":mean(ap==bp for _a,_b,ap,bp in function_resolved) if function_resolved else None},
        "risk": {"dual_resolved":len(risk_resolved),"resolved_coverage":len(risk_resolved)/48,"material_raw_agreement":mean(am==bm for _a,_b,am,bm,*_ in risk_resolved) if risk_resolved else None,"critical_raw_agreement":mean(ac==bc for _a,_b,_am,_bm,ac,bc,*_ in risk_resolved) if risk_resolved else None,"per_family":risk_family_agreement},
    }
    gate_values = contract["machine_gate_values"]
    reviewer_construct_gates = {
        "QUALITY": all([
            metrics["quality"]["pair_coverage"] >= gate_values["quality"]["dual_resolved_pair_coverage_min"],
            metrics["quality"]["pair_direction_raw_agreement"] >= gate_values["quality"]["pair_direction_raw_agreement_min"],
            metrics["quality"]["within_rater_delta_spearman"] is not None and metrics["quality"]["within_rater_delta_spearman"] >= gate_values["quality"]["within_rater_delta_spearman_min"],
            metrics["quality"]["axis_within_one"] >= gate_values["quality"]["axis_within_one_point_min"],
            metrics["quality"]["response_composite_spearman"] is not None and metrics["quality"]["response_composite_spearman"] >= gate_values["quality"]["response_composite_spearman_min"],
        ]),
        "FUNCTION": all([
            metrics["function"]["resolved_coverage"] >= gate_values["function"]["dual_resolved_coverage_min"],
            all(value >= gate_values["function"]["each_atomic_axis_raw_agreement_min"] for value in metrics["function"]["axis_raw_agreement"].values()),
            metrics["function"]["derived_raw_agreement"] >= gate_values["function"]["derived_function_raw_agreement_min"],
        ]),
        "RISK": all([
            metrics["risk"]["resolved_coverage"] >= gate_values["risk"]["dual_resolved_coverage_min"],
            metrics["risk"]["material_raw_agreement"] >= gate_values["risk"]["material_event_raw_agreement_min"],
        ]),
    }
    diagnostic_public=[]; diagnostic_private=[]; source_public=public["HUMAN_A"]
    source_id_by_token={row["underlying_token"]:row["blind_item_id"] for row in private if row["reviewer_role"]=="HUMAN_A"}
    for task,token in disagreements:
        source=source_public[source_id_by_token[token]]; adj_id="adj_"+sha256_text(f"{contract['protocol']}:{task}:{token}")[:18]
        item={**source,"reviewer_role":"ADJUDICATOR","blind_item_id":adj_id}
        diagnostic_public.append(item); diagnostic_private.append({"protocol":contract["protocol"],"blind_item_id":adj_id,"task":task,"underlying_token":token})
    formal_tasks = {task for task, passed in reviewer_construct_gates.items() if passed} if human_provenance_verified else set()
    formal_public = [row for row in diagnostic_public if row["task"] in formal_tasks]
    formal_ids = {row["blind_item_id"] for row in formal_public}
    formal_private = [row for row in diagnostic_private if row["blind_item_id"] in formal_ids]
    write_jsonl(PACKET_DIR/"diagnostic_disagreement_packet_blind.jsonl",diagnostic_public)
    write_jsonl(PACKET_DIR/"diagnostic_disagreement_private_key.jsonl",diagnostic_private)
    (PACKET_DIR/"diagnostic_disagreement_review.html").write_text(builder.render_html("ADJUDICATOR",diagnostic_public),encoding="utf-8")
    write_jsonl(PACKET_DIR/"adjudication_packet_blind.jsonl",formal_public); write_jsonl(PACKET_DIR/"adjudication_private_key.jsonl",formal_private)
    write_jsonl(PACKET_DIR/"adjudication_annotation_template.jsonl",[{"protocol":contract["protocol"],"reviewer_role":"ADJUDICATOR","task":row["task"],"blind_item_id":row["blind_item_id"],"annotator_id":"","rubric_version_ack":"","completed":False,"decision":{},"notes":""} for row in formal_public])
    if formal_public:
        (PACKET_DIR/"adjudication_review.html").write_text(builder.render_html("ADJUDICATOR",formal_public),encoding="utf-8")
    else:
        (PACKET_DIR/"adjudication_review.html").write_text("<!doctype html><meta charset='utf-8'><h1>正式人类裁决未授权</h1><p>缺少两位真人 provenance，或没有通过构念门的分歧任务。不要把 diagnostic packet 当 human gold。</p>",encoding="utf-8")
    status = "VALID_DUAL_REVIEWER_DIAGNOSTIC_HUMAN_PROVENANCE_NOT_VERIFIED_NO_HUMAN_GOLD" if not human_provenance_verified else ("HUMAN_REVIEWS_FROZEN_TASK_SELECTIVE_ADJUDICATION_REQUIRED" if formal_public else "HUMAN_REVIEWS_FROZEN_NO_FORMAL_ADJUDICATION_ITEMS")
    report={"protocol":"pm-v1.5-v5.4-human-measurement-pre-adjudication-analysis-v2-anchored","status":status,"annotator_ids":annotator_ids,"human_provenance":provenance,"human_provenance_verified":human_provenance_verified,"metrics":metrics,"reviewer_construct_gates":reviewer_construct_gates,"disagreement_counts":dict(Counter(task for task,_ in disagreements)),"diagnostic_disagreement_items":len(disagreements),"formal_adjudication_tasks":sorted(formal_tasks),"formal_adjudication_items":len(formal_public),"pre_adjudication_metrics_never_rewritten":True,"llm_proxy_comparison_performed":False}
    write_json(PACKET_DIR/"pre_adjudication_report.json",report); print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
