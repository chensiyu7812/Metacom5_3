"""2026-11-28 revision on CPU: revised W4 conditions (same evidence, no silence, U1+, NoMem, OptOnly),
seed-fixed LoRA init, adapted generator identity, strict adapter load check, reply-level U2/U3 trainer
(compute parity, hard deadline, 20-step technical smoke), and the minimal companion chain."""
from dataclasses import replace
import json

import pytest

torch = pytest.importorskip('torch')
transformers = pytest.importorskip('transformers')

from metacom_pm.need_aware.agent import behavior as B
from metacom_pm.need_aware.agent import companion as C
from metacom_pm.need_aware.memory import reader as R
from metacom_pm.need_aware.memory.writer import MemoryWriter, write_for_task
from metacom_pm.need_aware.runtime import lora as LORA
from metacom_pm.need_aware.runtime import models as M
from metacom_pm.need_aware.runtime import requests as Q
from metacom_pm.need_aware.runtime import training as T
from metacom_pm.need_aware.runtime.backend import check_adapter_load
from metacom_pm.rl1v3.generator.limited_run import AdmissionError

from test_need_aware_agent import runtime
from test_need_aware_wp4_backend import ChatTok, FakeNative, tiny_model


@pytest.fixture
def mcq(tmp_path):
    task, resolver = runtime(tmp_path)
    store = write_for_task(resolver, MemoryWriter(), task)
    packed = R.pack(list(store.units), lambda s: len(s.split()), 10 ** 6)
    return task, store, packed


def test_w40_conditions_share_evidence_and_diagnostics_drop_it(mcq):
    task, store, packed = mcq
    out = {c: B.mcq_messages(c, task, store, packed) for c in B.CONDITIONS}
    ids = {c: out[c][1]['delivered_ids'] for c in B.SAME_EVIDENCE}
    assert len({tuple(v) for v in ids.values()}) == 1 and ids['U0']
    assert out['U2'][0] == out['U3'][0] == out['U0'][0]
    final = {c: out[c][0][-1]['content'] for c in B.CONDITIONS}
    assert 'Final Answer: A' in final['U0'] and task.user_query in final['U1+']
    assert B.U1_PLUS_RULES in final['U1+'] and B.U1_PLUS_RULES not in final['U1'] and B.U1_POLICY in final['U1']
    assert R.EMPTY_BLOCK in final['NoMem'] and out['NoMem'][1]['delivered_ids'] == []
    assert task.user_query not in final['OptOnly'] and len(out['OptOnly'][0]) == 2
    assert all(o['text'] in final['OptOnly'] for o in task.options)


def test_rule_layers_read_only_the_delivered_units(mcq):
    task, store, packed = mcq
    # a forget request that exists in the store but was NOT delivered must not appear in U1/U1+
    extra = replace(store.units[0], unit_id='x-forget', order=999, original_text='Please forget that I like sushi.',
                    constraint_candidates=('forget_request',))
    wider = replace(store, units=[*store.units, extra])
    for plus in (False, True):
        block, tr = B.rule_view(list(packed.units), query=task.user_query, plus=plus)
        assert 'sushi' not in block and tr['shown_ids'] == [u.unit_id for u in packed.units]
    assert 'sushi' in B.reglos_silence_view(list(packed.units), wider)[0]       # historical store-wide reference


def test_u1_plus_marks_holder_and_served_person():
    req = [dict(role='system', content='S'), dict(role='user', content='My sister is allergic to nuts.'),
           dict(role='user', content='Can you suggest a cake for my sister?')]
    out, tr = B.u1_messages(req, plus=True)
    assert 'possibly my sister' in out[0]['content'] and "may be my sister's" in out[1]['content']
    assert tr['withheld'] == 0


