#!/usr/bin/env python3
"""Run the opt-in common interface on isolated train/dev catalogs, offline.

Local tokenizers only. No torch models, embeddings, G/J, optimizer, human task,
test/gold, credentials or network. Six MS reads are a fixed engineering probe,
NOT an environment horizon. Failed native capacity is reported, not truncated.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.schema import Action, digest
from metacom_pm.rl1.resource_organization import OrganizedItem, OrganizationCatalog, OrganizedRenderer
from metacom_pm.rl1.organized_policy_interface import HeadSession, commit_program, replay_program, VERSION
from metacom_pm.rl1.organized_features import FullTextFeatures


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(a):
    started = time.monotonic()
    if a.output.exists():
        raise ValueError('new output directory required')
    used = {}
    def read(p, expected=None):
        p = p.resolve(); h = sha(p)
        if expected is not None and h != expected:
            raise ValueError('source hash changed: '+str(p))
        used[str(p)] = h
        return json.loads(p.read_text())
    manifest = read(a.organization/'OUTPUT_MANIFEST.json')
    def org(name):
        if name not in manifest or Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('outside isolated source allowlist')
        return read(a.organization/name, manifest[name])
    protected = org('PROTECTED_HASHES.json')
    for p,h in protected.items():
        if sha(Path(p)) != h: raise ValueError('protected artifact changed')
    rows = org('CATALOG_MANIFEST.json')
    if len(rows) != 114 or Counter(r['split'] for r in rows) != {'train':96,'dev':18}:
        raise ValueError('train/dev scope changed')
    rs = org('RS_LIBRARY_PRIVATE.json')
    library = {x['key']:OrganizedItem(**x) for x in rs['items']}
    if digest([x.identity for x in library.values()]) != rs['identity']:
        raise ValueError('shared source library changed')
    from transformers import AutoTokenizer
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    if sha(a.g_tokenizer/'tokenizer.json') != LLAMA_TOKENIZER_JSON_SHA256:
        raise ValueError('original G tokenizer changed')
    for base in (a.g_tokenizer,a.bge_tokenizer):
        for name in ('tokenizer.json','tokenizer_config.json','special_tokens_map.json','config.json'):
            read(base/name)
    gt = AutoTokenizer.from_pretrained(a.g_tokenizer,local_files_only=True,trust_remote_code=False)
    bt = AutoTokenizer.from_pretrained(a.bge_tokenizer,local_files_only=True,trust_remote_code=False)
    native = read(a.g_tokenizer/'config.json')['max_position_embeddings']
    window = read(a.bge_tokenizer/'tokenizer_config.json')['model_max_length']
    if window != 8192 or a.bge_tokenizer.name != '9a0624b896d81da7492a910ffa53731274b6cf3d':
        raise ValueError('expected pinned BGE tokenizer native window/revision')
    @lru_cache(maxsize=32768)
    def count(text): return len(gt.encode(text,add_special_tokens=False,truncation=False))
    @lru_cache(maxsize=32768)
    def bge_ids(text): return tuple(bt.encode(text,add_special_tokens=False,truncation=False))
    renderer = OrganizedRenderer(count_text=count,
        count_chat=lambda messages:len(gt.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256,template=gt.chat_template)),context_limit=native)
    features = FullTextFeatures(encode_tokens=bge_ids,add_special_tokens=bt.build_inputs_with_special_tokens,
        native_window=window,special_tokens=bt.num_special_tokens_to_add(pair=False),
        tokenizer_identity=digest({n:sha(a.bge_tokenizer/n) for n in ('tokenizer.json','tokenizer_config.json','special_tokens_map.json')}),
        encoder_identity='original-BGE-weights-not-loaded; proposed-chunk-pooling',dimension=1024)
    def save(name,data):
        p = a.output/name; p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with p.open('x') as f:
            json.dump(data,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
        p.chmod(0o600)
    results = []
    for index,row in enumerate(rows):
        stored = org('catalogs_private/'+row['prefix_identity']+'.json')
        prefix = prefix_from_dict(stored['prefix'])
        if prefix.identity != row['prefix_identity'] or prefix.split != row['split']:
            raise ValueError('prefix identity/split changed')
        metadata = stored['frozen_RS_metadata']
        items = [replace(v,original_rank=metadata[k][0],bge_similarity=metadata[k][1]) if k in metadata else v for k,v in library.items()]
        items += [OrganizedItem(**x) for x in stored['memory']]
        catalog = OrganizationCatalog(prefix,items,provenance_identity=stored['catalog_identity'])
        seq,oneshot,hidden = HeadSession(catalog,renderer),HeadSession(catalog,renderer),HeadSession(catalog,renderer,without_text=True)
        initial = seq.observe()
        # Number selected from public inventory metadata BEFORE any GET. This
        # is a replay test, not a learned OneShot or a chosen Fixed-Dev baseline.
        n = min(6, initial.remaining_items[2])
        actions = (Action.GET_MS,)*n+(Action.STOP,)
        program = commit_program(oneshot.observe(),actions,interface_identity=oneshot.interface_identity)
        trace=[]; last=initial; last_hidden=hidden.observe(); failure=None
        for action in actions:
            before = seq.observe()
            if not before.action_mask[action]:
                failure='native_context_before_planned_GET';break
            after = seq.step(action); masked = hidden.step(action)
            if any(x.content is not None for x in masked.acquired) or after.action_mask != masked.action_mask:
                raise ValueError('NoText/physical domain mismatch')
            if not after.stopped:last,last_hidden=after,masked
            trace.append(dict(action=int(action),observation_identity=digest(asdict(after)),
                counts=after.counts,resource_tokens=after.resource_tokens,input_tokens=after.input_tokens,
                no_text_identity=digest(asdict(masked)),reward=None))
        if failure:
            results.append(dict(prefix_identity=prefix.identity,split=prefix.split,status=failure,trace=trace))
            continue
        replay_program(oneshot,program)
        terminals = [s.terminal(executor_identity='OFFLINE_ONLY_NOT_G_EXECUTION',draw_identity='not-executed') for s in (seq,oneshot,hidden)]
        if len({t['identity'] for t in terminals}) != 1:
            raise ValueError('methods differ in physical terminal for same action sequence')
        full_plan,hidden_plan=features.plan(last),features.plan(last_hidden)
        if len(hidden_plan['documents']) != 1:
            raise ValueError('NoText attempted to tokenize acquired body')
        docs=full_plan['documents']
        for d in docs:
            if sum(c['end_token']-c['start_token'] for c in d['chunks']) != len(d['payload_ids']):
                raise ValueError('token coverage mismatch')
        record=dict(index=row['index'],prefix_identity=prefix.identity,split=prefix.split,owner=prefix.owner_id,
            status='OFFLINE_REPLAY_COMPLETE',GETs=n,resource_tokens=last.resource_tokens,input_tokens=last.input_tokens,
            same_physical_terminal=True,no_text_acquired_body_tokens=0,
            visible_documents=len(docs),BGE_payload_tokens=sum(len(d['payload_ids']) for d in docs),
            BGE_chunks=sum(len(d['chunks']) for d in docs),
            documents_exceeding_native_BGE_window=sum(len(d['chunks'])>1 for d in docs),
            program_identity=program.identity,terminal_identity=terminals[0]['identity'],reward=None)
        results.append(record)
        save('traces_private/'+prefix.identity+'.json',dict(summary=record,trace=trace,program=asdict(program),
            terminal=terminals[0],full_feature_plan=full_plan,no_text_feature_plan=hidden_plan))
        if (index+1)%24 == 0:print(json.dumps(dict(completed=index+1,total=114)),flush=True)
    summary=dict(status='OFFLINE_INTERFACE_CANDIDATE_NOT_FORMAL_LEARNING',version=VERSION,
        prefixes=len(rows),split=dict(Counter(r['split'] for r in rows)),
        complete=sum(r['status']=='OFFLINE_REPLAY_COMPLETE' for r in results),
        native_capacity_failures=sum(r['status']!='OFFLINE_REPLAY_COMPLETE' for r in results),
        more_than_four_reads=sum(r.get('GETs',0)>4 for r in results),
        resource_tokens_above_2048=sum(r.get('resource_tokens',0)>2048 for r in results),
        maximum_GETs=max(r.get('GETs',0) for r in results),
        total_probe_GETs=sum(r.get('GETs',0) for r in results),
        BGE_payload_tokens=sum(r.get('BGE_payload_tokens',0) for r in results),
        BGE_chunks_planned=sum(r.get('BGE_chunks',0) for r in results),
        documents_exceeding_BGE_window=sum(r.get('documents_exceeding_native_BGE_window',0) for r in results),
        feature_dimension=features.feature_dimension,feature_identity=features.identity,
        tokenizer_only=True,weights_loaded=0,embedding_calls=0,G_calls=0,J_calls=0,training_updates=0,new_human_assignments=0,API_cost_usd='0',
        qualification=False,cost_contract=None,oneshot_definition='candidate precommitted head program; shared adaptive retriever; not formally selected',
        no_text_scope='body hidden from PM, retrieval and G unchanged; structural/token/mask information retained',
        seconds=time.monotonic()-started)
    save('SUMMARY.json',summary);save('COVERAGE_PRIVATE.json',results);save('INPUT_HASHES_PRIVATE.json',used);save('PROTECTED_HASHES.json',protected)
    code=[Path(__file__),PROJECT/'src/metacom_pm/rl1/organized_policy_interface.py',PROJECT/'src/metacom_pm/rl1/organized_features.py']
    save('CODE_HASHES.json',{str(p.resolve()):sha(p) for p in code})
    save('OUTPUT_MANIFEST.json',{str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()})
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--organization',type=Path,default=PROJECT/'outputs/pm_rl1/resource_organization_20261029_v1')
    p.add_argument('--output',type=Path,required=True)
    models=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub')
    p.add_argument('--g-tokenizer',type=Path,default=models/'models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')
    p.add_argument('--bge-tokenizer',type=Path,default=models/'models--BAAI--bge-m3/snapshots/9a0624b896d81da7492a910ffa53731274b6cf3d')
    run(p.parse_args())
