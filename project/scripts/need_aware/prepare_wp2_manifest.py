#!/usr/bin/env python3
"""Produce actual frozen logical slots; this grants no inference authorization."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
from metacom_pm.need_aware.data.contracts import load_runtime,digest
from metacom_pm.need_aware.data.personamem import SEED,sha_file,write_json,write_jsonl

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--artifacts',required=True);p.add_argument('--models',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    root,out=Path(a.artifacts),Path(a.output);tasks=load_runtime(root/'runtime/tasks.mcq.jsonl');models=json.loads(Path(a.models).read_text())
    direct={r['task_id']:r for r in map(json.loads,(root/'direct/direct.jsonl').read_text().splitlines())}
    rng=random.Random(SEED);rng.shuffle(tasks);order=[]
    for t in tasks:
        arms=list('ABCD');rng.shuffle(arms)
        order.extend((t,arm) for arm in arms)
    requests=[]
    for model in models['models']:
        for t,arm in order:
            status='not_evaluable' if arm in 'CD' and direct[t.task_id]['status']!='located_unique' else 'pending_authorization'
            r={'task_id':t.task_id,'model_id':model['model_id'],'model_revision':model['revision'],'arm':arm,
               'runtime_task_sha256':digest(t.to_dict()),'status':status,
               'direct_coordinate_manifest_sha256':digest(direct[t.task_id]) if arm in 'CD' else None,
               'input_cap_tokens':12000,'output_cap_tokens':1024,'backend_context_tokens':16384,
               'decode':{'do_sample':False,'enable_thinking':False,'seed':0,
                         'eos_token_id':model['naa_stop_token_ids'],'pad_token_id':model['pad_token_id'],
                         'suppress_tokens':model['suppress_tokens'],'stop':'native EOS; length is truncation, not success'},
               'actual_request_sha256':None,'actual_request_status':'B materializer must bind final native messages before inference'}
            r['logical_request_sha256']=digest(r);requests.append(r)
    assert len(requests)==1920 and len({r['logical_request_sha256'] for r in requests})==1920
    write_jsonl(out/'logical_requests.jsonl',requests)
    count=Counter(r['status'] for r in requests)
    report={'authorization':{'gpu':False,'training':False,'paid_api':False,'formal_test':False},
            'frozen_source_sha256':sha_file(root/'FREEZE.json'),'logical_slots':len(requests),
            'runnable_before_exact_deduplication':count['pending_authorization'],'not_evaluable_slots':count['not_evaluable'],
            'physical_generation_attempt_cap_proposed':1920,'retry_headroom_before_deduplication':1920-count['pending_authorization'],
            'gpu_wall_seconds_cap_proposed':43200,'gpu_count_proposed':1,'device_class':'RTX A6000 48GB; sequential model loading; availability rechecked at run time',
            'smoke':'first 16 runnable physical calls are inside this same budget, then continue on technical success',
            'retry':'only failed exact requests, append-only receipts; all attempts count against physical/time caps; never rerun successful requests to improve answers',
            'exact_cache':'B hashes final native messages + model/tokenizer/decode/retrieval versions; logical hashes are not an exact-output cache key',
            'open_generation_tasks_prepared':60,'open_generation_calls_in_this_request':0,
            'open_generation_followup_upper_bound':180,'open_generation_budget_note':'separate explicit allocation required; never hidden within 1920 MCQ slots',
            'model_calls_executed':0,'b_joint_confirmation':'pending B final renderer/runner commit and receipts',
            'manifest_sha256':sha_file(out/'logical_requests.jsonl')}
    write_json(out/'wp2_request.json',report);print(json.dumps(report,indent=2))
