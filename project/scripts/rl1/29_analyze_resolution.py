#!/usr/bin/env python3
"""Reproduce all completed judge parses and summarize the bounded resolution."""
import collections
import json
from pathlib import Path
import sqlite3
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.judge_indexed import parse_indexed
from metacom_pm.rl1.judge_scoped import parse_scoped

OUT=PROJECT/'outputs/pm_rl1/measurement_resolution_20260929_v1'
PILOT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'


def read(path): return json.loads(path.read_text())


def load_run(pointer,count):
    p=read(OUT/pointer);folder=Path(p['run_dir']);s=read(folder/'summary.json')
    assert sha256_file(folder/'summary.json')==p['summary_sha256']
    assert len(s['rows'])==count and len({r['job_id'] for r in s['rows']})==count
    with sqlite3.connect(folder/'attempts.sqlite') as db:
        statuses=dict(db.execute('select status,count(*) from attempts group by status'))
    assert sum(statuses.values())==count and not statuses.get('RUNNING',0)
    return folder,s,statuses


def measurement(pointer,jobs,count,parser):
    folder,summary,attempts=load_run(pointer,count);rows=summary['rows']
    lookup={j['job_id']:j for j in jobs}
    assert set(lookup)=={r['job_id'] for r in rows}
    for r in rows:
        j=lookup[r['job_id']];raw=read(folder/(r['request_id']+'.raw.json'))
        saved=read(folder/(r['request_id']+'.measurement.json'))
        replay=parser(raw['text'],evidence=j['evidence'],reply=j['reply'],runtime_identity=raw['runtime_identity'],
                      draw_id=j['draw_id'],finish_reason=raw['finish_reason'])
        assert saved==replay,r['request_id']
    groups={}
    for condition in sorted({r['condition'] for r in rows if r['repeat']==0}):
        rs=[r for r in rows if r['condition']==condition and r['repeat']==0]
        valid=[r for r in rs if r['measurement_status']=='measured_candidate']
        groups[condition]=dict(planned=len(rs),valid=len(valid),q_counts=dict(collections.Counter(str(r['q']) for r in valid)),
                               m_counts=dict(collections.Counter(str(r['m']) for r in valid)))
    pilot=[r for r in rows if r.get('exam_section','pilot')=='pilot']
    pairs=[]
    for i in range(1,13):
        p={r['condition']:r for r in pilot if r['pilot_index']==i and r['repeat']==0}
        for other in ('ON','damage','style'):
            a=p.get('OFF');b=p.get(other)
            valid=a and b and a['measurement_status']==b['measurement_status']=='measured_candidate'
            pairs.append(dict(pilot_index=i,comparison='OFF/'+other,available=bool(a and b),valid=bool(valid),
                 delta_q=b['q']-a['q'] if valid else None,delta_m=b['m']-a['m'] if valid else None,
                 delta_utility=(b['q']-a['q'])/4-(b['m']-a['m']) if valid else None))
    repeats=[]
    for r in pilot:
        if not r['repeat']:continue
        j=lookup[r['job_id']]
        b=next(b for b in pilot if lookup[b['job_id']]['item_id']==j['item_id'] and not b['repeat'])
        valid=r['measurement_status']==b['measurement_status']=='measured_candidate'
        repeats.append(dict(pilot_index=r['pilot_index'],condition=r['condition'],valid=valid,
             delta_q=r['q']-b['q'] if valid else None,delta_m=r['m']-b['m'] if valid else None,
             delta_utility=(r['q']-b['q'])/4-(r['m']-b['m']) if valid else None))
    return dict(calls=count,states=dict(collections.Counter(r['measurement_status'] for r in rows)),
                stop_reasons=dict(collections.Counter(r['finish_reason'] for r in rows)),
                errors=dict(collections.Counter(r['error'] for r in rows if r.get('error'))),
                groups=groups,pairs=pairs,repeats=repeats,attempt_states=attempts,
                load_seconds=summary['load_seconds'],engine_wall_seconds=summary['engine_wall_seconds'],
                output_tokens=sum(r['output_tokens'] for r in rows),all_parses_reproduced=True,
                run_dir=str(folder),rows=rows,reward_eligible=False)


