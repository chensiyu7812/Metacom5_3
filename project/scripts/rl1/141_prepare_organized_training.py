#!/usr/bin/env python3
"""Concrete source-bound initial training menu and complete BGE block plan.

Local tokenizers only. Preserve the original 24-prefix initial pool, translate
its count programs into explicit head order, and add reverse orders plus one
long MS program per prefix before any new feedback. No weights/G/J/labels.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.organized_encoding import tokenizer_identity, encoder_identity
from metacom_pm.rl1.organized_features import FullTextFeatures
from metacom_pm.rl1.organized_feedback import OrganizedEpisode, TokenCost
from metacom_pm.rl1.organized_supervision import endpoint, training_menu
from metacom_pm.rl1.resource_organization import OrganizationCatalog, OrganizedItem, OrganizedRenderer
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    (out/'sources_private').mkdir(mode=0o700)
    used={}
    def read(p,expected=None):
        p=Path(p).resolve();h=sha(p)
        if expected is not None and h!=expected:raise ValueError('source changed: '+str(p))
        used[str(p)]=h;return json.loads(p.read_text())
    base=PROJECT/'outputs/pm_rl1'
    org=base/'resource_organization_20261029_v1';manifest=read(org/'OUTPUT_MANIFEST.json')
    def source(name):return read(org/name,manifest[name])
    rows=source('CATALOG_MANIFEST.json');library=source('RS_LIBRARY_PRIVATE.json')
    items={x['key']:OrganizedItem(**x) for x in library['items']}
    if digest([x.identity for x in items.values()])!=library['identity']:raise ValueError('RS source drift')
    old=read(base/'completion_preparation_20261022/bc_terminal_candidates_private.json')
    if len(old)!=336 or any(x['split']!='train' for x in old):raise ValueError('initial train pool changed')
    wanted={x['prefix_identity'] for x in old}
    if len(wanted)!=24:raise ValueError('original initial prefix count changed')
    selected=[r for r in rows if r['prefix_identity'] in wanted]
    if len(selected)!=24 or any(r['split']!='train' for r in selected):raise ValueError('train-only source coverage')
    freeze=read(base/'completion_20260930_v2/P2/executor_freeze.json',
        '7f552e714c595428f8268505762cf7cf8313e021fa971ac7ab9ec035ce234457')
    runtime=freeze['primary_runtime']
    ref=read(base/'judge_selection_preparation_20261014_v1/four_head_diagnostic_preparation_20261020_v1/protocol.json')
    evidence_path=base/'completion_20260930_v2/P3/common_evidence/evidence_pool_private.json'
    allow=read(base/'completion_preparation_20261022/SOURCE_HASHES_PRIVATE.json')
    evidence=read(evidence_path,allow[str(evidence_path.resolve())])
    from transformers import AutoTokenizer
    gt=AutoTokenizer.from_pretrained(runtime['model_dir'],local_files_only=True)
    bt=AutoTokenizer.from_pretrained(ref['bge_local_dir'],local_files_only=True)
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    if sha(Path(runtime['model_dir'])/'tokenizer.json')!=LLAMA_TOKENIZER_JSON_SHA256:raise ValueError('G tokenizer changed')
    for folder in (Path(runtime['model_dir']),Path(ref['bge_local_dir'])):
        for name in ('tokenizer.json','tokenizer_config.json','special_tokens_map.json','config.json'):read(folder/name)
    @lru_cache(maxsize=32768)
    def count(text):return len(gt.encode(text,add_special_tokens=False,truncation=False))
    @lru_cache(maxsize=32768)
    def ids(text):return tuple(bt.encode(text,add_special_tokens=False,truncation=False))
    renderer=OrganizedRenderer(count_text=count,
        count_chat=lambda ms:len(gt.apply_chat_template(ms,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256,template=gt.chat_template)),
        context_limit=runtime['policy']['context_limit'])
    tok=tokenizer_identity(bt);encoder=encoder_identity(ref['bge_binding'],ref['bge_expected_runtime'],tok)
    planner=FullTextFeatures(encode_tokens=ids,add_special_tokens=bt.build_inputs_with_special_tokens,
        native_window=8192,special_tokens=bt.num_special_tokens_to_add(pair=False),
        tokenizer_identity=tok,encoder_identity=encoder,dimension=1024)
    save_json(out/'CONFIG.json',dict(version='pmrl1-organized-initial-preparation-v1',
        status='PREPARED_DOMAIN_NOT_QUALIFIED_REWARD',initial_prefixes=sorted(wanted),
        program_rule='original measured-count menu in RS/MP/MS/ME order; reverse each mixed order; add min(6, available MS) then STOP',
        program_rule_is_environment_cap=False,cost=asdict(TokenCost(.05,2048)),
        bge_binding=ref['bge_binding'],bge_runtime=ref['bge_expected_runtime'],bge_local_dir=ref['bge_local_dir'],
        bge_tokenizer_identity=tok,encoder_identity=encoder,feature_identity=planner.identity,
        gpu_uuid=ref['approval_scope']['gpu_uuid'],runtime=runtime,draw_identity=freeze['terminal_draw_identity'],
        renderer_identity=renderer.identity,oneshot_search_budget=None,formal_comparison_frozen=False))
    ends=[];states={};blocks={};rejected=[];requests={}
    for row in selected:
        pid=row['prefix_identity'];stored=source('catalogs_private/'+pid+'.json')
        prefix=prefix_from_dict(stored['prefix']);metadata=stored['frozen_RS_metadata']
        local=[replace(v,original_rank=metadata[k][0],bge_similarity=metadata[k][1]) if k in metadata else v for k,v in items.items()]
        local += [OrganizedItem(**x) for x in stored['memory']]
        catalog=OrganizationCatalog(prefix,local,provenance_identity=stored['catalog_identity'])
        ev=evidence[pid];es=dict(prefix_identity=pid,evidence_identity=digest(ev),source_identity=sha(evidence_path))
        def factory():return OrganizedEpisode(catalog,renderer,executor_identity=runtime['identity'],
            draw_identity=freeze['terminal_draw_identity'],trajectory_id='prepared-initial',
            evidence=ev,evidence_source=es,cost=TokenCost(.05,2048))
        initial=factory().session.observe();programs={(0,)}
        for c in old:
            if c['prefix_identity']!=pid:continue
            get=tuple(a for a,n in enumerate(c['counts'],1) for _ in range(n))
            programs.add(get+(0,));programs.add(tuple(reversed(get))+(0,))
        programs.add((3,)*min(6,initial.remaining_items[2])+(0,))
        save_json(out/'sources_private'/(pid+'.json'),dict(prefix=asdict(prefix),catalog_identity=catalog.identity,
            stored_source_path=str(org/'catalogs_private'/(pid+'.json')),evidence=ev,evidence_source=es))
        for actions in sorted(programs):
            e=factory();observations=[];failure=None
            for action in actions:
                obs=e.session.observe()
                if not obs.action_mask[action]:failure='unavailable_head_or_native_capacity';break
                observations.append(obs);e.step(action)
            if failure:
                rejected.append(dict(prefix_identity=pid,actions=actions,reason=failure));continue
            x,_=endpoint(factory,actions);ends.append(x)
            for req in e.requests.values():requests[req['request_id']]=req
            for obs in observations:
                key=digest(asdict(obs))
                if key in states:continue
                plan=planner.plan(obs)
                for doc in plan['documents']:
                    for block in doc['chunks']:blocks[digest(block['input_ids'])]=block['input_ids']
                states[key]=dict(prefix_identity=pid,observation=asdict(obs),plan=plan)
        print(json.dumps(dict(completed_prefixes=len(list((out/'sources_private').glob('*.json'))),total=24)),flush=True)
    menu=training_menu(ends,source_identity=digest(dict(inputs=used,config=sha(out/'CONFIG.json'))))
    save_json(out/'MENU_PRIVATE.json',menu);save_json(out/'REQUESTS_PRIVATE.json',requests)
    save_json(out/'OBSERVATIONS_PRIVATE.json',states);save_json(out/'BLOCKS_PRIVATE.json',blocks)
    # Establish reusable OFF explicitly by complete visible input and source
    # prefix. Metadata changes remain visible in the bridge proof; no new draw.
    audit=base/'reorganization_20261029_v4';am=read(audit/'OUTPUT_MANIFEST.json')
    oldrows=read(audit/'RESPONSE_LEDGER_PRIVATE.json',am['RESPONSE_LEDGER_PRIVATE.json'])
    oldhash=read(audit/'INPUT_HASHES_PRIVATE.json',am['INPUT_HASHES_PRIVATE.json'])
    reused={};proof=[]
    for row in oldrows:
        if row['split']!='train' or row['prefix_identity'] not in wanted or any(row['counts']):continue
        oldreq=read(PROJECT/row['request_path'],oldhash[row['request_path']])
        raw=read(PROJECT/row['raw_path'],oldhash[row['raw_path']])
        matches=[r for r in requests.values() if r['provenance']['prefix_identity']==row['prefix_identity'] and not r['provenance']['selected_keys']]
        if len(matches)!=1:raise ValueError('one true OFF required')
        new=matches[0]
        if (oldreq['messages']!=new['messages'] or oldreq['executor_identity']!=new['executor_identity']
                or oldreq['draw_identity']!=new['draw_identity'] or raw['input_tokens']!=new['expected_input_tokens']
                or raw['request_id']!=oldreq['request_id'] or raw['runtime_identity']!=new['executor_identity']
                or raw['source_provenance_identity']!=digest(oldreq['provenance']) or raw['finish_reason']!='natural_stop'):
            raise ValueError('historical OFF is not exactly reusable')
        link=dict(original_request=oldreq['request_id'],original_request_path=row['request_path'],original_raw_path=row['raw_path'],
            original_raw_sha256=oldhash[row['raw_path']],new_request=new['request_id'],source_prefix=row['prefix_identity'],
            rule='same empty resources, exact messages/G/draw/token count; only request/provenance metadata rebound',new_sample=False)
        proof.append(link)
        reused[new['request_id']]=dict(raw,request_id=new['request_id'],source_provenance_identity=digest(new['provenance']),
            original_request_id=oldreq['request_id'],reuse_proof_identity=digest(link))
    save_json(out/'REUSED_OFF_PRIVATE.json',reused);save_json(out/'REUSE_PROOF_PRIVATE.json',proof)
    save_json(out/'REJECTED_PROGRAMS.json',rejected);save_json(out/'INPUT_HASHES_PRIVATE.json',used)
    summary=dict(status='INITIAL_POOL_PREPARED_PENDING_NEW_GENERATIONS_AND_QUALIFIED_FEEDBACK',train_prefixes=24,
        programs=len(ends),requests=len(requests),reused_OFF=len(reused),new_G_required=len(requests)-len(reused),
        supervised_observations=len(states),unique_BGE_blocks=len(blocks),BGE_input_tokens=sum(map(len,blocks.values())),
        maximum_block_tokens=max(map(len,blocks.values())),max_GETs=max(len(x['actions'])-1 for x in ends),
        rejected_programs=len(rejected),missing_is_zero=False,qualified_targets=0,real_BGE_blocks=0,
        natural_updates=0,API_calls=0,menu_identity=menu['identity'])
    save_json(out/'SUMMARY.json',summary)
    save_json(out/'PACKAGE_MANIFEST.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
