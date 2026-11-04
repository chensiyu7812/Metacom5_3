"""Assemble exact before/after outputs and fit diagnostics, never quality scores."""
import html
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json
ROOT=PROJECT/'outputs/pm_rl1/executor_revision_20261104_v2'


def read(path):return json.loads(path.read_text())


def main():
    inputs=read(ROOT/'INPUTS_PRIVATE.json');cards=read(ROOT/'EVAL_CARDS_PRIVATE.json')
    training=read(ROOT/'TRAINING_PRIVATE.json');mapping=read(ROOT/'CANDIDATE_MAPPING.json')
    baselines={k:v['raw'] for k,v in read(ROOT/'REUSED_BASELINES_PRIVATE.json').items()};replays=read(ROOT/'PROTOCOL.json')['technical_failure']['original_replays']
    for job in read(ROOT/'BASELINE_JOBS_PRIVATE.json'):
        raw=read(ROOT/'baseline_G'/(job['request']['request_id']+'.raw.json'));key=job['input_identity']
        if job.get('replay'):
            old=baselines[key];replays.append(dict(input_identity=key,text_equal=old['text']==raw['text'],
                tokens_equal=old['output_token_ids']==raw['output_token_ids']))
        else:baselines[key]=raw
    rows=[]
    for key,rid in mapping.items():
        raw=read(ROOT/'candidate_G'/(rid+'.raw.json'));item=inputs[key];old=baselines[key]
        related=[c for c in cards if c['input_identity']==key]
        rows.append(dict(input_identity=key,candidate_request_identity=rid,case=related[0]['case'],
            conditions=[c['condition'] for c in related],case_used_for_updates=related[0]['used_for_updates'],
            exact_input_used_for_updates=any(r['input_identity']==key for r in training),
            selected_keys=item['selected_keys'],before=old['text'],after=raw['text'],
            before_identity=digest(old['text']),after_identity=digest(raw['text']),text_changed=old['text']!=raw['text'],
            before_output_tokens=old['output_tokens'],after_output_tokens=raw['output_tokens'],
            before_G_seconds=old['generation_seconds'],after_G_seconds=raw['generation_seconds'],
            quality=None,reward=None,latency_scope='G component, mixed old cache timing; not matched deployment latency'))
    save_json(ROOT/'RESULTS_PRIVATE.json',rows)
    metrics=[]
    points=[(0,read(ROOT/'training/baseline_fit.json'),read(ROOT/'training/baseline_contrast.json'))]
    points += [(e['epoch'],e['fit'],e['contrast']) for e in read(ROOT/'training/epochs.json')]
    for epoch,fit,cross in points:
        f={r['row_id']:r['nll'] for r in fit['rows']};c={r['row_id']:r['nll'] for r in cross['rows']}
        for case in ('N21','N23'):
            group={r['condition']:r for r in training if r['case']==case};margins={}
            for cond in ('OFF','MEMORY','OTHER'):
                actual=f[group[cond]['id']];opposite=c[case+':'+cond+':cross_target']
                margins[cond]=opposite-actual if cond=='MEMORY' else actual-opposite
            metrics.append(dict(epoch=epoch,case=case,memory_preference_margin=margins,
                ON_minus_OFF=margins['MEMORY']-margins['OFF'],ON_minus_OTHER=margins['MEMORY']-margins['OTHER'],
                definition='margin = token-mean NLL(generic target) - token-mean NLL(memory target); training-target diagnostic only'))
    save_json(ROOT/'FIT_CONTRAST.json',metrics)
    save_json(ROOT/'SUMMARY_GENERATION.json',dict(unique_pairs=len(rows),text_changed=sum(r['text_changed'] for r in rows),
        exact_training_inputs=sum(r['exact_input_used_for_updates'] for r in rows),
        update_excluded_inputs=sum(not r['case_used_for_updates'] for r in rows),replays=replays,
        generated_candidate=len(rows),new_human_labels=0,new_quality_rewards=0,api_cost_usd=0))
    esc=lambda s:html.escape(s if isinstance(s,str) else json.dumps(s,ensure_ascii=False,indent=2))
    parts=['<!doctype html><html lang="zh"><meta charset="utf-8"><title>执行器有限监督试验</title>',
           '<style>body{max-width:1400px;margin:28px auto;font:16px/1.6 system-ui;background:#f6f7fa;color:#172330}article{background:white;padding:22px;margin:24px 0;border:1px solid #ccd5df}pre{white-space:pre-wrap;overflow-wrap:anywhere}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}summary{cursor:pointer}@media(max-width:800px){.pair{display:block}}</style>',
           '<h1>执行器有限监督试验：完整原回复与候选回复</h1><p>17条AI弱示范，3轮固定训练。32输入、12个已暴露train情境；6情境未参加本轮更新，不是独立测试集。此页用于核查，不是人评问卷。历史引用、拟合或回复变短都不自动成为综合收益奖励。</p>']
    for row in sorted(rows,key=lambda r:(r['case'],r['conditions'])):
        item=inputs[row['input_identity']]
        parts.append('<article><h2>'+esc(row['case']+' / '+', '.join(row['conditions']))+'</h2><p>'+esc(dict(
            case_updated=row['case_used_for_updates'],exact_input_trained=row['exact_input_used_for_updates'],
            original_tokens=row['before_output_tokens'],candidate_tokens=row['after_output_tokens']))+'</p><div class="pair"><section><h3>原执行器</h3><pre>'+esc(row['before'])+'</pre></section><section><h3>候选执行器</h3><pre>'+esc(row['after'])+'</pre></section></div><details><summary>完整当前输入与资源</summary><pre>'+esc(item['messages'])+'</pre></details></article>')
    (ROOT/'REVIEW_ZH.html').write_text('\n'.join(parts)+'</html>')
    print(json.dumps(read(ROOT/'SUMMARY_GENERATION.json'),ensure_ascii=False))


if __name__=='__main__':main()
