"""Source-bound historical G results -> durable feedback queue, without G/J.

Only WAITING generation rows with an exact verified cache entry are settled.
An interrupted STARTED row is never reclaimed. Model absence is a cache miss,
not permission to generate; measurement rows and policy trajectories are never
copied or modified. Cache ingestion and its provenance receipt are atomic.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .bound_generation import validate_and_project
from .calibration_workflow import stamp, verify_identity
from .schema import digest

VERSION = 'pmrl1-source-bound-generation-reuse-v1'
FIELDS = {'request_path', 'request_sha256', 'raw_path', 'raw_sha256'}


def _read(path, expected):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('generation cache file changed')
    return json.loads(data)


def _entry(entry):
    if set(entry) != FIELDS:
        raise ValueError('complete request/result cache binding required')
    request = _read(entry['request_path'], entry['request_sha256'])
    raw = _read(entry['raw_path'], entry['raw_sha256'])
    validate_and_project(request, request['executor_identity'])
    if (raw.get('request_id') != request['request_id']
            or raw.get('runtime_identity') != request['executor_identity']
            or raw.get('source_provenance_identity') != digest(request['provenance'])
            or raw.get('finish_reason') != 'natural_stop'
            or not isinstance(raw.get('text'), str) or not raw['text'].strip()):
        raise ValueError('cache result is not a complete source-bound natural reply')
    return request, raw


def make_cache_index(entries, *, source_identity):
    if not entries or not source_identity:
        raise ValueError('nonempty explicit cache source required')
    indexed = {}
    for entry in entries:
        request, _ = _entry(entry)
        rid = request['request_id']
        if rid in indexed:
            raise ValueError('duplicate cache request; select original artifact explicitly')
        indexed[rid] = deepcopy(entry)
    return stamp(dict(version=VERSION, source_identity=source_identity,
                      entries=indexed, new_generation_authorized=False))


def replay_cached_generations(queue, index, *, max_items=16):
    verify_identity(index)
    if (index.get('version') != VERSION or index.get('new_generation_authorized') is not False
            or type(max_items) is not int or max_items < 1):
        raise ValueError('bounded offline cache replay required')
    reused, misses = [], []
    with queue.transaction() as db:
        # No in-flight rows are read or retried, and a preceding measurement
        # cannot block an unrelated generation cache hit.
        rows = db.execute("SELECT id,payload FROM feedback WHERE kind='generation' "
                          "AND state='WAITING' ORDER BY rowid").fetchall()
        for key, payload in rows:
            request = json.loads(payload)
            if key != digest(dict(kind='generation', payload=request)):
                raise ValueError('queued generation payload changed')
            validate_and_project(request, request['executor_identity'])
            entry = index['entries'].get(request['request_id'])
            if entry is None:
                misses.append(key)
                continue
            cached_request, raw = _entry(entry)
            if cached_request != request:
                raise ValueError('cache belongs to a different complete request')
            db.execute('CREATE TABLE IF NOT EXISTS generation_cache_reuse '
                       '(id TEXT PRIMARY KEY, index_identity TEXT, request_sha256 TEXT, '
                       'raw_sha256 TEXT, result_identity TEXT)')
            db.execute('INSERT INTO generation_cache_reuse VALUES (?,?,?,?,?)',
                       (key, index['identity'], entry['request_sha256'],
                        entry['raw_sha256'], digest(raw)))
            result = json.dumps(raw, sort_keys=True, ensure_ascii=False, allow_nan=False)
            db.execute("UPDATE feedback SET state='SETTLED', result=? "
                       "WHERE id=? AND state='WAITING'", (result, key))
            reused.append(key)
            if len(reused) == max_items:
                break
    return dict(status='OFFLINE_CACHE_REPLAY', reused=reused, cache_misses=misses,
                new_generation_calls=0, new_measurement_calls=0, new_cost_usd='0')
