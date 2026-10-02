#!/usr/bin/env python3
"""Generate the frozen P2 shared pool with the selected source-bound executor.

Missing or failed calls remain explicit. Interrupted claims cannot silently
restart. This stage creates replies, never reward values or teacher labels.
"""
import argparse
from collections import Counter
import importlib.metadata
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.cache import AttemptCache
from metacom_pm.rl1.bound_generation import BoundNaturalGenerator, PROTOCOL, validate_and_project

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2'
OUT = ROOT / 'P2/common_pool'


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preflight-only', action='store_true')
    ap.add_argument('--arm', choices=('primary', 'secondary'), default='primary')
    args = ap.parse_args()
    start = time.monotonic()
    freeze = read(OUT / 'input_freeze.json')
    for name, expected in freeze['files'].items():
        assert sha256_file(OUT / name) == expected, name
    for name, expected in freeze['source_files'].items():
        assert sha256_file(PROJECT / name) == expected, name
    executor = read(ROOT / 'P2/executor_freeze.json')
    for name, expected in executor['files'].items():
        assert sha256_file(PROJECT / name) == expected, name
    assert executor['renderer_identity'] == freeze['renderer_identity']
    if args.arm == 'primary':
        slots = read(OUT / 'slots_private.json')['rows']
        assert len(slots) == 586
        runtime = executor['primary_runtime']
        inputs_path = OUT / 'slots_private.json'
    else:
        if executor['selected'] == 'base':
            raise RuntimeError('primary is base; secondary would duplicate it')
        secondary = read(OUT / 'secondary_inputs_private.json')
        for name, expected in secondary['source_files'].items():
            assert sha256_file(PROJECT / name) == expected, name
        slots = secondary['rows']
        assert len(slots) + len(secondary['unavailable']) == 54
        assert all(s['split'] == 'dev' for s in slots)
        runtime = executor['base_runtime']
        inputs_path = OUT / 'secondary_inputs_private.json'
    assert all(s['split'] in ('train', 'dev') for s in slots)
    specs = read(ROOT / 'P1/episode_specs_private.json')
    jobs = []
    for slot in slots:
        spec = specs[slot['index']]
        assert slot['prefix_identity'] == digest(spec['prefix'])
        assert digest(slot['messages']) == slot['messages_identity']
        payload = dict(messages=slot['messages'], executor_identity=runtime['identity'],
            draw_identity=executor['terminal_draw_identity'], renderer_identity=freeze['renderer_identity'],
            provenance=dict(protocol=PROTOCOL, prefix_identity=slot['prefix_identity'],
                inventory_identity=digest(spec['inventory']), retrieval_identity=spec['retrieval_identity'],
                canonical_counts=slot['counts']))
        request = dict(request_id=digest(payload), **payload)
        validate_and_project(request, runtime['identity'])
        jobs.append(dict(slot=slot, request=request))
    assert len({j['request']['request_id'] for j in jobs}) == len(slots)
    protocol = dict(version='pm-rl1-p2-common-pool-v1', arm=args.arm, jobs=len(jobs),
        jobs_identity=digest(jobs), executor_freeze_sha256=sha256_file(ROOT / 'P2/executor_freeze.json'),
        input_freeze_sha256=sha256_file(OUT / 'input_freeze.json'),
        inputs_sha256=sha256_file(inputs_path),
        runner_sha256=sha256_file(Path(__file__)),
        decode='Frozen greedy natural EOS/EOT; native context remainder and existing watchdog',
        reward_status='UNMEASURED_NOT_ZERO', quality_retries=0)
    run = OUT / 'generation' / digest(protocol)
    if (run / 'protocol.json').exists():
        assert read(run / 'protocol.json') == protocol
    else:
        save(run / 'protocol.json', protocol)
        save(run / 'jobs_private.json', jobs)
    assert digest(read(run / 'jobs_private.json')) == digest(jobs)
    save(OUT / (args.arm + '_generation_pointer.json'), dict(run_dir=str(run)))
    print(json.dumps(dict(preflight='OK', jobs=len(jobs), run_dir=str(run))), flush=True)
    if args.preflight_only:
        return
    import torch
    if torch.cuda.device_count() != 1 or 'A6000' not in torch.cuda.get_device_name(0):
        raise RuntimeError('bind A6000; no fallback')
    generator = BoundNaturalGenerator(Path(runtime['model_dir']), minimum_free_gib=40)
    if runtime['adapter']:
        from peft import PeftModel
        adapter = runtime['adapter']
        assert importlib.metadata.version('peft') == adapter['peft_version'], 'adapter loader package drift'
        generator.model = PeftModel.from_pretrained(generator.model, adapter['path'],
            adapter_name=adapter['name'], is_trainable=False).eval()
        generator.manifest = dict(generator.manifest, adapter=adapter)
        generator.identity = digest(generator.manifest)
    # JSON persists EOS tuples as arrays; compare the complete canonical
    # manifest instead of Python container types. No field is discarded.
    actual_runtime = dict(generator.manifest, identity=generator.identity)
    save(run / 'runtime_observed.json', actual_runtime)
    assert digest(actual_runtime) == digest(runtime), 'frozen runtime mismatch'
    save(run / 'runtime.json', runtime)
    cache = AttemptCache(run / 'attempts.sqlite')
    rows = []
    for job in jobs:
        request = job['request']; sid = job['slot']['slot_id']; rid = request['request_id']
        save(run / (rid + '.request.json'), request)
        cached = cache.claim(request)
        if cached is None:
            try:
                raw = generator.generate(request)
            except Exception as exc:
                raw = dict(request_id=rid, runtime_identity=generator.identity,
                    text='', finish_reason='exception', exception_type=type(exc).__name__,
                    error=str(exc), api_cost_usd=0)
            cache.finish(rid, raw)
        else:
            raw = cached
        save(run / (rid + '.raw.json'), raw)
        row = {k: job['slot'][k] for k in ('index', 'owner', 'split', 'prefix_identity', 'plan_index', 'counts', 'resource_tokens')}
        row.update(slot_id=sid, request_id=rid, finish_reason=raw['finish_reason'],
            raw_sha256=sha256_file(run / (rid + '.raw.json')), cache_hit=cached is not None,
            input_tokens=raw.get('input_tokens'), output_tokens=raw.get('output_tokens'),
            generation_seconds=raw.get('generation_seconds'), reward_status='UNMEASURED_NOT_ZERO')
        rows.append(row)
        save(run / 'summary.json', dict(status='COMPLETE_UNSCORED' if len(rows) == len(jobs) else 'IN_PROGRESS',
            planned=len(jobs), rows=rows, statuses=dict(Counter(r['finish_reason'] for r in rows)),
            physical_calls_this_invocation=sum(not r['cache_hit'] for r in rows),
            load_seconds=generator.load_seconds, total_seconds_this_invocation=time.monotonic() - start,
            API_usd=0, reward_measurements=0))
        if len(rows) <= 3 or len(rows) % 16 == 0 or len(rows) == len(jobs):
            print(json.dumps(dict(done=len(rows), total=len(jobs), finish=raw['finish_reason'])), flush=True)
        if raw['finish_reason'] == 'exception':
            raise RuntimeError('generation exception retained; no automatic resend')


if __name__ == '__main__':
    main()
