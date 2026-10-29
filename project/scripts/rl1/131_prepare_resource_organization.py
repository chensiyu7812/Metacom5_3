#!/usr/bin/env python3
"""Build addressable four-head catalogs and a no-inference capacity comparison.

Only isolated, hash-checked inputs from audit 130 are allowed. No mixed corpus,
test/gold, provider, embedding, inference, training or new human labels.
"""
import argparse
from collections import Counter,defaultdict
from dataclasses import asdict,replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.schema import EpisodeSpec,Resource,HEADS,PLANS,digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.representation import attributed_resource,VERSION as DELIVERY_VERSION
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.resource_organization import (
    VERSION,RANKING,OrganizedItem,existing_item,OrganizationCatalog,OrganizedRenderer,OrganizationSession,
)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with path.open('x') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
    path.chmod(0o600)


def run(audit,output,tokenizer_dir):
    started=time.monotonic()
    manifest=json.loads((audit/'OUTPUT_MANIFEST.json').read_text())
    old_inputs=json.loads((audit/'INPUT_HASHES_PRIVATE.json').read_text())
    used={}
    def checked(base,name,expected):
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('relative allowlisted path required')
        if name not in expected:raise ValueError('input not in frozen audit manifest')
        p=base/name
        if sha(p)!=expected[name]:raise ValueError('input hash changed: '+name)
        used[str(p)]=expected[name]
        if p.suffix=='.jsonl':return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
        return json.loads(p.read_text())
    def old(name):return checked(PROJECT,name,old_inputs)
    def prior(name):return checked(audit,name,manifest)
    protected=prior('PROTECTED_HASHES.json')
    for p,h in protected.items():
        if sha(Path(p))!=h:raise ValueError('protected file changed')
    raw_specs=old('outputs/pm_rl1/completion_20260930_v2/P1/episode_specs_private.json')
    specs=[EpisodeSpec(**dict(s,prefix=prefix_from_dict(s['prefix']),inventory=tuple(
        tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in head) for head in s['inventory']))) for s in raw_specs]
    if len(specs)!=114 or any(s.prefix.split not in ('train','dev') for s in specs):raise ValueError('train/dev scope changed')
    candidate_rows=prior('CANDIDATE_LEDGER_PRIVATE.json')
    rowmap={(r['prefix_identity'],r['candidate_id']):r for r in candidate_rows}
    capacities=prior('CAPACITY_PRIVATE.json')
    response_prefixes={r['prefix_identity'] for r in prior('RESPONSE_LEDGER_PRIVATE.json')}
    aliases=old('data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl')
    splits={r['dialogue_id']:r for r in old('data/strategy/esconv_split_manifest_v1_5.jsonl')}
    from transformers import AutoTokenizer
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    if sha(tokenizer_dir/'tokenizer.json')!=LLAMA_TOKENIZER_JSON_SHA256:raise ValueError('tokenizer changed')
    tok=AutoTokenizer.from_pretrained(tokenizer_dir,local_files_only=True,trust_remote_code=False)
    @lru_cache(maxsize=32768)
    def count(text):return len(tok.encode(text,add_special_tokens=False))
    def chat(messages):return len(tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True))
    config=json.loads((tokenizer_dir/'config.json').read_text())
    args=dict(count_text=count,count_chat=chat,tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256,template=tok.chat_template)),
              context_limit=config['max_position_embeddings'])
    old_renderer=DirectReplyRenderer(**args);new_renderer=OrganizedRenderer(**args)
    freeze=old('outputs/pm_rl1/completion_20260930_v2/P1/interface_repair_v3/renderer_freeze.json')
    if old_renderer.identity!=freeze['new_renderer_identity']:raise ValueError('old renderer identity changed')
    rs=[];family_map=defaultdict(list)
    for a in aliases:
        if hashlib.sha256(a['rendered_card_text'].encode()).hexdigest()!=a['rendered_card_text_sha256']:raise ValueError('RS text changed')
        if any(splits[s]['split']!='train' or splits[s]['excluded_for_evoemo_overlap'] for s in a['source_dialogue_ids']):raise ValueError('RS source split violation')
        # Reuse existing atomic delivery. The temporary zero is NOT a BGE result;
        # the published organization record explicitly has bge_similarity=None.
        r=attributed_resource(Resource(a['treatment_id'],'RS',a['rendered_card_text'],0.,0,None,None,None,'na',tuple(a['source_dialogue_ids'])),count_text=count)
        x=replace(existing_item(r,families=a['atomic_move_families'],source_check='canonical_train_alias_manifest'),bge_similarity=None)
        rs.append(x)
        for family in a['atomic_move_families']:family_map[family].append(x.key)
    library_identity=digest([x.identity for x in rs])
    save(output/'RS_LIBRARY_PRIVATE.json',dict(identity=library_identity,items=[asdict(x) for x in rs],
        families=dict(family_map),applicability_conditions=None,fit_labels=None,shared_not_copied_per_prefix=True))
    print(json.dumps(dict(stage='RS_library',items=len(rs),families=len(family_map))),flush=True)
    catalog_rows=[];ablation=[];traces=[]
    for i,spec in enumerate(specs):
        p=spec.prefix
        ledger=prior('ledgers_private/'+p.identity+'.json')
        if ledger['identity']!=digest({k:v for k,v in ledger.items() if k!='identity'}) or ledger['prefix_identity']!=p.identity:
            raise ValueError('side index identity mismatch')
        memory=[existing_item(r,rank=rank,source_check=rowmap[(p.identity,r.candidate_id)]['source_check'])
                for h,items in zip(HEADS,spec.inventory) if h!='RS' for rank,r in enumerate(items,1)]
        existing_sessions={sid for r in memory if r.head=='MS' for sid in r.source_ids}
        added=[]
        for session in ledger['session_directory']:
            sid=session['session_id']
            if sid in existing_sessions:continue
            turns=[ledger['source_turns'][k] for k in session['source_keys']]
            if any(t['owner_id']!=p.owner_id or t['session_id']!=sid or t['session_rank']>=p.cutoff_rank or t['reported_at']>p.timestamp for t in turns):
                raise ValueError('illegal source directory')
            text='\n'.join(t['speaker']+': '+t['text'] for t in turns)
            body=dict(schema=DELIVERY_VERSION,kind='MS',reported_at=session['reported_at'],
                      speaker_scope='Historical seeker and supporter; neither role supplies an AI biography.',full_source_conversation=text)
            content=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            added.append(OrganizedItem('org-ms-'+digest(dict(owner=p.owner_id,session=sid)),'MS',content,text,
                digest([t['identity'] for t in turns]),p.owner_id,session['session_rank'],session['reported_at'],(sid,),
                source_check='full_session_from_frozen_legal_evidence_not_new_raw_corpus_read'))
        memory.extend(added)
        old_rs={r.candidate_id:(rank,r.similarity) for rank,r in enumerate(spec.inventory[0],1)}
        contextual_rs=[replace(x,original_rank=old_rs[x.key][0],bge_similarity=old_rs[x.key][1]) if x.key in old_rs else x for x in rs]
        cat=OrganizationCatalog(p,(*contextual_rs,*memory),provenance_identity=digest(dict(ledger=ledger['identity'],shared_rs=library_identity,frozen_spec=spec.identity)))
        # Export shared RS once. Per-prefix graph contains memory sources only.
        directory=OrganizationCatalog(p,memory,provenance_identity=ledger['identity']).directory()
        directory.update(identity=cat.identity,shared_RS_library_identity=library_identity,RS_families={'reference':'../RS_LIBRARY_PRIVATE.json'})
        save(output/'catalogs_private'/(p.identity+'.json'),dict(prefix=asdict(p),catalog_identity=cat.identity,
            library_identity=library_identity,frozen_RS_metadata=old_rs,memory=[asdict(x) for x in memory],directory=directory))
        catalog_rows.append(dict(index=i,prefix_identity=p.identity,split=p.split,owner=p.owner_id,
            identity=cat.identity,by_head={h:len(rs) if h=='RS' else sum(x.head==h for x in memory) for h in HEADS},
            additional_complete_MS=len(added),MP_ME_scope='frozen_target_views_only_not_full_compiler_rebuild',
            historical_source_coverage='complete_frozen_evidence' if p.identity in response_prefixes else 'partial_known_source_bank'))
        # Hold old rendering and old <=4-count domain fixed: isolate constraints.
        native_reachable=set()
        native_plans=[]
        for plan,prev in zip(PLANS,capacities[i]['plans']):
            if tuple(prev['counts'])!=plan:raise ValueError('plan order mismatch')
            fit=prev['inventory_available'] and chat(old_renderer.messages(spec,plan))<old_renderer.context_limit
            can=fit and (not any(plan) or any(tuple(n-(j==k) for j,n in enumerate(plan)) in native_reachable for k in range(4) if plan[k]))
            if can:native_reachable.add(plan)
            native_plans.append(dict(counts=plan,reachable=bool(can)))
        for h,items in enumerate(spec.inventory):
            for rank,r in enumerate(items,1):
                old_row=rowmap[(p.identity,r.candidate_id)]
                isolated=replace(spec,inventory=tuple((r,) if j==h else () for j in range(4)))
                one=tuple(int(j==h) for j in range(4))
                native_one=chat(old_renderer.messages(isolated,one))<old_renderer.context_limit
                ablation.append(dict(index=i,prefix_identity=p.identity,head=r.head,key=r.candidate_id,rank=rank,
                    original_rank_prefix_2048=old_row['reachable_in_any_plan'],
                    rank_prefix_native_only=any(c[h]>=rank for c in native_reachable),
                    addressable_2048=bool(native_one and old_row['hypothetical_isolated_tokens']<=2048),
                    addressable_native_only=bool(native_one),
                    isolated_tokens=old_row['hypothetical_isolated_tokens'],prefix_tokens=old_row['prefix_resource_tokens'],
                    reward=None,quality_gain='unverified',renderer_identity=old_renderer.identity))
        session=OrganizationSession(cat,new_renderer)
        first='MP' if any(x.head=='MP' for x in memory) else 'ME'
        if any(x.head==first for x in memory):
            before=cat.rank('RS')[0]
            session.get(first)
            after=cat.rank('RS',tuple(session.receipt()['acquired']))[0]
            session.get('RS');session.stop()
            traces.append(dict(index=i,kind='fixed_head_offline_retrieval_trace_not_PM_or_G',
                before_RS=before,after_RS=after,changed_next_RS=before['key']!=after['key'],receipt=session.receipt()))
        if i%24==0:print(json.dumps(dict(stage='catalogs',completed=i+1)),flush=True)
    summary=dict(status='OFFLINE_ORGANIZATION_PROTOTYPE_NOT_PROMOTED',baseline_audit=str(audit),
        version=VERSION,ranking_method=RANKING,prefixes=len(catalog_rows),
        owners={split:len({r['owner'] for r in catalog_rows if r['split']==split}) for split in ('train','dev')},
        shared_RS_items=len(rs),RS_family_count=len(family_map),
        memory_occurrences={h:sum(r['by_head'][h] for r in catalog_rows) for h in ('MP','MS','ME')},
        additional_complete_MS_occurrences=sum(r['additional_complete_MS'] for r in catalog_rows),
        frozen_candidate_constraint_ablation={h:{k:sum(r[k] for r in ablation if r['head']==h) for k in (
            'original_rank_prefix_2048','rank_prefix_native_only','addressable_2048','addressable_native_only')}
            for h in HEADS},
        fixed_head_traces=len(traces),next_RS_changed_after_legal_read=sum(t['changed_next_RS'] for t in traces),
        next_RS_change_is_not_quality_or_learning_evidence=True,
        native_context_limit=old_renderer.context_limit,artificial_resource_token_cap=None,max_GETs=None,topk_cap=None,
        content_truncation=False,new_model_loads=0,new_model_calls=0,training_updates=0,new_human_tasks=0,
        new_semantic_summary_or_relation_or_fit_labels=0,formal_environment_changed=False,
        token_cost_and_elapsed_time_recorded=True,elapsed_seconds=time.monotonic()-started,
        limitations=['Lexical retrieval is a deterministic engineering baseline, not evidence of better relevance.',
            'MP/ME remain frozen target-time views; missing raw source checks are not repaired by reindexing.',
            'Additional MS comes from the existing isolated source bank; not full corpus coverage for all prefixes.',
            'No new qualified feedback, generator response, human preference or policy update.',
            'Changing rank and reachable items invalidates the old 70-plan feature/baseline contract for a new formal study.',
            'Removing the hard cap does not make resources free; revised reward/latency accounting must be frozen before learning.'])
    for name,value in [('PROFILE.json',summary),('CATALOG_MANIFEST.json',catalog_rows),('CONSTRAINT_ABLATION_PRIVATE.json',ablation),('RETRIEVAL_TRACES_PRIVATE.json',traces),('INPUT_HASHES_PRIVATE.json',used)]:save(output/name,value)
    for p,h in used.items():
        if sha(Path(p))!=h:raise ValueError('input modified during run')
    for p,h in protected.items():
        if sha(Path(p))!=h:raise ValueError('protected file modified')
    save(output/'PROTECTED_HASHES.json',protected)
    code=[Path(__file__),PROJECT/'src/metacom_pm/rl1/resource_organization.py']
    save(output/'SOURCE_CODE_HASHES.json',{str(p.relative_to(PROJECT)):sha(p) for p in code})
    save(output/'OUTPUT_MANIFEST.json',{str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*.json'))})
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,default=PROJECT/'outputs/pm_rl1/reorganization_20261029_v4')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tokenizer-dir',type=Path,required=True)
    a=parser.parse_args()
    if a.output.exists():raise SystemExit('New output directory required')
    a.output.mkdir(parents=True,mode=0o700)
    try:result=run(a.audit,a.output,a.tokenizer_dir)
    except Exception as e:
        save(a.output/'FAILURE.json',dict(status='FAILED_CLOSED',type=type(e).__name__,message=str(e),model_calls=0))
        raise
    print(json.dumps(result,ensure_ascii=False))