def main():
    original=read(PILOT/'exam_private.json');common=read(OUT/'scoped_common_exam_private.json')
    v2=measurement('indexed_pilot_pointer.json',original['jobs'],55,parse_indexed)
    v3=measurement('scoped_common_v3_pointer.json',common['jobs'],67,parse_scoped)
    coverage=[];keys=read(OUT/'coordinator_only/coverage_keys.json')
    for i,k in enumerate(keys,1):
        rs={r['condition']:r for r in v3['rows'] if r['exam_section']=='coverage' and r['pilot_index']==i}
        clean=rs['supported_or_respectful'];bad=rs['targeted_change']
        valid=clean['measurement_status']==bad['measurement_status']=='measured_candidate'
        coverage.append(dict(category=k['category'],valid=valid,
             clean_q=clean['q'],clean_m=clean['m'],changed_q=bad['q'],changed_m=bad['m'],
             q_change=bad['q']-clean['q'] if valid else None,m_change=bad['m']-clean['m'] if valid else None,
             standard='assistant-authored directional hypothesis, not independent accuracy'))
    diagnostics={}
    for name in ('compass_review','compass_review_simple'):
        folder,s,attempts=load_run(name+'_pointer.json',12)
        diagnostics[name]=dict(calls=12,states=dict(collections.Counter(r['measurement_status'] for r in s['rows'])),
              finishes=dict(collections.Counter(r['finish_reason'] for r in s['rows'])),
              verdicts=dict(collections.Counter(r.get('pairwise') for r in s['rows'])),
              engine_wall_seconds=s['engine_wall_seconds'],load_seconds=s['load_seconds'],attempt_states=attempts,
              rows=[dict(item_id=r['job_id'],**read(folder/(r['request_id']+'.measurement.json'))) for r in s['rows']],
              human_review=False,shared_qwen_lineage=True)
    simple=diagnostics['compass_review_simple'];lookup={r['item_id']:r for r in simple['rows']}
    controls=[]
    for k in keys:
        expected=next(label for label,variant in k['label_to_variant'].items() if variant=='supported_or_respectful')+'_better'
        actual=(lookup[k['item_id']].get('verdict') or {}).get('pairwise')
        controls.append(dict(category=k['category'],assistant_hypothesis=expected,verdict=actual,agrees=expected==actual))
    simple['control_directions']=controls
    simple['always_A_hypothesis_agreement']=sum(r['assistant_hypothesis']=='A_better' for r in controls)
    simple['model_hypothesis_agreement']=sum(r['agrees'] for r in controls)
    simple['label_rationale_conflict']=dict(category='historical_only_relationship',
         finding='returned label A_better, while rationale says A misidentifies Eliza and explicitly concludes B is better',
         provenance='coordinator semantic audit; original model verdict not corrected')
    e0={name:read(OUT/name/'summary.json') for name in ('e0','e0_initialized','e0_value_initialized')}
    before=read(OUT/'preexisting_files.json')
    changed=[p for p,h in before.items() if not (PROJECT.parent/p).exists() or sha256_file(PROJECT.parent/p)!=h]
    assert not changed,changed
    result=dict(status='MEASUREMENT_RESOLUTION_COMPLETED_SCOPE_DECISION_REQUIRED_IN_REPORT',v2=v2,v3=v3,
         coverage=coverage,independent_model_diagnostics=diagnostics,e0=e0,
         physical_judge_calls=55+67+12+12,generator_calls=0,paid_API_usd=0,human_submissions=0,
         real_semantic_PM_training_updates=0,executor_LoRA_updates=0,
         preexisting_files_preserved=len(before),training_reward_labels_created=0,
         source_hashes={str(f.relative_to(PROJECT)):sha256_file(f) for f in [PILOT/'exam_private.json',
             OUT/'coverage_exam_private.json',OUT/'scoped_common_exam_private.json',OUT/'scoped_revision_freeze.json']},
         script_sha256=sha256_file(Path(__file__)))
    dest=OUT/'analysis.json';dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(v2=v2['states'],v3=v3['states'],coverage=coverage,physical_judge_calls=146,
                         preexisting_files_preserved=len(before)),ensure_ascii=False))


if __name__=='__main__':main()
