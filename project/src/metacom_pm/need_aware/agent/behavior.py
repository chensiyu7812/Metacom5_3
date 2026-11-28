"""WP4 same-evidence behaviour conditions (MASTER_PLAN v1.1 section 5.3).

  U0  original G, identical fixed evidence, plain direct reply
  U1  U0 + a deterministic Reglos-style rule layer (arXiv 2611.06049)
  U2  U0 rendering, generator = the same base G after ordinary SFT (LoRA)          -> generator_id
  U3  U0 rendering, generator = same data/budget + paired applicability supervision -> generator_id

U2/U3 differ from U0 only in the generator weights, never in the input: the rendered
messages of U0/U2/U3 are byte-identical for the same task and evidence.

U1 is an *adaptation*, not a reproduction. Reglos obtains ownership labels, supersession
and forget-to-fact matching from LLM calls; NAA adds no online LLM, so U1 uses only the
writer's deterministic signals (speaker, lexical third-party cue, explicit forget requests
with lexical-candidate links, explicit change statements). Implemented Reglos elements:
the memory-use policy placed before the records, forget requests shown as tombstones
(nothing deleted), records marked by those signals, and the silence rule (withhold all
records when every delivered user record is tied to a forget request or only mentions
another person). The policy wording is our paraphrase of the paper's rule list.
"""
from __future__ import annotations

from ..memory import reader as R
from ..memory.writer import link_forget_requests
from . import arms as WP2

CONDITIONS = ('U0', 'U1', 'U2', 'U3')
BEHAVIOR_VERSION = 'naa-wp4-behavior-v1'
BASE_GENERATOR = 'base'

U1_POLICY = (
    'Memory-use policy (applies to the records below):\n'
    "- Use the user's own current preferences when they help with the current request.\n"
    '- The records are incomplete; do not assume that something missing is false.\n'
    '- Never rely on information the user asked you to forget or not to use.\n'
    '- Do not use a preference the user said has changed or is no longer true.\n'
    "- A preference of another person is not the user's preference; use it only when the request is "
    'about or for that person.\n'
    '- Make no assumptions from demographics, and never repeat sensitive identifiers.')
SILENCE_NOTE = ('No earlier records are shown for this request: the only user records available are tied to a '
                'request to forget or describe another person.')


def task_block(task, evidence_block, *, recall_suffix):
    text = evidence_block + '\n\nCurrent request from the user:\n' + task.user_query
    if recall_suffix:
        text += WP2.RECALL_SUFFIX
    return text


def _messages(task, store, user_text):
    return [dict(role='system', content=WP2.system_prompt(store.situation)),
            *[dict(m) for m in task.current_messages], dict(role='user', content=user_text)]


def u1_view(units, store):
    """Return (block, trace) for the Reglos-style rule layer over the SAME delivered units."""
    links = link_forget_requests(store.units)                  # whole legal store, as Reglos tombstones
    forget_targets = {x['target_unit_id'] for x in links if x['target_unit_id']}
    requests = [u for u in store.units if 'forget_request' in u.constraint_candidates]
    user = [u for u in units if u.is_current_user]
    tied = [u for u in user if u.unit_id in forget_targets or 'forget_request' in u.constraint_candidates
            or u.third_party_mention]
    silence = bool(user) and len(tied) == len(user)
    shown = [] if silence else list(units)
    r = R.refs(shown)
    lines = [U1_POLICY]
    if requests:
        lines.append('Requests by the user to forget or not use something (each applies only to what it names):')
        lines += [f"- (message {u.order}) {' '.join(u.original_text.split())}" for u in requests]
    if silence:
        lines.append(SILENCE_NOTE)
    elif shown:
        lines.append(R.RAW_HEADER)
        for u in shown:
            marks = []
            if u.unit_id in forget_targets:
                marks.append('the user later asked not to use this')
            if 'explicit_change_statement' in u.constraint_candidates:
                marks.append('states a change; an earlier conflicting preference on the same matter may no longer be true')
            if u.is_current_user and u.third_party_mention:
                marks.append('mentions another person; may describe them, not the user')
            if not u.is_current_user:
                marks.append("assistant reply, not the user's statement")
            lines.append(R.record_line(r[u.unit_id], u) + (f" [{'; '.join(marks)}]" if marks else ''))
    else:
        lines.append(R.EMPTY_BLOCK)
    trace = dict(silence=silence, forget_requests_listed=len(requests),
                 forget_marked=sum(u.unit_id in forget_targets for u in shown), shown_ids=[u.unit_id for u in shown])
    return '\n'.join(lines), trace


def build(condition, task, store, packed, *, recall_suffix=False, generator_id=BASE_GENERATOR):
    """Messages + trace for one condition. U0/U2/U3 share the input; only generator_id differs."""
    if condition not in CONDITIONS:
        raise ValueError('unknown WP4 condition')
    if condition in ('U2', 'U3') and generator_id == BASE_GENERATOR:
        raise ValueError(condition + ' requires an adapted generator identity')
    if condition in ('U0', 'U1') and generator_id != BASE_GENERATOR:
        raise ValueError(condition + ' runs on the original generator')
    trace = dict(version=BEHAVIOR_VERSION, condition=condition, generator_id=generator_id,
                 recall_suffix=recall_suffix, delivered_ids=[u.unit_id for u in packed.units],
                 evidence_tokens=packed.tokens)
    if condition == 'U1':
        block, extra = u1_view(list(packed.units), store)
        trace.update(extra)
    else:
        block = R.render(list(packed.units), 'raw')
    return _messages(task, store, task_block(task, block, recall_suffix=recall_suffix)), trace
