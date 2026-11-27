#!/usr/bin/env python3
"""NAA B-line CLI: write -> embed -> retrieve -> materialize -> infer -> export -> aggregate.

Runtime inputs only: A's runtime JSONL + histories, and (for arms C/D and the retrieval
coverage diagnostic) A's Direct coordinate manifest. The evaluation sidecar is never
opened here; scoring is A's scorer on the exported predictions.
`infer` without a researcher approval refuses before any device access; `--plumbing`
is a CPU dry run whose outputs are labelled plumbing and cannot be scored as a model.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

from metacom_pm.need_aware.data.contracts import digest, load_runtime
from metacom_pm.need_aware.data.history import HistoryResolver
from metacom_pm.need_aware.memory import reader as R
from metacom_pm.need_aware.memory.writer import MemoryWriter, StoreCache, WRITER_VERSION, write_for_task
from metacom_pm.need_aware.agent import arms as ARMS
from metacom_pm.need_aware.agent.retrieval import (BGE_QUERY_PREFIX, BGEEncoder, EmbeddingCache, OwnerIndex,
                                                    RetrievalSpec, query_text, recency, RETRIEVAL_VERSION)
from metacom_pm.need_aware.runtime import models as M
from metacom_pm.need_aware.runtime import requests as Q
from metacom_pm.need_aware.runtime.authorization import (MANIFEST_PROTOCOL, authorize, load_manifest,
                                                          manifest_sha256, refuse_without)
from metacom_pm.need_aware.runtime.budget import default_caps, summarize
from metacom_pm.need_aware.runtime.ledger import Ledger

ROOT = Path(__file__).resolve().parents[3]
BGE_PATH = '/opt/tokkio-data0/tokkio_models/huggingface/hub/models--BAAI--bge-small-en-v1.5/snapshots/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'


def jdump(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def jsonl(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tasks_of(runtime_root, modes=('mcq', 'generation')):
    out = []
    for mode in modes:
        out += load_runtime(Path(runtime_root) / f'tasks.{mode}.jsonl')
    return out


def direct_map(path):
    rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    return {r['task_id']: r for r in rows}


def stores_for(tasks, runtime_root, cache):
    resolver = HistoryResolver(runtime_root); writer = MemoryWriter(); out = {}
    for t in tasks:
        store = write_for_task(resolver, writer, t)
        cache.put(store)
        out[t.task_id] = store
    return out


# ---------------------------------------------------------------- write
def cmd_write(a):
    t0 = time.monotonic()
    tasks = tasks_of(a.runtime_root)
    cache = StoreCache(Path(a.out) / 'stores')
    stores = stores_for(tasks, a.runtime_root, cache)
    units = [u for s in stores.values() for u in s.units]
    uniq = {s.store_id: s for s in stores.values()}
    summary = dict(writer_version=WRITER_VERSION, tasks=len(tasks), stores=len(uniq),
                   owners=len({s.owner_id for s in uniq.values()}),
                   units_total=sum(len(s.units) for s in uniq.values()),
                   user_units=sum(u.is_current_user for s in uniq.values() for u in s.units),
                   assistant_units=sum(not u.is_current_user for s in uniq.values() for u in s.units),
                   excluded=dict(Counter(x['reason'] for s in uniq.values() for x in s.excluded)),
                   situation=dict(Counter(s.situation for s in uniq.values())),
                   constraint_candidates=dict(Counter(c for s in uniq.values() for u in s.units for c in u.constraint_candidates)),
                   stores_with_forget_candidate=sum(any('forget_request' in u.constraint_candidates for u in s.units) for s in uniq.values()),
                   forget_requests=sum(len(s.constraints) for s in uniq.values()),
                   forget_requests_linked=sum(c['target_unit_id'] is not None for s in uniq.values() for c in s.constraints),
                   reported_at_non_null=sum(u.reported_at is not None for u in units),
                   query_or_options_seen_by_writer=False, cpu_seconds=round(time.monotonic() - t0, 2))
    jdump(Path(a.out) / 'write_summary.json', summary)
    jsonl(Path(a.out) / 'task_stores.jsonl', [dict(task_id=k, store_id=v.store_id) for k, v in sorted(stores.items())])
    print(json.dumps(summary, indent=2))


# ---------------------------------------------------------------- embed
def cmd_embed(a):
    t0 = time.monotonic()
    cache = StoreCache(Path(a.out) / 'stores')
    ids = sorted({json.loads(x)['store_id'] for x in (Path(a.out) / 'task_stores.jsonl').read_text().splitlines()})
    enc = BGEEncoder(a.encoder, threads=a.threads)
    model_id = RetrievalSpec().dense_model
    emb = EmbeddingCache(Path(a.out) / 'embeddings', model_id)
    built = reused = n = 0
    for sid in ids:
        store = cache.get(sid)
        _, hit = emb.get_or_build(store, store.units, enc)
        built += not hit; reused += hit; n += len(store.units)
    summary = dict(model=model_id, stores=len(ids), units=n, built=built, reused=reused,
                   truncated_at_512=enc.truncated, device='cpu', threads=a.threads,
                   cpu_seconds=round(time.monotonic() - t0, 2))
    jdump(Path(a.out) / 'embed_summary.json', summary)
    print(json.dumps(summary, indent=2))


# ---------------------------------------------------------------- shared helpers
class SymmetricCounter:
    """Evidence tokens = max over the compared generators' native tokenizers (same evidence for both)."""

    def __init__(self, labels):
        self.toks = [M.NativeTokenizer(M.MODELS[x]) for x in labels]
        self.memo = {}

    def __call__(self, text):
        if text not in self.memo:
            self.memo[text] = max(t.count(text) for t in self.toks)
        return self.memo[text]


