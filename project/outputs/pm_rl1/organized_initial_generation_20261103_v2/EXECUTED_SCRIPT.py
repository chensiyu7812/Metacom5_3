#!/usr/bin/env python3
"""Prepare/check/execute finite real G inputs for the new initial train pool.

No J, reward assignment or optimizer. Reused OFF stays source-bound and is
never counted as a new sample. Unknown generation is not automatically retried.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.local_backend import local_protocol, LOCAL, check_static
from metacom_pm.rl1.organized_local_backend import OrganizedLocalBackend
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.generation_worker import GenerationWorker
from metacom_pm.rl1.cached_generation_worker import make_cache_index,replay_cached_generations
from metacom_pm.rl1.natural_batch import FeedbackQueue
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json,file_sha


def read(path):return json.loads(Path(path).read_text())


def prepare(package,output):
    manifest=read(package/'PACKAGE_MANIFEST.json')
    for name,h in manifest.items():
        if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(package/name)!=h:raise ValueError('source package changed')
    c=read(package/'CONFIG.json');requests=read(package/'REQUESTS_PRIVATE.json');reused=read(package/'REUSED_OFF_PRIVATE.json')
    if not set(reused)<=set(requests):raise ValueError('foreign reuse')
    runtime=c['runtime'];assets={str(Path(runtime['model_dir'])/n):h for n,h in runtime['model_files'].items()}
    assets.update({str(Path(runtime['adapter']['path'])/n):h for n,h in runtime['adapter']['files'].items()})
    for name in ('generation','bound_generation','generation_requests','organized_feedback','local_backend','organized_local_backend',
                 'local_gpu_guard','generation_worker','cached_generation_worker','natural_batch'):
        p=PROJECT/'src/metacom_pm/rl1'/(name+'.py');assets[str(p)]=file_sha(p)
    assets[str(Path(__file__).resolve())]=file_sha(__file__)
    source=PROJECT/'scripts/rl1/92_run_p2_common_pool.py';assets[str(source)]=file_sha(source)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    pending=[k for k in requests if k not in reused]
    protocol=local_protocol(scope=LOCAL,runtime=runtime,bge_binding=c['bge_binding'],bge_runtime=c['bge_runtime'],
        assets=assets,packages=runtime['packages']|{'peft':runtime['adapter']['peft_version']},
        gpu_uuid=c['gpu_uuid'],request_ids=pending,max_embedding_batches=1,context_identity=digest(manifest))
    protocol=stamp({k:v for k,v in protocol.items() if k!='identity'} | dict(
        gpu_sampling_policy='last_xml',run_directory=str((output/'backend').resolve())))
    save_json(output/'PROTOCOL.json',protocol)
    save_json(output/'SOURCE.json',dict(package=str(package.resolve()),manifest_identity=digest(manifest),
        source_manifest_sha256=file_sha(package/'PACKAGE_MANIFEST.json'),requests_identity=digest(requests),reused_identity=digest(reused)))
    save_json(output/'READY.json',dict(status='PREPARED',new_G_upper=len(pending),reused_OFF=len(reused),max_G_loads=1,
        actual_BGE_scope=0,J_calls=0,API_cost_usd=0,training_updates=0,protocol_identity=protocol['identity']))
    return protocol


def execute(output,approval):
    protocol=read(output/'PROTOCOL.json');source=read(output/'SOURCE.json');package=Path(source['package'])
    if file_sha(package/'PACKAGE_MANIFEST.json')!=source['source_manifest_sha256']:raise ValueError('source manifest drift')
    requests=read(package/'REQUESTS_PRIVATE.json');reused=read(package/'REUSED_OFF_PRIVATE.json')
    if digest(requests)!=source['requests_identity'] or digest(reused)!=source['reused_identity']:raise ValueError('bound requests/results changed')
    grant=read(approval);record=Path(grant['researcher_authorization_record'])
    if file_sha(record)!=grant['researcher_record_sha256']:raise ValueError('actual user authorization record changed')
    check_static(protocol)
    q=FeedbackQueue(output/'feedback.sqlite')
    for req in requests.values():q.generate(req)
    cached=output/'reused';cached.mkdir(exist_ok=True,mode=0o700);entries=[]
    for key,raw in reused.items():
        rp=cached/(key+'.request.json');op=cached/(key+'.raw.json')
        if not rp.exists():save_json(rp,requests[key])
        if not op.exists():save_json(op,raw)
        entries.append(dict(request_path=str(rp),request_sha256=file_sha(rp),raw_path=str(op),raw_sha256=file_sha(op)))
    index=make_cache_index(entries,source_identity=source['reused_identity'])
    replay=replay_cached_generations(q,index,max_items=len(reused));save_json(output/'CACHE_REPLAY.json',replay)
    backend=OrganizedLocalBackend(protocol,output/'backend',approval=grant)
    worker=GenerationWorker(q,backend,output/'worker');completed=0;started=time.monotonic()
    while True:
        result=worker.step()
        if result['status']=='IDLE':break
        if result['status']!='GENERATION_SETTLED':raise RuntimeError(result['status'])
        completed+=result['new_calls']
        if result['finish_reason']!='natural_stop':raise RuntimeError('non-natural generation; retained, no retry')
        if completed%10==0:print(json.dumps(dict(new_generations=completed,total=len(protocol['request_ids']))),flush=True)
    responses={k:q.generate(r) for k,r in requests.items()}
    if any(v is None for v in responses.values()):raise ValueError('unfilled generation request')
    save_json(output/'RESPONSES_PRIVATE.json',responses)
    report=dict(status='INITIAL_GENERATIONS_COMPLETE_PENDING_QUALIFIED_FEEDBACK',requests=len(requests),
        reused_OFF=len(reused),new_G_calls=completed,G_loads=len(list((output/'backend').glob('load_*.done.json'))),
        finish_reasons=dict(Counter(r['finish_reason'] for r in responses.values())),
        BGE_loads=0,J_calls=0,API_cost_usd=0,qualified_scores=0,BC_checkpoints=0,natural_updates=0,
        protocol_identity=protocol['identity'],seconds=time.monotonic()-started)
    save_json(output/'RESULTS.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','check','execute'])
    p.add_argument('--package',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--approval',type=Path)
    a=p.parse_args()
    if a.mode=='prepare':
        prepare(a.package,a.output);print(json.dumps(read(a.output/'READY.json')),flush=True)
    elif a.mode=='check':print(json.dumps(check_static(read(a.output/'PROTOCOL.json'))),flush=True)
    else:execute(a.output,a.approval)
