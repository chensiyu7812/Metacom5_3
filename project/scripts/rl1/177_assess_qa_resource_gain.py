#!/usr/bin/env python3
"""Assess the frozen QA diagnostic. Never admit a training reward or start RL."""
import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import verify_identity
from metacom_pm.rl1.durable import save_json_once as save


def summarize(rows, primary_cases, protocol):
    """Full-answer accuracy bounds; pending is [0,1], never an observed zero."""
    lookup={(r['case'],r['arm']):r for r in rows}
    if len(lookup)!=len(rows):raise ValueError('duplicate case/arm')
    arms=['OFF','C','D','R1','R2']
    def bounds(row):
        if not row['valid'] or row['verdict'] in ('pending','uncertain'):
            return (0.0,1.0)
        if row['verdict']=='correct':return (1.0,1.0)
        if row['verdict'] in ('partial','incorrect','abstained'):return (0.0,0.0)
        raise ValueError('unrecognized verdict')
    stats={}
    for arm in arms:
        entries=[bounds(lookup.get((c,arm),dict(valid=False,verdict='pending'))) for c in primary_cases]
        stats[arm]=dict(lower=sum(x[0] for x in entries)/len(entries),upper=sum(x[1] for x in entries)/len(entries))
    def difference(a,b):
        return dict(lower=stats[a]['lower']-stats[b]['upper'],upper=stats[a]['upper']-stats[b]['lower'])
    diffs={a+'/'+b:difference(a,b) for a,b in [('C','OFF'),('C','D'),('R1','OFF'),('R2','OFF'),('R2','R1')]}
    owners=defaultdict(list)
    for case in primary_cases:
        c=lookup.get((case,'C'));off=lookup.get((case,'OFF'))
        if c and off:owners[c['owner']].append(bounds(c)[0]-bounds(off)[1])
    positives=sum(sum(v)/len(v)>0 for v in owners.values())
    coverage=all(r['valid'] for r in rows) and all((c,a) in lookup for c in set(primary_cases)|{r['case'] for r in rows} for a in arms)
    primary_resolved=all(lookup.get((c,a),{}).get('verdict') not in (None,'pending','uncertain') for c in primary_cases for a in arms)
    g=protocol['resource_gate'];r=protocol['deployable_retrieval_screen']
    resource=(coverage and stats['C']['lower']>=g['C_accuracy_min'] and diffs['C/OFF']['lower']>=g['C_minus_OFF_min']
        and diffs['C/D']['lower']>=g['C_minus_D_min'] and positives>=g['positive_C_minus_OFF_owner_means_min'])
    retrieval=(resource and diffs['R2/OFF']['lower']>=r['R2_minus_OFF_min']
        and diffs['R2/OFF']['lower']>=r['retain_C_minus_OFF_gain_fraction_min']*diffs['C/OFF']['upper'])
    status=('PENDING_TECHNICAL_COVERAGE' if not coverage else
            'RESOURCE_AND_SHORT_RETRIEVAL_SCREEN_PASSED_NOT_RL_READY' if retrieval else
            'RESOURCE_PRESENT_RETRIEVAL_GAP_NO_RL' if resource and primary_resolved else
            'PENDING_PRIMARY_SOURCE_REVIEW' if not primary_resolved else 'RESOURCE_SCREEN_NOT_MET_STOP_CONFIGURATION')
    return dict(status=status,full_answer_accuracy_bounds=stats,paired_mean_difference_bounds=diffs,
        primary_cases=len(primary_cases),positive_owner_means_lower_bound=positives,
        all_planned_outputs_natural=coverage,primary_verdicts_resolved=primary_resolved,
        resource_gate_passed=resource,short_retrieval_screen_passed=retrieval,
        deployment_latency_passed=None,sequential_policy_value_established=False,
        reward_qualified=False,RL_ready=False)


def main(out):
    read=lambda p:json.loads(p.read_text())
    decision=read(out/'DECISION_PROTOCOL.json');verify_identity(decision)
    results=read(out/'RESULTS_PRIVATE.json')
    # Optional source-bound review is keyed by blinded input ID, not an arm guess.
    reviews=read(out/'BLIND_SOURCE_VERDICTS_PRIVATE.json') if (out/'BLIND_SOURCE_VERDICTS_PRIVATE.json').exists() else {}
    spec=importlib.util.spec_from_file_location('probe',Path(__file__).with_name('176_probe_qa_resource_gain.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[]
    for result in results:
        verdict='pending';origin='missing_or_needs_source_review'
        if result['valid']:
            manual=reviews.get(result['blind_review_id'])
            if manual:
                assert manual['reply_identity']==result['raw']['text_identity']
                assert manual['verdict'] in ('correct','partial','incorrect','abstained','uncertain')
                verdict=manual['verdict'];origin='assistant_blind_source_review_not_independent_human'
            elif result['review_kind']=='admit_factual_diagnostic' and result['strict_alias_match']:
                verdict='correct';origin='predeclared_alias'
            elif module.normalized_answer(result['raw']['text'])=='unknown':
                verdict='abstained';origin='explicit_unknown'
        rows.append(dict(case=result['case'],owner=result['owner'],arm=result['arm'],valid=result['valid'],
            verdict=verdict,origin=origin,blind_review_id=result['blind_review_id']))
    assert len(rows)==len(read(out/'CARDS_PRIVATE.json'))==95
    expected={(c['case'],c['arm']) for c in read(out/'CARDS_PRIVATE.json')}
    assert {(r['case'],r['arm']) for r in rows}==expected
    summary=summarize(rows,decision['primary_cases'],decision)
    summary['secondary_rows']=[r for r in rows if r['case'] in decision['secondary_cases']]
    summary['API_cost_usd']=0
    # A review revision uses its own output file; never overwrite a prior verdict.
    index=len(list(out.glob('ASSESSMENT_*.json')))
    save(out/f'ASSESSMENT_{index:02}.json',dict(decision_identity=decision['identity'],rows=rows,summary=summary))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    main(p.parse_args().output.resolve())
