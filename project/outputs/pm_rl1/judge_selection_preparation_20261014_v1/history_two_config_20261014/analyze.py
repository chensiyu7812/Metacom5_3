"""Offline selection readout. Missing/unknown stays missing; never issues a freeze."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import selection as s
from prepare import csvwrite


def analyze(candidate,run_dir,out,allow_mock=False,review_path=None):
    p=s.load_plan();c=s.config_for(p,candidate)
    reqs=[r for r in p['requests'] if r['candidate']==candidate]
    records={};table=[]
    for r in reqs:
        path=run_dir/(r['request_id']+'.result.json')
        value=s.read(path) if path.exists() else None
        if value is not None:
            if value['request']!=r or (value['mode']!='live' and not allow_mock):
                raise ValueError('result configuration/draw/mode binding mismatch')
            records[r['request_id']]=value
        m=value['measurement'] if value else {}
        table.append(dict(request_id=r['request_id'],item_key=r['item_key'],phase=r['phase'],draw=r['draw'],
            status=m.get('measurement_status','not_started'),q=m.get('q'),m=m.get('m'),
            U=m.get('candidate_utility'),candidate=candidate))
    primary={t['item_key']:t for t in table if t['draw']=='primary'}
    ref=s.read(s.HERE/'human_and_historical_reference_private.json')
    comparisons=[]
    for order in sorted({r['Chen_order'] for r in ref}):
        a,b=primary[f'dev{order:02d}A'],primary[f'dev{order:02d}B']
        h=next(r for r in ref if r['Chen_order']==order)
        known=a['U'] is not None and b['U'] is not None
        direction=('A' if a['U']>b['U'] else 'B' if b['U']>a['U'] else 'tie') if known else None
        comparable=h['preference_comparable'] and known
        comparisons.append(dict(Chen_order=order,pair_id=h['pair_id'],owner=h['owner'],prefix_index=h['prefix_index'],
            kind=h['kind'],human_preference=h['human_preference'],human_comparable=h['preference_comparable'],
            candidate_preference=direction,delta_U=(a['U']-b['U']) if known else None,
            agreement=(direction==h['human_preference']) if comparable else None,
            explicit_preference=h['human_preference'] in ('A','B'),
            unknown_reason='' if known else 'missing/technical/semantic unknown; NOT a tie'))
    repeats=[]
    for t in table:
        if t['draw']!='repeat-1':continue
        base=primary[t['item_key']];known=base['U'] is not None and t['U'] is not None
        repeats.append(dict(item_key=t['item_key'],comparable=known,
            equal_U=(t['U']==base['U']) if known else None,
            severe_flip=((t['m']==1)!=(base['m']==1)) if known else None))
    risks=[]
    levels={'none_detected':0,'local':.25,'severe':1}
    for h in ref:
        t=primary[h['item_key']];known=h['human_risk_level'] in levels and t['m'] is not None
        risks.append(dict(item_key=h['item_key'],human_level=h['human_risk_level'],candidate_m=t['m'],
            comparable=known,agreement=(levels[h['human_risk_level']]==t['m']) if known else None,
            warning='comparison to one accepted human record; NOT adjudicated factual/severity gold'))
    dimensions=['actor_attribution','source_support_contradiction','citation_location','risk_severity','q_quality']
    review_counts={d:Counter() for d in dimensions}
    if review_path:
        seen=set();ids={r['request_id'] for r in reqs}
        for row in csv.DictReader(review_path.open()):
            if row['candidate']!=candidate:continue
            key=(row['request_id'],row['dimension'])
            if key in seen or key[0] not in ids or key[1] not in dimensions:
                raise ValueError('semantic review duplicate/identity mismatch')
            seen.add(key);verdict=row['verdict']
            if verdict not in ('pending','supported','error','unknown','not_applicable'):
                raise ValueError('unknown review verdict')
            if verdict!='pending':
                path=run_dir/(key[0]+'.response.json')
                if not path.exists() or row['reviewed_raw_sha256']!=s.sha(path):
                    raise ValueError('review not bound to exact raw response')
                if not row['explanation'] or not row['reviewer']:
                    raise ValueError('unsubstantiated semantic review')
                if verdict in ('supported','error') and key[1] in ('actor_attribution','source_support_contradiction','citation_location'):
                    if not row['source_ids'] or not row['exact_quote']:
                        raise ValueError('source-grounded review needs IDs and quotations')
                    item=p['items'][next(r['item_key'] for r in reqs if r['request_id']==key[0])]
                    e=item['evidence'];turns=e['current_prefix']+[t for h in e['legal_past_sessions'] for t in h['turns']]
                    texts={t['id']:t['text'] for t in turns}
                    ids=[i.strip() for i in row['source_ids'].split(';')]
                    if any(i not in texts for i in ids) or not any(row['exact_quote'] in texts[i] for i in ids):
                        raise ValueError('review quote does not occur in cited legal source')
            review_counts[key[1]][verdict]+=1
    for d in dimensions:
        review_counts[d]['pending']+=40-sum(review_counts[d].values())
    out.mkdir(parents=True,exist_ok=False)
    for name,data in [('reply_metrics.csv',table),('pair_metrics.csv',comparisons),('repeat_metrics.csv',repeats),('risk_comparisons.csv',risks)]:
        csvwrite(out/name,data)
    counts=Counter(t['status'] for t in table)
    summary=dict(plan_identity=p['identity'],configuration_identity=c['identity'],mock_allowed=allow_mock,
        scheduled=40,results_present=len(records),not_started=counts['not_started'],status_counts=dict(counts),
        technical_success=dict(numerator=sum(counts[k] for k in s.VALID),denominator=len(records)),
        numeric_coverage=dict(numerator=counts['measured_candidate'],denominator=40),
        semantic_unknown=counts['semantic_uncertainty'],
        primary_reply_slots=32,unique_human_pair_observations=16,independent_Du_observations=0,
        clear=dict(available=sum(x['explicit_preference'] and x['human_comparable'] for x in comparisons),
            compared=sum(x['explicit_preference'] and x['agreement'] is not None for x in comparisons),
            matches=sum(x['explicit_preference'] and x['agreement'] is True for x in comparisons)),
        ties=dict(available=sum(x['human_preference']=='tie' and x['human_comparable'] for x in comparisons),
            compared=sum(x['human_preference']=='tie' and x['agreement'] is not None for x in comparisons),
            matches=sum(x['human_preference']=='tie' and x['agreement'] is True for x in comparisons)),
        repeat_compared=sum(x['comparable'] for x in repeats),
        repeat_equal=sum(x['equal_U'] is True for x in repeats),
        repeat_severe_flips=sum(x['severe_flip'] is True for x in repeats),
        risk_comparable=sum(x['comparable'] for x in risks),
        remaining_manual_dimensions=['actor_attribution','source_support_contradiction','citation_location','risk_severity','q_quality'],
        semantic_review_counts={k:dict(v) for k,v in review_counts.items()},
        qualification='NOT_EVALUATED; development selection only; no sealed or independent qualification',
        winner=None,manual_source_review_required=True,
        confidence_intervals=None,ci_reason='3 owners/9 shared prefixes; synthetic variants and Du not independent; descriptive selection only')
    s.save(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate',choices=['deepseek_flash_high','gemma4_12b_bf16'],required=True)
    ap.add_argument('--run-dir',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--allow-mock',action='store_true',help='explicitly labelled plumbing demonstration; never evidence')
    ap.add_argument('--review',type=Path,help='completed copy of source-bound review CSV; pending remains unknown')
    a=ap.parse_args();analyze(a.candidate,a.run_dir,a.out,a.allow_mock,a.review)
