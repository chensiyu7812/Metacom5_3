#!/usr/bin/env python3
"""Audit whether failed-G4B3 MP consensus rows support a diagnostic-only OOF."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json  # noqa: E402

LABELS = ROOT / "outputs/pm_v1_5_paper1_v3_g4b3_mp_pre_adjudication_20260811/mp_consensus_labels.jsonl"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811/private_case_key.jsonl"
G3 = ROOT / "outputs/pm_v1_5_paper1_v3_g3_candidate_surface_audit_20260811/candidate_surface_diagnostics_unlabeled.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_mp_consensus_diagnostic_oof_readiness_audit_20260811"


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    labels = rows(LABELS)
    private = {row["case_key"]: row for row in rows(PRIVATE) if row["component"] == "MP"}
    g3 = {(row["state_id"], row["actual_rank1_id"]): row for row in rows(G3) if row["component"] == "MP" and row["candidate_present"]}
    if len(labels) != 204 or len({row["case_key"] for row in labels}) != 204:
        raise RuntimeError("label grain is not 204 unique MP cases")
    joined = []
    for label in labels:
        key = private[label["case_key"]]
        feature = g3[(label["state_id"], label["actual_rank1_id"])]
        joined.append({
            **label,
            "profile_field": key["proxy_flags"]["profile_field"],
            "redundant": bool(key["proxy_flags"]["exact_profile_value_already_visible"]),
            "candidate_age_sessions": feature["candidate_age_sessions"],
            "scope_match_level": feature["scope_match_level"],
            "selection_score": feature["selection_score"],
            "top1_top2_margin": feature["top1_top2_margin"],
            "strict_past_pool_count": feature["strict_past_pool_count"],
        })
    resolved = [row for row in joined if row["primary_binary_label"] is not None]
    unresolved = [row for row in joined if row["primary_binary_label"] is None]
    field_rows = []
    for field in sorted({row["profile_field"] for row in joined}):
        segment = [row for row in joined if row["profile_field"] == field]
        seg_resolved = [row for row in segment if row["primary_binary_label"] is not None]
        counts = Counter(row["primary_binary_label"] for row in seg_resolved)
        field_rows.append({
            "profile_field": field, "cases": len(segment), "resolved": len(seg_resolved),
            "resolution_rate": len(seg_resolved) / len(segment),
            "on": counts[1], "off": counts[0],
            "groups": len({row["split_group_key"] for row in segment}),
        })
    group_rows = []
    for group in sorted({row["split_group_key"] for row in joined}):
        segment = [row for row in joined if row["split_group_key"] == group]
        seg_resolved = [row for row in segment if row["primary_binary_label"] is not None]
        counts = Counter(row["primary_binary_label"] for row in seg_resolved)
        group_rows.append({
            "split_group_key": group, "cases": len(segment), "resolved": len(seg_resolved),
            "resolution_rate": len(seg_resolved) / len(segment), "on": counts[1], "off": counts[0],
        })
    pair_counts = Counter((row["reviewer_a_decision"], row["reviewer_b_decision"]) for row in joined)
    allowed_feature_names = [
        "profile_field", "redundant", "candidate_age_sessions", "scope_match_level",
        "selection_score", "top1_top2_margin", "strict_past_pool_count",
    ]
    checks = {
        "grain_unique_204": len(labels) == len({row["case_key"] for row in labels}) == 204,
        "private_join_complete_one_to_one": len(private) == 204 and len(joined) == 204,
        "g3_feature_join_complete": len(joined) == 204,
        "resolved_capacity_136": len(resolved) == 136,
        "both_classes_min_32": Counter(row["primary_binary_label"] for row in resolved)[0] >= 32 and Counter(row["primary_binary_label"] for row in resolved)[1] >= 32,
        "all_17_groups_resolved": len({row["split_group_key"] for row in resolved}) == 17,
        "each_class_at_least_8_groups": all(len({row["split_group_key"] for row in resolved if row["primary_binary_label"] == label}) >= 8 for label in (0, 1)),
        "no_raw_identity_or_profile_value_features": set(allowed_feature_names).isdisjoint({"runtime_owner_key", "state_id", "raw_profile_value", "candidate_text", "user_name"}),
        "original_measurement_fail_preserved": len(unresolved) == 68,
    }
    field_rates = [row["resolution_rate"] for row in field_rows]
    group_rates = [row["resolution_rate"] for row in group_rows]
    risk_findings = [
        {
            "severity": "HIGH", "finding": "measurement_not_reproducible_for_formal_labels",
            "evidence": "G4B3 agreement gates failed; 68/204 cases unresolved.",
            "impact": "Consensus rows cannot be promoted to formal Paper-1 labels or used to claim construct validity."
        },
        {
            "severity": "MEDIUM", "finding": "consensus_selection_is_not_missing_completely_at_random",
            "evidence": f"Field resolution rates range {min(field_rates):.3f}-{max(field_rates):.3f}; group rates range {min(group_rates):.3f}-{max(group_rates):.3f}.",
            "impact": "Diagnostic OOF estimates learnability on the easier consensus-resolved subpopulation, not all public MP opportunities."
        },
        {
            "severity": "LOW", "finding": "diagnostic_capacity_and_group_integrity_are_adequate",
            "evidence": "136 resolved rows: OFF=84, ON=52, all 17 connected groups; class group coverage OFF=15, ON=12.",
            "impact": "One outcome-blind, diagnostic-only grouped OOF is statistically executable without row-level leakage."
        },
    ]
    audit = {
        "protocol": "pm-v1.5-paper1-v3-mp-consensus-diagnostic-oof-readiness-audit-v1",
        "status": "MP_CONSENSUS_DIAGNOSTIC_OOF_INTERPRETABLE_FORMAL_LABEL_ROUTE_REMAINS_FAIL",
        "intended_use": "diagnostic-only grouped OOF to test whether frozen identity-free features contain cross-user signal",
        "forbidden_interpretation": "formal label PASS, full MP opportunity performance, paper claim, threshold selection, or generator authorization",
        "counts": {"cases": 204, "resolved": 136, "unresolved": 68, "on": 52, "off": 84, "groups": 17},
        "reviewer_pair_counts": {f"{a}__{b}": n for (a, b), n in sorted(pair_counts.items())},
        "field_rows": field_rows, "group_rows": group_rows,
        "feature_schema": {"allowed": allowed_feature_names, "categorical": ["profile_field"], "raw_identity_forbidden": True},
        "checks": checks, "failed_checks": [key for key, value in checks.items() if not value],
        "risk_findings": risk_findings,
        "decision": {
            "diagnostic_oof_may_be_separately_designed": all(checks.values()),
            "formal_oof_authorized": False,
            "one_run_only": True,
            "threshold_or_feature_change_after_predictions": False,
            "required_split": "leave-one-connected-group-out",
            "required_comparators": ["prevalence-only", "field-only transparent rule"],
        },
        "inputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in (LABELS, PRIVATE, G3)},
        "api_calls": 0, "pm_fit": False,
    }
    OUT.mkdir(parents=True, exist_ok=False)
    write_json(OUT / "report.json", audit)

    field_sql = "WITH field_audit(profile_field,cases,resolved,resolution_rate,on_count,off_count,groups) AS (VALUES\n" + ",\n".join(
        f"('{row['profile_field']}',{row['cases']},{row['resolved']},{row['resolution_rate']},{row['on']},{row['off']},{row['groups']})" for row in field_rows
    ) + "\n) SELECT * FROM field_audit;"
    source = {"id": "src_mp_audit", "label": "Frozen MP consensus-readiness audit", "query": {"engine": "SQLite", "language": "sql", "sql": field_sql, "description": "Profile-field resolution and class capacity from the frozen 204-case MP dual review.", "executed_at": "2026-08-11T00:00:00+09:00", "tables_used": ["field_audit"], "filters": ["MP only", "204 frozen public cases", "no adjudication"], "metric_definitions": ["Resolution rate = exact resolved consensus / reviewed cases within profile field."]}}
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1, "surface": "report", "title": "MP 共识标签：可做诊断 OOF，但不能作为正式标签通过",
            "description": "G4B3 失败后的数据质量、选择偏差和诊断性学习价值审计。", "generatedAt": "2026-08-11T00:00:00+09:00",
            "sources": [source],
            "charts": [{"id": "field_resolution", "title": "各 profile field 的共识覆盖率", "subtitle": "204 个冻结 MP cases；柱高为 exact resolved consensus 比例", "type": "bar", "dataset": "field_rows", "encodings": {"x": {"field": "profile_field", "type": "nominal", "label": "Profile field"}, "y": {"field": "resolution_rate", "type": "quantitative", "label": "共识覆盖率", "format": "percent"}, "tooltip": [{"field": "cases", "type": "quantitative", "label": "Cases"}, {"field": "on", "type": "quantitative", "label": "ON"}, {"field": "off", "type": "quantitative", "label": "OFF"}]}, "valueFormat": "percent", "layout": "full", "sourceId": "src_mp_audit"}],
            "tables": [{"id": "field_table", "title": "字段级容量与选择偏差", "subtitle": "Exact counts；用于判断 consensus-only 子集的运输范围", "dataset": "field_rows", "defaultSort": {"field": "cases", "direction": "desc"}, "density": "spacious", "sourceId": "src_mp_audit", "columns": [{"field": "profile_field", "label": "字段", "type": "text"}, {"field": "cases", "label": "Cases", "format": "number"}, {"field": "resolved", "label": "Resolved", "format": "number"}, {"field": "resolution_rate", "label": "覆盖率", "format": "percent"}, {"field": "on", "label": "ON", "format": "number"}, {"field": "off", "label": "OFF", "format": "number"}, {"field": "groups", "label": "Groups", "format": "number"}]}],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# MP 共识标签：可做诊断 OOF，但不能作为正式标签通过", "layout": "full"},
                {"id": "summary", "type": "markdown", "sourceId": "src_mp_audit", "body": "## 技术结论：运行一次诊断 OOF 有价值，但研究主张仍被阻断\n\n136/204 条形成 exact resolved consensus，包含 ON=52、OFF=84，并覆盖全部 17 个 connected groups；这足以测试冻结低容量特征是否存在跨用户信号。原 G4B3 一致性 FAIL 和 68 条 unresolved 必须保留，因此诊断结果只能代表较容易的共识子群，不能成为正式 MP 标签或论文结论。", "layout": "full"},
                {"id": "selection", "type": "markdown", "sourceId": "src_mp_audit", "body": f"## 共识筛选不是完全随机缺失\n\n不同 profile field 的共识覆盖率范围为 {min(field_rates):.1%}–{max(field_rates):.1%}，不同 connected group 为 {min(group_rates):.1%}–{max(group_rates):.1%}。因此只在 136 条上得到的 OOF 性能必须解释为 high-confidence semantic scope，而不是全部 MP opportunity。", "layout": "full"},
                {"id": "chart", "type": "chart", "chartId": "field_resolution", "layout": "full"},
                {"id": "table", "type": "table", "tableId": "field_table", "layout": "full"},
                {"id": "definitions", "type": "markdown", "body": "## 数据、grain 与特征边界\n\n分析单位是 `state × MP × actual Rank-1`。标签仅来自两位 reviewer 的 `SUITABLE/SUITABLE` 或 `NOT/NOT`；其他组合均 unresolved。诊断模型只允许 profile field 类型、current redundancy、candidate age、scope match、retrieval score/margin 和严格过去池规模；用户 ID、原始 profile value、姓名和原始候选文本禁止进入特征。", "layout": "full"},
                {"id": "method", "type": "markdown", "body": "## 方法与稳健性\n\n审计对 204 条 label rows、204 条 private mapping 和 G3 outcome-blind diagnostics 做一对一完整性检查。所有 17 groups 在 resolved 子集中出现，OFF/ON 分别覆盖 15/12 groups。诊断阶段必须使用 leave-one-connected-group-out；不得把 136 行当 136 个独立用户，也不得在看到预测后改变特征或阈值。", "layout": "full"},
                {"id": "limits", "type": "markdown", "body": "## 限制：它回答可学习性，不回答正式有效性\n\n若 diagnostic OOF 失败，可直接停止 MP 自动标签路线；若成功，只说明高置信语义子群存在可预测结构，仍需真正的 source-aware 双人标注或新的前瞻构念合同才能支持正式 OOF。任何结果都不能回写 G4B3 的失败门。", "layout": "full"},
                {"id": "next", "type": "markdown", "body": "## 下一步\n\n1. 冻结一次 leave-one-group-out diagnostic OOF 和 prevalence/field-only comparators。\n2. 只报告连续概率、AUC、balanced accuracy、Brier 与 17-group bootstrap，不按结果选阈值。\n3. 成功后再决定是否投入真正双人 source-aware 标注；失败则 MP 保持 OFF，转向独立 MS/ME 人工标签路线。", "layout": "full"},
                {"id": "questions", "type": "markdown", "body": "## 尚待回答\n\n- 冻结的 identity-free 特征能否跨 connected group 预测 consensus-only suitability？\n- 一致性失败主要来自构念本身，还是 B reviewer 的系统性宽松？\n- 若诊断信号存在，人类双评能否把适用边界稳定扩展到 unresolved cases？", "layout": "full"}
            ]
        },
        "snapshot": {"version": 1, "generatedAt": "2026-08-11T00:00:00+09:00", "status": "ready", "datasets": {"field_rows": field_rows}, "accessIssues": []},
        "sources": [source]
    }
    write_json(OUT / "artifact.json", artifact)
    write_json(OUT / "source_notes.json", {"audience": "technical", "delivery_mode": "html", "chart_map": [{"section": "selection bias", "question": "Does consensus coverage differ by profile field?", "family": "comparison", "type": "bar", "fields": ["profile_field", "resolution_rate"], "takeaway": "consensus selection is not uniform", "palette_policy": "single-root preferred"}], "required_structure_mapping": {"technical_summary": "summary", "key_findings": ["selection", "chart", "table"], "scope_and_definitions": "definitions", "methodology": "method", "limitations": "limits", "recommended_next_steps": "next", "further_questions": "questions"}})
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
