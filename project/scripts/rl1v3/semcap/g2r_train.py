#!/usr/bin/env python3
"""G2-R training: dialogue evidence-state adaptation (T1) and + event-factuality auxiliary (T2).

T1  cross-encoder/nli-deberta-v3-base, its NLI head kept (label semantics bound in
    evidence_state.HEAD), fine-tuned on INLI 3-way + DCS-train (upsampled).
T2  identical main data/schedule/seed + a separate 5-way MAVEN-FACT head on the shared
    encoder (conditional factuality given a marked trigger). Batches are task-homogeneous,
    so no example ever receives a fake label for the other task (missing supervision is
    masked by construction). Aux sampling p(class) ~ n^0.5 with UNWEIGHTED loss (the CPU
    smoke's balanced sampling *plus* inverse-sqrt weights double-compensated). T2 sees more
    examples and compute than T1; this is reported, not hidden.

Fixed single configuration; the pre-declared final checkpoint is the last epoch (no
selection on dev). Per-epoch checkpoints keep model, tokenizer, label map, aux head,
optimizer/scheduler/RNG state for resume. A GPU ledger enforces the cumulative 3 h cap.
"""
import argparse, json, math, os, random, sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from metacom_pm.rl1v3.semcap.evidence_state import HEAD, HEAD_INDEX, LABELS, metrics  # noqa: E402
import factuality_train as FT  # noqa: E402  (MAVEN loader; LABELS CT+/PS+/PS-/CT-/Uu)

CAP_SECONDS = 3 * 3600


def ledger_check(path, requested):
    used = sum(json.loads(s)['seconds'] for s in Path(path).read_text().splitlines() if s.strip()) if Path(path).exists() else 0
    if used + requested > CAP_SECONDS:
        raise SystemExit(f'GPU ledger: used {used:.0f}s + requested {requested}s exceeds {CAP_SECONDS}s')
    return used


def ledger_add(path, job, seconds, gpu):
    with open(path, 'a') as f:
        f.write(json.dumps(dict(job=job, seconds=round(seconds, 1), gpu=gpu, ended=time.strftime('%Y-%m-%dT%H:%M:%S'))) + '\n')


def jl(p):
    return [json.loads(s) for s in Path(p).read_text().splitlines() if s.strip()]