def load_vectors(out, store):
    emb = EmbeddingCache(Path(out) / 'embeddings', RetrievalSpec().dense_model)
    p = emb._path(store.store_id)
    return json.loads(p.read_text())['vectors'] if p.exists() else None


class QueryEncoder:
    def __init__(self, path):
        self.enc = BGEEncoder(path, threads=4)
        self.memo = {}

    def __call__(self, text):
        if text not in self.memo:
            self.memo[text] = self.enc.encode([BGE_QUERY_PREFIX + text])[0]
        return self.memo[text]


SPEC_GRID = [RetrievalSpec(backend=b, unit_filter=f, expand_next=e)
             for b in ('bm25', 'dense', 'hybrid') for f in ('all', 'user_only') for e in (False, True)]


# ---------------------------------------------------------------- retrieve (CPU + coverage diagnostic)
def cmd_retrieve(a):
    t0 = time.monotonic()
    tasks = tasks_of(a.runtime_root, ('mcq',))
    direct = direct_map(a.direct)
    cache = StoreCache(Path(a.out) / 'stores')
    task_store = {json.loads(x)['task_id']: json.loads(x)['store_id'] for x in (Path(a.out) / 'task_stores.jsonl').read_text().splitlines()}
    count = SymmetricCounter(a.models.split(','))
    backends = a.backends.split(',')
    grid = [spec for spec in SPEC_GRID if spec.backend in backends]
    qenc = QueryEncoder(a.encoder) if set(backends) & {'dense', 'hybrid'} else None
    budgets = [int(x) for x in a.budgets.split(',')]
    rows = []
    timing = defaultdict(list)
    for t in tasks:
        store = cache.get(task_store[t.task_id])
        d = direct.get(t.task_id)
        targets = [s['source_id'] for s in d['spans']] if d and d['status'] == 'located_unique' else None
        q = query_text(t)
        qv = None
        if qenc:
            s0 = time.perf_counter(); qv = qenc(q); timing['query_encode_s'].append(time.perf_counter() - s0)
        vecs = load_vectors(a.out, store) if qenc else None
        conds = [('A_recency', None)] + [(spec.identity, spec) for spec in grid]
        for name, spec in conds:
            s0 = time.perf_counter()
            if spec is None:
                ranked = recency(store); contiguous = True
            else:
                ranked = OwnerIndex(store, spec, unit_vectors=vecs).rank(q, query_vector=qv); contiguous = False
            timing['rank_s:' + ('A' if spec is None else spec.backend)].append(time.perf_counter() - s0)
            for b in budgets:
                p = R.pack(ranked, count, b, contiguous=contiguous)
                got = {u.unit_id for u in p.units}
                row = dict(task_id=t.task_id, condition=name, budget=b, delivered=len(got), tokens=p.tokens,
                           direct_status=d['status'] if d else 'absent')
                if targets:
                    user_t = [x for x in targets if store.by_id().get(x) and store.by_id()[x].is_current_user]
                    row.update(recall=sum(x in got for x in targets) / len(targets), any_hit=any(x in got for x in targets),
                               user_recall=(sum(x in got for x in user_t) / len(user_t)) if user_t else None)
                rows.append(row)
    agg = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if 'recall' in r:
            key = (r['condition'], r['budget'])
            agg[key]['recall'].append(r['recall']); agg[key]['any_hit'].append(r['any_hit'])
            if r['user_recall'] is not None:
                agg[key]['user_recall'].append(r['user_recall'])
            agg[key]['tokens'].append(r['tokens'])
    names = {spec.identity: asdict(spec) for spec in grid}
    table = []
    for (cond, b), v in sorted(agg.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        table.append(dict(condition=cond, spec=names.get(cond, 'A_recency'), budget=b, n=len(v['recall']),
                          mean_recall=round(statistics.mean(v['recall']), 4),
                          any_hit_rate=round(statistics.mean(v['any_hit']), 4),
                          mean_user_recall=round(statistics.mean(v['user_recall']), 4) if v['user_recall'] else None,
                          mean_tokens=round(statistics.mean(v['tokens']), 1)))
    simple = {'bm25': 0, 'dense': 1, 'hybrid': 2}
    chosen = {}
    for b in budgets:
        cand = [r for r in table if r['budget'] == b and r['condition'] != 'A_recency']
        best = max(cand, key=lambda r: (r['mean_recall'], r['any_hit_rate'], -simple[r['spec']['backend']]))
        chosen[str(b)] = best
    summary = dict(retrieval_version=RETRIEVAL_VERSION, tasks=len(tasks), direct_located=sum(1 for t in tasks if direct.get(t.task_id, {}).get('status') == 'located_unique'),
                   budgets=budgets, symmetric_counter=a.models, table=table, best_by_budget=chosen,
                   selection_rule='max mean Direct-span recall on the 240 frozen dev tasks, then any-hit, then simpler backend; '
                                  'diagnostic coverage only, Direct ids never enter arm B',
                   timing={k: dict(n=len(v), mean_ms=round(1000 * statistics.mean(v), 3),
                                   p95_ms=round(1000 * sorted(v)[int(.95 * (len(v) - 1))], 3)) for k, v in timing.items()},
                   options_used_in_query=False, cpu_seconds=round(time.monotonic() - t0, 2))
    jsonl(Path(a.out) / f'retrieval_rows{a.tag}.private.jsonl', rows)
    jdump(Path(a.out) / f'retrieval_summary{a.tag}.json', summary)
    print(json.dumps(dict(best_by_budget=chosen, cpu_seconds=summary['cpu_seconds']), indent=2))


# ---------------------------------------------------------------- materialize
def bind_logical_slots(rows, tasks, direct, bindings, path):
    """One-to-one binding of actual requests to A's frozen WP2 logical slots, in A's order."""
    slots = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    by_model = {b.model_id: label for label, b in bindings.items()}
    task_sha = {t.task_id: digest(t.to_dict()) for t in tasks}
    mine = {(r['task_id'], r['arm'], r['model_label']): r for r in rows}
    ordered = []
    for s in slots:
        label = by_model.get(s['model_id'])
        if label is None or s['task_id'] not in task_sha:
            continue
        r = mine.pop((s['task_id'], s['arm'], label))
        b = bindings[label]
        if s['model_revision'] != b.revision or s['runtime_task_sha256'] != task_sha[s['task_id']]:
            raise SystemExit('logical slot task/model identity differs: ' + s['logical_request_sha256'])
        if s['arm'] in 'CD' and s['direct_coordinate_manifest_sha256'] != digest(direct[s['task_id']]):
            raise SystemExit('logical slot Direct manifest differs')
        if (s['status'] == 'not_evaluable') != (r['status'] == 'not_evaluable'):
            raise SystemExit('logical slot evaluability differs: ' + r['logical_id'])
        if r['status'] != 'not_evaluable':
            d = r['decode']
            common = {k: s['decode'][k] for k in ('do_sample', 'enable_thinking', 'seed', 'eos_token_id', 'pad_token_id', 'suppress_tokens')}
            if any(d[k] != v for k, v in common.items()) or d['max_new_tokens'] != s['output_cap_tokens'] \
                    or s['input_cap_tokens'] != M.COMMON_INPUT_CAP or s['backend_context_tokens'] != M.BACKEND_CONTEXT_CAP:
                raise SystemExit('logical slot decode/caps differ: ' + r['logical_id'])
        r['logical_request_sha256'] = s['logical_request_sha256']
        ordered.append(r)
    if mine:
        raise SystemExit(f'{len(mine)} materialized requests have no A logical slot')
    return ordered, file_sha(path)



# HF loading-info allowances: G0e ties lm_head to embed_tokens (historical CHECKPOINT_CPU.json);
# Qwen3.5 ships 15 multi-token-prediction tensors the HF text path does not use.
LOAD_ALLOWANCES = {'G0e': dict(allowed_missing=['lm_head.weight'], allowed_unused=[]),
                   'Qwen35': dict(allowed_missing=[], allowed_unused='QWEN_MTP_UNUSED')}


def checkpoint_headers(spec):
    from metacom_pm.rl1v3.generator.runprep_checkpoint import QWEN_MTP_UNUSED, read_header
    hs = [read_header(p)[1] for p in sorted(Path(spec.path).glob('*.safetensors'))]
    allow = dict(LOAD_ALLOWANCES[spec.label])
    if allow['allowed_unused'] == 'QWEN_MTP_UNUSED':
        allow['allowed_unused'] = sorted(QWEN_MTP_UNUSED)
    return dict(files=[h['file'] for h in hs], header_sha256=[h['header_sha256'] for h in hs],
                tensors=sum(h['tensors'] for h in hs), tensor_data_read=False, **allow)


def verify_model_bytes(spec, deadline):
    """Fresh full SHA-256 of every model file against A's inventory before any load."""
    out = {}
    for name, expected in spec['files_sha256'].items():
        h = hashlib.sha256()
        with (Path(spec['path']) / name).open('rb') as f:
            for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
                if time.monotonic() > deadline:
                    raise SystemExit('model byte verification deadline')
                h.update(block)
        if h.hexdigest() != expected:
            raise SystemExit('model file hash mismatch: ' + spec['label'] + '/' + name)
        out[name] = expected
    return out


def runtime_pins():
    import importlib.metadata as md
    import platform
    return dict(python=platform.python_version(), python_executable=sys.executable,
                packages={k: md.version(k) for k in ('torch', 'transformers', 'tokenizers', 'safetensors')},
                worker_module='metacom_pm.need_aware.runtime.hf_worker')


def cmd_materialize(a):
    t0 = time.monotonic()
    tasks = tasks_of(a.runtime_root, (a.mode,))
    if a.limit:
        tasks = tasks[:a.limit]
    direct = direct_map(a.direct)
    cache = StoreCache(Path(a.out) / 'stores')
    task_store = {json.loads(x)['task_id']: json.loads(x)['store_id'] for x in (Path(a.out) / 'task_stores.jsonl').read_text().splitlines()}
    spec = RetrievalSpec(**json.loads(a.retrieval))
    labels = a.models.split(',')
    arm_list = [x for x in ARMS.ARMS if x in a.arms.split(',')]
    count = SymmetricCounter(labels)
    natives = {x: count.toks[i] for i, x in enumerate(labels)}
    bindings = {x: M.bind_inventory(M.MODELS[x], a.inventory) for x in labels}
    qenc = QueryEncoder(a.encoder) if spec.backend in ('dense', 'hybrid') else None
    versions = dict(writer=WRITER_VERSION, reader=R.READER_VERSION, retrieval=spec.identity, prompt=ARMS.PROMPT_VERSION,
                    request=Q.REQUEST_VERSION, binding=M.BINDING_VERSION, render_note=ARMS.RENDER_NOTE,
                    evidence_budget=a.budget)
    rows, arm_traces = [], []
    for t in tasks:
        store = cache.get(task_store[t.task_id])
        d = direct.get(t.task_id)
        direct_ids = [s['source_id'] for s in d['spans']] if d and d['status'] == 'located_unique' else None
        index = OwnerIndex(store, spec, unit_vectors=load_vectors(a.out, store)) if spec else None
        qv = qenc(query_text(t)) if qenc else None
        packed = {}
        for arm in arm_list:
            try:
                packed[arm] = ARMS.select_units(arm, t, store, index=index, query_vector=qv, direct_ids=direct_ids,
                                                count_tokens=count, budget=a.budget)
            except ARMS.NotEvaluable as exc:
                packed[arm] = exc
        if 'C' in packed and 'D' in packed and not isinstance(packed['C'], Exception):
            assert [u.unit_id for u in packed['C'].units] == [u.unit_id for u in packed['D'].units]
        for label in labels:
            b = bindings[label]; decode = b.decode()
            for arm in arm_list:
                p = packed[arm]
                if isinstance(p, Exception):
                    rows.append(Q.not_evaluable(t, arm, b, str(p), versions)); continue
                msgs, trace = ARMS.build(arm, t, store, p)
                trace.update(store_id=store.store_id, arm_name=ARMS.ARM_NAMES[arm],
                             retrieval=spec.identity if arm == 'B' else None)
                ids = natives[label].chat_ids(msgs)
                rows.append(Q.make(t, arm, b, msgs, ids, decode, trace, M.capacity(ids, decode), versions))
    slots_sha = None
    if a.logical_slots:
        rows, slots_sha = bind_logical_slots(rows, tasks, direct, bindings, a.logical_slots)
    dedupe = Q.deduplicate(rows)
    out = Path(a.manifest_dir); out.mkdir(parents=True, exist_ok=True)
    order = {x: i for i, x in enumerate(labels)}
    # Model-major (one load each); tasks in a pre-declared seeded permutation so any budget-truncated
    # prefix is a random subsample of the frozen 240 (not the hard stratum last); arms within a task.
    if not slots_sha:
        rank = {t.task_id: hashlib.sha256(f'{a.order_seed}|{t.task_id}'.encode()).hexdigest() for t in tasks}
        rows.sort(key=lambda r: (order[r['model_label']], rank[r['task_id']], r['arm']))
    jsonl(out / 'requests.private.jsonl', rows)
    index_rows = [{k: r.get(k) for k in ('logical_id', 'task_id', 'task_mode', 'persona_group', 'arm', 'model_label',
                                          'request_sha256', 'status', 'duplicate_of', 'reason',
                                          'logical_request_sha256')} for r in rows]
    for r in index_rows:
        if r['duplicate_of'] is None:
            r.pop('duplicate_of')
        if r['reason'] is None:
            r.pop('reason')
        if r['logical_request_sha256'] is None:
            r.pop('logical_request_sha256')
    caps = default_caps(dedupe['physical_unique'])
    caps.update(input_cap=M.COMMON_INPUT_CAP, backend_cap=M.BACKEND_CONTEXT_CAP)
    manifest = dict(protocol=MANIFEST_PROTOCOL, authorized=False, research_qualified=False,
                    scope='NAA WP2 development: frozen val MCQ tasks x 4 arms x generators',
                    dataset_revision=tasks[0].dataset_revision, task_mode=a.mode, tasks=len(tasks),
                    runtime_tasks_sha256=file_sha(Path(a.runtime_root) / f'tasks.{a.mode}.jsonl'),
                    direct_sha256=file_sha(a.direct), model_order=labels,
                    bindings={x: asdict(bindings[x]) | {'g_id': bindings[x].g_id, 'decode': bindings[x].decode()} for x in labels},
                    checkpoints={x: checkpoint_headers(bindings[x]) for x in labels},
                    runtime=runtime_pins(), versions=versions, caps=caps, counts=dedupe,
                    logical_slots_sha256=slots_sha,
                    order_rule=('A frozen WP2 logical slot order (seeded task shuffle, shuffled arms per task, model-major)'
                                if slots_sha else f'model-major; sha256({a.order_seed}|task_id) permutation; arms A-D'),
                    requests_file='requests.private.jsonl', requests_sha256=file_sha(out / 'requests.private.jsonl'),
                    requests=index_rows)
    manifest['scope_sha256'] = digest({k: manifest[k] for k in ('requests_sha256', 'model_order', 'caps', 'versions')})
    jdump(out / 'MANIFEST.json', manifest)
    stats = materialize_stats(rows)
    stats.update(cpu_seconds=round(time.monotonic() - t0, 2), manifest_sha256=manifest_sha256(manifest),
                 status_by_model_arm=summarize(manifest), counts=dedupe)
    jdump(out / 'MATERIALIZE_SUMMARY.json', stats)
    print(json.dumps({k: stats[k] for k in ('counts', 'cpu_seconds', 'manifest_sha256')}, indent=2))


def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(round(q * (len(v) - 1))))] if v else None


