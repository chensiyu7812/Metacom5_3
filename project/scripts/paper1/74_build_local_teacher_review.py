#!/usr/bin/env python3
"""Build a standalone local review of actual answers, evidence and judge reasons."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, sha256_file

PAGE = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>本地裁判逐题审阅</title>
<style>
:root{font-family:system-ui,sans-serif;color:#172638;background:#f4f6f8;line-height:1.6}body{max-width:1180px;margin:auto;padding:24px}h1{font-size:26px}h2{font-size:19px}h3{font-size:16px}p{margin:.5em 0}header,.case{background:white;border:1px solid #dce2e8;border-radius:9px;padding:20px;margin-bottom:18px}label{display:inline-block;margin:8px 16px 8px 0}input,select{font:inherit;padding:6px;border:1px solid #b7c4cf;border-radius:4px}input[type=search]{width:280px;max-width:75vw}.muted{color:#56687a;font-size:13px}.badge{display:inline-block;background:#e9f0f8;padding:2px 8px;border-radius:4px;font-size:13px}.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}.text{white-space:pre-wrap;overflow-wrap:anywhere;max-height:440px;overflow:auto;padding:12px;background:#f7f9fb;border:1px solid #e2e7ed}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:9px;text-align:left;border-bottom:1px solid #e2e7ed;vertical-align:top}summary{cursor:pointer;color:#174e7d;margin:8px 0}.different{color:#a33e16;font-weight:600}.good{color:#176348}.scroll{overflow:auto}@media(max-width:760px){body{padding:12px}.cols{grid-template-columns:1fr}input[type=search]{width:210px}}
</style>
<header><h1>本地裁判逐题审阅</h1>
<p>按同一对原始回复查看人评、裁判判断、换序结果和依据。ON 表示注入当前资源，OFF 表示关闭；所有换序判决已映射回 ON/OFF。</p>
<p class="muted">这是复用材料的开发比较。原始 A 是共同人评；六题复核、辅助事实检查与 AI B 分列。不能把同判率直接称为独立金标准准确率。格式修复只读取明确结论，处理字段、标点或明确的结果表述，不改判决。Summary 新版本与旧人评的题面条件不同。</p>
<label>任务 <select id="task"><option value="">全部</option><option>ESC</option><option>QA</option><option>Summary</option><option>DG</option></select></label>
<label>搜索 <input id="search" type="search" placeholder="问题、题号或回复内容"></label>
<label><input id="unstable" type="checkbox"> 至少一款裁判换序不一致</label>
<p id="count" class="muted"></p></header><main id="cases"></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('data').textContent);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text=s=>`<div class="text">${esc(s||'尚无可读结果')}</div>`;
function verdict(v,arm){if(!v)return '缺失 / 尚未完成';if(v==='equivalent')return '相当';if(v==='uncertain')return '无法判断';return (v==='A_better'?arm:(arm==='ON'?'OFF':'ON'))+' 更好';}
function usable(r){return r?.candidate_verdict||r?.format_recovery?.verdict||null;}
function reason(r){return r?.rationale||r?.format_recovery?.rationale||'';}
function changed(j){return usable(j.base)&&usable(j.reverse)&&verdict(usable(j.base),j.base.A_arm)!==verdict(usable(j.reverse),j.reverse.A_arm);}
function card(c){
 const title=c.task==='ESC'?(c.task_input.split("\n").filter(x=>x.startsWith("seeker:")).at(-1)||c.task_input):c.task_input;
 const judges=c.judges.map(j=>{const a=verdict(usable(j.base),c.A_arm),b=verdict(usable(j.reverse),c.A_arm==='ON'?'OFF':'ON');return `<tr><th>${esc(j.name)}</th><td>${esc(a)}${j.base?.format_recovery?' <span class="muted">格式修复</span>':''}</td><td class="${changed(j)?'different':''}">${esc(b)}${j.reverse?.format_recovery?' <span class="muted">格式修复</span>':''}</td><td><details><summary>理由与原始记录</summary><p>原顺序</p>${text(reason(j.base))}<p>换序</p>${text(reason(j.reverse))}<p class="muted">原顺序状态：${esc(j.base?.status)}；换序状态：${esc(j.reverse?.status)}</p><a href="${esc(j.raw_base)}">原始输出 JSON</a> · <a href="${esc(j.raw_reverse)}">换序输出 JSON</a></details></td></tr>`}).join('');
 const refs=Object.entries(c.references).map(([k,v])=>`${esc(k)}：${esc(verdict(v,c.A_arm))}`).join('；');
 const natural=c.natural?`<details><summary>Summary 自然结束回复与补齐历史后的判断</summary><div class="cols"><div><h3>ON 自然结束</h3>${text(c.natural.ON)}</div><div><h3>OFF 自然结束</h3>${text(c.natural.OFF)}</div></div>${c.summary_variants.map(v=>`<h3>${esc(v.name)} · ${esc(v.variant)}</h3><p>原顺序：${esc(verdict(v.base?.candidate_verdict,c.A_arm))}；换序：${esc(verdict(v.reverse?.candidate_verdict,c.A_arm==='ON'?'OFF':'ON'))}</p><details><summary>两次判断理由</summary>${text(v.base?.rationale)}${text(v.reverse?.rationale)}</details>`).join('')}<details><summary>补齐的原始历史与证据使用说明</summary>${text(c.full_reference)}</details></details>`:'';
 return `<article class="case"><span class="badge">${esc(c.task)} · ${esc(c.head)}</span><h2>${esc(title)}</h2>${title!==c.task_input?`<details><summary>完整任务上下文</summary>${text(c.task_input)}</details>`:''}<p class="muted">${esc(c.base_pair_id)}</p><p>${refs}</p><div class="cols"><div><h3>ON 原始回复</h3>${text(c.A_arm==='ON'?c.response_A:c.response_B)}</div><div><h3>OFF 原始回复</h3>${text(c.A_arm==='OFF'?c.response_A:c.response_B)}</div></div><details><summary>原始裁判证据</summary>${text(c.reference_material)}</details><div class="scroll"><table><thead><tr><th>配置</th><th>原顺序</th><th>换序后</th><th>依据</th></tr></thead><tbody>${judges}</tbody></table></div>${natural}</article>`;
}
function render(){const task=document.getElementById('task').value,q=document.getElementById('search').value.toLowerCase(),u=document.getElementById('unstable').checked;const rows=data.filter(c=>(!task||c.task===task)&&(!q||[c.task_input,c.base_pair_id,c.response_A,c.response_B].join(' ').toLowerCase().includes(q))&&(!u||c.judges.some(changed)));document.getElementById('count').textContent=`显示 ${rows.length} / ${data.length} 对基础题。缺失结果不按换序不一致计算；160 次呈现对应 80 对题。`;document.getElementById('cases').innerHTML=rows.map(card).join('');}
for(const id of ['task','search','unstable'])document.getElementById(id).addEventListener('input',render);render();
</script></html>'''


def main():
    root = PROJECT / "outputs/paper1_pairwise_teacher"
    current = root / "local_comparison_20260917_v2"
    binding = read_json(PROJECT / "data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json")["sheets"]["RATER_A"]
    source = PROJECT / binding["path"]
    assert sha256_file(source) == binding["sha256"]
    items = {r["presentation_id"]: r for r in read_json(source)["items"]}
    models = {"selene_mini_8b": "Selene · JSON", "compassjudger2_7b": "Compass · JSON",
              "qwen35_9b": "Qwen · 通用推理配置", "selene_reasoning_first": "Selene · 先理由后结论"}
    aligned = {key: read_json(current / key / "aligned_results.json") for key in models}
    natural = {}
    for path in (current / "summary_generator/responses").glob("*.json"):
        row = read_json(path)
        for bid in row["base_pair_ids"]:
            natural.setdefault(bid, {})[row["arm"]] = row["raw_output"]
    variants = {key: read_json(current / "summary_evidence_diagnostic" / (key + "_aligned.json"))
                for key in ["compassjudger2_7b", "qwen35_9b", "selene_reasoning_first"]}
    diagnostic_requests = read_json(current / "summary_evidence_diagnostic/requests.json")
    cards = []
    for reference in read_json(root / "gemini_qualification_v2/aligned_results.json"):
        if reference["reverse_duplicate"]:
            continue
        pid, bid = reference["presentation_id"], reference["base_pair_id"]
        item = items[pid]
        judges = []
        for key, name in models.items():
            pair = [r for r in aligned[key] if r["base_pair_id"] == bid]
            assert len(pair) == 2
            base = next(r for r in pair if r["is_base"])
            reverse = next(r for r in pair if not r["is_base"])
            judges.append({"name": name, "base": base, "reverse": reverse,
                "raw_base": f"{key}/responses/{base['presentation_id']}.json",
                "raw_reverse": f"{key}/responses/{reverse['presentation_id']}.json"})
        card = {"base_pair_id": bid, "task": reference["task"], "A_arm": reference["A_arm"],
            "head": judges[0]["base"]["head"], "judges": judges,
            **{k: item[k] for k in ["task_input", "reference_material", "response_A", "response_B"]},
            "references": {label: reference[key] for key, label in [
                ("original_A", "原始 A"), ("human_followup", "含六题复核"),
                ("assistant_fact_sensitivity", "辅助事实检查"), ("exploratory_AI_B", "AI B（探索）")]},
            "natural": natural.get(bid), "summary_variants": []}
        if bid in natural:
            prompt = next(r["messages"][0]["content"] for r in diagnostic_requests if r["base_pair_id"] == bid)
            card["full_reference"] = prompt.split("AUTHORIZED REFERENCE MATERIAL:\n", 1)[1].rsplit("\n\nRESPONSE A:", 1)[0]
            for key, rows in variants.items():
                for variant, label in [("same_answers_full_history", "旧回复＋完整历史"), ("natural_answers_full_history", "自然结束回复＋完整历史")]:
                    pair = [r for r in rows if r["base_pair_id"] == bid and r["development_variant"] == variant]
                    assert len(pair) == 2
                    card["summary_variants"].append({"name": models[key], "variant": label,
                        "base": next(r for r in pair if not r["reverse_duplicate"]),
                        "reverse": next(r for r in pair if r["reverse_duplicate"])})
        cards.append(card)
    assert len(cards) == len({c["base_pair_id"] for c in cards}) == 80
    encoded = json.dumps(cards, ensure_ascii=False).replace("<", "\\u003c")
    destination = current / "逐题审阅.html"
    destination.write_text(PAGE.replace("__DATA__", encoded))
    print({"path": str(destination), "base_pairs": len(cards), "external_assets": 0})


if __name__ == "__main__":
    main()
