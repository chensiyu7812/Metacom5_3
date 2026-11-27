"""Source-bound claim-support capability: existing NLI vs MiniCheck, CPU.

Semantic Capability Layer component. Input is only the legal visible evidence
projection (evidence_id/speaker/text/reported_at/origin) plus one candidate
proposition. Output is a three-way *support* reading:

  supported     the cited evidence states the proposition
  contradicted  the cited evidence states its negation (NLI contradiction only)
  unknown       neither; absence of evidence is NOT negation

MiniCheck is a binary grounding checker (supported / not supported); its
"not supported" is never mapped to "contradicted" or to "did not happen".
Speaker identity is host metadata: the `attributed` renderer states each
speaker deterministically ("The seeker said: ...") so the model is not asked
to guess who "I" is. Neither renderer receives labels, gold or future turns.
"""
from __future__ import annotations

import time

ALLOWED = {'evidence_id', 'text', 'speaker', 'reported_at', 'origin'}
SPEAKER = {'seeker': 'the seeker (the user)', 'supporter': 'the supporter'}


def _check(evidence):
    if any(set(e) != ALLOWED for e in evidence):
        raise ValueError('only legal source projection accepted')
    return evidence


def render_tagged(evidence):
    """Exact premise format of event_understanding.inspect (existing NLI run)."""
    return '\n'.join(f"[{e['evidence_id']}] ({e['speaker']}; report {e['reported_at']}) {e['text']}"
                     for e in _check(evidence))


def render_attributed(evidence):
    """Deterministic speaker attribution from host metadata; no semantic rewriting."""
    lines = []
    for e in _check(evidence):
        who = SPEAKER.get(e['speaker'], e['speaker'])
        when = '' if e['origin'] == 'current_visible' or not e['reported_at'] else f"In a session reported on {e['reported_at']}, "
        lines.append(f"{when}{who[0].upper() + who[1:] if not when else who} said: \"{' '.join(e['text'].split())}\"")
    return '\n'.join(lines)


RENDERERS = {'tagged': render_tagged, 'attributed': render_attributed}


class MiniCheckFT5:
    """Minimal adapter of the official MiniCheck-Flan-T5-Large inference.

    Mirrors Liyan06/MiniCheck inference.py: input 'predict: ' + doc + '</s>' + claim,
    one decoder step from id 0, softmax over token ids [3 (no), 209 (yes)], max over
    ~500-word document chunks, supported iff prob > 0.5 (official default, not tuned).
    Chunks split on evidence-line boundaries instead of nltk sentences.
    """
    CHUNK_WORDS = 500

    def __init__(self, snapshot, threads=None):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        self.torch = torch
        if threads:
            torch.set_num_threads(threads)
        t0 = time.monotonic_ns()
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(snapshot, local_files_only=True).float().eval()
        self.load_ns = time.monotonic_ns() - t0

    def _chunks(self, doc):
        cur, n = [], 0
        for line in doc.split('\n'):
            w = len(line.split())
            if cur and n + w > self.CHUNK_WORDS:
                yield '\n'.join(cur); cur, n = [], 0
            cur.append(line); n += w
        if cur:
            yield '\n'.join(cur)

    def score(self, doc, claim):
        start = time.monotonic_ns()
        probs, lengths = [], []
        for chunk in self._chunks(doc):
            enc = self.tokenizer('predict: ' + chunk + self.tokenizer.eos_token + claim,
                                 max_length=2048, truncation=True, return_tensors='pt')
            lengths.append(int(enc['input_ids'].shape[1]))
            with self.torch.inference_mode():
                logits = self.model(**enc, decoder_input_ids=self.torch.zeros((1, 1), dtype=self.torch.long)).logits[:, 0]
            probs.append(float(logits[:, [3, 209]].softmax(-1)[0, 1]))
        p = max(probs)
        return dict(model='MiniCheck-Flan-T5-Large', support_prob=p, supported=p > .5, chunks=len(probs),
                    input_tokens=lengths, truncated=any(x >= 2048 for x in lengths),
                    elapsed_ns=time.monotonic_ns() - start)


