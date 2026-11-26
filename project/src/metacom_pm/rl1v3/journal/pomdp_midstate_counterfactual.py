"""Four-call, source-only restored-state contrast. No authorization at import.

Historical episodes, grammar, renderer, worker and guard are imported unchanged.
Preparation uses the CPU tokenizer, never weights, a model or an evaluator.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
from pathlib import Path
import signal

from ..generator import limited_run as L
from ..generator.g0e import DECODE
from ..io import file_sha256,object_sha256
from . import pomdp_memory as P
from .pomdp_dynamic_run import MonotonicJournal,assert_loaded_executor
from .pomdp_latency import MonotonicClock,duration_ns

PROTOCOL='pmrl1-j-restored-midstate-four-v1'
JOB_KIND='JOURNAL_RESTORED_MIDSTATE4'
BASE_COMMIT='c40b90c99cb991cf1c2793ffbe9927a0011885ab'
BRANCHES=('RESTORED_STOP','RANK1_EXPAND_STOP')


def read(path):return json.loads(Path(path).read_text())
def rows(path):return [json.loads(s) for s in Path(path).read_text().splitlines() if s]


def state_private(episode):
    return dict(state_sha256=episode.state_hash(),observation=episode.observe(),
        observation_sha256=object_sha256(episode.observe()),identity=episode.identity,nonce=episode.nonce,
        handles=episode.handles,contents=episode.contents,expanded=sorted(episode.expanded),
        last_hits=list(episode.last_hits),allowed_tokens=sorted(episode.allowed_tokens),
        accesses=episode.accesses,charged_tokens=episode.charged_tokens,
        done=episode.done,budget_exhausted=episode.budget_exhausted,
        payload=episode.packet().payload(),payload_sha256=episode.packet().payload_sha256)


def restore(factory,task,state,*,emit,clock,deadline_ns):
    """Replay complete observed prefix with original nonce; never set private fields."""
    episode=factory(task,'LLMToolAgent',emit=emit,clock=clock,deadline_ns=deadline_ns)
    for action in state['replay_actions']:episode.step(action)
    actual=state_private(episode)
    for field in ('state_sha256','observation_sha256','payload_sha256'):
        L.require(actual[field]==state[field],'restored '+field)
    L.require(actual['observation']==state['observation'],'complete restored observation')
    if 'snapshot' in state:
        L.require(actual==state['snapshot'],'complete restored private snapshot')
    L.require(not episode.done and 'EXPAND' in episode.observe()['action_mask'],'restored expandable state')
    return episode


def ranked_handles(episode):
    # Current ranked SEARCH result is explicit observation; no gold/pool rank here.
    observed=episode.observe();order=list(observed['last_hits'])
    order.extend(h['handle'] for h in sorted(observed['hits'],key=lambda h:h['observed_ordinal']) if h['handle'] not in order)
    L.require(len(order)==len(set(order))==len(episode.handles),'complete observed handle enumeration')
    return order


def span_key(ref):
    return object_sha256({k:ref.get(k) for k in ('source_id','owner_id','session_id','turn_index','speaker','exact_quote')})


def candidate_receipt(episode,handle):
    """Actual CPU EXPAND, with source overlap separate from native token charge."""
    before=episode.observe();record=episode.records[episode.handles[handle]['record_id']]
    seen={span_key(s) for item in episode.contents.values() for s in ([item['span']] if 'span' in item else item.get('spans',[]))}
    refs={span_key(s) for s in record['source_refs']}
    keys=set(episode.contents);legal=bool(episode.legal(record));error=None;was_expanded=handle in episode.expanded
    try:episode.step({'action':'EXPAND','handle':handle})
    except P.RejectedAction as exc:error=str(exc)
    after=episode.observe()
    return dict(handle=handle,record_id=record['record_id'],source_legal=legal,
        action_admissible=error is None,budget_reachable=error is None,rejection_reason=error,
        source_turns_in_parent=len(refs),new_unique_source_turns=len(refs-seen),
        repeated_source_turns=len(refs&seen),already_expanded=was_expanded,
        before_input_tokens=before['input_tokens'],after_input_tokens=after['input_tokens'],
        native_input_token_delta=after['input_tokens']-before['input_tokens'],
        charged_tool_tokens_delta=after['delivered_tokens_used']-before['delivered_tokens_used'],
        tool_tokens_remaining=after['delivered_tokens_remaining'],accesses_remaining=after['accesses_remaining'],
        canonical_new_content_units=len(set(episode.contents)-keys),
        source_overlap_semantics='parent includes earlier span; original renderer retains both, no deduplication',
        task_success=None,formal_reward=None)


def choose_rank1(candidates):
    L.require(bool(candidates),'no observed EXPAND candidate')
    first=candidates[0]
    # Never skip a budget-refused first hit in favor of a rewarding later one.
    L.require(first['source_legal'] and first['action_admissible'] and first['budget_reachable'],
              'highest observed ranked hit is not safely executable')
    return first['handle']


def make_factory(plan,ledger_root):
    from .pomdp_dynamic_runtime import LiveEpisodeFactory
    from .selective_memory_validation_sources import load_development_cache
    from ..retrieve.native_tokens import NativeTokenizer
    from ..generator.g0e_port import PromptTokenizer
    source=read(plan['source_config_path']);baseline=read(plan['baseline_path'])
    registry=load_development_cache(resources_path=source['resources_path'],metadata_path=source['metadata_path'],
        allowed_owners=source['allowed_owners'],excluded_owners=source['excluded_owners'])
    tokenizer=PromptTokenizer(NativeTokenizer(plan['model_path'],source['asset_manifest_path']))
    task_map={t['task_id']:t for t in rows(plan['task_manifest_path'])}
    tasks=[task_map[t] for t in plan['task_ids']]
    factory=LiveEpisodeFactory(registry=registry,tokenizer=tokenizer,baseline_sha256=baseline['binding_sha256'],
        envelopes={r['task_id']:r for r in rows(plan['envelopes_path'])},ledger_root=ledger_root,
        frozen_pools_path=plan['cpu_pools_path'])
    factory.prepare(tasks)
    return factory,tasks


def request_rows(tasks,states,factory,clock,deadline_ns):
    requests=[];diagnostics=[];frozen_states=[]
    for task,state in zip(tasks,states):
        episode=restore(factory,task,state,emit=lambda *a,**k:None,clock=clock,deadline_ns=deadline_ns)
        frozen=dict(state,snapshot=state_private(episode));frozen_states.append(frozen)
        candidates=[]
        for rank,handle in enumerate(ranked_handles(episode),1):
            branch=restore(factory,task,frozen,emit=lambda *a,**k:None,clock=clock,deadline_ns=deadline_ns)
            candidates.append(dict(rank=rank,**candidate_receipt(branch,handle)))
        selected=choose_rank1(candidates)
        diagnostics.append(dict(task_id=task['task_id'],candidates=candidates,selected_handle=selected,
            selection='first actual observed rank; no evaluator/reference used',formal_reward=None))
        for branch in BRANCHES:
            fresh=restore(factory,task,frozen,emit=lambda *a,**k:None,clock=clock,deadline_ns=deadline_ns)
            actions=([{'action':'EXPAND','handle':selected}] if branch==BRANCHES[1] else [])+[{'action':'STOP'}]
            for action in actions:fresh.step(action)
            payload=fresh.packet().payload()
            row=dict(task_id=task['task_id'],branch=branch,restored_state_sha256=frozen['state_sha256'],
                restored_observation_sha256=frozen['observation_sha256'],actions=actions,payload=payload,
                payload_sha256=object_sha256(payload),native_input_tokens=len(payload['input_ids']),
                final_observation_sha256=object_sha256(fresh.observe()),source_receipt=fresh.receipt(),
                task_sha256=object_sha256(task),formal_reward=None)
            # Stable identity excludes historical perf_counter timings in receipt.
            row['frozen_request_id']='jmid4:'+object_sha256({k:row[k] for k in
                ('task_id','branch','restored_state_sha256','restored_observation_sha256','actions','payload_sha256','task_sha256')})
            requests.append(row)
    return requests,diagnostics,frozen_states


def check(path):
    plan=read(path)
    L.require((plan['protocol'],plan['job_kind'],plan['base_commit'])==(PROTOCOL,JOB_KIND,BASE_COMMIT),'new identity')
    L.require(plan['authorized'] is False and plan['automatic_retry'] is False and plan['automatic_followup'] is False,'no implicit authority')
    for key,want in (('max_calls',4),('max_model_loads',1),('warmup_calls',0),('global_seconds',1200),('load_seconds',600),('request_seconds',300)):
        L.require(type(plan.get(key)) is int and plan[key]==want,'budget '+key)
    L.require(plan['controller_calls']==0 and plan['formal_reward'] is None,'terminal-only diagnostic')
    L.require(plan['cache_policy']=='disabled_new_physical_terminal_each_branch','new latency needs physical calls')
    L.require(plan['gpu_uuid']==L.GPU and plan['model_path']=='/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3','frozen device/model')
    L.require(plan['python']=='/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python','frozen Python')
    required={plan[k] for k in ('baseline_path','checkpoint_path','source_config_path','task_manifest_path',
        'envelopes_path','cpu_pools_path','review_path','requests_path','states_path','original_plan_path','original_exact_path')}
    L.require(required<=set(plan['files_sha256']),'unbound input')
    for name,sha in plan['files_sha256'].items():L.require(file_sha256(name)==sha,'input changed '+name)
    for rel,sha in plan['executor_files_sha256'].items():
        full=(Path(plan['executor_root'])/rel).resolve()
        L.require(full.is_relative_to(Path(plan['executor_root']).resolve()) and file_sha256(full)==sha,'executor '+rel)
    L.require(object_sha256(plan['executor_files_sha256'])==plan['executor_inventory_sha256'],'inventory')
    original=read(plan['original_plan_path'])
    for rel,sha in original['executor_files_sha256'].items():
        L.require(plan['executor_files_sha256'].get(rel)==sha,'frozen historical implementation changed')
    for key in ('baseline_path','checkpoint_path','source_config_path','task_manifest_path','envelopes_path','cpu_pools_path','review_path'):
        L.require(plan[key]==original[key],'original dependency '+key)
    for rel in ('project/src/metacom_pm/rl1v3/journal/pomdp_midstate_counterfactual.py',
                'project/scripts/rl1v3/journal_run_pomdp_midstate.py'):
        L.require(rel in plan['executor_files_sha256'],'unbound new executor')
    for rel,sha in plan['vendor_files_sha256'].items():L.require(file_sha256(Path(plan['vendor_path'])/rel)==sha,'vendor')
    for name,sha in plan['constraint_runtime_files_sha256'].items():L.require(file_sha256(name)==sha,'runtime dependency')
    baseline=read(plan['baseline_path'])
    L.require(file_sha256(plan['baseline_path'])=='1639a4a6f4c6f94cb256e24017f1a904c478642ea4549d4ca2f9e5c6ad8fa7ae','signed baseline')
    L.require(object_sha256(baseline)==plan['baseline_sha256'] and baseline['spec']['decode']==DECODE,'original G decode')
    L.require(file_sha256(plan['checkpoint_path'])=='288944b7d3fcb6faf52b2f82ba658e0d4a0fe26e4e3f91676b5e694817e63584','checkpoint')
    requests=rows(plan['requests_path']);states=rows(plan['states_path'])
    L.require(len(requests)==4 and len(states)==2 and len(plan['task_ids'])==2,'two states four terminals')
    L.require([(r['task_id'],r['branch']) for r in requests]==[(t,b) for t in plan['task_ids'] for b in BRANCHES],'complete fixed pairs')
    L.require([r['frozen_request_id'] for r in requests]==plan['ordered_request_ids'],'request order')
    L.require([s['task_id'] for s in states]==plan['task_ids'],'state order')
    old_states=[s for s in read(plan['original_exact_path']) if 'task_id' in s]
    L.require([s['original_batch'] for s in states]==[s['batch'] for s in old_states]==['DR1','DR2'],'original preselected batches')
    taskmap={t['task_id']:t for t in rows(plan['task_manifest_path'])}
    L.require(plan['task_sha256']=={t:object_sha256(taskmap[t]) for t in plan['task_ids']},'actual task hash')
    for current,old in zip(states,old_states):
        for field in ('task_id','state_sha256','observation_sha256','payload_sha256'):
            L.require(current[field]==old[field],'original preselected state '+field)
    for r in requests:
        L.require(object_sha256(r['payload'])==r['payload_sha256'] and r['payload']['decode']==DECODE,'payload')
        L.require(len(r['payload']['input_ids'])+DECODE['max_new_tokens']<=16384,'context')
        state=next(s for s in states if s['task_id']==r['task_id'])
        actions=([dict(action='EXPAND',handle=state['snapshot']['last_hits'][0])] if r['branch']==BRANCHES[1] else [])+[dict(action='STOP')]
        L.require(r['actions']==actions,'frozen rank1/STOP actions')
        L.require(r['frozen_request_id']=='jmid4:'+object_sha256({k:r[k] for k in
            ('task_id','branch','restored_state_sha256','restored_observation_sha256','actions','payload_sha256','task_sha256')}),'request identity')
    L.require(plan['scope_sha256']==object_sha256(dict(protocol=PROTOCOL,task_ids=plan['task_ids'],
        ordered_request_ids=plan['ordered_request_ids'],requests_sha256=file_sha256(plan['requests_path']),
        states_sha256=file_sha256(plan['states_path']),global_seconds=1200,max_calls=4)),'scope')
    return plan,requests,states,baseline


def admit(plan,auth):
    L.require(auth.get('authorized') is True and (auth.get('protocol'),auth.get('job_kind'))==(PROTOCOL,JOB_KIND),'new midstate4 approval required')
    L.require(auth.get('plan_sha256')==object_sha256(plan),'approval exact plan')
    for key,want in (('max_calls',4),('max_model_loads',1),('global_seconds',1200),('warmup_calls',0),('retry_calls',0)):
        L.require(type(auth.get(key)) is int and auth[key]==want,'approval '+key)
    L.require(auth.get('researcher') and auth.get('gpu_uuid')==L.GPU,'researcher/device')
    L.require(file_sha256(auth['decision_evidence'])==auth['decision_evidence_sha256'],'real decision evidence')
    return auth


def first_output_deltas(decision_start,output):
    events=(output.get('passive_output_observer') or {}).get('events',{})
    result={}
    for name in ('first_generated_token','first_non_special_token','first_nonempty_decoded_text'):
        stamp=events.get(name)
        result['decision_to_'+name+'_ns']=None if stamp is None else duration_ns(decision_start,stamp)
    return dict(result,client_ttft_ns=None,useful_text_ttft_ns=None,
        semantic_text_validity='not_machine_qualified',first_output_scope='same-boot internal passive observer; not client delivery')


def execute(*,plan,requests,states,tasks,factory,backend,emit,clock,deadline_ns,guard):
    """Exactly four allowlisted terminal calls at most; no fallback, cache or retry."""
    L.require(len(requests)==4 and len(states)==len(tasks)==2,'four-call execution scope')
    L.require([(r['task_id'],r['branch']) for r in requests]==[(t['task_id'],b) for t in tasks for b in BRANCHES],'ordered four calls')
    result=[];physical=0;state_map={s['task_id']:s for s in states};task_map={t['task_id']:t for t in tasks}
    for frozen in requests:
        task=task_map[frozen['task_id']];state=state_map[frozen['task_id']]
        restore_start=clock.stamp();replay_events=[]
        episode=restore(factory,task,state,emit=lambda event,**fields:replay_events.append(dict(event=event,**fields)),
            clock=clock,deadline_ns=deadline_ns)
        restored=clock.stamp()
        emit('MIDSTATE_RESTORED',stamp=restored,task_id=task['task_id'],branch=frozen['branch'],
            restoration_started=restore_start,restoration_ns=duration_ns(restore_start,restored),
            state_sha256=episode.state_hash(),observation_sha256=object_sha256(episode.observe()),
            restoration_events=replay_events,online_branch_cost=False)
        # Only after complete identity checks: both branches begin at this point.
        start=clock.stamp();L.require(start['monotonic_ns']<deadline_ns,'global deadline')
        episode.emit=lambda event,**fields:emit(event,branch=frozen['branch'],**fields)
        emit('BRANCH_DECISION_START',stamp=start,task_id=task['task_id'],branch=frozen['branch'],
            frozen_request_id=frozen['frozen_request_id'],state_sha256=state['state_sha256'])
        for action in frozen['actions']:episode.step(action)
        payload=episode.packet().payload()
        L.require(payload==frozen['payload'] and object_sha256(payload)==frozen['payload_sha256'],'actual branch payload differs')
        L.require(object_sha256(episode.observe())==frozen['final_observation_sha256'],'actual branch state differs')
        guards=clock.stamp();guard();guard_end=clock.stamp()
        emit('EXPERIMENT_GUARD_RETURNED',stamp=guard_end,started=guards,elapsed_ns=duration_ns(guards,guard_end))
        L.require(physical<4 and guard_end['monotonic_ns']<deadline_ns,'terminal-only call/deadline cap');physical+=1
        binding=dict(task_id=task['task_id'],method=frozen['branch'],physical_ordinal=physical,
            task_sha256=object_sha256(task),payload_sha256=frozen['payload_sha256'],boot_id=clock.boot_id,
            deadline_ns=deadline_ns,scope_sha256=plan['scope_sha256'],frozen_request_id=frozen['frozen_request_id'])
        request=dict(role='terminal',payload=payload,binding=binding)
        request['request_id']='jdynamic:'+object_sha256(request)
        call_start=clock.stamp();emit('MODEL_REQUEST_START',stamp=call_start,request=request,role='terminal',physical_ordinal=physical)
        try:output=backend.generate(request,min(300,(deadline_ns-call_start['monotonic_ns'])/1e9))
        except BaseException as exc:
            failed=clock.stamp()
            emit('MODEL_REQUEST_FAILED',stamp=failed,request_id=request['request_id'],role='terminal',
                physical_ordinal=physical,elapsed_ns=duration_ns(call_start,failed),
                error=type(exc).__name__+': '+str(exc),wire_failure=getattr(backend,'last_failure',None),
                partial_generated_output=None,first_effective_output=None,retry_calls=0)
            raise
        returned=clock.stamp();emit('MODEL_REQUEST_RETURNED',stamp=returned,request_id=request['request_id'],output=output,output_sha256=object_sha256(output))
        L.require(returned['monotonic_ns']<deadline_ns and output['request_sha256']==object_sha256(request),'response binding/deadline')
        finish=L.validate_result({'model_input':payload},output)
        L.require(finish=='eos','terminal incomplete; stop whole four-call package without retry')
        if backend.kind=='hf_dynamic_real':
            L.require(output['started']['boot_id']==output['finished']['boot_id']==clock.boot_id,'worker boot')
            L.require(call_start['monotonic_ns']<=output['started']['monotonic_ns']<=output['finished']['monotonic_ns']<=returned['monotonic_ns'],'worker timing bounds')
            L.require(abs(output['seconds']-duration_ns(output['started'],output['finished'])/1e9)<1e-9,'worker duration')
            L.require(output['inference_ordinal']==physical and output['first_inference_after_load']==(physical==1),'cold inference identity')
            L.require(output['passive_output_observer']['generated_token_count']==len(output['token_ids']) and output['passive_output_observer']['stream_ended'],'passive output identity')
            L.require(factory.tokenizer.native.tokenizer.decode(output['token_ids'],skip_special_tokens=True)==output['text'],'native output text')
            L.require(output.get('client_ttft_ns') is None,'unmeasured client delivery')
            for stamp in output['passive_output_observer']['events'].values():
                if stamp is not None:L.require(stamp['boot_id']==clock.boot_id and output['started']['monotonic_ns']<=stamp['monotonic_ns']<=output['finished']['monotonic_ns'],'callback clock')
        emit('MODEL_REQUEST_VALIDATED',request_id=request['request_id'],role='terminal',finish_reason=finish,
            output_tokens=len(output['token_ids']))
        end=clock.stamp();entry=dict(task_id=task['task_id'],branch=frozen['branch'],request_id=request['request_id'],
            frozen_request_id=frozen['frozen_request_id'],payload_sha256=frozen['payload_sha256'],
            output_sha256=object_sha256(output),decision_started=start,finished=end,
            decision_to_validated_reply_ns=duration_ns(start,end),restoration_ns=duration_ns(restore_start,restored),
            finish_reason=finish,source_receipt=episode.receipt(),formal_reward=None,logging_wall_ns=None,
            **first_output_deltas(start,output))
        emit('BRANCH_COMPLETED',stamp=end,**entry);result.append(entry)
    return dict(status='FINISHED',physical_backend_calls=physical,
        actual_model_calls=physical if backend.kind=='hf_dynamic_real' else 0,
        backend=backend.kind,controller_calls=0,branches=result,formal_reward=None)


def run(path,approval,run_root):
    plan,requests,states,baseline=check(path);auth=admit(plan,read(approval))
    from .pomdp_dynamic_worker import SubprocessDynamicHF
    assert_loaded_executor(plan)
    root=Path(run_root).resolve();storage=L.storage_guard(root)
    with (L.DATA/'tokkio_projects/pmrl1-validation/limited-g0e-exclusive.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);device=L.device_guard(initial=True)
        claims=L.DATA/'tokkio_projects/pmrl1-validation/limited-g0e-claims';claims.mkdir(parents=True,exist_ok=True)
        # Scope reservation survives any failure and rejects same-state retries.
        reservation=object_sha256(dict(protocol=PROTOCOL,task_ids=plan['task_ids'],baseline_sha256=plan['baseline_sha256'],
            states=[s['observation_sha256'] for s in states],branches=BRANCHES))
        L.write_once(claims/('midstate4-'+reservation+'.json'),dict(plan_sha256=object_sha256(plan),approval_sha256=object_sha256(auth),no_retry=True))
        clock=MonotonicClock();start=clock.stamp();deadline_ns=start['monotonic_ns']+1200*10**9
        journal=MonotonicJournal(root/('job-'+object_sha256(auth)),clock)
        journal.add('RUN_START',stamp=start,plan_sha256=object_sha256(plan),approval=auth,storage=storage,gpu=device)
        backend=None;result=None;failure=None;previous=signal.getsignal(signal.SIGALRM)
        def expire(*_):raise L.AdmissionError('whole-job 1200-second deadline')
        signal.signal(signal.SIGALRM,expire);signal.setitimer(signal.ITIMER_REAL,1200)
        try:
            # Weight bytes are touched only here, after exact approval, never CPU prepare/check.
            for name,expected in baseline['spec']['model']['files'].items():
                p=Path(plan['model_path'])/name;L.require(p.stat().st_size==expected['bytes'],'model size')
                h=hashlib.sha256()
                with p.open('rb') as f:
                    for block in iter(lambda:f.read(8*1024*1024),b''):
                        L.require(clock.now_ns()<deadline_ns,'model hash deadline');h.update(block)
                L.require(h.hexdigest()==expected['sha256'],'model byte SHA')
            for name,sha in read(plan['checkpoint_path'])['software_files'].items():L.require(file_sha256(name)==sha,'HF software')
            factory,tasks=make_factory(plan,journal.path/'runtime-ledgers');assert_loaded_executor(plan)
            backend=SubprocessDynamicHF(Path(plan['executor_root']),plan,baseline,journal.path,deadline_ns/1e9)
            load=clock.stamp();journal.add('LOAD_START',stamp=load)
            loaded=backend.load(min(600,(deadline_ns-clock.now_ns())/1e9));journal.add('LOAD_OK',measurement=loaded,started=load)
            result=execute(plan=plan,requests=requests,states=states,tasks=tasks,factory=factory,backend=backend,
                emit=journal.add,clock=clock,deadline_ns=deadline_ns,
                guard=lambda:(L.storage_guard(root),L.device_guard(backend.p.pid if backend.p else None)))
        except BaseException as exc:
            failure=type(exc).__name__+': '+str(exc);journal.add('SUPERVISOR_STOP',reason=failure,no_retry=True,formal_reward=None)
        finally:
            if backend is not None:
                try:backend.close()
                except BaseException as exc:
                    failure=(failure or '')+'; close: '+str(exc);journal.add('SUPERVISOR_STOP',reason=failure,no_retry=True)
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        end=clock.stamp();summary=dict(protocol=PROTOCOL,status='STOPPED' if failure else 'FINISHED',
            started=start,finished=end,wall_ns=duration_ns(start,end),runtime=result,supervisor_failure=failure,
            no_retry=True,formal_reward=None,last_journal_sha256=journal.prev)
        L.write_once(journal.path/'SUMMARY.json',summary);return summary
