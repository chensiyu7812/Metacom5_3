#!/usr/bin/env python3
"""Prepare two exact restored states and four terminal-only requests on CPU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--original-plan',required=True)
    p.add_argument('--exact',required=True);p.add_argument('--events',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();os.environ['CUDA_VISIBLE_DEVICES']=''
    repo=Path(__file__).resolve().parents[3];out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    old=json.loads(Path(a.original_plan).read_text());executor=out/'executor'
    shutil.copytree(old['executor_root'],executor,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    additions=['project/src/metacom_pm/rl1v3/journal/pomdp_midstate_counterfactual.py',
        'project/scripts/rl1v3/journal_prepare_pomdp_midstate.py','project/scripts/rl1v3/journal_run_pomdp_midstate.py']
    for rel in additions:
        (executor/rel).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/rel,executor/rel)
    sys.path.insert(0,str(executor/'project/src'))
    from metacom_pm.rl1v3.journal import pomdp_midstate_counterfactual as M
    from metacom_pm.rl1v3.io import object_sha256,file_sha256
    from metacom_pm.rl1v3.journal.pomdp_latency import MonotonicClock
    exact=[s for s in M.read(a.exact) if 'task_id' in s]
    if [s['batch'] for s in exact]!=['DR1','DR2']:raise ValueError('only original preselected states')
    events=M.rows(a.events);states=[]
    for s in exact:
        prefix=[e for e in events if e['event']=='TOOL_RETURNED' and e.get('task_id')==s['task_id']
            and e.get('method')=='LLMToolAgent' and e['seq']<=s['event_seq']]
        if not prefix or prefix[-1]['observation_sha256']!=s['observation_sha256']:raise ValueError('old observation trace binding')
        states.append(dict(task_id=s['task_id'],original_batch=s['batch'],original_event_seq=s['event_seq'],
            replay_actions=[e['action'] for e in prefix],observation=prefix[-1]['observation'],
            observation_sha256=s['observation_sha256'],state_sha256=s['state_sha256'],payload_sha256=s['payload_sha256']))
    taskids=[s['task_id'] for s in states]
    plan={k:old[k] for k in ('baseline_path','baseline_sha256','checkpoint_path','source_config_path',
        'task_manifest_path','envelopes_path','cpu_pools_path','review_path','model_path','python','gpu_uuid',
        'constraint_runtime_files_sha256','vendor_files_sha256')}
    plan.update(protocol=M.PROTOCOL,job_kind=M.JOB_KIND,base_commit=M.BASE_COMMIT,authorized=False,
        max_calls=4,max_model_loads=1,warmup_calls=0,controller_calls=0,global_seconds=1200,load_seconds=600,
        request_seconds=300,automatic_retry=False,automatic_followup=False,task_ids=taskids,
        executor_root=str(executor),vendor_path=str(executor/Path(old['vendor_path']).relative_to(old['executor_root'])),
        cache_policy='disabled_new_physical_terminal_each_branch',formal_reward=None,
        restoration_semantics='complete original prefix replay; compare state + complete observation + snapshot + payload',
        timing_semantics='fresh post-restore decision stamp to validated terminal; restore/model load separate; no old latency reuse',
        branch_order=[{'task_alias':alias,'branch':b} for alias in ('T01','T03') for b in M.BRANCHES],
        original_plan_path=str(Path(a.original_plan).resolve()),original_exact_path=str(Path(a.exact).resolve()))
    clock=MonotonicClock();started=clock.stamp();factory,tasks=M.make_factory(plan,out/'cpu-ledgers')
    requests,diagnostics,frozen=M.request_rows(tasks,states,factory,clock,clock.now_ns()+600*10**9)
    def write(name,value,jsonl=False):
        path=out/name
        path.write_text((''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in value) if jsonl
            else json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n'))
        return str(path)
    plan['requests_path']=write('REQUESTS_PRIVATE.jsonl',requests,True)
    plan['states_path']=write('RESTORED_STATES_PRIVATE.jsonl',frozen,True)
    diagnostic_path=write('EXPAND_CANDIDATES_PRIVATE.jsonl',diagnostics,True)
    plan['ordered_request_ids']=[r['frozen_request_id'] for r in requests]
    plan['task_sha256']={t['task_id']:object_sha256(t) for t in tasks}
    plan['files_sha256']=dict(old['files_sha256'])
    for name in (plan['requests_path'],plan['states_path'],diagnostic_path,a.exact,a.events,a.original_plan):
        plan['files_sha256'][str(Path(name).resolve())]=file_sha256(name)
    plan['executor_files_sha256']={rel:file_sha256(executor/rel) for rel in old['executor_files_sha256']}
    plan['executor_files_sha256'].update({rel:file_sha256(executor/rel) for rel in additions})
    plan['executor_inventory_sha256']=object_sha256(plan['executor_files_sha256'])
    plan['scope_sha256']=object_sha256(dict(protocol=M.PROTOCOL,task_ids=taskids,
        ordered_request_ids=plan['ordered_request_ids'],requests_sha256=file_sha256(plan['requests_path']),
        states_sha256=file_sha256(plan['states_path']),global_seconds=1200,max_calls=4))
    plan_path=write('PLAN.json',plan)
    M.check(plan_path)
    # Exercise the full new restore/branch/payload/request loop without a model.
    class CPUFixture:
        kind='cpu_transport_fixture_not_model'
        def __init__(self):self.calls=0
        def generate(self,request,seconds):
            self.calls+=1
            return dict(text='Synthetic CPU transport check; not a model answer.',
                token_ids=[17,request['payload']['decode']['eos_token_id'][0]],finish_reason='eos',seconds=0,
                input_tokens=len(request['payload']['input_ids']),request_sha256=object_sha256(request))
    fixture=CPUFixture();fixture_events=[]
    fixture_result=M.execute(plan=plan,requests=requests,states=frozen,tasks=tasks,factory=factory,
        backend=fixture,emit=lambda event,**fields:fixture_events.append(dict(event=event,**fields)),
        clock=clock,deadline_ns=clock.now_ns()+600*10**9,guard=lambda:None)
    if fixture.calls!=4 or fixture_result['actual_model_calls']!=0:raise ValueError('CPU fixture identity')
    write('CPU_RUNTIME_FIXTURE_PRIVATE.json',dict(runtime=fixture_result,events=fixture_events,
        interpretation='CPU request transport only; no generated answers, scientific outcomes or latency measurements'))
    public=[]
    for alias,diag in zip(('T01','T03'),diagnostics):
        public.append(dict(task=alias,candidates=[{k:v for k,v in c.items() if k not in ('handle','record_id')} for c in diag['candidates']],
            selected_rank=1,source_only_selection=True))
    report=dict(protocol=M.PROTOCOL,status='CPU_READY_AWAITING_EXPLICIT_APPROVAL',plan_sha256=object_sha256(plan),
        plan_file_sha256=file_sha256(plan_path),requests_file_sha256=file_sha256(plan['requests_path']),
        states_file_sha256=file_sha256(plan['states_path']),executor_inventory_sha256=plan['executor_inventory_sha256'],
        candidates=public,requests=[dict(task=alias,branch=r['branch'],frozen_request_id=r['frozen_request_id'],
            input_tokens=r['native_input_tokens'],payload_sha256=r['payload_sha256']) for alias,pair in zip(('T01','T03'),(requests[:2],requests[2:])) for r in pair],
        cpu_seconds=(clock.now_ns()-started['monotonic_ns'])/1e9,model_loads=0,model_calls=0,gpu_calls=0,
        api_calls=0,training_calls=0,weights_read=False,cpu_transport_fixture_calls=fixture.calls,
        actual_source_payloads_replayed_and_verified=4,formal_reward=None)
    write('CPU_CHECK_PUBLIC.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
