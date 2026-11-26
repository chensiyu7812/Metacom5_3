#!/usr/bin/env python3
"""CPU-only source construction. Private task/evaluation outputs stay off GitHub."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from metacom_pm.rl1v3.io import object_sha256, file_sha256
from metacom_pm.rl1v3.journal import gsws as S
from metacom_pm.rl1v3.journal.gsws_runtime import acquire, payload, interpreter_decode
from metacom_pm.rl1v3.journal.ge2_sources import rows, write_once, dialogue_envelope, normalize_atoms
from metacom_pm.rl1v3.journal.ge2_factory import GE2Factory
from metacom_pm.rl1v3.journal.ge2_retrieval import RetrievalConfig
from metacom_pm.rl1v3.journal.pomdp_latency import MonotonicClock
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
from metacom_pm.rl1v3.generator.g0e import DECODE


def build(old, selection, output):
    old=Path(old);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    source=old/'source-bundle-v2';pack=old/'packages-v2'
    choose=json.loads(Path(selection).read_text())
    cfg=json.loads((pack/'SOURCE_CONFIG_PRIVATE.json').read_text())
    priorplan=json.loads((pack/'batch-01/PLAN.json').read_text())
    baseline=json.loads(Path(priorplan['baseline_path']).read_text())
    taskbank={r['task_id']:r for f in ['CPU_TASKS_46.runtime.jsonl','TASKS.runtime.jsonl'] for r in rows(source/f)}
    envbank={r['task_id']:r for f in ['CPU_ENVELOPES_46_PRIVATE.jsonl','TASK_ENVELOPES.private.jsonl'] for r in rows(source/f)}
    oldeval={r['task_id']:r for r in rows(source/'EVALSPEC.private.jsonl')}
    cpueval={r['task_id']:r for r in rows(source/'CPU_EVAL_46_PRIVATE.jsonl')}
    tasks=[];envelopes={}
    for choice in choose:
        tid=choice['original_task_id'];task=deepcopy(taskbank[tid]);env=deepcopy(envbank[tid])
        if choice['source']=='actual_pre_supporter_prefix':
            task,env=dialogue_envelope(task,env,task_id=choice['gsws_task_id'],channel='natural',actual_natural=True)
        else:
            task['task_id']=choice['gsws_task_id']
            env.update(task_id=task['task_id'],visible_task=task,visible_task_sha256=object_sha256(task))
        prefix=env.get('actual_prefix',env.get('qa_prefix'))
        assert prefix['fold']!=6 and prefix['owner_id'] in cfg['allowed_owners']
        tasks.append(task);envelopes[task['task_id']]=env
    tok=PromptTokenizer(NativeTokenizer(priorplan['model_path'],cfg['asset_manifest_path']))
    factory=GE2Factory(source_config=cfg,envelopes=envelopes,tokenizer=tok,baseline=baseline,
                       ledger_root=out/'ledgers',retrieval_config=RetrievalConfig(backend='bm25'))
    prep=factory.prepare(tasks)
    evals=[];states=[];public=[];examples=[]
    for choice,task in zip(choose,tasks):
        tid=task['task_id'];original=choice['original_task_id'];records=factory.prepared[tid][0][-1]
        if original in oldeval:
            ev=deepcopy(oldeval[original]);ev.update(task_id=tid)
        else:
            oldev=cpueval[original]
            atoms,checks=normalize_atoms(oldev['origin'],oldev['original_evaluation'],records,task['turns'],natural=choice['channel']=='natural')
            ev=dict(task_id=tid,required_atoms=atoms,source_checks=checks,original_evaluation=oldev,
                constraints=[dict(id='current_goal',text='Respond to the actual last user turn in context; memory recital is optional for natural support.')])
        ev.update(goal_alias=choice['goal_alias'],channel=choice['channel'],exposure=choice['source'],
            review_status='assistant_development_reference_not_independent_human',formal_reward=None,
            criteria=['goal_and_explicit_boundaries','speaker_subject','reported_vs_event_time',
                      'suggestion_plan_attempt_action_outcome','source_support_vs_quote_existence',
                      'uncertainty_conflict_applicability','natural_support_without_forced_memory_recital'],
            result_states=['pass','fail','unknown','equivalent','not_applicable','technical_failure'],
            current_only_policy='Distinguish justified unknown under visible evidence from complete archive-goal success.',
            source_schedule='same original query BM25 Top4 then all returned parents; no evaluation coordinates')
        evals.append(ev);prior={}
        for stage in (0,1):
            clock=MonotonicClock();ep=factory(task,'CPU_SHARED:S'+str(stage),clock=clock,emit=lambda *a,**k:None,deadline_ns=clock.now_ns()+600*10**9)
            receipt=acquire(ep,task,stage);raw=ep.packet().payload()['messages']
            actual=S.project(task,ep,stage)
            state_row=dict(task_id=tid,goal_alias=choice['goal_alias'],stage=stage,observation=actual,source_receipt=receipt,
                raw_messages=raw,raw_payload=payload(ep,S.final_messages(raw,task),DECODE),source_records=records)
            states.append(state_row)
            row=dict(goal=choice['goal_alias'],stage=stage,channel=choice['channel'],exposure=choice['source'],
                legal_sources=len(records),visible_turns=len(task['turns']),read_turns=sum(e['kind']=='historical_report' for e in actual['evidence']),
                read_sources=len(ep.read_intervals),accesses=ep.accesses,refusals=len(ep.failed_attempts),
                raw_input_tokens=len(state_row['raw_payload']['input_ids']),formal_reward=None)
            for arm in S.ARMS[1:]:
                obs=S.project(task,ep,stage,prior.get(arm));first=obs['evidence'][0]
                # Real source quote in a transparent wiring fixture, NOT a model semantic result.
                value=(dict(notes='CPU fixture: the visible turn says: '+first['text'],evidence_ids=[first['evidence_id']]) if arm=='A1_READING_NOTES' else
                       dict(goal_and_boundaries='CPU fixture; goal interpretation pending.',claims=[dict(text=first['text'],
                         epistemic='reported',subject=first['speaker'],stage='unknown',event_time='unknown',
                         applicability='current_explicit',evidence_ids=[first['evidence_id']])],
                         gaps_or_conflicts='CPU fixture; not a qualified semantic judgment.',response_implications='Pending actual model.'))
                st=S.accept_interpretation(json.dumps(value),arm,obs,model_output_sha256=object_sha256(value),fixture=True)
                prior[arm]=st
                ip=payload(ep,S.interpreter_messages(obs,arm),interpreter_decode(DECODE,arm))
                gp=payload(ep,S.final_messages(raw,task,st),DECODE)
                assert S.shared_view(obs,st)==S.shared_view(obs,st)
                row[arm+'_fixture_interpreter_input_tokens']=len(ip['input_ids'])
                row[arm+'_fixture_final_input_tokens']=len(gp['input_ids'])
                examples.append(dict(task_id=tid,stage=stage,arm=arm,observation=obs,fixture_output=st,
                                     interpreter_payload=ip,terminal_fixture_payload=gp,actual_model_output=False))
            public.append(row)
    for name,value,jl in [('TASKS.runtime.jsonl',tasks,True),('TASK_ENVELOPES.private.jsonl',list(envelopes.values()),True),
                          ('SOURCE_CONFIG_PRIVATE.json',cfg,False),('EVALSPEC.private.jsonl',evals,True),
                          ('CPU_STATES_PRIVATE.jsonl',states,True),('CPU_FIXTURES_NOT_MODEL_PRIVATE.jsonl',examples,True),
                          ('TASK_COVERAGE_PUBLIC.json',public,False),('SEMANTIC_CONTRACT.json',S.contract(),False)]:
        write_once(out/name,value,jsonl=jl)
    summary=dict(status='CPU_SOURCES_AND_FIXTURES_BUILT',goals=8,correlated_states=16,terminal_slots=48,
                 interpreter_slots=32,actual_model_calls=0,fold6_body_read=False,source_preparation=prep,
                 cpu_fixtures_are_semantic_results=False,selection_sha256=file_sha256(selection),
                 inputs_sha256={str(p):file_sha256(p) for p in [Path(selection),source/'TASKS.runtime.jsonl',source/'CPU_TASKS_46.runtime.jsonl',source/'TASK_ENVELOPES.private.jsonl',source/'CPU_ENVELOPES_46_PRIVATE.jsonl']})
    write_once(out/'CPU_BUILD_PRIVATE.json',summary)
    return {k:v for k,v in summary.items() if k not in ('source_preparation','inputs_sha256')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--old',required=True);p.add_argument('--selection',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(json.dumps(build(a.old,a.selection,a.output),indent=2))
