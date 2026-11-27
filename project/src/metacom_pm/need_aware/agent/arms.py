"""Four controlled NAA input conditions over one shared rendering contract.

  A recency_baseline -- most recent pre-cutoff records packed contiguously into the common
                        evidence budget: a recent-history window, NOT a no-memory condition
                        and never the whole history.
  B strong_fixed_rag -- fixed retrieval over the same legal history, same budget. The chosen
                        dense user_only@8192 delivers nearly all USER statements but no
                        assistant reference turns: user-statement coverage is not complete
                        evidence coverage.
  C direct_evidence  -- A's located Direct source coordinates (diagnostic only; the reader
                        sees source text, never the answer or why it was chosen).
  D evidence_state   -- exactly C's units and text + deterministic state projection.

Same system prompt, same final-turn layout and same decode for every arm and model.
MCQ options appear only in the final instruction, never in retrieval or the writer.
"""
from __future__ import annotations

from ..data.prompts import RECALL_SUFFIX, instruction
from ..memory import reader as R
from ...rl1v3.semcap import identity as I
from .retrieval import query_text, recency

ARMS = ('A', 'B', 'C', 'D')
ARM_NAMES = {'A': 'recency_baseline', 'B': 'strong_fixed_rag', 'C': 'direct_evidence', 'D': 'evidence_state'}
VIEW = {'A': 'raw', 'B': 'raw', 'C': 'raw', 'D': 'state'}
PROMPT_VERSION = 'naa-arms-prompt-v2'
BASE_SYSTEM = ('You are a helpful AI assistant continuing a long-running conversation with this user. '
               'Answer the user\'s current request directly and helpfully.')
RENDER_NOTE = ('Official PersonaMem-v2 MCQ instruction text is used verbatim, but placed at the end of the final '
               'user turn because native chat templates (Qwen3.5) reject a trailing system message.')


def system_prompt(situation):
    return I.system_prompt(BASE_SYSTEM, situation)


def final_user_turn(task, evidence_block):
    text = evidence_block + '\n\nCurrent request from the user:\n' + task.user_query + RECALL_SUFFIX
    if task.task_mode == 'mcq':
        text += '\n\n' + instruction(task.options)
    elif task.options:
        raise ValueError('generation task carries options')
    return text


def messages(task, store, evidence_block):
    return [dict(role='system', content=system_prompt(store.situation)),
            *[dict(m) for m in task.current_messages],
            dict(role='user', content=final_user_turn(task, evidence_block))]


class NotEvaluable(Exception):
    pass


def select_units(arm, task, store, *, index=None, query_vector=None, direct_ids=None,
                 count_tokens, budget):
    if arm == 'A':
        return R.pack(recency(store), count_tokens, budget, contiguous=True)
    if arm == 'B':
        ranked = index.rank(query_text(task), query_vector=query_vector)
        return R.pack(ranked, count_tokens, budget)
    if arm in ('C', 'D'):
        if direct_ids is None:
            raise NotEvaluable('direct evidence not located (diagnostic not_evaluable)')
        units = store.by_id()
        missing = [x for x in direct_ids if x not in units]
        if missing:
            # e.g. a Direct span that is the excluded system profile: never delivered.
            raise NotEvaluable('direct span not a deliverable memory unit: ' + ','.join(missing))
        chosen = sorted((units[x] for x in direct_ids), key=lambda u: u.order)
        packed = R.pack(chosen, count_tokens, budget)
        if packed.skipped_over_budget:
            raise NotEvaluable('direct evidence exceeds common evidence budget')
        return packed
    raise ValueError('unknown arm')


def build(arm, task, store, packed):
    block = R.render(list(packed.units), VIEW[arm])
    return messages(task, store, block), R.trace(packed, VIEW[arm])
