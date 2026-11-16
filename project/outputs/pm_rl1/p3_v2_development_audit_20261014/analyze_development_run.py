#!/usr/bin/env python3
"""Offline, lossless comparison of one authorized development run.

Never loads models or decrypts labels. No pass/fail qualification is inferred.
"""
from collections import Counter
import argparse
import csv
import json
from pathlib import Path
from statistics import median
import sys

PROJECT=Path('/home/tokkio/Metacom5_3/project')
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.calibration_workflow import bind_measurement
from metacom_pm.rl1 import judge_completion as old_scorer, judge_completion_candidate as new_scorer


def read(p):return json.loads(p.read_text())


def save(p,obj):
    with p.open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


def direction(scores):
    if any(s is None or s.get('q') is None or s.get('m') is None for s in scores):return None
    a,b=[s['q']/4-s['m'] for s in scores]
    return 'A' if a>b else 'B' if b>a else 'tie'


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    base=PROJECT/'outputs/pm_rl1';oldroot=base/'completion_20260930_v2/P3/candidate_v1'
    newroot=base/'p3_v2_after_confirmation_20261014';newrun=newroot/'runs/development'
    oldrun=Path(read(oldroot/'development_pointer.json')['run_dir'])
    jobs={j['job_id']:j for j in read(oldroot/'jobs_private.json')}
    plan=read(newroot/'development_plan.json');summary=read(newrun/'summary.json')
    old_summary=read(oldrun/'summary.json')
    assert plan['phase']=='development' and len(plan['requests'])==33
    allowed={j['job_id'] for j in jobs.values() if j['group'] in ('development','recheck_probe')}
    assert {r['job_id'] for r in plan['requests']}==allowed
    assert summary['planned']==33 and 0<=summary['physical_calls_this_invocation']<=33
    assert len({r['job_id'] for r in summary['rows']})==len(summary['rows'])
    assert {r['job_id'] for r in summary['rows']}<=allowed
    receipts={};by={};bound=[]
    for name,root,run,s,scorer in [('old',oldroot,oldrun,old_summary,old_scorer),('new',newroot,newrun,summary,new_scorer)]:
        runtime=read(run/'runtime.json');protocol=read(root/'protocol.json');by[name]={}
        for row in s['rows']:
            j=jobs[row['job_id']];assert j['group'] in ('development','recheck_probe')
            paths=[run/(row['request_id']+suffix) for suffix in ('.request.json','.raw.json','.measurement.json')]
            request,raw,m=map(read,paths)
            b=bind_measurement(j,request,raw,m,runtime=runtime,protocol=protocol,scorer=scorer,cache_hit=row['cache_hit'])
            bound.append(dict(version=name,**b));receipts.update({str(p):sha256_file(p) for p in paths})
            by[name][j['job_id']]=dict(job_id=j['job_id'],request_id=row['request_id'],status=m['measurement_status'],
                q=m['q'],m=m['m'],utility=m['candidate_utility'],finish_reason=raw['finish_reason'],
                seconds=raw['seconds'],input_tokens=raw['input_tokens'],output_tokens=raw['output_tokens'],
                raw_final_json=json.loads(raw['text'].split('</think>')[-1].strip()) if m.get('flat_judge_output') else None,
                parsed=m.get('parsed'),raw_path=str(paths[1]),measurement_path=str(paths[2]))
    comparisons=read(base/'human_acceptance_20261014_v2/intake/development_comparisons_private.json')
    labels=read(base/'development_closeout_20261014_v1/acceptance_final/development_intake_private.json')
    chen={r['pair_id']:r for r in labels if r['reviewer']=='Chen'}
    pairs=[];scores=[]
    for c in comparisons:
        human=chen[c['pair_id']];swap=human['mapping']['swapped'];sides={}
        for i,s in enumerate(c['scores']):
            side='A' if i==int(swap) else 'B';j=jobs[s['job_id']]
            sides[side]=dict(job_id=j['job_id'],reply=j['reply'],evidence_identity=digest(j['evidence']),
                old=by['old'][j['job_id']],new=by['new'].get(j['job_id']))
            scores.append(dict(Chen_order=c['Chen_order'],pair_id=c['pair_id'],side=side,**sides[side]))
        pref=human['preference']['value']
        pairs.append(dict(Chen_order=c['Chen_order'],pair_id=c['pair_id'],kind=c['kind'],contrast=c['contrast'],
            control_type=c['control_type'],owner=c['owner'],prefix_identity=c['prefix_identity'],
            raw_human_label=human['raw_label'],accepted_preference=pref,
            human_label_identity=human['raw_label_identity'],human_provenance=human['provenance'],
            old_direction=direction([sides[k]['old'] for k in ('A','B')]),
            new_direction=direction([sides[k]['new'] for k in ('A','B')]),sides=sides))
    stats={}
    for version in ('old','new'):
        def metric(group,kind=None):
            rows=[p for p in pairs if p['accepted_preference'] in group and
                  (kind is None or p['kind']==kind)]
            return dict(planned_pairs=len(rows),computable_pairs=sum(p[version+'_direction'] is not None for p in rows),
                matched=sum(p[version+'_direction']==p['accepted_preference'] for p in rows),
                nonmatch=sum(p[version+'_direction'] is not None and p[version+'_direction']!=p['accepted_preference'] for p in rows))
        risks=Counter();risk_unknown=0;risk_computable=0
        for p in pairs:
            for side in ('A','B'):
                h=p['raw_human_label']['risk_'+side];a=p['sides'][side][version]
                if h not in ('none_detected','local','severe'):
                    risk_unknown+=1;continue
                if a and a['m'] is not None:
                    risks[h+' -> '+str(a['m'])]+=1;risk_computable+=1
        stats[version]=dict(all_comparable=metric(('A','B','tie')),clear=metric(('A','B')),ties=metric(('tie',)),
            accepted_uncertain=1,risk_enum_computable=risk_computable,risk_unknown=risk_unknown,
            risk_enum_cross_tab=dict(risks),risk_caveat='Raw human options, not source-adjudicated gold; Du excluded',
            by_kind={kind:dict(all_comparable=metric(('A','B','tie'),kind),
                clear=metric(('A','B'),kind),ties=metric(('tie',),kind)) for kind in ('natural','control')})
    changed=[dict(Chen_order=s['Chen_order'],side=s['side'],old_q=s['old']['q'],old_m=s['old']['m'],
                  new_q=s['new']['q'],new_m=s['new']['m']) for s in scores if s['new'] and
                  (s['old']['q'],s['old']['m'])!=(s['new']['q'],s['new']['m'])]
    reported={r['job_id'] for r in summary['rows']}
    started_ids={r['job_id'] for r in plan['requests'][:summary['physical_calls_this_invocation']]}
    technical=[r['job_id'] for r in summary['rows'] if r['measurement_status'] not in ('measured_candidate','semantic_uncertainty')]
    unknown=[r['job_id'] for r in summary['rows'] if r['measurement_status']=='semantic_uncertainty']
    time_sum=sum(r['seconds'] for r in summary['rows'])
    result=dict(status='DEVELOPMENT_COMPARISON_NOT_INDEPENDENT_QUALIFICATION',planned=33,
        started=summary['physical_calls_this_invocation'],finished=len(summary['rows']),
        primary_finished=sum(jobs[r['job_id']]['group']=='development' for r in summary['rows']),
        probe_finished=sum(jobs[r['job_id']]['group']=='recheck_probe' for r in summary['rows']),
        never_started=sorted(allowed-started_ids),started_without_saved_result=sorted(started_ids-reported),
        technical_failures=technical,semantic_uncertainty=unknown,statuses=summary['statuses'],
        engine_wall_seconds=summary['engine_wall_seconds'],load_seconds=summary['load_seconds'],
        overlapping_individual_seconds_sum=time_sum,API_usd=0,
        source_primary_calls_before=33,cumulative_P3_calls=33+summary['physical_calls_this_invocation'],
        remaining_of_140=140-33-summary['physical_calls_this_invocation'],
        remaining_after_reserved_59=140-33-summary['physical_calls_this_invocation']-59,
        stats=stats,changed_components=changed,
        independent_origins=1,development_pairs=16,owners=len({p['owner'] for p in pairs}),
        prefixes=len({p['prefix_identity'] for p in pairs}),reward_qualified=False,
        frozen_validation_read=False,independent_repeat12_run=False)
    probe_jobs=[j for j in jobs.values() if j['group']=='recheck_probe']
    probe=[dict(job_id=j['job_id'],primary_job_id=j['primary_job_id'],old=by['old'].get(j['job_id']),
        new=by['new'].get(j['job_id']),new_primary=by['new'].get(j['primary_job_id']),
        does_not_replace_primary=True,not_the_twelve_independent_repeats=True) for j in probe_jobs]
    result['token_usage']={name:dict(input_tokens=sum(r['input_tokens'] for r in s['rows']),
        output_tokens=sum(r['output_tokens'] for r in s['rows']),
        request_seconds_median=median(r['seconds'] for r in s['rows']) if s['rows'] else None)
        for name,s in [('old',old_summary),('new',summary)]}
    result['old_engine_wall_seconds']=old_summary['engine_wall_seconds']
    common=[p for p in pairs if p['accepted_preference'] in ('A','B','tie') and
            p['old_direction'] is not None and p['new_direction'] is not None]
    result['same_available_pairs_comparison']=dict(n=len(common),
        Chen_orders=[p['Chen_order'] for p in common],
        old_matched=sum(p['old_direction']==p['accepted_preference'] for p in common),
        new_matched=sum(p['new_direction']==p['accepted_preference'] for p in common))
    completed={r['job_id']:r for r in summary['rows']}
    ledger=[]
    for i,entry in enumerate(plan['requests']):
        row=completed.get(entry['job_id'])
        started=i<summary['physical_calls_this_invocation']
        ledger.append(dict(dispatch_ordinal=i+1,started=started,job_id=entry['job_id'],
            request_id=entry['request_id'],group=jobs[entry['job_id']]['group'],
            runtime_identity=read(newroot/'runtime.json')['identity'],
            request_attempt_index=entry['attempt'],attempt_number_this_run=1 if started else None,
            included_in_initial_four=i<4,cache_hit=False if started else None,
            measurement_status=row['measurement_status'] if row else
                'STARTED_WITHOUT_SAVED_RESULT' if started else 'UNATTEMPTED',
            actual_result=row,API_usd=0))
    save(out/'actual_call_ledger.json',ledger)
    input_paths=[oldroot/'jobs_private.json',oldroot/'protocol.json',newroot/'protocol.json',
        newroot/'runtime.json',newroot/'development_plan.json',newrun/'summary.json',
        base/'development_closeout_20261014_v1/acceptance_final/development_intake_private.json',
        base/'human_acceptance_20261014_v2/intake/development_comparisons_private.json']
    receipts.update({str(p):sha256_file(p) for p in input_paths})
    save(out/'comparison_summary.json',result);save(out/'pair_comparisons_private.json',pairs)
    save(out/'reply_comparisons_private.json',scores);save(out/'recheck_probe_private.json',probe)
    save(out/'verified_measurement_bindings.json',bound);save(out/'source_file_hashes.json',receipts)
    with (out/'逐题分项差异.csv').open('x',encoding='utf-8-sig',newline='') as f:
        fields=['Chen题号','pair_id','侧','原人工偏好','人评风险原值','旧q','旧m','旧U','新状态','新q','新m','新U','原始新理由','job_id']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for p in pairs:
            for side in ('A','B'):
                s=p['sides'][side];o=s['old'];n=s['new'] or {}
                reason=(n.get('raw_final_json') or {}).get('q_rationale',{}).get('reason','')
                w.writerow(dict(zip(fields,[p['Chen_order'],p['pair_id'],side,p['raw_human_label']['preference'],p['raw_human_label']['risk_'+side],o['q'],o['m'],o['utility'],n.get('status','UNATTEMPTED'),n.get('q'),n.get('m'),n.get('utility'),reason,s['job_id']])))
    lines=['# 开发16题新旧原始理由对照','',
        '仅开发集；A/B按Chen已核对映射。Du为派生记录，不增加独立观察。以下是模型原始最终JSON，尚不等于语义正确。',
        '完整thinking和token记录保留在对应raw.json中；本文仅呈现最终回答。','']
    for p in sorted(pairs,key=lambda x:x['Chen_order']):
        lines.extend([f"## 第{p['Chen_order']}题",'',f"pair_id: `{p['pair_id']}`",
            f"人工偏好接收值: `{p['accepted_preference']}`；旧/新裁判方向: `{p['old_direction']}` / `{p['new_direction']}`",'',
            '人工原值（保持原文）：','```json',json.dumps(p['raw_human_label'],ensure_ascii=False,indent=2),'```',''])
        for side in ('A','B'):
            s=p['sides'][side];lines.extend([f'### Chen {side}',s['reply'],'',f"job_id: `{s['job_id']}`",''])
            for version,title in [('old','旧主评分'),('new','新主评分')]:
                r=s[version]
                if r is None:lines.extend([title+': 尚无落盘结果','']);continue
                lines.extend([f"{title}：q={r['q']}, m={r['m']}, U={r['utility']}；{r['status']}",
                    f"原始输出：`{r['raw_path']}`",'```json',
                    json.dumps(r['raw_final_json'],ensure_ascii=False,indent=2),'```',''])
        source=jobs[p['sides']['A']['job_id']]['evidence']['current_prefix']
        lines.extend(['### 本题当前前缀（来源原文）','```json',json.dumps(source,ensure_ascii=False,indent=2),'```',''])
    lines.extend(['## 既有重检探针（不替换主评分）','```json',json.dumps(probe,ensure_ascii=False,indent=2),'```',''])
    with (out/'新旧原始理由对照_开发16题.md').open('x') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
