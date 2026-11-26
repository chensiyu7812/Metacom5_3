"""Source-bound event inspection, with optional CPU entailment assistance.

This is a capability tool, not a qualified event extractor, natural-quality
judge or reward. It accepts visible evidence and a candidate proposition;
it cannot retrieve hidden history or manufacture an event's completion.
"""
from __future__ import annotations

import re
import time
from typing import Protocol

PROTOCOL = 'gsws-event-evidence-skill-v1'
LABELS = ('CT+', 'PS+', 'PS-', 'CT-', 'Uu')
PROCEDURE = (
    'Locate the candidate event and its exact original speaker/source.',
    'Keep a report of an intention separate from the intended event.',
    'Check subject, negation, modality and action phase separately.',
    'Keep report time separate from event time; do not invent a calendar date.',
    'Check later actually visible updates; do not infer execution from silence.',
    'Return supported, contradicted or unresolved claims; absence is not negation.',
)
CUES = {
    'negation_surface': r"\b(?:not|never|no|without|cannot|didn't|haven't|hasn't|wasn't|couldn't)\b",
    'modal_or_intention_surface': r'\b(?:may|might|could|would|hope|hoping|plan|planned|planning|intend|intended|want|wanted|offer|offered|decided|if)\b',
    'phase_surface': r'\b(?:already|still|yet|started|finished|completed|tried|trying|attempt|stopped|cancelled)\b',
    'time_surface': r'\b(?:today|yesterday|tomorrow|tonight|weekend|recently|later|before|after)\b',
}


def evidence_input(observation):
    """Use the exact GSWS legal-observation projection, never eval sidecars."""
    from .gsws import model_evidence
    visible = model_evidence(observation)
    result = []
    for turn in visible['current_dialogue']:
        result.append(dict(evidence_id=turn['id'], text=turn['text'], speaker=turn['speaker'],
                           reported_at=visible['current_time'], origin='current_visible'))
    for session in visible['history']:
        for turn in session['turns']:
            result.append(dict(evidence_id=turn['id'], text=turn['text'], speaker=turn['speaker'],
                               reported_at=session['reported_at'], origin='actually_read_history'))
    return result


def invoke_from_gsws(observation, *, proposition=None, evidence_ids=None, model=None):
    """Thin GE2/GSWS tool boundary. A proposal cannot fetch new hidden evidence.

    This does not alter any frozen GSWS experiment or select an agent action.
    PM and G may consume the same unqualified tool result in a future experiment.
    """
    from ..io import object_sha256
    visible = evidence_input(observation)
    result = inspect(visible, proposition, evidence_ids, model)
    return dict(protocol=PROTOCOL, observation_sha256=observation['snapshot_sha256'],
        visible_input_sha256=object_sha256(visible), result=result,
        result_sha256=object_sha256(result), status='tool_result_not_verified_fact',
        automatic_memory_write=False, adaptive_invocation_tested=False)


class EntailmentModel(Protocol):
    def score(self, premises: list[str], hypotheses: list[str]): ...


def inspect(evidence, proposition=None, evidence_ids=None, model: EntailmentModel | None = None):
    start = time.monotonic_ns()
    allowed = {'evidence_id', 'text', 'speaker', 'reported_at', 'origin'}
    if any(set(e) != allowed for e in evidence):
        raise ValueError('only source projection accepted; labels/targets are not tool inputs')
    by_id = {e['evidence_id']: e for e in evidence}
    if len(by_id) != len(evidence):
        raise ValueError('ambiguous evidence ID')
    selected = list(by_id) if evidence_ids is None else evidence_ids
    if any(i not in by_id for i in selected):
        raise ValueError('unread evidence requested')
    units = [by_id[i] for i in selected]
    cues = []
    for e in units:
        for kind, pattern in CUES.items():
            for m in re.finditer(pattern, e['text'], flags=re.I):
                cues.append(dict(evidence_id=e['evidence_id'], start_char=m.start(), end_char=m.end(),
                                 quote=m.group(), kind=kind, meaning='surface cue, not a factuality label'))
    result = dict(protocol=PROTOCOL, evidence=units, surface_cues=cues, procedure=list(PROCEDURE),
        factuality='unknown', actor_coreference='unknown', action_stage='unknown', event_time='unknown',
        report_times=[dict(evidence_id=e['evidence_id'], reported_at=e['reported_at']) for e in units],
        proposition=proposition, entailment_assistance=None, semantic_qualified=False, formal_reward=None)
    if model is not None:
        if not proposition or not units:
            raise ValueError('a visible source and explicit candidate proposition are required')
        # A user-question or a supporter suggestion does not become a user assertion.
        premise = '\n'.join(f"[{e['evidence_id']}] ({e['speaker']}; report {e['reported_at']}) {e['text']}" for e in units)
        scored = model.score([premise], [proposition])[0]
        result['entailment_assistance'] = scored
    result['elapsed_ns'] = time.monotonic_ns() - start
    return result


class LocalNLIAssistance:
    """Existing frozen NLI, CPU only. No silent truncation or threshold tuning."""
    def __init__(self, snapshot):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=False).float().to('cpu').eval()
        labels = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        if labels != {0: 'contradiction', 1: 'entailment', 2: 'neutral'}:
            raise ValueError('NLI label mapping changed')

    def score(self, premises, hypotheses):
        result = []
        for premise, hypothesis in zip(premises, hypotheses, strict=True):
            start = time.monotonic_ns()
            tokens = self.tokenizer(premise, hypothesis, return_tensors='pt', truncation=False)
            length = tokens['input_ids'].shape[1]
            if length > 512:
                result.append(dict(status='capacity_not_scored', verdict='unknown', probabilities=None,
                                   input_tokens=length, elapsed_ns=time.monotonic_ns()-start))
                continue
            with self.torch.inference_mode():
                values = self.model(**tokens).logits.softmax(-1)[0].tolist()
            c, e, n = values
            verdict = 'supported' if e >= .8 and c <= .1 else 'contradicted' if c >= .8 and e <= .1 else 'unknown'
            result.append(dict(status='CPU_scored', verdict=verdict, probabilities=dict(contradiction=c,entailment=e,neutral=n),
                input_tokens=length, elapsed_ns=time.monotonic_ns()-start,
                limitation='NLI is not absence detection, temporal qualification, natural quality or reward'))
        return result