def materialize_stats(rows):
    by = defaultdict(list)
    for r in rows:
        by[(r['model_label'], r['arm'])].append(r)
    out = {}
    for (m, arm), rs in sorted(by.items()):
        ready = [r for r in rs if r['status'] == 'ready']
        toks = [len(r['input_ids']) for r in rs if 'input_ids' in r]
        ev = [r['trace']['evidence_tokens'] for r in rs if 'trace' in r]
        nd = [len(r['trace']['delivered_ids']) for r in rs if 'trace' in r]
        out[f'{m}|{arm}'] = dict(logical=len(rs), ready=len(ready), status=dict(Counter(r['status'] for r in rs)),
                                 not_evaluable_reasons=dict(Counter(r.get('reason', '')[:60] for r in rs if r['status'] == 'not_evaluable')),
                                 input_tokens=dict(min=min(toks), median=pct(toks, .5), p95=pct(toks, .95), max=max(toks)) if toks else None,
                                 evidence_tokens=dict(median=pct(ev, .5), max=max(ev)) if ev else None,
                                 delivered_units=dict(median=pct(nd, .5), max=max(nd)) if nd else None)
    return dict(by_model_arm=out)


# ---------------------------------------------------------------- infer / export / aggregate
def load_full(manifest_dir):
    manifest = load_manifest(Path(manifest_dir) / 'MANIFEST.json')
    path = Path(manifest_dir) / manifest['requests_file']
    if file_sha(path) != manifest['requests_sha256']:
        raise SystemExit('request file differs from manifest')
    full = {json.loads(x)['logical_id']: json.loads(x) for x in path.read_text().splitlines() if x.strip()}
    rows = []
    for r in manifest['requests']:
        f = full[r['logical_id']]
        if f.get('request_sha256') != r['request_sha256'] or f['status'] != r['status']:
            raise SystemExit('manifest index differs from request file')
        rows.append({**f, **({'duplicate_of': r['duplicate_of']} if 'duplicate_of' in r else {})})
    return manifest, rows


