#!/usr/bin/env python3
"""Actual legal source/tool execution with deterministic CPU protocol fixtures.

No model, HF backend, GPU, paid API or scientific output is executed. Synthetic
controller replies exercise the entire runtime, including live SEARCH/EXPAND.
"""
import argparse,json
from collections import Counter,defaultdict
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
from metacom_pm.rl1v3.journal.selective_memory_validation_sources import load_development_cache
from metacom_pm.rl1v3.journal.pomdp_dynamic_runtime import LiveEpisodeFactory,execute_source_pair
from metacom_pm.rl1v3.journal.pomdp_latency import MonotonicClock
from metacom_pm.rl1v3.journal import pomdp_dynamic_runtime,pomdp_dynamic_worker,pomdp_controller_protocol,pomdp_latency


class CPUFixtureBackend:
    kind='cpu_protocol_fixture_not_model'
    def __init__(self,tokenizer,scope):self.tokenizer=tokenizer;self.scope_sha256=scope;self.counts=Counter();self.requests=[]
    def generate(self,request,seconds):
        self.requests.append(request);role=request['role'];tid=request['binding']['task_id'];self.counts[(tid,role)]+=1
        if role=='terminal':text='CPU protocol fixture only; no model response was generated.'
        else:
            observation=json.loads(request['payload']['messages'][1]['content'])
            if role=='oneshot':
                value=[dict(action='SEARCH',query=observation['query']),dict(action='EXPAND',from_search=0,hit_rank=0),dict(action='STOP')]
            else:
                number=self.counts[(tid,role)]
                value=(dict(action='SEARCH',query=observation['query']) if number in (1,3)
                    else dict(action='EXPAND',handle=observation['last_hits'][0 if number==2 else -1]))
            text=json.dumps(value,ensure_ascii=False)
        ids=self.tokenizer.encode(text,add_special_tokens=False)+[1]
        if len(ids)>request['payload']['decode']['max_new_tokens']:raise ValueError('CPU fixture exceeds role cap')
        return dict(token_ids=ids,text=text,finish_reason='eos',seconds=0.0,
            input_tokens=len(request['payload']['input_ids']),request_sha256=object_sha256(request),
            fixture=True,actual_model_called=False)


