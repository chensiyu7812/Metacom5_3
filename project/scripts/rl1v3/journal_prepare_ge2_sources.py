#!/usr/bin/env python3
"""Freeze source-only GE2 task inputs; CPU/tokenizer only, no generation."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,object_sha256
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
from metacom_pm.rl1v3.journal import ge2_sources as S

def main():
    p=argparse.ArgumentParser()
    for name in ('selection','design','resources','metadata','memory','audit','pomdp-bundle','joint-bundle','base-plan','asset-manifest','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    selection=json.loads(a.selection.read_text());design=json.loads(a.design.read_text())
    config=dict(protocol=S.PROTOCOL,resources_path=str(a.resources),metadata_path=str(a.metadata),
        allowed_owners=design['allowed_owners'],excluded_owners=design['excluded_J06_owners'],
        source_inputs_sha256={str(x):file_sha256(x) for x in (a.resources,a.metadata)},sealed_fold6_body_read=False)
    S.write_once(a.out/'SOURCE_CONFIG_PRIVATE.json',config)
    registry=S.load_factory_inputs(config)
    base=json.loads(a.base_plan.read_text());baseline=json.loads(Path(base['baseline_path']).read_text())
    tok=PromptTokenizer(NativeTokenizer(base['model_path'],a.asset_manifest))
    runtime={r['task_id']:r for r in S.rows(a.memory/'tasks_runtime.jsonl')}
    official={r['task_id']:r for r in S.rows(a.memory/'evalspec_private.jsonl')}
    audits={r['task_id']:r for r in S.rows(a.audit)}
    oldtasks={r['task_id']:r for r in S.rows(a.pomdp_bundle/'TASKS.runtime.jsonl')}
    oldenvs={r['task_id']:r for r in S.rows(a.pomdp_bundle/'TASK_ENVELOPES.private.jsonl')}
    oldevals={r['task_id']:r for r in S.rows(a.pomdp_bundle/'EVALSPEC.private.jsonl')}
    jointtasks={r['task_id']:r for r in S.rows(a.joint_bundle/'TASKS.runtime.jsonl')}
    jointenvs={r['task_id']:r for r in S.rows(a.joint_bundle/'TASK_ENVELOPES.private.jsonl')}
    jointevals={r['task_id']:r for r in S.rows(a.joint_bundle/'EVALSPEC.private.jsonl')}
    tasks=[];envs=[];evals=[];pools=[];checks=[];direct=[]
    for chosen in selection['tasks']:
        oid=chosen['original_task_id'];tid=chosen['task_id'];origin=chosen['origin'];channel=chosen['channel']
        if origin=='official30':
            task,env=S.qa_envelope(runtime[oid],official[oid],registry,tid);evaluation=audits[oid]
            original_eval=official[oid];support_goal=None
            constraints=[dict(id=r['id'],text=r['criterion']) for r in original_eval['requirements']]
        elif origin=='existing_SMV_joint':
            task,env=S.dialogue_envelope(jointtasks[oid],jointenvs[oid],task_id=tid,channel=channel)
            evaluation=jointevals[oid];original_eval=evaluation;support_goal=evaluation['support_goal']
            constraints=[dict(id='prohibition-'+str(i+1),text=v) for i,v in enumerate(evaluation['prohibitions'])]
        else:
            task,env=S.dialogue_envelope(oldtasks[oid],oldenvs[oid],task_id=tid,channel=channel,actual_natural=True)
            evaluation=oldevals[oid];original_eval=evaluation
            support_goal='Respond as the next supporter to the actual visible complete prefix. No constructed historical-recall request, fixed sentence count, no-question rule, or old artificial support goal is inherited. Relevance and support quality remain assistant-development semantic observations; a suitable STOP reply is allowed.'
            constraints=[]
        env.update(original_task_id=oid,channel=channel,selection_alias=chosen['task_alias'],selection_sha256=file_sha256(a.selection))
        prepared,bound=S.prepare_source_port(task,env,registry,tok,baseline,a.out/'ledgers')
        records=prepared[-1]
        atoms,locs=S.normalize_atoms(origin,evaluation,records,task['turns'],natural=channel=='natural')
        item=dict(task_id=tid,task_alias=chosen['task_alias'],channel=channel,origin=origin,
            original_task_id=oid,original_evaluation=original_eval,original_evaluation_sha256=object_sha256(original_eval),
            required_atoms=atoms,constraints=constraints,support_goal=support_goal,
            unresolved_boundaries=evaluation.get('absence_review',evaluation.get('unresolved_boundary_ids',[])),
            interpretation='Exact-source supply diagnostics only. Faithful paraphrase permitted. Natural support does not require historical recital. Semantic quality is assistant development review, not independent human qualification.',
            formal_reward=None,source_time_scope='official_end_history' if origin=='official30' else 'real_pre_supporter_prefix',
            current_turns_sha256=object_sha256(task['turns']),source_port_binding_sha256=prepared[-2].sha256)
        tasks.append(task);envs.append(env);evals.append(item)
        pools.append(dict(task_id=tid,source_port_binding_sha256=prepared[-2].sha256,records=records))
        checks.append(dict(task_id=tid,source_locations=locs,base_input_tokens=len(prepared[3].make_packet().input_ids),
            source_count=len(records),prefix_sha256=prepared[1].runtime_sha256,natural_prefix_exact=channel=='natural'))
        if channel!='natural':
            selected={}
            for atom in atoms:
                for group in atom['sufficient_groups'][:1]:
                    for ref in group:
                        if ref.get('record_id'):
                            selected[(ref['record_id'],ref['turn_index'])]=ref
            # Original abstention context is source-only, not proof of archive-wide absence.
            if origin=='official30' and not selected:
                for atom in evaluation['atoms']:
                    for ref in atom['source_evidence']:
                        loc=S.located_reference(ref,records,task['turns'])
                        if loc['unique_legal_location']:
                            found=loc['candidates'][0];selected[(found['record_id'],found['turn_index'])]=found
            direct.append(dict(task_id=tid,source_units=[dict(record_id=r, start_turn=i,end_turn=i)
                for r,i in sorted(selected)],protocol='ge2-direct-source-only-exact-turn-recipe-v1'))
    for name,value in [('TASKS.runtime.jsonl',tasks),('TASK_ENVELOPES.private.jsonl',envs),('EVALSPEC.private.jsonl',evals),
        ('LEGAL_POOLS_PRIVATE.jsonl',pools),('SOURCE_READ_CHECKS_PRIVATE.jsonl',checks),('DIRECT_SOURCE_RECIPE_PRIVATE.jsonl',direct)]:S.write_once(a.out/name,value,jsonl=True)
    # Fixed full old denominator: 16 constructed tasks and 30 official questions.
    cpu=[];cpu_env=[];cpu_eval=[]
    for task in oldtasks.values():
        oid=task['task_id'];ev=oldevals[oid]
        t,e=S.dialogue_envelope(task,oldenvs[oid],channel='fact' if ev['goal_kind']=='fact' else 'constructed_support')
        cpu.append(t);cpu_env.append(e);cpu_eval.append(dict(task_id=oid,origin='pomdp16',original_evaluation=ev))
    for oid in runtime:
        t,e=S.qa_envelope(runtime[oid],official[oid],registry)
        cpu.append(t);cpu_env.append(e);cpu_eval.append(dict(task_id=oid,origin='official30',original_evaluation=audits[oid]))
    for name,value in [('CPU_TASKS_46.runtime.jsonl',cpu),('CPU_ENVELOPES_46_PRIVATE.jsonl',cpu_env),('CPU_EVAL_46_PRIVATE.jsonl',cpu_eval)]:S.write_once(a.out/name,value,jsonl=True)
    S.write_once(a.out/'MANIFEST_PRIVATE.json',dict(protocol=S.PROTOCOL,tasks=8,cpu_original_tasks=46,
        all_source_sessions=len(registry.entries),generator_calls=0,selection_sha256=file_sha256(a.selection),
        files={str(p.relative_to(a.out)):file_sha256(p) for p in sorted(a.out.glob('*')) if p.is_file()}))
    print(json.dumps(dict(bundle=str(a.out),tasks=8,cpu_original_tasks=46,generator_calls=0)))

if __name__=='__main__':main()
