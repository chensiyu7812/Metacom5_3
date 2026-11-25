"""Independent CPU recomputation of frozen J06 observations and STOP/MS costs.

All 96 actual replies are joined to unchanged original atom/support observations.
New candidate and task-label switches are explicitly post-hoc diagnostics only.
"""
import argparse,json,re
from collections import Counter,defaultdict
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.journal.selective_memory import choose,visible_features


def jl(p):return [json.loads(s) for s in Path(p).read_text().splitlines()]


def interval_difference(a,b,shared=False):
    if a is None or b is None:return None
    return [0,0] if shared else [a[0]-b[1],a[1]-b[0]]


def metrics(rows):
    if len({r['request_id'] for r in rows})!=len(rows):raise ValueError('unexpected request reuse')
    out=dict(tasks=len(rows),selected_arms=dict(Counter(r['arm'] for r in rows)))
    for d in ('fact','support','joint'):out[d]=[sum(r[d][i] for r in rows) for i in (0,1)]
    out.update({k:sum(r[k] for r in rows) for k in ('input_tokens','output_tokens','generation_seconds','path_cpu_ms')})
    return out


def recompute(joint_root,out):
    root,out=Path(joint_root),Path(out);out.mkdir(parents=True,exist_ok=False);hashes={}
    def read(p,lines=False):
        hashes[str(p)]=file_sha256(p)
        return jl(p) if lines else json.loads(p.read_text())
    tasks=read(root/'source-bundle-v1/TASKS.runtime.jsonl',True)
    frozen=read(root/'POLICIES_PREOUTPUT.json')
    old=read(root/'analysis-v2/JOINED_ENDPOINTS_PRIVATE.jsonl',True)
    side=read(root/'fact-review-v1/CONTEXT_SCOPE_UNCERTAINTY_PRIVATE.json')
    disputes={(r['logical_id'],r['atom_id']):r['completion_interval'] for r in side['affected_atoms']}
    by_old={r['logical_id']:r for r in old};actual={};facts={};support={};journal={}
    for n in range(1,7):
        for dest,p in ((actual,root/f'actual-v1/batch-{n:02d}/ACTUAL_RESPONSES_PRIVATE.jsonl'),
            (facts,root/f'fact-review-v1/BATCH_{n:02d}_FACT_REVIEW_PRIVATE.jsonl'),
            (support,root/f'support-review-v1/BATCH{n:02d}_SUPPORT_PRIVATE.jsonl')):
            for r in read(p,True):
                if r['logical_id'] in dest:raise ValueError('duplicate logical row')
                dest[r['logical_id']]=r
        jobs=list((root.parent/f'J{n}_run1').glob('job-*'));assert len(jobs)==1
        for p in sorted(jobs[0].glob('[0-9]*.json')):
            e=read(p)
            if e['event']=='REQUEST_RETURNED':
                if e['request_id'] in journal:raise ValueError('duplicate actual return')
                journal[e['request_id']]=e['output']
    assert len(tasks)==24 and len(actual)==len(facts)==len(support)==len(journal)==96
    labels={t['task_id']:f'J{i:02d}' for i,t in enumerate(tasks,1)}
    owners={};rows=[];private=[];by_task=defaultdict(dict)
    atom_bounds={'supported':[1,1],'partial':[0,0],'omitted':[0,0],'unsupported':[0,0],'unresolved':[0,1]}
    for t in tasks:
        for arm in ('STOP','MS','RS','MS_RS'):
            lid=next(k for k,r in actual.items() if r['task_id']==t['task_id'] and r['arm']==arm)
            a,f,s,o=actual[lid],facts[lid],support[lid],by_old[lid]
            for item in (f,s,o):
                assert all(item[k]==a[k] for k in ('logical_id','request_id','output_sha256','evalspec_sha256'))
                assert item['formal_reward'] is None
            answer=journal[a['request_id']]
            assert object_sha256(answer)==a['output_sha256'] and answer==a['output']
            assert a['technical_status']=='eos'
            atoms=[]
            for atom in f['fact_atoms']:
                assert all(q in answer['text'] for q in atom['output_quotes'])
                atoms.append(disputes.get((lid,atom['id']),atom_bounds[atom['status']]))
            fi=[min(v[i] for v in atoms) for i in (0,1)]
            verdicts=[]
            for field in ('requirements','prohibitions'):
                for v in s[field].values():
                    assert all(q in answer['text'] for q in v['output_quotes'])
                    verdicts.append(v['verdict'])
            si=[0,0] if 'fail' in verdicts else [0,1] if 'uncertain' in verdicts else [1,1]
            ji=[min(fi[i],si[i]) for i in (0,1)]
            assert (fi,si,ji)==(o['fact_interval'],o['support_interval'],o['joint_interval'])
            owners.setdefault(o['source_group'],f'G{len(owners)+1:02d}')
            r=dict(task=labels[t['task_id']],source_group=owners[o['source_group']],arm=arm,request_id=a['request_id'],
                output_sha256=a['output_sha256'],fact=fi,support=si,joint=ji,input_tokens=answer['input_tokens'],
                output_tokens=len(answer['token_ids']),generation_seconds=answer['seconds'],path_cpu_ms=o['cost']['path_cpu_ms'])
            rows.append(r);by_task[r['task']][arm]=r
            private.append(dict(**r,query=t['query'],full_original_response=answer['text']))
    shared=[k for k,a in by_task.items() if a['STOP']['joint']==a['MS']['joint']==[1,1]]
    requested=['J06','J08','J14','J16','J18']
    assert shared==requested
    selected=dict(always_STOP=[a['STOP'] for a in by_task.values()],always_MS=[a['MS'] for a in by_task.values()],
        requested_five_switch=[a['STOP' if k in requested else 'MS'] for k,a in by_task.items()])
    # First selector preserves maximal certain completion, then possible completion.
    selected['privileged_STOP_MS']=[min((a['STOP'],a['MS']),key=lambda r:(-r['joint'][0],-r['joint'][1],r['input_tokens'])) for a in by_task.values()]
    # A cheapest witness of the optimistic upper bound can sacrifice certainty.
    selected['optimistic_cheapest_upper_witness']=[min((a['STOP'],a['MS']),key=lambda r:(-r['joint'][1],r['input_tokens'])) for a in by_task.values()]
    feature_rows=[];frozen_choices={r['task_id']:r['arm'] for r in frozen['policies']['visible_query_rule']}
    for t in tasks:
        q=t['query'];rule=frozen['rule'];m=re.search(rule['memory_regex'],q,re.I)
        h=bool(re.search(rule['help_regex'],q,re.I)) and not bool(re.search(rule['no_help_regex'],q,re.I))
        original='MS_RS' if m and h else 'MS' if m else 'RS' if h else 'STOP'
        assert original==frozen_choices[t['task_id']]
        feature_rows.append(dict(task=labels[t['task_id']],old_history_word=bool(m),old_help_match=h,
            old_choice=original,**visible_features(q),candidate_choice=choose(q)))
    selected['C1_current_report_candidate']=[by_task[r['task']][r['candidate_choice']] for r in feature_rows]
    summaries={name:metrics(rs) for name,rs in selected.items()};switch_tables={}
    for name,rs in selected.items():
        changes=[];buckets=defaultdict(lambda:dict(tasks=[],input_saved=0,output_saved=0))
        for r in rs:
            ms=by_task[r['task']]['MS'];delta=interval_difference(r['joint'],ms['joint'],r['request_id']==ms['request_id'])
            if r['arm']=='MS':category='same_endpoint'
            elif r['joint']==ms['joint']==[1,1]:category='both_confirmed_success'
            elif r['joint']==ms['joint']==[0,0]:category='both_confirmed_failure'
            elif r['joint'][0]!=r['joint'][1] or ms['joint'][0]!=ms['joint'][1]:category='uncertain_selection'
            elif r['joint']==[0,0] and ms['joint']==[1,1]:category='confirmed_success_lost'
            else:category='confirmed_repair'
            change=dict(task=r['task'],source_group=r['source_group'],selected_arm=r['arm'],joint=r['joint'],MS_joint=ms['joint'],
                paired_joint_delta=delta,category=category,input_saved=ms['input_tokens']-r['input_tokens'],
                output_saved=ms['output_tokens']-r['output_tokens'],generation_seconds_saved=ms['generation_seconds']-r['generation_seconds'],
                selected_input_tokens=r['input_tokens'],selected_output_tokens=r['output_tokens'])
            changes.append(change);buckets[category]['tasks'].append(r['task'])
            for key in ('input_saved','output_saved'):buckets[category][key]+=change[key]
        summaries[name]['versus_MS']=dict(paired_joint_delta=[sum(r['paired_joint_delta'][i] for r in changes) for i in (0,1)],
            input_saved=sum(r['input_saved'] for r in changes),output_saved=sum(r['output_saved'] for r in changes),savings_categories=dict(buckets))
        switch_tables[name]=changes
    assert summaries['requested_five_switch']['joint']==[18,20] and summaries['requested_five_switch']['input_tokens']==21357
    assert summaries['requested_five_switch']['versus_MS']['input_saved']==4129
    envelope=[sum(max(a['STOP']['joint'][i],a['MS']['joint'][i]) for a in by_task.values()) for i in (0,1)]
    result=dict(protocol='posthoc-stop-ms-diagnostic-v1',base_commit='35650aa2d63a52d59e73d549a19ac64996b9314a',tasks=24,source_groups=6,
        all_96_original_observations_and_actual_outputs_reconciled=True,common_confirmed_success=shared,
        summaries=summaries,STOP_MS_privileged_quality_envelope=envelope,
        old_rule=dict(choices=dict(Counter(r['old_choice'] for r in feature_rows)),history_word_hits=sum(r['old_history_word'] for r in feature_rows),
            current_report_cue_present=sum(r['explicit_current_report'] for r in feature_rows),
            defect='Historical mention is not equivalent to missing current information; old rule has no current-sufficiency override.'),
        new_rule_status='Post-output development hypothesis only; all 24 tasks are exposed, no confirmatory qualification.',
        cost_scope='Sum actual selected call tokens/generation times and measured CPU paths; no new execution and no deployment E2E claim.',
        formal_reward=None,deployable_effect_confirmed=False,new_model_calls=0)
    write_json_once(out/'SUMMARY_PUBLIC.json',result)
    write_json_once(out/'TASKWISE_PUBLIC.json',dict(rows=rows,selection_diagnostics=switch_tables,feature_audit=feature_rows))
    write_jsonl_once(out/'FULL_READBACK_PRIVATE.jsonl',private)
    write_json_once(out/'INPUT_MANIFEST_PRIVATE.json',dict(inputs_sha256=hashes,source_files=len(hashes),model_calls=0,code_sha256=file_sha256(__file__)))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('joint-root','out'):p.add_argument('--'+name,required=True)
    print(json.dumps(recompute(**vars(p.parse_args())),indent=2))
