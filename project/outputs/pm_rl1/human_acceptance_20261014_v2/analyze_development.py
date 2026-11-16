#!/usr/bin/env python3
"""Deterministic descriptive statistics; no decrypt, API, model or inference."""
import argparse
from collections import Counter
import json
from pathlib import Path
from audit_development import dump, table


def calculate(intake):
    rows=json.loads((intake/'development_comparisons_private.json').read_text())
    audit=[r for r in json.loads((intake/'development_item_audit_private.json').read_text()) if r['slot']=='rater_1']
    assert len(rows)==len(audit)==16 and len({r['pair_id'] for r in rows})==16
    strata=[]
    groups=[('全部开发',rows),('自然', [r for r in rows if r['kind']=='natural']),
            ('控制', [r for r in rows if r['kind']=='control']),
            ('自然-资源', [r for r in rows if r['contrast']=='resource']),
            ('自然-执行器', [r for r in rows if r['contrast']=='executor'])]
    groups.extend(('owner-'+o,[r for r in rows if r['owner']==o]) for o in sorted({r['owner'] for r in rows}))
    for group, rr in groups:
        comparable=[r for r in rr if r['preference_comparable']]
        clear=[r for r in comparable if r['human_direction'] in ('left','right')]
        ties=[r for r in comparable if r['human_direction']=='tie']
        matches=sum(r['preference_match'] is True for r in comparable)
        strata.append(dict(group=group,pairs=len(rr),owners=len({r['owner'] for r in rr}),
            prefixes=len({r['prefix_identity'] for r in rr}),strict_complete=sum(r['strict_label_valid'] for r in rr),
            comparable=len(comparable),missing_preference=sum(r['human_direction'] not in ('left','right','tie','uncertain') for r in rr),
            uncertain_preference=sum(r['human_direction']=='uncertain' for r in rr),
            human_left=sum(r['human_direction']=='left' for r in rr),human_right=sum(r['human_direction']=='right' for r in rr),
            human_tie=len(ties),matches=matches,agreement=matches/len(comparable) if comparable else None,
            clear=len(clear),clear_matches=sum(r['preference_match'] is True for r in clear),
            ties=len(ties),tie_matches=sum(r['preference_match'] is True for r in ties)))
    confusion=[]
    for criterion in ('enum_only','evidence_ready'):
        counts=Counter()
        for r in rows:
            for side, name in enumerate(('left','right')):
                risk=r['human_risk_'+name]
                if risk not in ('none_detected','local','severe'):continue
                if criterion=='evidence_ready' and not r[name+'_risk_evidence_ready']:continue
                counts[risk,r['scores'][side]['m']]+=1
        for risk in ('none_detected','local','severe'):
            confusion.append(dict(cohort=criterion,human_risk=risk,auto_m0=counts[risk,0],
                auto_m025=counts[risk,.25],auto_m1=counts[risk,1],
                denominator=sum(v for (h,m),v in counts.items() if h==risk)))
    # Natural comparison categories are frozen provenance, not apparent form A/B.
    strategies=[]
    for r in rows:
        if r['kind']!='natural':continue
        sides=r['canonical_sides']
        descriptors=[dict(arm=s['arm'],counts=s['counts'],resource_tokens=s['resource_tokens']) for s in sides]
        strategies.append(dict(pair_id=r['pair_id'],Chen_order=r['Chen_order'],contrast=r['contrast'],
            left=descriptors[0],right=descriptors[1],human_direction=r['human_direction'],judge_direction=r['judge_direction']))
    totals=dict(pairs=len(rows),preference_pairs=sum(r['preference_comparable'] for r in audit),strict_complete=sum(r['strict_valid'] for r in audit),
        risk_enum_sides=sum(r['risk_'+s+'_comparable'] for r in audit for s in 'AB'),
        risk_missing_sides=sum(not r['risk_'+s+'_enum_valid'] for r in audit for s in 'AB'),
        risk_evidence_ready_sides=sum(r['risk_'+s+'_evidence_ready'] for r in audit for s in 'AB'),
        risk_both_enum_pairs=sum(all(r['risk_'+s+'_comparable'] for s in 'AB') for r in audit),
        risk_both_evidence_ready_pairs=sum(all(r['risk_'+s+'_evidence_ready'] for s in 'AB') for r in audit),
        usable_nonzero_risk_with_required_evidence=sum(r['risk_'+s+'_evidence_ready'] and r['label']['risk_'+s] in ('local','severe') for r in audit for s in 'AB'),
        owner_counts=dict(Counter(r['owner'] for r in rows)),prefix_pair_counts=dict(Counter(r['prefix_identity'] for r in rows)),
        uncertainty_policy='uncertain excluded from agreement, reported separately; blank never converted to tie/zero',
        CI=None,CI_reason='Purposive development sample; 16 pairs share 9 prefixes and only 3 owners. No independent-pair/rater CI or p-values.',
        independent_interrater_agreement=None,interrater_reason='Du is a converted copy, not an independently entered original record',
        qualification_status='NOT_EVALUATED_ON_SEALED_VALIDATION', reward_qualified=False)
    return dict(totals=totals,preference_strata=strata,risk_confusion=confusion,natural_strategies=strategies)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--intake',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=calculate(a.intake);a.out.mkdir(exist_ok=False)
    dump(a.out/'statistics.json',result)
    for k in ('preference_strata','risk_confusion','natural_strategies'):table(a.out/(k+'.csv'),result[k])
    print(json.dumps(result['totals'],ensure_ascii=False,indent=2))
