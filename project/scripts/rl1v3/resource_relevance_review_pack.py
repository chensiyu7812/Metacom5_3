"""Stratified development review package. Frozen v0 ranks; no labels fitted."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.bank.v0_port import make_port_factory
from metacom_pm.rl1v3.sources.source_registry import span
from metacom_pm.rl1v3.retrieve.v0 import search
from metacom_pm.rl1v3.io import canonical_json,object_sha256,file_sha256,write_json_once,write_jsonl_once
PROTOCOL='pmrl1v3-relevance-review-pack-1'


def build(root,out,factory=None):
    f=factory or make_port_factory(root=root)
    base=root/'project/outputs/pm_rl1/v3'
    oldpath=base/'relevance_dev_20261118/DIAGNOSTIC.jsonl'
    old=[json.loads(x) for x in oldpath.read_text().splitlines()]
    coverage=[json.loads(x) for x in (base/'B1/coverage_sample_v1.jsonl').read_text().splitlines()]
    selected={(r['prefix_id'],h):dict(prefix=r,head=h,selection='all four heads of fixed development coverage')
        for r in coverage if 1<=r['fold']<=5 for h in K.HEAD_ORDER}
    for r in old:
        selected.setdefault((r['prefix_id'],r['head']),dict(prefix=r['prefix'],head=r['head'],selection='preserved earlier boundary/development case'))
    source_checked=set();records={};rows=[];blind=[]
    for (pid,h),selection in sorted(selected.items()):
        meta=selection['prefix'];prefix=f.prefix(meta);port=f.for_prefix(prefix);ranked=search(f.bank,h,prefix)
        current=f.registry.entry(prefix.owner_id,prefix.session_id).source
        query_refs=[span(current,t.turn_index) for t in prefix.turns[-3:]]
        for s in query_refs:s.verify(current);K.verify_legal_span(s,prefix,current)
        candidates=[]
        for i,c in enumerate(ranked.ranked,1):
            r=f.bank.by_id[c.record_id]
            assert r in f.bank.candidates(h,prefix)
            if r.record_id not in source_checked:
                assert not port.verify_records((r.record_id,))
                source_checked.add(r.record_id)
            records[r.record_id]=json.loads(canonical_json(r))
            candidates.append(dict(record_id=r.record_id,rank=i,score=c.score,
                source_rank=r.source_rank,reported_at=json.loads(canonical_json(r.reported_at)),
                ready_at=json.loads(canonical_json(r.ready_at)),stage=r.stage,review_status=r.review_status))
        result=port.read(h);success=isinstance(result,K.ReadSuccess)
        assert success==bool(candidates)
        if success:assert result.record_ids==(candidates[0]['record_id'],)
        rid=result.record_ids[0] if success else None
        prior=[dict(category=r['category'],rationale_zh=r['rationale_zh'],evidence_level='developer_diagnostic_not_gold')
            for r in old if (r['prefix_id'],r['head'])==(pid,h)]
        sample_id='review:'+object_sha256(dict(protocol=PROTOCOL,prefix_id=pid,head=h,query_identity=ranked.query_identity))
        row=dict(sample_id=sample_id,protocol=PROTOCOL,prefix=meta,head=h,selection=selection['selection'],
            temporal_stratum=dict(cutoff_rank=prefix.cutoff_rank,rank_bucket=meta.get('rank_bucket','boundary'),cut_turn=prefix.cut_turn),
            query_protocol='last_three_visible_turns_v0',query_identity=ranked.query_identity,
            query_text='\n'.join(t.text for t in prefix.turns[-3:]),current_visible_turns=[dict(role=t.role,text=t.text) for t in prefix.turns],
            query_source_spans=json.loads(canonical_json(query_refs)),legal_candidate_count=len(candidates),
            legal_candidates=candidates,candidate_catalog='CANDIDATE_RECORDS.jsonl',filters_applied=ranked.filters_applied,
            reading_text=result.reading.reading_text if success else None,reading_tokens=result.reading.tokens if success else 0,
            selected_record_id=rid,source_spans=records[rid]['source_refs'] if rid else [],
            read_status='success' if success else result.reason,read_failure_detail=None if success else result.detail,
            score_definition='v0 fraction of query words in full record; no relevance calibration',
            previous_developer_annotations=prior,
            reviewer_fields=dict(reviewer=None,reviewed_at=None,topic_relevance='unreviewed',
                event_time_validity='unreviewed',need_to_read_now='unreviewed',need_to_mention_now='unreviewed',
                rs_case_applicability='unreviewed',misleading_advice_risk='unreviewed',evidence_quotes=[],reason=None),
            bank_version=f.bank.version,index_version=f.bank.index_version,source_version=f.registry.version)
        rows.append(row)
        blind.append(dict(sample_id=sample_id,head=h,current_visible_turns=row['current_visible_turns'],
            reading_text=row['reading_text'],source_spans=row['source_spans'],read_status=row['read_status'],
            reviewer_fields=row['reviewer_fields']))
    write_jsonl_once(out/'REVIEW_SAMPLES.jsonl',rows)
    write_jsonl_once(out/'CANDIDATE_RECORDS.jsonl',[records[k] for k in sorted(records)])
    write_jsonl_once(out/'BLIND_REVIEW.jsonl',sorted(blind,key=lambda r:object_sha256(['blind-review-v1',r['sample_id']])))
    summary=dict(protocol=PROTOCOL,rows=len(rows),heads=dict(Counter(r['head'] for r in rows)),
        owners=sorted({r['prefix']['owner_id'] for r in rows}),folds=sorted({r['prefix']['fold'] for r in rows}),
        cutoff_ranks=sorted({r['temporal_stratum']['cutoff_rank'] for r in rows}),
        read_status=dict(Counter(r['read_status'] for r in rows)),candidate_catalog_records=len(records),
        retained_prior_rows=len(old),retained_prior_sha256=file_sha256(oldpath),
        previous_categories=dict(Counter(r['category'] for r in old)),
        review_status='all new researcher judgments pending',independent_gold=False,recall_accuracy=None,
        ranking_changed=False,generator_calls=0,support_benefit=None,
        limitations=['development coverage frame, not prevalence sample','developer labels are not independent gold',
            'RS full train cases are unverified, not professional methods','no future or terminal outcome inputs',
            'no legal candidate is a source/filter condition, not a relevance judgment'],
        selection_input_sha256=file_sha256(base/'B1/coverage_sample_v1.jsonl'),
        v0_code_sha256=file_sha256(root/'project/src/metacom_pm/rl1v3/retrieve/v0.py'))
    write_json_once(out/'SUMMARY.json',summary);return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    print(json.dumps(build(ROOT,p.parse_args().out)))
