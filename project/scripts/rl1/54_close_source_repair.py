#!/usr/bin/env python3
"""Close the source-repair and explicitly post-hoc engineering evidence trail."""
from collections import Counter
from html import escape as esc
import json
from pathlib import Path
import statistics
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
REPAIR=PROJECT/'outputs/pm_rl1/source_repair_20260929_v2'
PILOT=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v2'
ENG=PROJECT/'outputs/pm_rl1/executor_engineering_20260929_v1'

def read(path):return json.loads(path.read_text())
def save(path,obj):
    with path.open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def pre(text):return '<pre>'+esc(text)+'</pre>'

def main():
    author=Path(read(PILOT/'author_pointer.json')['run_dir']);a=read(author/'summary.json')
    train=Path(read(ENG/'training_pointer.json')['run_dir']);t=read(train/'summary.json');reload=read(train/'reload.json')
    diag=Path(read(ENG/'diagnostic_pointer.json')['run_dir']);d=read(diag/'summary.json')
    admission=read(PILOT/'admission_summary.json');reviews=read(PILOT/'admission_reviews_private.json')
    assert len(a['rows'])==108 and len(d['rows'])==36 and reload['passed']
    src=read(REPAIR/'profile_reassertion_reviews.json');projection=read(REPAIR/'prior_prefix_projection_audit.json')
    prep=read(PILOT/'preparation_manifest.json')
    cost=dict(new_paid_api_calls=0,new_paid_api_usd=0,new_human_submissions=0,
        author_calls=len(a['rows']),author_natural_stop=sum(r['finish_reason']=='natural_stop' for r in a['rows']),
        author_input_tokens=sum(r['input_tokens'] for r in a['rows']),author_output_tokens=sum(r['output_tokens'] for r in a['rows']),
        author_output_min=min(r['output_tokens'] for r in a['rows']),author_output_median=statistics.median(r['output_tokens'] for r in a['rows']),
        author_output_max=max(r['output_tokens'] for r in a['rows']),
        author_load_seconds=a['load_seconds'],author_engine_wall_seconds=a['engine_wall_seconds'],author_total_seconds=a['total_seconds'],
        author_sum_concurrent_request_seconds=sum(r['seconds'] for r in a['rows']),
        bge_preparation_seconds=prep['total_seconds'],bge_model_identity_load_seconds=prep['bge_load_seconds'],
        optimization_steps=t['steps'],train_examples=61,accepted_dev_examples=29,
        sft_total_seconds=t['total_seconds'],sft_load_seconds=t['load_seconds'],
        sft_peak_allocated_bytes=t['peak_allocated_bytes'],reload_total_seconds=reload['total_seconds'],
        diagnostic_calls=36,diagnostic_total_seconds=d['total_seconds'],
        diagnostic_input_tokens=sum(r['input_tokens'] or 0 for r in d['rows']),
        diagnostic_output_tokens=sum(r['output_tokens'] or 0 for r in d['rows']),
        caveats=['GPU electricity/rental and researcher/AI review time not monetized; zero API bill is not zero research cost.',
                 'Concurrent request-duration sums are not wall time.',
                 'Post-hoc subset NLL and diagnostic outputs are engineering evidence, not calibrated reward or helpfulness gains.'])
    save(REPAIR/'cost_accounting.json',cost)
    checks={}
    for file in ('preexisting_files.json','prior_run_files.json'):
        old=read(REPAIR/file)
        changed=[n for n,h in old.items() if not (PROJECT.parent/n).is_file() or sha256_file(PROJECT.parent/n)!=h]
        checks[file]=dict(checked=len(old),changed=changed)
        if changed:raise RuntimeError('preservation failed: '+str(changed))
    original=Path('/home/tokkio/PM_RL1_单轮资源选择与执行_环境及训练实施方案_20260928.md')
    checks['original_plan_unchanged']=sha256_file(original)=='7888613fac3a0820db2be012d9f85b59eb0dbb0a22d373a68eaaa3b6acb94a6b'
    assert checks['original_plan_unchanged']
    save(REPAIR/'preservation_check.json',checks)
    status=dict(status='SOURCE_GATE_INTEGRATED_ENGINEERING_CYCLE_COMPLETED',source_audit=src['counts'],
        source_scope='101 reassertions plus 3 source/state exclusions; selected 36 resources reviewed. Not full-corpus qualification.',
        source_projection_removed_unique=projection['removed_unique'],source_projection_removed_occurrences=projection['removed_occurrences'],
        source_gate_conditions=54,original_pilot_gate_passed=False,original_pilot_review_counts=admission['counts'],
        original_missing_cells=admission['missing_prefix_conditions'],
        engineering_post_hoc=True,engineering_rows=90,engineering_eligible_for_research_or_rl=False,
        optimization_steps=t['steps'],base_weights_unchanged=t['frozen_base_hash_before']==t['frozen_base_hash_after'],
        baseline_dev_nll=t['baseline_dev_nll'],selected_dev_nll=t['selected_dev_nll'],selected_epoch=t['selected_epoch'],
        reload_passed=reload['passed'],reload_nll_delta=reload['absolute_nll_delta'],
        diagnostics_by_arm={arm:dict(Counter(r['finish_reason'] for r in d['rows'] if r['arm']==arm)) for arm in ('base','lora')},
        natural_support_ppo_updates=0,new_human_submissions=0,new_paid_api_usd=0,
        next='Use completed diagnostics to separate teacher data coverage, executor behavior and reward measurement. Avoid repeating the identical author batch to chase coverage; keep human assessment for frozen systems.')
    save(REPAIR/'stage_status.json',status)
    body=['<h1>PM-RL1 来源修复与工程验证</h1>',
        '<p class="notice">101 条来源审查、108 条作者回复、36 条工程对照回复。全部为开发材料和 AI 辅助判断；原训练合同未通过，事后工程 adapter 不具备正式研究/RL 资格。本页不收集人工答卷。</p>',
        '<label>筛选文字 <input id="q" placeholder="如 p18、reject、recruiter"></label>',
        '<details><summary>阶段状态与费用</summary>'+pre(json.dumps(dict(status=status,cost=cost),ensure_ascii=False,indent=2))+'</details>',
        '<h2>101 次新引文核对</h2>']
    for r in src['rows']:
        body.append('<article><details><summary>'+esc(f"{r['index']} · {r['owner']} · {r['slot']} · {r['citation_status']}")+'</summary>'+pre(r['rationale'])+
            '<b>原证据 '+esc(r['prior_date'])+'</b>'+pre('\n'.join(s['exact_text'] for s in r['prior_spans']))+
            '<b>新证据 '+esc(r['new_date'])+'</b>'+pre('\n'.join(s['exact_text'] for s in r['new_spans']))+'</details></article>')
    body.append('<h2>108 条作者回复及审查</h2>')
    for r in reviews['rows']:
        raw=read(author/(r['request_identity']+'.raw.json'));req=read(author/(r['request_identity']+'.request.json'))
        body.append('<article><details><summary>'+esc(f"{r['index']} · {r['split']} · {r['condition']} / {r['seed']} · {r['status']}")+'</summary>'+pre(raw['text'])+
            '<b>审查</b>'+pre(r['rationale'])+'<details><summary>精确可见输入</summary>'+pre(json.dumps(req['messages'],ensure_ascii=False,indent=2))+'</details></details></article>')
    body.append('<h2>18 组相同输入：基础模型 / 工程 adapter</h2>')
    pairs={}
    for r in d['rows']:pairs.setdefault((r['index'],r['condition']),{})[r['arm']]=r
    for (i,c),pair in sorted(pairs.items()):
        body.append('<article><details><summary>'+esc(f'{i} · {c}')+'</summary>')
        for arm in ('base','lora'):
            r=pair[arm];raw=read(diag/(r['request_id']+'.raw.json'))
            body.append('<h3>'+esc(arm+' · '+r['finish_reason'])+'</h3>'+pre(raw['text']))
        body.append('<details><summary>共同精确输入</summary>'+pre(json.dumps(read(diag/(pair['base']['request_id']+'.request.json'))['messages'],ensure_ascii=False,indent=2))+'</details></details></article>')
    html='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PM-RL1 修复与工程验证</title><style>body{max-width:1100px;margin:24px auto;padding:20px;font:16px/1.6 system-ui;background:#f7f8fa;color:#192335}article,details{margin:10px 0}article{background:white;border:1px solid #d5dce5;padding:12px;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 system-ui}summary{cursor:pointer}.notice{background:#fff2d9;padding:16px}input{font:inherit;padding:6px;min-width:300px}</style>'''+''.join(body)+'''<script>document.querySelector('#q').addEventListener('input',e=>{let q=e.target.value.toLowerCase();document.querySelectorAll('article').forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(q))})</script></html>'''
    (REPAIR/'review.html').write_text(html)
    print(json.dumps(dict(status=status,cost=cost),ensure_ascii=False))
if __name__=='__main__':main()
