#!/usr/bin/env python3
"""Bounded free local latency pilot: 2 warmups + 24 interleaved requests.

No paid services, quality scorer, optimizer, trained-policy claim or retries.
Models resident; request-local feature cache starts empty on EVERY request.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, replace
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.client_latency import ReferenceStreamClient, validate_trace
from metacom_pm.rl1.durable import save_json_once
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.latency_serving import RequestVectors, prepare_online, stream_generate, streaming_identity, stage
from metacom_pm.rl1.local_backend import check_static, load_generator
from metacom_pm.rl1.local_gpu_guard import LocalGPUCheck
from metacom_pm.rl1.observation_features import make_actor_critic
from metacom_pm.rl1.organized_encoding import LoadedBGEBlocks
from metacom_pm.rl1.organized_features import FullTextFeatures
from metacom_pm.rl1.resource_organization import OrganizedItem, OrganizationCatalog, OrganizedRenderer
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json, file_sha

BASE = PROJECT/'outputs/pm_rl1'
TRAIN = BASE/'organized_initial_training_20261103_v2'
ARMS = dict(OFF=[0],MS1=[3,0],MS6=[3,3,3,3,3,3,0],
            MS6_sequential_replay=[3,3,3,3,3,3,0])


def read(path): return json.loads(Path(path).read_text())


def verify(folder,name='OUTPUT_MANIFEST.json'):
    for relative,h in read(folder/name).items():
        if Path(relative).is_absolute() or '..' in Path(relative).parts or file_sha(folder/relative) != h:
            raise ValueError('source manifest mismatch')


def prepare(output):
    if output.exists(): raise ValueError('new output required')
    branches = BASE/'decision_branches_20261104_v2'
    feedback = BASE/'actual_training_feedback_20261103_v1'
    verify(TRAIN,'PACKAGE_MANIFEST.json'); verify(branches); verify(feedback)
    c = read(TRAIN/'CONFIG.json'); menu = read(TRAIN/'MENU_PRIVATE.json')
    cases = {r['case_id']:r['prefix_identity'] for r in read(branches/'CASES_PRIVATE.json') if r['case_id'] in ('C02','C03')}
    if set(cases) != {'C02','C03'}: raise ValueError('bound cases missing')
    expected = {}
    for cid,pid in cases.items():
        for arm,actions in ARMS.items():
            rows = [e for e in menu['endpoints'] if e['prefix_identity']==pid and e['actions']==actions]
            if len(rows) != 1: raise ValueError('diagnostic program has no unique historical input')
            expected[cid+'/'+arm] = rows[0]['requests']['ON']
    schedule = []; rng = random.Random(17)
    for cid in cases:
        schedule.append(dict(case=cid,arm='MS6_sequential_replay',repeat=-1,warmup=True))
    for repeat in range(3):
        order = list(cases); rng.shuffle(order)
        for cid in order:
            arms = list(ARMS); rng.shuffle(arms)
            schedule.extend(dict(case=cid,arm=arm,repeat=repeat,warmup=False) for arm in arms)
    for i,row in enumerate(schedule): row['slot'] = f'latency_{i:03d}'
    source_paths = [TRAIN/'PACKAGE_MANIFEST.json',branches/'OUTPUT_MANIFEST.json',feedback/'OUTPUT_MANIFEST.json',
        PROJECT/'docs/reviews/20261104/pm_rl1_latency_primary/OBJECTIVE.json',
        BASE/'organized_initial_generation_20261103_v2/PROTOCOL.json',
        BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json',Path(__file__)]
    sources = read(TRAIN/'INPUT_HASHES_PRIVATE.json')
    for p in source_paths: sources[str(p.resolve())] = file_sha(p)
    for name in ('client_latency','latency_serving','organized_encoding','organized_features','organized_policy_interface',
                 'resource_organization','observation_features','organized_feedback','local_gpu_guard','local_backend'):
        p = PROJECT/'src/metacom_pm/rl1'/(name+'.py'); sources[str(p.resolve())] = file_sha(p)
    lineage = read(feedback/'SOURCES_PRIVATE.json')
    if file_sha(source_paths[-2]) != lineage['response_export_sha256']:
        raise ValueError('historical replies changed')
    old_checks = read(PROJECT/'docs/reviews/20261104/pm_rl1_latency_primary/CHECKS.json')
    j = read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for p,h in j['policy']['historical_files'].items():
        if file_sha(p) != h: raise ValueError('frozen source changed')
    if file_sha(j['ledger']) != old_checks['ledger_sha256']: raise ValueError('ledger changed')
    regime = dict(surface='local_reference_queue_client',network='in-process FIFO, no network/browser claim',
        concurrency=1,gpu_uuid=c['gpu_uuid'],models='resident G+BGE; setup excluded and reported separately',
        feature_cache='empty at every request; exact acquired blocks reused within request only',
        generator_response_cache=False,token_count_cache=False,torch_cpu_threads=1,
        static_catalog='prebuilt legal source/term indexes resident; query ranking is online',
        streaming_executor=streaming_identity(c['runtime']['identity']),
        sequential_policy='seed-17 UNTRAINED original MLP forward; precommitted actions override its predictions',
        prior_warmups=2,repetitions_per_case_arm=3,client_technical_timeout_seconds=900.,
        tail_inference='observed p95 with n=3 equals maximum; no population-tail claim')
    body = dict(version='pmrl1-reference-latency-pilot-20261104-v1',cases=cases,arms=ARMS,schedule=schedule,
        regime=regime,regime_identity=digest(regime),max_G_loads=1,max_BGE_loads=1,max_G_calls=26,
        max_BGE_forward_batches=56,max_policy_forwards=56,api_calls=0,training_updates=0,
        output_directory=str(output.resolve()),sources=sources,ledger_sha256=old_checks['ledger_sha256'],
        authorization=dict(source='current conversation 2026-11-04',instruction='好的，继续推进。',
            scope='Implement client-path measurement and a bounded free local paired latency pilot under the explicitly corrected latency objective.'))
    protocol = dict(body,identity=digest(body))
    output.mkdir(parents=True,mode=0o700)
    save_json(output/'PROTOCOL.json',protocol); save_json(output/'EXPECTED_PRIVATE.json',expected)
    save_json(output/'EXPECTED_HASH.json',dict(sha256=file_sha(output/'EXPECTED_PRIVATE.json')))
    print(json.dumps(dict(status='PREPARED',G_calls_upper=26,measured_requests=24,warmups=2,
        BGE_batches_upper=56,api_cost_usd=0,protocol_identity=protocol['identity'])),flush=True)


def run(output):
    p = read(output/'PROTOCOL.json')
    if p['identity'] != digest({k:v for k,v in p.items() if k!='identity'}) or p['output_directory'] != str(output.resolve()):
        raise ValueError('bound pilot identity/directory changed')
    for path,h in p['sources'].items():
        if file_sha(path) != h: raise ValueError('frozen pilot source changed: '+path)
    verify(TRAIN,'PACKAGE_MANIFEST.json')
    if file_sha(output/'EXPECTED_PRIVATE.json') != read(output/'EXPECTED_HASH.json')['sha256']:
        raise ValueError('expected requests changed')
    if any(output.glob('LOAD_STARTED.json')): raise ValueError('load already entered; no automatic retry/resume')
    if any(os.environ.get(k) != '1' for k in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE')):
        raise ValueError('offline loading required')
    c = read(TRAIN/'CONFIG.json')
    check_static(read(BASE/'organized_initial_generation_20261103_v2/PROTOCOL.json'))
    guard = LocalGPUCheck(c['gpu_uuid'],c['runtime'],output/'gpu_checks',latest_snapshot=True)
    guard.check()
    save_json_once(output/'LOAD_STARTED.json',dict(protocol_identity=p['identity'],unix_seconds=time.time()))
    import torch
    torch.set_num_threads(1)
    start = time.monotonic()
    generator = load_generator(c['runtime'])
    if digest(dict(generator.manifest,identity=generator.identity)) != digest(c['runtime']):
        raise ValueError('actual frozen generator changed')
    save_json(output/'G_LOADED.json',dict(seconds=time.monotonic()-start,identity=generator.identity))
    print(json.dumps(dict(status='G_LOADED')),flush=True)
    from metacom_pm.paper1.embeddings.bge_m3 import FROZEN_BGE_M3_BINDING, _load_model
    guard.check(own_pid=os.getpid()); start = time.monotonic()
    if asdict(FROZEN_BGE_M3_BINDING) != c['bge_binding']: raise ValueError('BGE binding changed')
    model,runtime = _load_model(FROZEN_BGE_M3_BINDING)
    if asdict(runtime) != c['bge_runtime']: raise ValueError('BGE runtime changed')
    bge = LoadedBGEBlocks(model,binding=FROZEN_BGE_M3_BINDING,runtime=runtime,
        expected_tokenizer_identity=c['bge_tokenizer_identity'])
    if bge.identity != c['encoder_identity']: raise ValueError('BGE input identity changed')
    save_json(output/'BGE_LOADED.json',dict(seconds=time.monotonic()-start,identity=bge.identity))
    print(json.dumps(dict(status='BGE_LOADED')),flush=True)
    gt,bt = generator.tokenizer,model.tokenizer
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    renderer = OrganizedRenderer(count_text=lambda s:len(gt.encode(s,add_special_tokens=False,truncation=False)),
        count_chat=lambda ms:len(gt.apply_chat_template(ms,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256,template=gt.chat_template)),
        context_limit=c['runtime']['policy']['context_limit'])
    if renderer.identity != c['renderer_identity']: raise ValueError('renderer changed')
    planner = FullTextFeatures(encode_tokens=lambda s:bt.encode(s,add_special_tokens=False,truncation=False),
        add_special_tokens=bt.build_inputs_with_special_tokens,native_window=8192,
        special_tokens=bt.num_special_tokens_to_add(pair=False),tokenizer_identity=c['bge_tokenizer_identity'],
        encoder_identity=bge.identity,dimension=1024)
    if planner.identity != c['feature_identity']: raise ValueError('feature planner changed')
    library_paths = [s for s in read(TRAIN/'INPUT_HASHES_PRIVATE.json') if s.endswith('/RS_LIBRARY_PRIVATE.json')]
    if len(library_paths) != 1: raise ValueError('one original RS library required')
    library = read(library_paths[0]); items = {x['key']:OrganizedItem(**x) for x in library['items']}
    catalogs = {}
    for cid,pid in p['cases'].items():
        src = read(TRAIN/'sources_private'/(pid+'.json')); stored = read(src['stored_source_path'])
        metadata = stored['frozen_RS_metadata']
        local = [replace(v,original_rank=metadata[k][0],bge_similarity=metadata[k][1]) if k in metadata else v for k,v in items.items()]
        local += [OrganizedItem(**x) for x in stored['memory']]
        catalog = OrganizationCatalog(prefix_from_dict(src['prefix']),local,provenance_identity=stored['catalog_identity'])
        if catalog.identity != src['catalog_identity']: raise ValueError('catalog changed')
        catalogs[cid] = catalog
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(17); actor = make_actor_critic(planner.feature_dimension).eval()
    expected = read(output/'EXPECTED_PRIVATE.json')
    history = read(BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    slots = {r['slot']:r for r in p['schedule']}; entered = set(); counters = Counter()
    def encode(blocks):
        if counters['bge_batches'] >= p['max_BGE_forward_batches']: raise ValueError('bounded BGE envelope exhausted')
        counters['bge_batches'] += 1
        return bge(blocks)
    def decide(values,mask,planned):
        if counters['policy_forwards'] >= p['max_policy_forwards']: raise ValueError('bounded policy envelope exhausted')
        counters['policy_forwards'] += 1
        with torch.inference_mode():
            dist,value = actor(torch.tensor(values,dtype=torch.float32),torch.tensor(mask))
        if not torch.isfinite(value) or not mask[planned]: raise ValueError('invalid public policy computation')
        return planned
    def service(row,emit):
        if row != slots.get(row['slot']) or row['slot'] in entered:
            raise ValueError('request outside fixed schedule or already entered')
        entered.add(row['slot'])
        view = RequestVectors(planner,encode) if row['arm']=='MS6_sequential_replay' else None
        req,events = prepare_online(catalogs[row['case']],renderer,actions=p['arms'][row['arm']],
            sequential_view=view,decide=decide,executor_identity=p['regime']['streaming_executor'],draw_identity=row['slot'])
        old = expected[row['case']+'/'+row['arm']]
        if (req['messages'] != old['messages'] or req['provenance']['selected_keys'] != old['provenance']['selected_keys']
                or req['expected_input_tokens'] != old['expected_input_tokens']):
            raise ValueError('online retrieval differs from bound historical program')
        counters['G_calls'] += 1
        if counters['G_calls'] > p['max_G_calls']: raise ValueError('bounded G envelope exhausted')
        with stage(events,'G_tokenize_transfer_stream_decode'):
            raw = stream_generate(generator,req,emit)
        previous = history[old['request_id']]
        return dict(raw,request=req,stages=events,online_BGE_batches=view.calls if view else 0,
            online_policy_forwards=len(p['arms'][row['arm']]) if view else 0,
            historical_reply_identical=raw['text']==previous['text'],
            historical_token_ids_identical=raw['output_token_ids']==previous['output_token_ids'])
    client = ReferenceStreamClient(service,regime_identity=p['regime_identity'],
        technical_timeout_seconds=p['regime']['client_technical_timeout_seconds'])
    records = []
    try:
        for row in p['schedule']:
            # Resource admission and durable research logging are outside the
            # measured service path; they are not production request handling.
            guard.check(own_pid=os.getpid())
            save_json_once(output/(row['slot']+'.started.json'),dict(protocol_identity=p['identity'],row=row))
            trace,raw = client.measure(row,trace_id=row['slot'])
            result = dict(schedule=row,trace=trace,raw=raw)
            save_json_once(output/(row['slot']+'.result.private.json'),result); records.append(result)
            print(json.dumps(dict(slot=row['slot'],case=row['case'],arm=row['arm'],warmup=row['warmup'],
                status=trace['status'],ttft=trace['ttft_seconds'],completion=trace['completion_seconds'])),flush=True)
            if trace['status'] != 'natural_stop': raise RuntimeError('incomplete request retained; stage stops without retry')
    finally:
        client.close()
        save_json_once(output/'COUNTERS.json',dict(counters))
    summarize(output)


def summarize(output):
    p = read(output/'PROTOCOL.json'); records = []
    for row in p['schedule']:
        path = output/(row['slot']+'.result.private.json')
        if path.exists():
            r = read(path); validate_trace(r['trace'])
            if r['schedule'] != row or r['trace']['request_identity'] != digest(row) or r['trace']['regime_identity'] != p['regime_identity']:
                raise ValueError('schedule/client trace mismatch')
            if r['trace']['server_result_identity'] != (digest(r['raw']) if r['raw'] is not None else None):
                raise ValueError('raw service result changed')
            records.append(r)
    measured = [r for r in records if not r['schedule']['warmup']]
    groups = defaultdict(list)
    for r in measured: groups[r['schedule']['case']+'/'+r['schedule']['arm']].append(r)
    stats = {}
    for key,rows in groups.items():
        complete = [r for r in rows if r['trace']['status']=='natural_stop']
        metrics = {}
        for field in ('ttft_seconds','completion_seconds'):
            values = sorted(r['trace'][field] for r in complete)
            metrics[field] = None if not values else dict(n=len(values),median=statistics.median(values),
                min=min(values),max=max(values),observed_p95=values[math.ceil(.95*len(values))-1])
        stages = defaultdict(list)
        for r in complete:
            sums = Counter()
            for e in r['raw']['stages']: sums[e['stage']] += e['seconds']
            for name,value in sums.items(): stages[name].append(value)
        stats[key] = dict(requests=len(rows),completed=len(complete),**metrics,
            median_stage_seconds={name:statistics.median(v) for name,v in stages.items()},
            input_tokens=sorted({r['raw']['input_tokens'] for r in complete}),
            output_tokens=sorted({r['raw']['output_tokens'] for r in complete}),
            historical_reply_identical=all(r['raw']['historical_reply_identical'] for r in complete),
            historical_token_ids_identical=all(r['raw']['historical_token_ids_identical'] for r in complete))
    lookup = {(r['schedule']['case'],r['schedule']['repeat'],r['schedule']['arm']):r for r in measured}
    paired = {}
    for cid in p['cases']:
        for arm in p['arms']:
            if arm == 'OFF': continue
            deltas = []
            for repeat in range(3):
                a,b = lookup.get((cid,repeat,arm)),lookup.get((cid,repeat,'OFF'))
                if a and b and a['trace']['status']==b['trace']['status']=='natural_stop':
                    deltas.append({k:a['trace'][k]-b['trace'][k] for k in ('ttft_seconds','completion_seconds')})
            paired[cid+'/'+arm] = dict(pairs=len(deltas),differences= deltas,
                median_difference={k:statistics.median(d[k] for d in deltas) for k in ('ttft_seconds','completion_seconds')} if deltas else None)
    summary = dict(status='PILOT_COMPLETE' if len(records)==len(p['schedule']) and all(r['trace']['status']=='natural_stop' for r in records) else 'PARTIAL_RETAINED',
        scheduled=len(p['schedule']),recorded=len(records),measured=len(measured),warmups=len(records)-len(measured),
        groups=stats,paired_vs_OFF=paired,counters=read(output/'COUNTERS.json') if (output/'COUNTERS.json').exists() else None,
        regime=p['regime'],regime_identity=p['regime_identity'],quality_scores_created=0,api_cost_usd=0,natural_updates=0,
        qualified_latency_training_reward=False,population_p95_established=False,
        scope='Two previously inspected train contexts; local warm single-request streaming diagnostic, no learned policy or deployment generalization.')
    save_json(output/'SUMMARY.json',summary)
    save_json(output/'OUTPUT_MANIFEST.json',{str(f.relative_to(output)):file_sha(f) for f in output.rglob('*') if f.is_file() and f.name!='OUTPUT_MANIFEST.json'})
    print(json.dumps(dict(status=summary['status'],recorded=len(records),measured=len(measured),counters=summary['counters'])),flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','run','summarize'])
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    {'prepare':prepare,'run':run,'summarize':summarize}[args.mode](args.output)
