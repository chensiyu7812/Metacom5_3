#!/usr/bin/env python3
"""Evaluate one evidence-state checkpoint (T0 = untouched base NLI) on every eval file.

Writes raw predictions (probabilities) per file; inputs longer than --max-length are
`unprocessed` (technical), never not_established. Records device inference cost.
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from metacom_pm.rl1v3.semcap.evidence_state import HEAD, UNPROCESSED  # noqa: E402


def main(a):
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import g2r_train as G
    dev = a.device
    if dev.startswith('cuda'):
        assert 'A4500' in torch.cuda.get_device_name(0); G.ledger_check(a.ledger, a.max_seconds)
    else:
        torch.set_num_threads(a.threads)
    tok = AutoTokenizer.from_pretrained(a.checkpoint)
    model = AutoModelForSequenceClassification.from_pretrained(a.checkpoint).to(dev).eval()
    cfg = {int(k): v for k, v in model.config.id2label.items()}
    head = dict(HEAD)
    if len(cfg) == 4:
        assert cfg == {0: 'contradiction', 1: 'entailment', 2: 'neutral', 3: 'implied_entailment'}; head[3] = 'implied'
    else:
        assert cfg == {0: 'contradiction', 1: 'entailment', 2: 'neutral'}
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False); t0 = time.monotonic(); cost = {}
    for path in a.files:
        rows = [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]
        name = Path(path).name.split('.')[0]; preds = []; s0 = time.monotonic()
        for i in range(0, len(rows), a.batch):
            b = rows[i:i + a.batch]
            lens = [len(x) for x in tok([r['premise'] for r in b], [r['hypothesis'] for r in b], truncation=False)['input_ids']]
            ok = [j for j, n in enumerate(lens) if n <= a.max_length]
            probs = {}
            if ok:
                e = tok([b[j]['premise'] for j in ok], [b[j]['hypothesis'] for j in ok], padding=True, return_tensors='pt')
                with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16, enabled=dev.startswith('cuda')):
                    lg = model(**{k: v.to(dev) for k, v in e.items()}).logits.float()
                for j, p in zip(ok, lg.softmax(-1).tolist()):
                    probs[j] = {head[k]: round(p[k], 5) for k in range(len(head))}
            for j, r in enumerate(b):
                pr = probs.get(j)
                preds.append(dict(item_id=r['item_id'], gold=r['label'], input_tokens=lens[j],
                                  pred=UNPROCESSED if pr is None else max(pr, key=pr.get), probs=pr))
        (out / f'PRED_{name}.private.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in preds))
        cost[name] = dict(items=len(rows), seconds=round(time.monotonic() - s0, 3),
                          ms_per_item=round(1000 * (time.monotonic() - s0) / max(1, len(rows)), 2),
                          unprocessed=sum(x['pred'] == UNPROCESSED for x in preds))
    secs = time.monotonic() - t0
    if dev.startswith('cuda'): G.ledger_add(a.ledger, f'eval:{out.name}', secs, torch.cuda.get_device_name(0))
    (out / 'EVAL_COST.json').write_text(json.dumps(dict(checkpoint=a.checkpoint, device=dev, batch=a.batch,
        max_length=a.max_length, seconds=round(secs, 2), per_file=cost), indent=1) + '\n')
    print(json.dumps(cost))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ('checkpoint', 'output', 'ledger'): p.add_argument('--' + n, required=True)
    p.add_argument('--files', nargs='+', required=True)
    p.add_argument('--device', default='cuda:0'); p.add_argument('--batch', type=int, default=64)
    p.add_argument('--threads', type=int, default=8); p.add_argument('--max-length', type=int, default=512)
    p.add_argument('--max-seconds', type=int, default=900)
    main(p.parse_args())
