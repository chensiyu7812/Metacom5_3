#!/usr/bin/env python3
"""Explicit local P3 commands. Default operations never load a model or key.

freeze and receive are deliberately separate commands. Outputs are write-once.
No command starts training or grants automatic training authorization.
"""
import argparse
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.calibration_workflow import (make_freeze, require_freeze, receive_sealed,
    qualify, bind_measurement, stamp, verify_identity)
from metacom_pm.rl1.human_calibration import strict_json, decrypt_item
from metacom_pm.rl1 import judge_completion, judge_completion_candidate
from metacom_pm.rl1.schema import digest


def read(p): return strict_json(Path(p).read_text())


def save(p,v):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    with Path(p).open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def load_inputs(context):
    c=read(context);p3=Path(c['p3']);cal=p3/'calibration'
    pf=read(cal/'packet_freeze.json')
    # Never expose/copy key bytes or its hash. Other frozen files are verified.
    for name,h in pf['files'].items():
        if name.endswith('.pem'):continue
        if sha256_file(cal/name)!=h:raise ValueError('packet file changed: '+name)
    candidate=p3/'candidate_v1';cf=read(candidate/'candidate_freeze.json')
    for name,h in cf['files'].items():
        if sha256_file(candidate/name)!=h:raise ValueError('initial candidate artifact changed: '+name)
    for name,h in cf['source_files'].items():
        if sha256_file(PROJECT/name)!=h:raise ValueError('initial candidate source changed: '+name)
    code_files=[Path(__file__),PROJECT/'scripts/rl1/108_run_p3_acceptance_batch.py']
    code_files.extend(PROJECT/f'src/metacom_pm/rl1/{s}.py' for s in (
        'calibration_workflow','calibration_intake','calibration_decision','natural_runner',
        'judge_completion','judge_completion_candidate','human_calibration','schema'))
    review=read(c['development_score_review']) if c.get('development_score_review') else stamp(dict(status='DEVELOPMENT_REVIEW_PENDING'))
    verify_identity(review)
    for name,h in review.get('source_files',{}).items():
        if sha256_file(Path(name))!=h:raise ValueError('development score review source changed')
    inputs=dict(packet=dict(packet_identity=pf['packet_identity'],packet_freeze_sha256=sha256_file(cal/'packet_freeze.json')),
        forms={s:read(cal/f'{s}_form.json') for s in ('rater_1','rater_2')},
        maps={s:read(cal/f'{s}_map_private.json') for s in ('rater_1','rater_2')},
        pairs=read(cal/'pairs_private.json'),jobs=read(candidate/'jobs_private.json'),
        pair_score_map=read(candidate/'pair_score_map_private.json'),
        development_intake=read(c['development_intake']),contract=read(c['contract']),
        development_score_review=review,
        protocol=read(c['protocol']),runtime=read(c['runtime']),
        code={str(p.relative_to(PROJECT)):sha256_file(p) for p in code_files})
    return c,inputs


def select_scorer(protocol):
    for scorer in (judge_completion,judge_completion_candidate):
        if protocol['version']==scorer.VERSION and protocol['rubric_identity']==scorer.RUBRIC_ID:
            return scorer
    raise ValueError('unknown scorer version; no implicit substitution')


