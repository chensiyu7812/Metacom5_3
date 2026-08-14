#!/usr/bin/env python3
"""Independently validate the frozen G4B review design and V2 preflight."""

from __future__ import annotations

import html
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_g4b_nonexclusive_suitability_review import (  # noqa: E402
    G4BSuitabilityReview,
)


DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b_review_design_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b_review_preflight_v2_20260811"
V1 = ROOT / "outputs/pm_v1_5_paper1_v3_g4b_review_preflight_20260811/report.json"
RUNNER = ROOT / "scripts/v1_5/209l_run_paper1_v3_g4b_reviews_v1_5.py"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b_review_design_validation_v2_20260811"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> dict[str, Any]:
    design = read(DESIGN)
    preflight = read(PREFLIGHT / "report.json")
    v1 = read(V1)
    all_bindings = [*design["input_bindings"], *design["implementation_bindings"]]
    bindings_ok = all(
        (ROOT / row["path"]).is_file()
        and sha256_file(ROOT / row["path"]) == row["sha256"]
        for row in all_bindings
    )
    runner_text = RUNNER.read_text(encoding="utf-8")
    schema_fields = set(G4BSuitabilityReview.model_fields)
    retired = {
        "current_target_fit",
        "specific_increment_available",
        "component_minimum_possible_now",
        "current_boundary_permits",
    }
    costs = preflight["cost_ceiling"]
    checks = {
        "all_design_bindings_match": bindings_ok,
        "v1_failed_preflight_preserved": v1["status"] == "G4B_REVIEW_PREFLIGHT_FAIL",
        "v1_had_zero_api_labels_reviews": all(
            int(v1.get(key) or 0) == 0
            for key in ("api_calls", "reviews_created", "labels_created")
        ),
        "v2_preflight_passed": preflight["status"]
        == "G4B_REVIEW_PREFLIGHT_PASS_CONTROL_EXECUTION_PHASE_MAY_BE_DESIGNED",
        "v2_preflight_has_no_failed_checks": preflight["failed_checks"] == [],
        "single_decision_schema_only": schema_fields
        == {
            "review_item_id",
            "decision",
            "primary_reason_code",
            "visible_span_ids",
            "candidate_span_ids",
            "checklist_attested",
        },
        "retired_axes_absent_from_schema": not bool(schema_fields & retired),
        "nonexclusive_and_sixteen_actions_preserved": all(
            design["nonexclusive_label_and_action_invariants"][key]
            for key in (
                "nonexclusive",
                "same_state_may_have_MP_MS_ME_all_suitable",
                "at_most_one_positive_memory_forbidden",
                "all_16_requested_actions_remain_downstream",
                "checklist_attestation_does_not_limit_memory_count",
            )
        ),
        "runner_has_no_gold_or_private_key_path": all(
            token not in runner_text
            for token in ("control_gold_key", "private_case_key", "_private_20260811")
        ),
        "controls_are_72_one_case_calls": preflight["call_counts"]["controls"] == 72,
        "public_1014_calls_not_authorized": preflight["call_counts"][
            "public_not_authorized"
        ]
        == 1014
        and not preflight["public_execution_authorized"],
        "control_cap_exceeds_conservative_bound": costs["CONTROL"][
            "absolute_usd_cap"
        ]
        >= costs["CONTROL"]["conservative_computed_usd"],
        "public_cap_exceeds_conservative_bound": costs["PUBLIC"][
            "absolute_usd_cap"
        ]
        >= costs["PUBLIC"]["conservative_computed_usd"],
        "gold_is_delayed_until_separate_phase": not design["gold_isolation"][
            "review_execution_reads_gold"
        ],
        "control_failure_is_component_local": design[
            "control_qualification_per_reviewer_per_component"
        ]["failure_is_component_local"],
        "valid_judgment_never_retried_for_gold_disagreement": any(
            "disagrees with control gold" in row
            for row in design["raw_first_and_retry"]["retry_forbidden"]
        ),
        "all_execution_permissions_remain_false": not any(
            design["authorization"].values()
        ),
    }
    failed = [key for key, value in checks.items() if not value]
    return {
        "protocol": "pm-v1.5-paper1-v3-g4b-review-design-validation-v1",
        "status": (
            "G4B_REVIEW_DESIGN_PASS_EXACT_CONTROL_EXECUTION_PHASE_MAY_BE_DESIGNED"
            if not failed
            else "G4B_REVIEW_DESIGN_FAIL"
        ),
        "checks": checks,
        "failed_checks": failed,
        "design": {
            "path": str(DESIGN.relative_to(ROOT)),
            "sha256": sha256_file(DESIGN),
        },
        "preflight": {
            "path": str((PREFLIGHT / "report.json").relative_to(ROOT)),
            "sha256": sha256_file(PREFLIGHT / "report.json"),
            "call_plan_sha256": preflight["call_plan"]["sha256"],
        },
        "grain": design["scientific_grain"],
        "control_logical_calls": 72,
        "public_logical_calls_not_authorized": 1014,
        "control_cap_usd": costs["CONTROL"]["absolute_usd_cap"],
        "future_public_cap_usd": costs["PUBLIC"]["absolute_usd_cap"],
        "api_calls": 0,
        "reviews_created": 0,
        "labels_created": 0,
        "next_gate": "G4B1_EXACT_72_CONTROL_CALL_EXECUTION_PHASE",
    }


