#!/usr/bin/env python3
"""Build a local development evidence browser; never an independent review form."""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.evidence import evidence_turns
from metacom_pm.rl1.judge_indexed import response_units
from metacom_pm.rl1.schema import digest

OUT = PROJECT/'outputs/pm_rl1/measurement_resolution_20260929_v1'

TEMPLATE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PM-RL1 开发证据核查</title>
<style>
body{margin:0;color:#17212b;background:#f5f7fa;font:16px/1.6 system-ui,sans-serif}
header,main{max-width:1440px;margin:auto;padding:20px}h1{font-size:26px;margin:0 0 8px}
.notice{color:#5c4b23;background:#fff5d8;padding:12px;border-radius:8px}
.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:16px 0}
select{max-width:100%;flex:1}button,select,input{font:inherit;padding:7px}
.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}
.panel{background:white;padding:20px;border:1px solid #d8e0e9;border-radius:10px;min-width:0}
.text{white-space:pre-wrap;overflow-wrap:anywhere}.muted{font-size:14px;color:#526272}
.assessment,.source{border-top:1px solid #d8e0e9;padding:14px 0}.source.selected{border-left:4px solid #176baf;padding-left:12px}
.tag{font-size:14px;background:#e9f1f8;padding:3px 7px;border-radius:4px}.links{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.links button{color:#125a96;background:#fff;border:1px solid #b7cce0;border-radius:5px;font-size:14px}
h2{font-size:21px;margin:0 0 12px}h3{font-size:17px;margin:14px 0 6px}#sources{max-height:78vh;overflow:auto}
details{margin-top:14px}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}a{color:#125a96}
@media(max-width:850px){.grid{grid-template-columns:1fr}header,main{padding:12px}}
</style>
<header><h1>PM-RL1 · 开发证据核查</h1>
<div class="notice">这里公开条件与模型评分，用于复核已完成的开发实验。不是盲评表，也不是人工金标准；引用存在不等于推理正确。没有提交按钮，不收集人评。</div>
<p id="overview" class="muted"></p>
<div class="toolbar"><label for="filter">条件</label><select id="filter"></select><button id="prev">上一条</button><button id="next">下一条</button></div>
<div class="toolbar"><label for="case">记录</label><select id="case"></select></div></header>
<main class="grid"><section class="panel"><h2 id="title"></h2><p id="state" class="tag"></p>
<h3>当前需要 · 原始最后一条 seeker 发言</h3><div id="need" class="text"></div>
<h3>被评回复 · 完整原文</h3><div id="reply" class="text"></div><div id="audit" class="notice" hidden></div>
<h3>模型的质量理由</h3><div id="quality" class="text"></div><div id="qrefs" class="links"></div>
<h3>模型的逐项判断</h3><div id="assessments"></div><p id="coverage" class="muted text"></p>
<details><summary>原始结构化判断与绑定</summary><pre id="raw"></pre></details>
</section><section class="panel"><h2>合法证据 · 原文</h2>
<p class="muted">默认显示模型引用的 turns。来源高亮仅表示被引用，不表示支持关系已验证。完整历史仍可展开；不能用选摘中未找到，证明整段历史没有。</p>
<label><input id="all" type="checkbox"> 展开全部合法历史和当前前缀</label>
<p id="sourcecount" class="muted"></p><div id="sources"></div></section></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('data').textContent), $=id=>document.getElementById(id);
const fields=['全部',...new Set(data.rows.map(r=>r.condition))];
for(const f of fields){const o=document.createElement('option');o.textContent=f;o.value=f;$('filter').append(o)}
$('overview').textContent=`${data.rows.length} 条记录；${Object.keys(data.evidence).length} 份不同证据边界。单轮 q=0…4，m=0 / 0.25 / 1。所有结果仍为开发候选。`;
let visible=[];
function label(r){return `${r.exam_section} · ${r.pilot_index} · ${r.condition} · repeat ${r.repeat} · q=${r.q} / m=${r.m}`}
function selectRows(){visible=data.rows.filter(r=>$('filter').value==='全部'||r.condition===$('filter').value);$('case').replaceChildren();visible.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=label(r);$('case').append(o)});show()}
function text(tag,value,cls){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e}
function refs(node,ids){node.replaceChildren();for(const id of ids||[]){const b=text('button',id);b.onclick=()=>{$('all').checked=true;showSources();document.getElementById('source-'+id)?.scrollIntoView({block:'nearest',behavior:'smooth'})};node.append(b)}}
function current(){return visible[Number($('case').value)||0]}
function selected(r){return new Set([...(r.judge.q_rationale?.source_turn_ids||[]),...(r.judge.assessments||[]).flatMap(a=>a.source_turn_ids||[])])}
function showSources(){const r=current(),e=data.evidence[r.evidence_id],ids=selected(r);$('sources').replaceChildren();let n=0;for(const [id,t] of Object.entries(e.turns)){if(!$('all').checked&&!ids.has(id))continue;n++;const box=text('div','','source'+(ids.has(id)?' selected':''));box.id='source-'+id;box.append(text('b',id+' · '+t.role));box.append(text('div',t.text,'text'));$('sources').append(box)}$('sourcecount').textContent=`显示 ${n} / ${Object.keys(e.turns).length} turns；当前日期 ${e.current_date}`}
function show(){const r=current();if(!r)return;$('title').textContent=label(r);$('state').textContent=r.measurement_status+(r.error?' · '+r.error:'');$('need').textContent=data.evidence[r.evidence_id].last_seeker;$('reply').textContent=r.reply;$('quality').textContent=r.judge.q_rationale?.reason||'没有有效质量理由';refs($('qrefs'),r.judge.q_rationale?.source_turn_ids);$('assessments').replaceChildren();for(const a of r.judge.assessments||[]){const box=text('div','','assessment');box.append(text('b',`${a.response_unit_id} · ${a.relation} · severity ${a.severity}`));box.append(text('div',r.units[a.response_unit_id]||'','text'));box.append(text('div',a.reason,'text'));const links=text('div','','links');refs(links,a.source_turn_ids);box.append(links);$('assessments').append(box)}$('coverage').textContent=r.judge.coverage||'';$('raw').textContent=JSON.stringify({request_id:r.request_id,measurement_file:r.measurement_file,judge:r.judge},null,2);const notes=[];if(r.exam_section==='pilot'&&r.condition==='style'&&[7,8].includes(r.pilot_index))notes.push('已确认的考卷问题：缩写展开把 has been 错写为 is been，本题不属于纯风格不变性对照。原结果保留。');if(r.exam_section==='pilot'&&r.condition==='damage'&&r.pilot_index===6)notes.push('已确认的推理问题：去世不能证明此前没有和解；实际关键证据是 C:T009。核对模型是否真正使用了该证据。');$('audit').hidden=!notes.length;$('audit').textContent=notes.join('\n');showSources()}
$('filter').onchange=selectRows;$('case').onchange=show;$('all').onchange=showSources;
$('prev').onclick=()=>{$('case').selectedIndex=Math.max(0,$('case').selectedIndex-1);show()};$('next').onclick=()=>{$('case').selectedIndex=Math.min(visible.length-1,$('case').selectedIndex+1);show()};selectRows();
</script></html>'''


def main():
    read=lambda p:json.loads(p.read_text())
    pointer=read(OUT/'scoped_common_v4_pointer.json'); folder=Path(pointer['run_dir'])
    assert sha256_file(folder/'summary.json')==pointer['summary_sha256']
    exam=read(OUT/'scoped_common_exam_private.json'); lookup={j['job_id']:j for j in exam['jobs']}
    evidence={}; rows=[]
    for row in read(folder/'summary.json')['rows']:
        j=lookup[row['job_id']]; eid=digest(j['evidence'])
        evidence[eid]=dict(turns=evidence_turns(j['evidence']),current_date=j['evidence']['current_date'],
            last_seeker=next(t['text'] for t in reversed(j['evidence']['current_prefix']) if t['role']=='seeker'))
        f=folder/(row['request_id']+'.measurement.json'); measured=read(f)
        rows.append(row|dict(reply=j['reply'],units={u['id']:u['text'] for u in response_units(j['reply'])},
                            evidence_id=eid,judge=measured.get('flat_judge_output',{}),
                            measurement_file=str(f.relative_to(OUT))))
    rows.sort(key=lambda r:(r['exam_section'],r['pilot_index'],r['condition'],r['repeat']))
    payload=json.dumps(dict(evidence=evidence,rows=rows),ensure_ascii=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    dest=OUT/'evidence_browser.html';dest.write_text(TEMPLATE.replace('__DATA__',payload))
    print(json.dumps(dict(path=str(dest),rows=len(rows),evidence_boundaries=len(evidence),bytes=dest.stat().st_size,
        human_review_form=False,untrusted_source_inserted_as_text_only=True)))


if __name__=='__main__':main()