def test_lora_init_depends_only_on_seed_not_rng_state():
    digests = []
    for noise in (0, 5):
        model = tiny_model(); torch.manual_seed(1234 + noise); torch.rand(noise + 1)
        LORA.apply(model, suffixes=('q_proj', 'v_proj'), r=4, alpha=8, seed=42)
        digests.append(LORA.adapter_digest(model))
    other = tiny_model(); LORA.apply(other, suffixes=('q_proj', 'v_proj'), r=4, alpha=8, seed=43)
    assert digests[0] == digests[1] != LORA.adapter_digest(other)
    assert LORA.WP4_LORA == dict(suffixes=('q_proj', 'v_proj', 'in_proj_qkv'), r=8, alpha=16, dropout=0.)


def ident(method, **over):
    base = dict(method=method, adapter_sha256='a' * 64 if method == 'U2' else 'b' * 64, adapter_config_sha256='c' * 64,
                init_adapter_sha256='d' * 64, base_g_id=M.QWEN35.g_id, train_data_sha256='e' * 64,
                train_receipt_sha256='f' * 64 if method == 'U2' else '9' * 64, trainer_version=T.REPLY_TRAINER_VERSION)
    return dict(base, **over)


def test_adapter_identity_enters_g_id_and_request_hash_base_unchanged():
    spec = M.QWEN35
    decode = spec.decode(64)
    b2, b3 = M.adapted_binding(spec, ident('U2'), decode), M.adapted_binding(spec, ident('U3'), decode)
    assert spec.g_id == M.QWEN35.g_id and len({spec.g_id, b2['g_id'], b3['g_id']}) == 3
    assert b2['base_g_id'] == spec.g_id and b2['label'] == 'Qwen35+U2'
    msgs, ids = [dict(role='user', content='hi')], [1, 2, 3]
    shas = {Q.physical_identity(g, msgs, ids, decode) for g in (spec.g_id, b2['g_id'], b3['g_id'])}
    assert len(shas) == 3                                         # identical inputs never de-duplicate across U0/U2/U3
    for k in ('adapter_sha256', 'train_receipt_sha256', 'init_adapter_sha256', 'train_data_sha256'):
        assert M.adapted_binding(spec, ident('U2', **{k: '7' * 64}), decode)['g_id'] != b2['g_id']
    with pytest.raises(ValueError, match='different base'):
        M.adapted_binding(spec, ident('U2', base_g_id='naag:other'), decode)
    with pytest.raises(ValueError, match='incomplete'):
        M.adapted_binding(spec, ident('U2', trainer_version=''), decode)


def test_adapter_load_is_strictly_checked():
    spec = M.adapted_binding(M.QWEN35, ident('U2'), M.QWEN35.decode(64))
    ok = dict(loading=dict(adapter=dict(adapter_sha256='a' * 64, merged_modules=40)))
    check_adapter_load(spec, dict(path='p', sha256='a' * 64), ok)
    for bad_spec, bad_ad, bad_res in ((spec, dict(path='p', sha256='b' * 64), ok),
                                      (spec, dict(path='p', sha256='a' * 64), dict(loading={})),
                                      (spec, None, ok), ({'label': 'Qwen35'}, None, ok)):
        with pytest.raises(AdmissionError):
            check_adapter_load(bad_spec, bad_ad, bad_res)
    check_adapter_load({'label': 'Qwen35'}, None, dict(loading={}))


def reply_rows(n=8):
    rows = []
    for i in range(n):
        rows.append(dict(example_id=f'e{i}', group_id=f'g{i // 2}', owner_id=f'o{i % 3}', split='fit',
                         messages=[dict(role='user', content=f'dinner idea {i} for me')],
                         chosen='ramen with garlic', rejected=['a generic salad', 'nothing today'], provenance={}))
    return rows


def encoded():
    nat = FakeNative()
    rows = reply_rows()
    T.validate_reply(rows)
    enc, align = T.encode_reply(rows, T.native_encoder(nat, ChatTok.EOT, 256), eos_ids=[ChatTok.EOT], turn_end_id=ChatTok.EOT)
    return enc, align


