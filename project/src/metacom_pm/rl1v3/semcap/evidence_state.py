"""Dialogue evidence state: supported / contradicted / not_established, plus INSPECT_CLAIM.

not_established is an information state ("the visible evidence neither supports nor refutes
the claim"), not a negation of the claim in reality. Model failures (input over capacity,
missing checkpoint, runtime error) are reported as `unprocessed`, never as not_established.
Opposing evidence items are kept as an explicit conflict instead of being overwritten.

Label semantics are bound to the base NLI head: cross-encoder/nli-deberta-v3-base config
id2label = {0: contradiction, 1: entailment, 2: neutral}; fine-tuning keeps that head.
"""
from __future__ import annotations

import time
from collections import Counter

LABELS = ('supported', 'contradicted', 'not_established')
HEAD = {0: 'contradicted', 1: 'supported', 2: 'not_established'}
HEAD_INDEX = {v: k for k, v in HEAD.items()}
UNPROCESSED = 'unprocessed'
IMPLIED = 'implied'   # optional 4th head (T1i): suggested by context, not explicitly stated; never a confirmed fact
WHO = {'seeker': 'the user', 'supporter': 'the supporter'}


def render(evidence):
    """Deterministic premise text. evidence: [{speaker, text, session?}] in chronological order.
    Speaker words come from host metadata (identity is delivered, not inferred)."""
    sessions = [e.get('session') for e in evidence if e.get('session') is not None]
    multi = len(set(sessions)) > 1
    lines = []
    for e in evidence:
        who = WHO.get(e['speaker'], e['speaker'])
        text = ' '.join(str(e['text']).split())
        if multi:
            lines.append(f"In session {e['session']}, {who} said: \"{text}\"")
        else:
            lines.append(f"{who[0].upper() + who[1:]} said: \"{text}\"")
    if multi:
        lines.insert(0, 'Sessions are listed in chronological order.')
    return '\n'.join(lines)


def metrics(gold, pred):
    """gold/pred: sequences of labels; pred may contain UNPROCESSED (counted, never correct)."""
    n = len(gold); conf = Counter(zip(gold, pred)); out = dict(n=n)
    out['unprocessed'] = sum(p == UNPROCESSED for p in pred)
    per = {}
    for c in LABELS:
        tp = conf[(c, c)]; fp = sum(conf[(g, c)] for g in LABELS if g != c)
        fn = sum(v for (g, p), v in conf.items() if g == c and p != c)
        pr = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
        per[c] = dict(precision=round(pr, 4), recall=round(rc, 4), f1=round(2 * pr * rc / (pr + rc) if pr + rc else 0.0, 4),
                      support=tp + fn)
    present = [c for c in LABELS if per[c]['support']]
    out['per_class'] = per
    out['macro_f1'] = round(sum(per[c]['f1'] for c in present) / len(present), 4) if present else None
    out['balanced_accuracy'] = round(sum(per[c]['recall'] for c in present) / len(present), 4) if present else None
    out['accuracy'] = round(sum(conf[(c, c)] for c in LABELS) / n, 4) if n else None
    ne = [p for g, p in zip(gold, pred) if g == 'not_established']
    out['not_established_as_contradicted'] = [sum(p == 'contradicted' for p in ne), len(ne)]
    out['not_established_as_supported'] = [sum(p == 'supported' for p in ne), len(ne)]
    s = [p for g, p in zip(gold, pred) if g == 'supported']
    c = [p for g, p in zip(gold, pred) if g == 'contradicted']
    out['supported_missed'] = [sum(p != 'supported' for p in s), len(s)]
    out['contradicted_missed'] = [sum(p != 'contradicted' for p in c), len(c)]
    out['confusion'] = {f'{g}->{p}': v for (g, p), v in sorted(conf.items())}
    return out


def ece(probs, gold, bins=10):
    """Expected calibration error of the max-probability prediction."""
    tot = 0.0; n = len(gold); bucket = [[] for _ in range(bins)]
    for p, g in zip(probs, gold):
        lab = max(p, key=p.get); conf = p[lab]
        bucket[min(bins - 1, int(conf * bins))].append((conf, lab == g))
    for b in bucket:
        if b: tot += len(b) / n * abs(sum(x for x, _ in b) / len(b) - sum(y for _, y in b) / len(b))
    return round(tot, 4)


