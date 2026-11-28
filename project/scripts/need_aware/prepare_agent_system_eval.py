#!/usr/bin/env python3
"""Reuse the original PM60 + J06's 24 ES-MemEval/Memory×RS tasks; no new sampling programme."""
import argparse,json,shutil
from pathlib import Path
from collections import Counter
from metacom_pm.need_aware.data.contracts import load_runtime
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl,sha_file
from metacom_pm.need_aware.data.response_data import jsonl,key


def run(a):
    old=Path(a.artifacts);j=Path(a.joint_bundle);out=Path(a.out)
    manifest=json.loads((j/'MANIFEST.json').read_text())
    for rel,h in manifest['files_sha256'].items():assert sha_file(j/rel)==h
    jt={x['task_id']:x for x in jsonl(j/'TASKS.runtime.jsonl')}
    envelopes={x['task_id']:x for x in jsonl(j/'TASK_ENVELOPES.private.jsonl')}
    je=jsonl(j/'EVALSPEC.private.jsonl');skills=jsonl(j/'RS_PROCEDURE.private.jsonl')
    pm=load_runtime(old/'runtime/tasks.generation.jsonl')
    pe={x['task_id']:x for x in jsonl(old/'evaluation/tasks.generation.jsonl')}
    runtime=[];specs=[]
    for t in pm:
        dest=out/'runtime/personamem'/t.history_ref;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(old/'runtime'/t.history_ref,dest)
        runtime.append(dict(task_id=t.task_id,source='original_personamem_open60',owner=t.persona_group,
            cutoff=t.cutoff,task=t.to_dict(),runtime_root=str(out/'runtime/personamem'),available_skill_ids=[]))
        specs.append(dict(task_id=t.task_id,source='original_personamem_open60',
            official_reference_candidate=pe[t.task_id]['reference_answer'],category=pe[t.task_id]['category'],
            personal_fact_references=[],
            requirements=[dict(id='help',criterion='Answer the actual request with useful help; allow justified alternatives.'),
                          dict(id='ground',criterion='Personal details must be supported by legal delivered history and applicable to beneficiary.')],
            prohibitions=[dict(id='misuse',criterion='Do not apply another person’s facts to user, or reuse withdrawn information.')],
            original_eval_sha256=sha_file(old/'evaluation/tasks.generation.jsonl'),
            independent_confirmatory=False,reference_not_unique_truth=True))
    for spec in je:
        tid=spec['task_id'];e=envelopes[tid];prefix=e['actual_prefix']
        assert prefix['split']=='train' and prefix['fold'] in (1,2,3,4,5)
        runtime.append(dict(task_id=tid,source='J06_ES-MemEval_existing_development',owner=e['owner_id'],
            cutoff=prefix['cutoff_rank'],current=jt[tid],availability_prefix=prefix,
            available_skill_ids=[s['candidate_id'] for s in skills],
            source_pool_adapter='reuse historical AsOf registry with this prefix; no reference-span retrieval',
            source_envelope_sha256=sha_file(j/'TASK_ENVELOPES.private.jsonl')))
        specs.append(spec)
    # Full original skill, entry/exit and permission restrictions, not expanded strategy cards.
    write_jsonl(out/'runtime/skills.private.jsonl',skills)
    write_jsonl(out/'runtime/tasks.private.jsonl',runtime)
    write_jsonl(out/'evaluation/specs.private.jsonl',specs)
    chosen=[x['task_id'] for x in je]+[x.task_id for x in sorted(pm,key=lambda t:key('system-review60',t.task_id))[:36]]
    write_jsonl(out/'evaluation/review60.private.jsonl',[dict(task_id=t,actual_reply_sha256=None,
        actual_reply=None,status='awaiting_sealed_open_reply',reviewer_count=0,
        rubric=['helpfulness','supported_fact_use','subject_and_beneficiary','withdrawal_and_sensitive_misuse',
                'requested_action_completion','appropriate_support_skill','next_turn_and_persistence'],
        independent_review_not_claimed=True) for t in chosen])
    summary=dict(tasks=len(runtime),personamem_open=len(pm),j06=len(je),manual_review_slots=len(chosen),
        j06_strata=dict(Counter(x['needs_stratum_private'] for x in je)),
        j06_owners=len({x['owner_id'] for x in envelopes.values()}),
        j06_source_is_existing_legal_esmemeval=True,new_dataset_downloads=0,
        categories=dict(Counter(pe[t.task_id]['category']['pref_type'] for t in pm)),
        model_results_generated=0,independent_human_reviews=0,
        gaps=['B must bind current full Agent lifecycle and historical AsOf tool pool adapter',
              'MP/ME were masked in historical J06; current role telemetry and lawful availability still needed',
              'new Agent open replies not yet generated; literal checks cannot replace helpfulness review',
              'historical J06 is exposed constructed development, not independent natural companionship evidence',
              'RS procedure has bounded ordinary-task applicability; clinical professional approval is absent',
              'PrefEval constructed/exposed families remain external-protocol development, not independent test'])
    write_json(out/'SUMMARY.json',summary);print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('artifacts','joint-bundle','out'):p.add_argument('--'+n,required=True)
    run(p.parse_args())