def test_reply_contract_and_alignment():
    enc, align = encoded()
    assert align['prompt_equals_inference_chat_ids'] and align['rows'] == 8
    bad = reply_rows(); bad[0]['messages'][-1]['content'] += ' Final Answer: A'
    with pytest.raises(T.ContractError, match='MCQ'):
        T.validate_reply(bad)
    bad = reply_rows(); bad[1]['split'] = 'tune'; bad[1]['owner_id'] = bad[0]['owner_id']
    with pytest.raises(T.ContractError, match='both fit and tune'):
        T.validate_reply(bad)
    with pytest.raises(T.ContractError, match='forbidden|development'):
        T.validate_reply(reply_rows(), forbidden_owners={'o1'})
    with pytest.raises(T.ContractError, match='stop token'):
        T.encode_reply(reply_rows(), T.native_encoder(FakeNative(), ChatTok.EOT, 256), eos_ids=[0], turn_end_id=ChatTok.EOT)


def test_reply_loss_u2_is_sft_with_zero_rank_but_same_graph():
    sft, c = torch.tensor(1.5, requires_grad=True), torch.tensor(-1., requires_grad=True)
    r = [torch.tensor(-.5, requires_grad=True)]
    u2 = T.reply_loss(sft, c, r, method='U2', weight=.5, margin=1.)
    u3 = T.reply_loss(sft, c, r, method='U3', weight=.5, margin=1.)
    assert float(u2) == 1.5 and float(u3) > 1.5
    u2.backward()
    assert r[0].grad is not None and float(r[0].grad) == 0.          # branch is computed, coefficient 0


class Clock:
    def __init__(self, step=1.):
        self.t, self.step = 0., step

    def __call__(self):
        self.t += self.step
        return self.t


CFG = dict(learning_rate=5e-2, weight_decay=0., warmup_steps=2, gradient_accumulation=1, rank_weight=1., rank_margin=2., seed=7)


def test_train_reply_u2_u3_parity_smoke_and_ranking_effect():
    enc, _ = encoded()
    enc = enc * 3                                                  # 24 one-example steps
    res, models = {}, {}
    for method in ('U2', 'U3'):
        model = tiny_model(); LORA.apply(model, suffixes=('q_proj', 'v_proj'), r=4, alpha=8, seed=3)
        clock = Clock(.01)
        guard = T.TrainGuard(started=0., max_seconds=1e6, save_reserve=10, close_reserve=10, clock=clock, watchdog=False)
        res[method] = T.train_reply(model, enc, dict(CFG, method=method), guard=guard, clock=clock, max_steps=24)
        models[method] = model
    for k in ('steps', 'tokens'):
        assert res['U2'][k] == res['U3'][k]
    assert res['U2']['smoke']['passed'] and res['U3']['smoke']['passed'] and res['U2']['steps'] == 24

    def margin(model):
        model.eval()
        with torch.no_grad():
            e = enc[0]
            return float(T._reply_logp(model, e['chosen'], 'cpu')[1] - T._reply_logp(model, e['rejected'][0], 'cpu')[1])
    assert margin(models['U3']) > margin(models['U2'])


def test_train_reply_hard_deadline_and_smoke_budget_stop():
    enc, _ = encoded()
    model = tiny_model(); LORA.apply(model, suffixes=('q_proj', 'v_proj'), r=4, alpha=8, seed=3)
    clock = Clock(1.)                                              # every clock read = 1 s
    guard = T.TrainGuard(started=0., max_seconds=40, save_reserve=5, close_reserve=5, clock=clock, watchdog=False)
    r = T.train_reply(model, enc * 10, dict(CFG, method='U3'), guard=guard, clock=clock, max_steps=80)
    assert r['stop'] == 'hard deadline (save/close reserve)' and r['steps'] < 20
    model = tiny_model(); LORA.apply(model, suffixes=('q_proj', 'v_proj'), r=4, alpha=8, seed=3)
    clock = Clock(.5)
    guard = T.TrainGuard(started=0., max_seconds=400, save_reserve=5, close_reserve=5, clock=clock, watchdog=False)
    r = T.train_reply(model, enc * 30, dict(CFG, method='U2'), guard=guard, clock=clock, max_steps=240)
    assert r['stop'] == 'technical smoke failed' and r['steps'] == 20 and not r['smoke']['checks']['time']


