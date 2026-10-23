#!/usr/bin/env python3
"""Source-gated finite author supplement; exact old inputs retain old outcomes.

--preflight-only loads the tokenizer, but no inference model. Default execution
generates only the frozen missing requests. It never admits replies or trains.
"""
import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.cache import AttemptCache
from metacom_pm.rl1.resource_plan_preflight import validate_resource_plans
from metacom_pm.rl1.schema import digest

OUT = PROJECT / 'outputs/pm_rl1/executor_coverage_20260929_v1'
PACK = OUT / 'qualified_inputs'


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def preflight():
    freeze = read(PACK / 'freeze_manifest.json')
    for name, expected in freeze['files'].items():
        if sha256_file(PACK / name) != expected:
            raise ValueError('frozen input changed: ' + name)
    contract = read(PACK / 'condition_contract_private.json')
    for name, expected in contract['source_guard'].items():
        if sha256_file(PROJECT / name) != expected:
            raise ValueError('source guard changed: ' + name)
    work = read(PACK / 'author_work_manifest.json')
    cs = {(c['index'], c['condition']): c for c in contract['conditions']}
    seen = set()
    for job in work['jobs']:
        key = (job['index'], job['condition'], job['seed'])
        if key in seen:
            raise ValueError('duplicate author job')
        seen.add(key)
        c = cs[(job['index'], job['condition'])]
        if any(job[k] != c[k] for k in ('messages_identity', 'prefix_identity', 'split')):
            raise ValueError('author job context changed')
        if job['action'] == 'reuse_existing':
            origin = job['provenance']
            for kind in ('request', 'raw'):
                if sha256_file(Path(origin[kind + '_path'])) != origin[kind + '_sha256']:
                    raise ValueError('reused original changed')
            request = read(Path(origin['request_path']))
            raw = read(Path(origin['raw_path']))
            if (request['messages'] != c['messages'] or request['seed'] != job['seed']
                    or request['request_id'] != origin['origin_request_id']
                    or raw['request_id'] != request['request_id']
                    or raw['runtime_identity'] != request['executor_identity']):
                raise ValueError('reused original does not match input/seed/runtime')
        elif job['action'] != 'generate_once' or job['provenance'] is not None:
            raise ValueError('unknown author disposition')
    expected = {(c['index'], c['condition'], s) for c in contract['conditions'] for s in contract['seeds']}
    if seen != expected:
        raise ValueError('incomplete author work manifest')
    binding = importlib.util.spec_from_file_location('coverage_binding', PROJECT / 'scripts/rl1/58_freeze_executor_coverage.py')
    module = importlib.util.module_from_spec(binding)
    binding.loader.exec_module(module)
    receipt = validate_resource_plans(contract, specs=module.load_specs(read(PACK / 'episode_specs_private.json')),
        evidence=read(PACK / 'legal_evidence_private.json'), reviews=read(PACK / 'source_reviews_private.json'),
        renderer=module.make_renderer())
    # Canonical comparison tolerates only JSON's tuple/list representation.
    if (digest(receipt) != freeze['preflight_identity']
            or digest(receipt) != digest(read(PACK / 'generation_preflight.json'))):
        raise ValueError('source/GET preflight changed')
    return contract, work, receipt


