"""Fixed development spotcheck, not Recall@k gold or resource-effect evidence."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.bank.v0_port import make_port_factory
from metacom_pm.rl1v3.sources.source_registry import span
from metacom_pm.rl1v3.retrieve.v0 import search
from metacom_pm.rl1v3.io import canonical_json,file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3 import contracts as K


def run(out):
    f=make_port_factory(root=ROOT)
    selections=json.loads((ROOT/'project/configs/rl1v3/relevance_dev_g0e.json').read_text())
    census={r['prefix_id']:r for r in map(json.loads,(ROOT/'project/outputs/pm_rl1/v3/B0/prefix_census.jsonl').read_text().splitlines())}
    rows=[]
    for selection in selections:
        row=selection['prefix'];assert 1<=row['fold']<=5
        p=f.prefix(row);port=f.for_prefix(p);head=selection['head'];result=search(f.bank,head,p)
        current=f.registry.entry(p.owner_id,p.session_id).source
        query_spans=[span(current,t.turn_index) for t in p.turns[-3:]]
        for s in query_spans:s.verify(current);K.verify_legal_span(s,p,current)
        read=port.read(head);got=isinstance(read,K.ReadSuccess)
        if selection['category']=='no_legal_past_source':
            assert not port.legal_sessions() and not result.ranked and not got
        else:assert got and not port.verify_records(read.record_ids)
        record=f.bank.by_id[result.ranked[0].record_id] if got else None
        rows.append(dict(**selection,fold=row['fold'],query_protocol='last_three_visible_turns_v0',
            query_identity=result.query_identity,query_text='\n'.join(t.text for t in p.turns[-3:]),
            query_spans=json.loads(canonical_json(query_spans)),legal_candidates=len(result.ranked),
            score=result.ranked[0].score if got else None,
            score_definition='fraction_of_query_words_in_full_reading; not calibrated relevance or reward',
            record_id=record.record_id if record else None,source_family=record.family_id if record else None,
            source_spans=json.loads(canonical_json(record.source_refs)) if record else [],
            reading_text=read.reading.reading_text if got else None,
            read_status='success' if got else read.reason,
            quality=record.review_status if record else None,
            source_version=f.registry.version,bank_version=f.bank.version,index_version=f.bank.index_version,
            annotations='WS-A development inspection; not human gold; misuse is a risk, not observed generation',
            model_called=False))
    write_jsonl_once(out/'DIAGNOSTIC.jsonl',rows)
    write_json_once(out/'SUMMARY.json',dict(protocol='pmrl1v3-relevance-dev-1',rows=len(rows),
        heads=dict(Counter(r['head'] for r in rows)),categories=dict(Counter(r['category'] for r in rows)),
        source_spans=sum(len(r['source_spans']) for r in rows),query_spans=sum(len(r['query_spans']) for r in rows),
        all_development_folds=True,read_success=sum(r['read_status']=='success' for r in rows),
        limitations=['purposive sample; no population estimate','no recall gold','no generator or support benefit evidence',
            'no ranking change or threshold fit','historical self-reports unverified; no graph propagation'],
        selection_sha256=file_sha256(ROOT/'project/configs/rl1v3/relevance_dev_g0e.json')))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out)