def main(args):
    c,inputs=load_inputs(args.context)
    if args.command in ('draft','freeze'):
        result=make_freeze(inputs,raters=c['raters'],revision_events=c['revision_events'])
        if args.command=='freeze':
            # Researcher reviews the exact draft identity, not a generic yes/no.
            if args.reviewed_draft_identity!=result['identity']:
                raise ValueError('reviewed draft identity mismatch')
            result=make_freeze(inputs,raters=c['raters'],revision_events=c['revision_events'],final=True)
        save(args.out,result)
    elif args.command=='receive':
        freeze=read(args.freeze);require_freeze(freeze,inputs)
        provenance=read(args.provenance)
        # Key deserialization occurs only after receive_sealed's guards and at
        # the first authorized validation envelope; no key is printed or saved.
        key=[]
        def decrypt(envelope,**bindings):
            if not key:
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                key.append(load_pem_private_key(Path(args.key).read_bytes(),password=None))
            return decrypt_item(envelope,key[0],**bindings)
        result=receive_sealed(read(args.submission),slot=args.slot,reviewer=args.reviewer,
            provenance=provenance,freeze=freeze,inputs=inputs,decrypt=decrypt)
        save(args.out,result)
    elif args.command=='import-scores':
        scorer=select_scorer(inputs['protocol']);jobs={j['job_id']:j for j in inputs['jobs']}
        results=[]
        for run in args.run:
            run=Path(run)
            summary=read(run/'summary.json')
            for row in summary['rows']:
                job=jobs[row['job_id']]
                if job['group']=='recheck_probe':continue
                if job['group']!='development':require_freeze(read(args.freeze),inputs)
                rid=row['request_id']
                results.append(bind_measurement(job,read(run/(rid+'.request.json')),read(run/(rid+'.raw.json')),
                    read(run/(rid+'.measurement.json')),runtime=inputs['runtime'],protocol=inputs['protocol'],
                    scorer=scorer,cache_hit=row['cache_hit']))
        save(args.out,results)
    elif args.command=='close-development':
        scorer=select_scorer(inputs['protocol']);run=Path(args.run)
        jobs={j['job_id']:j for j in inputs['jobs'] if j['group'] in ('development','recheck_probe')}
        summary=read(run/'summary.json');rows=summary['rows'];bound=[];sources={str(run/'summary.json'):sha256_file(run/'summary.json')}
        if len(rows)!=len(jobs) or {r['job_id'] for r in rows}!=set(jobs):raise ValueError('complete development measurements required')
        for row in rows:
            paths=[run/(row['request_id']+suffix) for suffix in ('.request.json','.raw.json','.measurement.json')]
            req,raw,measurement=map(read,paths)
            bound.append(bind_measurement(jobs[row['job_id']],req,raw,measurement,runtime=inputs['runtime'],
                protocol=inputs['protocol'],scorer=scorer,cache_hit=row['cache_hit']))
            sources.update({str(p):sha256_file(p) for p in paths})
        note=read(args.review_note)
        if note.get('decision')!='accept_for_sealed_evaluation' or not note.get('reviewer_identity') or not note.get('reason'):
            raise ValueError('explicit development review note required; format validity is not semantic acceptance')
        unresolved=[r['job_id'] for r in bound if r['measurement_status']!='measured_candidate']
        if unresolved:raise ValueError('development semantic/technical pending results remain')
        sources[str(Path(args.review_note).resolve())]=sha256_file(Path(args.review_note))
        result=stamp(dict(status='DEVELOPMENT_REVIEW_CLOSED',protocol_identity=inputs['protocol']['identity'],
            runtime_identity=inputs['runtime']['identity'],job_ids=list(jobs),unresolved_measurements=[],
            scores_identity=digest(bound),review_note=note,source_files=sources,reward_qualified=False))
        save(args.out,result)
        save(args.context_out,dict(c,development_score_review=str(Path(args.out).resolve())))
    elif args.command=='qualify':
        result=qualify(freeze=read(args.freeze),inputs=inputs,intakes=[read(p) for p in args.intake],
            scores=[s for p in args.scores for s in read(p)],
            confirmations=read(args.confirmations) if args.confirmations else [])
        save(args.out,result)
    elif args.command=='batch-plan':
        if args.phase=='validation':require_freeze(read(args.freeze),inputs)
        groups=('development','recheck_probe') if args.phase=='development' else ('validation','repeat')
        jobs=[j for j in inputs['jobs'] if j['group'] in groups]
        limit=inputs['contract']['measurement']['calibration_scorer_requests_max']
        if args.previous_calls<0 or args.previous_calls+len(jobs)>limit:raise ValueError('calibration request allowance exceeded')
        scorer=select_scorer(inputs['protocol']);requests=[]
        for j in jobs:
            messages,schema=scorer.messages_and_schema(j['evidence'],j['reply'],recheck=j['recheck'])
            payload=dict(messages=messages,json_schema=schema,executor_identity=inputs['runtime']['identity'],
                score_identity=digest(dict(evidence=j['evidence'],reply=j['reply'],rubric=scorer.RUBRIC_ID,
                    runtime=inputs['runtime']['identity'],recheck=j['recheck'],repeat_draw=j['draw_id'] if j['repeat'] else None)),
                draw_identity=j['draw_id'],seed=j['seed'],attempt=0)
            requests.append(dict(job_id=j['job_id'],request_id=digest(payload),**payload))
        result=stamp(dict(phase=args.phase,context=str(Path(args.context).resolve()),
            freeze_identity=read(args.freeze)['identity'] if args.phase=='validation' else None,
            freeze_path=str(Path(args.freeze).resolve()) if args.freeze else None,
            protocol_identity=inputs['protocol']['identity'],runtime_identity=inputs['runtime']['identity'],
            bindings={k:digest(v) for k,v in inputs.items()},requests=requests,
            previous_calls=args.previous_calls,request_limit=limit,API_usd=0,
            requires_explicit_execution=True))
        save(args.out,result)
    print(json.dumps(dict(command=args.command,output=str(args.out),model_calls=0),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    for name in ('draft','freeze','receive','import-scores','close-development','qualify','batch-plan'):
        s=sub.add_parser(name);s.add_argument('--context',required=True);s.add_argument('--out',type=Path,required=True)
        if name in ('receive','qualify','import-scores','batch-plan'):s.add_argument('--freeze')
        if name=='freeze':s.add_argument('--reviewed-draft-identity',required=True)
        if name=='receive':
            for k in ('submission','slot','reviewer','provenance','key'):s.add_argument('--'+k,required=True)
        if name=='import-scores':s.add_argument('--run',nargs='+',required=True)
        if name=='close-development':
            s.add_argument('--run',required=True);s.add_argument('--review-note',required=True);s.add_argument('--context-out',required=True)
        if name=='qualify':
            s.add_argument('--intake',nargs='+',required=True);s.add_argument('--scores',nargs='+',required=True)
            s.add_argument('--confirmations')
        if name=='batch-plan':
            s.add_argument('--phase',choices=('development','validation'),required=True)
            s.add_argument('--previous-calls',type=int,required=True)
    main(p.parse_args())
