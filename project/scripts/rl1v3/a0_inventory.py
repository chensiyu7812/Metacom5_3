#!/usr/bin/env python3
"""Read-only CPU A0 inventory. Never starts a model, training or a paid call."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import platform
import subprocess
import time

from metacom_pm.rl1v3.generator.preflight import (
    command_snapshot,environment_snapshot,model_snapshot,prepare_off_requests,tokenizer_probe,
)
from metacom_pm.rl1v3.io import build_manifest,parse_json,write_json_once,write_jsonl_once


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--dry-run',action='store_true',help='This command is always CPU-only, including without this flag')
    args=parser.parse_args(); config=parse_json(args.config.read_text()); root=Path.cwd()
    if config['scope']!='cpu_inventory_and_request_preparation_only' or config['gpu_execution_authorized'] or config['paid_calls_authorized']:
        raise ValueError('this inventory cannot grant or exercise inference authorization')
    report_path=args.out/'ENV_REPORT.json'
    if report_path.exists():
        print('Completed immutable inventory already exists; use a new output path for a new snapshot.')
        return
    args.out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter();observed_at=datetime.now(timezone.utc).isoformat()
    environment=[environment_snapshot(Path(p)) for p in config['environments']]
    gpu_queries=[command_snapshot(['nvidia-smi','--query-gpu=index,uuid,name,memory.total,memory.free,memory.used,utilization.gpu','--format=csv,noheader,nounits']),
                 command_snapshot(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory','--format=csv,noheader,nounits'])]
    write_json_once(args.out/'GPU_SNAPSHOT.json',dict(observed_at=observed_at,queries=gpu_queries,read_only=True))
    expected=parse_json(Path(config['legacy_model_binding']).read_text())['runtime']['model_files']
    bge=parse_json(Path(config['bge_binding']).read_text())['encoder_binding']
    models={}
    for name,path in config['models'].items():
        print('hashing local bytes: '+name,flush=True)
        binding=expected if name=='g0_candidate' else {'model.safetensors':bge['model_safetensors_sha256']} if name=='bge_dense' else None
        models[name]=model_snapshot(Path(path),expected_files=binding)
    requests=prepare_off_requests(parse_json(Path(config['source_specs']).read_text()),
                                  parse_json(Path(config['source_runtime']).read_text()),count=config['request_count'])
    request_path=args.out/'OFF_REQUESTS.jsonl';write_jsonl_once(request_path,requests)
    probe=tokenizer_probe(Path(config['tokenizer_python']),Path(config['models']['g0_candidate']),request_path,args.out/'TOKENIZER_PROBE.json')
    write_json_once(args.out/'TOKENIZER_EXECUTION.json',probe)
    report=dict(task='A0',status=('cpu_preparation_complete_gpu_measurements_pending' if probe['returncode']==0 else 'cpu_tokenization_failed_gpu_not_run'),qualification_tier='engineering_only',
        observed_at=observed_at,platform=platform.platform(),environments=environment,models=models,
        gpu_snapshot='GPU_SNAPSHOT.json',tokenizer_probe=probe,prepared_OFF_requests=len(requests),
        current_gpu_authorization='not_granted_for_this_v3_probe',historical_authorization='closed prior 36-call experiment; not transferable',
        model_calls=0,training_steps=0,paid_cost_usd=0,weights_loaded=False,
        generations_per_second=None,output_tokens_per_second=None,peak_vram_gib=None,generation_seconds=None,
        qwen_judge_throughput=None,qlora_12b_peak_vram_gib=None,vllm_support='not_measured',scale_tier=None,
        measured_inventory_wall_seconds=time.perf_counter()-started,
        gpu_hour_estimate=None,estimate_formula='(output_tokens / measured_output_tokens_per_second + measured_prefill_and_load_seconds) / 3600',
        required_followup=['authorize scoped A6000 batch; recheck exclusive UUID, other jobs and >=30 GiB free',
                           'run 100 prepared OFF requests through separately authorized HF/vLLM runner',
                           'measure Qwen judge and QLoRA memory in separately scoped runs; no guessed tier'])
    write_json_once(report_path,report)
    inputs={name:root/config[name] for name in ('legacy_model_binding','bge_binding','source_runtime','source_specs')}
    inputs['config']=args.config.resolve()
    code=list(root.glob('project/src/metacom_pm/rl1v3/generator/*.py'))+[Path(__file__).resolve(),root/'project/src/metacom_pm/rl1v3/io.py']
    manifest=build_manifest(task='A0',root=root,inputs=inputs,outputs=sorted(args.out.resolve().glob('*.json'))+[request_path.resolve()],
                            code=code,code_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
    write_json_once(args.out/'MANIFEST.json',manifest)
    print(f"A0 CPU inventory saved; {len(requests)} real OFF requests prepared; zero inference calls")


if __name__=='__main__':main()
