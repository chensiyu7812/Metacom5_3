#!/usr/bin/env python3
"""Deployable B1 all-role dense@8192 supply. CPU only; runtime inputs only.

No source CSV, answer, annotation, category, option or Direct access. Resume files
are checked against the task and supply identity. BGE is an encoder, not Generator.
"""
import argparse
from collections import Counter
from functools import lru_cache
import json
import os
from pathlib import Path
import time

from metacom_pm.need_aware.data.contracts import load_runtime, digest
from metacom_pm.need_aware.data.history import HistoryResolver
from metacom_pm.need_aware.data.personamem import write_json, sha_file
from metacom_pm.need_aware.memory.writer import MemoryWriter, StoreCache, write_for_task
from metacom_pm.need_aware.memory import reader as R
from metacom_pm.need_aware.agent.retrieval import BGEEncoder, EmbeddingCache, RetrievalSpec, OwnerIndex, query_text, BGE_QUERY_PREFIX
from metacom_pm.need_aware.agent import reply_protocol as RP
from metacom_pm.need_aware.runtime.models import NativeTokenizer, MODELS

SUPPLY = 'naa-response-b1-all8192-qwen-native-v1'
BGE = '/opt/tokkio-data0/tokkio_models/huggingface/hub/models--BAAI--bge-small-en-v1.5/snapshots/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'


def run(a):
    start=time.monotonic(); os.umask(0o077)
    root=Path(a.out); root.mkdir(parents=True,exist_ok=True)
    tasks=load_runtime(Path(a.runtime)/'tasks.jsonl')
    if any(t.options or t.task_mode!='generation' for t in tasks):
        raise ValueError('supply accepts only gold-free generation tasks')
    spec=RetrievalSpec(backend='dense',unit_filter='all')
    enc=BGEEncoder(BGE,threads=a.threads)
    tok=NativeTokenizer(MODELS['Qwen35'])
    count=lru_cache(maxsize=60000)(tok.count)
    cache=EmbeddingCache(root/'embeddings',spec.dense_model)
    reuse=[EmbeddingCache(Path(p)/'embeddings',spec.dense_model) for p in a.reuse]
    resolver=HistoryResolver(a.runtime);writer=MemoryWriter();stores={};indexes={}
    disk=StoreCache(root/'stores');stats=Counter()
    qpath=root/'query_vectors.private.json'
    qid=digest([(t.task_id,query_text(t)) for t in tasks])
    if qpath.exists():
        q=json.loads(qpath.read_text());assert q['identity']==qid
        vectors=q['vectors']
    else:
        vectors=enc.encode([BGE_QUERY_PREFIX+query_text(t) for t in tasks])
        write_json(qpath,dict(identity=qid,vectors=vectors))
    for task,qvec in zip(tasks,vectors):
        target=root/'runtime'/f'{task.task_id}.json'
        if target.exists():
            old=json.loads(target.read_text())
            assert old['task_sha256']==digest(task.to_dict()) and old['supply']==SUPPLY
            stats['resumed']+=1;continue
        ownerkey=(task.persona_group,task.source_family,task.cutoff)
        if ownerkey not in stores:
            store=write_for_task(resolver,writer,task);disk.put(store)
            vec=cache.load(store)
            for other in reuse:
                if vec is None: vec=other.load(store)
            if vec is None:
                vec,_=cache.get_or_build(store,store.units,enc);stats['encoded_owners']+=1
            else:stats['cached_owners']+=1
            stores[ownerkey]=store;indexes[ownerkey]=OwnerIndex(store,spec,unit_vectors=vec)
        store=stores[ownerkey]
        ranked=indexes[ownerkey].rank(query_text(task),query_vector=qvec)
        packed=R.pack(ranked,count,8192); evidence=R.render_raw(packed.units)
        msgs=RP.messages(task,evidence); n=len(tok.chat_ids(msgs))
        write_json(target,dict(task_id=task.task_id,task_sha256=digest(task.to_dict()),
            supply=SUPPLY,policy_sha256=RP.identity(),store_id=store.store_id,
            evidence=evidence,trace=R.trace(packed,'raw'),messages=msgs,input_tokens=n,
            evidence_records=[dict(source_id=u.unit_id,coordinates=u.coordinates,
                original_text_sha256=u.original_text_sha256,speaker=u.speaker,order=u.order,
                original_text=u.original_text) for u in packed.units]))
        stats['written']+=1
    write_json(root/'SUPPLY_DONE.json',dict(protocol=SUPPLY,tasks=len(tasks),stats=dict(stats),
        seconds=time.monotonic()-start,gpu_calls=0,generator_calls=0,
        tasks_sha256=sha_file(Path(a.runtime)/'tasks.jsonl'),
        runtime_manifest={p.name:sha_file(p) for p in sorted((root/'runtime').glob('*.json'))}))
    print(json.dumps({'tasks':len(tasks),'seconds':round(time.monotonic()-start),'stats':dict(stats)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',required=True);p.add_argument('--out',required=True)
    p.add_argument('--reuse',action='append',default=[]);p.add_argument('--threads',type=int,default=4)
    run(p.parse_args())
