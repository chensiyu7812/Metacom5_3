#!/usr/bin/env python3
"""Freeze eight unrun review sheets, or recheck the original SC36 on CPU."""
from pathlib import Path
import argparse
import ast
import hashlib
import html
import json
import secrets
import sys
from collections import Counter


def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rows(path):return [json.loads(s) for s in Path(path).read_text().splitlines() if s]
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
def save_rows(path,value):Path(path).write_text(''.join(json.dumps(v,ensure_ascii=False,sort_keys=True)+'\n' for v in value))


def freeze(args,E):
    bundle=Path(args.bundle);out=Path(args.out);out.mkdir(parents=True,exist_ok=False,mode=0o700)
    manifest=json.loads((bundle/'MANIFEST_PRIVATE.json').read_text())
    for name,h in manifest['files'].items():
        if file_sha(bundle/name)!=h:raise ValueError('source bundle file changed')
    tasks=rows(bundle/'TASKS.runtime.jsonl');specs=rows(bundle/'EVALSPEC.private.jsonl');pools=rows(bundle/'LEGAL_POOLS_PRIVATE.jsonl')
    bytask={t['task_id']:t for t in tasks};byeval={e['task_id']:e for e in specs};bypool={p['task_id']:p for p in pools}
    channels={t:('natural_support' if e['channel']=='natural' else e['channel']) for t,e in byeval.items()}
    selected=E.select_blind([t['task_id'] for t in tasks],channels);salt=secrets.token_hex(32)
    templates=[];keys=[];packets={};readable=['# GE2: PRIVATE blind-label review templates',
        'No generated outputs exist. All eight records are unrun and unreviewed. Reviewer is unassigned.',
        'This is not a new independent human reference. Do not send private source materials outside the authorized workspace.',
        'Methods, costs and paired outcomes are withheld. Common legal source packets are identical across conditions.']
    for task_id,arm in selected:
        task=bytask[task_id];ev=byeval[task_id]
        packet=dict(task=task,evaluation=ev,legal_source_records=bypool[task_id]['records'],
            review_only_not_runtime=True,delivery_audit='actual per-condition delivery withheld for first content review; separate sidecar after outputs')
        h=E.sha(packet);case='ge2blind:'+E.sha([salt,task_id,arm])[:20]
        row=E.review_template(case_id=case,task=task,evaluation=ev,channel=channels[task_id],source_packet_sha256=h)
        E.validate_review(row,task=task,evaluation=ev,source_packet_sha256=h)
        templates.append(row);keys.append(dict(case_id=case,task_id=task_id,arm=arm,source_packet_sha256=h))
        packets[h]=packet
    templates.sort(key=lambda r:r['case_id']);keys.sort(key=lambda r:r['case_id'])
    for h,packet in packets.items():
        save(out/('SOURCE_PACKET_'+h+'.private.json'),packet)
        task=packet['task'];ev=packet['evaluation']
        readable.extend(['\n## Common task/source packet '+h,'\nVisible conversation and query:',json.dumps(task['turns'],ensure_ascii=False,indent=2),
            '\nOriginal requirements and references (review-only):',json.dumps(ev,ensure_ascii=False,indent=2),
            '\nComplete legal source records (not necessarily delivered to each method):'])
        for i,r in enumerate(packet['legal_source_records'],1):
            readable.extend(['\n### Legal source '+str(i)+' / reported '+str(r['reported_at']),r['reading_text']])
    for row in templates:
        readable.extend(['\n## Output case '+row['case_id'],'Common source packet: '+row['source_packet_sha256'],
            '\nACTUAL OUTPUT: [NOT GENERATED / NO TEXT TO REVIEW]',
            '\nReviewer identity/kind, authoring exposure, prior output exposure, timestamp: [UNASSIGNED]',
            '\nReview each requested proposition, source/subject/time/stage, allowed alternatives and explicit constraints.',
            'Do not infer goal completion from a citation, call count or source coverage. Optional memories need not be repeated.',
            'Output spans use untrimmed original text offsets; preserve unknown/reference disputes and any extra personal assertions.',
            '\nBlank machine-readable review:',json.dumps(row,ensure_ascii=False,indent=2)])
    save_rows(out/'BLIND_REVIEW_TEMPLATES_PRIVATE.jsonl',templates)
    save(out/'BLIND_KEY_PRIVATE.json',dict(salt=salt,selection=keys,unblind_only_after_review_freeze=True))
    (out/'BLIND_REVIEW_READABLE_PRIVATE.md').write_text('\n'.join(readable)+'\n')
    save(out/'GE2_EVALUATION_CONTRACT.json',E.contract())
    summary=dict(protocol=E.PROTOCOL,planned_outputs=8,selected_tasks=[byeval[t]['task_alias'] for t in dict(selected)],
        normal_arms=list(E.NORMAL_ARMS),templates_valid=8,actual_outputs=0,semantic_observations=0,
        reviewer_status='unassigned',independent_human_reviews=0,old_five_human_items='pending_unchanged',
        contract_sha256=E.sha(E.contract()),source_bundle_manifest_sha256=file_sha(bundle/'MANIFEST_PRIVATE.json'),
        task_order_sha256=E.sha([t['task_id'] for t in tasks]),selection_key_file_sha256=file_sha(out/'BLIND_KEY_PRIVATE.json'),
        model_calls=0,gpu_calls=0,api_calls=0,training_calls=0,formal_reward=None,
        output_absence='no replacement of missing/unexecuted outputs; DirectEvidence remains separate development diagnostic')
    save(out/'BLIND_REVIEW_FREEZE_PUBLIC.json',summary)
    save(out/'MANIFEST_PUBLIC.json',dict(protocol=E.PROTOCOL,
        source_manifest_sha256=file_sha(bundle/'MANIFEST_PRIVATE.json'),implementation_sha256=file_sha(E.__file__),
        script_sha256=file_sha(__file__),files_sha256={p.name:file_sha(p) for p in out.iterdir() if p.is_file()},formal_reward=None))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def structured(args,E):
    scorer=Path(args.scorer)
    if file_sha(scorer)!=E.contract()['structured_branch']['scorer_sha256']:raise ValueError('original strict scorer changed')
    node=next(n for n in ast.parse(scorer.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='evaluate')
    scope={'json':json};exec(compile(ast.Module(body=[node],type_ignores=[]),str(scorer),'exec'),scope)
    inputs={str(scorer):file_sha(scorer)};counts={};details=[]
    if len(args.plan)!=len(args.endpoints):raise ValueError('one endpoint file per original plan')
    for planpath,eppath in zip(args.plan,args.endpoints):
        plan=json.loads(Path(planpath).read_text());refs={r['task_id']:r for r in rows(plan['review_path'])}
        requests={r['request_id']:r for r in rows(plan['requests_path'])}
        for p in (planpath,eppath,plan['review_path'],plan['requests_path']):inputs[str(p)]=file_sha(p)
        for endpoint in rows(eppath):
            b=endpoint['binding'];output=endpoint['actual_output'];ref=refs[b['task_id']];request=requests[b['request_id']]
            if E.sha(output)!=endpoint['output_sha256'] or E.sha(ref)!=b['reference_sha256']:raise ValueError('old output/reference binding')
            got=scope['evaluate'](output['text'],ref,arm=b['arm'],delivered_text=html.unescape('\n'.join(m['content'] for m in request['model_input']['messages'])))
            if got!=endpoint['evaluation']['strict_score']:raise ValueError('old score differs')
            count=counts.setdefault(b['arm'],Counter());count['outputs']+=1
            for k in ('value_correct','evidence_correct','epistemic_compliance','task_success'):count[k]+=got[k]
            details.append(dict(task=b['task_id'],arm=b['arm'],value_correct=got['value_correct'],task_success=got['task_success'],errors=got['errors']))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    report=dict(protocol='ge2-existing-sc36-readonly-recheck-v1',rows=len(details),unchanged_old_results=True,
        counts={k:dict(v) for k,v in counts.items()},source_files_sha256=inputs,
        evaluator_loading='unchanged evaluate AST; only json global; no unrelated preparation imports',
        model_calls=0,weights_read=False,GE2_natural_output_scoring=False,formal_reward=None)
    save(out/'SC36_RECHECK_PUBLIC.json',report);save(out/'SC36_RECHECK_TASKWISE_PUBLIC.json',details)
    print(json.dumps({k:v for k,v in report.items() if k!='source_files_sha256'},indent=2))


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='op',required=True)
    f=sub.add_parser('freeze');f.add_argument('--bundle',required=True);f.add_argument('--out',required=True)
    s=sub.add_parser('structured-recheck');s.add_argument('--scorer',required=True)
    s.add_argument('--plan',action='append',required=True);s.add_argument('--endpoints',action='append',required=True);s.add_argument('--out',required=True)
    args=p.parse_args();sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
    from metacom_pm.rl1v3.journal import ge2_evaluation as E
    (freeze if args.op=='freeze' else structured)(args,E)


if __name__=='__main__':main()
