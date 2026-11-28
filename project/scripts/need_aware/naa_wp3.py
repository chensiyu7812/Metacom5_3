#!/usr/bin/env python3
"""NAA WP3 B-line CLI (CPU only): prepare-train -> supply -> materialize.

  prepare-train  legal stores + BGE unit vectors for a fixed, seeded training-side sample
                 (one located task per owner) -- for diagnostics only, never tuning.
  supply         E0 ranking per task: 256/32 token windows -> BGE top-128 -> Qwen3-Reranker-0.6B
                 top-15 (all 128 scores kept). Resumable, one JSON per task; writes SUPPLY_DONE.json.
  materialize    the seven WP3 arms (B0 B1 B1s E0 E0s C Cn) x generators with the modified
                 short-answer protocol; private requests + public-safe statistics (tokens, capacity,
                 reference coverage, complete groups, Cn flags, CPU cost). --selection-only skips
                 prompts (training-side generation tasks have no options).

Runtime inputs: A's runtime tasks/histories; A's Direct coordinates are used only for C/Cn and
coverage diagnostics. The evaluation sidecar is never opened. No model generation happens here.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naa_agent as NA  # noqa: E402  (shared CPU helpers; no model is loaded on import)

from metacom_pm.need_aware.agent import arms_wp3 as W3  # noqa: E402
from metacom_pm.need_aware.agent import evidence as EV  # noqa: E402
from metacom_pm.need_aware.agent.retrieval import (BGEEncoder, BGE_QUERY_PREFIX, EmbeddingCache,  # noqa: E402
                                                    OwnerIndex, RetrievalSpec, query_text)
from metacom_pm.need_aware.data.contracts import digest, load_runtime  # noqa: E402
from metacom_pm.need_aware.data.history import HistoryResolver  # noqa: E402
from metacom_pm.need_aware.memory import reader as R  # noqa: E402
from metacom_pm.need_aware.memory.writer import (MemoryWriter, StoreCache, WRITER_VERSION,  # noqa: E402
                                                 text_identity, write_for_task)
from metacom_pm.need_aware.runtime import models as M  # noqa: E402
from metacom_pm.need_aware.runtime import requests as Q  # noqa: E402

RERANKER_PATH = '/opt/tokkio-data0/tokkio_models/naa_wp3/Qwen3-Reranker-0.6B-e61197e'
TRAIN_SAMPLE_SEED = 'naa-wp3-train-diagnostic-v1'
B0_SPEC = RetrievalSpec(backend='dense', unit_filter='user_only')
B1_SPEC = RetrievalSpec(backend='dense', unit_filter='all')


def tasks_from(path):
    return load_runtime(Path(path))


def task_store_map(root):
    p = NA.store_map(root)
    return {json.loads(x)['task_id']: json.loads(x)['store_id'] for x in p.read_text().splitlines()}


def located(path, key):
    """task_id -> list of Direct unit ids (located_unique only)."""
    out = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get(key) == 'located_unique':
            out[r['task_id']] = [s['source_id'] for s in r.get('spans') or r.get('verified_spans')]
    return out


# ---------------------------------------------------------------- prepare-train
def cmd_prepare_train(a):
    t0 = time.monotonic()
    prov = located(a.provenance, 'direct_status')
    tasks = {t.task_id: t for t in tasks_from(Path(a.runtime_root) / 'tasks.jsonl')}
    per_owner = {}
    for tid in sorted(prov):
        t = tasks[tid]
        key = hashlib.sha256(f'{TRAIN_SAMPLE_SEED}|{tid}'.encode()).hexdigest()
        if t.persona_group not in per_owner or key < per_owner[t.persona_group][0]:
            per_owner[t.persona_group] = (key, tid)
    owners = sorted(per_owner.values())[:a.n]
    chosen = [tasks[tid] for _, tid in owners]
    cache = StoreCache(Path(a.out) / 'stores')
    resolver, writer = HistoryResolver(a.runtime_root), MemoryWriter()
    enc = BGEEncoder(NA.BGE_PATH, threads=a.threads)
    emb = EmbeddingCache(Path(a.out) / 'embeddings', RetrievalSpec().dense_model)
    rows = []
    for t in chosen:
        store = write_for_task(resolver, writer, t)
        cache.put(store)
        emb.get_or_build(store, store.units, enc)
        rows.append(dict(task_id=t.task_id, store_id=store.store_id))
    NA.jsonl(NA.store_map(a.out), rows)
    NA.jsonl(Path(a.out) / 'train_sample.jsonl', [dict(task_id=t.task_id, persona_group=t.persona_group) for t in chosen])
    s = dict(seed=TRAIN_SAMPLE_SEED, rule='one located_unique task per owner, smallest sha256(seed|task_id); first n owners',
             owners_available=len(per_owner), sampled=len(chosen), writer=WRITER_VERSION,
             cpu_seconds=round(time.monotonic() - t0, 1))
    NA.jdump(Path(a.out) / 'PREPARE_TRAIN_SUMMARY.json', s)
    print(json.dumps(s, indent=2))


# ---------------------------------------------------------------- supply (E0 ranking)
class WindowVectors:
    def __init__(self, root, tokenizer, encoder):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.tok, self.enc = tokenizer, encoder
        self.spec = EV.window_spec_identity(RetrievalSpec().dense_model)

    def get(self, store):
        import numpy as np
        wins = EV.windows(store.units, self.tok)
        key = hashlib.sha256((self.spec + '|' + text_identity(store)).encode()).hexdigest()[:24]
        p, meta = self.root / f'{key}.npy', self.root / f'{key}.json'
        ids = [w.window_id for w in wins]
        if p.exists() and json.loads(meta.read_text())['window_ids'] == ids:
            mat = np.load(p)
        else:
            mat = np.asarray(self.enc.encode([w.text for w in wins]), dtype='float32')
            np.save(p.with_suffix('.tmp.npy'), mat); Path(p.with_suffix('.tmp.npy')).replace(p)
            meta.write_text(json.dumps(dict(spec=self.spec, text_identity=text_identity(store), window_ids=ids)))
        return wins, {w.window_id: mat[i].tolist() for i, w in enumerate(wins)}


def cmd_supply(a):
    from transformers import AutoTokenizer
    root, out = Path(a.store_root), Path(a.out)
    (out / 'e0').mkdir(parents=True, exist_ok=True)
    tasks = {t.task_id: t for t in tasks_from(a.tasks)}
    ts = task_store_map(root)
    ids = [x for x in (Path(a.task_ids).read_text().split() if a.task_ids else sorted(tasks)) if x in ts]
    cache = StoreCache(root / 'stores')
    bge_tok = AutoTokenizer.from_pretrained(NA.BGE_PATH, local_files_only=True)
    enc = BGEEncoder(NA.BGE_PATH, threads=a.threads)
    wv = WindowVectors(out / 'window_vectors', bge_tok, enc)
    reranker = None
    done = 0
    for n, tid in enumerate(ids):
        dest = out / 'e0' / f'{tid}.json'
        if dest.exists():
            done += 1; continue
        reranker = reranker or EV.QwenReranker(a.reranker, threads=a.threads)
        t = tasks[tid]; store = cache.get(ts[tid]); q = query_text(t)
        c0 = time.monotonic()
        wins, vecs = wv.get(store)
        qv = enc.encode([BGE_QUERY_PREFIX + q])[0]
        cand = EV.dense_candidates(wins, vecs, qv)
        c1 = time.monotonic(); before = reranker.tokens_scored
        scores = reranker.score(q, [w.text for w in cand])
        c2 = time.monotonic()
        ranked = sorted(zip(scores, range(len(cand))), key=lambda x: (-x[0], cand[x[1]].lo, cand[x[1]].window_id))
        rec = dict(task_id=tid, store_id=store.store_id, supply=EV.SUPPLY_VERSION, window_spec=wv.spec,
                   reranker=EV.RERANKER_ID, instruction_sha256=hashlib.sha256(EV.RERANK_INSTRUCTION.encode()).hexdigest(),
                   windows_total=len(wins),
                   candidates=[dict(window_id=cand[i].window_id, lo=cand[i].lo, hi=cand[i].hi, dense_rank=i,
                                    rerank_score=round(s, 6)) for s, i in ranked],
                   cpu_seconds=dict(windows_dense=round(c1 - c0, 3), rerank=round(c2 - c1, 3)),
                   rerank_tokens=reranker.tokens_scored - before)
        tmp = dest.with_suffix('.tmp'); tmp.write_text(json.dumps(rec)); tmp.replace(dest)
        done += 1
        NA.jdump(out / 'SUPPLY_PROGRESS.json', dict(done=done, total=len(ids), last=tid, utc=time.time()))
    NA.jdump(out / 'SUPPLY_DONE.json', dict(done=done, total=len(ids), supply=EV.SUPPLY_VERSION,
                                            reranker=EV.RERANKER_ID, threads=a.threads))


def e0_ranked(out, tid):
    p = Path(out) / 'e0' / f'{tid}.json'
    if not p.exists():
        return None
    rec = json.loads(p.read_text())
    ws = [EV.Window(c['window_id'], c['lo'], c['hi'], '') for c in rec['candidates']]
    return ws[:EV.RERANK_KEEP], rec


# ---------------------------------------------------------------- materialize + statistics
def q(v, x):
    return NA.pct(v, x) if v else None


def cmd_materialize(a):
    t0 = time.monotonic()
    root = Path(a.store_root)
    tasks = [t for t in tasks_from(a.tasks)]
    ts = task_store_map(root)
    if a.task_ids:
        keep = set(Path(a.task_ids).read_text().split()); tasks = [t for t in tasks if t.task_id in keep]
    tasks = [t for t in tasks if t.task_id in ts]
    direct = located(a.direct, a.direct_key)
    cache = StoreCache(root / 'stores')
    arms = [x for x in W3.ARMS if x in a.arms.split(',')]
    labels = a.models.split(',')
    count = NA.SymmetricCounter(labels)
    natives = {x: count.toks[i] for i, x in enumerate(labels)}
    bindings = {x: M.bind_inventory(M.MODELS[x], a.inventory) for x in labels} if not a.selection_only else {}
    qenc = NA.QueryEncoder(NA.BGE_PATH)
    versions = dict(writer=WRITER_VERSION, reader=R.READER_VERSION, supply=EV.SUPPLY_VERSION, prompt=W3.PROMPT_VERSION,
                    protocol=W3.SHORT_PROTOCOL, protocol_note=W3.SHORT_NOTE, request=Q.REQUEST_VERSION,
                    binding=M.BINDING_VERSION, b0=B0_SPEC.identity, b1=B1_SPEC.identity, reranker=EV.RERANKER_ID)
    rows, sel = [], []
    for t in tasks:
        store = cache.get(ts[t.task_id])
        vec = NA.load_vectors(root, store)
        qv = qenc(query_text(t))
        idx_u, idx_a = OwnerIndex(store, B0_SPEC, unit_vectors=vec), OwnerIndex(store, B1_SPEC, unit_vectors=vec)
        e0 = e0_ranked(a.supply_out, t.task_id) if any(x.startswith('E0') for x in arms) else None
        for arm in arms:
            try:
                if arm.startswith('E0') and e0 is None:
                    raise W3.WP2.NotEvaluable('E0 supply not computed for this task')
                packed, extra = W3.select(arm, t, store, dense_user=idx_u, dense_all=idx_a, query_vector=qv,
                                          e0_ranked=e0[0] if e0 else None, direct_ids=direct.get(t.task_id),
                                          count_tokens=count)
            except W3.WP2.NotEvaluable as exc:
                sel.append(dict(task_id=t.task_id, arm=arm, status='not_evaluable', reason=str(exc)))
                for label in labels if not a.selection_only else ():
                    rows.append(Q.not_evaluable(t, arm, bindings[label], str(exc), versions))
                continue
            cov = EV.coverage(packed.units, direct.get(t.task_id), store)
            sel.append(dict(task_id=t.task_id, arm=arm, status='ready', evidence_tokens=packed.tokens,
                            units=len(packed.units), user_units=sum(u.is_current_user for u in packed.units),
                            coverage=cov, extra={k: v for k, v in extra.items() if k != 'reference_positions'},
                            reference_positions=extra.get('reference_positions'),
                            supply_cpu_s=(e0[1]['cpu_seconds'] if e0 and arm.startswith('E0') else None)))
            for label in labels if not a.selection_only else ():
                b = bindings[label]; decode = b.decode(W3.SHORT_MAX_NEW_TOKENS)
                msgs, trace = W3.build(arm, t, store, packed)
                trace.update(store_id=store.store_id, arm_name=W3.ARM_NAMES[arm], deployable=arm in W3.DEPLOYABLE)
                ids = natives[label].chat_ids(msgs)
                rows.append(Q.make(t, arm, b, msgs, ids, decode, trace, M.capacity(ids, decode), versions))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    NA.jsonl(out / 'selection.private.jsonl', sel)
    if rows:
        NA.jsonl(out / 'requests.private.jsonl', rows)
    stats = summarize(sel, rows, labels)
    stats.update(tasks=len(tasks), arms=arms, models=labels, versions=versions, selection_only=a.selection_only,
                 cpu_seconds=round(time.monotonic() - t0, 1), direct_key=a.direct_key,
                 counts=Q.deduplicate(rows) if rows else None)
    NA.jdump(out / 'WP3_STATS.json', stats)
    print(json.dumps({k: stats[k] for k in ('tasks', 'arms', 'cpu_seconds')}, indent=2))


def summarize(sel, rows, labels):
    by = defaultdict(list)
    for s in sel:
        by[s['arm']].append(s)
    arms = {}
    for arm, ss in by.items():
        ready = [s for s in ss if s['status'] == 'ready']
        cov = [s['coverage'] for s in ready if s['coverage']]
        ev = [s['evidence_tokens'] for s in ready]
        mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None
        arms[arm] = dict(
            tasks=len(ss), ready=len(ready),
            not_evaluable=dict(Counter(s['reason'][:70] for s in ss if s['status'] != 'ready')),
            evidence_tokens=dict(p50=q(ev, .5), p95=q(ev, .95), max=max(ev) if ev else None),
            delivered_units_p50=q([s['units'] for s in ready], .5),
            user_unit_share_mean=mean([s['user_units'] / s['units'] for s in ready if s['units']]),
            coverage_tasks=len(cov),
            reference_recall_mean=mean([c['recall'] for c in cov]),
            user_reference_recall_mean=mean([c['user_recall'] for c in cov if c['user_recall'] is not None]),
            nonuser_reference_recall_mean=mean([c['nonuser_recall'] for c in cov if c['nonuser_recall'] is not None]),
            complete_reference_group=sum(c['complete_group'] for c in cov),
            supply_cpu_s=dict(p50=q([s['supply_cpu_s']['rerank'] + s['supply_cpu_s']['windows_dense']
                                    for s in ready if s.get('supply_cpu_s')], .5)) if arm.startswith('E0') else None,
            background=(dict(units_p50=q([s['extra']['background_units'] for s in ready], .5),
                             forget_or_change_tasks=sum(s['extra']['background_forget_or_change'] > 0 for s in ready),
                             third_party_tasks=sum(s['extra']['background_third_party'] > 0 for s in ready),
                             reference_first_position_p50=q([s['reference_positions'][0] for s in ready
                                                             if s['reference_positions']], .5))
                        if arm == 'Cn' else None))
    req = {}
    for label in labels:
        for arm in by:
            rs = [r for r in rows if r['model_label'] == label and r['arm'] == arm]
            if not rs:
                continue
            toks = [len(r['input_ids']) for r in rs if 'input_ids' in r]
            req[f'{label}|{arm}'] = dict(logical=len(rs), status=dict(Counter(r['status'] for r in rs)),
                                         input_tokens=dict(p50=q(toks, .5), p95=q(toks, .95), max=max(toks) if toks else None,
                                                           total=sum(toks)))
    return dict(by_arm=arms, by_model_arm=req)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest='cmd', required=True)
    g = s.add_parser('prepare-train')
    for x in ('--runtime-root', '--provenance', '--out'):
        g.add_argument(x, required=True)
    g.add_argument('--n', type=int, default=120); g.add_argument('--threads', type=int, default=8)
    u = s.add_parser('supply')
    for x in ('--store-root', '--tasks', '--out'):
        u.add_argument(x, required=True)
    u.add_argument('--task-ids'); u.add_argument('--reranker', default=RERANKER_PATH); u.add_argument('--threads', type=int, default=16)
    m = s.add_parser('materialize')
    for x in ('--store-root', '--tasks', '--direct', '--out', '--supply-out'):
        m.add_argument(x, required=True)
    m.add_argument('--direct-key', default='status'); m.add_argument('--task-ids')
    m.add_argument('--arms', default=','.join(W3.ARMS)); m.add_argument('--models', default='Qwen35,G0e')
    m.add_argument('--inventory', default='/opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json')
    m.add_argument('--selection-only', action='store_true')
    a = p.parse_args()
    dict(**{'prepare-train': cmd_prepare_train}, supply=cmd_supply, materialize=cmd_materialize)[a.cmd](a)


if __name__ == '__main__':
    main()
