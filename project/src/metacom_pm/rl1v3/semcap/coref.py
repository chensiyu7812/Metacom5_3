"""Speaker-anchored coreference (Maverick) for dialogue evidence.

Division of labour:
  * host (deterministic): who spoke each turn; a first-person singular pronoun in
    a turn by X refers to X. This anchors clusters to known participants.
  * Maverick (learned): links other mentions to those clusters (e.g. "you"/"your"
    in the supporter's turn -> the seeker; "my boyfriend" ... "he") and builds
    third-party chains. Unanchored clusters stay unresolved (generic "you" etc.).

Output is a candidate entity view, not a verified fact. Gold mentions/clusters are
never inputs. Model: sapienzanlp/maverick-mes-ontonotes (CC BY-NC-SA 4.0; research use).
"""
from __future__ import annotations

import re
import time

TOKEN = re.compile(r"\w+(?:'\w+)?|[^\w\s]")
FIRST = {'i', 'me', 'my', 'mine', 'myself', "i'm", "i've", "i'd", "i'll"}
SECOND = {'you', 'your', 'yours', 'yourself', "you're", "you've", "you'd", "you'll"}
POSSESSIVE = {'my', 'mine', 'your', 'yours'}
NAME = {'seeker': 'the seeker', 'supporter': 'the supporter'}
OTHER = {'seeker': 'supporter', 'supporter': 'seeker'}


class SpeakerCoref:
    def __init__(self, checkpoint, device='cpu'):
        from maverick import Maverick
        t0 = time.monotonic_ns()
        self.model = Maverick(hf_name_or_path=checkpoint, device=device)
        self.load_ns = time.monotonic_ns() - t0

    def analyse(self, evidence):
        start = time.monotonic_ns()
        toks = [TOKEN.findall(e['text']) or ['.'] for e in evidence]
        spk = [[e['speaker']] * len(t) for e, t in zip(evidence, toks)]
        out = self.model.predict(toks, speakers=spk)
        where = []  # flat token index -> (turn, local index)
        for ti, t in enumerate(toks):
            where.extend((ti, k) for k in range(len(t)))
        clusters = []
        for offsets in out['clusters_token_offsets']:
            mentions = []
            for s, e in offsets:
                ti, k0 = where[s]; _, k1 = where[e]
                mentions.append(dict(turn=ti, start=k0, end=k1, text=' '.join(toks[ti][k0:k1 + 1]),
                                     speaker=evidence[ti]['speaker']))
            anchors = {m['speaker'] for m in mentions if m['start'] == m['end'] and m['text'].lower() in FIRST}
            entity = next(iter(anchors)) if len(anchors) == 1 else ('conflict' if anchors else None)
            clusters.append(dict(entity=entity, mentions=mentions))
        return dict(tokens=toks, clusters=clusters, elapsed_ns=time.monotonic_ns() - start)

    @staticmethod
    def resolve_person_pronouns(evidence, analysis):
        """Rewrite single-token I/you mentions whose cluster is anchored to a participant
        into explicit participant names; everything else is left verbatim."""
        toks = [list(t) for t in analysis['tokens']]
        changed = 0
        for c in analysis['clusters']:
            if c['entity'] not in NAME:
                continue
            for m in c['mentions']:
                w = m['text'].lower()
                if m['start'] != m['end'] or w not in FIRST | SECOND:
                    continue
                name = NAME[c['entity']]
                toks[m['turn']][m['start']] = name + "'s" if w in POSSESSIVE else name
                changed += 1
        resolved = []
        for e, t in zip(evidence, toks):
            text = re.sub(r"\s+([.,!?;:')\]])", r'\1', ' '.join(t))
            resolved.append(dict(e, text=text))
        return resolved, changed

    @staticmethod
    def binding_agreement(evidence, analysis):
        """Compare anchored clusters with the deterministic 2-party reading of I/you
        (I in X's turn = X; you in X's turn = other speaker; generic 'you' is a known
        exception, so disagreement is a diagnostic, not proof of error)."""
        agree = disagree = 0; conflicts = 0
        for c in analysis['clusters']:
            if c['entity'] == 'conflict':
                conflicts += 1; continue
            if c['entity'] not in NAME:
                continue
            for m in c['mentions']:
                w = m['text'].lower()
                if m['start'] != m['end']:
                    continue
                if w in FIRST:
                    exp = m['speaker']
                elif w in SECOND:
                    exp = OTHER.get(m['speaker'])
                else:
                    continue
                agree += exp == c['entity']; disagree += exp != c['entity']
        return dict(agree=agree, disagree=disagree, merged_speaker_clusters=conflicts)
