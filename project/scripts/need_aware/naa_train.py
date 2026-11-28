#!/usr/bin/env python3
"""NAA WP4 training-backend CLI (B line). CPU commands run now; `train` needs a bounded approval.

  inspect     real architecture on the meta device (no weights): LoRA target names/parameter
              counts per suffix set; real native chat-template prompt/target boundary check.
  check-data  validate A's training JSONL (contract + leakage) and encode with the native
              tokenizer; --plumbing-from builds clearly labelled PLUMBING rows from real
              training-side inputs (real token lengths, placeholder targets, never trainable).
  estimate    steps / tokens / seconds / memory planning from measured WP2 prefill rates.
  train       refuses without a `naa-wp4-train-approval-v1` file bound to data, config, model,
              clean HEAD and caps -- before any device access.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naa_agent as NA  # noqa: E402

from metacom_pm.need_aware.agent import arms as WP2  # noqa: E402
from metacom_pm.need_aware.agent import behavior as B  # noqa: E402
from metacom_pm.need_aware.data.contracts import RuntimeTask, digest  # noqa: E402
from metacom_pm.need_aware.memory import reader as R  # noqa: E402
from metacom_pm.need_aware.memory.writer import StoreCache  # noqa: E402
from metacom_pm.need_aware.runtime import lora as LORA  # noqa: E402
from metacom_pm.need_aware.runtime import models as M  # noqa: E402
from metacom_pm.need_aware.runtime import training as T  # noqa: E402

SUFFIX_SETS = {'attn_qv': ('q_proj', 'v_proj'), 'attn_qkvo': ('q_proj', 'k_proj', 'v_proj', 'o_proj'),
               'attn_mlp': ('q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj')}
APPROVAL_PROTOCOL = 'naa-wp4-train-approval-v1'
WP2_LEDGER = '/opt/tokkio-data0/naa/20261127/agent_b/runs/wp2-exec-v2-model/model/LEDGER.001.jsonl'


def measured_prefill():
    """Real WP2 worker observations: input tokens / internal first-token latency (prefill-dominated)."""
    out = {}
    for line in open(WP2_LEDGER):
        e = json.loads(line)
        if e.get('event') == 'ATTEMPT_RESULT' and e.get('first_token_latency_ns') and e['input_tokens'] > 6000:
            out.setdefault(e['model_label'], []).append(e['input_tokens'] / (e['first_token_latency_ns'] / 1e9))
    return {m: round(sorted(v)[len(v) // 2]) for m, v in out.items()}


def cmd_inspect(a):
    import torch
    from transformers import AutoConfig, AutoModelForMultimodalLM, AutoTokenizer
    spec = M.MODELS[a.model]
    path = M.bind_inventory(spec, a.inventory).path
    cfg = AutoConfig.from_pretrained(path, local_files_only=True)
    with torch.device('meta'):
        model = AutoModelForMultimodalLM.from_config(cfg)
    base = sum(p.numel() for p in model.parameters())
    sets = {}
    for name, suf in SUFFIX_SETS.items():
        names = LORA.target_names(model, suf)
        per_r = sum(model.get_submodule(n).in_features + model.get_submodule(n).out_features for n in names)
        sets[name] = dict(modules=len(names), params_at_r16=per_r * 16, examples=names[:2])
    native = M.NativeTokenizer(M.bind_inventory(spec, a.inventory))
    msgs = [dict(role='system', content='You are a helpful assistant.'),
            dict(role='user', content='Records: (message 3; said by: the user) I love ramen.\n\nCurrent request: dinner idea?')]
    enc = T.native_encoder(native, T.TURN_END[a.model], M.COMMON_INPUT_CAP)(msgs, 'How about a ramen place with extra garlic?')
    names = native.check_special()
    names[T.TURN_END[a.model]] = native.tok.convert_ids_to_tokens(T.TURN_END[a.model])
    rep = dict(model=a.model, path=path, architecture=type(model).__name__, base_parameters=base, lora=sets,
               template_check=dict(prompt_tokens=enc.prompt_tokens, target_tokens=enc.target_tokens,
                                   trailing_template_tokens_removed=enc.trailing_template_tokens_removed,
                                   target_ends_with=enc.input_ids[-1], prompt_equals_inference_chat_ids=True,
                                   special_names=names),
               measured_wp2_prefill_tok_s=measured_prefill().get(a.model))
    NA.jdump(Path(a.out) / f'INSPECT.{a.model}.json', rep)
    print(json.dumps({k: rep[k] for k in ('architecture', 'base_parameters', 'template_check',
                                          'measured_wp2_prefill_tok_s')}, indent=2))
    print(json.dumps({k: {x: v[x] for x in ('modules', 'params_at_r16')} for k, v in rep['lora'].items()}))


def plumbing_rows(root, tasks_path, provenance, limit):
    """Real training-side inputs (legal store + verified Direct units) with PLUMBING targets."""
    tasks = {json.loads(l)['task_id']: json.loads(l) for l in open(tasks_path)}
    prov = {json.loads(l)['task_id']: json.loads(l) for l in open(provenance)}
    sample = [json.loads(l)['task_id'] for l in open(Path(root) / 'train_sample.jsonl')][:limit]
    rows = []
    for i, tid in enumerate(sample):
        t = tasks[tid]
        ev = [s['source_id'] for s in prov[tid]['verified_spans']]
        for v, beh in (('self', 'USE'), ('other', 'IGNORE')):
            rows.append(dict(example_id=f'plumb:{tid}:{v}', group_id=f'plumb:{tid}', owner_id=t['persona_group'],
                             split='fit', origin='constructed', behavior=beh, task=t, evidence_ids=ev,
                             target=f'PLUMBING TARGET {v} -- not supervision.',
                             contrast=dict(opposite_example_id=f"plumb:{tid}:{'other' if v == 'self' else 'self'}",
                                           unique_opposite=True), provenance=dict(plumbing=True)))
    return rows


def messages_factory(store_root, budget, count):
    cache = StoreCache(Path(store_root) / 'stores')
    ts = {json.loads(x)['task_id']: json.loads(x)['store_id'] for x in NA.store_map(store_root).read_text().splitlines()}

    def messages_of(r):
        task = RuntimeTask(**r['task'])
        store = cache.get(ts[task.task_id])
        by = store.by_id()
        packed = R.pack(sorted((by[x] for x in r['evidence_ids'] if x in by), key=lambda u: u.order), count, budget)
        return B.build('U0', task, store, packed)[0]          # identical renderer to U0/U2/U3 evaluation
    return messages_of


def cmd_check_data(a):
    from transformers import AutoTokenizer
    t0 = time.monotonic()
    if a.plumbing_from:
        rows = plumbing_rows(a.plumbing_from, a.tasks, a.provenance, a.limit)
    else:
        rows = [json.loads(l) for l in open(a.train) if l.strip()]
    forbidden = set(Path(a.forbidden_owners).read_text().split()) if a.forbidden_owners else set()
    summary, pairs = T.validate(rows, forbidden_owners=forbidden)
    messages_of = messages_factory(a.store_root, a.budget, NA.SymmetricCounter(a.models.split(',')))
    report = dict(schema=T.TRAIN_SCHEMA, contract=summary, plumbing=bool(a.plumbing_from), models={})
    for label in a.models.split(','):
        spec = M.MODELS[label]
        native = M.NativeTokenizer(M.bind_inventory(spec, a.inventory))
        enc = T.encode(rows, messages_of, T.native_encoder(native, T.TURN_END[label], M.COMMON_INPUT_CAP), pairs=pairs)
        seq = [len(e.positive.input_ids) for e in enc]
        report['models'][label] = dict(examples=len(enc), negatives=sum(e.negative is not None for e in enc),
                                       seq_tokens=dict(p50=NA.pct(seq, .5), p95=NA.pct(seq, .95), max=max(seq),
                                                       total=sum(seq)),
                                       target_tokens_p50=NA.pct([e.positive.target_tokens for e in enc], .5))
    report['cpu_seconds'] = round(time.monotonic() - t0, 1)
    NA.jdump(Path(a.out) / ('CHECK_DATA.plumbing.json' if a.plumbing_from else 'CHECK_DATA.json'), report)
    print(json.dumps(report, indent=2)[:2500])


def cmd_estimate(a):
    rates = measured_prefill()
    out = {}
    for label in a.models.split(','):
        insp = json.loads((Path(a.inspect_dir) / f'INSPECT.{label}.json').read_text())
        lora_p = insp['lora'][a.suffix_set]['params_at_r16'] * a.r // 16
        train_tps = rates[label] // 4
        weight = {'Qwen35': 18.83e9, 'G0e': 24.0e9}[label]         # measured WP2 LOAD_OK peak allocated
        rows = {}
        for groups in (1000, 2000, 3000):
            ex = 2 * groups
            for mode in ('sft', 'paired'):
                rows[f'{groups}g|{mode}'] = T.estimate(base_params=insp['base_parameters'], lora_params=lora_p,
                                                       weight_bytes=weight, examples=ex, mean_tokens=a.mean_tokens,
                                                       epochs=a.epochs, accumulation=a.accumulation,
                                                       train_tokens_per_s=train_tps, paired_fraction=a.paired_fraction,
                                                       mode=mode)
        out[label] = dict(measured_prefill_tok_s=rates[label], train_tok_s_assumed=train_tps, lora_params=lora_p,
                          suffix_set=a.suffix_set, r=a.r, rows=rows)
    NA.jdump(Path(a.out) / 'TRAIN_ESTIMATE.json', out)
    print(json.dumps({m: {k: (v['train_seconds'], v['steps']) for k, v in d['rows'].items()} for m, d in out.items()},
                     indent=1))


def cmd_train(a):
    """Bounded WP4 GPU training. Every check runs before any device access."""
    if not a.approval or not Path(a.approval).is_file():
        raise SystemExit('no WP4 training approval file: training refused (CPU preparation only)')
    ap = json.loads(Path(a.approval).read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], text=True)
    data_sha = hashlib.sha256(Path(a.train).read_bytes()).hexdigest()
    cfg = json.loads(Path(a.config).read_text())
    checks = dict(protocol=ap.get('protocol') == APPROVAL_PROTOCOL, authorized=ap.get('authorized') is True,
                  head=ap.get('executor_checkout_head') == head, clean=not dirty, data=ap.get('train_sha256') == data_sha,
                  config=ap.get('config_sha256') == digest(cfg), model=ap.get('model') == a.model,
                  mode=ap.get('mode') == cfg.get('mode'), steps=isinstance(ap.get('max_steps'), int),
                  seconds=isinstance(ap.get('max_gpu_seconds'), (int, float)),
                  evidence=bool(ap.get('researcher')) and bool(ap.get('decision_evidence')))
    if not all(checks.values()):
        raise SystemExit('WP4 training approval does not bind this run: refused ' + json.dumps(checks))
    out = Path(a.out)
    if (out / 'TRAIN_RECEIPT.json').exists():
        raise SystemExit('training run already exists; no silent restart')
    from metacom_pm.need_aware.runtime.backend import safe_device_guard, safe_storage_guard
    safe_storage_guard(out); safe_device_guard(initial=True)
    import torch
    from transformers import AutoModelForMultimodalLM, AutoTokenizer
    t0 = time.monotonic()
    spec = M.MODELS[a.model]; path = M.bind_inventory(spec, a.inventory).path
    torch.manual_seed(cfg['seed'])
    model = AutoModelForMultimodalLM.from_pretrained(path, local_files_only=True, dtype=torch.bfloat16,
                                                     attn_implementation='sdpa').to('cuda:0')
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.enable_input_require_grads()
    names = LORA.apply(model, suffixes=SUFFIX_SETS[cfg['suffix_set']], r=cfg['r'], alpha=cfg['alpha'],
                       dropout=cfg.get('dropout', 0.))
    rows = [json.loads(l) for l in open(a.train) if l.strip()]
    forbidden = set(Path(a.forbidden_owners).read_text().split()) if a.forbidden_owners else set()
    contract, pairs = T.validate(rows, forbidden_owners=forbidden)
    messages_of = messages_factory(a.store_root, cfg['evidence_budget'], NA.SymmetricCounter(['Qwen35', 'G0e']))
    fit = [r for r in rows if r['split'] == 'fit']; tune = [r for r in rows if r['split'] == 'tune']
    fit_ids = {r['example_id'] for r in fit}
    encode_one = T.native_encoder(M.NativeTokenizer(M.bind_inventory(spec, a.inventory)), T.TURN_END[a.model],
                                  M.COMMON_INPUT_CAP)
    enc_fit = T.encode(fit, messages_of, encode_one, pairs=[p for p in pairs if p[0] in fit_ids])
    reserve = 120.                                    # tune evaluation + save + teardown inside the cap
    receipt = T.train(model, enc_fit, cfg, pad_token_id=spec.pad_token_id, device='cuda:0',
                      max_steps=ap['max_steps'], max_seconds=ap['max_gpu_seconds'] - reserve - (time.monotonic() - t0))
    model.eval()
    enc_tune = T.encode(tune, messages_of, encode_one, pairs=[])
    with torch.no_grad():
        tune_nll = [float(-T._mean_logprob(model, e.positive, spec.pad_token_id, 'cuda:0')) for e in enc_tune]
    meta = LORA.save(out / 'adapter', model, dict(suffixes=list(SUFFIX_SETS[cfg['suffix_set']]), r=cfg['r'],
                                                  alpha=cfg['alpha']))
    NA.jdump(out / 'TRAIN_RECEIPT.json', dict(
        model=a.model, base_path=path, approval_sha256=hashlib.sha256(Path(a.approval).read_bytes()).hexdigest(),
        train_sha256=data_sha, config=cfg, contract=contract, lora_modules=len(names), adapter=meta,
        trainer=receipt, tune_mean_nll_per_token=(sum(tune_nll) / len(tune_nll)) if tune_nll else None,
        peak_reserved_bytes=torch.cuda.max_memory_reserved(), gpu_wall_seconds=round(time.monotonic() - t0, 1),
        executor_checkout_head=head))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest='cmd', required=True)
    inv = '/opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json'
    i = s.add_parser('inspect'); i.add_argument('--model', required=True); i.add_argument('--out', required=True)
    i.add_argument('--inventory', default=inv)
    c = s.add_parser('check-data')
    c.add_argument('--train'); c.add_argument('--plumbing-from'); c.add_argument('--tasks'); c.add_argument('--provenance')
    c.add_argument('--limit', type=int, default=40); c.add_argument('--store-root', required=True)
    c.add_argument('--forbidden-owners'); c.add_argument('--models', default='Qwen35,G0e')
    c.add_argument('--budget', type=int, default=1536); c.add_argument('--out', required=True)
    c.add_argument('--inventory', default=inv)
    e = s.add_parser('estimate'); e.add_argument('--inspect-dir', required=True); e.add_argument('--out', required=True)
    e.add_argument('--models', default='Qwen35,G0e'); e.add_argument('--suffix-set', default='attn_qkvo')
    e.add_argument('--r', type=int, default=16); e.add_argument('--mean-tokens', type=int, default=2000)
    e.add_argument('--epochs', type=int, default=2); e.add_argument('--accumulation', type=int, default=16)
    e.add_argument('--paired-fraction', type=float, default=1.0)
    t = s.add_parser('train')
    for x in ('--train', '--config', '--model', '--out'):
        t.add_argument(x, required=True)
    t.add_argument('--approval'); t.add_argument('--store-root', required=True); t.add_argument('--forbidden-owners')
    t.add_argument('--inventory', default=inv)
    a = p.parse_args()
    dict(inspect=cmd_inspect, **{'check-data': cmd_check_data}, estimate=cmd_estimate, train=cmd_train)[a.cmd](a)


if __name__ == '__main__':
    main()