def cmd_infer(a):
    from metacom_pm.need_aware.runtime import runner
    from metacom_pm.need_aware.runtime.backend import NAAHFBackend, PlumbingBackend
    manifest, rows = load_full(a.manifest_dir)
    msha = manifest_sha256(manifest)
    if a.plumbing:
        approval = dict(models=manifest['model_order'], max_physical_calls=manifest['caps']['max_physical_calls'],
                        max_gpu_seconds=manifest['caps']['max_gpu_seconds'], _sha256='plumbing-no-approval')
        ledger = Ledger(Path(a.run_root) / 'plumbing', manifest_sha256=msha)
        fails = set(a.inject_failure or [])
        factory = lambda label, **kw: PlumbingBackend(manifest['bindings'][label], fail_on=fails)
        summary = runner.run(dict(manifest, requests=rows), approval, ledger, factory, result_kind='plumbing',
                             only_models=a.models.split(',') if a.models else None)
        print(json.dumps(summary, indent=2)); return
    # Real model path: refuse before ANY device census, lock, byte read or worker spawn.
    approval = refuse_without(a.approval)
    authorize(manifest, approval, root=ROOT)
    approval['_sha256'] = digest(approval)
    from metacom_pm.rl1v3.generator import limited_run as L
    import fcntl
    run_root = Path(a.run_root).resolve()
    L.storage_guard(run_root)
    lock_path = L.DATA / 'tokkio_projects/pmrl1-validation/limited-g0e-exclusive.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        L.device_guard(initial=True)
        ledger = Ledger(run_root / 'model', manifest_sha256=msha)
        for label in approval['models']:
            t0 = time.monotonic()
            files = verify_model_bytes(manifest['bindings'][label], t0 + 1800)
            ledger.add('MODEL_BYTES_VERIFIED', model_label=label, files=files, cpu_seconds=time.monotonic() - t0)
        def factory(label, *, deadline, guard_bound_s):
            spec = manifest['bindings'][label]
            return NAAHFBackend(ROOT, spec, manifest, run_root / 'worker' / f'{label}-{int(time.time())}',
                                deadline, guard_bound_s=guard_bound_s)
        summary = runner.run(dict(manifest, requests=rows), approval, ledger, factory, result_kind='model',
                             guard=lambda: L.storage_guard(run_root))
    print(json.dumps(summary, indent=2))


