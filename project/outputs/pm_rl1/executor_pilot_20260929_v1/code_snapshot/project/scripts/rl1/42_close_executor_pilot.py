#!/usr/bin/env python3
"""Assemble an offline audit browser, truthful cost ledger and preservation check."""
from collections import Counter
from html import escape
import json
from pathlib import Path
import statistics
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
OUT=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v1'

def save(name,obj):
    with (OUT/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def main():
    author=Path(json.loads((OUT/'author_pointer.json').read_text())['run_dir'])
    summary=json.loads((author/'summary.json').read_text())
    reviews=json.loads((OUT/'admission_reviews_private.json').read_text())
    admission=json.loads((OUT/'admission_summary.json').read_text())
    conditions=json.loads((OUT/'condition_contract_private.json').read_text())['conditions']
    evidence=json.loads((OUT/'legal_evidence_private.json').read_text())
    faults=json.loads((OUT/'source_quarantine_private.json').read_text())
    prep=json.loads((OUT/'preparation_manifest.json').read_text())
    rows=[]
    for r in reviews['rows']:
        raw=json.loads((author/(r['request_identity']+'.raw.json')).read_text())
        req=json.loads((author/(r['request_identity']+'.request.json')).read_text())
        rows.append(dict(**r,response=raw['text'],messages=req['messages'],output_tokens=raw['output_tokens']))
    payload=json.dumps(dict(rows=rows,conditions=conditions,evidence=evidence,faults=faults),ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    html='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PM-RL1 执行器小批量审计</title><style>
body{font:16px/1.6 system-ui,sans-serif;margin:auto;max-width:1100px;padding:28px;color:#172033;background:#f5f6f8}h1{font-size:26px}section,article{background:white;border:1px solid #d8dfe8;border-radius:8px;padding:18px;margin:14px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 system-ui}summary{cursor:pointer}label{margin-right:12px}select,input{font:inherit;padding:5px}small{color:#586174}.accept{border-left:5px solid #327f65}.reject{border-left:5px solid #b64e3a}.uncertain{border-left:5px solid #ab8127}.notice{background:#fff5dc;padding:14px}button{font:inherit}</style>
<h1>PM-RL1：108 条候选的开发审计</h1>
<p class="notice">89 条接受、15 条拒绝、4 条不确定。整体准入失败；0 次参数更新，无 X_l_pilot。这里展示参与开发的 AI 辅助判断，不是独立人类金标准，也不是盲评表，不收集提交。</p>
<section><h2>已确认的来源刷新问题</h2><div id="faults"></div></section>
<label>状态 <select id="status"><option value="">全部</option><option>accept</option><option>reject</option><option>uncertain</option></select></label>
<label>前缀 <select id="prefix"><option value="">全部</option></select></label><label>检索回复/理由 <input id="query"></label><p id="count"></p><main id="rows"></main>
<script id="data" type="application/json">PAYLOAD</script><script>
const d=JSON.parse(document.querySelector('#data').textContent),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.querySelector('#prefix').innerHTML+=Array.from({length:18},(_,i)=>`<option>${i+1}</option>`).join('');
document.querySelector('#faults').innerHTML=d.faults.records.map(f=>`<details><summary>${esc(f.family[0]+' / '+f.family[2])}</summary><p>${esc(f.rationale)}</p><pre>${esc(JSON.stringify(f.evidence,null,2))}</pre></details>`).join('');
function render(){const status=document.querySelector('#status').value,prefix=document.querySelector('#prefix').value,q=document.querySelector('#query').value.toLowerCase();const rs=d.rows.filter(r=>(!status||r.status===status)&&(!prefix||r.index===Number(prefix))&&(!q||(r.response+' '+r.rationale).toLowerCase().includes(q)));document.querySelector('#count').textContent=`显示 ${rs.length} / 108 条`;
document.querySelector('#rows').innerHTML=rs.map(r=>{let ev=d.evidence[r.index-1].evidence;return `<article class="${r.status}"><h3>${r.index} · ${esc(r.split)} · ${esc(r.condition)} · seed ${r.seed} · ${esc(r.status)}</h3><pre>${esc(r.response)}</pre><p><b>开发审查：</b>${esc(r.rationale)}</p><small>历史信息实际引用标记：${r.historical_uptake}；输出 ${r.output_tokens} tokens。标记不等于质量或收益。</small><details><summary>作者与 G 实际可见的完整输入</summary>${r.messages.map(m=>`<p><b>${esc(m.role)}</b></p><pre>${esc(m.content)}</pre>`).join('')}</details><details><summary>核验用合法历史（未回灌作者输入）</summary><p>当前日期 ${esc(ev.current_date)}</p>${ev.legal_past_sessions.map(s=>`<details><summary>${esc(s.id+' '+s.date)}</summary>${s.turns.map(t=>`<pre>${esc(t.id+' '+t.role+': '+t.text)}</pre>`).join('')}</details>`).join('')}</details><details><summary>审计身份</summary><pre>${esc(JSON.stringify({request:r.request_identity,raw:r.raw_identity,evidence:r.evidence_identity,checks:r.checks},null,2))}</pre></details></article>`}).join('')}
for(const id of ['status','prefix','query'])document.querySelector('#'+id).addEventListener('input',render);render();
</script></html>'''.replace('PAYLOAD',payload)
    (OUT/'pilot_review.html').write_text(html)
    cost=dict(local_author_submitted=len(summary['rows']),local_author_returned=len(rows),natural_stop=sum(r['finish_reason']=='natural_stop' for r in summary['rows']),
        author_input_tokens=sum(r['input_tokens'] for r in summary['rows']),author_output_tokens=sum(r['output_tokens'] for r in summary['rows']),
        output_tokens_min=min(r['output_tokens'] for r in summary['rows']),output_tokens_median=statistics.median(r['output_tokens'] for r in summary['rows']),
        output_tokens_max=max(r['output_tokens'] for r in summary['rows']),load_seconds=summary['load_seconds'],
        author_engine_wall_seconds=summary['engine_wall_seconds'],author_total_process_seconds=summary['total_seconds'],
        author_sum_request_seconds=sum(r['seconds'] for r in summary['rows']),concurrency=4,
        bge_preparation_total_seconds=prep['total_seconds'],bge_encoder_constructor_seconds=prep['bge_load_seconds'],bge_encode_seconds=prep['bge_encode_seconds'],
        pre_submission_failures=[dict(cause='vLLM numeric CUDA device requirement; initial UUID rejected before any engine request',submitted_calls=0,duration_seconds=None)],
        local_verifier_calls=0,coordinator_ai_reviews=108,independent_human_submissions=0,
        sft_updates=0,adapter_reloads=0,dev_nll_forwards=0,diagnostic_generations=0,
        paid_api_calls=0,paid_api_cost_usd=0,
        caveats=['Sum of concurrent request durations is not wall/GPU billing time.',
                 'Coordinator analysis and source review, package download, hashing and test work are not zero-cost; no monetary valuation measured.',
                 'No GPU electricity or rental USD price was assumed.',
                 'Author completion does not imply semantic admission; all 108 outputs remain in denominator.',
                 'Qwen nonthinking author throughput is not Qwen thinking-judge throughput or a future training-cost estimate.',
                 'BGE constructor is lazy; GPU model loading occurs during runtime_identity access and is included in preparation total, not constructor time.'])
    save('cost_accounting.json',cost)
    previous=json.loads((OUT/'preexisting_files.json').read_text());changed=[]
    for name,expected in previous.items():
        p=PROJECT.parent/name
        if not p.is_file() or sha256_file(p)!=expected:changed.append(name)
    original=Path('/home/tokkio/PM_RL1_单轮资源选择与执行_环境及训练实施方案_20260928.md')
    original_ok=sha256_file(original)=='7888613fac3a0820db2be012d9f85b59eb0dbb0a22d373a68eaaa3b6acb94a6b'
    save('preservation_check.json',dict(preexisting_checked=len(previous),changed=changed,original_plan_unchanged=original_ok))
    if changed or not original_ok:raise RuntimeError('preexisting files changed')
    save('stage_status.json',dict(status='PILOT_ADMISSION_CLOSED_SOURCE_REPAIR_REQUIRED',author_calls=108,
        semantic_review_counts=admission['counts'],source_refresh_failures_confirmed=3,
        lora_updates=0,executor_adapter_created=False,natural_support_ppo_updates=0,
        training_runner='implemented; admission guard exercised; GPU optimization/reload paths not yet exercised',
        source_quarantine='evidence-bound exclusion implementation tested; old artifacts unchanged; full corrected source pool not yet released',
        human_evaluation='protocol prepared, no new submissions',api_cost_usd=0,
        next_dependency='bounded MP provenance/time-state repair and evidence-opportunity sampling before a newly registered R05 batch; do not relabel this failed batch as a trained executor'))
    print(json.dumps(dict(cost=cost,status='closed',preexisting_unchanged=len(previous)),ensure_ascii=False))

if __name__=='__main__':main()
