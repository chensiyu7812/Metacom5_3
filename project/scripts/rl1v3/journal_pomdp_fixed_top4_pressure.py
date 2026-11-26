#!/usr/bin/env python3
"""One CPU-only whole-session Top4 pressure baseline, not the SEARCH Top2 domain."""
import argparse,json
from pathlib import Path
from time import perf_counter
from collections import Counter
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
from metacom_pm.rl1v3.journal.joint_task_port import TaskTokenizer
from metacom_pm.rl1v3.journal import renderer,temporal_retrieval


def run(cpu,bundle,model,asset_manifest,out):
    cpu,bundle,out=map(Path,(cpu,bundle,out))
    if out.exists():raise FileExistsError(out)
    def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
    summary=json.loads((cpu/'CPU_SUMMARY_PUBLIC.json').read_text())
    frozen=json.loads((cpu/'POLICY_AND_RUNTIME_FREEZE.json').read_text())
    for name in ('LEGAL_POOLS.private.jsonl','TRACES.private.jsonl'):
        if file_sha256(cpu/name)!=summary['files_sha256'][name]:raise ValueError('existing CPU material changed')
    if file_sha256(bundle/'TASKS.runtime.jsonl')!=summary['task_manifest_sha256']:raise ValueError('task changed')
    pools={r['task_id']:r for r in rows(cpu/'LEGAL_POOLS.private.jsonl')}
    tasks=rows(bundle/'TASKS.runtime.jsonl');traces=rows(cpu/'TRACES.private.jsonl')
    prior={(r['task_id'],r['policy']):r for r in traces}
    tok=PromptTokenizer(NativeTokenizer(model,asset_manifest))
    if tok.identity!=frozen['tokenizer_identity']:raise ValueError('tokenizer changed')
    out.mkdir(parents=True)
    config=dict(protocol='pmrl1-j-pomdp-static-top4-pressure-v1',tokens_cap=4096,top_k=4,
        rule='same frozen Time-Lexical initial query; largest whole-session ranked prefix within cap; never skip a too-large higher-ranked session',
        operator='one retrieval plus up to four complete-session reads; macro, not the original 4 SEARCH/EXPAND primitive domain',
        snippet_delivery=False,source_pool='complete existing snapshot-verified legal pool',
        task_manifest_sha256=summary['task_manifest_sha256'],pool_sha256=summary['files_sha256']['LEGAL_POOLS.private.jsonl'],
        source_eval_accessed=False,model_calls=0,authorized=False,
        code_sha256=file_sha256(__file__),lexical_sha256=file_sha256(temporal_retrieval.__file__),
        renderer_sha256=file_sha256(renderer.__file__),tokenizer_identity=tok.identity)
    write_json_once(out/'PRECOMMITTED_CONFIG.json',config)
    results=[];requests=[]
    for task in tasks:
        start=perf_counter();records=pools[task['task_id']]['records']
        ranked,_=temporal_retrieval.lexical(records,task['query']);top=ranked[:4]
        tasktok=TaskTokenizer(tok,task['turns'],frozen['baseline_sha256'],file_sha256(renderer.__file__))
        texts={r['record_id']:'Complete parent session; reported '+r['reported_at']['date']+':\n'+r['reading_text'] for r in top}
        sizes={rid:tok.count(text) for rid,text in texts.items()}
        selected=[];charged=0
        for record in top:
            cost=sizes[record['record_id']]
            if charged+cost>4096:break
            selected.append(record);charged+=cost
        ordered=sorted(selected,key=lambda r:object_sha256([r['record_id'],'complete_parent']))
        block='\n\n'.join(texts[r['record_id']] for r in ordered)
        views=() if not block else (K.ReadingView(head='MS',view='raw',ordinal=1,reading_text=block,
            reported_at=None,tokens=tok.count(block),stage=None,expandable=False),)
        packet=tasktok.make_packet(views);payload=packet.payload()
        if charged>4096 or len(payload['input_ids'])+320>16384:raise ValueError('budget violation')
        if any(r['reading_text'] not in block for r in selected):raise ValueError('whole source missing')
        seq=prior[(task['task_id'],'SequentialRule')];fixed=prior[(task['task_id'],'FixedTopK')]
        results.append(dict(task_id=task['task_id'],source_count=len(records),selected_k=len(selected),
            full_top4_tokens=sum(sizes.values()),full_top4_fits=sum(sizes.values())<=4096,
            delivery_tokens=charged,input_tokens=len(payload['input_ids']),
            selected_session_ids=[r['parent_session_id'] for r in selected],
            selected_record_ids=[r['record_id'] for r in selected],reading_text=block,
            source_refs=[s for r in selected for s in r['source_refs']],
            retrieval_calls=1,whole_parent_reads=len(selected),same_primitive_access_cost=1+len(selected),
            macro_calls=1,initial_query_only=True,source_port_binding_sha256=pools[task['task_id']]['source_port_binding_sha256'],
            whole_cpu_seconds=perf_counter()-start,original_top2_input_tokens=fixed['canonical_input_tokens'],
            original_seq_input_tokens=seq['canonical_input_tokens'],
            original_seq_delivery_tokens=seq['delivered_tokens'],
            original_seq_accesses=seq['accesses'],formal_reward=None))
        requests.append(dict(task_id=task['task_id'],arm='FixedTop4MacroPressure',request_id='jreq:'+packet.payload_sha256,
            payload_sha256=packet.payload_sha256,input_tokens=len(payload['input_ids']),model_input=payload,
            renderer_id=packet.renderer_id,baseline_sha256=packet.baseline_sha256,model_called=False,authorized=False))
    write_jsonl_once(out/'TOP4_READS_PRIVATE.jsonl',results)
    write_jsonl_once(out/'TOP4_REQUESTS_PRIVATE.jsonl',requests)
    return finish(out)


