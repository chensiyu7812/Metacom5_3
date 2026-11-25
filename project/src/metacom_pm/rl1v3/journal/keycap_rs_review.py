"""Evidence-only analysis of the already frozen R1 complex RS experiment.

No model calls, altered tasks, graders or rewards. Journals are validated before
the sixteen physical replies are projected into an arm-masked review. Frozen
observations expand to eighteen logical arms only through exact payload reuse.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from ..io import file_sha256, object_sha256
from .rs_tasks import write_once

ARMS = {'R0','Generic','DP-RAW','DP-Method','RET-Method','F-resident'}
R1_PLAN_SHA = '4ff17d9e71f5c6977e74c1477970b61c99d0c8d9105021b33c2009389c1cdd51'


def jl(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines()]


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def validate_rows(plan, physical, logical):
    if len(physical)!=16 or len(logical)!=18 or object_sha256(plan)!=R1_PLAN_SHA:
        raise ValueError('original R1 scope/identity required')
    by_id={r['request_id']:r for r in physical}
    if len(by_id)!=16 or [r['request_id'] for r in physical]!=plan['ordered_request_ids']:
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


def validate_worker_return(row, value):
    decode=row['model_input']['decode'];ids=value['token_ids'];eos=decode['eos_token_id']
    eos=[eos] if isinstance(eos,int) else eos
    if not ids or any(type(t) is not int or t<0 for t in ids) or len(ids)>decode['max_new_tokens']:
        raise ValueError('invalid returned token sequence')
    if any(t in eos for t in ids[:-1]):raise ValueError('returned tokens after EOS')
    reason='eos' if ids[-1] in eos else 'length' if len(ids)==decode['max_new_tokens'] else 'invalid'
    if reason=='invalid' or value['finish_reason']!=reason:
        raise ValueError('returned finish reason/token mismatch')
    if value['input_tokens']!=row['input_tokens'] or not isinstance(value['text'],str) or not value['text'].strip():
        raise ValueError('response/input token mismatch')
    if type(value['seconds']) not in (int,float) or not math.isfinite(value['seconds']) or value['seconds']<0:
        raise ValueError('invalid generation timing')


def collect(package, job, preoutcome, output):
    package,job,preoutcome,output=map(Path,(package,job,preoutcome,output))
    plan_path=package/'batch-01/PLAN.json';plan=json.loads(plan_path.read_text())
    frozen=json.loads(preoutcome.read_text())
    if frozen['fixed_plan_object_sha256']!=R1_PLAN_SHA or frozen['new_result_files_read']!=0:
        raise ValueError('pre-output review binding required')
    for name,expected in frozen['inputs_sha256'].items():
        if file_sha256(name)!=expected:raise ValueError('pre-outcome input changed')
    physical=jl(plan['requests_path']);logical=jl(plan['logical_requests_path'])
    validate_rows(plan,physical,logical)
    paths=sorted(job.glob('[0-9]*.json'));events=[];previous=None
    for seq,path in enumerate(paths):
        e=json.loads(path.read_text())
        if e['seq']!=seq or e['previous_event_sha256']!=previous:
            raise ValueError('journal hash chain/order mismatch')
        previous=file_sha256(path);events.append(e)
    summary=json.loads((job/'SUMMARY.json').read_text())
    if summary['plan_sha256']!=R1_PLAN_SHA or summary['last_journal_sha256']!=previous:
        raise ValueError('journal summary identity mismatch')
    if not events or events[0]['event']!='RUN_START' or events[0]['plan_sha256']!=R1_PLAN_SHA:
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
        rid=row['request_id'];value=returned.get(rid);case='kr1:'+sha_text(rid)[:20]
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
    report=dict(protocol='pmrl1-j-keycap-r1-collection-v1',plan_sha256=R1_PLAN_SHA,
        logical_arms=18,physical_requests=16,physical_started=len(started),physical_returned=len(returned),
        physical_technical_counts=dict(Counter(r['technical_status'] for r in measurements)),
        task_families=3,exact_payload_reuses=2,job_status=summary['status'],
        total_wall_seconds=summary['wall_seconds'],
        physical_input_tokens=sum(m['input_tokens'] for m in measurements if m['response_sha256']),
        physical_output_tokens=sum(m['output_tokens'] or 0 for m in measurements),
        physical_generation_seconds=sum(m['generation_seconds'] or 0 for m in measurements),
        resource_and_response_reuse_not_independent=True,formal_reward=None,
        hashes={str(p.resolve()):file_sha256(p) for p in [plan_path,preoutcome,job/'SUMMARY.json',*paths,
            output/'REVIEW_INPUTS_PRIVATE.jsonl',output/'REVIEW_KEY_PRIVATE.jsonl']})
    write_once(output/'COLLECTION.json',report)
    return report


def validate_observation(observation, case):
    if observation['case_id']!=case['case_id'] or observation['task_id']!=case['task_id'] or observation['response_sha256']!=case['response_sha256']:
        raise ValueError('observation identity differs')
    spec=case['evalspec'];expected={i['id']:i['criterion'] for i in spec['requirements']+spec['prohibitions']}
    if len(observation['items'])!=len(expected) or {i['item_id']:i['criterion'] for i in observation['items']}!=expected:
        raise ValueError('frozen criteria changed')
    response=case['response'] or ''
    for item in observation['items']:
        if item['observation'] not in {'pass','fail','uncertain'} or item['formal_verdict']!='uncertain':
            raise ValueError('invalid observation or self-qualified verdict')
        if not (0<=item['start_char']<=item['end_char']<=len(response)) or (response and item['start_char']==item['end_char']):
            raise ValueError('invalid response evidence offsets')
        if item['evidence_quote']!=response[item['start_char']:item['end_char']] or not item['reason']:
            raise ValueError('missing/false response evidence')
        if case['technical_status']!='returned_eos' and item['observation']!='uncertain':
            raise ValueError('technical failure cannot become semantic success/failure')
    for flag in observation.get('auxiliary_flags',[]):
        if not (0<=flag['start_char']<flag['end_char']<=len(response)) or flag['quote']!=response[flag['start_char']:flag['end_char']] or flag['part_of_frozen_rubric'] is not False:
            raise ValueError('false auxiliary evidence or new criterion')
    if observation['qualified_reward'] is not None:
        raise ValueError('unqualified review cannot create reward')
    values={i['observation'] for i in observation['items']}
    return [0,0] if 'fail' in values else [1,1] if values=={'pass'} else [0,1]


def finalize(package, collection, review_path, receipt_path, output):
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
    if len(observations)!=16 or {o['case_id'] for o in observations}!=set(cases):
        raise ValueError('all sixteen physical replies required')
    checked={}
    for o in observations:checked[o['case_id']]=dict(o,development_interval=validate_observation(o,cases[o['case_id']]))
    keys={r['request_id']:r for r in jl(collection/'REVIEW_KEY_PRIVATE.jsonl')}
    logical=jl(package/'batch-01/LOGICAL_REQUESTS.private.jsonl')
    plan=json.loads((package/'batch-01/PLAN.json').read_text());validate_rows(plan,jl(plan['requests_path']),logical)
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
            timing_scope='Arm-accounted values; same physical output appears under DP and RET for two tasks. Do not sum arm totals as actual compute.',
            formal_rewards_qualified=0)
    strata={}
    for name in ('core_applicable','partial_coverage','entry_or_stop_boundary_requires_nonapplication'):
        group=[r for r in results if r['supply_stratum']==name]
        strata[name]=dict(logical_arms=len(group),unique_physical_replies=len({r['request_id'] for r in group}),
            task_families=len({r['task_id'] for r in group}),
            item_observations=dict(Counter(i['observation'] for r in group for i in r['items'])))
    public=dict(protocol='pmrl1-j-keycap-r1-development-review-v1',tasks=3,logical_arms=18,physical_requests=16,
        physical_generations=collection_report['physical_started'],
        exact_payload_reused_arms=2,observations_frozen_before_arm_key=True,independently_qualified_reviewer=False,
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
            'Entry/stop-boundary and direct partial-coverage tasks are absent from R1; no findings for those strata.',
            'Development text observations do not qualify their own semantic evaluator or training reward.',
            'Generation seconds exclude client/network/TTS; latency is not an efficacy score.'],
        changed_tasks=0,changed_skills=0,changed_prompts=0,new_analysis_model_calls=0,
        raw_source_response_or_gold_in_public=False,source_plan_sha256=R1_PLAN_SHA,
        observations_sha256=file_sha256(review_path))
    if output.exists():raise FileExistsError('new finalized evidence directory required')
    write_once(output/'PAIRED_REVIEW_PRIVATE.jsonl',results,lines=True)
    write_once(output/'SUMMARY_PUBLIC.json',public)
    text=['# R1 exact paired source and response evidence (private)',
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


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();subs=p.add_subparsers(dest='command',required=True)
    c=subs.add_parser('collect')
    for name in ('package','job','preoutcome','output'):c.add_argument('--'+name,required=True)
    f=subs.add_parser('finalize')
    for name in ('package','collection','review-path','receipt-path','output'):f.add_argument('--'+name,required=True)
    args=vars(p.parse_args());command=args.pop('command')
    print(json.dumps((collect if command=='collect' else finalize)(**args),ensure_ascii=False,indent=2))
