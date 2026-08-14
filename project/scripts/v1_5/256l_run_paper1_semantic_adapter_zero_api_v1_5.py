#!/usr/bin/env python3
"""Run the frozen zero-API semantic-adapter and oracle-plan probe."""

from __future__ import annotations

import argparse
from collections import Counter
import html
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_semantic_adapter_probe import (  # noqa: E402
    classify_semantic_state,
    forced_choice_scores,
    latest_dialogue_window,
    PHASE_LABELS,
    validate_oracle_plans,
)


CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_semantic_adapter_ablation_v1.json"
ORACLE = ROOT / "data/pm_v1_5_contracts/paper1_ms_oracle_semantic_plans_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_semantic_adapter_zero_api_20260811"

OBVIOUS_RELATION_CONTROLS = {
    "msq_bee16fdc790bfb7212015e64": "LOW_INFORMATION",
    "msq_87db08d48d8c622ccfabe7a2": "LOW_INFORMATION",
    "msq_e0b44973307ffd5799f5cb15": "DISTRACTING",
    "msq_54931d30df95fc06f7633046": "LOW_INFORMATION",
    "msq_de2b7cc3e811589d0a3f8543": "LOW_INFORMATION",
    "msq_5f168442f5caf697695830bd": "REDUNDANT_CURRENT",
    "msq_6d52bd04cb023726591d4dbf": "LOW_INFORMATION",
    "msq_c8f6fa9124234cdc9a057987": "LOW_INFORMATION",
    "msq_f36b5bb36a65509d7645bfaf": "DISTINCT_HELPFUL",
}


def require_environment(contract: dict[str, Any]) -> dict[str, Any]:
    model = contract["semantic_model"]
    execution = model["execution"]
    checks = {
        "api_calls_forbidden": contract["authority"]["api_calls_authorized"] == 0,
        "pm_fits_forbidden": contract["authority"]["pm_fits_authorized"] == 0,
        "python_no_user_site": os.environ.get("PYTHONNOUSERSITE") == "1",
        "cuda_device_frozen": os.environ.get("CUDA_VISIBLE_DEVICES") == execution["cuda_visible_devices"],
        "python_executable_frozen": str(Path(sys.executable).resolve()) == str(Path(execution["python"]).resolve()),
        "isolated_branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip() == contract["version_control"]["isolated_branch"],
        "model_revision_path_frozen": Path(model["snapshot_path"]).name == model["revision"],
    }
    for item in contract["frozen_inputs"]:
        checks[f"input_hash::{item['path']}"] = sha256_file(ROOT / item["path"]) == item["sha256"]
    return checks


def verify_model_files(contract: dict[str, Any]) -> dict[str, bool]:
    import hashlib

    snapshot = Path(contract["semantic_model"]["snapshot_path"])
    expected = contract["semantic_model"]["verified_files"]
    lfs = {"model.safetensors", "spm.model"}
    checks: dict[str, bool] = {}
    for name, wanted in expected.items():
        data = (snapshot / name).read_bytes()
        if name in lfs:
            got = hashlib.sha256(data).hexdigest()
        else:
            got = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        checks[f"model_hash::{name}"] = got == wanted
    return checks


def render_report(analysis: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    relation_counts = analysis["candidate_relation_top_labels"]
    phase_counts = analysis["support_phase_top_labels"]
    table_rows = []
    for row in rows:
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(row['qualification_case_id'])}</td>"
            f"<td>{html.escape(row['qualification_class'])}</td>"
            f"<td>{html.escape(row['semantic_state']['support_phase']['top_label'])}</td>"
            f"<td>{html.escape(row['semantic_state']['immediate_support_goal']['top_label'])}</td>"
            f"<td>{html.escape(row['semantic_state']['candidate_relation_to_current']['top_label'])}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>Paper 1 semantic adapter zero-API probe</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1180px;margin:32px auto;line-height:1.55}}code{{background:#f3f4f6;padding:2px 5px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #ddd;padding:6px;vertical-align:top}}th{{background:#f6f6f6}}.pass{{color:#087830}}.warn{{color:#9a5b00}}</style></head>
