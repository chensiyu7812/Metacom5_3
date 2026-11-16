#!/usr/bin/env python3
"""Read local model metadata and GPU metadata only; never load weights or keys."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=Path('/opt/tokkio-data0/tokkio_models')
rows=[];seen=set()
for p in sorted(ROOT.rglob('config.json')):
    if p.resolve() in seen: continue
    seen.add(p.resolve())
    try: d=json.loads(p.read_text())
    except (ValueError,OSError): continue
    if not d.get('architectures'): continue
    t=d.get('text_config',d)
    files=list(p.parent.glob('*.safetensors'))
    rows.append(dict(path=str(p.parent),config_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        model_type=d.get('model_type'),architectures=d['architectures'],dtype=t.get('dtype',t.get('torch_dtype',d.get('torch_dtype'))),
        layers=t.get('num_hidden_layers'),hidden_size=t.get('hidden_size'),kv_heads=t.get('num_key_value_heads'),
        context=t.get('max_position_embeddings'),quantization=d.get('quantization_config'),
        weight_files=len(files),weight_bytes=sum(f.stat().st_size for f in files),
        weight_content_read=False))
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,name,uuid,memory.total,memory.free,utilization.gpu',
    '--format=csv,noheader,nounits'],text=True).splitlines()
gpus=[]
for line in gpu:
    i,n,u,tot,free,util=[x.strip() for x in line.split(',')]
    gpus.append(dict(index=int(i),name=n,uuid=u,total_MiB=int(tot),free_MiB=int(free),utilization_percent=int(util)))
credentials=['DEEPSEEK_API_KEY','NVIDIA_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','DASHSCOPE_API_KEY']
value=dict(local_models=rows,gpus=gpus,credential_env_presence={k:k in os.environ for k in credentials},
    credential_values_read_or_saved=False,credential_files_read=False,account_availability_verified=False,
    provider_config='project/configs/experiment.yaml: training_judge_deepseek_official_flash is an older model/decode configuration; not reused silently',
    no_model_inference=True,no_download_or_install=True)
with (OUT/'hardware_and_models.json').open('x') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(model_configs=len(rows),gpus=gpus,credential_files_read=False)))
