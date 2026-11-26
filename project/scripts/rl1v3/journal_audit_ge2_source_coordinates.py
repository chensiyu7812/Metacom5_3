#!/usr/bin/env python3
"""Read-only source audit of eight GE2 tasks and frozen CPU conditions."""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def rows(path):return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]
def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
def save_rows(path,value):Path(path).write_text(''.join(json.dumps(v,ensure_ascii=False,sort_keys=True)+'\n' for v in value))


def main():
    p=argparse.ArgumentParser()
    for key in ('bundle','cpu','current-review','out'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
    from metacom_pm.rl1v3.journal import ge2_source_coordinate_audit as A
    inputs={}
    def verified_manifest(root,name,field):
        path=root/name;manifest=json.loads(path.read_text());inputs[str(path)]=file_sha(path)
        for filename,sha in manifest[field].items():
            target=root/filename
            if file_sha(target)!=sha:raise ValueError('frozen manifest mismatch: '+filename)
            inputs[str(target)]=sha
    verified_manifest(args.bundle,'MANIFEST_PRIVATE.json','files')
    verified_manifest(args.cpu,'MANIFEST_PRIVATE.json','files')
    config=json.loads((args.bundle/'SOURCE_CONFIG_PRIVATE.json').read_text())
    for path,h in config['source_inputs_sha256'].items():
        if file_sha(path)!=h:raise ValueError('original source identity changed')
        inputs[path]=h
    raw=rows(config['resources_path']);cache={(r['owner_id'],r['parent_session_id']):r for r in raw}
    tasks={r['task_id']:r for r in rows(args.bundle/'TASKS.runtime.jsonl')}
    evals={r['task_id']:r for r in rows(args.bundle/'EVALSPEC.private.jsonl')}
    envs={r['task_id']:r for r in rows(args.bundle/'TASK_ENVELOPES.private.jsonl')}
    pools={r['task_id']:r for r in rows(args.bundle/'LEGAL_POOLS_PRIVATE.jsonl')}
    review=rows(args.current_review);reviews={r['task_id']:r for r in review}
    inputs[str(args.current_review)]=file_sha(args.current_review)
    if set(tasks)!=set(reviews):raise ValueError('eight current context reviews required')
    original_checks=[];reference_checks=[];current_checks=[];task_summaries=[]
    for tid,task in tasks.items():
        ev=evals[tid];pool=pools[tid]['records'];records={r['record_id']:r for r in pool}
        for r in pool:
            original=cache[(r['owner_id'],r['parent_session_id'])]
            if r['source_refs']!=original['source_refs']:raise ValueError('pool source changed from frozen RAW')
            for s in r['source_refs']:
                if A.text_sha(s['exact_quote'])!=s['raw_turn_sha256'] or s['start_char']!=0 or s['end_char']!=len(s['exact_quote']):
                    raise ValueError('original turn content/Unicode extent damaged')
        rv=reviews[tid]
        if rv['task_sha256']!=A.object_sha(task) or rv['evaluation_sha256']!=A.object_sha(ev):raise ValueError('current review input binding')
        if rv['formal_reward'] is not None or rv['semantic_qualification'] is not False:raise ValueError('not a qualified evaluator')
        if [x['visible_turn_index'] for x in rv['visible_turn_observations']]!=list(range(len(task['turns']))):raise ValueError('current turn review coverage')
        for o,t in zip(rv['visible_turn_observations'],task['turns']):
            if o['turn_text_sha256']!=A.text_sha(t['text']) or o['speaker']!=t['role']:raise ValueError('current reviewed role/text binding')
        for atom in ev['required_atoms']:
            # Retain original ordinal vs upstream original_idx rather than conflating them.
            old=atom.get('original_atom',{})
            originals=old.get('source_evidence',[])+([old['source_span']] if 'source_span' in old else [])
            originals += [s for g in old.get('evidence_groups',[]) for s in g['spans']]
            for s in originals:
                owner=s.get('owner_id',old.get('owner'));session=s.get('session_id',old.get('session'))
                source=cache.get((owner,session));idx=s.get('turn_index',s.get('ordinal_turn'))
                original=next((t for t in source['source_refs'] if t['turn_index']==idx),None) if source else None
                ok=bool(original and original['speaker']==s['speaker'] and original['exact_quote'][s['start_char']:s['end_char']]==s['exact_quote']
                        and original['raw_turn_sha256']==s['raw_turn_sha256'])
                original_checks.append(dict(task_id=tid,atom_id=atom['id'],original_reference_sha256=A.object_sha(s),
                    original_idx=s.get('original_idx'),runtime_turn_index=idx,valid=ok))
                if not ok:raise ValueError('original reference coordinate damaged')
            for gi,group in enumerate(atom['sufficient_groups']):
                for si,ref in enumerate(group):
                    loc=A.reference_location(ref,records)
                    reference_checks.append(dict(task_id=tid,atom_id=atom['id'],group_index=gi,span_index=si,reference=ref,location=loc))
                    if loc['valid'] is False:raise ValueError('evaluation original coordinate invalid')
                    for occurrence in A.occurrences(ref,task):
                        derived=dict(occurrence)
                        if ev['channel']=='natural':
                            prefix=envs[tid]['actual_prefix'];pt=prefix['turns'][occurrence['visible_turn_index']]
                            if pt['text']!=task['turns'][occurrence['visible_turn_index']]['text']:raise ValueError('actual prefix visible drift')
                            original=cache[(prefix['owner_id'],prefix['session_id'])]['source_refs'][pt['turn_index']]
                            if original['speaker']!=pt['role'] or original['exact_quote']!=pt['text']:raise ValueError('current original turn mismatch')
                            derived.update(owner_id=prefix['owner_id'],session_id=prefix['session_id'],original_turn_index=pt['turn_index'],
                                original_turn_sha256=original['raw_turn_sha256'])
                        current_checks.append(dict(task_id=tid,atom_id=atom['id'],reference_sha256=A.object_sha(ref),
                            frozen_current_visible=ref.get('current_visible'),occurrence=derived,
                            semantic=A.current_semantic_delivery(ref,task,rv)))
        task_summaries.append(dict(task=ev['task_alias'],channel=ev['channel'],atoms=len(ev['required_atoms']),
            required_atoms=sum(a['requirement_role']=='explicit_answer' for a in ev['required_atoms']),
            historical_reference_instances=sum(x['task_id']==tid and x['location']['valid'] is True for x in reference_checks),
            current_reference_occurrences=sum(x['task_id']==tid for x in current_checks),
            current_review_status=rv['overall_status'],identity_failure=False,task_success=None))
    diagnostics=[];oldmap={(r['task_id'],r['backend']):r for r in rows(args.cpu/'SUPPLY_DIAGNOSTICS_PRIVATE.jsonl') if r['cohort']=='selected8'}
    for ranked in rows(args.cpu/'RANKINGS_PRIVATE.jsonl'):
        if ranked['cohort']!='selected8':continue
        tid=ranked['task_id'];ev=evals[tid];task=tasks[tid];records=pools[tid]['records']
        for variant,item in ranked['variants'].items():
            legacy=A.legacy_supply(ev['required_atoms'],item['delivered'],task['query'])
            frozen=oldmap[(tid,ranked['backend'])]['coverage'][variant]
            if any(legacy[k]!=frozen[k] for k in ('atoms','required_slots','covered_slots','unknown_slots')):
                raise ValueError('old substring reproduction differs')
            strict=A.strict_supply(ev['required_atoms'],records,item['intervals'],task,reviews[tid])
            diagnostics.append(dict(task_id=tid,task=ev['task_alias'],channel=ev['channel'],backend=ranked['backend'],condition=variant,
                legacy=legacy,strict=strict,intervals_sha256=A.object_sha(item['intervals']),
                frozen_cost={k:item[k] for k in ('source_tokens','input_tokens','capacity_reachable')},source_only=True))
    for recipe in rows(args.bundle/'DIRECT_SOURCE_RECIPE_PRIVATE.jsonl'):
        tid=recipe['task_id'];ev=evals[tid];records=pools[tid]['records'];intervals=A.direct_intervals(recipe)
        delivered=[dict(record_id=r['record_id'],text='\n'.join(s['exact_quote'] for s in r['source_refs']
            if any(lo<=s['turn_index']<=hi for lo,hi in intervals.get(r['record_id'],[])))) for r in records]
        diagnostics.append(dict(task_id=tid,task=ev['task_alias'],channel=ev['channel'],backend='direct_source_recipe',condition='DirectEvidence',
            legacy=A.legacy_supply(ev['required_atoms'],delivered,tasks[tid]['query']),
            strict=A.strict_supply(ev['required_atoms'],records,intervals,tasks[tid],reviews[tid]),
            intervals_sha256=A.object_sha(intervals),source_recipe_sha256=A.object_sha(recipe),source_only=True))
    public=[]
    for r in diagnostics:
        public.append(dict(task=r['task'],channel=r['channel'],backend=r['backend'],condition=r['condition'],
            legacy={k:v for k,v in r['legacy'].items() if k!='atoms'},strict={k:v for k,v in r['strict'].items() if k!='atoms'},
            intervals_sha256=r['intervals_sha256'],frozen_cost=r.get('frozen_cost'),source_only=True,task_success=None))
    out=args.out;out.mkdir(parents=True,exist_ok=False,mode=0o700)
    save_rows(out/'ORIGINAL_COORDINATES_PRIVATE.jsonl',original_checks);save_rows(out/'REFERENCE_COORDINATES_PRIVATE.jsonl',reference_checks)
    save_rows(out/'CURRENT_OCCURRENCES_PRIVATE.jsonl',current_checks);save_rows(out/'SUPPLY_COMPARISON_PRIVATE.jsonl',diagnostics)
    save_rows(out/'SUPPLY_COMPARISON_PUBLIC.jsonl',public)
    report=dict(protocol=A.PROTOCOL,base_commit='5440d422110c57cba6567fca216383cd86e838de',tasks=task_summaries,
        original_reference_instances_verified=len(original_checks),historical_reference_instances_verified=sum(x['location']['valid'] is True for x in reference_checks),
        current_reference_occurrences=len(current_checks),conditions=len(diagnostics),old_substring_reproductions=96,
        changed_required_covered_conditions=sum(r['legacy']['covered_slots']!=r['strict']['covered_slots'] for r in diagnostics),
        changed_any_atom_conditions=sum([a['covered'] for a in r['legacy']['atoms']]!=[a['covered'] for a in r['strict']['atoms']] for r in diagnostics),
        run_blocking_identity_damage=False,model_calls=0,weights_read=False,new_generated_outputs_read=0,
        reviewer_identity=sorted({r['reviewer_identity'] for r in review}),review_kind='assistant_development_source_semantics',
        semantic_qualification=False,formal_reward=None,task_success=None,
        limits=['No supplied-source count is generated-answer success.','Current quotes are bounded task premises, not independent proof of real-world execution.',
            'Calendar-derived and absence/unresolved references retain original uncertainty.','Actual run receipts and payloads require separate binding before reuse.'])
    save(out/'COUNTS_PUBLIC.json',report)
    save(out/'MANIFEST_PUBLIC.json',dict(protocol=A.PROTOCOL,inputs_sha256=inputs,
        code_sha256={str(Path(A.__file__)):file_sha(A.__file__),str(Path(__file__)):file_sha(__file__)},
        files_sha256={p.name:file_sha(p) for p in out.iterdir() if p.is_file()},model_calls=0))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
