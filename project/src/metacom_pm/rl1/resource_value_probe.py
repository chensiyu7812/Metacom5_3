"""Source-preserving interventions for a bounded resource-value diagnostic.

These are offline experiment materials, not PM observations or reward labels.
"""
from dataclasses import replace
import json

from .schema import digest

VERSION = 'pmrl1-resource-value-probe-v1'


def match_session(item, evidence):
    if item.head != 'MS':
        raise ValueError('complete MS required')
    raw = json.loads(item.content)['full_source_conversation']
    matches = [s for s in evidence['legal_past_sessions']
               if s['date'] == item.reported_at and
               '\n'.join(t['role'] + ': ' + t['text'] for t in s['turns']) == raw]
    if len(matches) != 1:
        raise ValueError('exact complete legal session not uniquely bound')
    if item.reported_at > evidence['current_date']:
        raise ValueError('future session')
    return matches[0]


def turn_layout(item, evidence):
    """Change representation only; reconstruct the complete original verbatim."""
    session = match_session(item, evidence)
    turns = [[i, t['role'], t['text']] for i, t in enumerate(session['turns'])]
    body = dict(schema=VERSION, kind='MS', reported_at=item.reported_at,
                source_scope='One complete strictly-past session; no inferred facts.',
                turn_fields=['turn_index', 'speaker', 'text'], turns=turns,
                omitted_turns=0, summary=None)
    content = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    assert '\n'.join(s + ': ' + t for _, s, t in turns) == json.loads(item.content)['full_source_conversation']
    changed = replace(item, content=content,
                      source_identity=digest(dict(original=item.identity, body=body)))
    return changed, dict(original=item.identity, variant=changed.identity,
                         session=session['id'], turns=len(turns), omitted_turns=0,
                         verbatim_text_and_speakers_preserved=True,
                         helpfulness=None, reward=None)