def finish(out):
    """Public aggregation can resume from frozen CPU reads without reranking."""
    out=Path(out)
    config=json.loads((out/'PRECOMMITTED_CONFIG.json').read_text())
    results=[json.loads(x) for x in (out/'TOP4_READS_PRIVATE.jsonl').read_text().splitlines()]
    requests=[json.loads(x) for x in (out/'TOP4_REQUESTS_PRIVATE.jsonl').read_text().splitlines()]
    public=dict(config,tasks=len(results),full_top4_fits=sum(r['full_top4_fits'] for r in results),
        selected_k_counts={str(k):v for k,v in Counter(r['selected_k'] for r in results).items()},
        delivery_tokens_total=sum(r['delivery_tokens'] for r in results),
        delivery_tokens_max=max(r['delivery_tokens'] for r in results),
        input_tokens_total=sum(r['input_tokens'] for r in results),input_tokens_max=max(r['input_tokens'] for r in results),
        unique_payloads=len({r['payload_sha256'] for r in requests}),
        whole_parent_reads=sum(r['whole_parent_reads'] for r in results),
        exceeds_old_four_primitive_accesses=sum(r['same_primitive_access_cost']>4 for r in results),
        original_fixed_top2_input_total=sum(r['original_top2_input_tokens'] for r in results),
        original_seq_input_total=sum(r['original_seq_input_tokens'] for r in results),
        whole_cpu_seconds=sum(r['whole_cpu_seconds'] for r in results),
        fair_interpretation='Strong practical static comparator under the same delivery-token/context cap; not action-matched. Strong sequence claim must compare with same-domain LLM OneShot, or first freeze a new shared action domain for every policy.',
        reward=None,reporter_sha256=file_sha256(__file__),
        files_sha256={p.name:file_sha256(p) for p in out.iterdir()})
    write_json_once(out/'TOP4_PRESSURE_PUBLIC.json',public)
    return public


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('cpu','bundle','model','asset-manifest','out'):parser.add_argument('--'+key,required=True)
    print(json.dumps(run(**vars(parser.parse_args())),indent=2))
