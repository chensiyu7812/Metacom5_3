#!/usr/bin/env python3
"""Prepare ONLY never-started requests after a fixed G stage interruption.

Completed requests are reused with their original protocol and sealed raw result.
Any uncertain start refuses preparation. An extra model load is pending explicit
authorization; this script performs no hardware, model or provider operation.
"""
import argparse
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.calibration_workflow import stamp,verify_identity
from metacom_pm.rl1.resource_comparison_runner import protocol_for
from metacom_pm.rl1.durable import save_json_once as save


def prepare(package,output):
    package,output=package.resolve(),output.resolve()
    if output.exists():raise ValueError('new successor directory required')
    manifest=json.loads((package/'PACKAGE_MANIFEST.json').read_text())
    def read(name):
        p=package/name
        if sha(p)!=manifest[name]:raise ValueError('predecessor package changed')
        return json.loads(p.read_text())
    original=read('G_PROTOCOL.json');verify_identity(original)
    requests=read('G_REQUESTS_PRIVATE.json');run=Path(original['run_directory'])
    if [r['identity'] for r in requests]!=original['request_ids']:raise ValueError('predecessor request set changed')
    reused_off=read('REUSED_OFF_PRIVATE.json')
    prior=[];remaining=[]
    for request in requests:
        key=request['identity'];verify_identity(request)
        paths=[run/(key+'.'+s+'.json') for s in ('started','raw','sealed')]
        if not any(p.exists() for p in paths):remaining.append(request);continue
        if not all(p.exists() for p in paths):raise ValueError('unknown prior start; no implicit repeat or exclusion')
        started,raw,sealed=[json.loads(p.read_text()) for p in paths];verify_identity(sealed)
        if (started!=dict(protocol_identity=original['identity'],request=request)
            or sealed['request_identity']!=key or sealed['protocol_identity']!=original['identity']
            or sealed['raw_identity']!=digest(raw) or sealed['provenance_identity']!=digest(request['provenance'])
            or raw['runtime_identity']!=original['runtime']['identity']):raise ValueError('prior completion binding failed')
        prior.append(dict(protocol_path=str(package/'G_PROTOCOL.json'),request=request,
            files={str(p):sha(p) for p in paths+[package/'G_PROTOCOL.json',run/'load.started.json',run/'load.observed.json',run/'load.done.json']}))
    if not prior or not remaining:raise ValueError('requires a genuinely partial prior run')
    raw=protocol_for(remaining,runtime=original['runtime'],assets=original['assets'],packages=original['packages'],
        gpu_uuid=original['gpu_uuid'],code_identity=original['code_identity'],source_package_identity=original['source_package_identity'],
        run_directory=output/'live_G')
    protocol=stamp({k:v for k,v in raw.items() if k!='identity'}|dict(predecessor_protocol=original['identity'],
        prior_results_identity=digest(prior),prior_G_loads=1,prior_G_calls=len(prior),
        combined_G_call_limit=len(requests),combined_G_load_limit=2))
    output.mkdir(parents=True,mode=0o700)
    for name,value in [('G_PROTOCOL.json',protocol),('G_REQUESTS_PRIVATE.json',remaining),('PRIOR_G_RESULTS_PRIVATE.json',prior),
        ('REUSED_OFF_PRIVATE.json',reused_off),('PROTECTED_HASHES.json',read('PROTECTED_HASHES.json')),
        ('CODE_HASHES.json',read('CODE_HASHES.json'))]:save(output/name,value)
    save(output/'G_APPROVAL_PENDING.json',dict(status='PENDING_RESEARCHER_DECISION',protocol_identity=protocol['identity'],
        operations=['resource_comparison_generation'],user_authorization_reference=None,
        researcher_authorization_record=None,researcher_record_sha256=None,
        additional_G_loads=1,remaining_G_calls_upper=len(remaining),reuse_prior_G=len(prior),reuse_original_OFF=len(reused_off),
        BGE_calls=0,API_cost_usd='0',scoring_calls=0,training_updates=0,new_human_assignments=0,automatic_retry=False))
    ready=dict(status='PREPARED_NOT_AUTHORIZED',protocol_identity=protocol['identity'],predecessor=original['identity'],
        remaining_inputs=len(remaining),prior_results_reused=len(prior),original_OFF_reused=len(reused_off),unknown_starts=0,
        additional_G_loads=1,combined_loads_upper=2,combined_G_calls_upper=len(requests),
        API_cost_usd='0',scope_change='one additional load required after external GPU process interrupted the resident generator',
        source_messages_and_original_G_unchanged=True)
    save(output/'READY.json',ready)
    save(output/'PREPARATION_CODE.json',{str(Path(__file__).resolve()):sha(Path(__file__))})
    save(output/'PACKAGE_MANIFEST.json',{p.name:sha(p) for p in output.iterdir() if p.is_file()})
    return ready


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();print(json.dumps(prepare(a.package,a.output),ensure_ascii=False))
