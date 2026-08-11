#!/usr/bin/env python3
"""Build the canonical technical-report artifact for V5.3 measurement repair."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import write_json  # noqa: E402


DIR = ROOT / "outputs/pm_v1_5_v5_3_dual_reviewer_calibration_20260810"
OUT = ROOT / "outputs/pm_v1_5_v5_3_measurement_repair_report_20260810"


def main() -> None:
    agreement = json.loads((DIR / "agreement_report.json").read_text())
    diagnostic = json.loads((DIR / "disagreement_diagnostics.json").read_text())
    gate_specs = {
        "candidate_clear_applicability": ("候选适用", 0.80, 0.60),
        "functional_qualified": ("功能做功", 0.80, 0.60),
        "response_preference_direction": ("回复偏好", 0.70, 0.40),
    }
    gate_rows = []
    for key, (label, raw_min, kappa_min) in gate_specs.items():
        metric = agreement["metrics"][key]
        gate_rows.append({
            "metric": label,
            "n": metric["n"],
            "raw_agreement": metric["raw_agreement"],
            "raw_threshold": raw_min,
            "cohen_kappa": metric["cohen_kappa"],
            "kappa_threshold": kappa_min,
            "pass": agreement["gates"][key],
        })
    component_rows = []
    for component in ("MP", "MS", "ME", "RS"):
        segment = diagnostic["segments"][component]
        component_rows.append({
            "component": component,
            "candidate_agreement": segment["candidate"]["raw_agreement"],
            "function_agreement": segment["function"]["raw_agreement"],
            "preference_agreement": segment["preference"]["raw_agreement"],
            "risk_agreement": segment["risk"]["raw_agreement"],
            "fully_labelable_groups": diagnostic[
                "provisionally_fully_labelable_groups_by_component"
            ].get(component, 0),
            "groups": 16,
        })
    gate_sql = """WITH gate_metrics(metric,n,raw_agreement,raw_threshold,cohen_kappa,kappa_threshold,pass) AS (
  VALUES
""" + ",\n".join(
        "    (" + ",".join([
            "'" + row["metric"].replace("'", "''") + "'",
            str(row["n"]),
            repr(row["raw_agreement"]),
            repr(row["raw_threshold"]),
            repr(row["cohen_kappa"]),
            repr(row["kappa_threshold"]),
            "'PASS'" if row["pass"] else "'FAIL'",
        ]) + ")"
        for row in gate_rows
    ) + "\n)\nSELECT * FROM gate_metrics;"
    component_sql = """WITH component_metrics(component,candidate_agreement,function_agreement,preference_agreement,risk_agreement,fully_labelable_groups,groups) AS (
  VALUES
""" + ",\n".join(
        "    (" + ",".join([
            "'" + row["component"] + "'",
            repr(row["candidate_agreement"]),
            repr(row["function_agreement"]),
            repr(row["preference_agreement"]),
            repr(row["risk_agreement"]),
            str(row["fully_labelable_groups"]),
            str(row["groups"]),
        ]) + ")"
        for row in component_rows
    ) + "\n)\nSELECT * FROM component_metrics;"
    connection = sqlite3.connect(":memory:")
    try:
        cursor = connection.execute(gate_sql)
        columns = [item[0] for item in cursor.description]
        gate_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor = connection.execute(component_sql)
        columns = [item[0] for item in cursor.description]
        component_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()
    source_agreement = {
        "id": "src_agreement",
        "label": "V5.3 dual-reviewer agreement report",
        "query": {
            "engine": "SQLite",
            "language": "sql",
            "sql": gate_sql,
            "description": "Materialize the three frozen agreement gates from the validated agreement report.",
            "executed_at": "2026-08-10T00:00:00+09:00",
            "tables_used": ["gate_metrics"],
            "filters": ["64 outcome-hidden groups; 16 per component; prior 32-group audit excluded"],
            "metric_definitions": [
                "Raw agreement = identical collapsed labels / reviewed units.",
                "Cohen kappa uses the two reviewers' observed marginal label distributions."
            ]
        }
    }
    source_diagnostic = {
        "id": "src_diagnostic",
        "label": "V5.3 reviewer disagreement diagnostics",
        "query": {
            "engine": "SQLite",
            "language": "sql",
            "sql": component_sql,
            "description": "Materialize component-segmented agreement and consensus-support rows from the disagreement diagnostic.",
            "executed_at": "2026-08-10T00:00:00+09:00",
            "tables_used": ["component_metrics"],
            "filters": ["same frozen 64-group calibration panel"],
            "metric_definitions": [
                "Provisionally fully labelable requires both reviewers to call the candidate clear, at least 2/3 replicates functionally qualified, all 3 risk-safe, and all 3 preference labels mutually agreed."
            ]
        }
    }
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "V5.3 测量修复：PM 训练仍不应启动",
            "description": "正式 576 组失败后的双 reviewer 校准、标签可信度与下一步决策。",
            "generatedAt": "2026-08-10T00:00:00+09:00",
            "sources": [source_agreement, source_diagnostic],
            "charts": [
                {
                    "id": "chart_gate_gap",
                    "title": "三项测量一致率与冻结门槛",
                    "subtitle": "候选与功能 n=64/192；偏好 n=192；所有门均未通过",
                    "type": "bar",
                    "dataset": "gate_metrics",
                    "encodings": {
                        "x": {"field": "metric", "type": "nominal", "label": "测量"},
                        "y": {
                            "fields": ["raw_agreement", "raw_threshold"],
                            "type": "quantitative",
                            "label": "一致率",
                            "format": "percent"
                        },
                        "tooltip": [
                            {"field": "n", "type": "quantitative", "label": "分母"},
                            {"field": "cohen_kappa", "type": "quantitative", "label": "Cohen κ"}
                        ]
                    },
                    "valueFormat": "percent",
                    "layout": "full",
                    "sourceId": "src_agreement"
                }
            ],
            "tables": [
                {
                    "id": "table_component_agreement",
                    "title": "组件级一致率与可用支持",
                    "subtitle": "每组件 16 组、48 replicate；exact values 用于定位失败层",
                    "dataset": "component_metrics",
                    "defaultSort": {"field": "fully_labelable_groups", "direction": "desc"},
                    "density": "spacious",
                    "sourceId": "src_diagnostic",
                    "columns": [
                        {"field": "component", "label": "组件", "type": "text"},
                        {"field": "candidate_agreement", "label": "候选一致", "format": "percent"},
                        {"field": "function_agreement", "label": "功能一致", "format": "percent"},
                        {"field": "preference_agreement", "label": "偏好一致", "format": "percent"},
                        {"field": "risk_agreement", "label": "风险一致", "format": "percent"},
                        {"field": "fully_labelable_groups", "label": "暂可标组", "format": "number"},
                        {"field": "groups", "label": "总组数", "format": "number"}
                    ]
                },
                {
                    "id": "table_gate_metrics",
                    "title": "冻结门的完整数值",
                    "subtitle": "raw agreement 与 Cohen κ 同时达标才允许进入后续标签支持审计",
                    "dataset": "gate_metrics",
                    "defaultSort": {"field": "raw_agreement", "direction": "desc"},
                    "density": "spacious",
                    "sourceId": "src_agreement",
                    "columns": [
                        {"field": "metric", "label": "测量", "type": "text"},
                        {"field": "n", "label": "分母", "format": "number"},
                        {"field": "raw_agreement", "label": "一致率", "format": "percent"},
                        {"field": "raw_threshold", "label": "一致率门槛", "format": "percent"},
                        {"field": "cohen_kappa", "label": "Cohen κ", "format": "number"},
                        {"field": "kappa_threshold", "label": "κ 门槛", "format": "number"},
                        {"field": "pass", "label": "通过", "type": "text"}
                    ]
                }
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# V5.3 测量修复：PM 训练仍不应启动", "layout": "full"},
                {"id": "summary", "type": "markdown", "sourceId": "src_agreement", "body": "## 技术结论：不是样本总数不足，而是可靠标签不足\n\n两位独立 reviewer 已完成 64 组、192 个 replicate 的 outcome-blind 校准，但候选适用、功能做功和 ON/OFF 偏好三个预冻结门全部失败。当前不能把旧 576 组 Q/F 或任一单 reviewer 判断用于 PM 训练。最安全的结论是：V5.3 已定位到测量层和标签支持层，尚未恢复可学习性。", "layout": "full"},
                {"id": "gate_intro", "type": "markdown", "sourceId": "src_agreement", "body": "## 三个核心测量门均未达到启动线\n\n候选一致率为 73.4%（门槛 80%）、功能一致率为 67.2%（门槛 80%）、偏好一致率为 63.0%（门槛 70%）；对应 κ 分别只有 0.065、0.236、0.184。低 κ 与方向性偏差说明分歧不是少量随机噪声。", "layout": "full"},
                {"id": "gate_chart", "type": "chart", "chartId": "chart_gate_gap", "layout": "full"},
                {"id": "gate_table", "type": "table", "tableId": "table_gate_metrics", "layout": "full"},
                {"id": "component_intro", "type": "markdown", "sourceId": "src_diagnostic", "body": "## RS 与 MP 的边界最不稳定，20/64 组暂时满足完整共识\n\n组件切分后，ME 的候选、功能和偏好一致率相对最高；RS 只有 1/16 组暂时满足完整共识条件，MP 的候选一致率仅 56.3%。四组件合计只有 20/64 组可进入下一步人工/中央裁决候选池，仍不能直接训练。", "layout": "full"},
                {"id": "component_table", "type": "table", "tableId": "table_component_agreement", "layout": "full"},
                {"id": "definitions", "type": "markdown", "body": "## 这次到底测了什么\n\n**候选适用**回答 actual Rank-1 是否对当前回应有明确增量；**功能做功**回答 ON 回复是否真正利用该资源完成其组件功能；**回复偏好**只比较即时支持质量；**风险**记录两臂绝对事件和资源归因。四者互不替代。未知、分歧、未保存 raw reply 或未验风险均为 `UNRESOLVED`，不是 OFF gold。分析 grain 为候选 64 个 effect group，F/Q/R 为 192 个 replicate。", "layout": "full"},
                {"id": "method", "type": "markdown", "body": "## 方法：先冻结身份，再打开旧 outcome key\n\n64 组从正式 panel 中按组件、候选类型、fold、cluster 与 redundancy 诊断平衡抽取，排除了先前 32 组单 reviewer 审计。Claude Haiku 4.5 与 GPT-5 mini 独立评审；证据通过枚举 ID 选择并由本地程序还原 exact span。两份 64 组账本完成、schema 验证和哈希冻结后，分析器才打开旧 outcome key。", "layout": "full"},
                {"id": "limitations", "type": "markdown", "sourceId": "src_diagnostic", "body": "## 限制与稳健性：共识仍高度偏向 ON\n\nReviewer B 系统性更宽松：candidate clear 58/64 vs 49/64，F qualified 155/192 vs 118/192，ON better 154/192 vs 121/192。即使只取一致标签，MS 的偏好共识仍是 ON 31 次、OFF 1 次、tie 1 次，缺乏可学习的双向边界。多数票或简单平均会掩盖而不是解决这个问题。", "layout": "full"},
                {"id": "next", "type": "markdown", "body": "## 下一步：先拆 evaluator，再构造公共数据上的双向语义支持\n\n1. 把 candidate、F、Q、R 拆成四个互盲 evaluator，禁止一个综合 prompt 让构念相互影响。\n2. 在未使用的公共状态上冻结新的 outcome-hidden 校准样本，定向覆盖 valid-applicable、valid-redundant、valid-not-useful 与明确边界；wrong-owner/time 只计 retrieval，不做 PM gold。\n3. 只保留双 reviewer 一致或中央裁决后的 resolved 标签；逐 head 检查至少 12 个独立 cluster、ON/OFF 双向支持和最多 3 个有效参数。\n4. 通过 grouped nested cross-fitting 后，合格 head 才进入原 16 动作 projector；未合格 head 固定 OFF 或透明规则。", "layout": "full"},
                {"id": "questions", "type": "markdown", "body": "## 尚待回答的问题\n\n- 角色分解后，偏好判断能否达到预冻结一致性门？\n- 公共真实状态能否提供足够的 valid-but-redundant/not-useful 负例，还是必须加入受控 state counterfactual？\n- 哪些组件能形成 partial learned PM，哪些应在第一篇论文中保持透明规则或 OFF？", "layout": "full"}
            ]
        },
        "snapshot": {
            "version": 1,
            "generatedAt": "2026-08-10T00:00:00+09:00",
            "status": "ready",
            "datasets": {
                "gate_metrics": gate_rows,
                "component_metrics": component_rows
            },
            "accessIssues": []
        },
        "sources": [source_agreement, source_diagnostic]
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "artifact.json", artifact)
    write_json(OUT / "source_notes.json", {
        "audience": "technical",
        "delivery_mode": "html",
        "required_structure_mapping": {
            "technical_summary": "summary",
            "key_findings_with_visual_evidence": ["gate_intro", "gate_chart", "component_intro", "component_table"],
            "scope_data_metric_definitions": "definitions",
            "methodology": "method",
            "limitations_uncertainty_robustness": "limitations",
            "recommended_next_steps": "next",
            "further_questions": "questions"
        },
        "chart_map": [{
            "section": "measurement readiness gates",
            "question": "actual raw agreement versus frozen threshold",
            "family": "comparison",
            "type": "grouped bar",
            "fields": ["metric", "raw_agreement", "raw_threshold"],
            "takeaway": "all three gates fail",
            "palette_policy": "hard two-root cap with target neutral/dashed where supported"
        }],
        "omission": "No trend or distribution chart: the evidence is a small set of discrete readiness metrics and component audit rows; tables preserve exact kappa and denominator values."
    })
    print(OUT / "artifact.json")


if __name__ == "__main__":
    main()
