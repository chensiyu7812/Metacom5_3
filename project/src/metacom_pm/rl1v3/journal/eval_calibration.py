"""Finite, source-bound calibration; mechanical checks are not support rewards.

Inputs/references are frozen separately. Existing classifier and historical
judge predictions are diagnostics, without new fitting, inference or labels.
"""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def order(value):return hashlib.sha256(('journal-calibration96-v1|'+value).encode()).hexdigest()
def jl(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]
def write(path,value,lines=False):
    with Path(path).open('x') as f:
        if lines:
            for row in value:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
        else:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')


def benefit(verdict,on_arm):
    if verdict not in {'A_better','B_better','equivalent'}:return 'unknown'
    return 'pass' if verdict==on_arm+'_better' else 'fail'


def completion_reference(observed):
    mapping={'complete':'pass','missing':'fail','abstained':'fail',
        'not_mentioned':'fail','absent':'fail','underspecified':'unknown',
        'partial':'unknown','uncertain':'unknown'}
    if observed not in mapping:raise ValueError('unrecognized atomic observation: '+observed)
    return mapping[observed]


def build(old,evidence,assets,design,manual,out):
    old,evidence,assets,design,manual,out=map(Path,(old,evidence,assets,design,manual,out))
    out.mkdir(parents=True,exist_ok=False)
    hashes={};items=[];refs=[]
    def read(path,lines=False):
        hashes[str(path)]=sha(path)
        return jl(path) if lines else json.loads(path.read_text())
    config=read(design);decisions=read(manual)
    audit=read(evidence/'memory_audit/v2/ATOMS_PRIVATE.jsonl',True)
    by_task={x['task_id']:x for x in audit}
    memory=read(evidence/'memory_outcomes-v1/JOINED_REVIEW_PRIVATE.json')
    rs=read(evidence/'rs/smoke_review-v1/PAIRED_REVIEW.private.jsonl',True)
    rs_specs={x['task_id']:x for x in read(old/'rs/candidates-v1/evalspec.private.jsonl',True)}
    raw=read(assets/'project/data/external/evo_emo.json')
    sessions={(u['id'],s['id']):s for u in raw for s in u['dialog_history']}
    def group(row):return 'memory-owner-family:'+('p13+p18' if row['owner_id'] in ('p13','p18') else row['owner_id'])
    def add(category,key,payload,reference,provenance,source_group,reference_details=None):
        iid=order(category+'|'+key)[:24]
        items.append(dict(item_id=iid,category=category,payload=payload,source_group=source_group))
        refs.append(dict(item_id=iid,reference=reference,provenance=provenance,details=reference_details))
    status={'documented_atoms_covered':'pass','evidence_insufficient':'fail'}
    for row in audit:
        atoms=[x for x in row['atoms'] if x['required']]
        add('source_coverage',row['task_id'],dict(task_id=row['task_id'],scope='official_EndHistoryQA',
            delivered_sessions=row['original_dp_sessions'],requirements=[dict(groups=x['sufficient_source_groups'],
                reference_state=x['status_end_history']) for x in atoms]),
            status.get(row['dp_evidence_end_history'],'unknown'),'frozen_source_audit_mechanical_delivery',group(row))
    candidates=[(row,arm) for row in audit if row['explicit_time']['upper'] for arm in ['dp','ret']]
    for row,arm in sorted(candidates,key=lambda x:order(x[0]['task_id']+'|'+x[1]))[:12]:
        time=row['explicit_time'];sid=row['original_'+arm+'_sessions']
        ref='unknown' if time['kind']=='explicit_month_interval' else ('fail' if row[arm+'_future_sessions_strict'] else 'pass')
        add('temporal_legality',row['task_id']+arm,dict(task_id=row['task_id'],arm=arm,
            scope='independent_strict_time_diagnostic_not_EndHistory_leakage',cutoff=time,
            sources=[dict(session_id=s,date=sessions[(row['owner_id'],s)]['timestamp']) for s in sid]),
            ref,'frozen_date_metadata_comparison',group(row))
    for row in memory:
        atom=next(x for x in row['atoms'] if x['necessary'])
        source=by_task[row['task_id']];target=next(x for x in source['atoms'] if x['atom_id']==atom['atom_id'])
        ref=completion_reference(atom['observed'])
        # Explicit unanswered observations are preserved, without interpreting unknown evidence as failure.
        if row['official_gold_development']=='observed_unanswered':ref='fail'
        add('atomic_completion',row['case_id'],dict(response=row['response'],target=target['claim'],
            question=row['question'],source_quotes=[x['exact_quote'] for x in target['source_evidence']],
            response_sha256=row['response_sha256']),ref,'same_model_assistant_development_not_independent',group(source),atom)
    bankroot=assets/'project/outputs/pm_rl1/human_reference_reuse_20261102_v2'
    bank=read(bankroot/'REFERENCE_BANK_PRIVATE.json')
    historical=assets/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/relation_reference_preparation_20261021_v1.draft03'
    for row in bank['singles']:
        key=row['old_item_key'];source=read(historical/'sources'/f'{key}.json')
        reply_path=historical/'replies'/f'{key}.txt';hashes[str(reply_path)]=sha(reply_path)
        decision=decisions['subject_stage'][row['record_id']]
        add('subject_or_stage',row['record_id'],dict(source=source,response=reply_path.read_text(),
            predicate='Personal-claim subject and action/event stage are source-consistent.'),
            decision['reference'],'historical_human_with_explicit_followup_uncertainty',
            'historical-evidence:'+row['evidence_identity'],dict(record=row,decision=decision))
    for row in rs:
        key=row['case_id'];source_group='annomi-video:'+rs_specs[row['task_id']]['source_family_ids'][0]
        decision=decisions['behavior'][key]
        add('behavior_recognition',key,dict(response=row['response'],predicate='main response behavior is reflection',
            response_sha256=row['response_sha256']),decision['reference'],
            'same_model_assistant_development_not_independent',source_group,decision)
        add('behavior_applicability',key,dict(response=row['response'],
            requirements=rs_specs[row['task_id']]['requirements'],
            source=rs_specs[row['task_id']]['source_locator'],
            predicate='Response behavior is appropriate to this visible user request.'),
            'unknown','no_independently_qualified_current_semantic_reference',source_group,
            dict(development_observation=row['applicable_to_visible_request_development_observation'],formal='uncertain'))
    hist=assets/'project/outputs/paper1_pairwise_teacher'
    csv_path=hist/'local_comparison_20260917_v2/base80_reference_and_judges.csv';hashes[str(csv_path)]=sha(csv_path)
    old_rows=list(csv.DictReader(csv_path.open(encoding='utf-8-sig')))
    aligned={x['presentation_id']:x for x in read(hist/'gemini_qualification_v2/aligned_results.json')}
    requests={x['presentation_id']:x for x in read(hist/'local_comparison_20260917_v2/qwen35_9b/requests.json')}
    manifest=read(hist/'local_comparison_20260917_v2/qwen35_9b/manifest.json')
    for task in ['DG','ESC']:
        for row in sorted([x for x in old_rows if x['task']==task],key=lambda x:order(x['base_pair_id']))[:7]:
            pid=row['presentation_id'];original=aligned[pid]
            assert not original['reverse_duplicate'] and original['original_A']==row['original_A']
            on_arm=row['A_arm'];on_arm='A' if on_arm=='ON' else 'B'
            add('natural_support_quality',row['base_pair_id'],dict(task=task,request=requests[pid],
                cached_judge_verdict=row['qwen35_9b_verdict'],on_arm=on_arm,
                cached_judge_identity=manifest['identity_sha256']),benefit(row['original_A'],on_arm),
                'historical_joint_human_as_submitted_not_new_task_qualification',
                'historical-'+task+':'+str(original['cluster_id']),
                dict(original_A=row['original_A'],human_followup=row['human_followup'],
                    assistant_sensitivity=row['assistant_fact_sensitivity'],source_presentation=pid))
    assert dict(Counter(x['category'] for x in items))==config['counts']
    assert len(items)==96 and len({x['item_id'] for x in items})==96
    write(out/'ITEMS_PRIVATE.jsonl',items,True);write(out/'REFERENCES_PRIVATE.jsonl',refs,True)
    freeze=dict(protocol=config['protocol'],items=96,counts=config['counts'],inputs_sha256=hashes,
        output_sha256={n:sha(out/n) for n in ['ITEMS_PRIVATE.jsonl','REFERENCES_PRIVATE.jsonl']},
        source_groups=len({x['source_group'] for x in items}),new_model_calls=0,reward_qualified=False)
    write(out/'FREEZE_MANIFEST.json',freeze)
    return freeze