def repeated(ids):
    return len(ids) >= 128 and all(ids[-32:] == ids[-32*(i+1):-32*i] for i in range(1, 4))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    start = time.monotonic()
    contract, work, receipt = preflight()
    print(json.dumps(dict(stage='preflight', status=receipt['status'], counts=work['counts'])), flush=True)
    if args.preflight_only:
        return
    import torch
    from vllm import LLM, SamplingParams
    if (torch.cuda.device_count() != 1 or 'A6000' not in torch.cuda.get_device_name(0)
            or torch.cuda.mem_get_info(0)[0] < 44 * 1024**3):
        raise RuntimeError('bind the free A6000 explicitly; no fallback')
    author = contract['author']
    model = Path(author['model'])
    context = read(model / 'config.json')['text_config']['max_position_embeddings']
    old_run = Path(read(PROJECT / 'outputs/pm_rl1/executor_pilot_20260929_v2/author_pointer.json')['run_dir'])
    old_runtime = read(old_run / 'runtime.json')
    files = {p.name: sha256_file(p) for p in sorted(model.iterdir())
             if p.is_file() and p.suffix in ('.json', '.safetensors', '.jinja', '.txt')}
    packages = {p: importlib.metadata.version(p) for p in ('torch', 'transformers', 'vllm')}
    if files != old_runtime['files'] or author != old_runtime['decode'] or packages != old_runtime['packages']:
        raise ValueError('author model/decode/packages changed; frozen old-output reuse identity no longer applies')
    runtime = dict(protocol='pm-rl1-coverage-author-v1', model=str(model), files=files, packages=packages,
        gpu=torch.cuda.get_device_name(0), cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),
        cuda_version=torch.version.cuda, dtype='bfloat16', backend='vllm', native_context=context, decode=author,
        concurrency=4, gpu_memory_utilization=.88, max_num_batched_tokens=4096, enforce_eager=True,
        enable_prefix_caching=False, language_model_only=True, engine_seed=17,
        contract_sha256=sha256_file(PACK / 'condition_contract_private.json'), preflight_identity=digest(receipt),
        author_work_sha256=sha256_file(PACK / 'author_work_manifest.json'), runner_sha256=sha256_file(Path(__file__)))
    identity = digest(runtime)
    run = OUT / 'author' / identity
    save(run / 'runtime.json', dict(**runtime, identity=identity))
    save(OUT / 'author_pointer.json', dict(run_dir=str(run), runtime_identity=identity))
    conditions = {(c['index'], c['condition']): c for c in contract['conditions']}
    queue, reuses = [], []
    for job in work['jobs']:
        if job['action'] == 'reuse_existing':
            reuses.append(job)
            continue
        c = conditions[(job['index'], job['condition'])]
        payload = dict(messages=c['messages'], executor_identity=identity, seed=job['seed'],
            draw_identity=digest([c['prefix_identity'], job['seed']]), renderer_identity=contract['renderer_identity'])
        request = dict(**payload, request_id=digest(payload))
        save(run / (request['request_id'] + '.request.json'), request)
        queue.append((job, request))
    if len(queue) != work['counts']['generate_once'] or len(reuses) != work['counts']['reuse_existing']:
        raise ValueError('author call counts changed')
    save(run / 'reused_originals.json', reuses)
    save(run / 'jobs.json', [dict(**j, request_id=r['request_id']) for j, r in queue])
    cache = AttemptCache(run / 'attempts.sqlite')
    smoke, deferred = queue[:3], queue[3:]
    queue, checked, active, results = smoke, False, {}, []
    print(json.dumps(dict(stage='loading', new_calls=len(smoke) + len(deferred), reused=len(reuses))), flush=True)
    load = time.monotonic()
    llm = LLM(model=str(model), dtype='bfloat16', max_model_len=context, gpu_memory_utilization=.88,
        max_num_seqs=4, max_num_batched_tokens=4096, enforce_eager=True, enable_prefix_caching=False,
        seed=17, language_model_only=True)
    load_seconds = time.monotonic() - load
    tokenizer, engine = llm.get_tokenizer(), llm.llm_engine
    engine_start = time.monotonic()

    def finish(job, request, raw, cache_hit):
        save(run / (request['request_id'] + '.raw.json'), raw)
        results.append(dict(**job, request_id=request['request_id'], cache_hit=cache_hit,
            finish_reason=raw['finish_reason'], input_tokens=raw['input_tokens'], output_tokens=raw['output_tokens'], seconds=raw['seconds']))
        save(run / 'summary.json', dict(status='NEW_OUTPUTS_UNREVIEWED', rows=results, reused_originals=len(reuses),
            load_seconds=load_seconds, engine_wall_seconds=time.monotonic() - engine_start,
            total_seconds=time.monotonic() - start, api_cost_usd=0, planned_new_calls=work['counts']['generate_once']))
        print(json.dumps({k: results[-1][k] for k in ('index', 'condition', 'seed', 'finish_reason', 'output_tokens')}), flush=True)

    while queue or active or not checked:
        if not queue and not active and not checked:
            checked = True
            if len(results) != 3 or any(r['finish_reason'] != 'natural_stop' for r in results):
                raise RuntimeError('technical smoke failed; no quality-based revision or retry')
            queue = deferred
            save(run / 'smoke.json', dict(ok=True, request_ids=[r['request_id'] for r in results], quality_admission=False))
        while queue and len(active) < 4:
            job, request = queue.pop(0)
            ids = tokenizer.apply_chat_template(request['messages'], tokenize=True, add_generation_prompt=True,
                                                return_dict=False, enable_thinking=False)
            if len(ids) >= context:
                raise RuntimeError('native context exhausted; no truncation')
            cached = cache.claim(request)
            if cached is not None:
                finish(job, request, cached, True)
                continue
            params = SamplingParams(temperature=author['temperature'], top_p=author['top_p'], top_k=author['top_k'],
                min_p=author['min_p'], presence_penalty=author['presence_penalty'], repetition_penalty=author['repetition_penalty'],
                max_tokens=context - len(ids), seed=job['seed'])
            engine.add_request(request['request_id'], {'prompt_token_ids': ids}, params)
            active[request['request_id']] = dict(job=job, request=request, start=time.monotonic(), input_tokens=len(ids))
        if not active:
            continue
        for output in engine.step():
            if output.request_id not in active or not output.outputs:
                continue
            a, state = output.outputs[0], active[output.request_id]
            elapsed, reason = time.monotonic() - state['start'], None
            if output.finished:
                reason = 'natural_stop' if a.finish_reason == 'stop' else 'context_exhausted' if a.finish_reason == 'length' else str(a.finish_reason)
            elif elapsed >= 300:
                reason = 'technical_timeout'
            elif repeated(list(a.token_ids)):
                reason = 'repetition_guard'
            if reason is None:
                continue
            if not output.finished:
                engine.abort_request([output.request_id])
            raw = dict(request_id=output.request_id, runtime_identity=identity, text=a.text, finish_reason=reason,
                model_finish_reason=a.finish_reason, model_stop_reason=a.stop_reason, input_tokens=state['input_tokens'],
                output_tokens=len(a.token_ids), output_token_ids=list(a.token_ids), seconds=elapsed, api_cost_usd=0)
            cache.finish(output.request_id, raw)
            finish(state['job'], state['request'], raw, False)
            del active[output.request_id]


if __name__ == '__main__':
    main()
