"""Bind the V01 answer once; preserve earlier references and frozen outputs."""
import hashlib,json
from collections import Counter
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[4];BASE=PROJECT/'outputs/pm_rl1'
SOURCE=BASE/'incremental_help_probe_20261105_v1'
PRIOR=BASE/'alternate_executor_human_review_20261105_v1/ANSWER_REGISTRY_PRIVATE.json'
ROOT=BASE/'incremental_help_human_review_20261105_v1'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def save(name,obj):
    with (ROOT/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    (ROOT/name).chmod(0o600)


def main():
    for name,h in read(SOURCE/'OUTPUT_MANIFEST.json').items():assert sha(SOURCE/name)==h,name
    p=read(SOURCE/'HUMAN_PAIR_PRIVATE.json');assert p['identity']==digest({k:v for k,v in p.items() if k!='identity'})
    assert p['question']=='V01' and p['case']=='N06'
    answer=read(ROOT/'RECEIVED_ANSWER_PRIVATE.json');assert answer['question_id']=='V01'
    bindings={label:dict(generator=p[label]['generator'],arm=p[label]['arm'],actions=p[label]['actual_program'],
        acquisition_order=p[label]['acquisition_order'],input_identity=p[label]['input_identity'],
        reply=p[label]['reply'],reply_identity=p[label]['reply_identity']) for label in ('A','B')}
    assert bindings['A']['arm']=='REAL_MS_PATH' and bindings['A']['actions']==[3,3,3,3,0]
    assert bindings['B']['arm']=='OFF' and bindings['B']['actions']==[0]
    assert all(v['generator']=='alternate' and digest(v['reply'])==v['reply_identity'] for v in bindings.values())
    pair_id=digest(dict(evidence=p['evidence_identity'],replies=sorted(v['reply_identity'] for v in bindings.values())))
    old=read(PRIOR);assert len(old)==44 and not any(r.get('pair_identity')==pair_id for r in old)
    row=dict(question_id='V01',case='N06',study=p['study'],instrument_identity=p['identity'],
        original_answer=answer['answer'],normalized_choice='相当',normalization_basis='明确说相当、都可以，只是支持策略不同；未给任一侧偏好。',
        alias_bindings=bindings,evidence=p['evidence'],evidence_identity=p['evidence_identity'],pair_identity=pair_id,
        outcome='tie',degree='equivalent',winner_alias=None,winner_reply_identity=None,
        exact_qm=None,numeric_reward=None,qualified_reward=False,submitted_on='2026-11-05',timezone='Asia/Tokyo')
    record_id='pmrl1-incremental-human-20261105-V01'
    record=dict(record_id=record_id,asset_id='pairs:20261105_current_conversation:'+record_id,
        task_family='pairs',kind='pair_preference',direction='tie',degree='equivalent',
        evidence=p['evidence'],evidence_identity=p['evidence_identity'],pair_identity=pair_id,
        reply_identities=sorted(v['reply_identity'] for v in bindings.values()),replies={v['reply_identity']:v['reply'] for v in bindings.values()},
        raw_label=dict(original_answer=answer['answer']),source='20261105_current_conversation',question_id='V01',study=p['study'],
        preferred_reply_identity=None,slight_edge_reply_identity=None,human_respondents=1,
        observation_origin='researcher answered the exact V01 comparison through current conversation',
        translation_exposure='Question included assistant Chinese translations; full English replies and all evidence linked. No claim that researcher read every linked turn.',
        assistance_status='not_reported',new_answer_event=True,independent_frozen_validation=False,independent_new_observation=False,
        independence_note='Same researcher, exposed train context, pair selected after generation for observed mechanism; not an independent recipient or population sample.',
        purpose='equivalent-acceptable-strategy calibration; no automatic label transfer to other paths, replies, models or scalar rewards',
        qualified_reward=False,exact_qm=None,numeric_reward=None,intake_identity=digest(row))
    merged=old+[record];assert len(merged)==len({r['asset_id'] for r in merged})==45
    for r in merged:
        assert digest(r['evidence'])==r['evidence_identity'] and all(digest(text)==k for k,text in r['replies'].items())
    files=[SOURCE/'HUMAN_PAIR_PRIVATE.json',SOURCE/'ONE_COMPARISON_ZH.html',SOURCE/'RESULTS_PRIVATE.json',
        SOURCE/'OUTPUT_MANIFEST.json',PRIOR,ROOT/'RECEIVED_ANSWER_PRIVATE.json']
    save('INTAKE_PRIVATE.json',dict(answer=row,raw_sha256=sha(ROOT/'RECEIVED_ANSWER_PRIVATE.json'),sources={str(f.resolve()):sha(f) for f in files}))
    save('ANSWER_REGISTRY_PRIVATE.json',merged)
    save('REFERENCE_INDEX.json',dict(active_registry=str(ROOT/'ANSWER_REGISTRY_PRIVATE.json'),base_registry=str(PRIOR),
        old_records_preserved=44,new_answer_events=1,registry_records=45,registry_task_families=dict(Counter(x['task_family'] for x in merged)),
        scoring_or_training_automatically_reconfigured=False))
    summary=dict(status='V01_BOUND_EQUIVALENT_STRATEGIES',human_answers=1,new_human_questions=0,
        choice='相当',historical_records_preserved=44,total_registry_records=45,
        mechanism_observed=True,positive_helpfulness_preference_observed=False,
        branch_status='ACTUAL_RESOURCE_PATH_CHANGED_STRATEGY_WITHOUT_DEMONSTRATED_HELPFULNESS_PREFERENCE',
        positive_candidate_latency_stage_triggered=False,positive_candidate_training_stage_triggered=False,
        general_resource_uselessness_claim=False,exact_quality_difference=None,
        reuse='Calibration must accept these two strategies rather than reward resource use or advice change alone.',
        transfer='No new label for target-only, MS1, original G, N13, or any unmeasured intermediate STOP.',
        total_utility_order='Unknown without actual latency and a justified utility convention; human equivalence is not exact numerical equality.',
        API_calls=0,API_cost_usd=0,model_calls=0,training_updates=0,old_cost_control_PPO_updates=24)
    save('SUMMARY.json',summary)
    save('OUTPUT_MANIFEST.json',{f.name:sha(f) for f in sorted(ROOT.iterdir()) if f.is_file()})
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
