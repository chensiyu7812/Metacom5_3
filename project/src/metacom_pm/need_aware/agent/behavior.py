"""WP4 same-evidence behaviour conditions (MASTER_PLAN v1.1 section 5.3, revised 2026-11-28).

  U0       original G + the fixed legal evidence delivery
  U1       U0 + a deterministic Reglos-style rule layer (arXiv 2611.06049) over the SAME delivered records
  U1+      U1 + holder / served-person matching (whom the request is for vs whose preference a record states)
  NoMem    diagnostic: the same request with no records (does an arm use history at all?)
  OptOnly  diagnostic: the four options alone, no request and no records (option-style bias)
  U2       U0 input, generator = the same base G after ordinary reply-level SFT (LoRA)  -> generator_id
  U3       U0 input, generator = same data/budget + reply-level ranking supervision   -> generator_id

Same-evidence rule: U0/U1/U1+/U2/U3 see exactly the delivered units. The rule layers read
nothing else -- forget requests, change statements and third-party mentions are taken only
from those units (no store-wide tombstone scan). Nothing is ever withheld: the 2026-11-28
decision forbids deleting evidence because a third-party cue ("my friend") appears.
The Reglos silence mechanism survives only as ``reglos_silence_view``, a historical
system-level reference that also reads the whole legal store and therefore is NOT a
same-evidence condition.

U1 is an adaptation, not a reproduction: Reglos gets ownership labels and forget links from
LLM calls; here only the writer's deterministic lexical signals are used. U1+ is the simple,
competitive beneficiary baseline the decision asks for: a lexical cue for whom the request is
for (a named person in the request, otherwise the user), the holder hint on every record that
mentions another person, and one matching rule. No model call, no fitted classifier.
"""
from __future__ import annotations

from ..data import short_protocol as SP
from ..memory import reader as R
from ..memory.writer import _FORGET, _OTHER, _UPDATE, link_forget_requests
from . import arms as WP2
from . import arms_wp3 as W3
from .reply_protocol import U1 as RESPONSE_U1, U1_PLUS as RESPONSE_U1_PLUS

CONDITIONS = ('U0', 'U1', 'U1+', 'NoMem', 'OptOnly', 'U2', 'U3')
W40_CONDITIONS = ('U0', 'U1', 'U1+', 'NoMem', 'OptOnly')       # revised W4-0 (base G only)
SAME_EVIDENCE = ('U0', 'U1', 'U1+', 'U2', 'U3')
BEHAVIOR_VERSION = 'naa-wp4-behavior-v4'
BASE_GENERATOR = 'base'

U1_POLICY = 'Memory-use policy (applies to the records below):\n' + RESPONSE_U1
U1_PLUS_RULES = RESPONSE_U1_PLUS
SILENCE_NOTE = ('No earlier records are shown for this request: the only user records available are tied to a '
                'request to forget or describe another person.')
OPTIONS_ONLY_SYSTEM = 'You are a helpful assistant.'


def policy(plus):
    return U1_POLICY + ('\n' + U1_PLUS_RULES if plus else '')


def person_cue(text):
    """Lexical third-party phrase (the writer's own regex), e.g. 'my sister'; None when absent."""
    m = _OTHER.search(text or '')
    return ' '.join(m.group(0).split()).lower() if m else None


def served_line(query):
    who = person_cue(query)
    return ('Lexical person cue: ' + (who if who else 'none detected') +
            '. This is not a beneficiary label. Infer whom the request serves from its full meaning; '
            'mentioning someone does not mean the request is for them, and names may lack a lexical cue.')


def _marks(u, *, linked, plus):
    marks = []
    if u.unit_id in linked:
        marks.append('possible lexical link to a later forget request; verify the referent and scope before applying it')
    if 'forget_request' in u.constraint_candidates:
        marks.append('a request to forget or not use something; it applies only to what it names')
    if 'explicit_change_statement' in u.constraint_candidates:
        marks.append('states a change; an earlier conflicting preference on the same matter may no longer be true')
    if u.is_current_user and u.third_party_mention:
        who = person_cue(u.original_text) if plus else None
        marks.append(f'mentions {who}; a preference here may be {who}\'s, not the user\'s' if who
                     else 'mentions another person; may describe them, not the user')
    if not u.is_current_user:
        marks.append("assistant reply, not the user's statement")
    return marks


