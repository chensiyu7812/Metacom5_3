#!/usr/bin/env python3
"""Recompute strict measurement diagnostics; never impute failed/missing scores."""
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.evidence import evidence_turns
from metacom_pm.rl1.judge import parse_measurement
from metacom_pm.rl1.schema import digest
OUT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'


def save(name,obj):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


def stats(values):
    if not values:return dict(n=0)
    ordered=sorted(values)
    return dict(n=len(values),min=min(values),median=statistics.median(values),mean=statistics.mean(values),
        p95=ordered[min(len(ordered)-1,int(.95*len(ordered)))],max=max(values))


def main():
    ptr=json.loads((OUT/'judge_pointer.json').read_text());run=Path(ptr['run_dir'])
    assert sha256_file(run/'summary.json')==ptr['summary_sha256']
    summary=json.loads((run/'summary.json').read_text())
    exam=json.loads((OUT/'exam_private.json').read_text());jobs={j['job_id']:j for j in exam['jobs']}
    assert len(jobs)==len(summary['rows'])==55
    rows=summary['rows'];by={};failures=[];details=[]
    for r in rows:
        j=jobs[r['job_id']]
        raw=json.loads((run/(r['request_id']+'.raw.json')).read_text())
        old=json.loads((run/(r['request_id']+'.measurement.json')).read_text())
        parsed=parse_measurement(raw['text'],evidence=j['evidence'],reply=j['reply'],
            runtime_identity=ptr['runtime_identity'],draw_id=j['draw_id'],finish_reason=raw['finish_reason'])
        assert parsed==old
        by[(r['pilot_index'],r['condition'],r['repeat'])]=r
        details.append(dict(pilot_index=r['pilot_index'],condition=r['condition'],repeat=r['repeat'],
            reply=j['reply'],measurement=parsed,raw_path=str(run/(r['request_id']+'.raw.json'))))
        if parsed['q'] is None:
            entry=dict(pilot_index=r['pilot_index'],condition=r['condition'],repeat=r['repeat'],
                status=parsed['measurement_status'],error=parsed.get('error'),quotes_not_exact=[])
            # Diagnostic only: don't mutate a quote, assign a score, infer a missing citation,
            # or fix malformed JSON. Distinguish typography from substantive mismatch.
            text=raw['text'].split('</think>')[-1].strip()
            if text.startswith('```json') and text.endswith('```'):text=text[7:-3].strip()
            try:
                obj=json.loads(text);turns=evidence_turns(j['evidence'])
                chunks=[obj.get('q_rationale',{})]+obj.get('claims',[])
                for k,chunk in enumerate(chunks):
                    quote=chunk.get('response_quote','')
                    if quote and quote not in j['reply']:
                        entry['quotes_not_exact'].append(dict(location='reply',part=k,quote=quote,original=j['reply']))
                    for ref in chunk.get('evidence',[]):
                        original=turns.get(ref.get('source_id'),{}).get('text','')
                        if not ref.get('quote') or ref['quote'] not in original:
                            entry['quotes_not_exact'].append(dict(location=ref.get('source_id'),part=k,quote=ref.get('quote'),original=original))
            except (ValueError,TypeError,KeyError):pass
            failures.append(entry)
    def difference(i,left,right,repeat=0):
        a=by.get((i,left,0));b=by.get((i,right,repeat))
        if not a or not b or a['q'] is None or b['q'] is None:return None
        return dict(pilot_index=i,left=left,right=right,delta_q=b['q']-a['q'],delta_m=b['m']-a['m'],
            delta_utility=(b['q']-a['q'])/4-(b['m']-a['m']),q_left=a['q'],q_right=b['q'],m_left=a['m'],m_right=b['m'])
    comparison={}
    for name,right in [('natural_OFF_ON','ON'),('damage_from_OFF','damage'),('style_from_OFF','style')]:
        valid=[d for i in range(1,13) if (d:=difference(i,'OFF',right)) is not None]
        planned=sum((i,right,0) in by for i in range(1,13))
        comparison[name]=dict(available_pairs_before_measurement=planned,valid_pairs=len(valid),missing_pairs=planned-len(valid),rows=valid,
            delta_q_counts=dict(Counter(d['delta_q'] for d in valid)),delta_m_counts=dict(Counter(d['delta_m'] for d in valid)))
    repeats=[];repeat_selected=[r for r in rows if r['repeat']==1]
    for r in repeat_selected:
        d=difference(r['pilot_index'],r['condition'],r['condition'],1)
        if d is not None:repeats.append(d)
    distribution={c:dict(total=sum(r['condition']==c and r['repeat']==0 for r in rows),
        status_counts=dict(Counter(r['measurement_status'] for r in rows if r['condition']==c and r['repeat']==0)),
        q_counts=dict(Counter(r['q'] for r in rows if r['condition']==c and r['repeat']==0 and r['q'] is not None)),
        m_counts=dict(Counter(r['m'] for r in rows if r['condition']==c and r['repeat']==0 and r['m'] is not None))) for c in ['OFF','ON','damage','style']}
    damage=[r for r in rows if r['condition']=='damage' and r['repeat']==0]
    damage_measured=[r for r in damage if r['q'] is not None]
    target_hits=[]
    control_data=json.loads((OUT/'coordinator_only/controls_and_missing.json').read_text())
    for c in control_data['controls']:
        if c['condition']!='damage':continue
        d=next(x for x in details if x['pilot_index']==c['pilot_index'] and x['condition']=='damage' and x['repeat']==0)
        measure=d['measurement'];findings=[]
        if 'parsed' in measure:
            obj=measure['parsed']
            findings=[obj['claims'][i] for i in obj['misuse_findings']]
        target_hits.append(dict(pilot_index=c['pilot_index'],measurement_status=measure['measurement_status'],
            m=measure['m'],edited_span=c['after'],findings=findings,
            exact_target_overlap=any(c['after'] in x['response_quote'] or x['response_quote'] in c['after'] for x in findings),
            caveat='lexical overlap is not independent semantic confirmation'))
    gp=json.loads((OUT/'generation_pointer.json').read_text());grun=Path(gp['run_dir']);gs=json.loads((grun/'summary.json').read_text())
    genrows=gs['rows'];gen_new=[r for r in genrows if not r['cache_hit']]
    preservation=json.loads(Path('/home/tokkio/PM_RL1_接手审计_20260928/repository_snapshot.json').read_text())['dirty_file_sha256']
    changed=[p for p,h in preservation.items() if sha256_file(PROJECT.parent/p)!=h]
    if changed:raise RuntimeError('preexisting files changed: '+str(changed))
    ledger=PROJECT/'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    assert sha256_file(ledger)=='71acad8990dd231ad054ea7a619e8df72b39d24da8d4f06a151933fb202f7a7d'
    result=dict(status='DEVELOPMENT_MEASUREMENT_AUDIT_NOT_JUDGE_QUALIFICATION',
        primary_items=45,stochastic_repeats=10,physical_judge_calls=55,
        finish_counts=dict(Counter(r['finish_reason'] for r in rows)),measurement_status_counts=dict(Counter(r['measurement_status'] for r in rows)),
        distributions=distribution,comparisons=comparison,
        repeat=dict(selected=len(repeat_selected),paired_valid=len(repeats),paired_missing=len(repeat_selected)-len(repeats),
            q_changed=sum(d['delta_q']!=0 for d in repeats),m_changed=sum(d['delta_m']!=0 for d in repeats),
            utility_changed=sum(d['delta_utility']!=0 for d in repeats),
            abs_utility_delta_gt_full_resource_penalty=sum(abs(d['delta_utility'])>.05 for d in repeats),rows=repeats),
        damage=dict(constructed=9,valid_measurements=len(damage_measured),missing=9-len(damage_measured),
            any_misuse_flagged=sum(r['m']>0 for r in damage_measured),
            note='any m>0 can flag the wrong claim; see target findings and independent review. These are assistant-authored easy current-fact controls, not human gold.'),
        generation=dict(actual_replies=24,new_calls=len(gen_new),exact_cache_hits=24-len(gen_new),
            finish_counts=dict(Counter(r['finish_reason'] for r in genrows)),
            output_tokens=stats([r['output_tokens'] for r in genrows]),new_generation_seconds=sum(r['seconds'] for r in gen_new),
            successful_load_seconds=json.loads((grun/'runtime.json').read_text())['load_seconds']),
        judge_compute=dict(input_tokens=stats([r['input_tokens'] for r in rows]),output_tokens=stats([r['output_tokens'] for r in rows]),
            summed_request_latency_seconds=sum(r['seconds'] for r in rows),engine_wall_seconds=summary['engine_wall_seconds'],
            successful_load_seconds=summary['load_seconds'],successful_process_seconds=summary['total_process_seconds'],
            engine_wall_seconds_per_completed_draw=summary['engine_wall_seconds']/len(rows),
            note='concurrent request latencies overlap; use engine wall for throughput. Failed startup is separate and not erased.'),
        independently_returned_reviews=0,independent_review_pairs_ready=10,independent_pairs_unavailable=2,
        new_paid_api_usd=0,paid_ledger_unchanged=True,preexisting_files_unchanged=len(preservation),
        reward_eligible=False,training_updates=0,
        limitations=['no calibrated human agreement for this protocol yet',
          'exact quotation validation does not certify semantic entailment',
          'mild style control does not cover large verbosity effects',
          'controlled damage covers current facts, not a complete history/identity/intent/outcome taxonomy',
          'small natural pilot does not establish resource benefits, SFT effects or PPO efficacy'])
    save('measurement_analysis.json',result)
    save('coordinator_only/failure_diagnostics.json',failures)
    save('coordinator_only/target_damage_findings.json',target_hits)
    save('coordinator_only/measurements_with_replies.json',details)
    save('analysis_manifest.json',dict(script_sha256=sha256_file(Path(__file__)),
        inputs={str(run/'summary.json'):sha256_file(run/'summary.json'),str(OUT/'exam_private.json'):sha256_file(OUT/'exam_private.json')},
        artifacts={f:sha256_file(OUT/f) for f in ['measurement_analysis.json','coordinator_only/failure_diagnostics.json','coordinator_only/target_damage_findings.json','coordinator_only/measurements_with_replies.json']},
        all_raw_measurements_reparsed_identically=True,new_model_calls=0))
    print(json.dumps({k:result[k] for k in ['finish_counts','measurement_status_counts','distributions','repeat','damage','judge_compute']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
