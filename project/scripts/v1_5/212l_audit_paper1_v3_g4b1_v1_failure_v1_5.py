#!/usr/bin/env python3
"""Classify the frozen G4B1 V1 failure without changing its result."""

from __future__ import annotations

import html
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_g4b_nonexclusive_suitability_review import prompt_messages  # noqa: E402


DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4_nonexclusive_suitability_design_v1.json"
QUAL = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_control_qualification_20260811/report.json"
LIVE = ROOT / "outputs/pm_v1_5_paper1_v3_g4b_reviews_20260811/controls_live_report.json"
CONTROL = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811/reviewer_a_controls.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_v1_failure_audit_20260811"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def first_row(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G4B1 failure audit output exists; refusing overwrite")
    design = read(DESIGN)
    qual = read(QUAL)
    live = read(LIVE)
    provider_system = prompt_messages(first_row(CONTROL), "REVIEWER_A")[0]["content"]
    per_reviewer = {}
    for reviewer, components in qual["reviewer_component_results"].items():
        per_reviewer[reviewer] = {
            "resolved_correct": sum(row["resolved_correct"] for row in components.values()),
            "resolved_total": sum(row["resolved_total"] for row in components.values()),
            "abstain_correct": sum(row["abstain_correct"] for row in components.values()),
            "abstain_total": sum(row["abstain_total"] for row in components.values()),
            "qualified_components": [
                component
                for component, row in components.items()
                if row["status"] == "QUALIFIED"
            ],
        }
    checks = {
        "frozen_scientific_result_is_fail": qual["status"]
        == "G4B1_CONTROL_QUALIFICATION_FAIL_NO_MEMORY_PUBLIC_REVIEW",
        "all_72_reviews_completed_first_attempt": live["completed_valid_reviews"] == 72
        and live["physical_attempts_started"] == 72
        and live["terminal_nonretryable_invalid"] == 0,
        "public_labels_fit_generator_are_zero": live["labels_created"] == 0
        and qual["public_reviews_created"] == 0
        and qual["training_labels_created"] == 0,
        "g4_required_worked_anchors": design["reviewer_qualification"][
            "worked_training_anchors_before_qualification"
        ]
        is True,
        "provider_prompt_omitted_worked_anchors": all(
            token not in provider_system.casefold()
            for token in ("worked example", "training example", "example 1")
        ),
        "reviewer_a_resolved_signal_is_not_collapsed": per_reviewer["REVIEWER_A"][
            "resolved_correct"
        ]
        == 30,
        "reviewer_b_has_suitability_overcall_not_transport_failure": per_reviewer[
            "REVIEWER_B"
        ]["resolved_correct"]
        == 21,
        "abstention_is_the_shared_failure_surface": per_reviewer["REVIEWER_A"][
            "abstain_correct"
        ]
        == 1
        and per_reviewer["REVIEWER_B"]["abstain_correct"] == 0,
    }
    failed = [key for key, value in checks.items() if not value]
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b1-v1-failure-audit-v1",
        "status": (
            "G4B1_V1_INSTRUMENT_IMPLEMENTATION_FAIL_FRESH_ANCHORED_V2_MAY_BE_DESIGNED_ONCE"
            if not failed
            else "G4B1_V1_FAILURE_ROOT_CAUSE_UNRESOLVED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "frozen_v1_result_remains": qual["status"],
        "reviewer_performance": per_reviewer,
        "root_cause": "The provider-visible qualification instrument omitted the worked training anchors explicitly required by the upstream G4 contract. Reviewer A retained perfect resolved binary discrimination but did not learn the narrow abstention boundary; Reviewer B additionally overcalled SUITABLE. This is an instrument implementation failure before PM labels or fitting, not evidence that all memory heads are unlearnable.",
        "only_permitted_repair": {
            "preserve": [
                "reviewer identities",
                "three decisions",
                "12 controls per component with 5/5/2 composition",
                "10/12 exact, 9/10 resolved, 2/2 abstain and critical-boundary gates",
                "raw-first and delayed-gold execution"
            ],
            "change_once": [
                "implement component-specific worked anchors already required by G4",
                "use fresh held-out controls disjoint from V1 and public cases",
                "add a machine check that anchors are provider-visible"
            ],
            "if_v2_fails": "no third prompt/control/gate revision; close failed components or use only a separately preregistered non-LLM annotation route"
        },
        "api_calls_in_audit": 0,
        "new_reviews_labels_or_fit": 0,
        "inputs": {
            "qualification": {"path": str(QUAL.relative_to(ROOT)), "sha256": sha256_file(QUAL)},
            "live": {"path": str(LIVE.relative_to(ROOT)), "sha256": sha256_file(LIVE)}
        }
    }
    rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{'PASS' if v else 'FAIL'}</td></tr>"
        for k, v in checks.items()
    )
    page = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>G4B1 V1 失败定责</title><style>body{{font-family:system-ui;background:#f5f7fa;color:#17212b}}main{{max-width:980px;margin:32px auto}}section{{background:white;border:1px solid #dfe5eb;border-radius:12px;padding:22px;margin:15px}}table{{width:100%;border-collapse:collapse}}td{{padding:8px;border-bottom:1px solid #eee}}.k{{font-size:1.25rem;line-height:1.6}}</style></head><body><main><section><h1>G4B1 V1：不是 PM 失败，而是资格 instrument 漏实现</h1><p class='k'>{html.escape(report['status'])}</p><p>72/72 控制题结构和运输全部正常；正式 public review、标签与 fit 均为 0。Claude 的 resolved 正/负题为 30/30，但 abstain 为 1/6；GPT-5 mini resolved 为 21/30，abstain 为 0/6。</p></section><section><h2>根因</h2><p>{html.escape(report['root_cause'])}</p></section><section><h2>机器证据</h2><table>{rows}</table></section><section><h2>唯一允许的下一步</h2><p>补上 G4 原本就要求的 component-specific worked anchors，改用全新 held-out controls；reviewer、三分类、样本构成和全部门槛不改。V2 若失败，不再第三次修改。</p></section></main></body></html>"""
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    (OUT / "report.html").write_text(page, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
