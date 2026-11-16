"""Offline selection readout. Missing/unknown stays missing; never issues a freeze."""
import argparse
from collections import Counter
import csv
import io
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
        tokens=(value or {}).get('token_accounting',{})
        table.append(dict(request_id=r['request_id'],item_key=r['item_key'],phase=r['phase'],draw=r['draw'],
            paired_slot=r['paired_slot'],
            status=m.get('measurement_status','not_started'),q=m.get('q'),m=m.get('m'),
            U=m.get('candidate_utility'),candidate=candidate,
            input_tokens=tokens.get('input'),thinking_tokens=tokens.get('thinking'),
            final_tokens=tokens.get('final'),total_output_tokens=tokens.get('total_output'),
            format_tokens=tokens.get('format'),elapsed_seconds=(value or {}).get('elapsed_seconds'),
            gpu_seconds=((value or {}).get('gpu_usage') or {}).get('gpu_seconds'),
            accounted_peak_usd=(value or {}).get('accounted_peak_usd'),
            reservation_retained=(value or {}).get('reservation_retained')))
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
    review_counts={d:Counter() for d in dimensions};material_errors=[]
    if review_path:
        seen=set();ids={r['request_id'] for r in reqs}
        for row in csv.DictReader(io.StringIO(review_path.read_text())):
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
                    cited_ids=[i.strip() for i in row['source_ids'].split(';')]
                    if any(i not in texts for i in cited_ids) or not any(row['exact_quote'] in texts[i] for i in cited_ids):
                        raise ValueError('review quote does not occur in cited legal source')
                if row['material_error'] not in ('0','1','unknown',''):
                    raise ValueError('material_error must be 0/1/unknown/blank')
                if verdict=='error' and row['material_error']=='1':material_errors.append(key)
            review_counts[key[1]][verdict]+=1
    for d in dimensions:
        review_counts[d]['pending']+=40-sum(review_counts[d].values())
    out.mkdir(parents=True,exist_ok=False)
    for name,data in [('reply_metrics.csv',table),('pair_metrics.csv',comparisons),('repeat_metrics.csv',repeats),('risk_comparisons.csv',risks)]:
        csvwrite(out/name,data)
    counts=Counter(t['status'] for t in table)
    equivalence=[]
    for key in ['variant_format_A','variant_format_B']:
        variant=next(t for t in table if t['item_key']==key)
        base=primary[p['items'][key]['parent_item_key']]
        known=variant['U'] is not None and base['U'] is not None
        equivalence.append(dict(item_key=key,parent_item_key=base['item_key'],comparable=known,
            equal_q=(variant['q']==base['q']) if known else None,
            equal_m=(variant['m']==base['m']) if known else None,
            equal_U=(variant['U']==base['U']) if known else None))
    csvwrite(out/'equivalence_metrics.csv',equivalence)
    usage={}
    for field in ['input_tokens','thinking_tokens','final_tokens','total_output_tokens','format_tokens',
                  'elapsed_seconds','gpu_seconds','accounted_peak_usd']:
        values=[float(t[field]) for t in table if t[field] is not None]
        usage[field]=dict(known_sum=sum(values),known_requests=len(values),
                          missing_of_started=len(records)-len(values),scheduled_denominator=40)
    summary=dict(plan_identity=p['identity'],configuration_identity=c['identity'],mock_allowed=allow_mock,
        scheduled=40,results_present=len(records),not_started=counts['not_started'],status_counts=dict(counts),
        technical_success=dict(numerator=sum(counts[k] for k in s.VALID),denominator=len(records)),
        full_coverage=len(records)==40 and sum(counts[k] for k in s.VALID)==40,
        technical_failures=sum(counts[k] for k in counts if k not in (*s.VALID,'not_started')),
        usage=usage,financial_reservations_retained=sum(t['reservation_retained'] is True for t in table),
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
        format_equivalence=equivalence,
        risk_comparable=sum(x['comparable'] for x in risks),
        remaining_manual_dimensions=['actor_attribution','source_support_contradiction','citation_location','risk_severity','q_quality'],
        semantic_review_counts={k:dict(v) for k,v in review_counts.items()},
        material_errors=material_errors,
        qualification='NOT_EVALUATED; development selection only; no sealed or independent qualification',
        winner=None,manual_source_review_required=True,
        confidence_intervals=None,ci_reason='3 owners/9 shared prefixes; synthetic variants and Du not independent; descriptive selection only')
    s.save(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary,table,comparisons


def compare_pool(run_root,out,allow_mock=False,review_path=None):
    """Paired descriptions with complete scheduled denominators; no automatic winner."""
    p=s.load_plan();out.mkdir(parents=True,exist_ok=False)
    results={c:analyze(c,run_root/c,out/c,allow_mock,review_path) for c in s.CANDIDATES}
    slot_maps={c:{t['paired_slot']:t for t in results[c][1]} for c in s.CANDIDATES}
    pair_maps={c:{t['Chen_order']:t for t in results[c][2]} for c in s.CANDIDATES}
    paired=[];summaries={}
    groups={'gemma_off_on':s.CANDIDATES[:2],'deepseek_off_on':s.CANDIDATES[2:],
            'all_four':s.CANDIDATES}
    for group,candidates in groups.items():
        numeric_slots=[];technical_slots=[];primary_slots=[]
        for slot in slot_maps[candidates[0]]:
            values=[slot_maps[c][slot] for c in candidates]
            known=all(v['U'] is not None for v in values)
            if known:numeric_slots.append(slot)
            if known and values[0]['draw']=='primary':primary_slots.append(slot)
            if all(v['status'] in s.VALID for v in values):technical_slots.append(slot)
            row=dict(group=group,paired_slot=slot,item_key=values[0]['item_key'],draw=values[0]['draw'],
                numeric_comparable=known,scheduled_configurations=len(candidates))
            for label,c in zip('ABCD' if group=='all_four' else ('AB' if group.startswith('gemma') else 'CD'),candidates):
                v=slot_maps[c][slot]
                row.update({label+'_'+k:v[k] for k in ['status','q','m','U','elapsed_seconds','total_output_tokens']})
            if len(candidates)==2:
                row['on_minus_off_U']=values[1]['U']-values[0]['U'] if known else None
            paired.append(row)
        common_pairs=[order for order in pair_maps[candidates[0]]
            if all(pair_maps[c][order]['candidate_preference'] is not None for c in candidates)]
        summaries[group]=dict(scheduled_reply_slots=40,primary_reply_slots=32,human_pairs=16,
            technical_common=len(technical_slots),numeric_common=len(numeric_slots),
            numeric_primary_common=len(primary_slots),numeric_pair_common=len(common_pairs),
            common_pair_orders=common_pairs,
            common_pair_results={c:[pair_maps[c][o] for o in common_pairs] for c in candidates},
            full_40_coverage_by_config={c:results[c][0]['full_coverage'] for c in candidates},
            warning='intersection is descriptive only; incomplete configurations are not eligible on survivor averages')
    # Column union avoids erasing the C/D identities in the pair-specific files.
    fields=list(dict.fromkeys(k for row in paired for k in row))
    csvwrite(out/'paired_configuration_metrics.csv',[{k:row.get(k) for k in fields} for row in paired])
    result=dict(plan_identity=p['identity'],mock_allowed=allow_mock,comparisons=summaries,
        configurations={c:r[0] for c,r in results.items()},winner=None,
        selection_requires='complete source-bound review of all 16 pairs plus diagnostics and predeclared rules',
        qualification='NOT_EVALUATED',independent_Du=0,unique_human_pairs=16,
        uncertainty='3 owners, 9 shared prefixes; no independence claim, no significance claim, no per-item ensemble')
    s.save(out/'pool_summary.json',result)
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate',choices=s.CANDIDATES)
    ap.add_argument('--compare-pool',action='store_true',help='paired A/B, C/D and all-four common sets; run-dir is pool root')
    ap.add_argument('--run-dir',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--allow-mock',action='store_true',help='explicitly labelled plumbing demonstration; never evidence')
    ap.add_argument('--review',type=Path,help='completed copy of source-bound review CSV; pending remains unknown')
    a=ap.parse_args()
    if a.compare_pool:
        if a.candidate:ap.error('--compare-pool cannot be combined with --candidate')
        compare_pool(a.run_dir,a.out,a.allow_mock,a.review)
    elif a.candidate:analyze(a.candidate,a.run_dir,a.out,a.allow_mock,a.review)
    else:ap.error('choose --candidate or --compare-pool')
