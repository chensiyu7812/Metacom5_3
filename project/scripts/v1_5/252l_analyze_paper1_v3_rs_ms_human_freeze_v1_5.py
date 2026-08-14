#!/usr/bin/env python3
"""Analyze the PI-adjudicated RS+MS review with HUMAN_A sensitivity evidence."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_two_human_freeze_20260811"
BUNDLE = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811"
BASE = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_same_stack_baseline_plan_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_pi_adjudicated_analysis_20260811"
MAPPING = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/private_mapping.jsonl"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def direction(label: str, on_side: str) -> str:
    if label == "EQUIVALENT":
        return "TIE"
    if label == "UNRESOLVED":
        return "UNRESOLVED"
    chosen = "A" if label == "A_BETTER" else "B"
    return "MS_ON_BETTER" if chosen == on_side else "RS_ONLY_BETTER"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("analysis output exists; refusing overwrite")
    freeze_report = json.loads((FREEZE / "report.json").read_text(encoding="utf-8"))
    if freeze_report["status"] != "TWO_HUMAN_RAW_REVIEWS_FROZEN_DISAGREEMENT_ADJUDICATION_PENDING":
        raise RuntimeError("raw review freeze is not complete")
    reviews = {
        "HUMAN_A": json.loads((FREEZE / "human_A_raw_frozen.json").read_text(encoding="utf-8"))["answers"],
        "HUMAN_B": json.loads((FREEZE / "human_B_raw_frozen.json").read_text(encoding="utf-8"))["answers"],
    }
    human_b_document = json.loads((FREEZE / "human_B_raw_frozen.json").read_text(encoding="utf-8"))
    if human_b_document.get("adjudication", {}).get("adjudicated_by") != "PI (study owner)":
        raise RuntimeError("HUMAN_B is not explicitly PI-adjudicated")
    qkey = {x["blind_item_id"]: x for x in rows(BUNDLE / "quality_private_key_v2.jsonl")}
    policies = {
        x["state_id"]: x
        for x in rows(BASE / "policy_actions_private.jsonl")
        if x["policy"] == "rs_fixed_on_plus_learned_ms"
    }
    rs_mapping = {x["state_id"]: x for x in rows(MAPPING) if x["rs_condition"] == "RS"}
    function_items = {x["blind_item_id"]: x for x in rows(BUNDLE / "function_source_aware_blind.jsonl")}

    learned_on_quality: dict[str, Counter] = {name: Counter() for name in reviews}
    learned_on_states = {state for state, row in policies.items() if row["ms_selected_on"]}
    for item_id, key in qkey.items():
        if key["state_id"] not in learned_on_states:
            continue
        for name, answers in reviews.items():
            learned_on_quality[name][direction(answers[item_id]["label"], key["MS_ON_presented_as"])] += 1

    learned_function: dict[str, Counter] = {name: Counter() for name in reviews}
    all_function: dict[str, Counter] = {name: Counter() for name in reviews}
    for state, mapping in rs_mapping.items():
        item_id = mapping["function_blind_item_id"]
        assert item_id in function_items
        for name, answers in reviews.items():
            label = answers[item_id]["label"]
            all_function[name][label] += 1
            if state in learned_on_states:
                learned_function[name][label] += 1

    closure_states = [
        {
            "state_id": "evo::p13::esc1198::seeker_turn::25",
            "signal": "plan formed + anger reduced + repeated thanks",
            "expected_response_act": "acknowledge improvement and close gently",
        },
        {
            "state_id": "evo::p1::p1_conv_1::seeker_turn::25",
            "signal": "feels lighter + plan to seek support + repeated thanks",
            "expected_response_act": "acknowledge relief and leave a future-open closing",
        },
    ]
    for row in closure_states:
        policy = policies[row["state_id"]]
        row.update({
            "learned_ms_on": policy["ms_selected_on"],
            "learned_policy_action": policy["selected_action"],
            "rs_only_action": "M0+RS",
            "affects_learned_ms_vs_rs_only": policy["selected_action"] != "M0+RS",
        })

    families = [
        "WRONG_OWNER_OR_SPEAKER_IDENTITY",
        "PAST_UPGRADED_TO_CURRENT_OR_UNVERIFIED_PRESENT",
        "UNSUPPORTED_PERSONAL_FACT_OR_CAUSE",
        "FIRST_PERSON_SOURCE_COPY_OR_ROLE_REVERSAL",
        "INTERNAL_RESOURCE_OR_SCAFFOLD_EXPOSURE",
        "EXPLICIT_BOUNDARY_VIOLATION_OR_EXCESSIVE_DIRECTIVENESS",
    ]
    risk_mapping = {}
    for row in rs_mapping.values():
        risk_mapping[row["risk_A_blind_item_id"]] = row["quality_A_action"]
        risk_mapping[row["risk_B_blind_item_id"]] = row["quality_B_action"]
    pi_risk = Counter()
    for item_id, action in risk_mapping.items():
        severities = [int(reviews["HUMAN_B"][item_id][f"{family}_severity"]) for family in families]
        pi_risk[(action, "any_nonzero")] += max(severities) > 0
        pi_risk[(action, "severity_sum")] += sum(severities)

    analysis = {
        "protocol": "pm-v1.5-paper1-v3-rs-ms-pi-adjudicated-analysis-v1",
        "status": "PI_ADJUDICATED_HUMAN_B_ANALYSIS_COMPLETE_NO_INDEPENDENT_IAA",
        "grain": {"states": 16, "connected_groups": 8, "learned_ms_on_states": 7},
        "review_validity": {
            "two_complete_files": True,
            "reviewer_ids": ["HUMAN_A", "HUMAN_B"],
            "review_roles_machine_verifiable": True,
            "independence_provenance_machine_verifiable": False,
            "user_reported_both_files_reviewed": True,
            "human_B_contains_PI_adjudication": True,
            "independent_human_IAA_eligible": False,
            "safe_claim": "HUMAN_B is the PI-adjudicated final file; HUMAN_A is sensitivity evidence only. Raw agreement is descriptive, not independent-human IAA.",
        },
        "raw_agreement": freeze_report["agreement"],
        "learned_ms_on_quality": {name: dict(counts) for name, counts in learned_on_quality.items()},
        "function": {
            "all_16": {name: dict(counts) for name, counts in all_function.items()},
            "learned_ms_on_7": {name: dict(counts) for name, counts in learned_function.items()},
            "functional_any_reviewer_all_16": 0,
            "functional_any_reviewer_learned_on_7": 0,
            "robust_interpretation": "No verified independent memory contribution in this RS-fixed-on slice; Quality differences cannot be attributed to MS Function.",
        },
        "pi_adjudicated_final": {
            "quality_learned_ms_on_7": dict(learned_on_quality["HUMAN_B"]),
            "function_learned_ms_on_7": dict(learned_function["HUMAN_B"]),
            "function_all_16": dict(all_function["HUMAN_B"]),
            "function_stratification": human_b_document["function_stratification"],
            "risk_all_16_by_action": {
                action: {
                    "nonzero_responses": pi_risk[(action, "any_nonzero")],
                    "severity_sum": pi_risk[(action, "severity_sum")],
                    "denominator": 16,
                }
                for action in ("M0+RS", "MS+RS")
            },
        },
        "closure_limitation": {
            "explicit_states": closure_states,
            "states": 2,
            "both_learned_ms_off": all(not x["learned_ms_on"] for x in closure_states),
            "changes_incremental_ms_contrast": any(x["affects_learned_ms_vs_rs_only"] for x in closure_states),
            "interpretation": "The panel estimates MS increment conditional on RS=ON. It does not evaluate whether a full PM should choose R0 at relief/closure states.",
        },
        "decision": "MS_RS_SLICE_FAILS_VERIFIED_FUNCTION; DO_NOT_DECLARE_MS_PASS_FROM_QUALITY; R0_INTERACTION_DIAGNOSTIC_USING_EXISTING_ARMS_NEXT",
        "api_calls": 0,
        "responses_generated": 0,
        "pm_refits": 0,
        "next": "DESIGN_ZERO_API_EXISTING_R0_SLICE_DIAGNOSTIC_TO_SEPARATE_RS_CROWD_OUT_FROM_GENERAL_MS_NONUSE",
    }

    quality_chart = []
    for reviewer, counts in learned_on_quality.items():
        evidence_role = "HUMAN_A_SENSITIVITY" if reviewer == "HUMAN_A" else "PI_ADJUDICATED_B"
        for outcome in ("MS_ON_BETTER", "RS_ONLY_BETTER", "TIE"):
            quality_chart.append({"reviewer": evidence_role, "outcome": outcome, "count": counts[outcome], "denominator": 7})
    function_table = []
    for reviewer, counts in learned_function.items():
        function_table.append({
            "reviewer": "HUMAN_A_SENSITIVITY" if reviewer == "HUMAN_A" else "PI_ADJUDICATED_B",
            "functional": counts["FUNCTIONAL"],
            "not_used_final": counts["NOT_USED_FINAL"],
            "surface_echo_only": counts["SURFACE_ECHO_ONLY"],
            "boundary_failure": counts["BOUNDARY_FAILURE"],
            "denominator": 7,
        })

    source = "frozen_review_analysis"
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "PI 裁定后的 RS+MS 结果与 closure 限制",
            "description": "Technical analysis of the PI-adjudicated final review with HUMAN_A sensitivity evidence.",
            "generatedAt": "2026-08-11T20:30:00+09:00",
            "sources": [{
                "id": source,
                "label": "PI-adjudicated RS+MS analysis",
                "path": "outputs/pm_v1_5_paper1_v3_rs_ms_pi_adjudicated_analysis_20260811/analysis.json",
                "query": {
                    "language": "sql",
                    "engine": "DuckDB-compatible audit SQL",
                    "sql": "SELECT reviewer, outcome, count, denominator FROM learned_ms_on_quality UNION ALL SELECT reviewer, function_label, count, denominator FROM learned_ms_on_function",
                    "description": "Hash-preserving join of frozen raw review files, blind keys, and the frozen learned-MS policy bindings.",
                    "tables_used": [
                        "outputs/pm_v1_5_paper1_v3_rs_ms_two_human_freeze_20260811/human_A_raw_frozen.json",
                        "outputs/pm_v1_5_paper1_v3_rs_ms_two_human_freeze_20260811/human_B_raw_frozen.json",
                        "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811/quality_private_key_v2.jsonl",
                        "outputs/pm_v1_5_paper1_v3_rs_ms_same_stack_baseline_plan_20260811/policy_actions_private.jsonl",
                    ],
                    "filters": ["RS slice only", "learned MS ON states=7", "PI-adjudicated HUMAN_B final plus HUMAN_A sensitivity"],
                    "metric_definitions": [
                        "MS_ON_BETTER means the reviewer preferred the MS+RS arm after opening the balanced A/B key.",
                        "FUNCTIONAL requires an independently attributable contribution from the strictly-past source.",
                    ],
                },
            }],
            "charts": [{
                "id": "learned_quality",
                "title": "Learned MS 开启状态的原始 Quality 方向",
                "subtitle": "PI裁定终值与HUMAN_A敏感性；各 n=7",
                "type": "bar",
                "dataset": "learned_quality",
                "sourceId": source,
                "layout": "full",
                "encodings": {
                    "x": {"field": "outcome", "type": "nominal", "label": "方向"},
                    "y": {"field": "count", "type": "quantitative", "label": "状态数"},
                    "color": {"field": "reviewer", "type": "nominal", "label": "评审文件"},
                },
                "valueFormat": "number",
                "maxRows": 6,
                "question": "MS selector 开启的状态上，MS+RS 是否比 RS-only 更好？",
                "rationale": "Grouped bars keep the PI final and sensitivity file separate rather than pooling evidence with different roles.",
                "emptyState": "No frozen Quality labels are available.",
            }],
            "tables": [
                {
                    "id": "function_learned",
                    "title": "Learned MS 开启状态的 Function 标签",
                    "subtitle": "每位评审 n=7；两份文件均未给出 FUNCTIONAL",
                    "dataset": "function_learned",
                    "density": "spacious",
                    "sourceId": source,
                    "layout": "full",
                    "columns": [
                        {"field": "reviewer", "label": "证据角色", "type": "text"},
                        {"field": "functional", "label": "Functional", "format": "number"},
                        {"field": "not_used_final", "label": "未使用", "format": "number"},
                        {"field": "surface_echo_only", "label": "表面呼应", "format": "number"},
                        {"field": "boundary_failure", "label": "资源越界", "format": "number"},
                        {"field": "denominator", "label": "n", "format": "number"},
                    ],
                },
                {
                    "id": "closure_states",
                    "title": "明确 relief/closure 状态",
                    "subtitle": "两状态的 learned MS 均为 OFF，因此不改变 MS 增量对比",
                    "dataset": "closure_states",
                    "density": "spacious",
                    "sourceId": source,
                    "layout": "full",
                    "columns": [
                        {"field": "state_id", "label": "State", "type": "text"},
                        {"field": "signal", "label": "Closure signal", "type": "text"},
                        {"field": "learned_policy_action", "label": "本 panel 动作", "type": "text"},
                        {"field": "expected_response_act", "label": "更合适的回复动作", "type": "text"},
                    ],
                },
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# PI 裁定后的 RS+MS 结果与 closure 限制", "layout": "full"},
                {"id": "summary", "type": "markdown", "body": "## 技术结论\n\n**MS 在这个 RS 固定开启切片中没有及格。** PI裁定后的HUMAN_B终值在 learned MS 开启的7个状态上给出 Quality `5胜/2负`，但 Function 为 `0/7`；全部16条也为 `0/16`。因此Quality优势不能归因于记忆做功。HUMAN_A的`3胜/3负/1平`只作敏感性证据。两条relief/closure状态另行证明本panel不能评价完整PM是否应选择R0。", "layout": "full", "sourceId": source},
                {"id": "quality_finding", "type": "markdown", "body": "## Quality 的5胜2负不能救回零 Function\n\nPI终值表面偏向MS+RS，但没有一条回复呈现可由过去来源独立解释的贡献。HUMAN_A敏感性结果又接近持平。最稳妥解释是生成措辞、RS表达或评审阈值造成了Quality差异，而不是记忆带来了支持增益。", "layout": "full", "sourceId": source},
                {"id": "quality_chart", "type": "chart", "chartId": "learned_quality", "layout": "full"},
                {"id": "function_finding", "type": "markdown", "body": "## Function 0/7 是当前最稳健、也最关键的结果\n\n两位评审在全部16条 MS+RS 回复中都没有判出任何 FUNCTIONAL；唯一分歧只是 `SURFACE_ECHO_ONLY` 对 `NOT_USED_FINAL`。在 selector 真正开启的7条中，两份文件均为7条 NOT_USED_FINAL。也就是说，MS 候选被送入 joint executor 后没有形成可由过去来源独立解释的贡献。", "layout": "full", "sourceId": source},
                {"id": "function_table", "type": "table", "tableId": "function_learned", "layout": "full"},
                {"id": "closure_finding", "type": "markdown", "body": "## Closure 暴露的是 RS/回复动作缺口，不是 MS selector 的这次错误\n\n工资计划已形成、工作困扰已缓解这两个状态都应优先确认改善并自然收尾。当前 Quality 包的两臂却都是 RS-ON，所以都倾向继续提问。好消息是 learned MS 在两状态均为 OFF，learned policy 与 RS-only 动作完全相同，因此 closure 不改变本次 MS 增量胜负；坏消息是这个实验不能检验完整四 bit PM 的 RS 门控，也不能宣称 overall PM 已通过。", "layout": "full", "sourceId": source},
                {"id": "closure_table", "type": "table", "tableId": "closure_states", "layout": "full"},
                {"id": "definitions", "type": "markdown", "body": "## 范围、数据和指标\n\n分析单位为16个 EvoEmo states、8个 connected groups。主比较不是 jointly learned RS+MS，而是 `RS fixed ON + learned MS` 对 RS-only；只有 selector 开启 MS 的7个 states 会改变 learned policy。Quality 是当前对话下的匿名 A/B净支持方向；Risk 是32条回复的六族绝对事件；Function 要求过去来源对最终回复产生不能仅由当前对话解释的贡献。", "layout": "full", "sourceId": source},
                {"id": "method", "type": "markdown", "body": "## 方法与冻结顺序\n\n两份64项文件先通过ID、枚举、完整性和逐字证据校验，再原样冻结并打开A/B key。HUMAN_B文件顶层明确记录`adjudicated_by: PI (study owner)`及最终规则，所以它作为PI裁定终值；HUMAN_A只作敏感性，11/16、187/192、15/16只能称描述性raw agreement。", "layout": "full", "sourceId": source},
                {"id": "limitations", "type": "markdown", "body": "## 限制、稳健性与责任边界\n\n这不是独立双人IAA：B已按PI裁定定稿。Risk终值中M0+RS有2/16条非零、MS+RS有3/16条非零，均无critical；HUMAN_A则全部判零，说明轻度风险阈值仍敏感。Function的失败更稳健：A、B都没有任何FUNCTIONAL，唯一差异只是表面呼应还是未使用。", "layout": "full", "sourceId": source},
                {"id": "next", "type": "markdown", "body": "## 下一步\n\n1. 冻结PI终值：RS条件下 learned-MS `verified Function=0/7`，不得由Quality 5胜2负改写为通过。\n2. 零API使用已经存在的MS+R0与M0+R0回复做一次预声明interaction diagnostic，判断MS是被RS主动作挤掉，还是R0下同样没有功能。\n3. closure作为RS/response-act单独诊断；未来完整PM测试必须允许RS-OFF并验证自然收尾。\n4. 不调selector阈值、不改标签、不重生成。", "layout": "full"},
                {"id": "questions", "type": "markdown", "body": "## 尚待回答\n\n- 现有MS+R0回复是否能在同7个states上产生verified Function？\n- closure-aware R0是否需要新的回复动作规划，还是现有R0 generator已能稳定自然收尾？", "layout": "full"},
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": "2026-08-11T20:30:00+09:00",
            "status": "ready",
            "datasets": {
                "learned_quality": quality_chart,
                "function_learned": function_table,
                "closure_states": closure_states,
            },
            "accessIssues": [],
            "notes": [
                "Chart map: learned_quality uses grouped categorical bars because two reviewer distributions must remain separate; n=7 per reviewer.",
                "No Function chart was used because two rows with a zero headline are clearer as an exact table.",
                "Review-provenance limitation: HUMAN_B explicitly contains PI adjudication; HUMAN_A is sensitivity evidence, not an independent co-primary reviewer.",
            ],
        },
    }
    OUT.mkdir(parents=True)
    (OUT / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(analysis, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