def cmd_export(a):
    manifest, rows = load_full(a.manifest_dir)
    sub = 'plumbing' if a.plumbing else 'model'
    ledger = Ledger(Path(a.run_root) / sub, manifest_sha256=manifest_sha256(manifest))
    done = ledger.completed()
    failed = {e['request_sha256'] for e in ledger.events if e['event'] in ('ATTEMPT_FAILED', 'ATTEMPT_INVALID')}
    run_id = 'naarun:' + digest([e['event_sha256'] for e in ledger.events[:1]])
    by = defaultdict(list)
    for r in rows:
        e = done.get(r.get('request_sha256'))
        status = ('not_evaluable' if r['status'] == 'not_evaluable' else 'capacity_exceeded' if r['status'] != 'ready'
                  else 'completed' if e else 'failed' if r['request_sha256'] in failed else 'missing')
        by[(r['model_label'], r['arm'])].append(dict(
            task_id=r['task_id'], logical_id=r['logical_id'], arm=r['arm'], model_label=r['model_label'],
            model_id=r['model_id'], result_kind='plumbing' if a.plumbing else 'model', run_id=run_id,
            request_sha256=r.get('request_sha256'), status=status, output=e['text'] if e else '',
            reused_exact='duplicate_of' in r, finish_reason=e['finish_reason'] if e else None))
    out = Path(a.out)
    files = {}
    for (m, arm), preds in sorted(by.items()):
        p = out / f'predictions.{m}.{arm}.jsonl'; jsonl(p, preds)
        files[f'{m}|{arm}'] = dict(path=str(p), rows=len(preds), status=dict(Counter(x['status'] for x in preds)))
    jdump(out / 'EXPORT_SUMMARY.json', dict(result_kind='plumbing' if a.plumbing else 'model', run_id=run_id, files=files,
                                           scorer='A: project/scripts/need_aware/score_mcq.py (evaluation process only)'))
    print(json.dumps(files, indent=2))


