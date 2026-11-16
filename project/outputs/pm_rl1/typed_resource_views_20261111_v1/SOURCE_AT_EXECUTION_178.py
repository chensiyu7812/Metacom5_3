#!/usr/bin/env python3
"""Bounded source-view/strategy diagnostic. Never changes the research backend."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import random
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.calibration_workflow import stamp, verify_identity
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.online_materials import load_materials, read
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.typed_resource_views import VERSION, BASIC_GUIDANCE, STRATEGIES, strategy_text, source_view

BASE = PROJECT/'outputs/pm_rl1'
TRAIN = BASE/'organized_initial_training_20261103_v2'
MODEL = Path('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3')
ARMS = ('B_basic', 'R_retrieved_RS', 'S_conditional', 'M_old_records',
        'V_source_view', 'F_full_sources', 'VS_source_and_strategy')


def ordering(value):
    return hashlib.sha256(('typed-resource-v1|'+value).encode()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj)
    return obj


def prepare(out):
    from transformers import AutoTokenizer
    if out.exists():
        raise ValueError('new output package required')
    _, catalogs, renderer = load_materials(TRAIN)
    runtime = read(BASE/'alternate_executor_probe_20261104_v1/PROTOCOL.json')['runtime']
    verify_identity(runtime)
    tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    assert digest(tok.chat_template) == runtime['chat_template_identity']
    # Admission/selection use sources only, never generated replies or feedback.
    admitted, exclusions = [], []
    for pid, catalog in sorted(catalogs.items()):
        src = read(TRAIN/'sources_private'/(pid+'.json'))
        selected = []
        for head in ('MP', 'ME'):
            hits = catalog.rank(head)
            if hits:
                selected.append(catalog.item(hits[0]['key']))
        try:
            view = source_view(catalog.prefix, selected, catalog._items.values(), src['evidence'])
        except ValueError as error:
            exclusions.append(dict(prefix=pid, reason=str(error)))
            continue
        admitted.append(dict(prefix=pid, owner=catalog.prefix.owner_id, view=view))
    chosen = []
    for owner in sorted({r['owner'] for r in admitted}, key=ordering):
        group = sorted((r for r in admitted if r['owner']==owner), key=lambda r:ordering(r['prefix']))
        chosen.append(group[0])
    chosen = chosen[:6]
    assert len(chosen)==6 and len({r['owner'] for r in chosen})==6
    out.mkdir(mode=0o700)
    selection = stamp(dict(scope='TRAIN_DEVELOPMENT_MECHANISM_PROBE_NOT_REOPENED_HELPFULNESS_GATE',
        authorization='2026-11-11 user agrees to try compact conditional strategies and structured/source-expandable memory.',
        rule='Existing 24 train prefixes. Initial prefix-only top1 MP and top1 ME where available. '
             'Require complete source/quote bindings. SHA256 typed-resource-v1|owner order; '
             'one smallest hashed prefix per owner, first six owners. No replacement after generation.',
        candidates=len(catalogs), mechanically_admitted=len(admitted), exclusions=exclusions,
        selected=[{k:r[k] for k in ('prefix','owner')} for r in chosen],
        sample_exposure='Previously inspected train development pool; not independent confirmatory data.',
        strategy_origin='Assistant-designed conditional guidelines based on existing eight family names; '
                        'not verified ESConv applicability labels, expert recommendations or new human preferences.',
        interpretation='Mechanism/feasibility comparison only. Do not score helpfulness by citation, length, '
                       'question absence, or conformity to these new instructions.',
        source_view='Every old cited span is retained within complete source turns +/- one adjacent turn. '
                    'Old normalized claims are audit-only; other source turns are explicitly omitted. '
                    'Full parents remain a separate arm. Not a lossless summary or full MP/ME rebuild.',
        decision='No promotion, new reward, broad retriever rebuild or PPO from this pilot. '
                 'No post-output prompt tuning or replacement examples. Record all failures and observations. '
                 'Only consider a later bounded utility test if a reproducible source/mechanism improvement is identified; '
                 'otherwise stop this candidate. New subjective judgments are not requested automatically.',
        planned_arms=list(ARMS), maximum_calls=42, maximum_loads=1, retries=0,
        API_cost_usd=0, new_training=False, old_human_labels_copied=False,
        latency='Single local G component timings only; not Tokkio useful-speech latency or a 3-second pass.'))
    save(out/'SELECTION_PROTOCOL.json',selection)
    save(out/'STRATEGY_CANDIDATES.json',dict(version=VERSION, basic=BASIC_GUIDANCE,
        strategies=list(STRATEGIES), provenance=selection['strategy_origin']))
    inputs, cards, requests, views = {}, [], {}, []
    source_paths = [TRAIN/'PACKAGE_MANIFEST.json', TRAIN/'INPUT_HASHES_PRIVATE.json', TRAIN/'CONFIG.json',
                    BASE/'alternate_executor_probe_20261104_v1/PROTOCOL.json']
    sources = dict(read(TRAIN/'INPUT_HASHES_PRIVATE.json'))
    for case_index, row in enumerate(chosen, 1):
        pid=row['prefix']; catalog=catalogs[pid]; view=row['view']; case=f'T{case_index:02}'
        source_path=TRAIN/'sources_private'/(pid+'.json'); source_paths.append(source_path)
        views.append(dict(case=case,prefix=pid,owner=row['owner'],**view))
        base=renderer.messages(catalog, ())
        base[0]['content']+='\n\n'+BASIC_GUIDANCE
        rs=catalog.item(catalog.rank('RS')[0]['key'])
        for arm in ARMS:
            ms=deepcopy(base); keys=[]; payload=None
            if arm=='R_retrieved_RS':
                ms[0]['content']+='\n\n'+renderer.block(catalog,[rs.key]); keys=[rs.key]
            elif arm=='M_old_records':
                keys=view['selected_keys'];ms[0]['content']+='\n\n'+renderer.block(catalog,keys)
            elif arm in ('V_source_view','VS_source_and_strategy','F_full_sources'):
                payload=view['full' if arm=='F_full_sources' else 'compact']
                keys=view['parent_keys'] if arm=='F_full_sources' else view['selected_keys']
                ms[0]['content']+='\n\n<source_evidence>\n'+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n</source_evidence>'
            if arm in ('S_conditional','VS_source_and_strategy'):
                ms[0]['content']+='\n\n'+strategy_text()
            native=tok.apply_chat_template(ms,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
            assert 0<len(native)<runtime['policy']['context_limit']
            identity=digest(dict(messages=ms,runtime=runtime['identity']))
            req=stamp(dict(input_identity=identity,messages=ms,messages_identity=digest(ms),
                selected_keys=keys,selected_resource_identities=[catalog.item(k).identity for k in keys],
                runtime_identity=runtime['identity'],input_tokens=len(native),token_ids_identity=digest(native)))
            if identity in requests:
                assert requests[identity]['messages']==ms
            else:
                requests[identity]=req
            inputs[identity]=dict(messages=ms,source_payload=payload,prefix=pid,selected_keys=keys)
            cards.append(dict(case=case,owner=row['owner'],prefix=pid,arm=arm,input_identity=identity,
                input_tokens=len(native),quality=None,reward=None))
    assert len(cards)==42 and len(requests)<=42
    for name,obj in [('VIEWS_PRIVATE.json',views),('INPUTS_PRIVATE.json',inputs),('CARDS_PRIVATE.json',cards)]:
        save(out/name,obj);source_paths.append(out/name)
    for name in ('SELECTION_PROTOCOL.json','STRATEGY_CANDIDATES.json'):
        source_paths.append(out/name)
    sources.update({str(p.resolve()):sha(p) for p in source_paths})
    code=[Path(__file__),PROJECT/'src/metacom_pm/rl1/typed_resource_views.py',
          PROJECT/'src/metacom_pm/rl1/online_materials.py',PROJECT/'src/metacom_pm/rl1/resource_value_probe.py',
          PROJECT/'src/metacom_pm/rl1/resource_organization.py',PROJECT/'scripts/rl1/167_probe_alternate_executor.py',
          PROJECT/'scripts/rl1/172_resume_slight_path_preload.py',PROJECT/'src/metacom_pm/rl1/generation.py',
          PROJECT/'src/metacom_pm/rl1/local_gpu_guard.py',PROJECT/'src/metacom_pm/rl1/durable.py']
    reqs=list(requests.values());random.Random(20261111).shuffle(reqs)
    protocol=stamp(dict(scope=VERSION,runtime=runtime,sources=sources,
        code={str(p.resolve()):sha(p) for p in code},requests_identity=digest(reqs),
        gpu_uuid='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4',
        max_calls=len(reqs),max_loads=1,automatic_retries=0,stage_seconds=1800,api_cost_usd=0,
        admission='Existing ScopedIdleCheck <=5%, >=45000MiB, no other processes; no device fallback.',
        authorization=selection['authorization'],new_rewards=False,new_training=False,promote=False))
    dest=out/'alternate_G';dest.mkdir(mode=0o700)
    save(dest/'PROTOCOL.json',protocol);save(dest/'REQUESTS_PRIVATE.json',reqs)
    save(out/'PREPARATION_MANIFEST.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    print(json.dumps(dict(status='PREPARED',contexts=6,owners=6,cards=42,requests=len(reqs),
        excluded_source_bindings=len(exclusions),max_native_tokens=max(r['input_tokens'] for r in reqs)),ensure_ascii=False))


def run(out):
    runner=module('typed_runner',PROJECT/'scripts/rl1/167_probe_alternate_executor.py')
    guard=module('typed_guard',PROJECT/'scripts/rl1/172_resume_slight_path_preload.py')
    runner.LocalGPUCheck=guard.ScopedIdleCheck
    runner.run(out/'alternate_G')


def collect(out):
    protocol=read(out/'alternate_G/PROTOCOL.json');verify_identity(protocol)
    requests=read(out/'alternate_G/REQUESTS_PRIVATE.json')
    assert digest(requests)==protocol['requests_identity']
    lookup={r['input_identity']:r for r in requests};results=[]
    for card in read(out/'CARDS_PRIVATE.json'):
        req=lookup[card['input_identity']];path=out/'alternate_G/raw'/(req['identity']+'.json')
        raw=read(path) if path.exists() else None
        if raw:
            assert raw['request_identity']==req['identity'] and raw['text_identity']==digest(raw['text'])
        results.append(dict(**card,raw=raw,valid=bool(raw and raw['finish_reason']=='natural_stop'
            and raw['completed_assistant_turn']),quality=None,reward=None))
    save(out/'RESULTS_PRIVATE.json',results)
    # Inspection page only, no questionnaire and no automatic quality score.
    inputs=read(out/'INPUTS_PRIVATE.json')
    parts=['<!doctype html><meta charset="utf-8"><title>资源组织候选对照</title>',
        '<style>body{max-width:1100px;margin:30px auto;font:17px/1.6 sans-serif}pre{white-space:pre-wrap}article{border-top:1px solid #aaa;padding:15px}details{background:#f5f5f5;padding:8px}</style>',
        '<h1>资源组织候选：开发浏览页</h1><p>这不是新问卷。条件公开，供检查来源和机制；没有人评分数或收益结论。英文回复为真实原文。</p>']
    for r in results:
        inp=inputs[r['input_identity']];raw=r['raw']
        parts.append('<article><h2>'+html.escape(r['case']+' · '+r['arm'])+'</h2><p>输入tokens: '+str(r['input_tokens'])+'</p><pre>'+html.escape(raw['text'] if raw else 'PENDING')+'</pre><details><summary>完整实际输入</summary><pre>'+html.escape(json.dumps(inp['messages'],ensure_ascii=False,indent=2))+'</pre></details></article>')
    with (out/'REVIEW_ZH.html').open('x') as f:f.write('\n'.join(parts))
    summary=dict(contexts=6,logical_conditions=len(results),unique_requests=len(requests),
        natural_conditions=sum(r['valid'] for r in results),
        input_tokens_by_arm={a:[r['input_tokens'] for r in results if r['arm']==a] for a in ARMS},
        component_seconds=sum(read(p)['generation_seconds'] for p in (out/'alternate_G/raw').glob('*.json') if not p.name.endswith('.started.json')),
        quality_measured=False,new_human_questions=0,rewards=0,training=0,API_cost_usd=0)
    save(out/'SUMMARY.json',summary);print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','run','collect'])
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    globals()[args.mode](args.output.resolve())
