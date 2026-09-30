#!/usr/bin/env python3
"""Offline blinded review form with local draft/export; no scores or arm key."""
from html import escape
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
OUT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'


def select(name, label, choices):
    options='<option value="">未填写</option>'+''.join(f'<option value="{escape(v)}">{escape(t)}</option>' for v,t in choices)
    return f'<label>{label}<select data-field="{name}">{options}</select></label>'


def main():
    source=OUT/'independent_review_UNSCORED.json'; data=json.loads(source.read_text())
    sections=[]
    for i,item in enumerate(data['items'],1):
        e=item['evidence']
        current=''.join(f'<p><b>{escape(t["id"])} · {escape(t["role"])}</b><br>{escape(t["text"])}</p>' for t in e['current_prefix'])
        history=''.join('<details><summary>'+escape(s['id']+' · '+s['date'])+'</summary>'+''.join(
            f'<p><b>{escape(t["id"])} · {escape(t["role"])}</b><br>{escape(t["text"])}</p>' for t in s['turns'])+'</details>' for s in e['legal_past_sessions'])
        answers=''
        for label in ['A','B']:
            fields=select('q_'+label,'质量 q',[(str(v),str(v)) for v in range(5)]+[('uncertain','无法判断')])
            fields+=select('m_'+label,'事实/时间/边界误用 m',[('0','0 · 未发现'),('0.25','0.25 · 局部'),('1','1 · 实质'),('uncertain','无法判断')])
            answers+=f'<article><h3>回复 {label}</h3><p class="reply">{escape(item["replies"][label])}</p><div class="scores">{fields}</div></article>'
        pair=select('pairwise','总体比较',[('A','A 更好'),('B','B 更好'),('equivalent','无可辨净差异'),('uncertain','无法判断')])
        sections.append(f'<section data-item="{item["item_id"]}"><h2>题 {i} / {len(data["items"])}</h2>'+
            f'<p class="small">题号：{item["item_id"]}　当前日期：{escape(e["current_date"])}</p><h3>当前公开对话</h3>'+current+
            '<div class="answers">'+answers+'</div>'+pair+
            '<label>依据（请分别写 A/B 的关键回复原句、对应 C:T… 或 H…:T… 及来源原句；说明决定分档/比较的原因）<textarea data-field="evidence" rows="5"></textarea></label>'+
            '<label>无法判断 / 有疑问的地方（如适用）<textarea data-field="uncertainty" rows="2"></textarea></label>'+
            '<details><summary>查阅完整合法过去历史（判断历史事实前请展开）</summary>'+history+'</details></section>')
    header='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PM-RL1 · 独立盲评卷</title><style>
