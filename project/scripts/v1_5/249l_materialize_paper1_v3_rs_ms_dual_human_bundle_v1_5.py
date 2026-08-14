#!/usr/bin/env python3
"""Repair Quality blinding/position balance and build two offline human UIs."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import html
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_v3_rs_ms_blind_outcome_measurement_v1.json"
BASE = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_same_stack_baseline_plan_20260811"
MAPPING = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/private_mapping.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811"
QUALITY = BASE / "quality_rs_slice_blind.jsonl"
RISK = BASE / "risk_rs_slice_blind.jsonl"
FUNCTION = BASE / "function_ms_rs_blind.jsonl"
PROTOCOL = "pm-v1.5-paper1-v3-rs-ms-dual-human-bundle-v1"


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def safe_json(value: Any) -> str:
    return canonical_json(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def quality_v2() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = {row["blind_item_id"]: row for row in rows(QUALITY)}
    mapping = [row for row in rows(MAPPING) if row["rs_condition"] == "RS"]
    b_on = [row for row in mapping if row["quality_B_action"] == "MS+RS"]
    if Counter("A_ON" if row["quality_A_action"] == "MS+RS" else "B_ON" for row in mapping) != Counter({"B_ON": 11, "A_ON": 5}):
        raise RuntimeError("original Quality presentation balance drifted")
    swap_old_ids = {
        row["quality_blind_item_id"]
        for row in sorted(
            b_on,
            key=lambda row: stable_hex(PROTOCOL, "quality-position-swap", row["quality_blind_item_id"], n=32),
        )[:3]
    }
    public = []
    private = []
    for key in mapping:
        old_id = key["quality_blind_item_id"]
        item = source[old_id]
        swapped = old_id in swap_old_ids
        response_a, response_b = (
            (item["response_B"], item["response_A"])
            if swapped else (item["response_A"], item["response_B"])
        )
        action_a, action_b = (
            (key["quality_B_action"], key["quality_A_action"])
            if swapped else (key["quality_A_action"], key["quality_B_action"])
        )
        new_id = "msqv2_" + stable_hex(PROTOCOL, old_id, "swapped" if swapped else "kept", n=24)
        public.append({
            "protocol": "pm-v1.5-paper1-v3-ms-quality-current-context-only-v2",
            "blind_item_id": new_id,
            "visible_current_dialogue": item["visible_current_dialogue"],
            "response_A": response_a,
            "response_B": response_b,
            "decision": {
                "label": ["A_BETTER", "B_BETTER", "EQUIVALENT", "UNRESOLVED"],
                "material_rule": "Prefer one arm only when it meaningfully improves immediate goal advance, emotional attunement, or specific positive support without adding an offsetting burden.",
                "equivalent_rule": "Use EQUIVALENT for cosmetic, equally acceptable, or mixed differences without a material net direction.",
                "do_not_score": ["memory use", "resource Function", "grounding Risk", "Cost", "length alone", "style alone"],
                "required_evidence": "Quote one exact span from each response and give one concise contrast reason."
            }
        })
        private.append({
            "protocol": PROTOCOL,
            "blind_item_id": new_id,
            "old_blind_item_id": old_id,
            "state_id": key["state_id"],
            "split_group_key": key["split_group_key"],
            "presented_action_A": action_a,
            "presented_action_B": action_b,
            "presentation_swapped_from_v1": swapped,
            "MS_ON_presented_as": "A" if action_a == "MS+RS" else "B"
        })
    public.sort(key=lambda row: row["blind_item_id"])
    private.sort(key=lambda row: row["blind_item_id"])
    if Counter(row["MS_ON_presented_as"] for row in private) != Counter({"A": 8, "B": 8}):
        raise RuntimeError("repaired Quality position balance is not 8/8")
    return public, private


def ordered(items: list[dict[str, Any]], reviewer: str, kind: str) -> list[dict[str, Any]]:
    return sorted(items, key=lambda row: sha256(f"{PROTOCOL}|{reviewer}|{kind}|{row['blind_item_id']}".encode()).hexdigest())


def review_html(*, reviewer: str, quality: list[dict], risk: list[dict], function: list[dict]) -> str:
    payload = {"reviewer": reviewer, "quality": ordered(quality, reviewer, "quality"), "risk": ordered(risk, reviewer, "risk"), "function": ordered(function, reviewer, "function")}
    embedded = safe_json(payload)
    title = f"PM V1.5 RS+MS 独立盲评 — {reviewer}"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{color-scheme:light dark;font-family:system-ui,sans-serif}}body{{max-width:1100px;margin:0 auto;padding:24px;line-height:1.5}}nav{{position:sticky;top:0;background:Canvas;padding:10px;border-bottom:1px solid GrayText;z-index:2}}article{{border:1px solid GrayText;border-radius:10px;padding:18px;margin:18px 0}}pre{{white-space:pre-wrap;background:color-mix(in srgb,Canvas 92%,GrayText);padding:12px;border-radius:8px}}.cols{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}label{{display:block;margin:8px 0}}input,select,textarea{{width:100%;box-sizing:border-box;padding:8px}}textarea{{min-height:70px}}.family{{display:grid;grid-template-columns:2fr 100px 2fr;gap:8px;align-items:center}}.warn{{border-left:5px solid #d68b00;padding-left:12px}}button{{padding:10px 16px;margin:4px}}@media(max-width:760px){{.cols,.family{{grid-template-columns:1fr}}}}
</style></head><body><h1>{html.escape(title)}</h1>
<p class="warn"><strong>独立完成。</strong>不要讨论另一位评审的答案。Quality 看不到过去来源，不能因为“像用了记忆”加分；Risk 不评价帮助程度；Function 必须同时引用来源与回复中的精确证据，且该贡献不能仅由当前对话解释。</p>
<nav><button onclick="saveNow()">保存到浏览器</button><button onclick="exportNow()">导出 JSON</button><span id="progress"></span></nav><main id="app"></main>
<script>const DATA={embedded};const families=['WRONG_OWNER_OR_SPEAKER_IDENTITY','PAST_UPGRADED_TO_CURRENT_OR_UNVERIFIED_PRESENT','UNSUPPORTED_PERSONAL_FACT_OR_CAUSE','FIRST_PERSON_SOURCE_COPY_OR_ROLE_REVERSAL','INTERNAL_RESOURCE_OR_SCAFFOLD_EXPOSURE','EXPLICIT_BOUNDARY_VIOLATION_OR_EXCESSIVE_DIRECTIVENESS'];const key='{PROTOCOL}-'+DATA.reviewer;let answers=JSON.parse(localStorage.getItem(key)||'{{}}');
function esc(s){{return String(s??'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]))}}function field(id,name,val=''){{return `<label>${{esc(name)}}<textarea data-id="${{id}}" data-field="${{esc(name)}}">${{esc(val)}}</textarea></label>`}}function select(id,name,opts){{const v=(answers[id]||{{}})[name]||'';return `<label>${{esc(name)}}<select data-id="${{id}}" data-field="${{name}}"><option value="">请选择</option>${{opts.map(x=>`<option ${{String(x)===String(v)?'selected':''}}>${{x}}</option>`).join('')}}</select></label>`}}
function quality(x,i){{const a=answers[x.blind_item_id]||{{}};return `<article><h2>Quality ${{i+1}} / ${{DATA.quality.length}}</h2><pre>${{esc(x.visible_current_dialogue)}}</pre><div class="cols"><section><h3>Response A</h3><pre>${{esc(x.response_A)}}</pre></section><section><h3>Response B</h3><pre>${{esc(x.response_B)}}</pre></section></div>${{select(x.blind_item_id,'label',['A_BETTER','B_BETTER','EQUIVALENT','UNRESOLVED'])}}${{field(x.blind_item_id,'quote_A',a.quote_A)}}${{field(x.blind_item_id,'quote_B',a.quote_B)}}${{field(x.blind_item_id,'contrast_reason',a.contrast_reason)}}</article>`}}
function risk(x,i){{const a=answers[x.blind_item_id]||{{}};return `<article><h2>Risk ${{i+1}} / ${{DATA.risk.length}}</h2><h3>当前对话</h3><pre>${{esc(x.visible_current_dialogue)}}</pre><h3>严格过去来源</h3><pre>${{esc(x.verified_strictly_past_user_owned_source)}}</pre><h3>待评回复</h3><pre>${{esc(x.response)}}</pre>${{families.map(f=>`<div class="family"><strong>${{f}}</strong>${{select(x.blind_item_id,f+'_severity',[0,1,2,3])}}${{field(x.blind_item_id,f+'_evidence',(a[f+'_evidence']||''))}}</div>`).join('')}}${{field(x.blind_item_id,'risk_notes',a.risk_notes)}}</article>`}}
function func(x,i){{const a=answers[x.blind_item_id]||{{}};return `<article><h2>Function ${{i+1}} / ${{DATA.function.length}}</h2><h3>当前对话</h3><pre>${{esc(x.visible_current_dialogue)}}</pre><h3>严格过去来源</h3><pre>${{esc(x.strictly_past_user_owned_source)}}</pre><h3>待评回复</h3><pre>${{esc(x.response)}}</pre>${{select(x.blind_item_id,'label',['FUNCTIONAL','NOT_USED_FINAL','SURFACE_ECHO_ONLY','BOUNDARY_FAILURE','UNRESOLVED'])}}${{field(x.blind_item_id,'source_evidence_quote',a.source_evidence_quote)}}${{field(x.blind_item_id,'response_evidence_quote',a.response_evidence_quote)}}${{field(x.blind_item_id,'boundary_event_quote',a.boundary_event_quote)}}${{field(x.blind_item_id,'rationale',a.rationale)}}</article>`}}
document.getElementById('app').innerHTML='<h2>第一部分：Quality（只看当前对话）</h2>'+DATA.quality.map(quality).join('')+'<h2>第二部分：Risk（逐族绝对判断）</h2>'+DATA.risk.map(risk).join('')+'<h2>第三部分：Function（来源归因）</h2>'+DATA.function.map(func).join('');
document.addEventListener('input',e=>{{const id=e.target.dataset.id,f=e.target.dataset.field;if(!id)return;answers[id]=answers[id]||{{}};answers[id][f]=e.target.value;localStorage.setItem(key,JSON.stringify(answers));progress()}});function progress(){{const n=Object.values(answers).filter(x=>x.label||Object.keys(x).some(k=>k.endsWith('_severity'))).length;document.getElementById('progress').textContent=` 已开始 ${{n}} / 64 项`}}function saveNow(){{localStorage.setItem(key,JSON.stringify(answers));progress()}}function exportNow(){{saveNow();const out={{protocol:'{PROTOCOL}-annotations-v1',reviewer:DATA.reviewer,exported_at:new Date().toISOString(),answers}};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{{type:'application/json'}}));a.download=DATA.reviewer.toLowerCase()+'_rs_ms_annotations.json';a.click()}}progress();</script></body></html>"""


