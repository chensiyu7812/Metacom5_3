"""Bounded preparation/dispatch checks for the RS prompt comparison.

Called by the existing P2 runner. It does not load models, contact providers,
score responses or change the selected executor freeze.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

from metacom_pm.io import sha256_file
from .bound_generation import validate_and_project
from .cache import AttemptCache
from .schema import digest


# These are separate fixed batches, not a parameter for expanding a prior run.
# The first completed batch and all its starts remain in their original path.
PROTOCOL_CAPS = {
    'pm-rl1-rs-paired-development-v1': 16,
    'pm-rl1-rs-additional-contexts-v1-20261019': 41,
}


def read(path):
    return json.loads(Path(path).read_text())


def save_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists():
        if path.read_text() != encoded:
            raise ValueError('immutable artifact differs: ' + str(path))
    else:
        with path.open('x') as f:
            f.write(encoded)


def validate_package(package):
    package = Path(package).resolve()
    p = read(package / 'protocol.json')
    cap = PROTOCOL_CAPS.get(p['version'])
    if cap is None or p['max_generation_attempts'] != cap:
        raise ValueError('unknown diagnostic protocol or cap')
    for relative, expected in p['files'].items():
        if sha256_file(package / relative) != expected:
            raise ValueError('prepared file changed: ' + relative)
    for name, expected in p['source_files'].items():
        if sha256_file(Path(name)) != expected:
            raise ValueError('source/code changed: ' + name)
    jobs = read(package / 'jobs_private.json')
    if len(jobs) != cap or digest(jobs) != p['jobs_identity']:
        raise ValueError('fixed job list changed')
    if len({j['slot_id'] for j in jobs}) != cap or len({j['request']['request_id'] for j in jobs}) != cap:
        raise ValueError('duplicate slot/request')
    for j in jobs:
        validate_and_project(j['request'], p['runtime']['identity'])
    return p, jobs


def validate_authorization(protocol, authorization):
    cap = PROTOCOL_CAPS.get(protocol.get('version'))
    if cap is None or protocol.get('max_generation_attempts') != cap:
        raise ValueError('unknown diagnostic protocol/cap has no execution authorization')
    expected = dict(protocol_identity=digest(protocol), status='RESEARCHER_APPROVED',
        max_generation_attempts=cap, max_new_judge_requests=0, max_api_cost_usd=0,
        gpu_uuid=protocol['gpu_uuid'])
    if any(authorization.get(k) != v for k, v in expected.items()) or not authorization.get('user_instruction'):
        raise ValueError('this exact new generator batch has no matching execution authorization')


def execute_jobs(protocol, jobs, generator, before_request):
    """Use the original attempt cache; keep permanent per-slot start receipts.

    The caller holds the stage lock. No new-version directory or request hash
    can bypass a started slot in this fixed execution directory.
    """
    run = Path(protocol['execution_dir'])
    save_once(run / 'protocol.json', protocol)
    if (run / 'STOP.json').exists():
        return read(run / 'STOP.json')
    planned = {j['slot_id'] for j in jobs}
    starts = {p.stem.removesuffix('.started') for p in run.glob('*.started.json')}
    if not starts <= planned or len(starts) > protocol['max_generation_attempts']:
        raise ValueError('foreign start receipt or cap exceeded')
    cache = AttemptCache(run / 'attempts.sqlite')
    rows = []
    for job in jobs:
        slot = job['slot_id']; request = job['request']; rid = request['request_id']
        started_path = run / (slot + '.started.json')
        raw_path = run / (slot + '.raw.json')
        if started_path.exists():
            previous = read(started_path)
            if previous['request_identity'] != rid:
                raise ValueError('slot started under another request/version; never redispatch')
            if not raw_path.exists():
                raise RuntimeError('started request unresolved; no automatic retry')
            raw = read(raw_path)
            if raw['request_id'] != rid or raw['runtime_identity'] != generator.identity:
                raise ValueError('prior result binding mismatch')
        else:
            if len(list(run.glob('*.started.json'))) >= protocol['max_generation_attempts']:
                raise RuntimeError('generation cap reached')
            if not before_request():
                stop = dict(status='STOP_GPU_GUARD', next_slot=slot, completed_rows=rows)
                save_once(run / 'STOP.json', stop)
                return stop
            # Claim and permanent receipt precede model entry. A crash leaves
            # unresolved responsibility; neither representation permits retry.
            if cache.claim(request) is not None:
                raise RuntimeError('cache entry without a matching slot receipt')
            save_once(started_path, dict(slot_id=slot, request_identity=rid,
                old_request_id=job['old_request_id'], protocol_identity=digest(protocol),
                utc=datetime.now(timezone.utc).isoformat()))
            save_once(run / (slot + '.request.json'), request)
            try:
                raw = generator.generate(request)
            except Exception as exc:
                raw = dict(request_id=rid, runtime_identity=generator.identity, text='',
                    finish_reason='exception', exception_type=type(exc).__name__,
                    error=str(exc), api_cost_usd=0)
            save_once(raw_path, raw)
            cache.finish(rid, raw)
        rows.append(dict(slot_id=slot, request_id=rid, arm=job['arm'],
            row_id=job['row_id'], finish_reason=raw['finish_reason'],
            input_tokens=raw.get('input_tokens'), output_tokens=raw.get('output_tokens'),
            generation_seconds=raw.get('generation_seconds'),
            peak_allocated_bytes=raw.get('peak_allocated_bytes'),
            q=None, m=None, U=None, status='UNSCORED_DEVELOPMENT'))
        if raw['finish_reason'] != 'natural_stop' or not raw.get('text', '').strip():
            stop = dict(status='STOP_TECHNICAL_FAILURE', failed_slot=slot, rows=rows)
            save_once(run / 'STOP.json', stop)
            return stop
    result = dict(status='COMPLETE_UNSCORED', rows=rows, judge_requests=0,
        api_cost_usd=0, eligible_for_reward=False,
        started_attempts=len(list(run.glob('*.started.json'))))
    save_once(run / 'results.json', result)
    return result