body{font:16px/1.7 system-ui,sans-serif;color:#20313e;background:#f3f6f8;max-width:1120px;margin:auto;padding:20px}
header,section{background:white;border:1px solid #d8e0e6;border-radius:8px;padding:24px;margin:18px 0}
h1{font-size:26px}h2{font-size:23px}h3{font-size:18px}.small{font-size:13px;color:#536473}
.answers{display:grid;grid-template-columns:1fr 1fr;gap:18px}article{padding:18px;background:#f1f6fa;border-radius:6px}
.reply{white-space:pre-wrap}p{overflow-wrap:anywhere}label{display:block;margin:12px 0}select,input,textarea,button{font:inherit;box-sizing:border-box}
select,input,textarea{border:1px solid #8b9baa;border-radius:4px;padding:8px;background:white}select{margin:0 12px;max-width:100%}textarea{display:block;width:100%}
button{padding:10px 22px;background:#185679;color:white;border:0;border-radius:5px;cursor:pointer}summary{cursor:pointer;font-weight:600;padding:10px 0}
details details{margin:8px 14px;border-top:1px solid #d7e0e7}.toolbar{position:sticky;top:0;background:#e5eef3;padding:12px;z-index:2}.scores{display:flex;flex-wrap:wrap}
@media(max-width:760px){body{padding:6px}.answers{grid-template-columns:1fr}header,section{padding:14px}.toolbar{position:static}}
</style></head><body><header><h1>PM-RL1 · 独立盲评卷</h1>
<p>本卷 10 对，原定 12 对中另 2 对的诊断条件不适用，因此未替换成其他题。请独立完成后再讨论；不要先看协调端答案映射或本地裁判分数。原始英文是判分证据。</p>
<p>只评价最后 seeker 发言之后这条新回复。两条回复共享完整合法历史，过去的 supporter 回复不计入新回复质量。当前明确更正优先；旧建议、猜测和问题不自动成为用户事实。意向不等于执行，执行不等于有效。</p>
<p><b>质量 q：</b>0 严重失配/无法使用；1 主导性的错误或越界；2 基本回应但有重要不足；3 贴合、连贯、适当且无重要缺陷；4 充分满足当前需要及约束。简短回复也可为 4；长度、建议量、记忆展示、某种风格本身不加分。</p>
<p><b>误用 m：</b>0 在检查范围内未发现；0.25 局部事实/人物/时间/边界错误；1 实质误用。无具体个人事实断言可以 m=0，但请注明“无可核查断言”；这不代表已证明事实能力。一般建议、明确假设和问题要与事实断言区分。</p>
<p>有充分理由才区分 q 的相邻档。无可辨净差异可以包含“同样差”；无法判断请保留，不强行评分。两条回复可能都好、都差或各有优缺点。说明依据比追求一致更重要。</p>
<label>评审者标识（自填姓名或代号）<input id="reviewer" autocomplete="off"></label>
<label>评审者类型<select id="reviewer-kind"><option value="">未填写</option><option value="individual_human">个人独立人评</option><option value="human_consensus">多人讨论后的共同意见</option><option value="model">模型复核</option></select></label>
<label>身份补充（模型复核请写型号/版本；共同评审请写参与方式）<input id="reviewer-details" autocomplete="off"></label>
<p class="small">浏览器仅在本机保存草稿，不联网提交。完成后点击“导出答卷 JSON”；该文件才是可交回的答卷。换浏览器或清理缓存可能丢失草稿。</p></header>
<div class="toolbar"><button id="export" type="button">导出答卷 JSON</button> <span id="status" role="status"></span></div>'''
    binding=json.dumps(dict(protocol='pm-rl1-independent-review-v1',source_sha256=sha256_file(source)),ensure_ascii=False)
    script=r'''
<script>
"use strict";
const binding=__BINDING__;
const storageKey=binding.protocol+":"+binding.source_sha256;
function collect(){
 return {...binding,reviewer_identity:document.getElementById("reviewer").value.trim(),
  reviewer_kind:document.getElementById("reviewer-kind").value,reviewer_details:document.getElementById("reviewer-details").value.trim(),
  exported_at:new Date().toISOString(),items:Array.from(document.querySelectorAll("section[data-item]")).map(section=>{
   const row={item_id:section.dataset.item};
   section.querySelectorAll("[data-field]").forEach(el=>row[el.dataset.field]=el.value);
   return row;
  })};
}
function update(){
 const value=collect();
 let completed=value.items.filter(r=>["q_A","m_A","q_B","m_B","pairwise"].every(k=>r[k]!=="") && r.evidence.trim()).length;
 document.getElementById("status").textContent=`已完整填写 ${completed}/${value.items.length} 题（未填写或无法判断会原样保留）`;
 try{localStorage.setItem(storageKey,JSON.stringify(value));}catch(error){document.getElementById("status").textContent+="；本机草稿保存不可用，请及时导出。";}
}
try{
 const draft=JSON.parse(localStorage.getItem(storageKey)||"null");
 if(draft && draft.source_sha256===binding.source_sha256){
  document.getElementById("reviewer").value=draft.reviewer_identity||"";
  document.getElementById("reviewer-kind").value=draft.reviewer_kind||"";
  document.getElementById("reviewer-details").value=draft.reviewer_details||"";
  for(const row of draft.items||[]){
   const section=Array.from(document.querySelectorAll("section[data-item]")).find(el=>el.dataset.item===row.item_id);
   if(section) section.querySelectorAll("[data-field]").forEach(el=>{if(typeof row[el.dataset.field]==="string")el.value=row[el.dataset.field];});
  }
 }
}catch(error){}
document.addEventListener("input",update);document.addEventListener("change",update);
document.getElementById("export").addEventListener("click",()=>{
 const value=collect();
 const blob=new Blob([JSON.stringify(value,null,2)+"\n"],{type:"application/json;charset=utf-8"});
 const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="PM_RL1_独立盲评答卷.json";a.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
});update();
</script></body></html>
'''.replace('__BINDING__',binding)
    output=OUT/'independent_review.html'
    output.write_text(header+''.join(sections)+script)
    scripttext=script.split('<script>',1)[1].split('</script>',1)[0]
    Path('/tmp/rl1_review.js').write_text(scripttext)
    print(json.dumps(dict(path=str(output),pairs=len(data['items']),sha256=sha256_file(output),blank_by_default=True)))


if __name__=='__main__':main()
