"""INSPECT_CLAIM as an internal Agent skill over the GE2/GSWS legal observation (candidate).

Boundary (unchanged frozen GE2/GSWS code is only *read*):
  - evidence comes from journal.event_understanding.evidence_input(observation), i.e. the
    current visible dialogue plus history the agent actually read; unread IDs are refused;
  - the claim must be formed by the running system (controller action or Memory Writer
    candidate); this module never invents or repairs claims;
  - an external case (situation C) is never evidence about the current user;
  - the skill is one local classifier call (no LLM call); the Working Memory update is an
    internal bookkeeping step, not another model call.
Output is a scoped tool result, not a verified fact and not a reward.
"""
from __future__ import annotations

from . import identity as I
from .evidence_state import UNPROCESSED, revise

PROTOCOL = 'semcap-inspect-claim-v1'
SUBJECTS = ('user', 'supporter', 'third_party', 'unknown')
TIME_SCOPES = ('as_of_latest_evidence', 'at_report_time')
ACTION_FIELDS = {'action', 'claim', 'evidence_ids', 'subject', 'time_scope'}


def parse_action(action, readable_ids):
    """Validate a controller-proposed INSPECT_CLAIM action against what was actually read."""
    if type(action) is not dict or set(action) != ACTION_FIELDS or action['action'] != 'INSPECT_CLAIM':
        raise ValueError('INSPECT_CLAIM fields')
    c = action['claim']
    if type(c) is not str or not c.strip() or len(c) > 400 or '\n' in c:
        raise ValueError('claim must be one short sentence')
    ids = action['evidence_ids']
    if type(ids) is not list or not 1 <= len(ids) <= 16 or len(set(ids)) != len(ids):
        raise ValueError('evidence_ids list')
    unread = [i for i in ids if i not in readable_ids]
    if unread:
        raise ValueError(f'unread evidence requested: {unread}')
    if action['subject'] not in SUBJECTS or action['time_scope'] not in TIME_SCOPES:
        raise ValueError('subject/time_scope enum')
    return action


def evidence_items(visible, evidence_ids):
    """Order selected legal items chronologically by report time; current dialogue last.
    Session numbers are host-derived from report times (deterministic), not inferred."""
    by_id = {e['evidence_id']: e for e in visible}
    chosen = [by_id[i] for i in evidence_ids]
    def key(e):
        return (1 if e['origin'] == 'current_visible' else 0, str(e.get('reported_at')))
    times = sorted({key(e) for e in chosen})
    rank = {t: n + 1 for n, t in enumerate(times)}
    order = {i: n for n, i in enumerate(evidence_ids)}
    chosen.sort(key=lambda e: (key(e), order[e['evidence_id']]))
    return [dict(evidence_id=e['evidence_id'], speaker=e['speaker'], text=e['text'], session=rank[key(e)])
            for e in chosen]


class InspectClaimSkill:
    def __init__(self, inspector, situation):
        if situation not in I.SITUATIONS:
            raise ValueError('identity situation required')
        self.inspector = inspector; self.situation = situation

    def invoke(self, visible, action, working_memory):
        """visible: evidence_input(observation) list. Returns (result, new_wm, trace)."""
        readable = {e['evidence_id'] for e in visible}
        act = parse_action(action, readable)
        before = working_memory.get(act['claim'])
        by_id = {e['evidence_id']: e for e in visible}
        # Per-item source isolation (v2): an item tagged as an external case never counts as
        # evidence about the current user, even when it is mixed into the user's history.
        external = [i for i in act['evidence_ids'] if by_id[i].get('situation') == I.EXTERNAL_CASE]
        user_ids = [i for i in act['evidence_ids'] if i not in external]
        if self.situation == I.EXTERNAL_CASE or not user_ids:
            result = dict(skill='INSPECT_CLAIM', claim=act['claim'], judgement=UNPROCESSED, evidence_ids=act['evidence_ids'],
                          unresolved='external case is not evidence about the current user', conflict=None,
                          probabilities=None, per_item=None, cost=dict(model_calls=0, llm_calls=0, seconds=0.0))
        else:
            items = evidence_items(visible, user_ids)
            result = self.inspector(items, act['claim'], subject=act['subject'], time_scope=act['time_scope'],
                                    per_item=len(items) > 1)
        result = dict(result, excluded_external_ids=external)
        wm = dict(working_memory)
        if result['judgement'] != UNPROCESSED:
            wm[act['claim']] = revise(before, result)
        trace = dict(protocol=PROTOCOL, situation=self.situation, action=act,
                     before=None if before is None else before.get('judgement'), result_judgement=result['judgement'],
                     after=wm.get(act['claim'], {}).get('judgement'),
                     transition=wm.get(act['claim'], {}).get('transition'), conflict=result.get('conflict'),
                     cost=result['cost'], status='tool_result_not_verified_fact', formal_reward=None)
        return result, wm, trace


def generator_note(working_memory, max_items=6):
    """Concise Working Memory projection for the Generator (no structured JSON dump)."""
    lines = []
    for claim, e in list(working_memory.items())[:max_items]:
        j = e['judgement']; ids = ', '.join(map(str, e.get('evidence_ids') or []))
        c = e.get('conflict')
        if c and c.get('kind') in ('cross_session_difference', 'change_over_time'):
            later = 'later records go against it' if c['later_side'] == 'contradicting' else 'later records support it'
            lines.append(f'- "{claim}": earlier and later reports differ ({later}: {", ".join(c[c["later_side"]])}); '
                         'this may be a change over time or a conflict between reports; do not decide which.')
        elif c:
            lines.append(f'- "{claim}": the records conflict ({", ".join(c["supporting"])} vs '
                         f'{", ".join(c["contradicting"])}); do not resolve it yourself.')
        elif j == 'supported':
            lines.append(f'- "{claim}": supported by what the user/records said ({ids}).')
        elif j == 'implied':
            lines.append(f'- "{claim}": only implied by the records ({ids}), not stated; treat as tentative.')
        elif j == 'contradicted':
            lines.append(f'- "{claim}": contradicted by the records ({ids}).')
        else:
            lines.append(f'- "{claim}": not established by the records read so far; do not assume it happened or not.')
    if not lines:
        return ''
    return ('Checked statements (from records you have read; tool results, not verified facts):\n' + '\n'.join(lines))