<body><h1>语义适配器零 API 探针</h1>
<p><strong>结论：</strong>{html.escape(analysis['decision'])}</p>
<p>本轮没有调用生成 API、没有创建训练标签、没有重训 PM，也没有改变阈值。模型只作为冻结的诊断特征提取器。</p>
<ul><li>明显 candidate-relation 对照：{analysis['obvious_relation_controls_correct']}/{analysis['obvious_relation_controls_total']}</li>
<li>两条 closure 对照识别：{analysis['closure_controls_correct']}/{analysis['closure_controls_total']}</li>
<li>16 个状态的 phase 分布：<code>{html.escape(json.dumps(phase_counts, ensure_ascii=False, sort_keys=True))}</code></li>
<li>16 个状态的 relation 分布：<code>{html.escape(json.dumps(relation_counts, ensure_ascii=False, sort_keys=True))}</code></li>
<li>Oracle plans：<span class=\"{'pass' if analysis['oracle_plan_checks_pass'] else 'warn'}\">{'PASS' if analysis['oracle_plan_checks_pass'] else 'FAIL'}</span></li></ul>
<h2>解释边界</h2><p>NLI 的输出不是“理解正确率”，更不是 gold。它只回答：一个现成小模型能否稳定提供少量有用状态信号。若明显对照都分不开，就不应把它加入正式 PM。</p>
<h2>逐状态输出</h2><table><thead><tr><th>case</th><th>frozen class</th><th>phase</th><th>goal</th><th>candidate relation</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    contract = read_json(CONTRACT)
    cases_path = ROOT / contract["frozen_inputs"][0]["path"]
    cases = read_jsonl(cases_path)
    oracle = read_json(ORACLE)

    environment_checks = require_environment(contract)
    model_checks = verify_model_files(contract)
    suitable_ids = {row["qualification_case_id"] for row in cases if row["qualification_class"] == "TEACHER_SUITABLE"}
    oracle_checks = validate_oracle_plans(oracle["plans"], expected_case_ids=suitable_ids)
    all_static_checks = {**environment_checks, **model_checks, **oracle_checks}
    failed = [name for name, passed in all_static_checks.items() if not passed]
    if failed:
        raise RuntimeError("zero-API preflight failed: " + ", ".join(failed))
    if args.validate_only:
        print(json.dumps({"status": "ZERO_API_PREFLIGHT_PASS", "checks": all_static_checks}, indent=2))
        return

    from transformers import pipeline

    classifier = pipeline(
        "zero-shot-classification",
        model=contract["semantic_model"]["snapshot_path"],
        tokenizer=contract["semantic_model"]["snapshot_path"],
        device=0,
    )
    semantic_rows = []
    for row in cases:
        semantic_rows.append({
            "protocol": "pm-v1.5-paper1-semantic-adapter-probe-row-v1",
            "qualification_case_id": row["qualification_case_id"],
            "state_id": row["state_id"],
            "split_group_key": row["split_group_key"],
            "qualification_class": row["qualification_class"],
            "negative_stratum": row["negative_stratum"],
            "semantic_state": classify_semantic_state(
                classifier,
                current_context=row["current_context"],
                exact_source=row["exact_source"],
            ),
        })

    closure_path = ROOT / contract["frozen_inputs"][2]["path"]
    closure_rows = []
    for row in read_jsonl(closure_path):
        score = forced_choice_scores(
            classifier,
            sequence=latest_dialogue_window(row["visible_current_dialogue"]),
            labels=PHASE_LABELS,
            hypothesis_template="The emotional-support stage is {}.",
        )
        closure_rows.append({"blind_item_id": row["blind_item_id"], "support_phase": score})

    by_id = {row["qualification_case_id"]: row for row in semantic_rows}
    obvious_correct = sum(
        by_id[case_id]["semantic_state"]["candidate_relation_to_current"]["top_label"] == expected
        for case_id, expected in OBVIOUS_RELATION_CONTROLS.items()
    )
    closure_correct = sum(row["support_phase"]["top_label"] == "RELIEF_CLOSURE" for row in closure_rows)
    relation_counts = Counter(
        row["semantic_state"]["candidate_relation_to_current"]["top_label"] for row in semantic_rows
    )
    phase_counts = Counter(row["semantic_state"]["support_phase"]["top_label"] for row in semantic_rows)

    # This deliberately requires performance on both constructs; two closure
    # examples alone cannot justify adding the model to the formal PM.
    retain = obvious_correct >= 7 and closure_correct == 2
    decision = (
        "RETAIN_AS_BOUNDED_DIAGNOSTIC_FEATURE_CANDIDATE"
        if retain
        else "REJECT_THIS_OFF_THE_SHELF_NLI_MODEL_FOR_FORMAL_PM; KEEP_ORACLE_PLAN_UPPER_BOUND_TEST"
    )
    analysis = {
        "protocol": "pm-v1.5-paper1-semantic-adapter-zero-api-analysis-v1",
        "status": "ZERO_API_PROBE_COMPLETE",
        "decision": decision,
        "obvious_relation_controls_correct": obvious_correct,
        "obvious_relation_controls_total": len(OBVIOUS_RELATION_CONTROLS),
        "closure_controls_correct": closure_correct,
        "closure_controls_total": len(closure_rows),
        "support_phase_top_labels": dict(phase_counts),
        "candidate_relation_top_labels": dict(relation_counts),
        "oracle_plan_checks": oracle_checks,
        "oracle_plan_checks_pass": all(oracle_checks.values()),
        "environment_and_hash_checks": {**environment_checks, **model_checks},
        "api_calls": 0,
        "training_labels_created": 0,
        "pm_fits": 0,
        "threshold_changes": 0,
        "claim_limit": "Small frozen development probe; no human-language understanding percentage and no formal PM result.",
        "next_step": "Independently audit the eight oracle plans. Only then design a content-addressed, cost-capped generator upper-bound phase.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "semantic_scores_private.jsonl", semantic_rows)
    write_jsonl(OUT / "closure_scores_private.jsonl", closure_rows)
    write_json(OUT / "analysis.json", analysis)
    (OUT / "report.html").write_text(render_report(analysis, semantic_rows), encoding="utf-8")
    report = {
        "protocol": "pm-v1.5-paper1-semantic-adapter-zero-api-report-v1",
        "status": "ZERO_API_SEMANTIC_ADAPTER_PROBE_PASS" if all(oracle_checks.values()) else "FAIL",
        "decision": decision,
        "contract": {"path": str(CONTRACT.relative_to(ROOT)), "sha256": sha256_file(CONTRACT)},
        "oracle_plans": {"path": str(ORACLE.relative_to(ROOT)), "sha256": sha256_file(ORACLE), "rows": 8},
        "artifacts": {
            "analysis": {"path": str((OUT / "analysis.json").relative_to(ROOT)), "sha256": sha256_file(OUT / "analysis.json")},
            "semantic_scores": {"path": str((OUT / "semantic_scores_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "semantic_scores_private.jsonl"), "rows": 16},
            "closure_scores": {"path": str((OUT / "closure_scores_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "closure_scores_private.jsonl"), "rows": 2},
            "html": {"path": str((OUT / "report.html").relative_to(ROOT)), "sha256": sha256_file(OUT / "report.html")},
        },
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
