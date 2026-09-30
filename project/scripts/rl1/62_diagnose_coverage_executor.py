#!/usr/bin/env python3
"""72 greedy dev generations: base and every predeclared epoch, same inputs.

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
OUT=PROJECT/'outputs/pm_rl1/executor_training_20260930_v1'
PACK=PROJECT/'outputs/pm_rl1/executor_coverage_20260929_v1/qualified_inputs'
MODEL=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)

def main():
    from peft import PeftModel
    start=time.monotonic()
    freeze=json.loads((OUT/'dataset_freeze.json').read_text())
    for name,expected in freeze['files'].items():
        if sha256_file(PROJECT/name)!=expected:raise ValueError('frozen training input changed: '+name)
    training=Path(json.loads((OUT/'training_pointer.json').read_text())['run_dir'])
    reload=json.loads((training/'reload.json').read_text())
    if not reload['passed'] or not reload['fresh_process']:raise ValueError('reload must pass before diagnostics')
    selected=json.loads((training/'selection.json').read_text())
    epochs=json.loads((training/'epochs.json').read_text())
    assert [e['epoch'] for e in epochs]==[1,2,3]
    for epoch in epochs:
        checkpoint=Path(epoch['checkpoint'])
        for name,expected in epoch['adapter_files'].items():
            if sha256_file(checkpoint/name)!=expected:raise ValueError('adapter changed')
    contract=json.loads((PACK/'condition_contract_private.json').read_text())
    conditions=[c for c in contract['conditions'] if c['split']=='dev'];assert len(conditions)==18
    protocol=dict(version='pm-rl1-frozen-coverage-all-epochs-diagnostic-v1',conditions=[(c['index'],c['condition'],c['messages_identity']) for c in conditions],
        arms=['base','epoch_1','epoch_2','epoch_3'],decode='greedy natural EOS/EOT, seed 0; native context remainder; existing watchdog',
        contract_sha256=sha256_file(PACK/'condition_contract_private.json'),selection_sha256=sha256_file(training/'selection.json'),
        reload_sha256=sha256_file(training/'reload.json'),runner_sha256=sha256_file(Path(__file__)),calls=72,
        epochs_sha256=sha256_file(training/'epochs.json'),checkpoint_selection_uses_these_outputs=False)
    run=OUT/'diagnostics'/digest(protocol);save(run/'protocol.json',protocol)
    save(OUT/'diagnostic_pointer.json',dict(run_dir=str(run)))
    generator=LocalNaturalGenerator(MODEL,minimum_free_gib=40)
    base_manifest=dict(generator.manifest);results=[]
    cache=AttemptCache(run/'attempts.sqlite')
    for arm in ('base','epoch_1','epoch_2','epoch_3'):
        if arm!='base':
            epoch=epochs[int(arm[-1])-1];checkpoint=Path(epoch['checkpoint'])
            if arm=='epoch_1':
                generator.model=PeftModel.from_pretrained(generator.model,checkpoint,adapter_name=arm,is_trainable=False).eval()
            else:
                generator.model.load_adapter(checkpoint,adapter_name=arm,is_trainable=False)
                generator.model.set_adapter(arm)
                generator.model.eval()
            generator.manifest=dict(base_manifest,adapter=dict(path=str(checkpoint),files=epoch['adapter_files'],name=arm))
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
    if len(results)!=72:raise ValueError('diagnostic call count mismatch')
if __name__=='__main__':main()
