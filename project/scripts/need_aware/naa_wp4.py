#!/usr/bin/env python3
"""NAA WP4 request manifests and evaluation interfaces (CPU only; no model call here).

  manifest-w40      REVISED W4-0 (2026-11-28): A's frozen development MCQ tasks (<=280) x U0/U1/U1+/NoMem/OptOnly
                    on base Qwen3.5-9B, naa-short-mcq-v1 (64 tokens), one fixed WP3 evidence arm for every
                    same-evidence condition (delivered ids checked equal across U0/U1/U1+).
  manifest-adapted  W4-E: the W4-0 inputs byte-for-byte with the U2/U3 adapted generators (U0 input -> U2/U3,
                    plus NoMem/OptOnly diagnostics); adapted g_id from the full adapter identity, strict checks.
  export-open       natural open-task evaluation interface: blinded rating packets + separate unblinding key.
                    Natural tasks are judged on the reply itself (A's rubric), never by constructed-task action labels.
  manifest          (superseded W4-0 plan) A's constructed 180 variants + natural 60 x U0/U1.

Constructed rows: A's pre-rendered runtime messages (runtime_sha256 = digest(runtime row)); U0 sends
them unchanged, U1 adds the Reglos-style rule layer (agent/behavior.u1_messages). Natural tasks: B's
frozen WP3 E0s delivery (same evidence for every U arm), A's single open JSON system prompt, no
compulsory recall suffix (modified open protocol, reported separately). U2/U3 later reuse these exact
inputs with an adapted generator. No model call here; the runner needs a bounded approval.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naa_agent as NA  # noqa: E402
import naa_wp3 as W3CLI  # noqa: E402

from metacom_pm.need_aware.agent import behavior as B  # noqa: E402
from metacom_pm.need_aware.agent import arms_wp3 as W3  # noqa: E402
from metacom_pm.need_aware.agent import evidence as EV  # noqa: E402
from metacom_pm.need_aware.agent.retrieval import OwnerIndex, query_text  # noqa: E402
from metacom_pm.need_aware.data import short_protocol as SP  # noqa: E402
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


# ---------------------------------------------------------------- revised W4-0 (MCQ, 5 conditions)
W40_PROTOCOL = 'naa-wp4-w40-v1'
W40_MAX_TASKS = 280


def frozen_tasks(path, ids_path, limit):
    tasks = W3CLI.tasks_from(path)
    if ids_path:
        ids = json.loads(Path(ids_path).read_text())
        by = {t.task_id: t for t in tasks}
        if len(set(ids)) != len(ids) or any(i not in by for i in ids):
            raise SystemExit('frozen task list must be unique and inside the runtime file')
        tasks = [by[i] for i in ids]
    if len(tasks) > limit:
        raise SystemExit(f'{len(tasks)} tasks > {limit}: freeze a reasonable subset with A (--task-ids); never widen')
    if any(t.task_mode != 'mcq' or [o['id'] for o in t.options] != list('ABCD') for t in tasks):
        raise SystemExit('W4-0 uses the four-option short-answer protocol only')
    return tasks


def _write_manifest(out, rows, manifest, caps):
    NA.jsonl(out / 'requests.private.jsonl', rows)
    manifest.update(caps=caps, requests_file='requests.private.jsonl', requests_sha256=NA.file_sha(out / 'requests.private.jsonl'),
                    requests=[{k: r.get(k) for k in ('logical_id', 'task_id', 'task_mode', 'persona_group', 'arm',
                                                     'model_label', 'request_sha256', 'status', 'reason')
                               if r.get(k) is not None or k == 'request_sha256'} for r in rows])
    manifest['scope_sha256'] = digest({k: manifest[k] for k in ('requests_sha256', 'model_order', 'caps', 'versions')})
    NA.jdump(out / 'MANIFEST.json', manifest)


def cmd_manifest_w40(a):
    from metacom_pm.need_aware.runtime.authorization import MANIFEST_PROTOCOL, manifest_sha256
    from metacom_pm.need_aware.runtime.budget import default_caps
    t0 = time.monotonic()
    if a.evidence_arm not in W3.DEPLOYABLE:
        raise SystemExit('the fixed W4 evidence must be one deployable WP3 arm')
    tasks = frozen_tasks(a.tasks, a.task_ids, a.max_tasks)
    b = M.bind_inventory(M.MODELS['Qwen35'], a.inventory)
    native = M.NativeTokenizer(b)
    decode = b.decode(SP.MAX_NEW_TOKENS)
    count = NA.SymmetricCounter(['Qwen35', 'G0e'])             # the WP3 budget counter (same deliveries as W3)
    qenc = NA.QueryEncoder(NA.BGE_PATH)
    ts = W3CLI.task_store_map(a.store_root)
    cache = StoreCache(Path(a.store_root) / 'stores')
    versions = dict(behavior=B.BEHAVIOR_VERSION, protocol=SP.PROTOCOL, w40=W40_PROTOCOL, writer=WRITER_VERSION,
                    reader=R.READER_VERSION, supply=EV.SUPPLY_VERSION, prompt=W3.PROMPT_VERSION, request=Q.REQUEST_VERSION,
                    binding=M.BINDING_VERSION, evidence_arm=a.evidence_arm)
    rows, same = [], 0
    for t in tasks:
        store = cache.get(ts[t.task_id])
        vec = NA.load_vectors(a.store_root, store)
        qv = qenc(query_text(t))
        e0 = W3CLI.e0_ranked(a.supply_out, t.task_id) if a.evidence_arm.startswith('E0') else None
        if a.evidence_arm.startswith('E0') and e0 is None:
            raise SystemExit('E0 supply missing for ' + t.task_id)
        packed, _ = W3.select(a.evidence_arm, t, store, dense_user=OwnerIndex(store, W3CLI.B0_SPEC, unit_vectors=vec),
                              dense_all=OwnerIndex(store, W3CLI.B1_SPEC, unit_vectors=vec), query_vector=qv,
                              e0_ranked=e0[0] if e0 else None, count_tokens=count)
        delivered = {}
        for cond in B.W40_CONDITIONS:
            msgs, tr = B.mcq_messages(cond, t, store, packed)
            tr.update(store_id=store.store_id, evidence_arm=a.evidence_arm if cond in B.SAME_EVIDENCE else None)
            ids = native.chat_ids(msgs)
            row = Q.make(t, cond, b, msgs, ids, decode, tr, M.capacity(ids, decode), versions)
            row.update(scoring_protocol=SP.PROTOCOL, task_sha256=digest(t.to_dict()))
            rows.append(row)
            if cond in B.SAME_EVIDENCE:
                delivered[cond] = tr['delivered_ids']
        if len({tuple(v) for v in delivered.values()}) != 1:
            raise SystemExit('same-evidence violated for ' + t.task_id)
        same += 1
    dedupe = Q.deduplicate(rows)
    out = Path(a.manifest_dir); out.mkdir(parents=True, exist_ok=False)
    caps = default_caps(dedupe['physical_unique'], gpu_seconds=a.gpu_seconds, max_physical_calls=a.max_physical_calls,
                        per_model_gpu_seconds=a.gpu_seconds)
    caps.update(input_cap=M.COMMON_INPUT_CAP, backend_cap=M.BACKEND_CONTEXT_CAP, max_model_loads_per_model=2,
                teardown_seconds=10)
    manifest = dict(protocol=MANIFEST_PROTOCOL, authorized=False, research_qualified=False,
                    scope='NAA revised W4-0: base Qwen35 x U0/U1/U1+/NoMem/OptOnly, fixed evidence ' + a.evidence_arm,
                    tasks_sha256=NA.file_sha(a.tasks), task_ids_sha256=NA.file_sha(a.task_ids) if a.task_ids else None,
                    model_order=['Qwen35'], bindings={'Qwen35': {**b.__dict__, 'g_id': b.g_id, 'decode': decode}},
                    checkpoints={'Qwen35': NA.checkpoint_headers(b)}, runtime=NA.runtime_pins(), versions=versions,
                    counts=dedupe, order_rule='frozen task order, conditions U0,U1,U1+,NoMem,OptOnly within a task')
    _write_manifest(out, rows, manifest, caps)
    toks = defaultdict(list)
    for r in rows:
        toks[r['arm']].append(len(r['input_ids']))
    ready = sum(r['status'] == 'ready' for r in rows)
    stats = dict(manifest_sha256=manifest_sha256(manifest), tasks=len(tasks), same_evidence_tasks=same, counts=dedupe,
                 status=dict(Counter(f"{r['arm']}|{r['status']}" for r in rows)),
                 input_tokens={k: dict(p50=NA.pct(v, .5), p95=NA.pct(v, .95), max=max(v), total=sum(v)) for k, v in toks.items()},
                 worst_case_gpu_s=round(sum(len(r['input_ids']) for r in rows if r['status'] == 'ready') / 5298
                                        + ready * SP.MAX_NEW_TOKENS / 21.17 + 2 * 38 + 10),
                 caps=caps, cpu_seconds=round(time.monotonic() - t0, 1))
    NA.jdump(out / 'MATERIALIZE_SUMMARY.json', stats)
    print(json.dumps({k: stats[k] for k in ('manifest_sha256', 'tasks', 'counts', 'worst_case_gpu_s')}, indent=2))


# ---------------------------------------------------------------- W4-E: adapted generators on the W4-0 inputs
ADAPTED_INPUTS = {'U0': '', 'NoMem': ':NoMem', 'OptOnly': ':OptOnly'}


def cmd_manifest_adapted(a):
    from metacom_pm.need_aware.runtime.authorization import MANIFEST_PROTOCOL, manifest_sha256
    from metacom_pm.need_aware.runtime.budget import default_caps
    base, rows = NA.load_full(a.base_manifest_dir)
    if base['model_order'] != ['Qwen35']:
        raise SystemExit('W4-E reuses a base-Qwen35 W4-0 manifest')
    spec = M.bind_inventory(M.MODELS['Qwen35'], a.inventory)
    decode = base['bindings']['Qwen35']['decode']
    if spec.g_id != base['bindings']['Qwen35']['g_id'] or spec.decode(decode['max_new_tokens']) != decode:
        raise SystemExit('base binding changed since W4-0')
    idents = [json.loads(Path(p).read_text()) for p in a.adapter_identity]
    if sorted(i['method'] for i in idents) != ['U2', 'U3']:
        raise SystemExit('exactly one U2 and one U3 adapter')
    for k in ('init_adapter_sha256', 'train_data_sha256', 'base_g_id', 'trainer_version'):
        if len({i[k] for i in idents}) != 1:
            raise SystemExit('U2/U3 differ in ' + k + ' (same init, data, base and trainer required)')
    bindings, checkpoints, out_rows = {}, {}, []
    for i in idents:
        if NA.file_sha(Path(i['adapter_path']) / 'adapter.safetensors') != i['adapter_sha256']:
            raise SystemExit('adapter bytes differ from identity ' + i['method'])
        rec = Path(i['adapter_path']).parent / 'TRAIN_RECEIPT.json'
        if NA.file_sha(rec) != i['train_receipt_sha256']:
            raise SystemExit('training receipt differs from identity ' + i['method'])
        bnd = M.adapted_binding(spec, i, decode)
        lab = bnd['label']
        bindings[lab] = bnd
        checkpoints[lab] = dict(base['checkpoints']['Qwen35'], adapter=dict(path=i['adapter_path'], sha256=i['adapter_sha256']))
        for r in rows:
            if r['arm'] not in ADAPTED_INPUTS or r['status'] != 'ready':
                continue
            arm = i['method'] + ADAPTED_INPUTS[r['arm']]
            n = dict(r, arm=arm, model_label=lab, g_id=bnd['g_id'], logical_id=Q.logical_id(r['task_id'], arm, lab),
                     request_sha256=Q.physical_identity(bnd['g_id'], r['messages'], r['input_ids'], decode),
                     input_from=r['request_sha256'], trace=dict(r['trace'], generator_id=bnd['g_id'], condition=arm))
            n.pop('duplicate_of', None)
            out_rows.append(n)
    shas = [r['request_sha256'] for r in out_rows]
    if len(set(shas)) != len(shas) or set(shas) & {r['request_sha256'] for r in rows}:
        raise SystemExit('adapted requests collide with each other or with base requests')
    dedupe = Q.deduplicate(out_rows)
    out = Path(a.manifest_dir); out.mkdir(parents=True, exist_ok=False)
    caps = default_caps(dedupe['physical_unique'], gpu_seconds=a.gpu_seconds, max_physical_calls=a.max_physical_calls,
                        per_model_gpu_seconds=a.gpu_seconds)
    caps.update(input_cap=M.COMMON_INPUT_CAP, backend_cap=M.BACKEND_CONTEXT_CAP, max_model_loads_per_model=2,
                teardown_seconds=10)
    versions = dict(base['versions'], adapted_binding=M.ADAPTED_BINDING_VERSION)
    manifest = dict(protocol=MANIFEST_PROTOCOL, authorized=False, research_qualified=False,
                    scope='NAA W4-E: U2/U3 adapted Qwen35 on the byte-identical W4-0 inputs (+NoMem/OptOnly)',
                    base_manifest_sha256=manifest_sha256(base), model_order=sorted(bindings), bindings=bindings,
                    checkpoints=checkpoints, runtime=base['runtime'], versions=versions, counts=dedupe,
                    adapter_identities={i['method']: i for i in idents})
    _write_manifest(out, out_rows, manifest, caps)
    print(json.dumps(dict(manifest_sha256=manifest_sha256(manifest), counts=dedupe, labels=sorted(bindings)), indent=2))


# ---------------------------------------------------------------- natural open-task evaluation interface
def parse_open(text):
    """A's open contract is JSON {action, response}; the reply text is what raters judge."""
    t = text.strip()
    if t.startswith('```'):
        t = t.strip('`').split('\n', 1)[-1]
    try:
        d = json.loads(t[t.index('{'):t.rindex('}') + 1])
        return dict(parse_ok=isinstance(d.get('response'), str), action=d.get('action'), reply=d.get('response') or '')
    except (ValueError, AttributeError):
        return dict(parse_ok=False, action=None, reply=text)