def program(payload,category):
    if category=='source_coverage':
        req=payload['requirements'];delivered=set(payload['delivered_sessions'])
        if any(r['reference_state'] not in {'supported','calendar_derived'} for r in req):return 'unknown'
        return 'pass' if all(any(all(s.rsplit(':',1)[0] in delivered for s in g) for g in r['groups']) for r in req) else 'fail'
    if category=='temporal_legality':
        t=payload['cutoff']
        if t['lower']!=t['upper'] or any(not s['date'] for s in payload['sources']):return 'unknown'
        return 'pass' if all(s['date']<=t['upper'] for s in payload['sources']) else 'fail'
    if category=='atomic_completion':
        text=payload['response'].casefold().strip().rstrip('.')
        if payload['target'].casefold().strip().rstrip('.')==text:return 'pass'
        if text=='unknown':return 'fail'
        return 'unknown'
    return 'unknown'


def metrics(rows):
    known=[r for r in rows if r['reference']!='unknown'];neg=[r for r in known if r['reference']=='fail'];pos=[r for r in known if r['reference']=='pass']
    fp=sum(r['prediction']=='pass' for r in neg);fn=sum(r['prediction']=='fail' for r in pos)
    return dict(items=len(rows),reference_known=len(known),reference_unknown=len(rows)-len(known),
        decided=sum(r['prediction']!='unknown' for r in rows),unknown=sum(r['prediction']=='unknown' for r in rows),
        unknown_rate=sum(r['prediction']=='unknown' for r in rows)/len(rows),
        false_pass=fp,false_fail=fn,negative_reference_denominator=len(neg),positive_reference_denominator=len(pos),
        false_pass_rate=fp/len(neg) if neg else None,false_fail_rate=fn/len(pos) if pos else None,
        unsupported_pass_on_unknown=sum(r['reference']=='unknown' and r['prediction']=='pass' for r in rows),
        unknown_on_known_reference=sum(r['reference']!='unknown' and r['prediction']=='unknown' for r in rows))


