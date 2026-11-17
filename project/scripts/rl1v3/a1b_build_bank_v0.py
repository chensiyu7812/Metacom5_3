"""Build/replay real v0 on CPU. No model inference, training or paid calls."""
from pathlib import Path
from collections import Counter,defaultdict
from dataclasses import replace
import argparse,json,time
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.bank import bank_v0 as B
from metacom_pm.rl1v3.retrieve import Reader
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import canonical_json,file_sha256,object_sha256,write_json_once,write_jsonl_once


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
    p.add_argument('--registry',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--tokenizer-model',type=Path,required=True)
    args=p.parse_args();root=args.root;out=args.out;start=time.perf_counter()
    registry=S.load(args.registry);bank=B.build(root,registry);B.save(bank,out/'bank')
    bank=B.load(out/'bank',registry,expected_version=bank.version)
    tok=NativeTokenizer(args.tokenizer_model,root/S.AUDIT)
    # Verify generic fast-tokenizer loading against 100 already measured native A0 requests.
    probe=json.loads((root/'project/outputs/pm_rl1/v3/A0/repair_1/TOKENIZER_PROBE.json').read_text())
    expected={r['prefix_id']:r for r in probe['rows']};checks=[]
    requests=root/'project/outputs/pm_rl1/v3/A0/repair_1/OFF_REQUESTS.jsonl'
    for line in requests.read_text().splitlines():
        row=json.loads(line);req=row['request'];ids=tok.tokenizer.apply_chat_template(req['messages'],tokenize=True,
            add_generation_prompt=True,enable_thinking=req['enable_thinking'])
        assert object_sha256(ids)==expected[row['prefix_id']]['input_ids_sha256']
        checks.append(dict(prefix_id=row['prefix_id'],input_tokens=len(ids),input_ids_sha256=object_sha256(ids)))
    write_json_once(out/'TOKENIZER_CHECK.json',dict(tokenizer_identity=tok.identity,files=tok.file_hashes,
        native_context_tokens=tok.native_context_tokens,original_A0_request_sha256=file_sha256(requests),
        all_100_match=len(checks)==100,rows=checks,weights_loaded=False,model_calls=0))
    prefixes=root/'project/outputs/pm_rl1/v3/B0/prefix_census.jsonl'
    rows=[json.loads(l) for l in prefixes.read_text().splitlines()]
    stats={h:dict(prefixes=0,available=0,attempts=0,success=0,failures=Counter(),token_counts=[]) for h in K.HEAD_ORDER}
    eligible_ids=set();read_ids=set();results=[];filters=Counter();filter_cache={};example=None
    for i,row in enumerate(rows):
        prefix=registry.prefix(row['owner_id'],row['session_id'],row['cut_turn'])
        assert prefix.prefix_id==row['prefix_id']
        reader=Reader(bank,prefix,tok,g_id='gemma-4-12B-it-707f0a3-tokenizer-only-not-frozen-G0',decode_id='not_run')
        cache_key=(prefix.owner_id,prefix.session_id)
        if cache_key not in filter_cache:
            counter=Counter();ids=set()
            for record in bank.records:
                reason=bank.reason(record,prefix)
                counter[reason or 'passed']+=1
                if reason is None:ids.add(record.record_id)
            filter_cache[cache_key]=(counter,ids)
        counter,ids=filter_cache[cache_key];filters.update(counter);eligible_ids.update(ids)
        successes=[]
        for head in K.HEAD_ORDER:
            s=stats[head];s['prefixes']+=1;s['attempts']+=1
            count=sum(bank.by_id[rid].head==head for rid in ids);s['available']+=count>0
            res=reader.read(head);repeated=reader.read(head)
            assert replace(res,elapsed_ms=0)==replace(repeated,elapsed_ms=0)
            report=dict(prefix_id=prefix.prefix_id,owner_id=prefix.owner_id,session_id=prefix.session_id,head=head,
                legal_candidates=count,status=res.status,bank_version=bank.version,index_version=bank.index_version,
                renderer_id=reader.renderer_id,output_sha256=object_sha256(replace(res,elapsed_ms=0)),elapsed_ms=res.elapsed_ms)
            if isinstance(res,K.ReadSuccess):
                s['success']+=1;s['token_counts'].append(res.reading.tokens);read_ids.update(res.record_ids)
                assert res.reading.tokens==tok.count(res.reading.reading_text)
                assert all(bank.reason(bank.by_id[rid],prefix) is None for rid in res.record_ids)
                report.update(record_ids=res.record_ids,reading_sha256=res.reading.sha256,tokens=res.reading.tokens,
                    actual_prompt_tokens=tok.prompt_tokens(prefix,(res.reading,)),charged_input_tokens=res.input_tokens_after)
                successes.append(res)
            else:s['failures'][res.reason+':'+res.detail]+=1;report['failure']=res.reason+':'+res.detail
            results.append(report)
        if example is None and len(successes)==4:
            actual=[]
            for head in ('MS','ME','MP','RS'):
                res=reader.read(head,acquired=tuple(r.reading for r in actual));assert isinstance(res,K.ReadSuccess);actual.append(res)
            key=reader.terminal_key(actual);trace=K.ExecutionTrace(domain_id='finite_head_v1',
                ordered_path=tuple('GET_'+r.reading.head for r in actual)+('STOP',),acquired=tuple(r.record_ids for r in actual),
                readings=tuple(r.reading for r in actual));trace.verify_key(key)
            replay=reader.replay(key);assert isinstance(replay,K.ExecutionTrace)
            example=dict(prefix=prefix,terminal_key=key,actual_trace=trace,canonical_replay=replay,
                selected_records=[bank.by_id[r.record_ids[0]] for r in actual],
                actual_prompt_tokens=tok.prompt_tokens(prefix,trace.readings),
                generator_response=None,terminal_reward=None,terminal_status='pending_generation_not_run',
                note='GETs are real; STOP identity replay only. No fabricated reply or B2 label.')
        if (i+1)%500==0:print(f'{i+1}/{len(rows)} real prefixes measured',flush=True)
    score={}
    for kind in sorted({r['old_head'] for r in bank.ledger}):
        group=[r for r in bank.ledger if r['old_head']==kind]
        score[kind]=dict(existing=len(group),source_verified=sum(r.get('source_verified',False) for r in group),
            lineage_verified=sum(r.get('lineage_verified',False) for r in group),
            mapped_into_bank=sum(bool(r['new_record_ids']) for r in group),
            distinct_bank_records=len({x for r in group for x in r['new_record_ids']}),
            ever_legal=sum(bool(set(r['new_record_ids'])&eligible_ids) for r in group),
            successfully_read=sum(bool(set(r['new_record_ids'])&read_ids) for r in group),
            migration_status=dict(Counter(r['status'] for r in group)))
    for head in stats:
        s=stats[head];tokens=s.pop('token_counts');s.update(availability_rate=s['available']/s['prefixes'],
            get_success_rate=s['success']/s['attempts'],tokens_min=min(tokens,default=None),tokens_max=max(tokens,default=None),
            distinct_eligible_records=sum(bank.by_id[rid].head==head for rid in eligible_ids),
            distinct_read_records=sum(bank.by_id[rid].head==head for rid in read_ids))
    write_jsonl_once(out/'READ_RESULTS.jsonl',results)
    write_json_once(out/'ASSET_CONVERSION_SCORECARD.json',dict(protocol='pmrl1v3-conversion-scorecard-v0.1',
        task_status='preparation_pending_C0_freeze',bank_version=bank.version,index_version=bank.index_version,
        source_version=registry.version,tokenizer_identity=tok.identity,prefixes_sha256=file_sha256(prefixes),
        heads=dict(Counter(r.head for r in bank.records)),review_status=dict(Counter(r.review_status for r in bank.records)),
        assets=score,read_metrics=stats,candidate_filter_counts=dict(filters),prefix_count=len(rows),
        row_grain_warning='RS strategies/treatments/cases are linked layers; never sum as independent methods',
        quality_claim='No recall improvement or response quality claim; no OFF comparison or generation',
        source_gate_counts=dict(Counter(r['reason'] for r in registry.rejected)),
        cpu_seconds=time.perf_counter()-start,model_calls=0,weights_loaded=False,paid_calls=0))
    if example is None:raise ValueError('no real four-head replay example')
    write_json_once(out/'REAL_REPLAY.json',example)
    print(canonical_json(stats),flush=True)

if __name__=='__main__':main()