def rule_view(units, *, query='', plus=False):
    """(block, trace) for U1 / U1+ over exactly ``units``; every unit stays shown."""
    units = list(units)
    links = link_forget_requests(units)                      # delivered units only (same-evidence)
    linked = {x['target_unit_id'] for x in links if x['target_unit_id']}
    lines = [policy(plus)]
    if plus:
        lines.append(served_line(query))
    if units:
        r = R.refs(units)
        lines.append(R.RAW_HEADER)
        for u in units:
            m = _marks(u, linked=linked, plus=plus)
            lines.append(R.record_line(r[u.unit_id], u) + (f" [{'; '.join(m)}]" if m else ''))
    else:
        lines.append(R.EMPTY_BLOCK)
    trace = dict(rule='U1+' if plus else 'U1', shown_ids=[u.unit_id for u in units], withheld=0,
                 forget_requests=sum('forget_request' in u.constraint_candidates for u in units),
                 forget_marked=len(linked), third_party_marked=sum(bool(u.is_current_user and u.third_party_mention)
                                                                   for u in units),
                 request_person_cue=person_cue(query) if plus else None)
    return '\n'.join(lines), trace


def reglos_silence_view(units, store):
    """HISTORICAL reference only (old U1): store-wide tombstones + silence. Not same-evidence."""
    links = link_forget_requests(store.units)
    forget_targets = {x['target_unit_id'] for x in links if x['target_unit_id']}
    requests = [u for u in store.units if 'forget_request' in u.constraint_candidates]
    user = [u for u in units if u.is_current_user]
    tied = [u for u in user if u.unit_id in forget_targets or 'forget_request' in u.constraint_candidates
            or u.third_party_mention]
    silence = bool(user) and len(tied) == len(user)
    shown = [] if silence else list(units)
    lines = [U1_POLICY]
    if requests:
        lines.append('Requests by the user to forget or not use something (each applies only to what it names):')
        lines += [f"- (message {u.order}) {' '.join(u.original_text.split())}" for u in requests]
    if silence:
        lines.append(SILENCE_NOTE)
    elif shown:
        r = R.refs(shown)
        lines.append(R.RAW_HEADER)
        lines += [R.record_line(r[u.unit_id], u) + (f" [{'; '.join(m)}]" if (m := _marks(
            u, linked=forget_targets, plus=False)) else '') for u in shown]
    else:
        lines.append(R.EMPTY_BLOCK)
    return '\n'.join(lines), dict(rule='reglos_silence_historical', silence=silence, same_evidence=False,
                                  shown_ids=[u.unit_id for u in shown], store_wide_forget_requests=len(requests))


# ------------------------------------------------------------------ W4-0 / W4-E MCQ (naa-short-mcq-v1, 64 tokens)
def mcq_messages(condition, task, store, packed):
    """Messages + trace for one W4 MCQ condition, in the WP3 layout (same system prompt, current turns,
    "Current request" + recall suffix + A's short instruction). U2/U3 return U0's exact messages."""
    if condition not in CONDITIONS:
        raise ValueError('unknown WP4 condition ' + condition)
    units = list(packed.units) if packed is not None else []
    trace = dict(version=BEHAVIOR_VERSION, condition=condition, protocol=SP.PROTOCOL)
    if condition == 'OptOnly':
        msgs = [dict(role='system', content=OPTIONS_ONLY_SYSTEM), dict(role='user', content=SP.instruction(task.options))]
        return msgs, dict(trace, delivered_ids=[], evidence_tokens=0, query_shown=False)
    if condition == 'NoMem':
        return W3.messages(task, store, R.EMPTY_BLOCK), dict(trace, delivered_ids=[], evidence_tokens=0)
    trace.update(delivered_ids=[u.unit_id for u in units], evidence_tokens=packed.tokens)
    if condition in ('U1', 'U1+'):
        block, extra = rule_view(units, query=task.user_query, plus=condition == 'U1+')
        trace.update(extra)
    else:
        block = R.render(units, 'raw')
    return W3.messages(task, store, block), trace


