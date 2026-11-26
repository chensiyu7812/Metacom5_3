"""GSWS one-load HF service (transport/model path copied from GE2) using the historical HF generation/measurement path.

Imports never load torch, weights or access a device. Only an admitted parent's
explicit worker load command can do so. This module is new, not an SC36 repair.
"""
from __future__ import annotations
import contextlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import hashlib
import selectors
import signal
import subprocess
import sys
import threading
import time
from collections import Counter

from ..generator import limited_run as L
from ..generator.runprep_checkpoint import check_loaded_model,read_header
from ..io import object_sha256
from .gsws import compile_grammar, ControllerConstraintProcessor
from . import gsws as S
from .gsws_runtime import ROLE_MAP, interpreter_decode
from .pomdp_latency import MonotonicClock,FirstOutputObserver,duration_ns

class WorkerCallBudget:
    def __init__(self,task_sha256,scope_sha256,role_caps,terminal_slots):
        L.require(len(task_sha256)==2 and all(task_sha256.values()) and scope_sha256,'two-goal scope')
        L.require(role_caps=={'terminal':12,'oneshot':4,'agent':4},'GSWS role caps')
        self.tasks=dict(task_sha256);self.scope=scope_sha256;self.caps=role_caps
        self.allowed={(r['task_id'],r['stage'],r['arm']) for r in terminal_slots}
        L.require(len(self.allowed)==12,'twelve terminal slots')
        self.total=0;self.roles=Counter();self.seen=set()
    def claim(self,request):
        role=request.get('role');b=request.get('binding',{});tid=b.get('task_id')
        L.require(role in self.caps and self.total<20,'GSWS total/role budget')
        self.total+=1;self.roles[role]+=1
        L.require(self.roles[role]<=self.caps[role],'GSWS role cap')
        L.require(tid in self.tasks and b.get('task_sha256')==self.tasks[tid],'task allowlist')
        L.require(b.get('scope_sha256')==self.scope,'scope binding')
        key=(tid,b.get('stage'),b.get('arm'))
        L.require(key in self.allowed,'stage/arm allowlist')
        L.require(role=='terminal' or b['arm']==ROLE_MAP[role],'interpreter role')
        L.require((role,*key) not in self.seen,'no repeat calls')
        self.seen.add((role,*key))
    def settle(self,request,output):
        L.require(len(output)<= (320 if request['role']=='terminal' else 512),'output token cap')


