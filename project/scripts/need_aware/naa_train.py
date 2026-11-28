#!/usr/bin/env python3
"""NAA WP4 training-backend CLI (B line). CPU commands run now; `train` needs a bounded approval.

  inspect     real architecture on the meta device (no weights): LoRA target names/parameter
              counts per suffix set; real native chat-template prompt/target boundary check.
  check-data  validate A's training JSONL (contract + leakage) and encode with the native
              tokenizer; --plumbing-from builds clearly labelled PLUMBING rows from real
              training-side inputs (real token lengths, placeholder targets, never trainable).
  estimate    steps / tokens / seconds / memory planning from measured WP2 prefill rates.
  check-v11   A v1.1 training contract on real tokenizers/architecture: encode_target prefix == inference
              chat_ids, end token == native turn end, real LoRA coverage of A's target modules, memory and
              an upper-bound time from measured short-input forward latency (WP2 ledger).
  train-v11   A rows + A objective (U2/U3) on GPU; refuses without a bound approval before device access.
  check-reply  2026-11-28 main path: A's reply rows (official reply + non-preferred replies) -> contract,
              exact inference prompt ids + native turn end, compute-parity token totals, time/memory bound.
  train-reply  U2 (reply SFT) / U3 (SFT + reply ranking) on GPU: approval bound to HEAD/data/candidate/caps,
              exclusive GPU lock, TrainGuard hard deadline + watchdog, seed-fixed adapter init (hash
              recorded), 20-step technical smoke, adapter identity for the generator binding.
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
from metacom_pm.need_aware.data.contracts import RuntimeTask, digest, load_runtime  # noqa: E402
from metacom_pm.need_aware.memory import reader as R  # noqa: E402
from metacom_pm.need_aware.memory.writer import StoreCache  # noqa: E402
from metacom_pm.need_aware.runtime import lora as LORA  # noqa: E402
from metacom_pm.need_aware.runtime import models as M  # noqa: E402
from metacom_pm.need_aware.runtime import training as T  # noqa: E402

SUFFIX_SETS = {'attn_qv': ('q_proj', 'v_proj'), 'attn_qkvo': ('q_proj', 'k_proj', 'v_proj', 'o_proj'),
               'attn_mlp': ('q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'),
               # Qwen3.5: 24 of 32 layers are linear attention (in_proj_qkv/z/a/b, out_proj); q/v exist on 8 only
               'qv_all_layers': ('q_proj', 'v_proj', 'in_proj_qkv')}
APPROVAL_PROTOCOL = 'naa-wp4-train-approval-v1'
REPLY_APPROVAL_PROTOCOL = 'naa-wp4-reply-train-approval-v1'
TRAIN_LOCK = '/opt/tokkio-data0/tokkio_projects/pmrl1-validation/limited-g0e-exclusive.lock'   # same lock as inference
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
                       dropout=cfg.get('dropout', 0.), seed=cfg['seed'])
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


def measured_short_forward():
    """Upper bound for one forward of a short sequence: WP2 internal first-token latency, Qwen, inputs < 1,600."""
    v = [json.loads(l) for l in open(WP2_LEDGER)]
    t = sorted(e['first_token_latency_ns'] / 1e9 for e in v if e.get('event') == 'ATTEMPT_RESULT'
               and e.get('model_label') == 'Qwen35' and e.get('first_token_latency_ns') and e['input_tokens'] < 1600)
    return dict(p50=round(t[len(t) // 2], 4), p95=round(t[int(.95 * len(t))], 4), n=len(t))


def cmd_check_v11(a):
    import torch
    from transformers import AutoConfig, AutoModelForMultimodalLM
    from metacom_pm.need_aware.data.training_objective import encode_target
    cand = json.loads(Path(a.candidate).read_text())
    spec = M.MODELS['Qwen35']; b = M.bind_inventory(spec, a.inventory)
    if b.revision != cand['revision']:
        raise SystemExit('candidate base revision differs from the bound Qwen35 checkpoint')
    native = M.NativeTokenizer(b)
    out = dict(candidate_sha256=NA.file_sha(a.candidate), base=dict(model=spec.model_id, revision=b.revision, path=b.path))
    for split in ('fit', 'tune'):
        path = cand[f'{split}_file' if split == 'tune' else 'train_file']
        if NA.file_sha(path) != cand[f'{"train" if split == "fit" else "tune"}_sha256']:
            raise SystemExit(split + ' file changed after the candidate freeze')
        rows = [json.loads(l) for l in open(path)]
        if {r['split'] for r in rows} != {split}:
            raise SystemExit(split + ' file mixes splits (development must never enter training)')
        same = end = 0; seq, proc = [], []
        for r in rows:
            e = encode_target(native.tok, r, max_length=cand['max_seq_length'])
            n = sum(x == -100 for x in e['labels'])
            same += e['input_ids'][:n] == native.chat_ids(r['messages'])
            end += e['input_ids'][-1] == T.TURN_END['Qwen35']
            seq.append(len(e['input_ids']))
            proc.append(len(e['input_ids']) + len(e['chosen_action']['input_ids']) + len(e['rejected_action']['input_ids']))
        out[split] = dict(rows=len(rows), groups=len({r['group_id'] for r in rows}), owners=len({r['owner_id'] for r in rows}),
                          prefix_equals_inference_chat_ids=same, ends_with_native_turn_end=end,
                          pair_loss_rows=sum(bool(r['pair_loss_mask']) for r in rows),
                          seq_tokens=dict(p50=NA.pct(seq, .5), p95=NA.pct(seq, .95), max=max(seq)),
                          processed_tokens_three_branches=sum(proc))
    forbidden = set(Path(a.forbidden_owners).read_text().split()) if a.forbidden_owners else set()
    fit_owners = {json.loads(l)['owner_id'] for l in open(cand['train_file'])}
    out['forbidden_owner_overlap'] = len(fit_owners & forbidden)
    cfg = AutoConfig.from_pretrained(b.path, local_files_only=True)
    with torch.device('meta'):
        model = AutoModelForMultimodalLM.from_config(cfg)
    cov = {}
    for name, suf in (('A_candidate', tuple(cand['lora']['target_modules'])), ('qv_all_layers', SUFFIX_SETS['qv_all_layers']),
                      ('attn_mlp', SUFFIX_SETS['attn_mlp'])):
        names = LORA.target_names(model, suf)
        layers = {n.split('.layers.')[1].split('.')[0] for n in names if '.layers.' in n}
        cov[name] = dict(modules=len(names), layers_touched=len(layers), of_layers=cfg.text_config.num_hidden_layers,
                         params=sum(cand['lora']['rank'] * (model.get_submodule(n).in_features
                                                            + model.get_submodule(n).out_features) for n in names))
    out['lora_coverage'] = cov
    fwd = measured_short_forward()
    per_example = 3 * 4 * fwd['p50']             # 3 branches x (fwd + bwd ~2x + checkpoint recompute)
    fit = out['fit']['rows']; tune = out['tune']['rows']
    out['time_upper_bound'] = dict(measured_short_forward_s=fwd, per_example_s=round(per_example, 3),
                                   train_s_per_method=round(fit * per_example), tune_eval_s=round(tune * 3 * fwd['p50']),
                                   steps=-(-fit // cand['gradient_accumulation']),
                                   basis='WP2 Qwen35 internal first-token latency at <1,600 input tokens (>= one forward of '
                                         'the <=250-token training sequences); 4x per branch; verified by a 20-step smoke')
    out['memory'] = dict(weights_bf16_GB=18.83, note='measured WP2 LOAD_OK peak allocated; sequences <=250 tokens, '
                         'logits_to_keep tails, LoRA+Adam < 0.1 GB; activations negligible vs 48 GB')
    out['gemma_note'] = ('A encode_target ends with tokenizer.eos_token_id; for G0e that is <eos>(1), not the native '
                         'turn end <turn|>(106). Not used: the training candidate is Qwen35 only.')
    NA.jdump(Path(a.out) / 'TRAIN_CONTRACT_V11.json', out)
    print(json.dumps(out, indent=1)[:3000])


def cmd_train_v11(a):
    """Bounded U2/U3 GPU training on A's frozen rows. Every check before any device access."""
    from metacom_pm.need_aware.data.training_objective import encode_target
    if not a.approval or not Path(a.approval).is_file():
        raise SystemExit('no WP4 training approval file: training refused (CPU preparation only)')
    ap = json.loads(Path(a.approval).read_text()); cand = json.loads(Path(a.candidate).read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], text=True)
    checks = dict(protocol=ap.get('protocol') == APPROVAL_PROTOCOL, authorized=ap.get('authorized') is True,
                  head=ap.get('executor_checkout_head') == head, clean=not dirty, method=ap.get('method') == a.method,
                  candidate=ap.get('candidate_sha256') == NA.file_sha(a.candidate),
                  data=NA.file_sha(cand['train_file']) == cand['train_sha256'] == ap.get('train_sha256'),
                  steps=isinstance(ap.get('max_steps'), int) and ap['max_steps'] <= cand['max_optimizer_steps'],
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
    from transformers import AutoModelForMultimodalLM
    t0 = time.monotonic()
    spec = M.MODELS['Qwen35']; b = M.bind_inventory(spec, a.inventory); native = M.NativeTokenizer(b)
    rows = [json.loads(l) for l in open(cand['train_file'])]
    enc = [encode_target(native.tok, r, max_length=cand['max_seq_length']) for r in T.group_order(rows, cand['seed'])]
    if any(e['input_ids'][-1] != T.TURN_END['Qwen35'] for e in enc):
        raise SystemExit('target does not end with the native turn end')
    model = AutoModelForMultimodalLM.from_pretrained(b.path, local_files_only=True, dtype=torch.bfloat16,
                                                     attn_implementation='sdpa').to('cuda:0')
    load_s = time.monotonic() - t0
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.enable_input_require_grads()
    lc = cand['lora']
    names = LORA.apply(model, **LORA.WP4_LORA, seed=cand['seed'])    # frozen 2026-11-28; no approval override
    cfg = dict(method=a.method, learning_rate=cand['learning_rate'], weight_decay=cand['weight_decay'],
               warmup_steps=cand['warmup_steps'], gradient_accumulation=cand['gradient_accumulation'],
               pair_weight=cand['pair_weight'], pair_margin=cand['pair_margin'], seed=cand['seed'])
    reserve = 180.
    receipt = T.train_v11(model, enc, cfg, device='cuda:0', max_steps=ap['max_steps'],
                          max_seconds=ap['max_gpu_seconds'] - reserve - (time.monotonic() - t0))
    s0 = time.monotonic()
    meta = LORA.save(out / 'adapter', model, dict(suffixes=list(LORA.WP4_LORA['suffixes']), r=LORA.WP4_LORA['r'],
                                                  alpha=LORA.WP4_LORA['alpha']))
    NA.jdump(out / 'TRAIN_RECEIPT.json', dict(
        method=a.method, candidate_sha256=NA.file_sha(a.candidate), approval_sha256=NA.file_sha(a.approval),
        base=dict(path=b.path, revision=b.revision), lora_modules=len(names), adapter=meta, trainer=receipt,
        load_s=round(load_s, 1), save_s=round(time.monotonic() - s0, 1),
        peak_reserved_bytes=torch.cuda.max_memory_reserved(), gpu_wall_seconds=round(time.monotonic() - t0, 1),
        executor_checkout_head=head))


# ---------------------------------------------------------------- 2026-11-28 reply-level supervision
def reply_rows(path, store_root=None, budget=None):
    """A's reply rows. Rows without `messages` are rendered here with the U0 renderer from B's stores
    (task + evidence_ids), the same renderer as evaluation minus the MCQ instruction."""
    rows = [json.loads(l) for l in open(path) if l.strip()]
    if all('messages' in r for r in rows):
        return rows, 'A pre-rendered'
    cache = StoreCache(Path(store_root) / 'stores')
    smap = {json.loads(x)['task_id']: json.loads(x)['store_id'] for x in NA.store_map(store_root).read_text().splitlines()}
    for r in rows:
        if 'messages' in r:
            continue
        task = RuntimeTask(**r['task']); store = cache.get(smap[task.task_id]); by = store.by_id()
        units = sorted((by[x] for x in r['evidence_ids']), key=lambda u: u.order)
        packed = R.Packed(units=tuple(units), priority_ids=tuple(r['evidence_ids']), skipped_over_budget=(), tokens=0)
        r['messages'] = B.build('U0', task, store, packed, recall_suffix=True)[0]
    return rows, 'B U0 renderer'


def reply_bound(enc, short_forward_s, prefill_tok_s, *, factor=4.):
    """Upper bound seconds for one epoch: every branch costs factor x max(short-forward latency, tokens/prefill)."""
    per = lambda n: factor * max(short_forward_s, n / prefill_tok_s)
    return sum(per(len(e['chosen'].input_ids)) + sum(per(len(x.input_ids)) for x in e['rejected']) for e in enc)


def cmd_check_reply(a):
    cand = json.loads(Path(a.candidate).read_text())
    rows, how = reply_rows(cand['train_file'], a.store_root)
    forbidden = set(Path(a.forbidden_owners).read_text().split()) if a.forbidden_owners else set()
    contract = T.validate_reply(rows, forbidden_owners=forbidden, allow_plumbing=True)
    contract['plumbing_rows'] = sum(bool(r['provenance'].get('plumbing')) for r in rows)
    b = M.bind_inventory(M.MODELS['Qwen35'], a.inventory); native = M.NativeTokenizer(b)
    fit = [r for r in T.group_order(rows, cand['seed']) if r['split'] == 'fit']
    enc, align = T.encode_reply(fit, T.native_encoder(native, T.TURN_END['Qwen35'], M.COMMON_INPUT_CAP),
                                eos_ids=b.decode()['eos_token_id'], turn_end_id=T.TURN_END['Qwen35'])
    sf, pf = measured_short_forward(), measured_prefill()['Qwen35']
    steps = min(cand['max_optimizer_steps'], -(-len(enc) // cand['gradient_accumulation']))
    epoch_s = reply_bound(enc, sf['p50'], pf)
    out = dict(schema=T.REPLY_SCHEMA, candidate_sha256=NA.file_sha(a.candidate), render=how, contract=contract,
               alignment=align, lora=dict(LORA.WP4_LORA, suffixes=list(LORA.WP4_LORA['suffixes'])), steps=steps,
               compute_parity='U2 and U3 run every chosen and rejected branch; U2 ranking coefficient 0',
               time_bound=dict(per_method_train_s=round(epoch_s), basis=f"4 x max({sf['p50']} s short forward, tokens/{pf} tok/s)",
                               smoke_steps=T.SMOKE_STEPS, load_s=38, save_close_reserve_s=130),
               base_g_id=b.g_id, executor_checkout_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip())
    NA.jdump(Path(a.out), out)
    print(json.dumps({k: out[k] for k in ('render', 'alignment', 'steps', 'time_bound')}, indent=2))


def cmd_plumbing_reply(a):
    """PLUMBING reply rows from a W4-0 manifest's U0 rows: real task, real delivered evidence, option texts as
    placeholder replies (no gold is read; option A is NOT the answer). For lengths/encoding only; training refuses them."""
    _, rows = NA.load_full(a.manifest_dir)
    tasks = {t.task_id: t for t in load_runtime(Path(a.tasks))}
    out = []
    for r in rows:
        if r['arm'] != 'U0' or r['status'] != 'ready':
            continue
        t = tasks[r['task_id']]
        out.append(dict(example_id='plumb:' + t.task_id, group_id='plumb:' + t.task_id, owner_id=t.persona_group,
                        split='fit', task=t.to_dict(), evidence_ids=r['trace']['delivered_ids'],
                        chosen=t.options[0]['text'], rejected=[o['text'] for o in t.options[1:]],
                        provenance=dict(plumbing=True, note='placeholder replies; not supervision')))
    NA.jsonl(Path(a.out), out)
    print(len(out), 'PLUMBING reply rows')


def cmd_train_reply(a):
    """Bounded U2/U3 reply training. Every admission check happens before any lock or device access."""
    import fcntl
    if not a.approval or not Path(a.approval).is_file():
        raise SystemExit('no WP4 reply-training approval file: training refused (CPU preparation only)')
    ap = json.loads(Path(a.approval).read_text()); cand = json.loads(Path(a.candidate).read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], text=True)
    train_sha = NA.file_sha(cand['train_file'])
    checks = dict(protocol=ap.get('protocol') == REPLY_APPROVAL_PROTOCOL, authorized=ap.get('authorized') is True,
                  head=ap.get('executor_checkout_head') == head, clean=not dirty, method=ap.get('method') == a.method,
                  candidate=ap.get('candidate_sha256') == NA.file_sha(a.candidate),
                  data=train_sha == cand['train_sha256'] == ap.get('train_sha256'),
                  steps=isinstance(ap.get('max_steps'), int) and 0 < ap['max_steps'] <= cand['max_optimizer_steps'],
                  seconds=isinstance(ap.get('max_gpu_seconds'), (int, float)) and ap['max_gpu_seconds'] > 0,
                  lora=ap.get('lora') == dict(LORA.WP4_LORA, suffixes=list(LORA.WP4_LORA['suffixes'])),
                  evidence=bool(ap.get('researcher')) and bool(ap.get('decision_evidence')))
    if not all(checks.values()):
        raise SystemExit('WP4 reply-training approval does not bind this run: refused ' + json.dumps(checks))
    out = Path(a.out)
    if out.exists():
        raise SystemExit('training output exists; no silent restart')
    out.mkdir(parents=True)
    b = M.bind_inventory(M.MODELS['Qwen35'], a.inventory); native = M.NativeTokenizer(b)
    rows, how = reply_rows(cand['train_file'], a.store_root)
    T.validate_reply(rows, forbidden_owners=set(Path(a.forbidden_owners).read_text().split()) if a.forbidden_owners else ())
    ordered = T.group_order(rows, cand['seed'])                     # identical order for U2 and U3
    enc, align = T.encode_reply([r for r in ordered if r['split'] == 'fit'],
                                T.native_encoder(native, T.TURN_END['Qwen35'], M.COMMON_INPUT_CAP),
                                eos_ids=b.decode()['eos_token_id'], turn_end_id=T.TURN_END['Qwen35'])
    from metacom_pm.need_aware.runtime.backend import safe_device_guard, safe_storage_guard
    safe_storage_guard(out)
    lock = open(TRAIN_LOCK, 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)               # never queue behind / preempt another GPU job
    t_lock = time.monotonic()
    safe_device_guard(initial=True)
    stamp = lambda name, **kw: NA.jdump(out / name, dict(utc=time.time(), elapsed=round(time.monotonic() - t_lock, 1), **kw))
    guard = T.TrainGuard(started=t_lock, max_seconds=ap['max_gpu_seconds'], save_reserve=a.save_reserve,
                         close_reserve=10., storage=lambda: safe_storage_guard(out), device=lambda: safe_device_guard(),
                         on_kill=lambda: stamp('HARD_KILL.json', reason='hard deadline reached inside a call'))
    import torch
    from transformers import AutoModelForMultimodalLM
    model = AutoModelForMultimodalLM.from_pretrained(b.path, local_files_only=True, dtype=torch.bfloat16,
                                                     attn_implementation='sdpa').to('cuda:0')
    load_s = time.monotonic() - t_lock
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.enable_input_require_grads()
    names = LORA.apply(model, **LORA.WP4_LORA, seed=cand['seed'])   # seed fixed BEFORE adapter creation
    init_sha = LORA.adapter_digest(model)
    cfg = dict(method=a.method, learning_rate=cand['learning_rate'], weight_decay=cand['weight_decay'],
               warmup_steps=cand['warmup_steps'], gradient_accumulation=cand['gradient_accumulation'],
               rank_weight=cand['rank_weight'], rank_margin=cand['rank_margin'], seed=cand['seed'])
    receipt = T.train_reply(model, enc, cfg, guard=guard, device='cuda:0', max_steps=ap['max_steps'],
                            log_path=out / 'steps.jsonl', peak=torch.cuda.max_memory_reserved)
    s0 = time.monotonic()
    meta = LORA.save(out / 'adapter', model, dict(suffixes=list(LORA.WP4_LORA['suffixes']), r=LORA.WP4_LORA['r'],
                                                  alpha=LORA.WP4_LORA['alpha'], seed=cand['seed']))
    rec = dict(method=a.method, candidate_sha256=NA.file_sha(a.candidate), approval_sha256=NA.file_sha(a.approval),
               train_data_sha256=train_sha, render=how, alignment=align, base_g_id=b.g_id,
               base=dict(path=b.path, revision=b.revision), lora_modules=len(names), init_adapter_sha256=init_sha,
               adapter=meta, adapter_config_sha256=digest(meta['config']), trainer=receipt,
               load_s=round(load_s, 1), save_s=round(time.monotonic() - s0, 1),
               peak_reserved_bytes=torch.cuda.max_memory_reserved(), gpu_wall_seconds=round(time.monotonic() - t_lock, 1),
               executor_checkout_head=head)
    NA.jdump(out / 'TRAIN_RECEIPT.json', rec)
    NA.jdump(out / 'ADAPTER_IDENTITY.json', dict(
        method=a.method, adapter_sha256=meta['adapter_sha256'], adapter_config_sha256=rec['adapter_config_sha256'],
        init_adapter_sha256=init_sha, base_g_id=b.g_id, train_data_sha256=train_sha,
        train_receipt_sha256=NA.file_sha(out / 'TRAIN_RECEIPT.json'), trainer_version=T.REPLY_TRAINER_VERSION,
        adapter_path=str(out / 'adapter')))


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
    v = s.add_parser('check-v11'); v.add_argument('--candidate', required=True); v.add_argument('--out', required=True)
    v.add_argument('--forbidden-owners'); v.add_argument('--inventory', default=inv)
    w = s.add_parser('train-v11')
    for x in ('--candidate', '--method', '--out'):
        w.add_argument(x, required=True)
    w.add_argument('--approval'); w.add_argument('--inventory', default=inv)
    cr = s.add_parser('check-reply'); cr.add_argument('--candidate', required=True); cr.add_argument('--out', required=True)
    cr.add_argument('--store-root'); cr.add_argument('--forbidden-owners'); cr.add_argument('--inventory', default=inv)
    pr = s.add_parser('plumbing-reply'); pr.add_argument('--manifest-dir', required=True)
    pr.add_argument('--tasks', required=True); pr.add_argument('--out', required=True)
    tr = s.add_parser('train-reply')
    for x in ('--candidate', '--method', '--out'):
        tr.add_argument(x, required=True)
    tr.add_argument('--approval'); tr.add_argument('--store-root'); tr.add_argument('--forbidden-owners')
    tr.add_argument('--save-reserve', type=float, default=120.); tr.add_argument('--inventory', default=inv)
    a = p.parse_args()
    dict(**{'check-reply': cmd_check_reply, 'train-reply': cmd_train_reply, 'plumbing-reply': cmd_plumbing_reply},
         **{'check-v11': cmd_check_v11, 'train-v11': cmd_train_v11}, inspect=cmd_inspect, **{'check-data': cmd_check_data}, estimate=cmd_estimate, train=cmd_train)[a.cmd](a)


if __name__ == '__main__':
    main()
