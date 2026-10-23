#!/usr/bin/env python3
"""Bind P2 exact-input author and source review before any new output."""
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.p2_supervision import REVIEW_INSTRUCTION,CHECKS

OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'
P1=OUT.parent/'P1'
MODEL=Path('/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b')


def main():
    if (OUT/'supervision_freeze.json').exists():raise RuntimeError('already frozen')
    freeze=json.loads((OUT/'slot_freeze.json').read_text())
    for name,h in freeze['files'].items():assert sha256_file(OUT/name)==h,name
    for name,h in freeze['source_files'].items():assert sha256_file(PROJECT/name)==h,name
    slots=json.loads((OUT/'authoring_slots_private.json').read_text())['slots']
    specs=json.loads((P1/'episode_specs_private.json').read_text())
    source=PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    users={u['owner_id']:u for u in json.loads(source.read_text())['users']}
    evidence={};jobs=[]
    for slot in slots:
        spec=specs[slot['index']];p=spec['prefix']
        assert p['owner_id']==slot['owner'] and p['split']==slot['split'] and p['split']!='test'
        sessions={s['session_id']:s for s in users[p['owner_id']]['sessions']}
        current=sessions[p['session_id']]
        assert current['chronological_rank']==p['cutoff_rank']
        # Only prefix content and actually acquired records are visible evidence.
        documents=[dict(id=f'C{i}',scope='VISIBLE',role=t['role'],time='current_session',text=t['content'])
                   for i,t in enumerate(p['turns'])]
        selected=[]
        for head,n in zip(spec['inventory'],slot['counts']):
            for rank,r in enumerate(head[:n],1):
                documents.append(dict(id=f"R{r['head']}{rank}",scope='VISIBLE',head=r['head'],
                                      time=r['source_time'],text=r['content']))
                selected.append(r['candidate_id'])
                if r['head']=='RS':continue
                sid=r['source_ids'][0] if r['head']=='MS' else r['source_ids'][1]
                session=sessions[sid]
                assert session['chronological_rank']==r['source_rank']<p['cutoff_rank']
                assert session['timestamp']==r['source_time'] and r['owner_id']==p['owner_id']
                for t in session['turns']:
                    documents.append(dict(id=f"S{r['head']}{rank}T{t['idx']}",scope='SOURCE',
                        role=t['role'],time=session['timestamp'],text=t['content']))
        assert selected==slot['candidate_ids']
        evidence[slot['slot_id']]=dict(current_date=p['timestamp'],documents=documents,
            documents_identity=digest(documents),visible_messages_identity=digest(slot['messages']))
        jobs.append(dict(slot_id=slot['slot_id'],index=slot['index'],split=slot['split'],
            category=slot['category'],prefix_identity=slot['prefix_identity'],attempt=0,seed=17,
            messages=slot['messages'],renderer_identity=freeze['renderer_identity']))
    prior=json.loads((PROJECT/'outputs/pm_rl1/executor_coverage_20260929_v1/author_pointer.json').read_text())
    old=json.loads((Path(prior['run_dir'])/'runtime.json').read_text())
    model_files={p.name:sha256_file(p) for p in sorted(MODEL.iterdir())
        if p.is_file() and p.suffix in ('.json','.safetensors','.jinja','.txt')}
    assert model_files==old['files'],'existing local model changed'
    protocol=dict(version='p2-source-bound-weak-supervision-v1',model=str(MODEL),model_files=model_files,
        packages=old['packages'],native_context=old['native_context'],
        author_decode=old['decode'],review_decode=dict(old['decode'],purpose='source admission only; not reward',
            visible_input='exact candidate input plus acquired-source originals and candidate reply',temperature=0.0,
            top_p=1.0,top_k=-1,presence_penalty=0.0),
        review_prompt=REVIEW_INSTRUCTION,review_checks=CHECKS,
        author_initial=684,author_repairs_max=dict(train=80,dev=16),per_slot_max_repairs=1,
        review_initial_max=684,review_repair_max=96,review_semantic_retries=0,
        repair_selection='Fixed hash pm-rl1-p2-repair-v1 + slot_id within each split; eligible only after source-bound review; one repair max',
        admission='Strict natural completion, exact quote/schema bindings, all checks true, no uncertain material claim; AI weak targets only',
        coordinator_audit='36 prospectively hashed slots (3 per category/split), plus known index102 OFF; all observed review mistakes are recorded, never hidden',
        independence='Author and automated source reviewer share Qwen weights; correlated errors possible; no reward qualification',
        no_claim='Quotes check provenance, not entailment or completeness; accepted weak supervision is not human truth',
        paid_API_usd=0,test_access=False,human_tasks=0)
    audit=[]
    for split in ('train','dev'):
        for category in ('OFF','single','cross_two','same_two','three','four'):
            rows=[s for s in slots if s['split']==split and s['category']==category]
            audit.extend(s['slot_id'] for s in sorted(rows,key=lambda s:digest(['p2-coordinator-audit-v1',s['slot_id']]))[:3])
    known=next(s['slot_id'] for s in slots if s['index']==102 and s['category']=='OFF')
    audit=sorted(set(audit+[known]))
    def save(name,obj):
        with (OUT/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    save('supervision_protocol.json',protocol)
    save('source_evidence_private.json',evidence)
    save('author_jobs_private.json',jobs)
    save('coordinator_audit_slots.json',dict(slot_ids=audit,labels='pending; AI development audit, not human gold'))
    guards=[source,OUT/'slot_freeze.json',OUT/'authoring_slots_private.json',P1/'episode_specs_private.json',
        PROJECT/'src/metacom_pm/rl1/p2_supervision.py',PROJECT/'scripts/rl1/82_run_p2_local_jobs.py',Path(__file__)]
    save('supervision_freeze.json',dict(status='FROZEN_BEFORE_AUTHOR_GENERATION',
        files={name:sha256_file(OUT/name) for name in ('supervision_protocol.json','source_evidence_private.json','author_jobs_private.json','coordinator_audit_slots.json')},
        source_files={str(p.relative_to(PROJECT)):sha256_file(p) for p in guards},
        input_slots=684,source_evidence_count=len(evidence),coordinator_audit_slots=len(audit),
        author_calls=0,review_calls=0,accepted_targets=0))
    print(json.dumps(dict(status='FROZEN',slots=684,audit_slots=len(audit),model_files_verified=True)))


if __name__=='__main__':main()