def validate_generate_request(request,spec,tokenizer,*,boot_id,now_ns,deadline_ns):
    L.require(set(request)=={'role','payload','binding','request_id'},'request allowlist')
    role=request['role'];p=request['payload'];b=request['binding']
    L.require(role in ('terminal','oneshot','agent'),'role')
    L.require(request['request_id']=='jgsws:'+object_sha256({k:v for k,v in request.items() if k!='request_id'}),'request hash')
    L.require(b['boot_id']==boot_id and now_ns<deadline_ns<=b['deadline_ns'],'clock/deadline')
    L.require(set(p)=={'messages','input_ids','decode'} and object_sha256(p)==b['payload_sha256'],'payload hash')
    expected=spec['decode'] if role=='terminal' else interpreter_decode(spec['decode'],ROLE_MAP[role])
    L.require(p['decode']==expected,'same G or frozen interpreter decode')
    if role=='terminal':
        L.require(p['messages'][0]==dict(role='system',content=spec['system_prompt']),'same G system')
        L.require(object_sha256(b['task'])==b['task_sha256'],'visible task identity')
        state=b['state']
        if state is not None:
            L.require(state['state_sha256']==object_sha256({k:v for k,v in state.items() if k!='state_sha256'}),'actual interpretation hash')
            L.require(state['task_sha256']==b['task_sha256'] and state['stage']==b['stage'] and state['arm']==b['arm'],'interpretation scope')
            L.require(state['origin']=='actual_model_output','no CPU fixture in actual G')
        L.require(p['messages']==S.final_messages(b['raw_messages'],b['task'],state),'final projection')
    else:
        obs=b['observation'];S.validate_projection(obs)
        L.require(obs['task_sha256']==b['task_sha256'] and obs['stage']==b['stage'],'observation scope')
        L.require(object_sha256(obs)==b['observation_sha256'] and obs['content_sha256']==b['content_sha256'],'actual observation hash')
        L.require(p['messages']==S.interpreter_messages(obs,ROLE_MAP[role]),'interpreter projection')
    ids=list(tokenizer.apply_chat_template(p['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False))
    L.require(ids==p['input_ids'] and len(ids)+expected['max_new_tokens']<=16384,'native tokenizer/capacity')
    return role,ids,expected


class SubprocessGSWSHF(L.SubprocessHF):
    kind='hf_dynamic_real'
    def __init__(self,root,plan,baseline,out,deadline):
        super().__init__(root,plan,baseline,out,deadline)
        self.scope_sha256=plan['scope_sha256']
        self.wire_failures=0;self.last_failure=None
    def _exchange(self,command,seconds):
        """Old bounded transport semantics, with immutable failed-wire evidence.

        A partial wire response is not a partial generated answer. No retries or
        new calls occur here. Failure logs are private and do not qualify output.
        """
        clock=MonotonicClock();started=clock.stamp()
        limit=min(self.deadline,time.monotonic()+seconds)
        def expire():
            if self.p.poll() is None:
                try:os.killpg(self.p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        timer=threading.Timer(max(0,limit-time.monotonic()),expire)
        timer.daemon=True;timer.start();sel=selectors.DefaultSelector()
        response=None;raw_line=None
        try:
            self.p.stdin.write((json.dumps(command)+'\n').encode());self.p.stdin.flush()
            sel.register(self.p.stdout,selectors.EVENT_READ)
            while True:
                L.require(time.monotonic()<limit,'worker hard deadline')
                L.device_guard(self.p.pid)
                if b'\n' in self.buffer:
                    raw_line,self.buffer=self.buffer.split(b'\n',1);response=json.loads(raw_line)
                    L.require(response.get('ok') is True,'worker error: '+str(response.get('error')))
                    return response['result']
                ready=sel.select(min(1,max(0,limit-time.monotonic())))
                if ready:
                    data=os.read(self.p.stdout.fileno(),65536)
                    L.require(bool(data),'worker exited without complete response')
                    self.buffer+=data;L.require(len(self.buffer)<16*1024*1024,'worker response overflow')
        except BaseException as error:
            finished=clock.stamp();self.wire_failures+=1
            record=dict(operation=command.get('operation'),command_sha256=object_sha256(command),
                request_id=command.get('request',{}).get('request_id'),started=started,finished=finished,
                elapsed_ns=duration_ns(started,finished),error=type(error).__name__+': '+str(error),
                worker_response=response,raw_response_line_hex=None if raw_line is None else raw_line.hex(),
                buffered_incomplete_wire_hex=self.buffer.hex(),partial_generated_output=None,
                first_effective_output=None,retry_calls=0,
                timing_scope='actual failed parent transport interval; no unobserved partial output or TTFT inferred')
            path=self.out/('WIRE_FAILURE_%03d.private.json'%self.wire_failures)
            data=(json.dumps(record,sort_keys=True,ensure_ascii=False)+'\n').encode()
            with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            self.last_failure=dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),
                started=started,finished=finished,elapsed_ns=record['elapsed_ns'])
            raise
        finally:sel.close();timer.cancel()
    def load(self,seconds):
        clock=MonotonicClock();supervisor_load_started=clock.stamp()
        L.require(self.p is None,'one model load only')
        L.require(time.monotonic()<self.deadline,'global deadline before load')
        L.device_guard(initial=True)
        self.error=(self.out/'worker.stderr.log').open('xb')
        env=dict(os.environ,PYTHONPATH=str(self.root/'project/src')+os.pathsep+self.plan['vendor_path'],
            CUDA_VISIBLE_DEVICES=L.GPU,CUBLAS_WORKSPACE_CONFIG=':4096:8',HF_HUB_OFFLINE='1',
            TRANSFORMERS_OFFLINE='1',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
            PMRL1_DYNAMIC_GRAMMAR_VENDOR=self.plan['vendor_path'],
            PMRL1_LIMITED_SUPERVISOR_PID=str(os.getpid()),PMRL1_LIMITED_DEADLINE=str(self.deadline))
        worker_spawn_started=clock.stamp()
        self.p=subprocess.Popen([sys.executable,'-m','metacom_pm.rl1v3.generator.limited_worker_guard',
            self.plan['python'],'-m','metacom_pm.rl1v3.journal.gsws_worker'],
            cwd=self.out,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.error,env=env,start_new_session=True)
        worker_spawn_finished=clock.stamp()
        checkpoint=Path(self.plan['checkpoint_path'])
        if not checkpoint.is_absolute():checkpoint=self.root/checkpoint
        result=self._exchange(dict(operation='load',model_path=self.plan['model_path'],
            spec=self.baseline['spec'],checkpoint=json.loads(checkpoint.read_text()),
            deadline_ns=int(min(self.deadline,time.monotonic()+seconds)*1e9),
            boot_id=MonotonicClock().boot_id,task_ids=self.plan['task_ids'],
            task_sha256=self.plan['task_sha256'],scope_sha256=self.plan['scope_sha256'],
            role_caps=self.plan['role_call_caps'],terminal_slots=self.plan['terminal_slots']),seconds)
        supervisor_load_finished=clock.stamp()
        result.update(worker_spawn_started=worker_spawn_started,worker_spawn_finished=worker_spawn_finished,
            worker_spawn_ns=duration_ns(worker_spawn_started,worker_spawn_finished),
            worker_spawn_scope='Popen syscall only; neither model readiness nor worker warmup',
            supervisor_load_started=supervisor_load_started,supervisor_load_finished=supervisor_load_finished,
            supervisor_load_ns=duration_ns(supervisor_load_started,supervisor_load_finished),
            supervisor_load_scope='inclusive parent load operation including guard/spawn/IPC and worker load')
        return result

    def generate(self,request,seconds):
        deadline_ns=min(request['binding']['deadline_ns'],int(min(self.deadline,time.monotonic()+seconds)*1e9))
        clock=MonotonicClock();started=clock.stamp()
        result=self._exchange(dict(operation='generate',request=request,deadline_ns=deadline_ns),seconds)
        finished=clock.stamp()
        result['supervisor_exchange']=dict(started=started,finished=finished,elapsed_ns=duration_ns(started,finished),
            timing_scope='inclusive IPC, device polling and response deserialization; not an isolated deserialization duration')
        return result


def main():
    parent=os.environ.get('PMRL1_LIMITED_SUPERVISOR_PID')
    L.require(parent and int(parent)==os.getppid(),'internal worker requires admitted supervisor')
    wire=sys.stdout;clock=MonotonicClock();model=tok=torch=gc_class=None;spec=None;loaded=False;inferences=0
    for line in sys.stdin:
        try:
            command=json.loads(line)
            L.require(clock.now_ns()<command['deadline_ns'],'worker command deadline')
            with contextlib.redirect_stdout(sys.stderr):
                if command['operation']=='load':
                    L.require(not loaded,'one model load only');loaded=True
                    L.require(command['boot_id']==clock.boot_id,'cross-process boot mismatch')
                    spec=command['spec'];path=command['model_path'];report=command['checkpoint']
                    L.require(set(command['task_ids'])==set(command['task_sha256']) and len(command['task_ids'])==2,'load task scope')
                    budgets=WorkerCallBudget(command['task_sha256'],command['scope_sha256'],command['role_caps'],command['terminal_slots'])
                    L.require(report['structural_match'] and report['architecture']==spec['model']['architecture'],'checkpoint structure')
                    L.require(platform.python_version()==spec['runtime']['python'],'Python version')
                    for name,version in spec['runtime']['packages'].items():
                        if name!='vllm':L.require(importlib.metadata.version(name)==version,'package '+name)
                    for header in report['headers']:
                        L.require(read_header(os.path.join(path,header['file']))[1]==header,'checkpoint header')
                    import torch
                    from transformers import AutoTokenizer,AutoModelForMultimodalLM,GenerationConfig,AutoConfig
                    import xgrammar
                    L.require(Path(xgrammar.__file__).resolve().is_relative_to(Path(os.environ['PMRL1_DYNAMIC_GRAMMAR_VENDOR']).resolve()),'isolated grammar dependency required')
                    L.require(importlib.metadata.version('xgrammar')=='0.1.21','frozen grammar package')
                    gc_class=GenerationConfig
                    torch.set_num_threads(1);torch.manual_seed(0);torch.use_deterministic_algorithms(True)
                    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
                    started=clock.stamp()
                    tok=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
                    config=AutoConfig.from_pretrained(path,local_files_only=True,trust_remote_code=False)
                    grammar_start=clock.stamp()
                    grammars={r:compile_grammar(r,tok,vocab_size=config.text_config.vocab_size,
                        eos_token_ids=spec['decode']['eos_token_id']) for r in ROLE_MAP.values()}
                    grammar_end=clock.stamp()
                    model,info=AutoModelForMultimodalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False,
                        ignore_mismatched_sizes=False,output_loading_info=True,dtype=torch.bfloat16,attn_implementation='sdpa')
                    diagnostic=check_loaded_model(model,info,report)
                    model=model.to('cuda:0').eval();torch.cuda.synchronize()
                    ended=clock.stamp()
                    L.require(ended['monotonic_ns']<command['deadline_ns'],'load deadline')
                    result=dict(seconds=duration_ns(started,ended)/1e9,started=started,finished=ended,
                        loading=diagnostic,architecture=type(model).__name__,
                        grammar_compile_ns=duration_ns(grammar_start,grammar_end),grammar_compile_started=grammar_start,
                        grammar_compile_finished=grammar_end,model_loads=1,warmup_calls=0,
                        peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved())
                elif command['operation']=='generate':
                    L.require(model is not None,'load required')
                    request=command['request']
                    budgets.claim(request)
                    validation_started=clock.stamp()
                    role,ids,decode=validate_generate_request(request,spec,tok,boot_id=clock.boot_id,
                        now_ns=clock.now_ns(),deadline_ns=command['deadline_ns'])
                    validation_finished=clock.stamp()
                    prep_started=clock.stamp()
                    inp=torch.tensor([ids],device='cuda:0');mask=torch.ones_like(inp)
                    gc=gc_class.from_pretrained(path,local_files_only=True)
                    for key,value in decode.items():
                        if key not in {'seed','enable_thinking'}:setattr(gc,key,value)
                    processor=None if role=='terminal' else ControllerConstraintProcessor(grammars[ROLE_MAP[role]],prompt_length=len(ids))
                    torch.manual_seed(0);torch.cuda.reset_peak_memory_stats()
                    prep_finished=clock.stamp()
                    started=clock.stamp();inferences+=1
                    observer=FirstOutputObserver(tok,prompt_token_count=len(ids),clock=clock,generation_start_stamp=started)
                    with torch.inference_mode():
                        generated=model.generate(inp,attention_mask=mask,generation_config=gc,
                            logits_processor=[] if processor is None else [processor],streamer=observer)
                    torch.cuda.synchronize();ended=clock.stamp()
                    output=generated[0,len(ids):].tolist();eos=decode['eos_token_id']
                    stop=next((i+1 for i,x in enumerate(output) if x in eos),len(output));output=output[:stop]
                    budgets.settle(request,output)
                    grammar_state=None if processor is None else processor.finalize(output)
                    observation=observer.measurement()
                    L.require(observer.tokens==output,'passive observer output differs')
                    seconds=duration_ns(started,ended)/1e9
                    result=dict(token_ids=output,text=tok.decode(output,skip_special_tokens=True),
                        finish_reason='eos' if output and output[-1] in eos else 'length',seconds=seconds,input_tokens=len(ids),
                        request_sha256=object_sha256(request),role=role,started=started,finished=ended,
                        first_inference_after_load=inferences==1,inference_ordinal=inferences,
                        request_validation_started=validation_started,request_validation_finished=validation_finished,
                        request_validation_ns=duration_ns(validation_started,validation_finished),
                        request_validation_scope='system/hash/observation checks and native tokenizer revalidation, inclusive',
                        generation_preparation_started=prep_started,generation_preparation_finished=prep_finished,
                        generation_preparation_ns=duration_ns(prep_started,prep_finished),
                        generation_preparation_scope='input transfer, generation config, fresh matcher, seed and peak reset',
                        passive_output_observer=observation,client_ttft_ns=None,
                        grammar_state=grammar_state,constraint_measurement=None if processor is None else processor.measurement(),
                        output_tokens_per_second=len(output)/seconds if seconds else None,
                        peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                        timing_scope='same-boot worker monotonic; callbacks are passive internal observations, not client delivery')
                    del inp,mask,generated
                else:raise ValueError('unknown worker operation')
            wire.write(json.dumps({'ok':True,'result':result})+'\n');wire.flush()
        except BaseException as error:
            wire.write(json.dumps({'ok':False,'error':type(error).__name__+': '+str(error),
                'failure_stamp':clock.stamp()})+'\n');wire.flush()
            return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
