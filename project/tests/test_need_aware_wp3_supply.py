"""NAA WP3 evidence-supply regression (CPU fixtures, no model): GE2 interval reuse, Raw-RAG-style
windows and whole-window packing, C+noise invariants, arm contract and short-answer protocol."""
import json

import pytest

from metacom_pm.need_aware.agent import arms_wp3 as W3
from metacom_pm.need_aware.agent import evidence as EV
from metacom_pm.need_aware.agent.retrieval import OwnerIndex, RetrievalSpec, query_text
from metacom_pm.need_aware.evaluation.mcq import extract_final_answer
from metacom_pm.need_aware.memory import reader as R
from metacom_pm.need_aware.memory.writer import MemoryWriter, write_for_task
from metacom_pm.rl1v3.journal.ge2_retrieval import union_intervals

from test_need_aware_agent import OPTIONS, runtime  # shared legal fixture


class WordTok:
    """Whitespace 'tokenizer' with the HF encode/decode surface used by evidence.windows."""
    def __init__(self):
        self.vocab, self.inv = {}, []

    def encode(self, text, add_special_tokens=False):
        out = []
        for w in text.split():
            if w not in self.vocab:
                self.vocab[w] = len(self.inv); self.inv.append(w)
            out.append(self.vocab[w])
        return out

    def decode(self, ids):
        return ' '.join(self.inv[i] for i in ids)


def count(text):
    return len(text.split())


@pytest.fixture
def setup(tmp_path):
    task, resolver = runtime(tmp_path)
    return task, write_for_task(resolver, MemoryWriter(), task)


def test_windows_link_every_token_to_complete_source_turns(setup):
    _, store = setup
    ws = EV.windows(store.units, WordTok(), size=8, overlap=2)
    orders = sorted(u.order for u in store.units)
    assert ws and ws[0].lo == orders[0] and ws[-1].hi == orders[-1]
    for a, b in zip(ws, ws[1:]):
        assert a.lo <= b.lo and a.hi <= b.hi            # monotone, overlapping stride
    assert all(o in orders for w in ws for o in (w.lo, w.hi))
    assert 'zither' not in ' '.join(w.text for w in ws)  # system profile never indexed


def test_pack_windows_keeps_whole_turns_dedupes_and_renders_chronologically(setup):
    _, store = setup
    by = {u.order: u for u in store.units}
    ws = [EV.Window('w2', 3, 4, ''), EV.Window('w1', 1, 3, ''), EV.Window('w3', 5, 6, '')]
    packed, intervals = EV.pack_windows(ws, store, count, budget=10 ** 6)
    assert [u.order for u in packed.units] == sorted(by)          # union, no repeats, source order
    assert intervals == union_intervals([[3, 4], [1, 3], [5, 6]]) == [[1, 6]]
    one = EV.unit_cost(count, by[1]) + EV.unit_cost(count, by[2]) + EV.unit_cost(count, by[3])
    packed, _ = EV.pack_windows([EV.Window('w1', 1, 3, ''), EV.Window('w9', 4, 6, '')], store, count, budget=one)
    assert [u.order for u in packed.units] == [1, 2, 3] and packed.skipped_over_budget == ('w9',)  # skipped whole


def test_c_plus_noise_keeps_c_exactly_and_is_seeded_not_selected(setup):
    task, store = setup
    direct = [u.unit_id for u in store.units if u.order == 3]
    c = W3.select('C', task, store, direct_ids=direct, count_tokens=count)[0]
    n1, f1 = EV.with_background(c, store, count, budget=40, task_id=task.task_id)
    n2, f2 = EV.with_background(c, store, count, budget=40, task_id=task.task_id)
    assert n1 == n2 and f1 == f2                                    # fixed seed
    assert set(direct) <= {u.unit_id for u in n1.units}             # C never lost
    assert [u.order for u in n1.units] == sorted(u.order for u in n1.units)
    assert n1.tokens <= 40 and all(u.owner_id == store.owner_id for u in n1.units)
    other = EV.with_background(c, store, count, budget=40, task_id='another-task')[0]
    assert {u.unit_id for u in other.units} >= set(direct)


def test_coverage_separates_user_and_nonuser_reference(setup):
    _, store = setup
    user = [u for u in store.units if u.is_current_user][0]
    asst = [u for u in store.units if not u.is_current_user][0]
    cov = EV.coverage([user], [user.unit_id, asst.unit_id], store)
    assert cov['user_recall'] == 1.0 and cov['nonuser_recall'] == 0.0 and not cov['complete_group']
    assert EV.coverage([user], None, store) is None


def test_arms_share_prompt_and_short_protocol_and_hide_options_from_retrieval(setup):
    task, store = setup
    vec = {u.unit_id: [1.0, float(u.order)] for u in store.units}
    iu = OwnerIndex(store, RetrievalSpec(backend='dense', unit_filter='user_only'), unit_vectors=vec)
    ia = OwnerIndex(store, RetrievalSpec(backend='dense', unit_filter='all'), unit_vectors=vec)
    e0 = [EV.Window('w', 1, 2, '')]
    direct = [store.units[0].unit_id]
    msgs = {}
    for arm in W3.ARMS:
        p, _ = W3.select(arm, task, store, dense_user=iu, dense_all=ia, query_vector=[1.0, 0.0], e0_ranked=e0,
                         direct_ids=direct, count_tokens=count)
        msgs[arm] = W3.build(arm, task, store, p)[0]
    systems = {m[0]['content'] for m in msgs.values()}
    tails = {m[-1]['content'].split('Current request from the user:')[1] for m in msgs.values()}
    assert len(systems) == 1 and len(tails) == 1                     # only the evidence differs
    tail = tails.pop()
    assert tail.endswith(W3.SP.SHORT_SUFFIX) and 'step by step' not in tail and 'Please recall' in tail
    assert all(o['text'] in tail for o in OPTIONS) and not any(o['text'] in query_text(task) for o in OPTIONS)
    assert extract_final_answer("Final Answer: B") == "B"            # A official upstream parser reads it
    b0 = W3.select('B0', task, store, dense_user=iu, query_vector=[1.0, 0.0], count_tokens=count)[0]
    assert all(u.is_current_user for u in b0.units)
    assert W3.BUDGET['E0s'] == W3.BUDGET['B1s'] == 1536 and W3.SHORT_MAX_NEW_TOKENS == 64


def test_c_and_cn_not_evaluable_without_direct(setup):
    task, store = setup
    for arm in ('C', 'Cn'):
        with pytest.raises(W3.WP2.NotEvaluable):
            W3.select(arm, task, store, direct_ids=None, count_tokens=count)
