#!/usr/bin/env python3
"""Freeze accepted weak targets after initial/repair reviews and bound AI audit."""
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest,HEADS
from metacom_pm.rl1.executor_coverage import merge_accepted,coverage
OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'


def read(p):return json.loads(p.read_text())


def main():
    if (OUT/'dataset_freeze.json').exists():raise RuntimeError('dataset already frozen')
    slots=read(OUT/'authoring_slots_private.json')['slots'];slot_map={s['slot_id']:s for s in slots}
    original=read(OUT/'provisional_admission_private.json')['rows']
    original_map={r['slot_id']:r for r in original}
    repair_selection=read(OUT/'repair_selection.json')
    repair=[]
    if repair_selection['selected']:
        repair=read(OUT/'provisional_admission_repair_private.json')['rows']
        assert len(repair)==repair_selection['selected']
    repair_map={r['slot_id']:r for r in repair}
    audit_path=OUT/'coordinator_audit_decisions_private.json';audit=read(audit_path)
    wanted=set(read(OUT/'coordinator_audit_slots.json')['slot_ids'])
    assert audit['status']=='COMPLETE' and {r['slot_id'] for r in audit['rows']}==wanted
    assert len(audit['rows'])==len(wanted) and audit['independent_human_gold'] is False
    for r in audit['rows']:
        source=original_map[r['slot_id']]
        assert r['author_raw_sha256']==source['author_raw_sha256']
        assert r['review_raw_sha256']==source['review_raw_sha256']
        assert r['rationale'] and r['override_status'] in (None,'reject','uncertain')
    overrides={r['slot_id']:r['override_status'] for r in audit['rows'] if r['override_status']}
    targets=[];decisions=[];guards=[audit_path,OUT/'slot_freeze.json',OUT/'supervision_freeze.json',
        OUT/'provisional_admission_private.json',OUT/'source_evidence_private.json',
        OUT/'repair_selection.json',OUT/'authoring_slots_private.json',OUT/'behavior_inputs_private.json',
        OUT/'behavior_input_reading_notes_private.json',Path(__file__)]
    if repair:guards.append(OUT/'provisional_admission_repair_private.json')
    guards.extend(PROJECT/'scripts/rl1'/name for name in (
        '87_train_p2_executor.py','88_diagnose_p2_epochs.py','89_select_p2_executor.py'))
    for s in slots:
        sid=s['slot_id'];a=original_map.get(sid);b=repair_map.get(sid);chosen=None
        initial_status=overrides.get(sid,a['status'] if a else 'technical_failure')
        if initial_status=='accept':chosen=a
        elif b and b['status']=='accept':chosen=b
        if chosen:
            raw_path=Path(chosen['author_raw_path']);review_path=Path(chosen['review_raw_path'])
            assert sha256_file(raw_path)==chosen['author_raw_sha256']
            assert sha256_file(review_path)==chosen['review_raw_sha256']
            raw=read(raw_path);assert raw['finish_reason']=='natural_stop'
            assert digest(raw['text'])==chosen['response_identity']
            parsed=chosen['parsed'];assert parsed['status']=='accept' and all(parsed['checks'].values())
            targets.append(dict(request_id=chosen['author_request_id'],slot_id=sid,index=s['index'],
                owner=s['owner'],split=s['split'],condition=s['category'],counts=s['counts'],
                prefix_identity=s['prefix_identity'],messages=s['messages'],response=raw['text'],
                messages_identity=digest(s['messages']),response_identity=digest(raw['text']),
                review_identity=digest(chosen),
                resource_behavior='none' if not sum(s['counts']) else parsed['resource_behavior'],
                resource_behavior_model_reported=parsed['resource_behavior'],
                resource_behavior_semantically_verified=False,
                provenance_batch='P2_source_bound_weak_supervision_v1',author_attempt=chosen['attempt']))
            guards.extend([raw_path,review_path])
        decisions.append(dict(slot_id=sid,index=s['index'],category=s['category'],split=s['split'],
            initial_status=initial_status,repair_status=b['status'] if b else None,
            final_status='accept' if chosen else 'not_admitted',selected_attempt=chosen['attempt'] if chosen else None))
    merged,duplicates=merge_accepted([],targets);cov=coverage(merged)
    for split in ('train','dev'):
        group=[r for r in merged if r['split']==split]
        cov[split]['by_category']={c:dict(examples=sum(r['condition']==c for r in group),
            prefixes=len({r['prefix_identity'] for r in group if r['condition']==c}),
            owners=len({r['owner'] for r in group if r['condition']==c}))
            for c in ('OFF','single','cross_two','same_two','three','four')}
        cov[split]['resource_behavior_model_reported']=dict(Counter(r['resource_behavior_model_reported'] for r in group))
        cov[split]['behavior_caution']='Model can confuse current-prefix use with optional-resource use; counts are not verified uptake coverage. OFF is structurally none.'
    if not all(cov['train']['by_head'][h]>0 for h in HEADS):raise ValueError('missing head coverage; retain data but do not claim four-head executor readiness')
    def save(n,v):
        with (OUT/n).open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    save('accepted_dataset_private.json',dict(status='AI_WEAK_SUPERVISION_NOT_INDEPENDENT_GOLD',rows=merged,
        dataset_identity=digest(merged),source_review_qualified_as_reward=False,
        source_reviews='Same Qwen as author + bound exact-quote checks + finite coordinator AI audit',
        student_input='Original fixed DirectReplyRenderer messages only, even for repaired candidates'))
    initial_length=[]
    for r in original:
        raw=read(Path(r['author_raw_path']))
        initial_length.append(dict(status=overrides.get(r['slot_id'],r['status']),
            category=r['category'],split=r['split'],output_tokens=raw['output_tokens']))
    length_summary={status:dict(n=len(xs),min=min(xs),median=statistics.median(xs),max=max(xs))
        for status in sorted({r['status'] for r in initial_length})
        for xs in [[r['output_tokens'] for r in initial_length if r['status']==status]]}
    save('admission_summary.json',dict(accepted=len(merged),coverage=cov,
        initial_statuses=dict(Counter(r['initial_status'] for r in decisions)),
        initial_statuses_by_split_category={split:{cat:dict(Counter(r['status'] for r in initial_length
            if r['split']==split and r['category']==cat)) for cat in
            ('OFF','single','cross_two','same_two','three','four')} for split in ('train','dev')},
        initial_Qwen_output_tokens_by_status=length_summary,
        selection_analysis_scope='Descriptive admission/length coverage; not a causal quality effect or a calibrated error rate',
        selected_attempts=dict(Counter(str(r['selected_attempt']) for r in decisions)),
        rejected_or_unresolved=sum(r['final_status']!='accept' for r in decisions),
        duplicates=duplicates,coordinator_audit_count=len(audit['rows']),coordinator_downgrades=len(overrides),
        API_usd=0,human_labels=0,claim='Input/weak-target coverage only; no support-quality gain or reward qualification.'))
    save('final_admission_private.json',decisions)
    guards.extend(OUT/n for n in ('accepted_dataset_private.json','admission_summary.json','final_admission_private.json'))
    # Bind all pre-existing freeze references as well as the final target records.
    for name in ('slot_freeze.json','supervision_freeze.json'):
        f=read(OUT/name)
        for n,h in f['files'].items():assert sha256_file(OUT/n)==h;guards.append(OUT/n)
        for n,h in f['source_files'].items():assert sha256_file(PROJECT/n)==h;guards.append(PROJECT/n)
    save('dataset_freeze.json',dict(status='FROZEN_BEFORE_PARAMETER_UPDATES',dataset_identity=digest(merged),
        files={str(p.relative_to(PROJECT)):sha256_file(p) for p in sorted(set(guards))},
        repairs=repair_selection['selected'],new_human_labels=0,API_usd=0))
    print(json.dumps(dict(accepted=len(merged),coverage=cov),ensure_ascii=False))


if __name__=='__main__':main()
