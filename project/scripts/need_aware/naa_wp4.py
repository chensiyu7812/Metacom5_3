#!/usr/bin/env python3
"""NAA WP4 open same-evidence requests (CPU): A's constructed 180 variants + natural 60 x U0/U1.

Constructed rows: A's pre-rendered runtime messages (runtime_sha256 = digest(runtime row)); U0 sends
them unchanged, U1 adds the Reglos-style rule layer (agent/behavior.u1_messages). Natural tasks: B's
frozen WP3 E0s delivery (same evidence for every U arm), A's single open JSON system prompt, no
compulsory recall suffix (modified open protocol, reported separately). U2/U3 later reuse these exact
inputs with an adapted generator. No model call here; the runner needs a bounded approval.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naa_agent as NA  # noqa: E402
import naa_wp3 as W3CLI  # noqa: E402

from metacom_pm.need_aware.agent import behavior as B  # noqa: E402
from metacom_pm.need_aware.agent import evidence as EV  # noqa: E402
from metacom_pm.need_aware.data.contracts import digest  # noqa: E402
from metacom_pm.need_aware.memory import reader as R  # noqa: E402
from metacom_pm.need_aware.memory.writer import StoreCache, WRITER_VERSION  # noqa: E402
from metacom_pm.need_aware.runtime import models as M  # noqa: E402
from metacom_pm.need_aware.runtime import requests as Q  # noqa: E402

OPEN_PROTOCOL = 'naa-wp4-open-v1'
OPEN_MAX_NEW_TOKENS = 384          # B proposal (A policy sets no cap); JSON {action, response}


def request(task_id, family, condition, binding, msgs, ids, decode, trace, versions, **extra):
    cap = M.capacity(ids, decode)
    return dict(logical_id=Q.logical_id(task_id, condition, binding.label), task_id=task_id, task_mode='open',
                persona_group=family, arm=condition, model_label=binding.label, model_id=binding.model_id,
                g_id=binding.g_id, decode=decode, messages=msgs, input_ids=ids, input_ids_sha256=digest(ids),
                capacity=cap, trace=trace, versions=versions, status='ready' if cap['fits'] else 'capacity_exceeded',
                request_sha256=Q.physical_identity(binding.g_id, msgs, ids, decode), **extra)


def cmd_manifest(a):
    from metacom_pm.need_aware.runtime.authorization import MANIFEST_PROTOCOL, manifest_sha256
    from metacom_pm.need_aware.runtime.budget import default_caps
    t0 = time.monotonic()
    b = M.bind_inventory(M.MODELS['Qwen35'], a.inventory)
    native = M.NativeTokenizer(b)
    decode = b.decode(OPEN_MAX_NEW_TOKENS)
    count = NA.SymmetricCounter(['Qwen35', 'G0e'])
    versions = dict(behavior=B.BEHAVIOR_VERSION, protocol=OPEN_PROTOCOL, writer=WRITER_VERSION, reader=R.READER_VERSION,
                    supply=EV.SUPPLY_VERSION, request=Q.REQUEST_VERSION, binding=M.BINDING_VERSION)
    constructed = [json.loads(l) for l in open(a.constructed)]
    systems = {r['messages'][0]['content'] for r in constructed}
    if len(systems) != 1:
        raise SystemExit('constructed rows must share one open system prompt')
    open_system = systems.pop()
    rows = []
    for r in constructed:
        rsha = digest(r)
        for cond in ('U0', 'U1'):
            msgs, tr = (r['messages'], dict(condition='U0')) if cond == 'U0' else B.u1_messages(r['messages'])
            tr.update(kind='constructed', generator_id=B.BASE_GENERATOR)
            rows.append(request(r['task_id'], r['source_family'], cond, b, msgs, native.chat_ids(msgs), decode, tr,
                                versions, runtime_sha256=rsha, kind='constructed', scoring_protocol=OPEN_PROTOCOL))
    nat = json.loads(Path(a.natural).read_text())
    if NA.file_sha(nat['runtime']) != nat['runtime_sha256']:
        raise SystemExit('natural runtime changed')
    tasks = W3CLI.tasks_from(nat['runtime'])
    ts = W3CLI.task_store_map(a.store_root)
    cache = StoreCache(Path(a.store_root) / 'stores')
    for t in tasks:
        store = cache.get(ts[t.task_id])
        e0 = W3CLI.e0_ranked(a.supply_out, t.task_id)
        if e0 is None:
            raise SystemExit('E0 supply missing for natural task ' + t.task_id)
        packed, _ = EV.pack_windows(e0[0], store, count, EV.COMPACT_BUDGET)
        for cond in ('U0', 'U1'):
            msgs = B.natural_messages(cond, t, store, packed, open_system)
            tr = dict(condition=cond, kind='natural', evidence='E0s@1536', delivered_ids=[u.unit_id for u in packed.units],
                      evidence_tokens=packed.tokens, recall_suffix=False, generator_id=B.BASE_GENERATOR)
            rows.append(request(t.task_id, t.persona_group, cond, b, msgs, native.chat_ids(msgs), decode, tr, versions,
                                task_sha256=digest(t.to_dict()), kind='natural', scoring_protocol=OPEN_PROTOCOL))
    dedupe = Q.deduplicate(rows)
    out = Path(a.manifest_dir); out.mkdir(parents=True, exist_ok=False)
    NA.jsonl(out / 'requests.private.jsonl', rows)
    caps = default_caps(dedupe['physical_unique'], gpu_seconds=a.gpu_seconds, max_physical_calls=a.max_physical_calls,
                        per_model_gpu_seconds=a.gpu_seconds)
    caps.update(input_cap=M.COMMON_INPUT_CAP, backend_cap=M.BACKEND_CONTEXT_CAP, max_model_loads_per_model=2,
                teardown_seconds=10)
    manifest = dict(protocol=MANIFEST_PROTOCOL, authorized=False, research_qualified=False,
                    scope='NAA WP4 open same-evidence development baseline U0/U1 (base Qwen35)',
                    constructed_sha256=NA.file_sha(a.constructed), natural=nat, model_order=['Qwen35'],
                    bindings={'Qwen35': {**b.__dict__, 'g_id': b.g_id, 'decode': decode}},
                    checkpoints={'Qwen35': NA.checkpoint_headers(b)}, runtime=NA.runtime_pins(), versions=versions,
                    caps=caps, counts=dedupe, requests_file='requests.private.jsonl',
                    requests_sha256=NA.file_sha(out / 'requests.private.jsonl'),
                    requests=[{k: r.get(k) for k in ('logical_id', 'task_id', 'task_mode', 'persona_group', 'arm',
                                                     'model_label', 'request_sha256', 'status')} for r in rows])
    manifest['scope_sha256'] = digest({k: manifest[k] for k in ('requests_sha256', 'model_order', 'caps', 'versions')})
    NA.jdump(out / 'MANIFEST.json', manifest)
    toks = [len(r['input_ids']) for r in rows]
    stats = dict(manifest_sha256=manifest_sha256(manifest), counts=dedupe, cpu_seconds=round(time.monotonic() - t0, 1),
                 status={f'{k}|{arm}|{st}': n for (k, arm, st), n in
                         Counter((r['kind'], r['arm'], r['status']) for r in rows).items()},
                 u1_silence={k: sum(1 for r in rows if r['arm'] == 'U1' and r['kind'] == k and r['trace'].get('silence'))
                             for k in ('constructed', 'natural')},
                 input_tokens=dict(p50=NA.pct(toks, .5), p95=NA.pct(toks, .95), max=max(toks), total=sum(toks)), caps=caps)
    NA.jdump(out / 'MATERIALIZE_SUMMARY.json', stats)
    print(json.dumps({k: stats[k] for k in ('manifest_sha256', 'counts', 'u1_silence', 'input_tokens')}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest='cmd', required=True)
    m = s.add_parser('manifest')
    for x in ('--constructed', '--natural', '--store-root', '--supply-out', '--manifest-dir'):
        m.add_argument(x, required=True)
    m.add_argument('--gpu-seconds', type=int, required=True); m.add_argument('--max-physical-calls', type=int, required=True)
    m.add_argument('--inventory', default='/opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json')
    a = p.parse_args()
    dict(manifest=cmd_manifest)[a.cmd](a)


if __name__ == '__main__':
    main()
