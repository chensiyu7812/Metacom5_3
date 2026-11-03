#!/usr/bin/env python3
"""Preserve the researcher's new answer without inventing scalar rewards."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest

BASE=PROJECT/'outputs/pm_rl1'
RAW_ANSWER='这个场景，我个人感觉是相当。怎么说呢，差距不是很明显，可以说如果B是90分，A是95分的程度，很接近。这种其实给我们的另一个“价值”是，如何判断所谓使用资源的收益，然后不同的“情况”，这个收益值不值得，如何去界定？'
QUESTION_ITEM_ID='["request_user_input_async","call_07b8aac097744a53997f10003f739174",0]'


def main(output):
    if output.exists():raise ValueError('new output directory required')
    sources={}
    def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def read(path):
        path=Path(path).resolve();sources[str(path)]=sha(path)
        return json.loads(path.read_text())
    def verify(folder,name='OUTPUT_MANIFEST.json'):
        for rel,h in read(folder/name).items():
            assert not Path(rel).is_absolute() and '..' not in Path(rel).parts
            assert sha(folder/rel)==h
    findings=BASE/'decision_findings_20261104_v1'
    human=BASE/'human_answer_reanalysis_20261103_v2'
    feedback=BASE/'actual_training_feedback_20261103_v1'
    train=BASE/'organized_initial_training_20261103_v2'
    for folder in (findings,human,feedback):verify(folder)
    verify(train,'PACKAGE_MANIFEST.json')
    question=read(findings/'PRIORITY_QUESTION_PRIVATE.json')
    assert question['question_id']=='pmrl1-c02-history-benefit-20261104-v1'
    assert question['answer'] is question['qm'] is None
    items=read(feedback/'INPUTS_PRIVATE.json')
    endpoints={r['endpoint_identity']:r for r in read(feedback/'ENDPOINTS_PRIVATE.json')}
    cards={c['alias']:c for c in question['cards']}
    assert set(cards)=={'A','B'} and cards['A']['actions']==[3]*6+[0] and cards['B']['actions']==[0]
    eid=digest(question['evidence'])
    for c in cards.values():
        actual=items[c['input_identity']];end=endpoints[c['endpoint_identity']]
        assert c['evidence_identity']==actual['evidence_identity']==eid
        assert digest(c['reply'])==c['reply_identity']==actual['reply_identity']
        assert actual['evidence']==question['evidence'] and actual['reply']==c['reply']
        assert end['ON']==c['input_identity'] and end['actions']==c['actions']
        assert end['resource_tokens']==c['resource_tokens']
    pair_id=digest(dict(evidence=eid,replies=sorted(c['reply_identity'] for c in cards.values())))
    old=read(human/'ANSWER_REGISTRY_PRIVATE.json')
    assert not any(r.get('pair_identity')==pair_id for r in old)
    intake=dict(question_id=question['question_id'],question_item_id=QUESTION_ITEM_ID,
        source='current_conversation_researcher_answer',client_date='2026-11-04',timezone='Asia/Tokyo',
        original_answer=RAW_ANSWER,question_artifact_sha256=sha(findings/'PRIORITY_QUESTION_PRIVATE.json'),
        evidence_identity=eid,pair_identity=pair_id,alias_bindings=cards,
        analyst_interpretation=dict(practical_comparison='near_equivalent',
            small_edge='A',illustrative_values=dict(A=95,B=90),
            values_are_calibrated_cardinal_utilities=False,
            not_inferred=['exact_equal_utility','strict_material_preference','preference_probability',
                'q_A','q_B','m_A','m_B','net_reward_winner']),
        exact_qm=None,numeric_reward=None,qualified_reward=False,
        decision_use='Retain a near-equivalence, cost-sensitive reference; do not promote as a clear material resource-benefit positive.',
        reask_same_question=False)
    ref=dict(direction='near_equivalent_with_small_A_edge',evidence_identity=eid,
        independent_frozen_validation=False,kind='pair_preference_with_illustrative_magnitude',
        observation_origin='researcher-current-conversation',pair_identity=pair_id,
        preferred_reply_identity=None,slight_edge_reply_identity=cards['A']['reply_identity'],
        purpose='targeted exposed train diagnostic; not a scalar reward or rater-agreement sample',
        qualified_reward=False,raw_label=dict(original_answer=RAW_ANSWER),record_id=question['question_id'],
        reply_identities=sorted(c['reply_identity'] for c in cards.values()),source='20261104_current_conversation',
        asset_id='pairs:20261104_current_conversation:'+question['question_id'],
        evidence=question['evidence'],replies={c['reply_identity']:c['reply'] for c in cards.values()},
        task_family='pairs',independent_new_observation=False,new_answer_event=True,
        independence_note='One new human answer, not another independent rater or held-out evaluation.',
        original_question_number=None,intake_identity=digest(intake))
    merged=old+[ref]
    for r in merged:
        assert digest(r['evidence'])==r['evidence_identity']
        assert all(digest(text)==rid for rid,text in r['replies'].items())
    assert len({r['asset_id'] for r in merged})==len(merged)
    # Facts and hypothetical sensitivity rows are separate data objects.
    config=read(train/'CONFIG.json');cost=config['cost']
    w=Decimal(str(cost['weight']));unit=Decimal(cost['unit_tokens'])
    extra=cards['A']['resource_tokens']-cards['B']['resource_tokens']
    penalty=w*Decimal(extra)/unit
    sensitivity=dict(actual=dict(extra_resource_tokens=extra,GET_A=6,GET_B=0,
        cost_weight=float(w),unit_tokens=int(unit),additional_utility_cost=float(penalty),
        required_quality_minus_misuse_improvement_for_positive_net=float(penalty),
        measured_quality_difference=None,measured_misuse_difference=None,measured_net_advantage=None,
        cost_unit='candidate utility penalty, not dollars or measured latency'),
        hypothetical=dict(not_measurements=True,not_training_labels=True,
            assumption='Illustratively align the 90/95 analogy to U=score/100 with unchanged misuse; the researcher did not establish this mapping.',
            assumed_delta_U=.05,net_at_current_weight=float(Decimal('.05')-penalty),
            break_even_token_difference=float(Decimal('.05')*unit/w),
            break_even_weight_per_2048=float(Decimal('.05')*unit/Decimal(extra)),
            weight_sensitivity=[dict(weight_per_2048=float(v),
                net_advantage=float(Decimal('.05')-v*Decimal(extra)/unit))
                for v in map(Decimal,['0','.01','.02','.05','.1'])],
            category_sensitivity=[dict(assumption=label,delta_U=float(delta),net=float(delta-penalty))
                for label,delta in [('same_q_same_m',Decimal(0)),('A_one_q_level_better_same_m',Decimal('.25'))]],
            changes_to_runtime_cost=0))
    # No live or historical human input is rewritten.
    cfg=read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for p,h in cfg['policy']['historical_files'].items():assert sha(p)==h
    sources[str(Path(cfg['ledger']).resolve())]=sha(cfg['ledger'])
    previous=read(PROJECT/'docs/reviews/20261104/pm_rl1_decision_branches/CHECKS.json')
    assert sha(cfg['ledger'])==previous['original_ledger_sha256']
    sources[str(Path(__file__).resolve())]=sha(__file__)
    assert all(sha(p)==h for p,h in sources.items())
    output.mkdir(parents=True,mode=0o700)
    def save(name,value):
        p=output/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
    save('INTAKE_PRIVATE.json',intake);save('ANSWER_REGISTRY_PRIVATE.json',merged)
    save('VALUE_SENSITIVITY.json',sensitivity)
    save('REFERENCE_INDEX.json',dict(active_registry=str(output/'ANSWER_REGISTRY_PRIVATE.json'),
        base_registry=str(human/'ANSWER_REGISTRY_PRIVATE.json'),base_preserved=True,
        new_reference_asset_id=ref['asset_id'],new_pair_is_not_a_hard_tie=True,
        scoring_or_training_adapter_automatically_reconfigured=False))
    stats=dict(human_answers_received_this_intake=1,registry_records=len(merged),
        registry_task_families=dict(Counter(r['task_family'] for r in merged)),
        old_records_preserved=merged[:-1]==old,original_question_preserved=True,
        original_answer_identity=digest(RAW_ANSWER),new_scalar_rewards=0,new_G=0,new_J=0,
        new_cost_usd=0,natural_BC_updates=0,natural_PPO_updates=0,
        extra_resource_tokens=extra,additional_utility_cost=float(penalty),
        qualified_reward=False,formal_cost_weight_changed=False,
        frozen_historical_files_verified=len(cfg['policy']['historical_files']))
    save('SUMMARY.json',stats);save('SOURCE_HASHES_PRIVATE.json',sources)
    save('OUTPUT_MANIFEST.json',{p.name:sha(p) for p in output.iterdir()})
    print(json.dumps(stats,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)
