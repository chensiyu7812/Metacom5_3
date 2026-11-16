#!/usr/bin/env python3
"""One scope revision measured on the same 55 pilot jobs plus 12 fixed controls.

No source replies are generated; all scores remain development candidates.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.cache import AttemptCache
from metacom_pm.rl1.judge_scoped import messages_and_schema, parse_scoped as parse_measurement
from metacom_pm.rl1.judge_scoped import RUBRIC_V3 as RUBRIC, RUBRIC_ID, VERSION as PARSER_VERSION
from metacom_pm.rl1.schema import digest

PILOT = PROJECT / "outputs/pm_rl1/measurement_pilot_20260928_v1"
OUT = PROJECT / "outputs/pm_rl1/measurement_resolution_20260929_v1"
MODEL = Path('/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b')


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def repeated(ids):
    return len(ids) >= 128 and all(ids[-32:] == ids[-32*(i+1):-32*i] for i in range(1, 4))


def main():
    import torch
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import StructuredOutputsParams
    started = time.monotonic()
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1 or 'A6000' not in torch.cuda.get_device_name(0):
        raise RuntimeError('bind the free A6000 explicitly')
    if torch.cuda.mem_get_info(0)[0] < 44 * 1024**3:
        raise RuntimeError('insufficient free A6000 memory; no fallback')
    exam_path = OUT / 'scoped_common_exam_private.json'
    exam = json.loads(exam_path.read_text())
    if len(exam['jobs']) != 67 or any(j['split'] not in ('train','dev') for j in exam['jobs']):
        raise RuntimeError('exact common 55+12 development exam required')
    if len({j['job_id'] for j in exam['jobs']}) != 67:
        raise RuntimeError('duplicate jobs')
    cfg = json.loads((MODEL / 'config.json').read_text())
    context = cfg['text_config']['max_position_embeddings']
    runtime = dict(protocol='pm-rl1-qwen-scoped-final-development-v3', model_dir=str(MODEL),
        files={p.name: sha256_file(p) for p in sorted(MODEL.iterdir()) if p.is_file() and p.suffix in ('.json', '.safetensors', '.jinja', '.txt')},
        packages={p: importlib.metadata.version(p) for p in ('torch', 'transformers', 'vllm')},
        gpu=torch.cuda.get_device_name(0), cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),
        cuda_device_order=os.environ.get('CUDA_DEVICE_ORDER'), cuda_version=torch.version.cuda,
        backend='vllm', dtype='bfloat16', native_context=context, serving_context=context,
        output_token_cap=None, normal_stop='model EOS/EOT', technical_timeout_seconds=900,
        repetition_watchdog=dict(width=32, repeats=4), concurrency=4, gpu_memory_utilization=.88,
        max_num_batched_tokens=4096, enforce_eager=True, prefix_caching=False, language_model_only=True,
        thinking=True, temperature=1.0, top_p=.95, top_k=20, min_p=0.,
        presence_penalty=1.5, repetition_penalty=1., engine_seed=20260928,
        draw_rule='common seed per prefix across primary conditions; repeat uses a different predeclared seed',
        rubric_identity=RUBRIC_ID, parser_version=PARSER_VERSION,
        judge_code_sha256=sha256_file(PROJECT / 'src/metacom_pm/rl1/judge_scoped.py'),
        indexed_validator_sha256=sha256_file(PROJECT / 'src/metacom_pm/rl1/judge_indexed.py'),
        semantic_validator_sha256=sha256_file(PROJECT / 'src/metacom_pm/rl1/judge.py'),
        constrained_json=True, reasoning_parser='qwen3',
        runner_sha256=sha256_file(Path(__file__)))
    identity = digest(runtime)
    run = OUT / 'scoped_common_v3' / identity
    save(run / 'runtime.json', dict(**runtime, identity=identity))
    save(run / 'rubric.json', dict(identity=RUBRIC_ID, text=RUBRIC))
    save(run / 'exam_binding.json', dict(exam_sha256=sha256_file(exam_path), calls=len(exam['jobs']), source_exam=str(exam_path), stage='scoped_common_v3', job_ids=[j['job_id'] for j in exam['jobs']]))
    cache = AttemptCache(run / 'attempts.sqlite')
    queue, results, active = [], [], {}
    for j in exam['jobs']:
        msg, schema = messages_and_schema(j['evidence'], j['reply'])
        row = dict(messages=msg, json_schema=schema, executor_identity=identity,
            draw_identity=j['draw_id'], seed=j['seed'], rubric_identity=RUBRIC_ID,
            evidence_identity=digest(j['evidence']), response_identity=digest(j['reply']))
        request = dict(**row, request_id=digest(row))
        save(run / (request['request_id'] + '.request.json'), request)
        # Claims are made only immediately before engine submission below.
        queue.append((j, request))
    print(json.dumps(dict(stage='load', jobs=len(queue), runtime_identity=identity, native_context=context)), flush=True)
    load_start = time.monotonic()
    llm = LLM(model=str(MODEL), dtype='bfloat16', max_model_len=context,
        gpu_memory_utilization=.88, max_num_seqs=4, max_num_batched_tokens=4096,
        enforce_eager=True, enable_prefix_caching=False, seed=20260928, language_model_only=True, reasoning_parser='qwen3')
    load_seconds = time.monotonic() - load_start
    tokenizer, engine = llm.get_tokenizer(), llm.llm_engine
    print(json.dumps(dict(stage='loaded', seconds=load_seconds)), flush=True)
    engine_started = time.monotonic()

    def finish(j, req, raw, cache_hit):
        parsed = parse_measurement(raw['text'], evidence=j['evidence'], reply=j['reply'],
            runtime_identity=identity, draw_id=j['draw_id'], finish_reason=raw['finish_reason'])
        save(run / (req['request_id'] + '.raw.json'), raw)
        save(run / (req['request_id'] + '.measurement.json'), parsed)
        row = dict(job_id=j['job_id'], pilot_index=j['pilot_index'], condition=j['condition'],
            repeat=j['repeat'], exam_section=j['exam_section'], request_id=req['request_id'], cache_hit=cache_hit,
            finish_reason=raw['finish_reason'], measurement_status=parsed['measurement_status'],
            q=parsed['q'], m=parsed['m'], input_tokens=raw.get('input_tokens'),
            output_tokens=raw.get('output_tokens'), seconds=raw.get('seconds'), error=parsed.get('error'))
        results.append(row)
        save(run / 'summary.json', dict(status='CANDIDATE_MEASUREMENT_NOT_TRAINING_REWARD', rows=results,
            api_cost_usd=0, load_seconds=load_seconds, engine_wall_seconds=time.monotonic()-engine_started,
            total_process_seconds=time.monotonic()-started, training_updates=0, independent_reviews=0, planned_jobs=len(exam['jobs']), stage='scoped_common_v3'))
        print(json.dumps(row, ensure_ascii=False), flush=True)

    while queue or active:
        while queue and len(active) < 4:
            j, req = queue.pop(0)
            ids = tokenizer.apply_chat_template(req['messages'], tokenize=True,
                add_generation_prompt=True, return_dict=False, enable_thinking=True)
            if len(ids) >= context:
                raise RuntimeError('full legal evidence exceeds native context; never truncate')
            cached = cache.claim(req)
            if cached is not None:
                finish(j, req, cached, True)
                continue
            params = SamplingParams(temperature=1., top_p=.95, top_k=20, min_p=0.,
                presence_penalty=1.5, repetition_penalty=1., max_tokens=context-len(ids), seed=j['seed'],
                structured_outputs=StructuredOutputsParams(json=req['json_schema']))
            engine.add_request(req['request_id'], {'prompt_token_ids': ids}, params)
            active[req['request_id']] = dict(job=j, request=req, started=time.monotonic(), input_tokens=len(ids))
        if not active:
            continue
        for output in engine.step():
            if output.request_id not in active or not output.outputs:
                continue
            state = active[output.request_id]; answer = output.outputs[0]
            elapsed = time.monotonic() - state['started']
            reason = None
            if output.finished:
                reason = 'natural_stop' if answer.finish_reason == 'stop' else 'context_exhausted' if answer.finish_reason == 'length' else str(answer.finish_reason)
            elif elapsed >= 900:
                reason = 'technical_timeout'
            elif repeated(list(answer.token_ids)):
                reason = 'repetition_guard'
            if reason is None:
                continue
            if not output.finished:
                engine.abort_request([output.request_id])
            raw = dict(request_id=output.request_id, runtime_identity=identity, text=answer.text,
                finish_reason=reason, model_finish_reason=answer.finish_reason, model_stop_reason=answer.stop_reason,
                input_tokens=state['input_tokens'], output_tokens=len(answer.token_ids), output_token_ids=list(answer.token_ids),
                seconds=elapsed, api_cost_usd=0)
            cache.finish(output.request_id, raw)
            finish(state['job'], state['request'], raw, False)
            del active[output.request_id]
    save(OUT / 'scoped_common_v3_pointer.json', dict(run_dir=str(run), runtime_identity=identity,
        summary_sha256=sha256_file(run / 'summary.json'), jobs=len(results)))


if __name__ == '__main__':
    main()
