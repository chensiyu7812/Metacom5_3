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


def load_frozen_generator(runtime):
    """Shared loader for the original pool and separately authorized diagnostics."""
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
    return generator


def run_rs_package(args):
    # No model, device or account operation before the exact package and its
    # new execution authorization have passed. This never uses the old D slots.
    from metacom_pm.rl1.rs_development import (validate_package,
        validate_authorization, execute_jobs, save_once)
    protocol, jobs = validate_package(args.rs_package)
    print(json.dumps(dict(preflight='OK', jobs=len(jobs), mode='RS diagnostic',
        protocol_identity=digest(protocol), execution_authorized=False)), flush=True)
    if args.preflight_only:
        return
    if not args.execution_authorization:
        raise RuntimeError('supply the separately approved exact RS batch authorization')
    authorization = read(args.execution_authorization)
    validate_authorization(protocol, authorization)
    import fcntl
    import os
    import subprocess
    run = Path(protocol['execution_dir'])
    run.mkdir(parents=True, exist_ok=True)
    with (run / '.dispatch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save_once(run / 'protocol.json', protocol)
        save_once(run / 'authorization.json', authorization)
        if (run / 'STOP.json').exists():
            raise RuntimeError('existing diagnostic STOP retained; no implicit resume')
        if (run / 'results.json').exists():
            print('Already complete; no GPU load or redispatch.', flush=True)
            return
        if (run / 'launch.json').exists():
            raise RuntimeError('earlier launch retained; no implicit second idle wait or interrupted-run restart')
        for receipt in run.glob('*.started.json'):
            if not receipt.with_name(receipt.name.replace('.started.json', '.raw.json')).exists():
                raise RuntimeError('unresolved prior model entry; no retry or GPU load')
        runtime = protocol['runtime']
        if (os.environ.get('CUDA_VISIBLE_DEVICES') != runtime['cuda_visible_devices']
                or os.environ.get('CUDA_DEVICE_ORDER') != runtime['cuda_device_order']):
            raise RuntimeError('frozen CUDA deployment changed')
        from datetime import datetime, timezone
        save_once(run / 'launch.json', dict(utc=datetime.now(timezone.utc).isoformat(),
            protocol_identity=digest(protocol), authorization_identity=digest(authorization)))
        # Establish the UUID of the frozen PCI-ordered CUDA ordinal as well as
        # checking the card by UUID; a name-only match is insufficient.
        mapping = subprocess.run(['nvidia-smi', '--query-gpu=pci.bus_id,uuid',
            '--format=csv,noheader'], capture_output=True, text=True, timeout=20)
        save_once(run / 'device_mapping.json', dict(returncode=mapping.returncode,
            stdout=mapping.stdout, stderr=mapping.stderr))
        rows = sorted([[f.strip() for f in r.split(',')] for r in mapping.stdout.splitlines()])
        ordinal = int(runtime['cuda_visible_devices'])
        if (mapping.returncode or len(rows) <= ordinal or any(len(r) != 2 for r in rows)
                or rows[ordinal][1] != protocol['gpu_uuid']):
            save_once(run / 'STOP.json', dict(status='STOP_DEVICE_MAPPING'))
            raise RuntimeError('frozen CUDA ordinal / designated UUID mismatch')
        sys.path.insert(0, str(Path(protocol['gpu_guard_path']).parent))
        from resume_engineering import GPUChecks
        checks = GPUChecks(run / 'gpu_checks')
        idle = checks.wait_idle(seconds=300)
        if not idle['eligible']:
            save_once(run / 'STOP.json', dict(status='STOP_GPU_PREFLIGHT', detail=idle))
            return
        for name, expected in runtime['model_files'].items():
            if sha256_file(Path(runtime['model_dir']) / name) != expected:
                save_once(run / 'STOP.json', dict(status='STOP_MODEL_FILE_DRIFT', file=name))
                raise RuntimeError('local model file changed; no download')
        for name, expected in runtime['adapter']['files'].items():
            if sha256_file(Path(runtime['adapter']['path']) / name) != expected:
                save_once(run / 'STOP.json', dict(status='STOP_ADAPTER_FILE_DRIFT', file=name))
                raise RuntimeError('local adapter file changed')
        generator = load_frozen_generator(runtime)
        actual = dict(generator.manifest, identity=generator.identity)
        save_once(run / 'runtime_observed.json', actual)
        if digest(actual) != digest(runtime):
            save_once(run / 'STOP.json', dict(status='STOP_RUNTIME_DRIFT'))
            raise RuntimeError('frozen runtime mismatch')
        result = execute_jobs(protocol, jobs, generator,
            before_request=lambda: checks.check(own_pid=os.getpid())['eligible'])
        print(json.dumps(dict(status=result['status'],
            started=len(list(run.glob('*.started.json'))))), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preflight-only', action='store_true')
    ap.add_argument('--arm', choices=('primary', 'secondary'), default='primary')
    ap.add_argument('--rs-package', type=Path, help='versioned, separately authorized RS diagnostic package')
    ap.add_argument('--execution-authorization', type=Path)
    args = ap.parse_args()
    if args.rs_package:
        run_rs_package(args)
        return
    # The legacy pool used the runner hash in its directory identity. Editing
    # this CLI must not create a fresh directory and replay all old requests.
    pointer = OUT / (args.arm + '_generation_pointer.json')
    if pointer.exists():
        legacy = read(Path(read(pointer)['run_dir']) / 'protocol.json')
        if legacy['runner_sha256'] != sha256_file(Path(__file__)):
            raise RuntimeError('legacy runner identity changed; refuse a new pool/replay; use the separately scoped RS entry')
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
    generator = load_frozen_generator(runtime)
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
