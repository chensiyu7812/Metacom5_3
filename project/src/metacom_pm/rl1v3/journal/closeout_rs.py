"""Read-only closeout of the four frozen complex-RS batches.

Original R1 evidence is imported unchanged. New replies receive evidence-linked
assistant development observations; no model calls or qualified rewards.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from ..io import file_sha256, object_sha256
from .rs_tasks import write_once

ARMS = {'R0','Generic','DP-RAW','DP-Method','RET-Method','F-resident'}
PLAN_SHAS = {1: '4ff17d9e71f5c6977e74c1477970b61c99d0c8d9105021b33c2009389c1cdd51', 2: 'c3f71c59595164c1f4d063d261f5b11cec58f132de553a96b03d553a3435c532', 3: 'a5fbb93eb41d9aebfaa43449f37a0569ec0c1f518b2d94ea2a7b56bf8f63685a', 4: '9437bbc23a0652d6689fe001ffadf72017d9dfd55318e4b3af28912a0cf39af9'}
PHYSICAL = {1: 16, 2: 18, 3: 17, 4: 17}


def jl(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines()]


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def validate_rows(plan, physical, logical):
    number=plan['batch_number']
    if number not in PLAN_SHAS or object_sha256(plan)!=PLAN_SHAS[number]:
        raise ValueError('original frozen complex-RS plan required')
    count=PHYSICAL[number]
    if len(physical)!=count or len(logical)!=18:
        raise ValueError('frozen batch scope required')
    by_id={r['request_id']:r for r in physical}
    if len(by_id)!=count or [r['request_id'] for r in physical]!=plan['ordered_request_ids']:
        raise ValueError('physical identities/order changed')
    groups=defaultdict(list)
    for row in logical:
        original=by_id.get(row['request_id'])
        if original is None or any(row[f]!=original[f] for f in ('payload_sha256','model_input')):
            raise ValueError('nonidentical logical reuse')
        groups[row['task_id']].append(row['arm'])
    if set(groups)!=set(plan['task_ids']) or any(len(a)!=6 or set(a)!=ARMS for a in groups.values()):
        raise ValueError('complete original three-by-six pairing required')
    if {r['request_id'] for r in logical}!=set(by_id):
        raise ValueError('unmapped physical response')


from .keycap_rs_review import validate_worker_return, validate_observation


def collect(package, job, preoutcome, output, batch_number):
    batch_number=int(batch_number)
    package,job,preoutcome,output=map(Path,(package,job,preoutcome,output))
    plan_path=package/f'batch-{batch_number:02d}/PLAN.json';plan=json.loads(plan_path.read_text())
    plan_sha=PLAN_SHAS[batch_number]
    frozen=json.loads(preoutcome.read_text())
    if frozen['new_result_files_read']!=0:
        raise ValueError('pre-output review binding required')
    for name,expected in frozen['inputs_sha256'].items():
        if file_sha256(name)!=expected:raise ValueError('pre-outcome input changed')
    for name,expected in plan['files_sha256'].items():
        if file_sha256(name)!=expected:raise ValueError('frozen plan input changed')
    physical=jl(plan['requests_path']);logical=jl(plan['logical_requests_path'])
    validate_rows(plan,physical,logical)
    paths=sorted(job.glob('[0-9]*.json'));events=[];previous=None
    for seq,path in enumerate(paths):
        e=json.loads(path.read_text())
        if e['seq']!=seq or e['previous_event_sha256']!=previous:
            raise ValueError('journal hash chain/order mismatch')
        previous=file_sha256(path);events.append(e)
    summary=json.loads((job/'SUMMARY.json').read_text())
    if summary['plan_sha256']!=plan_sha or summary['last_journal_sha256']!=previous:
        raise ValueError('journal summary identity mismatch')
    if not events or events[0]['event']!='RUN_START' or events[0]['plan_sha256']!=plan_sha:
        raise ValueError('run start identity mismatch')
    if sum(e['event']=='LOAD_START' for e in events)!=1:
        raise ValueError('single model load required')
    started=[e['request_id'] for e in events if e['event']=='REQUEST_START']
    returns=[e for e in events if e['event']=='REQUEST_RETURNED']
    validated={e['request_id']:e['finish_reason'] for e in events if e['event']=='REQUEST_VALIDATED'}
    if started!=plan['ordered_request_ids'][:len(started)] or len(started)!=len(set(started)) or len(started)!=summary['physical_calls']:
        raise ValueError('unrequested/repeated/out-of-order physical starts')
    if len({r['request_id'] for r in returns})!=len(returns) or not {r['request_id'] for r in returns}<=set(started):
        raise ValueError('duplicate or unstarted return')
    returned={r['request_id']:r['output'] for r in returns}
    by_id={r['request_id']:r for r in physical}
    for e in events:
        if e['event']=='REQUEST_START' and e['payload_sha256']!=by_id[e['request_id']]['payload_sha256']:
            raise ValueError('actual start payload differs from frozen request')
    for rid,value in returned.items():
        validate_worker_return(by_id[rid],value)
        if rid in validated and validated[rid]!=value['finish_reason']:
            raise ValueError('validated/returned finish differs')
    tasks={r['task_id']:r for r in jl(package/'TASKS.runtime.jsonl')}
    evaluations={r['task_id']:r for r in jl(package/'EVALSPEC.private.jsonl')}
    candidates=[];measurements=[]
    for row in physical:
        rid=row['request_id'];value=returned.get(rid);case='closeout-rs:'+sha_text(rid)[:20]
        status='not_started' if rid not in started else 'started_no_return'
        if value:
            status='returned_eos' if validated.get(rid)=='eos' else 'technical_'+value['finish_reason']
        candidates.append(dict(case_id=case,task_id=row['task_id'],
            question=tasks[row['task_id']]['turns'][-1]['text'],
            response=value['text'] if value else None,response_sha256=sha_text(value['text']) if value else None,
            technical_status=status,evalspec=evaluations[row['task_id']]))
        measurements.append(dict(case_id=case,request_id=rid,technical_status=status,
            input_tokens=row['input_tokens'],output_tokens=len(value['token_ids']) if value else None,
            generation_seconds=value['seconds'] if value else None,finish_reason=value['finish_reason'] if value else None,
            response_sha256=sha_text(value['text']) if value else None,
            logical_arms=[dict(task_id=r['task_id'],arm=r['arm']) for r in logical if r['request_id']==rid]))
    if output.exists():raise FileExistsError('new collection directory required')
    write_once(output/'REVIEW_INPUTS_PRIVATE.jsonl',sorted(candidates,key=lambda r:r['case_id']),lines=True)
    write_once(output/'REVIEW_KEY_PRIVATE.jsonl',measurements,lines=True)
    report=dict(protocol='pmrl1-j-closeout-rs-collection-v1',batch_number=batch_number,plan_sha256=plan_sha,
        logical_arms=18,physical_requests=len(physical),physical_started=len(started),physical_returned=len(returned),
        physical_technical_counts=dict(Counter(r['technical_status'] for r in measurements)),
        task_families=3,exact_payload_reuses=18-len(physical),job_status=summary['status'],
        total_wall_seconds=summary['wall_seconds'],
        physical_input_tokens=sum(m['input_tokens'] for m in measurements if m['response_sha256']),
        physical_output_tokens=sum(m['output_tokens'] or 0 for m in measurements),
        physical_generation_seconds=sum(m['generation_seconds'] or 0 for m in measurements),
        resource_and_response_reuse_not_independent=True,formal_reward=None,
        hashes={str(p.resolve()):file_sha256(p) for p in [plan_path,preoutcome,job/'SUMMARY.json',*paths,
            output/'REVIEW_INPUTS_PRIVATE.jsonl',output/'REVIEW_KEY_PRIVATE.jsonl']})
    write_once(output/'COLLECTION.json',report)
    return report


def finalize(package, collection, review_path, receipt_path, output, batch_number):
    batch_number=int(batch_number)
    plan_sha=PLAN_SHAS[batch_number]
    package,collection,review_path,receipt_path,output=map(Path,(package,collection,review_path,receipt_path,output))
    collection_report=json.loads((collection/'COLLECTION.json').read_text())
    for name,expected in collection_report['hashes'].items():
        if file_sha256(name)!=expected:raise ValueError('frozen collection/journal input changed')
    receipt=json.loads(receipt_path.read_text())
    if file_sha256(review_path)!=receipt['observations_sha256'] or receipt['arm_key_opened_before_freeze'] is not False:
        raise ValueError('observations not frozen before arm-key access')
    if file_sha256(collection/'REVIEW_INPUTS_PRIVATE.jsonl')!=receipt['review_input_sha256']:
        raise ValueError('review input changed')
    cases={r['case_id']:r for r in jl(collection/'REVIEW_INPUTS_PRIVATE.jsonl')}
    observations=jl(review_path)
    if len(observations)!=PHYSICAL[batch_number] or {o['case_id'] for o in observations}!=set(cases):
        raise ValueError('all frozen physical replies required')
    checked={}
    for o in observations:checked[o['case_id']]=dict(o,development_interval=validate_observation(o,cases[o['case_id']]))
    keys={r['request_id']:r for r in jl(collection/'REVIEW_KEY_PRIVATE.jsonl')}
    logical=jl(package/f'batch-{batch_number:02d}/LOGICAL_REQUESTS.private.jsonl')
    plan=json.loads((package/f'batch-{batch_number:02d}/PLAN.json').read_text());validate_rows(plan,jl(plan['requests_path']),logical)
    applicability={r['task_id']:r for r in json.loads((package/'APPLICABILITY_REVIEW.private.json').read_text())['reviews']}
    delivery={r['logical_id']:r for r in jl(package/'DELIVERY.private.jsonl')}
    results=[];seen=set()
    for row in logical:
        key=keys[row['request_id']];observation=checked[key['case_id']];case=cases[key['case_id']]
        delivered=delivery[row['logical_id']];app=applicability[row['task_id']]
        if delivered['request_id']!=row['request_id'] or delivered['input_tokens']!=key['input_tokens']:
            raise ValueError('actual/native delivery mismatch')
        layer=app['direct_coverage'] if row['arm'] in {'DP-RAW','DP-Method'} else app['ret_applicability_class'] if row['arm']=='RET-Method' else 'fixed_all_library' if row['arm']=='F-resident' else 'generic_or_no_method'
        results.append(dict(**observation,arm=row['arm'],request_id=row['request_id'],logical_id=row['logical_id'],
            response=case['response'],question=case['question'],evalspec=case['evalspec'],
            source_applicability=app,supply_stratum=layer,exact_physical_reuse=row['request_id'] in seen,
            technical_status=key['technical_status'],input_tokens=key['input_tokens'],output_tokens=key['output_tokens'],
            generation_seconds=key['generation_seconds'],resource_tokens=delivered['resource_tokens'],
            marginal_input_tokens_vs_R0=delivered['marginal_input_tokens_vs_R0'],
            formal_task_interval=[0,1],formal_reward=None))
        seen.add(row['request_id'])
    by_arm={}
    for arm in sorted(ARMS):
        group=[r for r in results if r['arm']==arm]
        by_arm[arm]=dict(logical_tasks=len(group),item_observations=dict(Counter(i['observation'] for r in group for i in r['items'])),
            development_task_intervals=dict(Counter(str(r['development_interval']) for r in group)),
            auxiliary_flags=dict(Counter(f['flag'] for r in group for f in r.get('auxiliary_flags',[]))),
            input_tokens_total=sum(r['input_tokens'] for r in group),output_tokens_total=sum(r['output_tokens'] or 0 for r in group),
            resource_tokens_total=sum(r['resource_tokens'] for r in group),
            marginal_input_tokens_vs_R0_total=sum(r['marginal_input_tokens_vs_R0'] for r in group),
            generation_seconds_total=sum(r['generation_seconds'] or 0 for r in group),
            timing_scope='Arm-accounted values; same physical output appears under DP and RET where payloads match exactly. Do not sum arm totals as actual compute.',
            formal_rewards_qualified=0)
    strata={}
    for name in ('core_applicable','partial_coverage','entry_or_stop_boundary_requires_nonapplication'):
        group=[r for r in results if r['supply_stratum']==name]
        strata[name]=dict(logical_arms=len(group),unique_physical_replies=len({r['request_id'] for r in group}),
            task_families=len({r['task_id'] for r in group}),
            item_observations=dict(Counter(i['observation'] for r in group for i in r['items'])))
    public=dict(protocol='pmrl1-j-closeout-rs-development-review-v1',batch_number=batch_number,tasks=3,logical_arms=18,physical_requests=PHYSICAL[batch_number],
        physical_generations=collection_report['physical_started'],
        exact_payload_reused_arms=18-PHYSICAL[batch_number],observations_frozen_before_arm_key=True,independently_qualified_reviewer=False,
        physical_item_observations=dict(Counter(i['observation'] for r in checked.values() for i in r['items'])),
        logical_item_observations=dict(Counter(i['observation'] for r in results for i in r['items'])),
        by_arm=by_arm,supply_strata=strata,
        actual_compute={k:collection_report[k] for k in ('physical_started','physical_returned','physical_technical_counts',
            'total_wall_seconds','physical_input_tokens','physical_output_tokens','physical_generation_seconds')},
        qualified_reward_count=0,formal_task_reward=None,formal_semantics='unqualified',
        limitations=['Three constructed, previously development-exposed task families are not an independent professional capability benchmark.',
            'DP selection is privileged evaluation-side supply, not an operational selector; a different RET method may be a legitimate alternative.',
            'RAW/Method differ by normative nonclinical adaptation and amount as well as representation; no pure compression attribution.',
            'Identical DP/RET payloads share one physical reply. Logical arm accounting is not independent replication.',
            'Direct and retrieval applicability strata have different original definitions; preserve them and report matched-task contrasts.',
            'Development text observations do not qualify their own semantic evaluator or training reward.',
            'Generation seconds exclude client/network/TTS; latency is not an efficacy score.'],
        changed_tasks=0,changed_skills=0,changed_prompts=0,new_analysis_model_calls=0,
        raw_source_response_or_gold_in_public=False,source_plan_sha256=plan_sha,
        observations_sha256=file_sha256(review_path))
    if output.exists():raise FileExistsError('new finalized evidence directory required')
    write_once(output/'PAIRED_REVIEW_PRIVATE.jsonl',results,lines=True)
    write_once(output/'SUMMARY_PUBLIC.json',public)
    text=['# Complex RS exact paired source and response evidence (private)',
        'Development observations only; no independent qualification or formal reward. Exact reused outputs are labelled.']
    for task_id in plan['task_ids']:
        group=[r for r in results if r['task_id']==task_id]
        text += ['\n## '+task_id,'\n### Visible current task\n'+group[0]['question'],
            '\n### Frozen source/EvalSpec\n```json\n'+json.dumps(group[0]['evalspec'],ensure_ascii=False,indent=2)+'\n```',
            '\n### Pre-output applicability/source review\n```json\n'+json.dumps(group[0]['source_applicability'],ensure_ascii=False,indent=2)+'\n```']
        for r in group:
            text += ['\n### '+r['arm']+'; physical reuse='+str(r['exact_physical_reuse']),
                '\n'+str(r['response']), '\n```json\n'+json.dumps({k:r[k] for k in ('items','auxiliary_flags',
                    'development_interval','formal_reward','input_tokens','resource_tokens','generation_seconds')},ensure_ascii=False,indent=2)+'\n```']
    with (output/'READABLE_COMPARISON_PRIVATE.md').open('x') as f:f.write('\n'.join(text)+'\n')
    write_once(output/'MANIFEST.json',dict(protocol=public['protocol'],
        code_sha256=file_sha256(__file__),inputs_sha256={str(p.resolve()):file_sha256(p) for p in [review_path,receipt_path,
            collection/'REVIEW_INPUTS_PRIVATE.jsonl',collection/'REVIEW_KEY_PRIVATE.jsonl',collection/'COLLECTION.json']},
        outputs_sha256={p.name:file_sha256(p) for p in output.iterdir() if p.is_file()}))
    return public


def count_group(rows):
    return dict(tasks=len(rows),technical_status_counts=dict(Counter(r['technical_status'] for r in rows)),item_observations=dict(Counter(i['observation'] for r in rows for i in r['items'])),
        task_intervals=dict(Counter(str(r['development_interval']) for r in rows)),
        input_tokens=sum(r['input_tokens'] for r in rows),output_tokens=sum(r['output_tokens'] or 0 for r in rows),
        resource_tokens=sum(r['resource_tokens'] for r in rows),
        auxiliary_flags=dict(Counter(f['flag'] for r in rows for f in r.get('auxiliary_flags',[]))))


def paired_comparison(rows,left,right):
    groups=defaultdict(dict)
    for r in rows:groups[r['task_id']][r['arm']]=r
    counts=Counter();items=Counter();reuse=0;technical_unknown_pairs=0
    for arms in groups.values():
        a,b=arms[left],arms[right];av,bv=a['development_interval'],b['development_interval']
        reuse+=a['request_id']==b['request_id']
        technical_unknown_pairs+=a.get('technical_status','returned_eos')!='returned_eos' or b.get('technical_status','returned_eos')!='returned_eos'
        result='left_better' if av[0]>bv[1] else 'right_better' if bv[0]>av[1] else 'tie' if av==bv and av[0]==av[1] else 'uncertain_overlap'
        counts[result]+=1
        ai={i['item_id']:i['observation'] for i in a['items']};bi={i['item_id']:i['observation'] for i in b['items']}
        if ai.keys()!=bi.keys():raise ValueError('matched frozen item identities required')
        items.update(x+' vs '+bi[k] for k,x in ai.items())
    return dict(left=left,right=right,paired_tasks=len(groups),task_interval_comparison=dict(counts),
        item_joint_counts=dict(items),exact_shared_physical_outputs=reuse,technical_unknown_pairs=technical_unknown_pairs,
        interpretation='Development interval comparison; unknown overlap is not a win or tie; exact copies are not replication.')


def merge(finals, output):
    finals=[Path(p) for p in finals];output=Path(output)
    if len(finals)!=4:raise ValueError('all four original batches required')
    rows=[];summaries=[];inputs={}
    for folder in finals:
        manifest=json.loads((folder/'MANIFEST.json').read_text())
        for name,h in manifest['outputs_sha256'].items():
            if file_sha256(folder/name)!=h:raise ValueError('finalized batch changed')
        rows.extend(jl(folder/'PAIRED_REVIEW_PRIVATE.jsonl'))
        summaries.append(json.loads((folder/'SUMMARY_PUBLIC.json').read_text()))
        inputs[str(folder/'MANIFEST.json')]=file_sha256(folder/'MANIFEST.json')
    if len(rows)!=72 or len({r['task_id'] for r in rows})!=12 or len({r['request_id'] for r in rows})!=68:
        raise ValueError('frozen full twelve-by-six scope required')
    tasks=defaultdict(list);physical={}
    for r in rows:
        tasks[r['task_id']].append(r)
        if r['formal_reward'] is not None or r['formal_task_interval']!=[0,1]:raise ValueError('unqualified formal reward changed')
        if r['request_id'] in physical:
            previous=physical[r['request_id']]
            if any(r[k]!=previous[k] for k in ('response_sha256','items','input_tokens','output_tokens','generation_seconds')):
                raise ValueError('shared physical outcome differs')
        physical.setdefault(r['request_id'],r)
    if any(len(g)!=6 or {r['arm'] for r in g}!=ARMS for g in tasks.values()):raise ValueError('complete six-arm pairing required')
    by_arm={arm:count_group([r for r in rows if r['arm']==arm]) for arm in sorted(ARMS)}
    strata={}
    for dimension in ('direct_coverage','ret_applicability_class'):
        values=sorted({r['source_applicability'][dimension] for r in rows})
        strata[dimension]={value:{arm:count_group([r for r in rows if r['arm']==arm and r['source_applicability'][dimension]==value]) for arm in sorted(ARMS)} for value in values}
    comparisons=[paired_comparison(rows,'DP-Method',arm) for arm in ['R0','Generic','DP-RAW','RET-Method','F-resident']]
    stratified_pairs={dimension:{value:[paired_comparison([r for r in rows if r['source_applicability'][dimension]==value],'DP-Method',arm) for arm in ['R0','Generic','RET-Method']] for value in strata[dimension]} for dimension in strata}
    counts=dict(Counter(i['observation'] for r in physical.values() for i in r['items']))
    public=dict(protocol='pmrl1-j-closeout-complex12-development-v1',task_families=12,logical_arms=72,
        physical_replies=68,exact_shared_outputs=4,physical_item_observations=counts,
        logical_item_observations=dict(Counter(i['observation'] for r in rows for i in r['items'])),
        by_arm=by_arm,paired_comparisons=comparisons,by_original_task_strata=strata,paired_comparisons_by_original_strata=stratified_pairs,
        actual_compute=dict(physical_calls=sum(s['actual_compute']['physical_started'] for s in summaries),
            technical_status_counts=dict(Counter(r['technical_status'] for r in physical.values())),
            input_tokens=sum(r['input_tokens'] for r in physical.values()),output_tokens=sum(r['output_tokens'] or 0 for r in physical.values()),
            generation_seconds=sum(r['generation_seconds'] or 0 for r in physical.values()),
            total_wall_seconds=sum(s['actual_compute']['total_wall_seconds'] for s in summaries)),
        changed_tasks=0,changed_resources=0,changed_rubrics=0,new_analysis_model_calls=0,
        formal_reward=None,qualified_reward_count=0,independent_human_review=False,
        raw_source_response_or_gold_in_public=False,
        limitations=['Assistant development observations do not qualify their evaluator or training reward.',
            'Twelve constructed, previously development-exposed task families; no independent professional-efficacy estimate.',
            'The original direct and RET applicability strata differ in definition. One identical planning supply is direct partial and RET core; do not infer a semantic advantage from that label.',
            'RAW versus Method varies normative nonclinical adaptation and token amount as well as representation.',
            'All six-arm comparisons are paired by task, but four DP/RET entries reuse one exact physical result.',
            'No significance claim or outcome-based replacement of tasks, prompts, skills, judge, or original evidence.'],
        source_final_manifests_sha256=inputs)
    if output.exists():raise FileExistsError('new merged evidence directory required')
    write_once(output/'PAIRED_REVIEW_PRIVATE.jsonl',rows,lines=True)
    write_once(output/'SUMMARY_PUBLIC.json',public)
    text=['# 原复杂十二题六臂：完整开发证据（私有）','助手逐项发展观察；不是独立真人评价，formal reward 全部 null。']
    for task_id,group in tasks.items():
        r=group[0]
        text+=['\n## '+task_id,'\n### 当前可见任务\n'+r['question'],
            '\n### 原任务要求和允许替代\n```json\n'+json.dumps(r['evalspec'],ensure_ascii=False,indent=2)+'\n```',
            '\n### 原供给适用性及来源\n```json\n'+json.dumps(r['source_applicability'],ensure_ascii=False,indent=2)+'\n```']
        for r in group:
            text+=['\n### '+r['arm']+' / physical='+r['request_id']+' / reuse='+str(r['exact_physical_reuse']),
                '\n'+r['response'],'\n```json\n'+json.dumps({k:r[k] for k in ['items','auxiliary_flags','development_interval','input_tokens','resource_tokens','output_tokens']},ensure_ascii=False,indent=2)+'\n```']
    (output/'READABLE_COMPARISON_PRIVATE.md').write_text('\n'.join(text)+'\n')
    write_once(output/'MANIFEST.json',dict(inputs_sha256=inputs,code_sha256=file_sha256(__file__),
        outputs_sha256={p.name:file_sha256(p) for p in output.iterdir()}))
    return public


def human_packet(queue, frozen, bank, out):
    """Render the existing five-item posthoc queue; never create human labels."""
    queue,frozen,bank,out=map(Path,(queue,frozen,bank,out))
    q=json.loads(queue.read_text());protocol=json.loads((frozen/'PROTOCOL_FROZEN.json').read_text())
    for path,h in protocol['inputs_sha256'].items():
        if file_sha256(path)!=h:raise ValueError('original semantic source changed')
    if len(q['rows'])!=5:raise ValueError('only the existing finite queue is allowed')
    original_inputs={r['item_id']:r for r in jl(frozen/'INPUTS_PRIVATE.jsonl')}
    original_refs={r['item_id']:r for r in jl(frozen/'REFERENCES_PRIVATE.jsonl')}
    supplemental=json.loads(bank.read_text())['supplements']
    questions={
        'official_primary_behavior_disagreement':[
            '依据给出的整段治疗师话语，其主要行为更符合提问、反映，还是混合/不确定？请定位区分两者的原文。',
            '“提及来访者先前的话”是否足以支持“主要在反映”的假设，还是这段话实际要求来访者提供或确认新信息？',
            '保留官方行为标签，或记录具体可复核的歧义；本项不裁决帮助性、适用性或总体回复质量。'],
        'underdetermined_fact_overconfident_decision':[
            '现有材料只说明预订与期望，还是足以证明后来实际参加了活动？',
            '报告日期与假设事件日期不同，是否构成事件否定，还是后来是否发生仍未知？',
            '请分别记录支持、矛盾、未知，并说明本地片段的证据范围；不要把没有提及当作事件未发生。'],
        'known_unsupported_stage_not_detected_as_contradiction':[
            '原真人补充拒绝将某次沟通预设为已完成；这应被记为任务层面的未支持/失败，还是严格逻辑矛盾？',
            '当前母亲/规则语境与历史父母/旅行语境能否支持假设所指的同一事件？请定位证据并保留不确定性。',
            '若模型给unknown，是否正确保留逻辑不确定性但未识别任务层面的不当预设？两种判据应分别记录，不能据此改写原64参考或96资格结论。']}
    rows=[]
    for source in q['rows']:
        item=source['input'];iid=item['item_id']
        if item!=original_inputs[iid] or source['reference']!=original_refs[iid]:raise ValueError('queue differs from frozen source/reference')
        row=dict(source,pending_questions=questions[source['reason']],human_decision=None,human_reviewer=None,
            adjudication_status='pending_real_human',assistant_role='Material preparation only; not an independent human rating.')
        if source['reference']['evidence'].get('record_id'):
            row['original_human_supplements']=[r for r in supplemental if r['record_id']==source['reference']['evidence']['record_id']]
        rows.append(row)
    if out.exists():raise FileExistsError('new human-readable packet required')
    write_once(out/'ITEMS_PRIVATE.jsonl',rows,lines=True)
    text=['# 五项既有错误/歧义复核（私有，待真人）',
        '这是预测后的有限错误复核，不是新资格测试。原64项、96项、阈值和标签不改。助手仅整理材料；没有新增真人评价。',
        '概率顺序为 contradiction / entailment / neutral；pass/fail 为冻结阈值输出，不等同于质量判断。']
    for n,row in enumerate(rows,1):
        text+=['\n## '+str(n)+' · '+row['input']['item_id'],
            '\n来源组：'+row['input']['source_group']+'；层：'+row['input']['stratum'],
            '\n### 现有来源证据\n'+row['input']['premise'],
            '\n### 待判假设\n'+row['input']['hypothesis'],
            '\n### 原参考及其人评/构造来源\n```json\n'+json.dumps(row['reference'],ensure_ascii=False,indent=2)+'\n```']
        if row.get('original_human_supplements'):
            text+=['\n### 原真人补充（完整保留，不是新增评价）\n```json\n'+json.dumps(row['original_human_supplements'],ensure_ascii=False,indent=2)+'\n```']
        text+=['\n### 已有模型输出\n```json\n'+json.dumps(row['prediction'],ensure_ascii=False,indent=2)+'\n```',
            '\n### 具体待裁决问题\n'+'\n'.join('- '+x for x in row['pending_questions']),
            '\n真人结论：**pending**；评审人：空；证据/理由：空。']
    (out/'READABLE_REVIEW_ZH_PRIVATE.md').write_text('\n'.join(text)+'\n')
    public=dict(protocol='pmrl1-j-existing-five-posthoc-review-packet-v1',items=5,
        reasons=dict(Counter(r['reason'] for r in rows)),new_human_judgments=0,pending_real_human=5,
        original_64_modified=False,original_96_modified=False,new_qualification_test=False,
        new_model_calls=0,reference_replacements=0,post_prediction_selection=True,
        qualification_or_reward_claim=False,source_queue_sha256=file_sha256(queue))
    write_once(out/'SUMMARY_PUBLIC.json',public)
    write_once(out/'MANIFEST.json',dict(code_sha256=file_sha256(__file__),
        inputs_sha256={str(p):file_sha256(p) for p in [queue,bank,frozen/'PROTOCOL_FROZEN.json',frozen/'INPUTS_PRIVATE.jsonl',frozen/'REFERENCES_PRIVATE.jsonl']},
        outputs_sha256={p.name:file_sha256(p) for p in out.iterdir()}))
    return public


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();subs=parser.add_subparsers(dest='command',required=True)
    c=subs.add_parser('collect')
    for name in ('package','job','preoutcome','output','batch-number'):c.add_argument('--'+name,required=True)
    f=subs.add_parser('finalize')
    for name in ('package','collection','review-path','receipt-path','output','batch-number'):f.add_argument('--'+name,required=True)
    m=subs.add_parser('merge');m.add_argument('--finals',nargs=4,required=True);m.add_argument('--output',required=True)
    h=subs.add_parser('human-packet')
    for name in ('queue','frozen','bank','out'):h.add_argument('--'+name,required=True)
    args=vars(parser.parse_args());command=args.pop('command')
    print(json.dumps({'collect':collect,'finalize':finalize,'merge':merge,'human-packet':human_packet}[command](**args),ensure_ascii=False,indent=2))
