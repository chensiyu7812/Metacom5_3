#!/usr/bin/env python3
"""36 greedy dev generations: same exact inputs, base versus reloaded LoRA.

Descriptive smoke/grounding diagnosis only; no reward or effectiveness claim.
"""
import importlib.util
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
OUT=PROJECT/'outputs/pm_rl1/executor_engineering_20260929_v1'
MODEL=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)

def main():
    from peft import PeftModel
    start=time.monotonic()
    spec=importlib.util.spec_from_file_location('source_gate',PROJECT/'scripts/rl1/47_author_repaired_pilot.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate);gate.preflight()
    training=Path(json.loads((OUT/'training_pointer.json').read_text())['run_dir'])
    reload=json.loads((training/'reload.json').read_text())
    if not reload['passed'] or not reload['fresh_process']:raise ValueError('reload must pass before diagnostics')
    selected=json.loads((training/'selection.json').read_text());checkpoint=Path(selected['checkpoint'])
    for name,expected in selected['adapter_files'].items():
        if sha256_file(checkpoint/name)!=expected:raise ValueError('adapter changed')
    contract=json.loads((OUT/'condition_contract_private.json').read_text())
    conditions=[c for c in contract['conditions'] if c['split']=='dev'];assert len(conditions)==18
    protocol=dict(version='pm-rl1-posthoc-engineering-diagnostic-v1',conditions=[(c['index'],c['condition'],c['messages_identity']) for c in conditions],
        arms=['base','lora'],decode='greedy natural EOS/EOT, seed 0; native context remainder; existing watchdog',
        contract_sha256=sha256_file(OUT/'condition_contract_private.json'),selection_sha256=sha256_file(training/'selection.json'),
        reload_sha256=sha256_file(training/'reload.json'),runner_sha256=sha256_file(Path(__file__)),calls=36)
    run=OUT/'diagnostics'/digest(protocol);save(run/'protocol.json',protocol)
    save(OUT/'diagnostic_pointer.json',dict(run_dir=str(run)))
    generator=LocalNaturalGenerator(MODEL,minimum_free_gib=40)
    base_manifest=dict(generator.manifest);results=[]
    cache=AttemptCache(run/'attempts.sqlite')
    for arm in ('base','lora'):
        if arm=='lora':
            generator.model=PeftModel.from_pretrained(generator.model,checkpoint,is_trainable=False).eval()
            generator.manifest=dict(base_manifest,adapter=dict(path=str(checkpoint),files=selected['adapter_files']))
            generator.identity=digest(generator.manifest)
        save(run/(arm+'.runtime.json'),dict(**generator.manifest,identity=generator.identity))
        for c in conditions:
            payload=dict(messages=c['messages'],executor_identity=generator.identity,
                draw_identity=digest([c['prefix_identity'],0]),renderer_identity=contract['renderer_identity'])
            request=dict(**payload,request_id=digest(payload));rid=request['request_id']
            save(run/(rid+'.request.json'),request)
            cached=cache.claim(request)
            if cached is None:
                try:raw=generator.generate(request)
                except Exception as exc:
                    raw=dict(request_id=rid,runtime_identity=generator.identity,text='',finish_reason='exception',exception_type=type(exc).__name__,error=str(exc),api_cost_usd=0)
                cache.finish(rid,raw)
            else:raw=cached
            save(run/(rid+'.raw.json'),raw)
            row=dict(arm=arm,index=c['index'],condition=c['condition'],request_id=rid,
                messages_identity=c['messages_identity'],finish_reason=raw['finish_reason'],
                input_tokens=raw.get('input_tokens'),output_tokens=raw.get('output_tokens'),seconds=raw.get('generation_seconds'),cache_hit=cached is not None)
            results.append(row);save(run/'summary.json',dict(status='DEVELOPMENT_DIAGNOSTICS_ONLY',rows=results,
                load_seconds=generator.load_seconds,total_seconds=time.monotonic()-start,api_cost_usd=0,reward_measurements=0))
            print(json.dumps(row),flush=True)
            if raw['finish_reason']=='exception':raise RuntimeError('diagnostic exception retained; no retry')
    if len(results)!=36:raise ValueError('diagnostic call count mismatch')
if __name__=='__main__':main()