def render_html(report: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(key)}</td><td class='{str(value).lower()}'>{'PASS' if value else 'FAIL'}</td></tr>"
        for key, value in report["checks"].items()
    )
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>G4B 评审设计技术审计</title><style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f4f6f8;color:#17212b}}
main{{max-width:1050px;margin:32px auto;padding:0 20px}}section{{background:white;border:1px solid #dde3e8;border-radius:12px;padding:22px;margin:16px 0}}
h1,h2{{margin-top:0}}.lead{{font-size:1.1rem;line-height:1.7}}.metric{{display:inline-block;margin:5px 8px 5px 0;padding:10px 14px;background:#eef4ff;border-radius:9px}}
table{{width:100%;border-collapse:collapse}}td{{padding:9px;border-bottom:1px solid #edf0f2}}td.true{{color:#08783e;font-weight:700}}td.false{{color:#b42318;font-weight:700}}
code{{background:#f2f4f7;padding:2px 5px;border-radius:4px}}small{{color:#52606d}}
</style></head><body><main><h1>G4B 非排他适用性评审：执行前技术审计</h1>
<section><h2>结论</h2><p class='lead'><strong>{html.escape(report['status'])}</strong>。当前只允许设计下一道 72 条控制题执行门；507×2 正式双评、标签、训练、generator 与外部实验仍未授权。</p>
<div class='metric'>控制题：72 次逻辑调用</div><div class='metric'>正式题：1,014 次，未授权</div><div class='metric'>控制题上限：${report['control_cap_usd']:.2f}</div></section>
<section><h2>为什么这次不会回到旧 P2B</h2><p>每个 <code>state × component × actual Rank-1</code> 只产生一个 SUITABLE / NOT_SUITABLE / SEMANTIC_ABSTAIN 决定。四项语义问题只作已检查证明，不产生四个标签，也不限制同一 state 可同时启用的记忆数量。评审 runner 不能读取 gold；两位评审的 72 条结果全部冻结后，另一零 API 程序才首次打开私有金标。</p></section>
<section><h2>机器检查</h2><table>{rows}</table></section>
<section><h2>执行与定责边界</h2><p>本阶段只资格化“候选当前是否适用”的测量工具。它不判断未来回复质量、风险、成本或 generator 是否会正确吸收资源，也不创建 PM 标签。控制题失败先归于 reviewer/instrument qualification，不得提前写成 PM 学不会。</p></section>
<section><h2>限制与下一步</h2><p>两位 reviewer 都是已识别的 LLM reviewer，不称真人。只有同一组件在两位 reviewer 上分别通过 12 条 fresh controls，才开放该组件的公共双评。单组件失败不关闭其他组件；正式结果出来后也禁止改控制题、阈值、codebook 或 prompt 追门。</p><small>Design SHA: {report['design']['sha256']} · Preflight SHA: {report['preflight']['sha256']}</small></section>
</main></body></html>"""


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G4B design validation output exists; refusing overwrite")
    report = validate()
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    (OUT / "report.html").write_text(render_html(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