def cmd_aggregate(a):
    manifest, rows = load_full(a.manifest_dir)
    sub = 'plumbing' if a.plumbing else 'model'
    ledger = Ledger(Path(a.run_root) / sub, manifest_sha256=manifest_sha256(manifest))
    ev = ledger.events
    res = [e for e in ev if e['event'] == 'ATTEMPT_RESULT']
    by = defaultdict(list)
    for e in res:
        by[(e['model_label'], e['arm'])].append(e)
    lat = {}
    for k, v in sorted(by.items()):
        g = [x['generation_ns'] / 1e9 for x in v if x.get('generation_ns') is not None]
        f = [x['first_token_latency_ns'] / 1e9 for x in v if x.get('first_token_latency_ns') is not None]
        lat[f'{k[0]}|{k[1]}'] = dict(n=len(v), output_tokens_median=pct([x['output_tokens'] for x in v], .5),
                                     generation_s_p50=pct(g, .5), generation_s_p95=pct(g, .95),
                                     first_token_s_p50=pct(f, .5) if f else 'unknown',
                                     first_token_s_p95=pct(f, .95) if f else 'unknown',
                                     length_stops=sum(x['finish_reason'] == 'length' for x in v))
    summary = dict(result_kind=sub, events=dict(Counter(e['event'] for e in ev)), physical_calls=ledger.physical_calls(),
                   gpu_seconds=ledger.gpu_seconds(), model_loads=dict(ledger.model_loads()),
                   completed_unique=len(ledger.completed()), latency=lat,
                   failures=[dict(event=e['event'], logical_id=e.get('logical_id'), error=e.get('error')) for e in ev
                             if e['event'] in ('ATTEMPT_FAILED', 'ATTEMPT_INVALID', 'LOAD_FAILED', 'STOP')])
    jdump(Path(a.run_root) / sub / 'AGGREGATE.json', summary)
    print(json.dumps({k: summary[k] for k in ('events', 'physical_calls', 'completed_unique', 'gpu_seconds')}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest='cmd', required=True)
    w = s.add_parser('write'); w.add_argument('--runtime-root', required=True); w.add_argument('--out', required=True)
    e = s.add_parser('embed'); e.add_argument('--out', required=True); e.add_argument('--encoder', default=BGE_PATH)
    e.add_argument('--threads', type=int, default=16)
    r = s.add_parser('retrieve')
    for x in ('--runtime-root', '--direct', '--out'):
        r.add_argument(x, required=True)
    r.add_argument('--encoder', default=BGE_PATH); r.add_argument('--budgets', default='1024,2048,4096,8192')
    r.add_argument('--models', default='G0e,Qwen35'); r.add_argument('--backends', default='bm25,dense,hybrid')
    r.add_argument('--tag', default='')
    m = s.add_parser('materialize')
    for x in ('--runtime-root', '--direct', '--out', '--manifest-dir', '--inventory'):
        m.add_argument(x, required=True)
    m.add_argument('--retrieval', required=True, help='RetrievalSpec JSON')
    m.add_argument('--budget', type=int, required=True); m.add_argument('--models', default='G0e,Qwen35')
    m.add_argument('--mode', default='mcq'); m.add_argument('--limit', type=int, default=0)
    m.add_argument('--encoder', default=BGE_PATH); m.add_argument('--order-seed', type=int, default=20261127)
    m.add_argument('--arms', default='A,B,C,D'); m.add_argument('--logical-slots')
    i = s.add_parser('infer'); i.add_argument('--manifest-dir', required=True); i.add_argument('--run-root', required=True)
    i.add_argument('--approval'); i.add_argument('--plumbing', action='store_true'); i.add_argument('--models')
    i.add_argument('--inject-failure', action='append')
    x = s.add_parser('export'); x.add_argument('--manifest-dir', required=True); x.add_argument('--run-root', required=True)
    x.add_argument('--out', required=True); x.add_argument('--plumbing', action='store_true')
    g = s.add_parser('aggregate'); g.add_argument('--manifest-dir', required=True); g.add_argument('--run-root', required=True)
    g.add_argument('--plumbing', action='store_true')
    a = p.parse_args()
    denied = [x for x in os.environ.get('NAA_DENY_PATHS', '').split(':') if x]
    if any(Path(x).exists() for x in denied):
        raise SystemExit('sandbox isolation failed: evaluation/source path visible')
    dict(write=cmd_write, embed=cmd_embed, retrieve=cmd_retrieve, materialize=cmd_materialize, infer=cmd_infer,
         export=cmd_export, aggregate=cmd_aggregate)[a.cmd](a)


if __name__ == '__main__':
    main()
