#!/usr/bin/env python3
"""Bind complete real replies to initial ON/OFF programs before any labeling.

Exact evidence/reply duplicates share a prospective measurement. Missing or
non-natural generation prevents release of a smaller, outcome-selected pool.
No selected judge, score, qualification, paid call or training is created.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json
from metacom_pm.rl1.calibration_workflow import verify_identity


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())


def build(package, generation, output):
    if output.exists(): raise ValueError('new feedback preparation directory required')
    manifest=read(package/'PACKAGE_MANIFEST.json')
    for name,h in manifest.items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(package/name)!=h:
            raise ValueError('initial preparation changed')
    source=read(generation/'SOURCE.json');report=read(generation/'RESULTS.json')
    protocol=read(generation/'PROTOCOL.json');verify_identity(protocol)
    if (source['manifest_identity']!=digest(manifest) or report['protocol_identity']!=protocol['identity']
            or report['status']!='INITIAL_GENERATIONS_COMPLETE_PENDING_QUALIFIED_FEEDBACK'):
        raise ValueError('complete bound generation stage required')
    requests=read(package/'REQUESTS_PRIVATE.json');responses=read(generation/'RESPONSES_PRIVATE.json')
    reused=read(package/'REUSED_OFF_PRIVATE.json');menu=read(package/'MENU_PRIVATE.json');verify_identity(menu)
    if set(responses)!=set(requests) or set(requests)-set(reused)!=set(protocol['request_ids']):
        raise ValueError('complete scheduled response coverage required')
    inputs={};bindings={};source_hashes={};evidence={}
    for req in requests.values():
        pid=req['provenance']['prefix_identity']
        if pid not in evidence:
            src=read(package/'sources_private'/(pid+'.json'))
            if src['prefix']['split']!='train': raise ValueError('train-only feedback preparation')
            evidence[pid]=src['evidence']
            if digest(evidence[pid])!=src['evidence_source']['evidence_identity']: raise ValueError('evidence drift')
        key=req['request_id'];raw=responses[key]
        if (raw['request_id']!=key or raw['runtime_identity']!=req['executor_identity']
                or raw['source_provenance_identity']!=digest(req['provenance'])
                or raw['input_tokens']!=req['expected_input_tokens'] or raw['finish_reason']!='natural_stop'
                or not raw['text'].strip()): raise ValueError('natural reply/source/runtime/input binding changed')
        if key in reused:
            if raw!=reused[key]: raise ValueError('historical OFF reuse changed')
        else:
            qid=digest(dict(kind='generation',payload=req));seal_path=generation/'worker'/(qid+'.sealed.json')
            seal=read(seal_path);verify_identity(seal)
            raw_path=generation/'worker'/(qid+'.raw.json')
            if (seal['queue_id']!=qid or seal['backend_identity']!=protocol['identity']
                    or sha(raw_path)!=seal['raw_sha256'] or raw!=read(raw_path)):
                raise ValueError('response export differs from sealed real generation')
            source_hashes[str(raw_path.resolve())]=seal['raw_sha256']
            source_hashes[str(seal_path.resolve())]=sha(seal_path)
        content=digest(dict(evidence=evidence[pid],reply=raw['text']))
        item=inputs.setdefault(content,dict(evidence=evidence[pid],reply=raw['text'],request_ids=[],
            evidence_identity=digest(evidence[pid]),reply_identity=digest(raw['text']),q=None,m=None,qualified_reward=False))
        item['request_ids'].append(key);bindings[key]=content
    endpoints=[dict(endpoint_identity=x['identity'],prefix_identity=x['prefix_identity'],actions=x['actions'],
        resource_tokens=x['resource_tokens'],cost_identity=x['cost_identity'],
        ON=bindings[x['requests']['ON']['request_id']],OFF=bindings[x['requests']['OFF']['request_id']])
        for x in menu['endpoints']]
    summary=dict(status='COMPLETE_REAL_INPUTS_PENDING_SELECTED_QUALIFIED_MEASUREMENT',
        prefixes=len(evidence),programs=len(endpoints),generation_inputs=len(requests),
        new_G_calls=len(protocol['request_ids']),reused_OFF=len(reused),
        unique_evidence_reply_inputs=len(inputs),generation_rows_sharing_scoring_input=len(requests)-len(inputs),
        ON_equals_OFF_programs=sum(e['ON']==e['OFF'] for e in endpoints),
        scoring_group_sizes=dict(Counter(len(x['request_ids']) for x in inputs.values())),
        selected_measurement_route=None,qualified_scores=0,BC_checkpoints=0,natural_updates=0,
        new_G_in_this_preparation=0,new_J_calls=0,API_cost_usd=0,
        menu_identity=menu['identity'],generation_protocol_identity=protocol['identity'],
        interpretation='Exact-content reuse only; program counts are not independent judgments. No missing feedback is zero.')
    output.mkdir(parents=True,mode=0o700)
    save_json(output/'INPUTS_PRIVATE.json',inputs);save_json(output/'ENDPOINTS_PRIVATE.json',endpoints)
    save_json(output/'SUMMARY.json',summary)
    save_json(output/'SOURCES_PRIVATE.json',dict(package_manifest_sha256=sha(package/'PACKAGE_MANIFEST.json'),
        response_export_sha256=sha(generation/'RESPONSES_PRIVATE.json'),code_sha256=sha(__file__),raw_and_seal_hashes=source_hashes))
    save_json(output/'OUTPUT_MANIFEST.json',{p.name:sha(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('package','generation','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();build(a.package,a.generation,a.output)