class InspectClaim:
    """INSPECT_CLAIM skill: one bounded, scoped judgement over evidence the agent actually read.

    Input:  evidence items the agent has read (with evidence_id, speaker, text, session),
            one candidate claim formed by the system, optional subject/time scope (recorded).
    Output: judgement, probabilities, evidence ids used, per-item support/contradiction when
            requested (conflict detection), unresolved note, cost. No extra LLM call.
    """
    def __init__(self, checkpoint, device='cpu', max_length=512, temperature=1.0, threads=None):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        if threads: torch.set_num_threads(threads)
        self.torch = torch; self.device = device; self.max_length = max_length; self.temperature = temperature
        self.tok = AutoTokenizer.from_pretrained(checkpoint)
        self.model = AutoModelForSequenceClassification.from_pretrained(checkpoint).to(device).eval()
        self.model_id = str(checkpoint)
        cfg = {int(k): v for k, v in self.model.config.id2label.items()}
        self.head = dict(HEAD)
        if len(cfg) == 4:
            if cfg != {0: 'contradiction', 1: 'entailment', 2: 'neutral', 3: 'implied_entailment'}:
                raise ValueError('label mapping changed')
            self.head[3] = IMPLIED
        elif cfg != {0: 'contradiction', 1: 'entailment', 2: 'neutral'}:
            raise ValueError('label mapping changed')

    def _score(self, premise, claim):
        enc = self.tok(premise, claim, truncation=False, return_tensors='pt')
        if enc['input_ids'].shape[1] > self.max_length:
            return None, int(enc['input_ids'].shape[1])
        with self.torch.inference_mode():
            logits = self.model(**{k: v.to(self.device) for k, v in enc.items()}).logits[0].float() / self.temperature
        p = logits.softmax(-1).tolist()
        return {self.head[i]: p[i] for i in range(len(self.head))}, int(enc['input_ids'].shape[1])

    def __call__(self, evidence, claim, *, subject=None, time_scope=None, per_item=False):
        t0 = time.perf_counter()
        ids = [e.get('evidence_id') for e in evidence]
        probs, ntok = self._score(render(evidence), claim) if evidence else (None, 0)
        if not evidence:
            res = dict(judgement='not_established', probabilities=None, unresolved='no evidence read')
        elif probs is None:
            res = dict(judgement=UNPROCESSED, probabilities=None, unresolved=f'input {ntok} tokens > capacity {self.max_length}')
        else:
            lab = max(probs, key=probs.get)
            res = dict(judgement=lab, probabilities={k: round(v, 4) for k, v in probs.items()},
                       unresolved={'not_established': 'visible evidence does not settle the claim',
                                   IMPLIED: 'suggested by context but not stated; not a confirmed fact'}.get(lab))
        items = None; conflict = None
        if per_item and evidence and res['judgement'] != UNPROCESSED:
            items = []
            for e in evidence:
                p, _ = self._score(render([e]), claim)
                items.append(dict(evidence_id=e.get('evidence_id'), judgement=None if p is None else max(p, key=p.get)))
            js = {i['judgement'] for i in items}
            if {'supported', 'contradicted'} <= js:
                conflict = dict(supporting=[i['evidence_id'] for i in items if i['judgement'] == 'supported'],
                                contradicting=[i['evidence_id'] for i in items if i['judgement'] == 'contradicted'])
        return dict(skill='INSPECT_CLAIM', claim=claim, subject=subject, time_scope=time_scope, evidence_ids=ids,
                    **res, per_item=items, conflict=conflict, model=self.model_id,
                    cost=dict(seconds=round(time.perf_counter() - t0, 4), input_tokens=ntok,
                              model_calls=1 + (len(evidence) if items is not None else 0), llm_calls=0))


def revise(entry, result):
    """Working-memory update after an INSPECT_CLAIM call. Keeps the history; never deletes.

    A change of judgement is recorded as a revision of *our understanding* given more
    evidence. It does not assert that the user's real state changed; time-scoped claims
    carry their own scope. Conflicts stay visible.
    """
    entry = dict(entry) if entry else dict(claim=result['claim'], judgement=None, history=[])
    prev = entry.get('judgement')
    entry['history'] = list(entry.get('history', [])) + [dict(judgement=result['judgement'],
                                                              evidence_ids=result['evidence_ids'], conflict=result['conflict'])]
    entry['transition'] = None if prev is None or prev == result['judgement'] else f"{prev}->{result['judgement']}"
    entry['judgement'] = result['judgement']; entry['evidence_ids'] = result['evidence_ids']
    entry['conflict'] = result['conflict']
    return entry
