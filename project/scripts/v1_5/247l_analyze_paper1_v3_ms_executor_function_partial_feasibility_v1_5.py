#!/usr/bin/env python3
"""Analyze the accepted partial GPT Function review without additional API calls."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402


REVIEWS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gpt_id_repair_continuation_20260811/reviews.jsonl"
REVIEWS_SHA256 = "e68824d575e43a27fc8046608dd55ae61b0eecfa3e3d17a31a0bcb3c57bb800b"
MAPPING = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/private_mapping.jsonl"
MAPPING_SHA256 = "3d24ffb565da2bfb6f031d5bb4119621fe54449e2b92256417b9c30505229bcb"
REJECTED_RAW = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gpt_id_repair_continuation_20260811/raw_attempts_before_gold.jsonl"
REJECTED_RAW_SHA256 = "1f90c51e62820f92f6cd6e519d25a3fb352e7aac321b06b9a8da2c50e1f15699"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_partial_feasibility_audit_20260811"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    for path, expected in ((REVIEWS, REVIEWS_SHA256), (MAPPING, MAPPING_SHA256), (REJECTED_RAW, REJECTED_RAW_SHA256)):
        if sha256_file(path) != expected:
            raise RuntimeError(f"bound analysis input drifted: {path}")
    OUT.mkdir(parents=True, exist_ok=True)
    mapping = {row["function_blind_item_id"]: row for row in rows(MAPPING)}
    accepted = [row for row in rows(REVIEWS) if row["stage"] == "PUBLIC"]
    if len(accepted) != 24 or len({row["blind_item_id"] for row in accepted}) != 24:
        raise RuntimeError("expected 24 unique accepted public reviews")
    joined = [{**row, **mapping[row["blind_item_id"]]} for row in accepted]
    labels = ["FUNCTIONAL", "NOT_USED_FINAL", "SURFACE_ECHO_ONLY", "BOUNDARY_FAILURE", "UNRESOLVED"]

    summary_rows = []
    for teacher, expected_label in (("TEACHER_SUITABLE", "FUNCTIONAL"), ("TEACHER_NOT_SUITABLE", "NOT_USED_FINAL")):
        cohort = [row for row in joined if row["teacher_class"] == teacher]
        counts = Counter(row["label"] for row in cohort)
        summary_rows.append(
            {
                "teacher_class": teacher,
                "expected_executor_behavior": expected_label,
                "observed_n": len(cohort),
                **{label.lower(): counts[label] for label in labels},
                "expected_behavior_count": counts[expected_label],
                "expected_behavior_rate": counts[expected_label] / len(cohort),
            }
        )
    segment_rows = []
    for rs in ("R0", "RS"):
        for teacher in ("TEACHER_SUITABLE", "TEACHER_NOT_SUITABLE"):
            cohort = [row for row in joined if row["rs_condition"] == rs and row["teacher_class"] == teacher]
            counts = Counter(row["label"] for row in cohort)
            expected = "FUNCTIONAL" if teacher == "TEACHER_SUITABLE" else "NOT_USED_FINAL"
            segment_rows.append(
                {
                    "rs_condition": rs,
                    "teacher_class": teacher,
                    "observed_n": len(cohort),
                    "functional": counts["FUNCTIONAL"],
                    "not_used_final": counts["NOT_USED_FINAL"],
                    "other_or_failure": len(cohort) - counts["FUNCTIONAL"] - counts["NOT_USED_FINAL"],
                    "expected_behavior_rate": counts[expected] / len(cohort),
                }
            )
    missing = sorted(set(mapping) - {row["blind_item_id"] for row in accepted})
    missing_teacher = Counter(mapping[item]["teacher_class"] for item in missing)
    missing_rs = Counter(mapping[item]["rs_condition"] for item in missing)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-function-partial-feasibility-audit-v1",
        "status": "POSITIVE_MEANING_ABSORPTION_SUPPORTED_NEGATIVE_SELF_SUPPRESSION_WEAK_PARTIAL_PROXY_ONLY",
        "decision": "PROCEED_TO_BOUNDED_RS_MS_SAME_STACK_BASELINE_DESIGN_NOT_PAPER_FINAL_FUNCTION_CLAIM",
        "grain": "one accepted source-aware Function label per MS-ON response",
        "coverage": {
            "accepted_public_items": 24,
            "planned_public_items": 32,
            "coverage_rate": 0.75,
            "connected_groups_observed": len({row["split_group_key"] for row in joined}),
            "connected_groups_planned": 8,
            "missing_teacher_class": dict(missing_teacher),
            "missing_rs_condition": dict(missing_rs),
        },
        "headline": {
            "suitable_functional": "12/12",
            "suitable_R0_functional": "6/6",
            "suitable_RS_functional": "6/6",
            "not_suitable_safe_nonuse": "6/12",
            "not_suitable_functional_calls": "4/12",
            "not_suitable_boundary_failure": "1/12",
            "not_suitable_surface_echo": "1/12",
        },
        "summary_by_teacher_class": summary_rows,
        "summary_by_rs_and_teacher": segment_rows,
        "measurement_quality": {
            "proxy_control_result": "11/12 PASS",
            "terminal_substantive_proxy_error": "current-context gratitude was incorrectly attributed to the strictly-past source; response evidence was copied from current dialogue",
            "usable_for": "development feasibility and failure localization",
            "not_usable_for": "human gold, dual-model agreement, complete Function pass, or paper-final effect estimate",
            "severity": "HIGH for paper-final measurement; LOW for the positive-capacity existence claim because all 12 suitable cases passed exact source and response evidence checks",
            "confidence": "moderate",
        },
        "interpretation": [
            "The V3 meaning-absorption executor can make a distinct, boundary-safe MS contribution when the frozen teacher says the source is suitable.",
            "The executor does not reliably self-suppress an unsuitable source once MS is requested; learned PM gating and projection remain necessary.",
            "The single GPT proxy tends to over-attribute Function under current/past semantic overlap, so its negative-side labels cannot be promoted to gold.",
        ],
        "next": [
            "Materialize the learned RS+MS policy action for the same 16 states without new generation.",
            "Compare RS-only, learned RS+MS, fixed-high MS, transparent rule, and cost-matched fixed on the existing same-stack arms.",
            "Use this proxy Function result only as a development diagnostic; paper-final Function needs targeted source-aware human adjudication, especially current-echo negatives.",
            "Do not reopen MP or ME during the MS baseline stage.",
        ],
        "visual_omission": "A two-row by five-label audit matrix is better served by an exact table than a chart; 24 accepted items and partial non-random execution order do not support an uncertainty visual.",
        "source_hashes": {
            "accepted_reviews": REVIEWS_SHA256,
            "private_mapping": MAPPING_SHA256,
            "terminal_rejected_raw": REJECTED_RAW_SHA256,
        },
        "api_calls": 0,
    }
    report_path = OUT / "report.json"
    write_json(report_path, report)

    title = "MS 执行器 Function 部分盲评可行性审计"
    source = {
        "id": "derived_function_audit",
        "label": "MS executor partial Function feasibility audit",
        "path": "outputs/pm_v1_5_paper1_v3_ms_executor_function_partial_feasibility_audit_20260811/report.json",
        "query": {
            "language": "sql",
            "engine": "DuckDB-compatible audit SQL",
            "sql": "SELECT * FROM (VALUES ('TEACHER_SUITABLE', 12, 12, 0, 0, 0, 1.0), ('TEACHER_NOT_SUITABLE', 12, 4, 6, 1, 1, 0.5)) AS t(teacher_class, observed_n, functional, not_used_final, surface_echo_only, boundary_failure, expected_behavior_rate)",
            "description": "Hash-bound join of accepted blind Function reviews to the private teacher-class mapping.",
            "tables_used": [
                "outputs/pm_v1_5_paper1_v3_ms_executor_function_gpt_id_repair_continuation_20260811/reviews.jsonl",
                "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/private_mapping.jsonl"
            ],
            "filters": ["stage=PUBLIC", "locally validated exact evidence only", "24 accepted of 32 planned"],
            "metric_definitions": [
                "Suitable Function rate = FUNCTIONAL labels / accepted TEACHER_SUITABLE responses.",
                "Negative safe-nonuse rate = NOT_USED_FINAL labels / accepted TEACHER_NOT_SUITABLE responses."
            ]
        }
    }
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": title,
            "description": "Technical audit of whether the V3 MS executor realizes suitable memory and suppresses unsuitable memory.",
            "generatedAt": "2026-08-11T12:00:00+09:00",
            "sources": [source],
            "charts": [
                {
                    "id": "expected_behavior_rate",
                    "title": "Expected executor behavior rate by suitability class",
                    "subtitle": "Accepted blind reviews only: 12 suitable and 12 not-suitable responses",
                    "type": "bar",
                    "dataset": "teacher_outcomes",
                    "sourceId": "derived_function_audit",
                    "layout": "full",
                    "encodings": {
                        "x": {"field": "teacher_class", "type": "nominal", "label": "Frozen suitability class"},
                        "y": {"field": "expected_behavior_rate", "type": "quantitative", "format": "percent", "label": "Expected behavior rate"}
                    },
                    "valueFormat": "percent",
                    "maxRows": 2,
                    "question": "Does the executor realize suitable MS and decline unsuitable MS when MS is requested?",
                    "rationale": "A two-category bar makes the asymmetric 100% versus 50% behavior immediately visible; the adjacent exact table preserves label counts.",
                    "emptyState": "No accepted Function reviews are available."
                }
            ],
            "tables": [
                {
                    "id": "teacher_outcomes",
                    "title": "Function labels by frozen suitability class",
                    "subtitle": "24 accepted blind reviews; exact counts are primary because coverage is partial",
                    "dataset": "teacher_outcomes",
                    "defaultSort": {"field": "teacher_class", "direction": "desc"},
                    "density": "spacious",
                    "sourceId": "derived_function_audit",
                    "layout": "full",
                    "columns": [
                        {"field": "teacher_class", "label": "Frozen class", "type": "text"},
                        {"field": "observed_n", "label": "n", "format": "number"},
                        {"field": "functional", "label": "Functional", "format": "number"},
                        {"field": "not_used_final", "label": "Safe non-use", "format": "number"},
                        {"field": "surface_echo_only", "label": "Surface echo", "format": "number"},
                        {"field": "boundary_failure", "label": "Boundary fail", "format": "number"},
                        {"field": "expected_behavior_rate", "label": "Expected behavior rate", "format": "percent"}
                    ]
                },
                {
                    "id": "rs_segments",
                    "title": "Function behavior by response-strategy condition",
                    "subtitle": "R0 and RS each retain suitable and unsuitable cases",
                    "dataset": "rs_segments",
                    "defaultSort": {"field": "rs_condition", "direction": "asc"},
                    "density": "spacious",
                    "sourceId": "derived_function_audit",
                    "layout": "full",
                    "columns": [
                        {"field": "rs_condition", "label": "Response strategy", "type": "text"},
                        {"field": "teacher_class", "label": "Frozen class", "type": "text"},
                        {"field": "observed_n", "label": "n", "format": "number"},
                        {"field": "functional", "label": "Functional", "format": "number"},
                        {"field": "not_used_final", "label": "Safe non-use", "format": "number"},
                        {"field": "other_or_failure", "label": "Other/failure", "format": "number"},
                        {"field": "expected_behavior_rate", "label": "Expected behavior rate", "format": "percent"}
                    ]
                }
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": f"# {title}", "layout": "full"},
                {"id": "summary", "type": "markdown", "body": "## 技术结论\n\n**可以进入受限的 RS+MS 同栈 baseline 设计，但不能把本轮称为完整 Function 通过。** 在 24 条严格验收的正式盲评中，冻结为 suitable 的 12 条全部被判为 FUNCTIONAL，R0 与 RS 各 6/6；这支持执行器具备吸收合适记忆并自然做功的能力。冻结为 not-suitable 的 12 条只有 6 条安全不使用，另有 4 条被代理判为 FUNCTIONAL、1 条边界失败、1 条表面复述，说明执行器不能替代 PM 门控。", "layout": "full", "sourceId": "derived_function_audit"},
                {"id": "finding_positive", "type": "markdown", "body": "## 合适记忆的正向实现信号很强\n\n12/12 suitable 回复均满足严格的 source quote 与 response quote 逐字证据门，并在 R0 与 RS 条件下各为 6/6。这不是回复质量胜负，但证明新版执行器没有再把记忆强制逐字拼接；它至少能在合适状态中形成可见的连续性或更知情的当前动作。", "layout": "full", "sourceId": "derived_function_audit"},
                {"id": "expected_behavior_chart", "type": "chart", "chartId": "expected_behavior_rate", "layout": "full"},
                {"id": "teacher_table", "type": "table", "tableId": "teacher_outcomes", "layout": "full"},
                {"id": "finding_negative", "type": "markdown", "body": "## 不合适记忆仍需由 PM 拦住\n\nnot-suitable 仅 6/12 自然降为 NOT_USED_FINAL。反事实地强制请求 MS 时，执行器仍可能使用无增量来源；因此最终系统的意义来自 selector、projector 与 executor 联合工作，不能指望 generator 自己修复错误调用。", "layout": "full", "sourceId": "derived_function_audit"},
                {"id": "rs_table", "type": "table", "tableId": "rs_segments", "layout": "full"},
                {"id": "scope", "type": "markdown", "body": "## 范围、粒度与指标\n\n分析单位是一条 MS-ON 最终回复的 source-aware Function 标签。suitable 的预期行为是 FUNCTIONAL；not-suitable 的预期行为是安全不使用 NOT_USED_FINAL。计划 32 条，实际严格验收 24 条（75%），覆盖全部 8 个 connected groups；缺失项在 teacher class 上为 4/4 平衡，但执行顺序并非随机抽样。", "layout": "full", "sourceId": "derived_function_audit"},
                {"id": "method", "type": "markdown", "body": "## 方法与责任边界\n\nGPT-5 mini 先在内容不相交的 12 道控制题上取得 11/12 并通过逐类资格门，随后才查看正式盲包。每个 FUNCTIONAL 必须同时给出旧来源和最终回复中的逐字证据；生成器 telemetry 不可作为证明。本报告只分析通过本地严格验证的 24 条，未把失败输出裁剪成有效标签。", "layout": "full"},
                {"id": "limits", "type": "markdown", "body": "## 限制与稳健性\n\n本轮是单 LLM 代理的部分开发测量，不是人评、双模型复现或论文终值。代理在终止项中把当前对话的感谢错误归因给过去记忆，并把当前对话片段当作回复证据，说明它会在 current/past 重叠时过度判定 Function。由此，正向 12/12 可作为能力存在证据；负向 4 个 FUNCTIONAL 不能直接当 gold，也不能据此估计真实误用率。", "layout": "full"},
                {"id": "next", "type": "markdown", "body": "## 下一步\n\n1. 零 API 物化同一 16 states 上 learned RS+MS、RS-only、fixed-high、transparent rule 与 cost-matched fixed 的动作。\n2. 复用已生成的四臂回复，不重新生成、不调 selector 阈值。\n3. baseline 的 Function 只作开发诊断；论文最终值对 learned policy 实际选中的回复做小规模 source-aware 人工裁决。\n4. 在 MS baseline 完成前不重新打开 MP 或 ME。", "layout": "full"},
                {"id": "questions", "type": "markdown", "body": "## 尚待回答\n\n- learned MS selector 在这 16 个 states 上实际开启哪些来源？\n- 把不合适来源挡在 executor 之前后，RS+MS 是否在质量不下降的同时减少误用与成本？\n- current-echo 负例的人类裁决是否确认单代理的过度归因？", "layout": "full"}
            ]
        },
        "snapshot": {
            "version": 1,
            "generatedAt": "2026-08-11T12:00:00+09:00",
            "status": "partial",
            "datasets": {"teacher_outcomes": summary_rows, "rs_segments": segment_rows},
            "accessIssues": [
                {"id": "partial_coverage", "scope": "public Function packet", "dataset": "teacher_outcomes", "message": "8 of 32 public reviews are not accepted: one substantive proxy error stopped execution and seven later calls were deliberately not run."},
                {"id": "single_proxy", "scope": "measurement validity", "message": "Only one model proxy qualified and produced accepted public labels; no human or second-model agreement is claimed."}
            ]
        },
        "sources": [source]
    }
    write_json(OUT / "artifact.json", artifact)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