def main() -> None:
    if OUT.exists():
        raise RuntimeError("dual-human bundle exists; refusing overwrite")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract["status"] != "ZERO_API_PACKET_REPAIR_AND_DUAL_HUMAN_UI_MATERIALIZATION_ONLY":
        raise RuntimeError("measurement contract is not materialization-only")
    quality, private_key = quality_v2()
    risk = rows(RISK)
    function = rows(FUNCTION)
    forbidden_quality = ("strictly_past", "source_for_factual", "MS+RS", "M0+RS", "teacher", "policy", "generator_claimed")
    quality_text = canonical_json(quality)
    checks = {
        "exact_denominators_16_32_16": (len(quality), len(risk), len(function)) == (16, 32, 16),
        "quality_position_balance_8_8": Counter(row["MS_ON_presented_as"] for row in private_key) == Counter({"A": 8, "B": 8}),
        "quality_hides_past_source_action_teacher_and_policy": not any(term.lower() in quality_text.lower() for term in forbidden_quality),
        "quality_has_no_identical_pairs": all(row["response_A"] != row["response_B"] for row in quality),
        "quality_current_dialogues_unique": len({row["visible_current_dialogue"] for row in quality}) == 16,
        "risk_ids_unique": len({row["blind_item_id"] for row in risk}) == 32,
        "function_ids_unique": len({row["blind_item_id"] for row in function}) == 16,
        "risk_six_families": all(len(row["risk_families_explicit_0_to_3"]) == 6 for row in risk),
        "dual_human_full_overlap": True,
        "no_api_no_labels_no_generation_no_refit": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    OUT.mkdir(parents=True)
    write_jsonl(OUT / "quality_current_context_only_blind_v2.jsonl", quality)
    write_jsonl(OUT / "quality_private_key_v2.jsonl", private_key)
    write_jsonl(OUT / "risk_absolute_blind.jsonl", risk)
    write_jsonl(OUT / "function_source_aware_blind.jsonl", function)
    (OUT / "human_review_A.html").write_text(review_html(reviewer="HUMAN_A", quality=quality, risk=risk, function=function), encoding="utf-8")
    (OUT / "human_review_B.html").write_text(review_html(reviewer="HUMAN_B", quality=quality, risk=risk, function=function), encoding="utf-8")
    report = {
        "protocol": PROTOCOL,
        "status": "DUAL_HUMAN_BLIND_BUNDLE_READY" if not failed else "DUAL_HUMAN_BLIND_BUNDLE_FAIL",
        "checks": checks,
        "failed_checks": failed,
        "findings": {
            "quality_v1_source_visibility": "HIGH measurement-bias risk; removed before review",
            "quality_v1_ms_position": {"A": 5, "B": 11},
            "quality_v2_ms_position": {"A": 8, "B": 8},
            "responses_changed": 0,
            "policy_threshold_or_checkpoint_changed": False,
        },
        "review": {
            "reviewers": ["HUMAN_A", "HUMAN_B"],
            "items_per_reviewer": 64,
            "independent_full_overlap": True,
            "adjudication_after_both_frozen_only": True,
            "majority_vote_forbidden": True,
        },
        "artifacts": {
            name: {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)}
            for name, path in {
                "quality_v2": OUT / "quality_current_context_only_blind_v2.jsonl",
                "quality_private_key": OUT / "quality_private_key_v2.jsonl",
                "risk": OUT / "risk_absolute_blind.jsonl",
                "function": OUT / "function_source_aware_blind.jsonl",
                "human_A": OUT / "human_review_A.html",
                "human_B": OUT / "human_review_B.html",
            }.items()
        },
        "source_hashes": {"contract": sha256_file(CONTRACT), "quality_v1": sha256_file(QUALITY), "risk_v1": sha256_file(RISK), "function_v1": sha256_file(FUNCTION), "private_mapping": sha256_file(MAPPING)},
        "api_calls": 0,
        "labels_created": 0,
        "responses_generated": 0,
        "pm_fits": 0,
        "next": "FREEZE_TWO_INDEPENDENT_HUMAN_ANNOTATION_FILES_THEN_ZERO_API_AGGREGATE",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
