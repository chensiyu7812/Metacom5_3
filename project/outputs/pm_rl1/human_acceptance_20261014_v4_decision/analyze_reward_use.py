#!/usr/bin/env python3
"""Read existing development results and explain their reward implications.

This creates diagnostic arithmetic, never rewards eligible for training.
No human-label conversion, key access, decryption, model call or new scoring.
"""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess


def run(repo,out):
    root=repo/'project/outputs/pm_rl1'
    v2=root/'human_acceptance_20261014_v2'
    v3=root/'human_acceptance_20261014_v3_notes/review'
    p3=root/'completion_20260930_v2/P3'
    inputs=[v2/'intake/development_comparisons_private.json',v2/'analysis/statistics.json',
        v3/'summary.json',v3/'notes_reconciliation_private.json',v3/'analyst_source_alignments_private.json',
        p3/'candidate_v1/protocol.json',
        repo/'project/docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md',
        repo/'project/docs/pm_rl1_completion_20260930_v2/runbook.md',
        repo/'project/src/metacom_pm/rl1/calibration_decision.py']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    hashes={str(p):sha(p) for p in inputs}
    read=lambda p:json.loads(p.read_text())
    comparisons=read(inputs[0]);stats=read(inputs[1]);notes=read(inputs[2]);protocol=read(inputs[5])
    assert notes['development_pairs_with_written_assessment']==16 and notes['validation_pairs_sealed']==24
    assert notes['formal_preference_imputations']==notes['formal_risk_imputations']==0
    assert not list(p3.rglob('*measurement*freeze*.json'))
    resources=[]
    for row in comparisons:
        if row['kind']!='natural' or row['contrast']!='resource':continue
        left,right=row['canonical_sides'];scores=row['scores']
        assert left['arm']==right['arm']=='primary' and left['resource_tokens']==0
        assert left['prefix_identity']==right['prefix_identity']==row['prefix_identity']
        assert left['owner']==right['owner']==row['owner']
        assert left['split']==right['split']=='dev'
        off=Decimal(scores[0]['q'])/4-Decimal(str(scores[0]['m']))
        on=Decimal(scores[1]['q'])/4-Decimal(str(scores[1]['m']))
        assert off==Decimal(str(scores[0]['utility'])) and on==Decimal(str(scores[1]['utility']))
        cost=Decimal('0.05')*Decimal(right['resource_tokens'])/Decimal(2048)
        resources.append(dict(Chen_order=row['Chen_order'],pair_id=row['pair_id'],owner=row['owner'],
            resource_tokens=right['resource_tokens'],human_preference={'left':'OFF','right':'ON','tie':'tie'}[row['human_direction']],
            candidate_OFF_U=float(off),candidate_ON_U=float(on),delta_U=float(on-off),cost_penalty=float(cost),
            hypothetical_net_reward=float(on-off-cost),scope='diagnostic arithmetic only; not an authorized training reward',
            human_numeric_reward=None))
    assert len(resources)==4
    assert sum(x['human_preference']=='tie' for x in resources)==3
    r6=next(x for x in resources if x['Chen_order']==6)
    assert r6['human_preference']=='ON' and r6['delta_U']==-.5
    assert r6['hypothetical_net_reward']==-.508056640625
    natural=next(s for s in stats['preference_strata'] if s['group']=='自然')
    assert (natural['matches'],natural['pairs'],natural['clear'],natural['clear_matches'],natural['ties'],natural['tie_matches'])==(5,8,1,0,7,5)
    result=dict(status='DEVELOPMENT_CANDIDATE_NOT_REWARD_QUALIFIED',
        qualification_decision_executed=False,formal_failure_declared=False,
        usable_now=['development_diagnostics','source-linked case comparison','offline engineering analysis of existing scores'],
        unsupported_now=['formal_PPO_reward','sole_confirmatory_effect_measure','general_risk_accuracy_claim'],
        human_material=dict(development_pairs=16,written_assessments=16,comparable_preferences=15,
            explicit_narrative_uncertainty=1,independent_export_record_sets=1,derived_Du_sets=1,sealed_pairs=24),
        natural_description=natural,resource_examples=resources,
        reward_model_risk='The only human-preferred ON example among four development resource pairs gets negative candidate delta_U; small nonrandom sample, not proof of universal wrong ranking.',
        existing_rubric_already_contains=['no style-only reward','different reasonable strategies may tie','tentative question vs factual assertion','explicit boundary required'],
        recommendation='Development closeout and one bounded candidate-revision draft before final measurement freeze; no automatic revision or opening now.',
        data_intake_gap='Notes audited != original strict intake passed. Any partial-field adapter must be declared before opening, preserve missingness/provenance, and keep qualification gates unchanged; it cannot create human severity.',
        pending_formal_evidence=['final_measurement_freeze','24 held-out human pairs','47 held-out unique primary reply scores','12 independent repeat scores','source-confirmed control records'],
        plan_identity=protocol['identity'],repository_HEAD=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        new_model_calls=0,API_usd=0,training_updates=0,private_key_reads=0,heldout_label_decryptions=0,human_label_changes=0,
        core_reward_or_protocol_changes=0)
    out.mkdir(exist_ok=False)
    (out/'decision_analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    with (out/'resource_reward_examples.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(resources[0]));w.writeheader();w.writerows(resources)
    assert all(sha(Path(p))==v for p,v in hashes.items())
    assert subprocess.check_output(['git','-C',str(repo),'status','--short'],text=True)==''
    (out/'input_manifest.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')
    (out/'CHECKS.json').write_text(json.dumps(dict(source_hashes_unchanged=True,source_and_executor_pairing_verified=True,
        reward_arithmetic_checked_with_Decimal=True,existing_human_preferences_unchanged=True,
        development_only=True,no_final_measurement_freeze=True,git_status_clean=True),indent=2)+'\n')
    print(json.dumps(dict(natural_agreement='5/8',resource_pairs=4,resource_human_ties=3,resource_human_ON_wins=1,
        example_6_net_reward=r6['hypothetical_net_reward'],reward_qualified=False),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.repo,a.out)