def score(frozen,classifier,out):
    import joblib
    frozen,out=Path(frozen),Path(out);out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((frozen/'FREEZE_MANIFEST.json').read_text())
    for name,expected in manifest['output_sha256'].items():
        if sha(frozen/name)!=expected:raise ValueError('calibration input changed')
    items=jl(frozen/'ITEMS_PRIVATE.jsonl');reference={x['item_id']:x for x in jl(frozen/'REFERENCES_PRIVATE.jsonl')}
    model=joblib.load(classifier);predictions=[]
    for row in items:
        cat=row['category'];p=row['payload'];detail={};method='conservative_program'
        result=program(p,cat)
        if cat=='behavior_recognition':
            probabilities=model.predict_proba([p['response']])[0];i=int(probabilities.argmax())
            label=str(model.classes_[i]);confidence=float(probabilities[i]);method='existing_TFIDF_auxiliary_threshold_0.5'
            result='unknown' if confidence<.5 else ('pass' if label=='reflection' else 'fail')
            detail=dict(label=label,confidence=confidence)
        elif cat=='natural_support_quality':
            result=benefit(p['cached_judge_verdict'],p['on_arm']);method='cached_historical_Qwen35_9B'
        naive='pass'
        if cat=='atomic_completion':
            words=set(re.findall(r'\w+',p['target'].casefold()))
            naive='pass' if len(words&set(re.findall(r'\w+',p['response'].casefold())))/max(1,len(words))>=.25 else 'fail'
        for candidate,prediction in [(method,result),('declared_naive_baseline_not_reward',naive)]:
            predictions.append(dict(item_id=row['item_id'],category=cat,source_group=row['source_group'],
                method=candidate,prediction=prediction,diagnostic=detail if candidate==method else {}))
    # No reference verdict participates in predictor calls above.
    write(out/'PREDICTIONS_BEFORE_REFERENCE_JOIN_PRIVATE.jsonl',predictions,True)
    joined=[dict(**r,reference=reference[r['item_id']]['reference'],
        reference_provenance=reference[r['item_id']]['provenance']) for r in predictions]
    write(out/'CALIBRATION_RESULTS_PRIVATE.jsonl',joined,True)
    groups=defaultdict(list)
    for row in joined:groups[(row['category'],row['method'])].append(row)
    report=dict(protocol=manifest['protocol'],calibration_items=96,physical_new_judge_calls=0,
        new_classifier_training=0,category_method_results=[dict(category=c,method=m,**metrics(v)) for (c,m),v in groups.items()],
        reference_provenance_counts=dict(Counter(x['provenance'] for x in reference.values())),
        source_groups=manifest['source_groups'],reward_qualified=False,
        limitations=['Mechanical delivery/date checks validate declared conditions, not semantic evidence entailment.',
            'Current behavior/atomic references are exposed assistant development observations, not independent human gold.',
            'Historical joint-human references and cached Qwen predictions retain original identities; no transfer qualification to new Generator/tasks.',
            'Natural-quality predicate is historical ON materially better; ties count nonpositive, uncertain remains unknown.',
            'False-pass/fail exclude unknown references; zero denominators are null. No unknown converted to a negative.',
            'Repeated-source groups must not be treated as 96 independent observations.'],
        bindings=dict(freeze_sha256=sha(frozen/'FREEZE_MANIFEST.json'),classifier_sha256=sha(classifier),
            predictor_code_sha256=sha(__file__),
            predictions_sha256=sha(out/'PREDICTIONS_BEFORE_REFERENCE_JOIN_PRIVATE.jsonl')))
    source_groups=defaultdict(list)
    for row in joined:source_groups[(row['source_group'],row['category'],row['method'])].append(row)
    write(out/'SOURCE_GROUP_RESULTS_PRIVATE.json',[dict(source_group=g,category=c,method=m,**metrics(v)) for (g,c,m),v in source_groups.items()])
    write(out/'PUBLIC_AGGREGATE.json',report)
    table=['# 96项原子评价校准（私有）\n','输入、参考和预测文件分别冻结；unknown不填零。\n',
        '| item | category | source group | reference | prediction | method |','|---|---|---|---|---|---|']
    table += ['| '+' | '.join(str(r[k]) for k in ['item_id','category','source_group','reference','prediction','method'])+' |' for r in joined]
    (out/'CALIBRATION96_PRIVATE.md').write_text('\n'.join(table)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build')
    for name in ['old','evidence','assets','design','manual','out']:b.add_argument('--'+name,required=True)
    s=sub.add_parser('score')
    for name in ['frozen','classifier','out']:s.add_argument('--'+name,required=True)
    args=vars(p.parse_args());command=args.pop('command')
    print(json.dumps((build if command=='build' else score)(**args),ensure_ascii=False,indent=2))