class DebertaNLI:
    """Same frozen cross-encoder and fixed thresholds as event_understanding.LocalNLIAssistance."""

    def __init__(self, snapshot):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        t0 = time.monotonic_ns()
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(snapshot, local_files_only=True).float().eval()
        self.load_ns = time.monotonic_ns() - t0
        if {int(k): v.lower() for k, v in self.model.config.id2label.items()} != {0: 'contradiction', 1: 'entailment', 2: 'neutral'}:
            raise ValueError('NLI label mapping changed')

    def score(self, premise, hypothesis):
        start = time.monotonic_ns()
        enc = self.tokenizer(premise, hypothesis, return_tensors='pt', truncation=False)
        n = int(enc['input_ids'].shape[1])
        if n > 512:
            return dict(status='capacity_not_scored', verdict='unknown', input_tokens=n, elapsed_ns=time.monotonic_ns() - start)
        with self.torch.inference_mode():
            c, e, neu = self.model(**enc).logits.softmax(-1)[0].tolist()
        verdict = 'supported' if e >= .8 and c <= .1 else 'contradicted' if c >= .8 and e <= .1 else 'unknown'
        return dict(status='CPU_scored', verdict=verdict, probabilities=dict(contradiction=c, entailment=e, neutral=neu),
                    input_tokens=n, elapsed_ns=time.monotonic_ns() - start)


def combine(minicheck, nli):
    """D: MiniCheck decides support; only an explicit NLI contradiction yields contradicted."""
    if minicheck['supported']:
        return 'supported'
    if nli.get('verdict') == 'contradicted':
        return 'contradicted'
    return 'unknown'


def metrics(rows, key):
    """rows: dicts with 'reference' and prediction under key. Development diagnostics only."""
    labels = ('supported', 'contradicted', 'unknown')
    out = dict(n=len(rows))
    rec = {}
    for lab in labels:
        ref = [r for r in rows if r['reference'] == lab]
        rec[lab] = None if not ref else sum(r[key] == lab for r in ref) / len(ref)
        pred = [r for r in rows if r[key] == lab]
        prec = None if not pred else sum(r['reference'] == lab for r in pred) / len(pred)
        f1 = None if not rec[lab] or not prec else 2 * prec * rec[lab] / (prec + rec[lab])
        out[lab] = dict(reference=len(ref), predicted=len(pred), recall=rec[lab], precision=prec, f1=f1)
    present = [lab for lab in labels if out[lab]['reference']]
    out['balanced_accuracy'] = sum(rec[lab] for lab in present) / len(present)
    out['macro_f1'] = sum((out[lab]['f1'] or 0) for lab in present) / len(present)
    non_sup = [r for r in rows if r['reference'] != 'supported']
    out['false_pass'] = [sum(r[key] == 'supported' for r in non_sup), len(non_sup)]
    unk = [r for r in rows if r['reference'] == 'unknown']
    out['absence_as_negation'] = [sum(r[key] == 'contradicted' for r in unk), len(unk)]
    swaps = [r for r in rows if 'swap' in r['factor']]
    out['subject_swap_false_pass'] = [sum(r[key] == 'supported' for r in swaps), len(swaps)]
    return out


def structured_reporter(proposition):
    """Convert a frozen textual 'The <role> says/reports ...' claim into the structured
    reporter field GSWS claims already carry (`subject`). None when the claim is not a
    self-report; this is format conversion, not semantic inference."""
    for role in ('seeker', 'supporter'):
        for verb in ('says', 'reports'):
            if proposition.startswith(f'The {role} {verb} '):
                return role
    return None


def render_scoped(evidence, reporter):
    """Speaker-scoped evidence: a self-report claim is checked only against the reporter's
    own turns (host-known speaker). Non-self-report claims keep the full attributed view."""
    if reporter is None:
        return render_attributed(evidence)
    own = [e for e in _check(evidence) if e['speaker'] == reporter]
    return render_attributed(own) if own else ''
