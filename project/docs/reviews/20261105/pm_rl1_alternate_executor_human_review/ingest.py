"""Append exact researcher's ordinal answers; no model calls or scalar rewards."""
import hashlib,json
from collections import Counter
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[4];BASE=PROJECT/'outputs/pm_rl1'
SOURCE=BASE/'alternate_executor_probe_20261104_v1';ROOT=BASE/'alternate_executor_human_review_20261105_v1'
PRIOR=BASE/'resource_value_probe_20261104_v1/ANSWER_REGISTRY_PRIVATE.json'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(name,obj):
    with (ROOT/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    (ROOT/name).chmod(0o600)


def main():
    for name,h in read(SOURCE/'OUTPUT_MANIFEST.json').items():assert sha(SOURCE/name)==h,name
    p=read(SOURCE/'PROTOCOL.json');received=read(ROOT/'RECEIVED_ANSWER_PRIVATE.json');pairs=read(SOURCE/'HUMAN_PAIRS_PRIVATE.json')
    assert received['study']=='pmrl1-alternate-'+p['identity']
    assert set(received['answers'])=={q['id'] for q in pairs} and len(pairs)==8
    original=read(PRIOR);rows=[];new=[]
    inventory={v['case']:v for v in read(BASE/'resource_value_probe_20261104_v1/INVENTORY_PRIVATE.json')}
    for q in pairs:
        answer=received['answers'][q['id']];choice=answer['choice'];assert choice in ('A略好','B略好','相当')
        models=[q['left_model'],q['right_model']];arms=[q['left_arm'],q['right_arm']];texts=[q['left'],q['right']]
        if q['reverse']:models.reverse();arms.reverse();texts.reverse()
        bindings={label:dict(model=model,arm=arm,reply=text,reply_identity=digest(text)) for label,model,arm,text in zip('AB',models,arms,texts)}
        assert bindings['A']['reply_identity']==q['A_identity'] and bindings['B']['reply_identity']==q['B_identity']
        assert digest(q['evidence'])==q['evidence_identity']
        win=choice[0] if choice!='相当' else None;winner=bindings[win] if win else None
        result=('tie' if not win else 'resource_slightly_preferred' if winner['arm']=='C_target_full_MS' else 'OFF_slightly_preferred') if q['kind']=='within_G_resource' else ('tie' if not win else 'alternate_slightly_preferred' if winner['model']=='alternate' else 'original_slightly_preferred')
        pair_id=digest(dict(evidence=q['evidence_identity'],replies=sorted([q['A_identity'],q['B_identity']])))
        assert not any(x.get('pair_identity')==pair_id for x in original+new)
        row=dict(question_id=q['id'],case=q['case'],owner=inventory[q['case']]['owner'],kind=q['kind'],
            original_answer=answer,alias_bindings=bindings,evidence=q['evidence'],evidence_identity=q['evidence_identity'],pair_identity=pair_id,
            outcome=result,degree='equivalent' if win is None else 'slight',winner_alias=win,
            winner_reply_identity=winner['reply_identity'] if winner else None,exact_qm=None,numeric_reward=None,
            qualified_reward=False,study=received['study'],submitted_on='2026-11-05',timezone='Asia/Tokyo')
        rows.append(row);record_id='pmrl1-alternate-human-20261105-'+q['id']
        new.append(dict(record_id=record_id,asset_id='pairs:20261105_current_conversation:'+record_id,
            task_family='pairs',kind='pair_preference',direction=result,degree=row['degree'],
            evidence=q['evidence'],evidence_identity=q['evidence_identity'],pair_identity=pair_id,
            reply_identities=sorted([q['A_identity'],q['B_identity']]),replies={x['reply_identity']:x['reply'] for x in bindings.values()},
            raw_label=answer,source='20261105_current_conversation',question_id=q['id'],study=received['study'],
            preferred_reply_identity=None,slight_edge_reply_identity=row['winner_reply_identity'],
            human_respondents=1,observation_origin='researcher supplied completed blind-form answers',assistance_status='not_reported',
            new_answer_event=True,independent_frozen_validation=False,independent_new_observation=False,
            independence_note='Same researcher; seven contexts, six source owners; N21 OFF reply shared by two different comparisons. Not recipient feedback or independent raters.',
            purpose='exact diagnostic references; no automatic transfer to other replies, Gs or scalar PPO rewards',
            qualified_reward=False,exact_qm=None,numeric_reward=None,intake_identity=digest(row)))
    merged=original+new;assert len(merged)==44 and len({x['asset_id'] for x in merged})==44
    for r in merged:
        assert digest(r['evidence'])==r['evidence_identity']
        assert all(digest(text)==key for key,text in r['replies'].items())
    resource=Counter(r['outcome'] for r in rows if r['kind']=='within_G_resource');cross=Counter(r['outcome'] for r in rows if r['kind']=='OFF_cross_G')
    summary=dict(status='HUMAN_REFERENCES_BOUND_NOT_SCALAR_REWARD',answers=8,respondents=1,contexts=len({r['case'] for r in rows}),source_owners=len({r['owner'] for r in rows}),
        resource_comparisons=dict(planned=7,answered=6,technical_failure_not_zero=1,outcomes=dict(resource),material_preference=0),
        OFF_cross_G=dict(answered=2,outcomes=dict(cross),both_at_least_tie_in_these_cases=True),
        total_choices=dict(Counter(r['original_answer']['choice'] for r in rows)),old_registry_records=36,new_registry_records=8,total_registry_records=44,
        scalar_reward_created=0,positive_resource_reward_qualified=False,format_failure_still_open=True,
        G_promoted=False,G_training_updates=0,PM_updates=0,API_cost_usd=0,new_human_questions=0,
        deployment_latency_observations_added=0,latency_lambda=None,old_cost_control_PPO_updates=24)
    save('INTAKE_PRIVATE.json',dict(source='user pasted JSON in current chat',received_on='2026-11-05',timezone='Asia/Tokyo',raw_sha256=sha(ROOT/'RECEIVED_ANSWER_PRIVATE.json'),
        sources={str(f.resolve()):sha(f) for f in [SOURCE/'PROTOCOL.json',SOURCE/'OUTPUT_MANIFEST.json',SOURCE/'HUMAN_PAIRS_PRIVATE.json',SOURCE/'HUMAN_REVIEW_ZH.html',PRIOR]},
        answers=rows,illustrative_scores='G06 85/95 retained verbatim, not q/m or a 0.10 utility difference',analyst_interpretation_is_human_label=False))
    save('ANSWER_REGISTRY_PRIVATE.json',merged);save('SUMMARY.json',summary)
    save('REFERENCE_INDEX.json',dict(active_registry=str(ROOT/'ANSWER_REGISTRY_PRIVATE.json'),base_registry=str(PRIOR),old_records_preserved=36,new_answer_events=8,
        registry_records=44,registry_task_families=dict(Counter(x['task_family'] for x in merged)),scoring_or_training_automatically_reconfigured=False))
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