def cmd_export_open(a):
    from metacom_pm.need_aware.runtime.authorization import manifest_sha256
    from metacom_pm.need_aware.runtime.ledger import Ledger
    manifest, rows = NA.load_full(a.manifest_dir)
    sub = 'plumbing' if a.plumbing else 'model'
    done = Ledger(Path(a.run_root) / sub, manifest_sha256=manifest_sha256(manifest)).completed()
    nat = [r for r in rows if r.get('kind', 'natural') == 'natural' and r['status'] == 'ready']
    packets, key, fmt = [], [], Counter()
    for r in nat:
        e = done.get(r['request_sha256'])
        if not e:
            continue
        p = parse_open(e['text'])
        fmt[(r['arm'], p['parse_ok'])] += 1
        item = 'item:' + digest(dict(seed=a.seed, sha=r['request_sha256']))[:20]
        evidence = next((m['content'] for m in r['messages'][1:-1] if m['role'] == 'user'), '')
        packets.append(dict(item_id=item, task_id=r['task_id'], request=r['messages'][-1]['content'],
                            evidence_shown_to_rater=evidence if r['arm'] == 'U0' else None, reply=p['reply']))
        key.append(dict(item_id=item, logical_id=r['logical_id'], condition=r['arm'], model_label=r['model_label'],
                        request_sha256=r['request_sha256'], parse_ok=p['parse_ok'], action=p['action'],
                        result_kind=sub))
    # evidence is identical for all same-evidence conditions of a task: show the U0 rendering to every item
    ev = {x['task_id']: x['evidence_shown_to_rater'] for x in packets if x['evidence_shown_to_rater'] is not None}
    for x in packets:
        x['evidence_shown_to_rater'] = ev.get(x['task_id'])
    packets.sort(key=lambda x: digest(dict(seed=a.seed, item=x['item_id'])))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    NA.jsonl(out / 'PACKETS.private.jsonl', packets)
    NA.jsonl(out / 'KEY.private.jsonl', key)
    NA.jdump(out / 'EXPORT_SUMMARY.json', dict(
        result_kind=sub, items=len(packets), manifest_sha256=manifest_sha256(manifest),
        format={f'{k}|parse_ok={v}': n for (k, v), n in sorted(fmt.items())},
        rule='natural open tasks: raters see request + legal evidence + reply only; conditions blinded and shuffled; '
             'the constructed-task action label is NOT a natural-task score (format/technical statistic only)',
        rubric_owner='A (score_wp4_open.py rubric); two independent blind raters before any semantic claim'))
    print(len(packets), dict(fmt))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest='cmd', required=True)
    m = s.add_parser('manifest')
    for x in ('--constructed', '--natural', '--store-root', '--supply-out', '--manifest-dir'):
        m.add_argument(x, required=True)
    m.add_argument('--gpu-seconds', type=int, required=True); m.add_argument('--max-physical-calls', type=int, required=True)
    m.add_argument('--inventory', default='/opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json')
    w = s.add_parser('manifest-w40')
    for x in ('--tasks', '--store-root', '--manifest-dir', '--evidence-arm'):
        w.add_argument(x, required=True)
    w.add_argument('--task-ids'); w.add_argument('--supply-out'); w.add_argument('--max-tasks', type=int, default=W40_MAX_TASKS)
    w.add_argument('--gpu-seconds', type=int, default=10000); w.add_argument('--max-physical-calls', type=int, default=1500)
    w.add_argument('--inventory', default='/opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json')
    d = s.add_parser('manifest-adapted')
    d.add_argument('--base-manifest-dir', required=True); d.add_argument('--adapter-identity', action='append', required=True)
    d.add_argument('--manifest-dir', required=True); d.add_argument('--gpu-seconds', type=int, required=True)
    d.add_argument('--max-physical-calls', type=int, required=True)
    d.add_argument('--inventory', default='/opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json')
    o = s.add_parser('export-open')
    for x in ('--manifest-dir', '--run-root', '--out'):
        o.add_argument(x, required=True)
    o.add_argument('--plumbing', action='store_true'); o.add_argument('--seed', default='naa-wp4-open-blind-v1')
    a = p.parse_args()
    dict(manifest=cmd_manifest, **{'manifest-w40': cmd_manifest_w40, 'manifest-adapted': cmd_manifest_adapted,
                                   'export-open': cmd_export_open})[a.cmd](a)


if __name__ == '__main__':
    main()