def run(bundle,cpu,proposal,resources,metadata,base_plan,asset_manifest,out):
    bundle,cpu,proposal,out=map(Path,(bundle,cpu,proposal,out))
    if out.exists():raise FileExistsError(out)
    def rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
    selected=json.loads((proposal/'PROPOSAL_PRIVATE.json').read_text())
    tasks_by_id={r['task_id']:r for r in rows(bundle/'TASKS.runtime.jsonl')}
    envs={r['task_id']:r for r in rows(bundle/'TASK_ENVELOPES.private.jsonl')}
    groups=defaultdict(list)
    for tid in selected['task_ids']:groups[envs[tid]['asof_runtime_sha256']].append(tasks_by_id[tid])
    if len(groups)!=4 or any(len(g)!=2 for g in groups.values()):raise ValueError('frozen four source pairs')
    original={(r['task_id'],r['arm']):r for r in rows(proposal/'DETERMINISTIC_32_REQUESTS.private.jsonl')}
    base=json.loads(Path(base_plan).read_text());baseline=json.loads(Path(base['baseline_path']).read_text())
    out.mkdir(parents=True);clock=MonotonicClock();started=clock.stamp()
    registry=load_development_cache(resources_path=resources,metadata_path=metadata,
        allowed_owners=['p1','p13','p15','p18'],excluded_owners=['p2','p3','p8','p10','p11','p12'])
    native=NativeTokenizer(base['model_path'],asset_manifest);tokenizer=PromptTokenizer(native)
    initial_ready=clock.stamp();summaries=[];all_events=[];all_requests=[];matches=[]
    for index,tasks in enumerate(groups.values(),1):
        factory=LiveEpisodeFactory(registry=registry,tokenizer=tokenizer,baseline_sha256=baseline['binding_sha256'],
            envelopes=envs,ledger_root=out/('ledgers-'+str(index)),frozen_pools_path=cpu/'LEGAL_POOLS.private.jsonl')
        prep_start=clock.stamp();factory.prepare(tasks);prep_end=clock.stamp()
        backend=CPUFixtureBackend(native.tokenizer,object_sha256(selected));events=[]
        result=execute_source_pair(tasks=tasks,factory=factory,backend=backend,
            emit=lambda name,**kw:events.append(dict(event=name,**kw)),clock=clock,deadline_ns=clock.now_ns()+1200*10**9)
        if result['status']!='FINISHED':raise ValueError('CPU dynamic failure: '+str(result['reason']))
        for request in backend.requests:
            key=(request['binding']['task_id'],request['binding']['method'])
            if request['role']=='terminal' and key in original:
                actual=request['payload'];previous=original[key]['model_input']
                if actual!=previous:raise ValueError('live deterministic payload differs: '+str(key))
                matches.append(dict(task_id=key[0],method=key[1],payload_sha256=object_sha256(actual),byte_projection_equal=True))
        summaries.append(dict(batch=index,backend=backend.kind,physical_fixture_dispatches=result['physical_calls'],
            fixture_calls_by_role=result['calls_by_role'],actual_model_calls=0,pending=len(result['pending']),
            terminal_results=len(result['results']),source_prepare_started=prep_start,source_prepare_finished=prep_end,
            source_prepare_ns=prep_end['monotonic_ns']-prep_start['monotonic_ns'],status=result['status']))
        write_json_once(out/('BATCH_%02d_PRIVATE.json'%index),result)
        all_events.extend(dict(batch=index,**event) for event in events);all_requests.extend(backend.requests)
    if len(matches)!=32:raise ValueError('not all existing deterministic inputs were matched')
    write_jsonl_once(out/'EVENTS_PRIVATE.jsonl',all_events)
    write_jsonl_once(out/'REQUESTS_PRIVATE.jsonl',all_requests)
    write_jsonl_once(out/'DETERMINISTIC_READBACK_PRIVATE.jsonl',matches)
    finished=clock.stamp();report=dict(protocol='pmrl1-j-dynamic-real-tool-cpu-check-v1',
        source_pairs=4,tasks=8,terminal_fixture_dispatches=48,controller_fixture_dispatches=40,
        fixture_dispatches=88,actual_model_calls=0,GPU_calls=0,paid_API_calls=0,cache_disabled=True,
        deterministic_payloads_identical=32,all_terminal_slots=48,formal_reward=None,
        checked='actual same-source Ledger/PrefixPort reconstruction, live lookup/expand, strict controller runtime and counters; CPU fixture replies are not model outputs',
        bootstrap_started=started,tokenizer_registry_ready=initial_ready,finished=finished,
        bootstrap_ns=initial_ready['monotonic_ns']-started['monotonic_ns'],
        cpu_total_ns=finished['monotonic_ns']-started['monotonic_ns'],batches=summaries,
        implementation_sha256={m.__name__:file_sha256(m.__file__) for m in
            (pomdp_dynamic_runtime,pomdp_dynamic_worker,pomdp_controller_protocol,pomdp_latency)},
        checker_sha256=file_sha256(__file__),
        event_counts=dict(Counter(e['event'] for e in all_events)),
        timing_categories=dict(Counter(s['category'] for e in all_events if e['event']=='TERMINAL_INPUT_BOUND'
            for s in e['source_receipt'].get('timing_spans',[]))),
        files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},
        runtime_input_identities={str(p):file_sha256(p) for p in [bundle/'TASKS.runtime.jsonl',bundle/'TASK_ENVELOPES.private.jsonl',
            cpu/'LEGAL_POOLS.private.jsonl',proposal/'DETERMINISTIC_32_REQUESTS.private.jsonl']})
    write_json_once(out/'CPU_CHECK_PUBLIC.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('bundle','cpu','proposal','resources','metadata','base-plan','asset-manifest','out'):parser.add_argument('--'+name,required=True)
    print(json.dumps(run(**vars(parser.parse_args())),indent=2))
