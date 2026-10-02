#!/usr/bin/env python3
"""Run only frozen P1 diagnostic slots, greedy natural end, base/old LoRA.

No reward, no parameter updates, no provider fallback or quality retries.
Completed raw responses survive resume; interrupted requests fail closed.
"""
import argparse
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.generation import LocalNaturalGenerator
from metacom_pm.rl1.cache import AttemptCache

OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P1'
MODEL=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if path.exists() and path.read_text()==text:return
    tmp=path.with_suffix('.tmp');tmp.write_text(text);tmp.replace(path)


def main(out):
    import torch
    from peft import PeftModel
    if torch.cuda.device_count()!=1 or 'A6000' not in torch.cuda.get_device_name(0):
        raise RuntimeError('bind A6000 explicitly; no GPU fallback')
    freeze=json.loads((out/'renderer_freeze.json').read_text())
    for name,expected in freeze['files'].items():
        if sha256_file(out/name)!=expected:raise ValueError('frozen input changed: '+name)
    for name,expected in freeze['source_files'].items():
        if sha256_file(PROJECT/name)!=expected:raise ValueError('original source changed: '+name)
    if sha256_file(PROJECT/'src/metacom_pm/rl1/representation.py')!=freeze['retrieval']['representation_code_sha256']:
        raise ValueError('representation implementation changed since freeze')
    manifest=json.loads((out/'diagnostic_manifest.json').read_text())
    assert manifest['response_slots']==len(manifest['conditions'])*2<=72
    training=json.loads((PROJECT/'outputs/pm_rl1/executor_training_20260930_v1/training_pointer.json').read_text())
    selection_path=Path(training['run_dir'])/'selection.json';selection=json.loads(selection_path.read_text())
    checkpoint=Path(selection['checkpoint'])
    for name,expected in selection['adapter_files'].items():
        if sha256_file(checkpoint/name)!=expected:raise ValueError('old adapter changed')
    protocol=dict(version='p1-representation-diagnostic-v1',
        freeze_sha256=sha256_file(out/'renderer_freeze.json'),
        manifest_sha256=sha256_file(out/'diagnostic_manifest.json'),
        selection_sha256=sha256_file(selection_path),runner_sha256=sha256_file(Path(__file__)),
        response_slots=manifest['response_slots'],retries=0,api_usd=0,
        purpose='Development regression only; no reward or independent efficacy labels')
    run=out/'diagnostics'/digest(protocol);start=time.monotonic()
    save(run/'protocol.json',protocol);save(out/'diagnostic_pointer.json',dict(run_dir=str(run)))
    generator=LocalNaturalGenerator(MODEL,minimum_free_gib=40)
    base_manifest=dict(generator.manifest);cache=AttemptCache(run/'attempts.sqlite');rows=[]
    for arm in ('base','old_lora_epoch3'):
        if arm!='base':
            generator.model=PeftModel.from_pretrained(generator.model,checkpoint,is_trainable=False).eval()
            generator.manifest=dict(base_manifest,adapter=dict(path=str(checkpoint),files=selection['adapter_files']))
            generator.identity=digest(generator.manifest)
        save(run/(arm+'.runtime.json'),dict(**generator.manifest,identity=generator.identity))
        for c in manifest['conditions']:
            payload=dict(messages=c['messages'],executor_identity=generator.identity,
                draw_identity=digest(['p1-representation-diagnostic-v1',c['prefix_identity'],0]),
                renderer_identity=c['renderer_identity'])
            request=dict(**payload,request_id=digest(payload));rid=request['request_id']
            save(run/(rid+'.request.json'),request)
            cached=cache.claim(request)
            if cached is None:
                try:raw=generator.generate(request)
                except Exception as exc:
                    raw=dict(request_id=rid,runtime_identity=generator.identity,text='',finish_reason='exception',
                        exception_type=type(exc).__name__,error=str(exc),api_cost_usd=0)
                cache.finish(rid,raw)
            else:raw=cached
            save(run/(rid+'.raw.json'),raw)
            row={k:c[k] for k in ('index','prefix_identity','owner','condition','representation','counts','resource_tokens')}
            row.update(arm=arm,request_id=rid,finish_reason=raw['finish_reason'],
                input_tokens=raw.get('input_tokens'),output_tokens=raw.get('output_tokens'),
                seconds=raw.get('generation_seconds'),cache_hit=cached is not None)
            rows.append(row)
            save(run/'summary.json',dict(status='COMPLETE' if len(rows)==manifest['response_slots'] else 'IN_PROGRESS',
                rows=rows,load_seconds=generator.load_seconds,elapsed_seconds=time.monotonic()-start,
                generator_calls=sum(not r['cache_hit'] for r in rows),judge_calls=0,api_usd=0))
            print(json.dumps(row),flush=True)
            if raw['finish_reason']=='exception':raise RuntimeError('exception preserved; no automatic retry')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    main(parser.parse_args().out)
