"""Supplement v2 HF fallback benchmark (old runner and plan preserved). Refuses GPU work without separately bound approval.

Use the documented external timeout as a second guard against a blocked CUDA
kernel. This module does not import any model library until all CPU gates pass.
"""
import argparse
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.generator.bounded_probe import authorize,device_guard,GPU_UUID
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once
from metacom_pm.rl1v3.generator.checkpoint_guard import check_loaded_model, read_header


def run(plan_path,approval_path,workload,out):
    plan=json.loads(plan_path.read_text());approval=json.loads(approval_path.read_text())
    cfg=authorize(plan,approval,workload)  # Before any lock, model import or device access.
    for path,sha in plan['code_sha256'].items():
        if file_sha256(ROOT/path)!=sha:raise ValueError('runner code changed after plan/approval')
    preflight_path=plan_path.parent/plan['checkpoint_preflight_file']
    if file_sha256(preflight_path)!=plan['checkpoint_preflight_sha256']:raise ValueError('checkpoint preflight changed')
    preflight=json.loads(preflight_path.read_text())['models'][workload]
    if not preflight['structural_match']:raise ValueError('checkpoint did not pass structural admission')
    for path,sha in preflight['software_files'].items():
        if file_sha256(path)!=sha:raise ValueError('HF implementation changed after CPU admission')
    request_path=plan_path.parent/cfg['requests_file']
    if file_sha256(request_path)!=cfg['requests_sha256']:raise ValueError('workload changed')
    requests={r['request_id']:r for r in (json.loads(x) for x in request_path.read_text().splitlines())}
    calls=sum(b['batch'] for b in cfg['batches'])+cfg['warmup_calls']
    if calls!=cfg['max_calls']:raise ValueError('call budget differs')
    if cfg['backend']!='hf':raise ValueError('only named HF fallback prepared; vLLM exact architecture preflight blocked')
    if out.exists():raise ValueError('new output directory required; no implicit retry')
    for package,v in cfg['runtime_packages'].items():
        if package=='vllm':continue  # HF does not import vLLM.
        if importlib.metadata.version(package)!=v:raise ValueError('runtime package mismatch: '+package)
    for variable in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','PYTHONNOUSERSITE'):
        if os.environ.get(variable)!='1':raise ValueError(variable+' must be 1')
    if os.environ.get('CUDA_VISIBLE_DEVICES')!=GPU_UUID:raise ValueError('explicit approved GPU UUID required')
    # Fresh weight/config verification is required only after authorization.
    model_path=Path(cfg['model_path'])
    for name,expected in cfg['model_files'].items():
        if file_sha256(model_path/name)!=expected['sha256']:raise ValueError('model artifact changed: '+name)
    if preflight['pinned_weight_hashes']!={n:v for n,v in cfg['model_files'].items() if n.endswith('.safetensors')}:
        raise ValueError('preflight/model binding mismatch')
    for old_header in preflight['headers']:
        _,fresh=read_header(model_path/old_header['file'])
        if fresh!=old_header:raise ValueError('checkpoint header changed')
    with open(plan['safety']['lock'],'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        initial=device_guard();out.mkdir(parents=True)
        write_json_once(out/'STARTED.json',dict(plan_sha256=object_sha256(plan),approval_sha256=object_sha256(approval),
            workload=workload,pid=os.getpid(),initial_gpu=initial,calls_limit=calls))
        started=time.monotonic();stop=threading.Event();errors=[];free_samples=[]
        def monitor():
            while not stop.wait(1):
                try:
                    snap=device_guard(own_pid=os.getpid());free_samples.append(snap['free_mib'])
                    if time.monotonic()-started>cfg['stage_timeout_seconds']:raise RuntimeError('stage deadline reached')
                except Exception as e:
                    errors.append(str(e));os.kill(os.getpid(),signal.SIGTERM);return
        def abort(signum,frame):raise RuntimeError('bounded own-job stop: '+(';'.join(errors) or str(signum)))
        signal.signal(signal.SIGTERM,abort);signal.signal(signal.SIGALRM,abort)
        thread=threading.Thread(target=monitor,daemon=True);thread.start()
        try:
            os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
            import torch
            from transformers import AutoTokenizer,AutoModelForMultimodalLM,GenerationConfig,StoppingCriteria,StoppingCriteriaList
            torch.set_num_threads(1);torch.manual_seed(0);torch.use_deterministic_algorithms(True)
            torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
            tok=AutoTokenizer.from_pretrained(model_path,local_files_only=True)
            for r in requests.values():
                ids=tok.apply_chat_template(r['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
                if list(ids)!=r['input_ids']:raise ValueError('runtime tokenizer differs from CPU input IDs')
            load_start=time.monotonic()
            model,loading_info=AutoModelForMultimodalLM.from_pretrained(model_path,local_files_only=True,
                trust_remote_code=False,ignore_mismatched_sizes=False,output_loading_info=True,
                dtype=torch.bfloat16,attn_implementation='sdpa')
            checked=check_loaded_model(model,loading_info,preflight)
            write_json_once(out/'WEIGHT_LOADING.json',dict(diagnostics=checked,structural_admission_sha256=object_sha256(preflight),
                no_missing_required_weights=True,weights_freshly_hashed=True))
            model=model.to('cuda:0').eval()
            torch.cuda.synchronize();load_seconds=time.monotonic()-load_start
            if type(model).__name__!=cfg['architecture']:raise ValueError('loaded architecture mismatch')
            write_json_once(out/'LOAD.json',dict(seconds=load_seconds,execution_identity=cfg['execution_identity'],
                architecture=type(model).__name__,gpu_uuid=GPU_UUID,peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                peak_reserved_bytes=torch.cuda.max_memory_reserved(),minimum_free_mib=min(free_samples) if free_samples else None))
            shortest=min(requests.values(),key=lambda r:len(r['input_ids']))
            groups=[dict(request_ids=[shortest['request_id']],batch=1,warmup=True) for _ in range(cfg['warmup_calls'])]+cfg['batches']
            for i,b in enumerate(groups):
                device_guard(own_pid=os.getpid());rows=[requests[rid] for rid in b['request_ids']]
                if len({object_sha256(r['decode']) for r in rows})!=1:raise ValueError('mixed decode batch')
                width=max(len(r['input_ids']) for r in rows);cap=max(r['max_new_tokens'] for r in rows)
                if (width+cap)*len(rows)>cfg['padded_context_cap']:raise ValueError('batch budget exceeded')
                if any(len(r['input_ids'])+r['max_new_tokens']>r['context_limit'] for r in rows):raise ValueError('context overflow')
                pad=rows[0]['decode']['pad_token_id']
                inp=torch.tensor([[pad]*(width-len(r['input_ids']))+r['input_ids'] for r in rows],device='cuda:0')
                mask=torch.tensor([[0]*(width-len(r['input_ids']))+[1]*len(r['input_ids']) for r in rows],device='cuda:0')
                prefix=out/('batch_%03d'%i)
                write_json_once(prefix.with_suffix('.started.json'),dict(request_ids=b['request_ids'],batch=len(rows),warmup=b.get('warmup',False)))
                forward=[];times=[];batch_start=time.monotonic();ttft=[]
                def before(*args):torch.cuda.synchronize();times.append(time.monotonic())
                def after(*args):torch.cuda.synchronize();forward.append(time.monotonic()-times.pop())
                hooks=[model.register_forward_pre_hook(before),model.register_forward_hook(after)]
                class Watch(StoppingCriteria):
                    def __call__(self,input_ids,scores,**kw):
                        torch.cuda.synchronize()
                        if not ttft:ttft.append(time.monotonic()-batch_start)
                        return False
                gc=(GenerationConfig.from_pretrained(model_path,local_files_only=True)
                    if (model_path/'generation_config.json').exists() else GenerationConfig.from_model_config(model.config))
                for k,v in rows[0]['decode'].items():
                    if k not in ('seed','enable_thinking'):setattr(gc,k,v)
                torch.manual_seed(0);torch.cuda.reset_peak_memory_stats();free_samples.clear()
                signal.alarm(cfg['request_timeout_seconds'])
                try:
                    with torch.inference_mode():result=model.generate(inp,attention_mask=mask,generation_config=gc,stopping_criteria=StoppingCriteriaList([Watch()]))
                    torch.cuda.synchronize()
                finally:
                    signal.alarm(0)
                    for hook in hooks:hook.remove()
                seconds=time.monotonic()-batch_start;outputs=[]
                for row,tokens in zip(rows,result[:,width:].tolist()):
                    eos=row['decode']['eos_token_id'];eos=[eos] if isinstance(eos,int) else eos
                    stopat=next((j+1 for j,t in enumerate(tokens) if t in eos),len(tokens));ids=tokens[:stopat]
                    outputs.append(dict(request_id=row['request_id'],condition=row['condition'],input_tokens=len(row['input_ids']),token_ids=ids,text=tok.decode(ids,skip_special_tokens=True),
                        finish='eos' if ids and ids[-1] in eos else 'technical_truncation',evaluation_status='pending',reward=None))
                write_json_once(prefix.with_suffix('.json'),dict(workload=workload,status='measured',
                    execution_identity=cfg['execution_identity'],actual_requests=len(rows),warmup=b.get('warmup',False),
                    seconds=seconds,input_lengths=[len(r['input_ids']) for r in rows],padded_input_tokens=width*len(rows),
                    prefill_forward_seconds=forward[0] if forward else None,decode_forward_seconds=sum(forward[1:]),
                    prefill_padded_tokens_per_second=width*len(rows)/forward[0] if forward and forward[0]>0 else None,
                    decode_tokens_per_second=sum(max(0,len(o['token_ids'])-1) for o in outputs)/sum(forward[1:]) if sum(forward[1:])>0 else None,
                    condition_counts={c:sum(r['condition']==c for r in rows) for c in sorted({r['condition'] for r in rows})},
                    normal_end_requests=sum(o['finish']=='eos' for o in outputs),
                    truncated_requests=sum(o['finish']=='technical_truncation' for o in outputs),
                    ttft_seconds=ttft[0] if ttft else None,output_tokens=sum(len(o['token_ids']) for o in outputs),
                    output_tokens_per_second=sum(len(o['token_ids']) for o in outputs)/seconds,
                    requests_per_second=len(rows)/seconds,peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                    peak_reserved_bytes=torch.cuda.max_memory_reserved(),minimum_observed_free_mib=min(free_samples) if free_samples else None,
                    timing_scope='synchronized local HF batch; not end-to-end user latency',outputs=outputs))
                del inp,mask,result
            write_json_once(out/'FINISHED.json',dict(calls=calls,model_loads=1,wall_seconds=time.monotonic()-started,
                actual_execution_identity=cfg['execution_identity'],engineering_timing_only=True))
        except BaseException as e:
            write_json_once(out/'FAILED.json',dict(type=type(e).__name__,reason=str(e),wall_seconds=time.monotonic()-started,
                no_retry=True,evaluation_status='pending'))
            raise
        finally:stop.set();signal.alarm(0);thread.join(timeout=2)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--approval',type=Path,required=True);p.add_argument('--workload',choices=['gemma','needcard'],required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.plan,a.approval,a.workload,a.out)
