#!/usr/bin/env python3
"""Trigger-conditioned event factuality (MAVEN-FACT) training entry.

Conditional EFD: the official trigger is given and marked (<t> ... </t>); this is
NOT end-to-end event discovery. DMBert-style CLS classifier over 5 labels
(CT+, PS+, PS-, CT-, Uu). CT+ is ~94% of mentions, so the loss is class-weighted
(inverse sqrt frequency) and reporting is Macro-F1, Balanced Accuracy and per-class
recall on the document-disjoint internal_dev split. Official test is never used.

`--smoke N` trains on a small stratified subset on CPU to verify the entry only;
its numbers are not a capability result. The full run is a separate GPU request.
Factuality (CT+ = 'stated as certainly happening') is not 'actually happened' and
is not a user-event label in dialogue without separate validation.
"""
import argparse, json, math, random, time
from collections import Counter
from pathlib import Path

LABELS = ['CT+', 'PS+', 'PS-', 'CT-', 'Uu']


def load(data_dir, split, limit=None, seed=0):
    d = Path(data_dir); tgt = {}
    for line in (d / 'TARGETS.private.jsonl').open():
        r = json.loads(line); tgt[r['item_id']] = r['factuality']
    rows = []
    for line in (d / 'INPUTS.private.jsonl').open():
        r = json.loads(line)
        if r['split'] != split:
            continue
        i = r['input']; trig = i['target_trigger']; toks = i['tokens'][trig['sent_id']]
        a, b = trig['offset']
        marked = toks[:a] + ['<t>'] + toks[a:b] + ['</t>'] + toks[b:]
        prev = ' '.join(i['tokens'][trig['sent_id'] - 1]) if trig['sent_id'] > 0 else ''
        rows.append(dict(item_id=r['item_id'], document_id=r['document_id'], text=' '.join(marked), context=prev,
                         label=LABELS.index(tgt[r['item_id']])))
    if limit:
        rng = random.Random(seed); by = {}
        for r in rows:
            by.setdefault(r['label'], []).append(r)
        per = max(1, limit // len(by)); rows = []
        for lab, rs in sorted(by.items()):
            rng.shuffle(rs); rows += rs[:per]
        rng.shuffle(rows)
    return rows


def evaluate(pred, gold):
    out = {}; recs = []; f1s = []
    for k, lab in enumerate(LABELS):
        tp = sum(p == k and g == k for p, g in zip(pred, gold)); n = sum(g == k for g in gold); m = sum(p == k for p in pred)
        rec = tp / n if n else None; prec = tp / m if m else None
        f1 = 2 * prec * rec / (prec + rec) if rec and prec else 0.0
        out[lab] = dict(n=n, recall=rec, precision=prec, f1=f1)
        if n:
            recs.append(rec); f1s.append(f1)
    out['macro_f1'] = sum(f1s) / len(f1s); out['balanced_accuracy'] = sum(recs) / len(recs)
    out['accuracy'] = sum(p == g for p, g in zip(pred, gold)) / len(gold)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', required=True); p.add_argument('--model', required=True); p.add_argument('--output', required=True)
    p.add_argument('--epochs', type=float, default=3); p.add_argument('--lr', type=float, default=2e-5)
    p.add_argument('--batch', type=int, default=16); p.add_argument('--max-length', type=int, default=192)
    p.add_argument('--smoke', type=int, default=0); p.add_argument('--dev-limit', type=int, default=0)
    p.add_argument('--device', default='cpu'); p.add_argument('--seed', type=int, default=42); p.add_argument('--threads', type=int, default=8)
    a = p.parse_args()
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
    torch.manual_seed(a.seed); random.seed(a.seed); torch.set_num_threads(a.threads)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    train = load(a.data, 'train_candidate', a.smoke or None, a.seed)
    dev = load(a.data, 'internal_dev', a.dev_limit or None, a.seed + 1)
    assert not ({r['document_id'] for r in train} & {r['document_id'] for r in dev}), 'document leakage'
    tok = AutoTokenizer.from_pretrained(a.model, local_files_only=True)
    tok.add_special_tokens({'additional_special_tokens': ['<t>', '</t>']})
    model = AutoModelForSequenceClassification.from_pretrained(a.model, num_labels=len(LABELS), local_files_only=True)
    model.resize_token_embeddings(len(tok)); model.to(a.device)
    freq = Counter(r['label'] for r in load(a.data, 'train_candidate'))
    w = torch.tensor([1 / math.sqrt(freq[k]) for k in range(len(LABELS))]); w = w / w.mean()
    lossf = torch.nn.CrossEntropyLoss(weight=w.to(a.device))
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = math.ceil(len(train) / a.batch * a.epochs)
    sch = get_linear_schedule_with_warmup(opt, int(.06 * steps), steps)

    def enc(batch):
        return {k: v.to(a.device) for k, v in tok([r['text'] for r in batch], [r['context'] for r in batch],
                truncation='longest_first', max_length=a.max_length, padding=True, return_tensors='pt').items()}
    t0 = time.monotonic(); step = 0; log = []
    model.train()
    while step < steps:
        random.shuffle(train)
        for i in range(0, len(train), a.batch):
            if step >= steps:
                break
            b = train[i:i + a.batch]
            loss = lossf(model(**enc(b)).logits, torch.tensor([r['label'] for r in b], device=a.device))
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sch.step(); opt.zero_grad(); step += 1
            if step % 20 == 0:
                log.append(dict(step=step, loss=float(loss))); print(log[-1], flush=True)
    train_s = time.monotonic() - t0
    model.eval(); pred = []; t1 = time.monotonic()
    with torch.inference_mode():
        for i in range(0, len(dev), 64):
            pred += model(**enc(dev[i:i + 64])).logits.argmax(-1).tolist()
    res = dict(protocol='semcap-maven-fact-conditional-efd-v1', smoke=bool(a.smoke), train_examples=len(train),
               dev_examples=len(dev), train_label_counts=dict(Counter(LABELS[r['label']] for r in train)),
               dev_label_counts=dict(Counter(LABELS[r['label']] for r in dev)), base_model=a.model, epochs=a.epochs,
               lr=a.lr, batch=a.batch, max_length=a.max_length, device=a.device, train_seconds=train_s,
               dev_seconds=time.monotonic() - t1, class_weights=w.tolist(), dev_metrics=evaluate(pred, [r['label'] for r in dev]),
               scope='conditional EFD with official triggers; internal document-disjoint dev; official test unused',
               caveat='smoke run verifies the entry only; not a capability result' if a.smoke else 'development result')
    (out / 'RESULT_PUBLIC.json').write_text(json.dumps(res, indent=1) + '\n'); (out / 'train_log.json').write_text(json.dumps(log))
    if not a.smoke:
        model.save_pretrained(out / 'model'); tok.save_pretrained(out / 'model')
    print(json.dumps(res['dev_metrics'], indent=1))


if __name__ == '__main__':
    main()
