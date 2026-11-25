"""CPU-only full legal-pool joint reads and six independent finite proposals."""
from pathlib import Path
from collections import Counter
from time import perf_counter
import json
import shutil
from .. import contracts as K
from ..sources import source_registry as S
from ..compile import asof as A
from ..io import canonical_json,decode_contract,file_sha256,object_sha256,write_json_once,write_jsonl_once
from .runtime_binding import VerifiedEpisode,binding_for,plain
from .joint_task_port import JointTaskPort,JointTaskEpisode
from .memory_packages import budget
from .joint_run import check,RUN_PROTOCOL,JOB_KIND
from . import renderer

ARMS=(('STOP',()),('MS',('MS',)),('RS',('RS',)),('MS_RS',('MS','RS')))

def jl(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]

def prepare(*,registry,tokenizer,bundle,smoke,measurements,repo,out):
    bundle,smoke,measurements,repo,out=map(Path,(bundle,smoke,measurements,repo,out));out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((bundle/'MANIFEST.json').read_text())
    # Only runtime/envelope/procedure files are parsed. Private evaluation content never enters selection.
    for name in ('TASKS.runtime.jsonl','TASK_ENVELOPES.private.jsonl','RS_PROCEDURE.private.jsonl'):
        assert file_sha256(bundle/name)==manifest['files_sha256'][name]
    tasks=jl(bundle/'TASKS.runtime.jsonl');envelopes={r['task_id']:r for r in jl(bundle/'TASK_ENVELOPES.private.jsonl')}
    rs,=jl(bundle/'RS_PROCEDURE.private.jsonl');assert len(tasks)==24
    base=json.loads((smoke/'SMOKE_PLAN.json').read_text());baseline=json.loads(Path(base['baseline_path']).read_text())
    measured=json.loads(measurements.read_text());writer='joint-full-legal-raw-v1';logical=[];checks=[];observations=[];pools=[]
    for task in tasks:
        tid=task['task_id'];envelope=envelopes[tid]
        assert object_sha256(task)==envelope['visible_task_sha256'] and task==envelope['visible_task']
        assert task['query']=='\n'.join(t['text'] for t in task['turns'])
        prefix=decode_contract(K.PrefixSpec,canonical_json(envelope['actual_prefix']))
        assert prefix.runtime_sha256==envelope['asof_runtime_sha256'];registry.context(prefix)
        entries=sorted((e for e in registry.entries if e.source.owner_id==prefix.owner_id and e.availability_scope=='personal_history'
            and registry.reason(e.source_id,prefix) is None),key=lambda e:e.source.chronological_rank)
        ledger=A.Ledger(out/'ledgers'/tid.replace(':','-'))
        for entry in entries:ledger.append(A.record_from_source(entry,kind='MS_RAW',writer=writer,subject='session'),registry)
        snapshot=A.materialize(registry,prefix,ledger,writer=writer)
        port=JointTaskPort(registry=registry,prefix=prefix,snapshot=snapshot,tokenizer=tokenizer,task_id=tid,
            turns=task['turns'],rs_candidate=rs,baseline_sha256=baseline['binding_sha256'],renderer_sha256=file_sha256(renderer.__file__))
        binding=binding_for(registry,prefix,snapshot,port,external_snapshot=object_sha256(rs))
        assert port.availability()['MP']==port.availability()['ME']==0
        public=port.public_observation();observations.append(dict(task_id=tid,observation=public))
        assert public['visible_turns']==task['turns'] and 'source_prefix' not in public
        pools.append(dict(task_id=tid,source_group=prefix.owner_id,legal_MS_sessions=[e.source.session_id for e in entries],
            legal_MS_count=len(entries),source_prefix_id=prefix.prefix_id,task_query_sha256=port.query_sha256,
            source_prefix_is_query=False,MS_pool_selected_without_eval_or_DP_pointer=True,RS_candidate_count=1))
        for arm,path in ARMS:
            path_started=perf_counter()
            # Independent fresh online state per path: STOP also pays measurement/mask setup.
            port=JointTaskPort(registry=registry,prefix=prefix,snapshot=snapshot,tokenizer=tokenizer,task_id=tid,
                turns=task['turns'],rs_candidate=rs,baseline_sha256=baseline['binding_sha256'],renderer_sha256=file_sha256(renderer.__file__))
            binding=binding_for(registry,prefix,snapshot,port,external_snapshot=object_sha256(rs))
            ep=JointTaskEpisode(registry=registry,prefix=prefix,snapshot=snapshot,port=port,binding=binding)
            state=ep.reset();step_rows=[]
            for head in path:
                state,info=ep.try_step(state,'GET_'+head)
                if head not in state.order:raise ValueError('actual GET rejected: '+head+' '+str(info)+' direct='+str(port.read(head)))
                step_rows.append(dict(head=head,reading_sha256=state.readings[-1].public_view.sha256,
                    record_ids=list(state.readings[-1].record_ids),tokens=state.readings[-1].tokens,
                    cpu_elapsed_ms=state.readings[-1].cost_s*1000))
            terminal,_=ep.try_step(state,'STOP');assert terminal.done and ep.stop_value(terminal).status=='pending'
            views=tuple(r.public_view for r in state.readings)
            _,invalid=ep.try_step(terminal,'GET_MS');assert invalid.reason=='after_stop'
            packet=port.tokenizer.make_packet(views);payload=packet.payload();sha=packet.payload_sha256
            logical.append(dict(domain='joint',task_id=tid,source_group=prefix.owner_id,arm=arm,logical_id=f'joint:{tid}:{arm}',
                request_id='jreq:'+sha,payload_sha256=sha,model_input=payload,input_ids_sha256=object_sha256(payload['input_ids']),
                input_tokens=len(payload['input_ids']),renderer_id=packet.renderer_id,baseline_sha256=baseline['binding_sha256'],
                authorized=False,model_called=False,task_query_sha256=port.query_sha256,
                source_port_binding_sha256=binding.sha256,endpoint_scope='task+query+payload+renderer+evaluation; not original natural-dialogue terminal'))
            observation=port.public_observation(views)
            checks.append(dict(online_path_cpu_ms=(perf_counter()-path_started)*1000,private_cost=dict(port.private_cost),task_id=tid,arm=arm,path=['GET_'+h for h in path]+['STOP'],order=list(state.order),
                actual_input_tokens=len(payload['input_ids']),billed_input_tokens=observation['input_tokens'],
                steps=step_rows,MP_ME_masked=True,after_stop_rejected=True,pending_reward=True,
                source_binding_sha256=binding.sha256,task_query_sha256=port.query_sha256,
                actual_selected_private_rankings=dict(port.private_rankings)))
    write_jsonl_once(out/'REQUESTS_ALL.private.jsonl',logical);write_jsonl_once(out/'READ_CHECKS.private.jsonl',checks)
    write_jsonl_once(out/'PUBLIC_OBSERVATIONS.private.jsonl',observations);write_jsonl_once(out/'LEGAL_POOLS.private.jsonl',pools)
    executor=out/'executor';shutil.copytree(base['executor_root'],executor);hashes=dict(base['executor_files_sha256'])
    for name,sha in hashes.items():assert file_sha256(executor/name)==sha
    additions=['project/src/metacom_pm/rl1v3/journal/joint_run.py','project/scripts/rl1v3/journal_joint_run.py']
    for name in additions:shutil.copy2(repo/name,executor/name);hashes[name]=file_sha256(executor/name)
    receipts=[]
    for number in range(1,7):
        selected=logical[(number-1)*16:number*16];first={}
        for r in selected:first.setdefault(r['request_id'],r)
        physical=list(first.values());job=out/f'batch-{number:02d}';job.mkdir()
        write_jsonl_once(job/'LOGICAL.private.jsonl',selected);write_jsonl_once(job/'REQUESTS.private.jsonl',physical)
        feasible=budget(physical,measured);write_json_once(job/'FEASIBILITY.json',feasible)
        plan=dict(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,batch_number=number,authorized=False,remaining_batches_authorized=False,
            research_qualified=False,executor_root=str(executor.resolve()),executor_files_sha256=hashes,
            requests_path=str((job/'REQUESTS.private.jsonl').resolve()),requests_sha256=file_sha256(job/'REQUESTS.private.jsonl'),
            frozen_requests_path=str((out/'REQUESTS_ALL.private.jsonl').resolve()),logical_requests_path=str((job/'LOGICAL.private.jsonl').resolve()),
            task_manifest_path=str((bundle/'TASKS.runtime.jsonl').resolve()),task_manifest_sha256=file_sha256(bundle/'TASKS.runtime.jsonl'),
            review_path=str((bundle/'EVALSPEC.private.jsonl').resolve()),review_sha256=manifest['files_sha256']['EVALSPEC.private.jsonl'],
            task_ids=[r['task_id'] for r in selected[::4]],logical_requests=16,max_calls=len(physical),
            ordered_request_ids=[r['request_id'] for r in physical],baseline_path=base['baseline_path'],baseline_sha256=base['baseline_sha256'],
            checkpoint_path=base['checkpoint_path'],model_path=base['model_path'],python=base['python'],max_model_loads=1,warmup_calls=0,
            automatic_retry=False,global_seconds=1200,load_seconds=600,request_seconds=300,renderer_id=physical[0]['renderer_id'],
            stop_rules=base['stop_rules'],paid_api_allowed=False)
        paths=[job/'REQUESTS.private.jsonl',job/'LOGICAL.private.jsonl',job/'FEASIBILITY.json',out/'REQUESTS_ALL.private.jsonl',
            out/'READ_CHECKS.private.jsonl',out/'PUBLIC_OBSERVATIONS.private.jsonl',out/'LEGAL_POOLS.private.jsonl',
            bundle/'MANIFEST.json',bundle/'TASKS.runtime.jsonl',bundle/'TASK_ENVELOPES.private.jsonl',bundle/'RS_PROCEDURE.private.jsonl',
            Path(base['baseline_path']),Path(base['checkpoint_path']),measurements,Path(__file__),Path(__file__).with_name('joint_task_port.py')]
        plan['files_sha256']={str(p.resolve()):file_sha256(p) for p in paths}
        # Evaluation bytes are frozen by producer manifest; never parsed for retrieval/building.
        plan['files_sha256'][str((bundle/'EVALSPEC.private.jsonl').resolve())]=manifest['files_sha256']['EVALSPEC.private.jsonl']
        write_json_once(job/'PLAN.json',plan);check(job/'PLAN.json')
        write_json_once(job/'AUTHORIZATION_PENDING.json',dict(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,authorized=False,
            plan_sha256=object_sha256(plan),max_calls=len(physical),max_model_loads=1,researcher=None,decision_evidence=None))
        receipt=dict(batch_number=number,plan_path=str(job/'PLAN.json'),plan_sha256=object_sha256(plan),
            logical=16,physical=len(physical),status='CPU_CHECK_PASSED',authorized=False,**feasible)
        write_json_once(job/'CPU_CHECK.json',receipt);receipts.append(receipt)
    report=dict(protocol='joint24-full-pool-four-path-cpu-v1',tasks=24,source_groups=len({p['source_group'] for p in pools}),
        actual_paths=len(checks),logical_requests=len(logical),physical_requests=len({r['request_id'] for r in logical}),
        MS_legal_pool_counts=dict(Counter(str(p['legal_MS_count']) for p in pools)),RS_candidate_count=1,MP_ME_masked=True,
        query='constructed visible query only',source_prefix='legal AsOf anchor only, never policy observation/query/G prompt',
        gold_or_DP_pointers_used_in_retrieval=False,eval_content_parsed=False,
        actual_G_calls=0,authorized=False,reward_qualified=False,old_executor_files_changed=[],executor_additions=additions,plans=receipts)
    write_json_once(out/'PACKAGE_REPORT.json',report);return report
