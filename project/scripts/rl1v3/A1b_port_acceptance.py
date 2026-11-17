"""CPU/native-tokenizer port evidence; no asset reconstruction or model calls."""
import argparse
import json
from collections import Counter
from pathlib import Path
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.bank.v0_port import make_port_factory
from metacom_pm.rl1v3.bank.rs_v0_catalog import load as load_catalog
from metacom_pm.rl1v3.io import canonical_json, decode_contract, file_sha256, object_sha256, write_json_once, write_jsonl_once
from metacom_pm.rl1v3.needs.sources import CensusSources, PrefixContext
from metacom_pm.rl1v3.needs.protocol import build_pack, render_messages


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--catalog',type=Path,required=True)
    args=ap.parse_args();root=args.root;out=args.out
    census=CensusSources(root/'project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json')
    factory=make_port_factory(census,root=root)
    catalog=load_catalog(args.catalog,root=root,bank=factory.bank)
    coverage=root/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl'
    rows=[json.loads(x) for x in coverage.read_text().splitlines()]
    assert len(rows)==24
    reads=[];packs=[];examples=[];failures=Counter();unique={h:set() for h in K.HEAD_ORDER}
    for row in rows:
        prefix=factory.prefix(row);port=factory(prefix)
        current,history=factory.registry.context(prefix)
        pack=build_pack(PrefixContext(prefix,current,history,row),catalog.for_needcard_writer())
        msgs=render_messages(pack)
        packs.append(dict(prefix_id=prefix.prefix_id,pack=pack,messages_sha256=object_sha256(msgs),model_called=False))
        results=[]
        for head in K.HEAD_ORDER:
            ranked=port.reader._search(head)
            x=port.read(head,input_tokens_before=port.base_tokens)
            rr=dict(prefix_id=prefix.prefix_id,head=head,candidate_count=len(ranked.ranked),result=x)
            reads.append(rr)
            if isinstance(x,K.ReadFailure):failures[x.reason+':'+x.detail]+=1;continue
            unique[head].update(x.record_ids)
            record=port.bank.by_id[x.record_ids[0]]
            assert not port.verify_records(x.record_ids)
            # Scores and source text are private audit data, never policy gains.
            examples.append(dict(prefix_id=prefix.prefix_id,owner_id=prefix.owner_id,
                session_id=prefix.session_id,head=head,current_question=prefix.turns[-1].text,
                retrieval_query='\n'.join(t.text for t in prefix.turns[-3:]),
                score=ranked.ranked[0].score,score_definition='lexical_query_word_coverage_v0_not_accuracy_or_reward',
                record_id=record.record_id,source_family=record.family_id,
                reading_text=x.reading.reading_text,source_spans=record.source_refs,quality=record.review_status))
            # Sequential state is explicitly supplied, not guessed from token count.
            prev=tuple(r.reading for r in results);before=results[-1].input_tokens_after if results else port.base_tokens
            seq=port.read(head,acquired=prev,input_tokens_before=before)
            assert isinstance(seq,K.ReadSuccess)
            results.append(seq)
        key=port.terminal_key(results);trace=port.execution_trace(results)
        replay=port.replay(key);fresh=factory(prefix).replay(key)
        assert isinstance(replay,K.ExecutionTrace) and replay==fresh
        packs[-1].update(terminal_key=key,execution_trace=trace,replay=replay,token_account=port.token_account(trace.readings))
    golden=root/'project/outputs/pm_rl1/v3/A1b_preparation/measured_v1/REAL_REPLAY.json'
    old=json.loads(golden.read_text());prefix=decode_contract(K.PrefixSpec,canonical_json(old['prefix']))
    port=factory(prefix);key=decode_contract(K.TerminalKey,canonical_json(old['terminal_key']))
    replay=port.replay(key)
    assert canonical_json(replay)==canonical_json(old['canonical_replay']), 'preserved replay changed'
    results=[]
    for action in old['actual_trace']['ordered_path'][:-1]:
        results.append(port.read(action[4:],acquired=tuple(r.reading for r in results),
                                 input_tokens_before=results[-1].input_tokens_after if results else port.base_tokens))
    assert canonical_json(port.execution_trace(results))==canonical_json(old['actual_trace'])
    assert port.terminal_key(results)==key
    write_jsonl_once(out/'READS_24.jsonl',reads)
    write_jsonl_once(out/'B1_INPUT_PACKS_24.jsonl',packs)
    write_jsonl_once(out/'RELEVANCE_POOL.jsonl',examples)
    write_json_once(out/'PORT_ACCEPTANCE.json',dict(protocol='pmrl1v3-a1b-port-acceptance-v1',
        source_version=factory.registry.version,bank_version=factory.bank.version,index_version=factory.bank.index_version,
        tokenizer=factory.tokenizer.identity,catalog_id=catalog.catalog_id,
        prefixes=len(rows),attempts=len(reads),success=sum(hasattr(r['result'],'reading') for r in reads),
        failures=dict(failures),unique_read_records={h:len(ids) for h,ids in unique.items()},
        b1_input_ready=len(packs),preserved_replay_exact_match=True,
        inputs={str(p.relative_to(root)):file_sha256(p) for p in (coverage,golden,args.catalog)},
        weights_loaded=False,model_calls=0,paid_calls=0,
        note='A port checks only; B5 coverage acceptance reported separately; GET success is not relevance accuracy'))


if __name__=='__main__':main()
