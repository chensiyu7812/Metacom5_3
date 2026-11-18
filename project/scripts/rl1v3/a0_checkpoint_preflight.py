"""CPU-only safetensors headers vs HF meta-device shapes; never load tensor bytes."""
from collections import Counter
import argparse
import inspect
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.generator.checkpoint_guard import PROTOCOL,QWEN_MTP_UNUSED,read_header,compare_shapes
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once


def inspect_model(cfg):
    if os.environ.get('CUDA_VISIBLE_DEVICES')!='':raise ValueError('CPU audit requires empty CUDA_VISIBLE_DEVICES')
    import torch
    import transformers
    from transformers import AutoConfig,AutoModelForMultimodalLM
    from transformers.conversion_mapping import get_checkpoint_conversion_mapping
    assert not torch.cuda.is_initialized()
    path=Path(cfg['model_path']);config=AutoConfig.from_pretrained(path,local_files_only=True,trust_remote_code=False)
    # Shapes only: meta allocation has no weight storage and performs no forward/generation.
    with torch.device('meta'):
        model=AutoModelForMultimodalLM.from_config(config,attn_implementation='sdpa',dtype=torch.bfloat16,trust_remote_code=False)
    state=model.state_dict();assert all(t.is_meta for t in state.values())
    if type(model).__name__!=cfg['architecture']:raise ValueError('wrong CPU model class')
    transforms=get_checkpoint_conversion_mapping(config.model_type) or [];renames=[]
    for t in transforms:
        if type(t).__name__!='WeightRenaming' or len(t.source_patterns)!=1 or len(t.target_patterns)!=1:
            raise ValueError('unreviewed checkpoint transform')
        renames.append((t.source_patterns[0],t.target_patterns[0]))
    checkpoint={};headers=[];shards={}
    for name,expected in cfg['model_files'].items():
        if not name.endswith('.safetensors'):continue
        if (path/name).stat().st_size!=expected['bytes']:raise ValueError('pinned weight size changed')
        tensors,header=read_header(path/name);headers.append(header)
        if set(checkpoint)&set(tensors):raise ValueError('duplicate tensor across shards')
        checkpoint.update(tensors);shards.update({k:name for k in tensors})
    if (path/'model.safetensors.index.json').exists():
        if json.loads((path/'model.safetensors.index.json').read_text())['weight_map']!=shards:
            raise ValueError('shard index/header mismatch')
    qwen=cfg['architecture']=='Qwen3_5ForConditionalGeneration'
    comparison=compare_shapes({k:list(v.shape) for k,v in state.items()},checkpoint,renames=renames,
        tied=model.all_tied_weights_keys,allowed_unused=QWEN_MTP_UNUSED if qwen else ())
    package=Path(transformers.__file__).parent
    files=[Path(inspect.getfile(type(model))),package/'conversion_mapping.py',package/'modeling_utils.py',
           package/'utils/loading_report.py',package/'core_model_loading.py']
    small={name:file_sha256(path/name) for name in cfg['model_files'] if not name.endswith('.safetensors')}
    for name,sha in small.items():
        if sha!=cfg['model_files'][name]['sha256']:raise ValueError('small model artifact changed: '+name)
    report=dict(protocol=PROTOCOL,architecture=type(model).__name__,auto_class='AutoModelForMultimodalLM',
        model_type=config.model_type,**comparison,headers=headers,renames=renames,
        hf_ignored_unexpected_patterns=sorted(getattr(model,'_keys_to_ignore_on_load_unexpected',None) or []),
        unused_reason='upstream non-speculative HF omits 15 MTP tensors; all 760 required tensors exist' if qwen else None,
        software_files={str(p):file_sha256(p) for p in files},nonweight_hashes=small,
        pinned_weight_hashes={n:v for n,v in cfg['model_files'].items() if n.endswith('.safetensors')},
        checkpoint_dtypes=dict(Counter(t['dtype'] for t in checkpoint.values())),
        cpu_meta_only=True,tensor_bytes_read=False,weight_loads=0,forward_calls=0,cuda_initialized=torch.cuda.is_initialized(),
        fresh_full_weight_sha256=False,full_byte_hash_required_before_authorized_load=True)
    assert not report['cuda_initialized']
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();plan=json.loads(a.plan.read_text())
    reports={name:inspect_model(cfg) for name,cfg in plan['workloads'].items()}
    write_json_once(a.out,dict(protocol=PROTOCOL,source_plan_sha256=object_sha256(plan),models=reports,
        gpu_authorized=False,model_inference_calls=0))
    print(json.dumps({k:{f:r[f] for f in ('architecture','expected_tensors','checkpoint_tensors','structural_match','explicit_unused')} for k,r in reports.items()}))
