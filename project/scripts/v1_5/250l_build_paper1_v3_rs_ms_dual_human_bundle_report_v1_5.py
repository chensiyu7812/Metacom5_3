#!/usr/bin/env python3
"""Build the portable technical-report artifact for the RS+MS human bundle."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811"


def main() -> None:
    report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
    if report["status"] != "DUAL_HUMAN_BLIND_BUNDLE_READY":
        raise RuntimeError("bundle is not ready")
    source = "bundle_audit"
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "RS+MS 双人盲评包：开评前测量审计",
            "description": "Technical readiness audit for the fixed 16-state RS+MS same-stack outcome panel.",
            "generatedAt": "2026-08-11T17:30:00+09:00",
            "sources": [{
                "id": source,
                "label": "RS+MS dual-human bundle machine audit",
                "path": "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811/report.json",
                "query": {
                    "language": "sql",
                    "engine": "DuckDB-compatible audit SQL",
                    "sql": "SELECT construct, v1_n, v2_n, source_visible_v1, source_visible_v2 FROM measurement_surface_audit",
                    "description": "Deterministic audit of the pre-review V1 and repaired V2 presentation surfaces.",
                    "tables_used": [
                        "outputs/pm_v1_5_paper1_v3_rs_ms_same_stack_baseline_plan_20260811/quality_rs_slice_blind.jsonl",
                        "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811/quality_current_context_only_blind_v2.jsonl",
                        "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811/risk_absolute_blind.jsonl",
                        "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811/function_source_aware_blind.jsonl",
                    ],
                    "filters": ["before human review", "zero labels", "zero API", "unchanged responses"],
                    "metric_definitions": [
                        "Quality source visibility means whether strictly-past evidence is displayed to the quality reviewer.",
                        "Position balance counts the anonymous side on which the MS-ON response appears.",
                    ],
                },
            }],
            "charts": [{
                "id": "position_balance",
                "title": "Quality 中 MS-ON 的 A/B 展示位置",
                "subtitle": "V2 仅交换三对的匿名展示顺序；回复文本未改",
                "type": "bar",
                "dataset": "position_balance",
                "sourceId": source,
                "layout": "full",
                "encodings": {
                    "x": {"field": "version_side", "type": "nominal", "label": "盲包版本与位置"},
                    "y": {"field": "count", "type": "quantitative", "label": "MS-ON 对数"},
                },
                "valueFormat": "number",
                "maxRows": 4,
                "question": "A/B 位置是否仍与 MS-ON 混杂？",
                "rationale": "四柱对照直接显示 V1 的 5/11 偏斜及 V2 的 8/8 平衡。",
                "emptyState": "No position audit is available.",
            }],
            "tables": [{
                "id": "construct_separation",
                "title": "三个构念的展示边界",
                "subtitle": "来源只在需要事实或功能归因时显示",
                "dataset": "construct_separation",
                "density": "spacious",
                "sourceId": source,
                "layout": "full",
                "columns": [
                    {"field": "construct", "label": "构念", "type": "text"},
                    {"field": "items", "label": "每位评审项数", "format": "number"},
                    {"field": "past_source_visible", "label": "过去来源可见", "type": "text"},
                    {"field": "decision", "label": "原子决定", "type": "text"},
                ],
            }],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# RS+MS 双人盲评包：开评前测量审计", "layout": "full"},
                {"id": "summary", "type": "markdown", "body": "## 技术结论\n\n**双人盲评包已经可开评，但尚无结果。** 两个会污染结论的展示问题在任何人工标签产生前修复：Quality 不再展示严格过去来源，MS-ON 的匿名位置从 A/B=5/11 平衡为 8/8。16 对 Quality、32 条绝对 Risk 和 16 条 source-aware Function 均通过机器验收；两位评审各自完整评 64 项。", "layout": "full", "sourceId": source},
                {"id": "findings", "type": "markdown", "body": "## 关键发现\n\nV1 Quality 包虽然隐藏动作名称，却展示了记忆来源，会诱导评审把“调用了记忆”当作质量优势。V2 只保留当前对话和匿名回复。第二个问题是 MS-ON 在 B 侧出现 11/16；V2 用稳定哈希交换三对，得到精确 8/8。两项修复都没有读取评测结果，也没有改变回复、policy、selector 或模型。", "layout": "full", "sourceId": source},
                {"id": "chart", "type": "chart", "chartId": "position_balance", "layout": "full"},
                {"id": "table", "type": "table", "tableId": "construct_separation", "layout": "full"},
                {"id": "scope", "type": "markdown", "body": "## 范围与定义\n\n这一步只测已有 16 个 EvoEmo RS-slice states 上的 `RS fixed ON + learned MS` 相对 RS-only。Quality 判断即时支持净方向；Risk 对两臂逐条、逐族记录字面风险；Function 判断过去来源是否对最终回复产生了不能仅由当前对话解释的独立贡献；Cost 由机器计算，不交给人评。", "layout": "full", "sourceId": source},
                {"id": "method", "type": "markdown", "body": "## 方法\n\nHUMAN_A 与 HUMAN_B 使用不同的稳定哈希顺序、完整重叠且独立完成。Quality 必须选择 A 更好、B 更好、等价或 unresolved，并分别引用两臂原文；Risk 六族均显式填 0–3，非零必须给回复证据；Function 只给一个 anchored 类别，同时引用来源和回复。两份原始导出冻结后才允许查看分歧并由第三位真人裁决；不得用多数票覆盖原始 disagreement。", "layout": "full"},
                {"id": "limitations", "type": "markdown", "body": "## 限制与稳健性\n\n目前标签数为 0，因此不能宣称 RS+MS 已经胜过 RS-only。16 个 states 覆盖 8 个 connected groups，只适合受限 same-stack feasibility；它不能替代三个公共数据轨的最终报告。此次修复发生在开评前，所以是前瞻测量纠错，不是看结果后调题。", "layout": "full", "sourceId": source},
                {"id": "next", "type": "markdown", "body": "## 下一步\n\n1. 两位真人分别打开各自离线页面并导出 JSON。\n2. 冻结并校验两份原始文件，再计算 Quality agreement、逐族 Risk agreement 与 Function agreement。\n3. 只对 disagreement 做第三人裁决，原始 A/B 不覆盖。\n4. 解盲后报告 learned 对 RS-only 的 Q/R/F/C，并再映射到 fixed-high、transparent 与 qualified matched-random。", "layout": "full"},
                {"id": "questions", "type": "markdown", "body": "## 尚待回答\n\n- learned MS 的 7 个 ON 是否在 Quality 上至少不劣于 RS-only？\n- 它是否富集 verified Function，同时避免两臂绝对 Risk 增加？\n- 人评 disagreement 是否集中在 current-context echo 或 tentative past-to-current 边界？", "layout": "full"},
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": "2026-08-11T17:30:00+09:00",
            "status": "ready",
            "datasets": {
                "position_balance": [
                    {"version_side": "V1 · A", "count": 5},
                    {"version_side": "V1 · B", "count": 11},
                    {"version_side": "V2 · A", "count": 8},
                    {"version_side": "V2 · B", "count": 8},
                ],
                "construct_separation": [
                    {"construct": "Quality", "items": 16, "past_source_visible": "否", "decision": "A/B/等价/未决"},
                    {"construct": "Risk", "items": 32, "past_source_visible": "是", "decision": "六族绝对 0–3"},
                    {"construct": "Function", "items": 16, "past_source_visible": "是", "decision": "功能/未用/表面/边界/未决"},
                ],
            },
            "accessIssues": [],
            "notes": ["No labels, API calls, response generation, threshold changes, or PM refits were performed."],
        },
    }
    (OUT / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
