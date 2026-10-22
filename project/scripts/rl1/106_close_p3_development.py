#!/usr/bin/env python3
"""Reproducible offline closeout from previously opened development records."""
import argparse
from collections import Counter
import difflib
import json
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.calibration_intake import accept_label
from metacom_pm.rl1.calibration_workflow import bind_measurement, stamp
from metacom_pm.rl1 import judge_completion as original, judge_completion_candidate as candidate
from metacom_pm.rl1.schema import digest


def read(p): return json.loads(p.read_text())


def save(p, value):
    with p.open('x') as f: f.write(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    base=PROJECT/'outputs/pm_rl1';p3=base/'completion_20260930_v2/P3';cal=p3/'calibration'
    prior=base/'human_acceptance_20261014_v2/intake'
    notes=base/'human_acceptance_20261014_v3_notes/review'
    comparisons=read(prior/'development_comparisons_private.json')
    audit=read(prior/'development_item_audit_private.json')
    alignments=read(notes/'analyst_source_alignments_private.json')
    forms={s:read(cal/f'{s}_form.json') for s in ('rater_1','rater_2')}
    maps={s:read(cal/f'{s}_map_private.json') for s in forms}
    jobs=read(p3/'candidate_v1/jobs_private.json');by_job={j['job_id']:j for j in jobs}
    pairs={p['pair_id']:p for p in read(cal/'pairs_private.json')['pairs']}
    records=[]
    for row in audit:
        slot=row['slot'];form=forms[slot];item=next(i for i in form['items'] if i['item_id']==row['item_id'])
        meta=maps[slot][row['item_id']]
        if meta['group']!='development':raise ValueError('only already-opened development rows permitted')
        c=next(c for c in comparisons if c['pair_id']==row['pair_id'])
        source=read(prior/f'{slot}_development_original_private.json')
        label=next(l for l in source['labels'] if l['item_id']==item['item_id'])
        if label!=row['label']:raise ValueError('raw audit/original mismatch')
        pair=pairs[meta['pair_id']];evidence=by_job[c['scores'][0]['job_id']]['evidence']
        if item['A']!=pair['replies'][int(meta['swapped'])] or item['B']!=pair['replies'][1-int(meta['swapped'])]:
            raise ValueError('A/B text mapping mismatch')
        provenance=dict(source['provenance'],observation_origin='Chen-saved-browser-record')
        if slot=='rater_2':provenance.update(kind='user_declared_identical_copy',derived_from='Chen',reason_frame='Chen')
        annotations=[]
        if slot=='rater_1':
            for a in alignments:
                if a['pair_id']!=row['pair_id']:continue
                annotations.append(dict(field='reason',span=a['human_span'],meaning=a['relation'],
                    side=a['side'],reply_span=a['reply_span'],sources=a['sources'],
                    author='assistant_source_alignment',source_confirmed=False,
                    source_file=str(notes/'analyst_source_alignments_private.json')))
            if c['Chen_order']==6:
                annotations.append(dict(field='reason',span='感觉不是很自然，逻辑也不对',
                    meaning='表达及逻辑质疑；不额外推导事实矛盾或严重程度。',author='assistant_notes_review'))
            if c['Chen_order']==14:
                annotations.append(dict(field='quote_A',span=label['quote_A'],
                    meaning='备注被放入quote_A；是偏好B的表达理由，不是A的逐字引文。',author='assistant_notes_review'))
        # The same uncertainty sentence is copied in Du's reason; preserve that
        # reference frame and provenance rather than treating it as new evidence.
        if c['Chen_order']==16:
            annotations.append(dict(field='reason',span='我无法判断这种回复是否贴切',
                recover_preference='uncertain',meaning='明确无法判断贴切性；不恢复A/B，也不取消原severe。',
                author='assistant_notes_review'))
        result=accept_label(label,item,meta,evidence,reviewer=row['reviewer'],provenance=provenance,
            annotations=annotations,reason_frame='Chen',
            raw_source=dict(path=str(prior/f'{slot}_development_original_private.json'),
                            sha256=sha256_file(prior/f'{slot}_development_original_private.json')))
        records.append(result)
    save(out/'development_intake_private.json',records)
    protocol=read(p3/'candidate_v1/protocol.json')
    runtime_dir=Path(read(p3/'candidate_v1/development_pointer.json')['run_dir'])
    runtime=read(runtime_dir/'runtime.json');summary=read(runtime_dir/'summary.json')
    bound=[];raw_audit=[];receipts={}
    for row in summary['rows']:
        job=by_job[row['job_id']]
        if job['group'] not in ('development','recheck_probe'):raise ValueError('sealed score unexpectedly present')
        paths=[runtime_dir/(row['request_id']+suffix) for suffix in ('.request.json','.raw.json','.measurement.json')]
        request,raw,measurement=map(read,paths)
        b=bind_measurement(job,request,raw,measurement,runtime=runtime,protocol=protocol,
                           scorer=original,cache_hit=row['cache_hit'])
        bound.append(b);receipts.update({str(p):sha256_file(p) for p in paths})
        if job['group']=='development':
            c=next(c for c in comparisons if any(s['job_id']==job['job_id'] for s in c['scores']))
            canonical=next(i for i,s in enumerate(c['scores']) if s['job_id']==job['job_id'])
            chen_map=maps['rater_1'][c['Chen_item_id']]
            side='A' if canonical==int(chen_map['swapped']) else 'B'
            raw_audit.append(dict(Chen_order=c['Chen_order'],pair_id=c['pair_id'],Chen_side=side,
                job_id=job['job_id'],request_id=request['request_id'],reply=job['reply'],
                evidence_identity=digest(job['evidence']),q=measurement['q'],m=measurement['m'],
                utility=measurement['candidate_utility'],
                original_final_json=json.loads(raw['text'].split('</think>')[-1].strip()),
                parsed_source_resolved=measurement['parsed'],paths=list(map(str,paths))))
    save(out/'development_scores_bound.json',bound)
    save(out/'original_judge_audit_private.json',sorted(raw_audit,key=lambda r:(r['Chen_order'],r['Chen_side'])))
    save(out/'source_receipts.json',receipts)
    chen=[r for r in records if r['reviewer']=='Chen']
    stats=dict(development_pairs=len(chen),independent_observation_origins=1,
        substantive_notes=sum(bool(r['raw_label']['reason'].strip()) for r in chen),
        preferences=dict(Counter(r['preference']['canonical'] for r in chen)),
        directly_recorded_preference=15,narrative_uncertain=1,comparable_preference=15,
        strict_original_labels=sum(r['original_strict_error'] is None for r in chen),
        risks=dict(Counter(str(r['risks'][s]['level']) for r in chen for s in ('A','B'))),
        risk_evidence_complete=sum(r['risks'][s]['evidence_complete'] for r in chen for s in ('A','B')),
        analyst_aligned_factual_items=[10,15],new_human_severity_values=0,
        reward_qualified=False,real_validation_labels_opened_this_run=0,model_calls=0)
    save(out/'intake_summary.json',stats)
    ledger=[dict(state='recheck_probe',job_id=j['job_id'],applied_semantic_revision=False)
            for j in jobs if j['group']=='recheck_probe']
    ledger.append(dict(state='proposed',from_protocol_identity=protocol['identity'],
                      candidate_rubric_identity=candidate.RUBRIC_ID,applied_semantic_revision=False))
    save(out/'revision_history.json',dict(events=ledger,actual_post_human_revisions=0,
        evidence=dict(frozen_protocol_count=protocol['semantic_revisions_after_human_labels'],
            runtime_identity=runtime['identity'],verified_original_requests=len(bound),
            history_scope='current frozen P3 candidate and its recorded local runs; older pilot revisions are separate identities'),
        proposed_revision_requires_confirmation=True))
    (out/'candidate_prompt.diff').write_text(''.join(difflib.unified_diff(original.RUBRIC.splitlines(True),
        candidate.RUBRIC.splitlines(True),fromfile='frozen_v1_system_prompt',tofile='PROPOSED_v2_system_prompt')))
    (out/'candidate_system_prompt.txt').write_text(candidate.RUBRIC)
    save(out/'candidate_metadata.json',dict(status='PROPOSED_NOT_ENABLED_NOT_FROZEN',
        version=candidate.VERSION,rubric_identity=candidate.RUBRIC_ID,parser_identity='unchanged parser semantics',
        q_m_formula_changed=False))
    context=dict(p3=str(p3),development_intake=str(out/'development_intake_private.json'),
        contract=str(PROJECT/'docs/pm_rl1_completion_20260930_v2/execution_contract.json'),
        protocol=str(p3/'candidate_v1/protocol.json'),runtime=str(runtime_dir/'runtime.json'),
        revision_events=[],raters=['Chen'])
    save(out/'workflow_context.json',context)
    save(out/'reproduction_receipt.json',dict(git_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip(),
        script_sha256=sha256_file(Path(__file__)),outputs={p.name:sha256_file(p) for p in out.iterdir() if p.is_file()},
        model_calls=0,real_validation_decryptions=0))
    print(json.dumps(stats,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out.resolve())