def test_history_chain_and_memory_store(tmp_path):
    h = C.History('u1', path=tmp_path / 'h.jsonl')
    h.add('user', 'I love spicy ramen.'); h.add('assistant', 'Noted!'); h.add('user', 'My friend hates spicy food.')
    st = h.store()
    assert [u.order for u in st.units] == [0, 1, 2] and st.units[2].third_party_mention and st.units[0].is_current_user
    again = C.History('u1', path=tmp_path / 'h.jsonl')
    assert again.head() == h.head()
    lines = (tmp_path / 'h.jsonl').read_text().splitlines()
    lines[0] = lines[0].replace('spicy', 'mild')
    (tmp_path / 'h.jsonl').write_text('\n'.join(lines) + '\n')
    with pytest.raises(ValueError, match='chain'):
        C.History('u1', path=tmp_path / 'h.jsonl')


SKILLS = [dict(skill_id='skill:plan', objective='Help the user plan one small practical next step.',
               required_observable_conditions=['The user asks for help making a plan.'], method_reading='PLAN METHOD'),
          dict(skill_id='skill:both', objective='Acknowledge both stated concerns.',
               required_observable_conditions=['Two competing wishes.'], method_reading='BOTH METHOD')]


def test_need_decision_and_skill_gate():
    assert C.need_decision('visible_rule', 'What did I tell you earlier about dinner?')['arm'] == 'MS'
    assert C.need_decision('never_memory', 'earlier')['memory'] is False
    assert C.need_decision('base_self_select', 'x', self_select=lambda q: 'MS_RS')['arm'] == 'MS_RS'
    assert C.need_decision('base_self_select', 'x', self_select=lambda q: 'no idea')['arm'] == 'STOP'
    lib = C.SupportSkills(SKILLS)
    assert lib.select('Can you help me plan a small next step?')['skill_id'] == 'skill:plan'
    assert lib.select('I do not want advice, just listen.') is None and lib.select('How are you?') is None


def test_companion_chain_end_to_end_on_cpu(tmp_path):
    h = C.History('u1', path=tmp_path / 'h.jsonl')
    for role, text in (('user', 'I love spicy ramen.'), ('assistant', 'Noted.'), ('user', 'My friend hates spicy food.'),
                       ('assistant', 'Okay.')):
        h.add(role, text)
    seen = []

    def gen(messages):
        seen.append(messages)
        return dict(text='PLUMBING reply %d' % len(seen), g_id='plumbing')
    agent = C.CompanionAgent(h, gen, C.Memory(lambda s: len(s.split()), 200), skills=C.SupportSkills(SKILLS), recent_turns=0)
    log = C.run_episode(agent, ['Hi there.', 'What food did I say earlier that I love?', 'Can you help me plan a small next step?'])
    assert [x['trace']['decision']['arm'] for x in log] == ['STOP', 'MS', 'RS']
    assert log[0]['trace']['memory_ids'] == [] and log[1]['trace']['memory_ids'] and log[1]['trace']['applicability'] == 'U1+'
    assert 'spicy ramen' in seen[1][-1]['content'] and B.U1_PLUS_RULES in seen[1][-1]['content']
    assert log[2]['trace']['skill_id'] == 'skill:plan' and 'PLAN METHOD' in seen[2][-1]['content']
    assert len(h.turns) == 10 and h.turns[-1]['text'] == 'PLUMBING reply 3'
    assert json.loads((tmp_path / 'h.jsonl').read_text().splitlines()[-1])['turn_sha256'] == h.head()
