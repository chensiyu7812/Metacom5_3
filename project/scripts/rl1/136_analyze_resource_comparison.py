#!/usr/bin/env python3
"""Audit a CLOSED fixed comparison from frozen private development inputs.

No models, tokenizers, API, evaluation gold or new human labels are used. All
source/output bindings are verified before content comparisons are calculated.
"""
import argparse
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.calibration_workflow import verify_identity
from metacom_pm.rl1.durable import save_json_once
from metacom_pm.rl1.resource_comparison_analysis import summarize


def run(a):
    used={}
    def read(path,expected=None):
        path=Path(path).resolve();h=sha(path)
        if expected is not None and expected!=h:raise ValueError('input changed: '+str(path))
        used[str(path)]=h;return json.loads(path.read_text())
    package=a.package.resolve();pm=read(package/'PACKAGE_MANIFEST.json')
    def packaged(name):return read(package/name,pm[name])
    protocol=packaged('G_PROTOCOL.json');verify_identity(protocol)
    requests=packaged('G_REQUESTS_PRIVATE.json');reuse=packaged('REUSED_OFF_PRIVATE.json')
    if [r['identity'] for r in requests]!=protocol['request_ids']:raise ValueError('request list changed')
    run_dir=Path(protocol['run_directory'])
    if run_dir!=package/'live_G':raise ValueError('execution directory changed')
    closed=read(run_dir/'CLOSED.json') if (run_dir/'CLOSED.json').exists() else None
    if closed:
        verify_identity(closed)
        if closed['protocol_identity']!=protocol['identity'] or closed['completed']!=len(requests):raise ValueError('incomplete or foreign closeout')
    elif not a.allow_partial:raise ValueError('run is not closed; explicit partial audit required')
    started=read(run_dir/'load.started.json');loaded=read(run_dir/'load.observed.json')
    done=read(run_dir/'load.done.json')
    if started['protocol_identity']!=protocol['identity'] or digest(loaded['runtime'])!=digest(protocol['runtime']) or done['runtime_identity']!=protocol['runtime']['identity']:
        raise ValueError('loaded G identity changed')
    vm=read(a.views/'OUTPUT_MANIFEST.json')
    if digest(vm)!=protocol['source_package_identity']:raise ValueError('prepared source package changed')
    def view(name):return read(a.views/name,vm[name])
    inputs=view('GENERATION_INPUTS_PRIVATE.json');comparisons=view('COMPARISONS_PRIVATE.json')
    selection=view('SELECTION_BEFORE_VIEWS.json')
    if any(x['split']!='dev' for x in selection['rows']):raise ValueError('non-development prefix')
    owner={x['prefix_identity']:x['owner'] for x in selection['rows']}
    result_by_input={};pending=[]
    def collect(request, active_protocol, directory, origin):
        verify_identity(request);key=request['identity'];input_id=request['prepared_input_identity']
        paths=[directory/(key+'.'+s+'.json') for s in ('started','raw','sealed')]
        if not all(p.exists() for p in paths):
            if origin!='new_generation' or closed is not None:raise ValueError('completed result missing')
            status='not_started' if not any(p.exists() for p in paths) else 'unreconciled_start'
            pending.append(dict(request_identity=key,input_identity=input_id,status=status))
            result_by_input[input_id]=(None,origin,None,key,request,status)
            return
        entry,raw,seal=[read(p) for p in paths];verify_identity(seal)
        if entry!=dict(protocol_identity=active_protocol['identity'],request=request):raise ValueError('started request drift')
        visible={k:request[k] for k in ('messages','draw_identity','renderer_identity')}
        visible['executor_identity']=protocol['runtime']['identity']
        if (raw['request_id']!=digest(visible) or raw['runtime_identity']!=protocol['runtime']['identity']
            or raw['input_tokens']!=request['expected_input_tokens'] or raw['api_cost_usd']!=0
            or seal['request_identity']!=key or seal['protocol_identity']!=active_protocol['identity']
            or seal['raw_identity']!=digest(raw) or seal['provenance_identity']!=digest(request['provenance'])
            or seal['execution_identity']!=request['execution_identity'] or seal['finish_reason']!=raw['finish_reason']):
            raise ValueError('raw/result binding mismatch')
        if input_id in result_by_input:raise ValueError('duplicate new input')
        result_by_input[input_id]=(raw,origin,str(paths[1]),key,request,None)
    for request in requests:collect(request,protocol,run_dir,'new_generation')
    priors=packaged('PRIOR_G_RESULTS_PRIVATE.json') if 'PRIOR_G_RESULTS_PRIVATE.json' in pm else []
    if priors and digest(priors)!=protocol.get('prior_results_identity'):raise ValueError('prior result bindings changed')
    for entry in priors:
        for path,h in entry['files'].items():read(path,h)
        previous=read(entry['protocol_path']);verify_identity(previous)
        if previous['runtime']!=protocol['runtime'] or previous['source_package_identity']!=protocol['source_package_identity']:
            raise ValueError('prior generation changed model or sources')
        collect(entry['request'],previous,Path(previous['run_directory']),'prior_generation_reuse')
    for r in reuse:
        raw=read(PROJECT/r['raw_path'],r['raw_sha256'])
        if raw['request_id']!=r['original_request_id'] or raw['text']!=r['reply'] or raw['runtime_identity']!=protocol['runtime']['identity']:
            raise ValueError('original OFF result changed')
        result_by_input[r['prepared_input_identity']]=(raw,'original_OFF_reuse',str(PROJECT/r['raw_path']),r['original_request_id'],None,None)
    if len(result_by_input)!=len(inputs):raise ValueError('prepared output coverage differs')
    rows=[]
    for item in inputs:
        raw,origin,path,rid,request,pending_status=result_by_input[item['identity']]
        heads={p['head'] for p in item['purposes'] if 'head' in p}
        heads|={c['head'] for c in comparisons if item['identity'] in c['input_identities']}
        if len(heads)>1:raise ValueError('not a one-head comparison')
        if request is not None and (request['messages']!=item['messages'] or request['provenance']['selected_keys']!=item['selected_keys']
                or request['provenance']['selected_resource_identities']!=item['selected_resource_identities']
                or request['provenance']['prefix_identity']!=item['prefix_identity']
                or request['provenance']['catalog_identity']!=item['catalog_identity']):raise ValueError('prepared provenance drift')
        if not heads and (origin!='original_OFF_reuse' or item['selected_keys']):raise ValueError('OFF binding changed')
        rows.append(dict(input_identity=item['identity'],prefix_identity=item['prefix_identity'],owner=owner[item['prefix_identity']],
            head=next(iter(heads)) if heads else None,selected_keys=item['selected_keys'],purposes=item['purposes'],
            origin=origin,request_identity=rid,raw_path=path,raw_sha256=used[str(Path(path).resolve())] if path else None,
            finish_reason=raw['finish_reason'] if raw else pending_status,reply=raw['text'] if raw and raw['finish_reason']=='natural_stop' else None,
            partial_reply=raw['text'] if raw and raw['finish_reason']!='natural_stop' else None,
            input_tokens=raw['input_tokens'] if raw else item['usage']['input_tokens'],output_tokens=raw['output_tokens'] if raw else None,
            resource_tokens=item['usage']['resource_tokens'],generation_seconds=raw.get('generation_seconds') if raw else None,
            q=None,m=None,quality_direction='unverified'))
    report,pairs,off_pairs=summarize(rows,comparisons)
    report.update(protocol_identity=protocol['identity'],current_run_G_loads=1,
        current_run_G_calls=sum((run_dir/(r['identity']+'.started.json')).exists() for r in requests),
        stage_family_G_loads=1+len({r['protocol_path'] for r in priors}),execution_closed=closed is not None,
        pending=len(pending),unreconciled_starts=sum(p['status']!='not_started' for p in pending),BGE_calls=0,API_cost_usd='0',
        load_seconds=loaded['seconds'],summary_method='exact strings and frozen pair metadata; no quality judge')
    out=a.output.resolve()
    if out.exists():raise ValueError('new analysis directory required; do not overwrite an audit')
    out.mkdir(parents=True,mode=0o700)
    for name,data in [('SUMMARY.json',report),('RESPONSES_PRIVATE.json',rows),('PAIRS_PRIVATE.json',pairs),
                      ('OFF_PAIRS_PRIVATE.json',off_pairs),('PENDING_REQUESTS_PRIVATE.json',pending),('INPUT_HASHES_PRIVATE.json',used)]:save_json_once(out/name,data)
    save_json_once(out/'CODE_HASHES.json',{str(Path(__file__).resolve()):sha(Path(__file__)),
        str(PROJECT/'src/metacom_pm/rl1/resource_comparison_analysis.py'):sha(PROJECT/'src/metacom_pm/rl1/resource_comparison_analysis.py')})
    save_json_once(out/'OUTPUT_MANIFEST.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',required=True,type=Path)
    p.add_argument('--views',type=Path,default=PROJECT/'outputs/pm_rl1/evidence_views_20261030_v3')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--allow-partial',action='store_true')
    run(p.parse_args())