def main(a):
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
    used = ledger_check(a.ledger, a.max_seconds)
    random.seed(a.seed); torch.manual_seed(a.seed)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=a.resume is not None)
    dev = 'cuda:0'; gpu_name = torch.cuda.get_device_name(0)
    assert 'A4500' in gpu_name, gpu_name
    tok = AutoTokenizer.from_pretrained(a.base)
    model = AutoModelForSequenceClassification.from_pretrained(a.base).to(dev)
    cfg = model.config.id2label
    assert {int(k): v for k, v in cfg.items()} == {0: 'contradiction', 1: 'entailment', 2: 'neutral'}, cfg
    aux = torch.nn.Linear(model.config.hidden_size, len(FT.LABELS)).to(dev) if a.arm == 'T2' else None
    head = dict(HEAD); head_index = dict(HEAD_INDEX)
    main_rows = jl(a.train_inli) + jl(a.train_dcs) * a.dcs_upsample
    if a.implied_class:
        # Separate 4th class: INLI implied_entailment is neither merged into supported nor
        # forced to not_established. Row initialised from the entailment row.
        old = model.classifier; new = torch.nn.Linear(old.in_features, 4).to(dev)
        with torch.no_grad():
            new.weight[:3] = old.weight; new.bias[:3] = old.bias
            new.weight[3] = old.weight[1]; new.bias[3] = old.bias[1]
        model.classifier = new; model.num_labels = 4; model.config.num_labels = 4
        model.config.id2label = {0: 'contradiction', 1: 'entailment', 2: 'neutral', 3: 'implied_entailment'}
        model.config.label2id = {v: k for k, v in model.config.id2label.items()}
        head[3] = 'implied'; head_index['implied'] = 3
        main_rows += [dict(r, label='implied') for r in jl(a.train_implied)]
    aux_rows = []
    if aux is not None:
        maven = FT.load(a.maven, 'train_candidate'); by = {}
        for r in maven: by.setdefault(r['label'], []).append(r)
        w = {k: len(v) ** 0.5 for k, v in by.items()}; tot = sum(w.values())
        rng = random.Random(a.seed)
        for k, v in sorted(by.items()):
            take = min(len(v), round(a.aux_samples * w[k] / tot)); rng.shuffle(v); aux_rows += v[:take]
        rng.shuffle(aux_rows)
    dev_sets = {Path(p).name.split('.')[0]: jl(p) for p in a.dev}
    maven_dev = FT.load(a.maven, 'internal_dev') if aux is not None else None
    params = list(model.parameters()) + (list(aux.parameters()) if aux is not None else [])
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.01)
    steps_per_epoch = math.ceil(len(main_rows) / a.batch)
    aux_every = a.aux_every if aux is not None else 0
    aux_steps = (steps_per_epoch // aux_every) if aux_every else 0
    total = (steps_per_epoch + aux_steps) * a.epochs
    sch = get_linear_schedule_with_warmup(opt, int(0.1 * total), total)
    start_epoch = 0
    if a.resume:
        st = torch.load(Path(a.resume) / 'trainer_state.pt', map_location=dev, weights_only=False)
        model.load_state_dict(st['model']); opt.load_state_dict(st['opt']); sch.load_state_dict(st['sch'])
        if aux is not None: aux.load_state_dict(st['aux'])
        random.setstate(st['py_rng']); torch.set_rng_state(st['torch_rng']); start_epoch = st['epoch']
    lossf = torch.nn.CrossEntropyLoss()
    trunc = Counter()

    def enc(a_, b_, maxlen, kind):
        full = tok(a_, b_, truncation=False)['input_ids']
        trunc[kind] += sum(len(x) > maxlen for x in full)
        e = tok(a_, b_, truncation='longest_first', max_length=maxlen, padding=True, return_tensors='pt')
        return {k: v.to(dev) for k, v in e.items()}

    def pooled(e):
        h = model.deberta(**e).last_hidden_state
        return model.pooler(h)

    def main_logits(e):
        return model.classifier(model.dropout(pooled(e)))

    @torch.no_grad()
    def evaluate(rows, bs=64):
        model.eval(); preds = []
        for i in range(0, len(rows), bs):
            b = rows[i:i + bs]
            with torch.autocast('cuda', dtype=torch.bfloat16):
                lg = main_logits(enc([r['premise'] for r in b], [r['hypothesis'] for r in b], a.eval_max_length, 'eval'))
            for r, p in zip(b, lg.float().softmax(-1).tolist()):
                probs = {head[j]: round(p[j], 5) for j in range(len(head))}
                preds.append(dict(item_id=r['item_id'], gold=r['label'], pred=max(probs, key=probs.get), probs=probs))
        model.train(); return preds

    @torch.no_grad()
    def evaluate_aux(rows, bs=64):
        model.eval(); g, p = [], []
        for i in range(0, len(rows), bs):
            b = rows[i:i + bs]
            with torch.autocast('cuda', dtype=torch.bfloat16):
                lg = aux(model.dropout(pooled(enc([r['text'] for r in b], [r['context'] for r in b], a.max_length, 'aux_eval'))))
            p += lg.argmax(-1).tolist(); g += [r['label'] for r in b]
        model.train(); return FT.evaluate(p, g)

    t0 = time.monotonic(); log = []
    model.train()
    for ep in range(start_epoch, a.epochs):
        rng = random.Random(a.seed + ep); order = main_rows[:]; rng.shuffle(order)
        aux_iter = iter(aux_rows * 2) if aux is not None else None
        el = Counter()
        for s in range(steps_per_epoch):
            if time.monotonic() - t0 > a.max_seconds - 120:
                raise SystemExit('time guard reached before epoch end')
            b = order[s * a.batch:(s + 1) * a.batch]
            y = torch.tensor([head_index[r['label']] for r in b], device=dev)
            with torch.autocast('cuda', dtype=torch.bfloat16):
                loss = lossf(main_logits(enc([r['premise'] for r in b], [r['hypothesis'] for r in b], a.max_length, 'main')).float(), y)
            loss.backward(); torch.nn.utils.clip_grad_norm_(params, 1.0); opt.step(); sch.step(); opt.zero_grad()
            el['main_loss'] += loss.item(); el['main_steps'] += 1
            if aux_every and (s + 1) % aux_every == 0:
                ab = [next(aux_iter) for _ in range(a.batch)]
                ya = torch.tensor([r['label'] for r in ab], device=dev)
                with torch.autocast('cuda', dtype=torch.bfloat16):
                    la = lossf(aux(model.dropout(pooled(enc([r['text'] for r in ab], [r['context'] for r in ab], a.max_length, 'aux')))).float(), ya)
                la.backward(); torch.nn.utils.clip_grad_norm_(params, 1.0); opt.step(); sch.step(); opt.zero_grad()
                el['aux_loss'] += la.item(); el['aux_steps'] += 1
        train_s = time.monotonic() - t0
        ck = out / f'checkpoint-epoch{ep + 1}'; ck.mkdir(exist_ok=True)
        model.save_pretrained(ck); tok.save_pretrained(ck)
        (ck / 'LABEL_MAP.json').write_text(json.dumps(dict(head=head, labels=LABELS, base=a.base, arm=a.arm, implied_class=a.implied_class), indent=1))
        st = dict(model=model.state_dict(), opt=opt.state_dict(), sch=sch.state_dict(), epoch=ep + 1,
                  py_rng=random.getstate(), torch_rng=torch.get_rng_state())
        if aux is not None:
            st['aux'] = aux.state_dict(); torch.save(aux.state_dict(), ck / 'aux_factuality_head.pt')
        torch.save(st, ck / 'trainer_state.pt')
        entry = dict(epoch=ep + 1, train_seconds_cum=round(train_s, 1), main_loss=el['main_loss'] / max(1, el['main_steps']),
                     aux_loss=el['aux_loss'] / max(1, el['aux_steps']) if el['aux_steps'] else None,
                     main_steps=el['main_steps'], aux_steps=el['aux_steps'], dev={})
        for name, rows in dev_sets.items():
            pr = evaluate(rows)
            (out / f'PRED_{name}_epoch{ep + 1}.private.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in pr))
            gold = [x['gold'] for x in pr if x['gold'] in LABELS]
            pp = [('not_established' if x['pred'] == 'implied' else x['pred']) for x in pr if x['gold'] in LABELS]
            entry['dev'][name] = metrics(gold, pp) if gold else dict(pred_counts=dict(Counter(x['pred'] for x in pr)))
        if maven_dev is not None:
            entry['maven_internal_dev'] = evaluate_aux(maven_dev)
        entry['seconds_cum'] = round(time.monotonic() - t0, 1); log.append(entry)
        (out / 'TRAIN_LOG.json').write_text(json.dumps(log, indent=1))
        print(json.dumps(dict(epoch=ep + 1, seconds=entry['seconds_cum'], main_loss=round(entry['main_loss'], 4),
                              **{k: v.get('macro_f1') for k, v in entry['dev'].items()})), flush=True)
    secs = time.monotonic() - t0
    ledger_add(a.ledger, f'{a.arm}:{out.name}', secs, gpu_name)
    rep = dict(arm=a.arm, implied_class=a.implied_class, base=a.base, gpu=gpu_name, seconds=round(secs, 1), ledger_used_before=round(used, 1),
               main_examples_per_epoch=len(main_rows), dcs_upsample=a.dcs_upsample,
               aux_examples=len(aux_rows), aux_label_counts=dict(Counter(FT.LABELS[r['label']] for r in aux_rows)),
               aux_every=aux_every, epochs=a.epochs, lr=a.lr, batch=a.batch, max_length=a.max_length,
               eval_max_length=a.eval_max_length, seed=a.seed, truncated_inputs=dict(trunc),
               peak_allocated_bytes=torch.cuda.max_memory_allocated(), final_checkpoint=f'checkpoint-epoch{a.epochs}',
               selection='pre-declared final = last epoch; no dev-based checkpoint choice')
    (out / 'TRAIN_REPORT.json').write_text(json.dumps(rep, indent=1) + '\n'); print(json.dumps(rep))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--arm', choices=['T1', 'T2', 'T1i'], required=True)
    for n in ('base', 'train-inli', 'train-dcs', 'maven', 'output', 'ledger'): p.add_argument('--' + n, required=True)
    p.add_argument('--dev', nargs='+', required=True)
    p.add_argument('--dcs-upsample', type=int, default=8); p.add_argument('--aux-samples', type=int, default=13000)
    p.add_argument('--aux-every', type=int, default=2); p.add_argument('--epochs', type=int, default=2)
    p.add_argument('--lr', type=float, default=2e-5); p.add_argument('--batch', type=int, default=16)
    p.add_argument('--max-length', type=int, default=320); p.add_argument('--eval-max-length', type=int, default=512)
    p.add_argument('--seed', type=int, default=42); p.add_argument('--max-seconds', type=int, default=3600)
    p.add_argument('--resume', default=None)
    p.add_argument('--implied-class', action='store_true'); p.add_argument('--train-implied')
    main(p.parse_args())
