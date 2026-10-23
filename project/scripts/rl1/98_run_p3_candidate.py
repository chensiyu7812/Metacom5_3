#!/usr/bin/env python3
"""Finite development-only P3 run. Never reads sealed labels or runs PPO."""
import argparse
from collections import Counter
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.cache import AttemptCache
from metacom_pm.rl1.judge_completion import messages_and_schema, parse_completion, score_identity
from metacom_pm.rl1.schema import digest

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P3/candidate_v1'


def read(p):
    return json.loads(p.read_text())


def save(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(p)


def repeated(ids):
    return len(ids) >= 128 and all(ids[-32:] == ids[-32*(i+1):-32*i] for i in range(1, 4))


def main(preflight_only):
    start = time.monotonic()
    freeze = read(ROOT / 'candidate_freeze.json')
    for n, h in freeze['files'].items():
        assert sha256_file(ROOT / n) == h, n
    for n, h in freeze['source_files'].items():
        assert sha256_file(PROJECT / n) == h, n
    protocol = read(ROOT / 'protocol.json')
    assert digest({k:v for k,v in protocol.items() if k != 'identity'}) == protocol['identity']
    jobs = [j for j in read(ROOT / 'jobs_private.json') if j['group'] in ('development', 'recheck_probe')]
    assert len([j for j in jobs if not j['recheck']]) <= 32
    assert sum(j['recheck'] for j in jobs) == 1
    model = Path(protocol['model']); cfg = protocol['runtime']; decode = protocol['decode']
    assert {p: importlib.metadata.version(p) for p in protocol['packages']} == protocol['packages']
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    prepared = []
    for j in jobs:
        messages, schema = messages_and_schema(j['evidence'], j['reply'], recheck=j['recheck'])
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
            return_dict=False, enable_thinking=decode['thinking'])
        assert 0 < len(ids) < cfg['native_context'], 'full source exceeds context; do not truncate'
        prepared.append((j, messages, schema, ids))
    preflight = dict(status='FULL_DEVELOPMENT_INPUTS_FIT_NATIVE_CONTEXT', jobs=len(jobs),
        minimum_input_tokens=min(len(t[3]) for t in prepared), maximum_input_tokens=max(len(t[3]) for t in prepared),
        task_output_cap=None, native_context=cfg['native_context'], truncation=False)
    save(ROOT / 'development_context_preflight.json', preflight)
    print(json.dumps(preflight), flush=True)
    if preflight_only:
        return
    import torch
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import StructuredOutputsParams
    if (torch.cuda.device_count() != 1 or 'A6000' not in torch.cuda.get_device_name(0)
            or torch.cuda.mem_get_info(0)[0] < 44 * 1024**3):
        raise RuntimeError('bind free A6000; no fallback')
    for n, h in protocol['model_files'].items():
        assert sha256_file(model / n) == h, n
    runtime = dict(protocol_identity=protocol['identity'], gpu=torch.cuda.get_device_name(0),
        cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'), cuda_version=torch.version.cuda,
        cuda_device_order=os.environ.get('CUDA_DEVICE_ORDER'), configuration=cfg,
        runner_sha256=sha256_file(Path(__file__)))
    identity = digest(runtime); run = ROOT / 'development' / identity
    save(run / 'runtime.json', dict(runtime, identity=identity))
    save(ROOT / 'development_pointer.json', dict(run_dir=str(run), runtime_identity=identity))
    queue = []
    for j, messages, schema, ids in prepared:
        payload = dict(messages=messages, json_schema=schema, executor_identity=identity,
            score_identity=score_identity(j['evidence'], j['reply'], runtime_identity=identity, recheck=j['recheck']),
            draw_identity=j['draw_id'], seed=j['seed'], attempt=0)
        req = dict(payload, request_id=digest(payload))
        save(run / (req['request_id'] + '.request.json'), req)
        queue.append((j, ids, req))
    cache = AttemptCache(run / 'attempts.sqlite'); results = []; active = {}
    smoke, deferred = queue[:4], queue[4:]; queue = smoke; checked = False
    load_start = time.monotonic()
    llm = LLM(model=str(model), dtype=cfg['dtype'], max_model_len=cfg['serving_context'],
        gpu_memory_utilization=cfg['gpu_memory_utilization'], max_num_seqs=cfg['concurrency'],
        max_num_batched_tokens=cfg['max_num_batched_tokens'], enforce_eager=cfg['enforce_eager'],
        enable_prefix_caching=cfg['enable_prefix_caching'], seed=cfg['engine_seed'],
        language_model_only=cfg['language_model_only'], reasoning_parser=cfg['reasoning_parser'])
    load_seconds = time.monotonic() - load_start; engine = llm.llm_engine
    engine_start = time.monotonic()
    print(json.dumps(dict(stage='loaded', seconds=load_seconds, runtime_identity=identity)), flush=True)

    def summary(status):
        save(run / 'summary.json', dict(status=status, planned=len(jobs), rows=results,
            physical_calls_this_invocation=sum(not r['cache_hit'] for r in results),
            unattempted=len(jobs)-len(results), statuses=dict(Counter(r['measurement_status'] for r in results)),
            load_seconds=load_seconds, engine_wall_seconds=time.monotonic()-engine_start,
            total_process_seconds=time.monotonic()-start, API_usd=0, human_labels_read=0,
            natural_RL_training_updates=0, reward_qualified=False))

    def finish(j, req, raw, cache_hit):
        parsed = parse_completion(raw['text'], evidence=j['evidence'], reply=j['reply'],
            runtime_identity=identity, draw_id=j['draw_id'], finish_reason=raw['finish_reason'])
        save(run / (req['request_id'] + '.raw.json'), raw)
        save(run / (req['request_id'] + '.measurement.json'), parsed)
        results.append(dict(job_id=j['job_id'], group=j['group'], request_id=req['request_id'],
            cache_hit=cache_hit, finish_reason=raw['finish_reason'], measurement_status=parsed['measurement_status'],
            q=parsed['q'], m=parsed['m'], utility=parsed['candidate_utility'],
            input_tokens=raw['input_tokens'], output_tokens=raw['output_tokens'], seconds=raw['seconds'],
            error=parsed.get('error'), raw_sha256=sha256_file(run / (req['request_id'] + '.raw.json'))))
        summary('IN_PROGRESS_NOT_QUALIFIED')
        print(json.dumps(dict(done=len(results), planned=len(jobs), **results[-1])), flush=True)

    while queue or active or not checked:
        if not queue and not active and not checked:
            checked = True
            if any(r['measurement_status'] not in ('measured_candidate', 'semantic_uncertainty') for r in results):
                summary('TECHNICAL_SMOKE_FAILED_REMAINDER_UNATTEMPTED')
                raise RuntimeError('development smoke failed; preserve attempts; do not hide missing cases')
            queue = deferred
        while queue and len(active) < cfg['concurrency']:
            j, ids, req = queue.pop(0)
            cached = cache.claim(req)
            if cached is not None:
                finish(j, req, cached, True)
                continue
            params = SamplingParams(**{k:v for k,v in decode.items() if k != 'thinking'},
                max_tokens=cfg['native_context']-len(ids), seed=j['seed'],
                structured_outputs=StructuredOutputsParams(json=req['json_schema']))
            engine.add_request(req['request_id'], {'prompt_token_ids': ids}, params)
            active[req['request_id']] = dict(job=j, request=req, started=time.monotonic(), input_tokens=len(ids))
        if not active:
            continue
        for output in engine.step():
            if output.request_id not in active or not output.outputs:
                continue
            s = active[output.request_id]; a = output.outputs[0]; elapsed = time.monotonic()-s['started']
            reason = None
            if output.finished:
                reason = 'natural_stop' if a.finish_reason == 'stop' else 'context_exhausted' if a.finish_reason == 'length' else str(a.finish_reason)
            elif elapsed >= cfg['technical_timeout_seconds']:
                reason = 'technical_timeout'
            elif repeated(list(a.token_ids)):
                reason = 'repetition_guard'
            if reason is None:
                continue
            if not output.finished:
                engine.abort_request([output.request_id])
            raw = dict(request_id=output.request_id, runtime_identity=identity, text=a.text,
                finish_reason=reason, model_finish_reason=a.finish_reason, model_stop_reason=a.stop_reason,
                input_tokens=s['input_tokens'], output_tokens=len(a.token_ids), output_token_ids=list(a.token_ids),
                seconds=elapsed, API_usd=0)
            cache.finish(output.request_id, raw); finish(s['job'], s['request'], raw, False)
            del active[output.request_id]
    summary('DEVELOPMENT_COMPLETE_CANDIDATE_NOT_QUALIFIED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight-only', action='store_true')
    main(parser.parse_args().preflight_only)
