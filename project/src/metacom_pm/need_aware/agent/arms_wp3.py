"""WP3 one-shot strong evidence-supply comparison (MASTER_PLAN v1.1 section 4).

Same legal history, generator, system prompt, identity contract, query, raw rendering
("said by", chronological, complete turns) and short-answer protocol in every arm; only
the delivered evidence (and its budget, the variable under test) differs.

  B0     WP2 B: dense user_only @8192                      historical reference, not the strongest
  B1     same ranking/packing, all roles @8192             full-role availability
  B1s    B1 @1536                                          budget / compaction
  E0     Raw-RAG-style windows + rerank + turn expansion @8192 native cap   strong deployable baseline
  E0s    E0 ranking @1536                                  same-method budget comparison
  C      A's legal Direct coordinates, all kept            diagnostic, not deployable, not an upper bound
  Cn     C unchanged + seeded legal same-owner background to ~8192   length/position/background effect

B1/B1s/E0/E0s differ in content, so their contrasts are not pure token-count effects.
C and Cn are structurally not evaluable when C cannot be located or exceeds its cap;
other arms keep the task. No MCQ option ever enters retrieval, reranking or the writer.
"""
from __future__ import annotations

from ..data.prompts import RECALL_SUFFIX
from ..memory import reader as R
from . import arms as WP2
from . import evidence as EV
from .retrieval import query_text

ARMS = ('B0', 'B1', 'B1s', 'E0', 'E0s', 'C', 'Cn')
ARM_NAMES = {'B0': 'wp2_dense_user_only_8192', 'B1': 'dense_all_roles_8192', 'B1s': 'dense_all_roles_1536',
             'E0': 'rawrag_style_native_8192', 'E0s': 'rawrag_style_compact_1536', 'C': 'direct_diagnostic',
             'Cn': 'direct_plus_seeded_background_8192'}
BUDGET = {'B0': EV.NATIVE_BUDGET, 'B1': EV.NATIVE_BUDGET, 'B1s': EV.COMPACT_BUDGET, 'E0': EV.NATIVE_BUDGET,
          'E0s': EV.COMPACT_BUDGET, 'C': EV.NATIVE_BUDGET, 'Cn': EV.NATIVE_BUDGET}
DEPLOYABLE = {'B0', 'B1', 'B1s', 'E0', 'E0s'}
PROMPT_VERSION = 'naa-wp3-prompt-v1'
SHORT_PROTOCOL = 'naa-mcq-short-v1'          # MODIFIED protocol: never mixed with the official WP2 protocol
SHORT_MAX_NEW_TOKENS = 64
SHORT_NOTE = ('Modified short-answer protocol: same question, option order and legal information as the '
              'official PersonaMem-v2 MCQ, but the reasoning request is replaced by a letter-only answer; '
              'results are labelled modified and never pooled with the official WP2 protocol.')


def short_instruction(options):
    return ('Please choose the best answer from the following options:\n\n'
            + '\n'.join(f"{o['id']}. {o['text']}" for o in options)
            + '\n\nReply with exactly one line in this form, using the letter of the best option and '
              'nothing else (no brackets, no explanation):\nFinal Answer: A')


def final_user_turn(task, evidence_block):
    if task.task_mode != 'mcq':
        raise ValueError('WP3 short-answer protocol is MCQ only')
    return (evidence_block + '\n\nCurrent request from the user:\n' + task.user_query + RECALL_SUFFIX
            + '\n\n' + short_instruction(task.options))


def messages(task, store, evidence_block):
    return [dict(role='system', content=WP2.system_prompt(store.situation)),
            *[dict(m) for m in task.current_messages],
            dict(role='user', content=final_user_turn(task, evidence_block))]


def select(arm, task, store, *, dense_user=None, dense_all=None, query_vector=None, e0_ranked=None,
           direct_ids=None, count_tokens):
    """Return (Packed, extra_trace). e0_ranked: reranked windows (highest first), computed once per task."""
    budget = BUDGET[arm]
    if arm == 'B0':
        return R.pack(dense_user.rank(query_text(task), query_vector=query_vector), count_tokens, budget), {}
    if arm in ('B1', 'B1s'):
        return R.pack(dense_all.rank(query_text(task), query_vector=query_vector), count_tokens, budget), {}
    if arm in ('E0', 'E0s'):
        if e0_ranked is None:
            raise ValueError('E0 ranking missing (run the supply stage first)')
        packed, intervals = EV.pack_windows(e0_ranked, store, count_tokens, budget)
        return packed, dict(intervals=intervals, windows_kept=len(e0_ranked) - len(packed.skipped_over_budget))
    if arm in ('C', 'Cn'):
        c = WP2.select_units('C', task, store, direct_ids=direct_ids, count_tokens=count_tokens, budget=budget)
        if arm == 'C':
            return c, {}
        packed, flags = EV.with_background(c, store, count_tokens, budget, task.task_id)
        return packed, flags
    raise ValueError('unknown WP3 arm')


def build(arm, task, store, packed):
    block = R.render(list(packed.units), 'raw')
    return messages(task, store, block), R.trace(packed, 'raw')