# ------------------------------------------------------------------ open-reply rows (A's pre-rendered layout)
def _cues(text):
    return dict(third_party=bool(_OTHER.search(text)), forget=bool(_FORGET.search(text)), change=bool(_UPDATE.search(text)))


def u1_messages(messages, *, plus=False):
    """U1 / U1+ over a pre-rendered row: [system, evidence turn(s)..., request]. Nothing is withheld."""
    if len(messages) < 2 or messages[0]['role'] != 'system' or messages[-1]['role'] != 'user':
        raise ValueError('expected system + evidence turns + final request')
    evidence = messages[1:-1]
    query = messages[-1]['content']
    sys_text = messages[0]['content'] + '\n\n' + policy(plus) + ('\n' + served_line(query) if plus else '')
    out = [dict(role='system', content=sys_text)]
    cues = []
    for m in evidence:
        c = _cues(m['content']) if m['role'] == 'user' else dict(third_party=False, forget=False, change=False)
        cues.append(c)
        marks = []
        if c['forget']:
            marks.append('a request to forget or not use something; it applies only to what it names')
        if c['change']:
            marks.append('states a change; an earlier conflicting preference on the same matter may no longer be true')
        if c['third_party']:
            who = person_cue(m['content']) if plus else None
            marks.append(f'mentions {who}; a preference here may be {who}\'s, not the user\'s' if who
                         else 'mentions another person; may describe them, not the user')
        out.append(dict(role=m['role'], content=m['content'] + (f" [{'; '.join(marks)}]" if marks else '')))
    out.append(dict(messages[-1]))
    return out, dict(version=BEHAVIOR_VERSION, condition='U1+' if plus else 'U1', withheld=0,
                     evidence_turns=len(evidence),
                     cue_counts={k: sum(c[k] for c in cues) for k in ('third_party', 'forget', 'change')})


def natural_messages(condition, task, store, packed, open_system):
    """Natural open tasks in the layout of A's constructed rows: one system prompt (A's open JSON contract),
    one evidence turn (B's frozen delivery), one request turn (no recall suffix)."""
    units = list(packed.units)
    if condition in ('U1', 'U1+'):
        block = rule_view(units, query=task.user_query, plus=condition == 'U1+')[0]
        head = policy(condition == 'U1+') + '\n'
        block = block[len(head):] if block.startswith(head) else block   # policy lives in the system turn
        system = open_system + '\n\n' + policy(condition == 'U1+')
    elif condition == 'NoMem':
        block, system = R.EMPTY_BLOCK, open_system
    else:
        block, system = R.render(units, 'raw'), open_system
    return [dict(role='system', content=system), *[dict(m) for m in task.current_messages],
            dict(role='user', content=block), dict(role='user', content=task.user_query)]


def build(condition, task, store, packed, *, recall_suffix=False, generator_id=BASE_GENERATOR):
    """WP2-layout messages + trace (training renderer). U0/U2/U3 share the input; only generator_id differs."""
    if condition not in CONDITIONS:
        raise ValueError('unknown WP4 condition')
    if condition in ('U2', 'U3') and generator_id == BASE_GENERATOR:
        raise ValueError(condition + ' requires an adapted generator identity')
    if condition not in ('U2', 'U3') and generator_id != BASE_GENERATOR:
        raise ValueError(condition + ' runs on the original generator')
    units = list(packed.units)
    trace = dict(version=BEHAVIOR_VERSION, condition=condition, generator_id=generator_id,
                 recall_suffix=recall_suffix, delivered_ids=[u.unit_id for u in units], evidence_tokens=packed.tokens)
    if condition in ('U1', 'U1+'):
        block, extra = rule_view(units, query=task.user_query, plus=condition == 'U1+')
        trace.update(extra)
    elif condition == 'NoMem':
        block = R.EMPTY_BLOCK
    else:
        block = R.render(units, 'raw')
    text = block + '\n\nCurrent request from the user:\n' + task.user_query + (WP2.RECALL_SUFFIX if recall_suffix else '')
    return [dict(role='system', content=WP2.system_prompt(store.situation)), *[dict(m) for m in task.current_messages],
            dict(role='user', content=text)], trace
