"""NAA WP4 backend regression on CPU: same-evidence conditions, training-data contract, minimal LoRA,
SFT vs paired supervision on a tiny random causal LM, adapter save/merge identity. Plumbing only."""
import hashlib

import pytest

torch = pytest.importorskip('torch')
transformers = pytest.importorskip('transformers')

from metacom_pm.need_aware.agent import behavior as B
from metacom_pm.need_aware.memory import reader as R
from metacom_pm.need_aware.memory.writer import MemoryWriter, write_for_task
from metacom_pm.need_aware.runtime import lora as LORA
from metacom_pm.need_aware.runtime import training as T

from test_need_aware_agent import runtime


class ChatTok:
    """Deterministic chat template: [role] words [EOT]; generation prompt = [assistant role]."""
    ROLE = {'system': 1, 'user': 2, 'assistant': 3}
    EOT, PAD = 4, 0
    all_special_ids = [0, 1, 2, 3, 4]

    def _w(self, text):
        return [10 + int(hashlib.sha256(w.encode()).hexdigest(), 16) % 54 for w in text.split()]

    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=False):
        ids = []
        for m in messages:
            ids += [self.ROLE[m['role']]] + self._w(m['content']) + [self.EOT]
        if add_generation_prompt:
            ids += [self.ROLE['assistant']]
        if messages and messages[-1]['role'] == 'assistant' and not add_generation_prompt:
            pass
        return ids


def tiny_model():
    cfg = transformers.LlamaConfig(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                                   num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=256)
    torch.manual_seed(0)
    return transformers.LlamaForCausalLM(cfg).eval()


@pytest.fixture
def setup(tmp_path):
    task, resolver = runtime(tmp_path, task_mode='generation', options=[])
    store = write_for_task(resolver, MemoryWriter(), task)
    return task, store


def test_u0_u2_u3_share_input_and_u1_adds_rules_only(setup):
    task, store = setup
    packed = R.pack(list(store.units), lambda s: len(s.split()), 10 ** 6)
    m0, _ = B.build('U0', task, store, packed)
    m2, t2 = B.build('U2', task, store, packed, generator_id='lora:abc')
    m3, _ = B.build('U3', task, store, packed, generator_id='lora:def')
    assert m0 == m2 == m3 and t2['generator_id'] == 'lora:abc'
    with pytest.raises(ValueError):
        B.build('U2', task, store, packed)                       # adapted generator identity required
    m1, t1 = B.build('U1', task, store, packed)
    assert m1[0] == m0[0] and 'Memory-use policy' in m1[-1]['content'] and not t1['silence']
    assert m1[-1]['content'].endswith(task.user_query) and 'Please recall' not in m1[-1]['content']


def test_u1_silence_rule_when_every_user_record_is_third_party(setup):
    task, store = setup
    from dataclasses import replace
    units = [replace(u, third_party_mention=True) if u.is_current_user else u for u in store.units]
    packed = R.Packed(units=tuple(units), priority_ids=(), skipped_over_budget=(), tokens=10)
    block, trace = B.u1_view(list(packed.units), store)
    assert trace['silence'] and B.SILENCE_NOTE in block and trace['shown_ids'] == []


def row(eid, group, owner='pm2:1', split='fit', behavior='USE', target='Sure, ramen it is.', opp=None, unique=False):
    return dict(example_id=eid, group_id=group, owner_id=owner, split=split, origin='natural', behavior=behavior,
                task=dict(persona_group=owner, options=[]), evidence_ids=['u1'], target=target,
                contrast=dict(opposite_example_id=opp, unique_opposite=unique), provenance={})


def test_training_contract_blocks_leakage_and_bad_contrasts():
    ok = [row('a', 'g', opp='b', unique=True), row('b', 'g', behavior='IGNORE', target='Any place works.', opp='a',
                                                  unique=True)]
    summary, pairs = T.validate(ok)
    assert summary['unique_opposite_pairs'] == 2 and pairs == [('a', 'b'), ('b', 'a')]
    with pytest.raises(T.ContractError, match='both fit and tune'):
        T.validate([row('a', 'g'), row('b', 'h', split='tune')])
    with pytest.raises(T.ContractError, match='development'):
        T.validate([row('a', 'g')], forbidden_owners={'pm2:1'})
    with pytest.raises(T.ContractError, match='different behaviour'):
        T.validate([row('a', 'g', opp='b', unique=True), row('b', 'g')])
    with pytest.raises(T.ContractError, match='same group'):
        T.validate([row('a', 'g', opp='b'), row('b', 'h')])


def encoded_pair():
    tok = ChatTok()
    request = {'a': 'records: user loves ramen . request: dinner idea for me',
               'b': 'records: user loves ramen . request: dinner idea for my vegan colleague'}
    rows = [row('a', 'g', opp='b', unique=True, target='ramen with extra garlic'),
            row('b', 'g', behavior='IGNORE', target='any generic restaurant', opp='a', unique=True)]
    _, pairs = T.validate(rows)
    return T.encode(rows, lambda r: [dict(role='user', content=request[r['example_id']])],
                    T.template_encoder(tok, 256, [ChatTok.EOT]), pairs=pairs)


def test_lora_freezes_base_starts_at_identity_and_trains():
    model = tiny_model()
    ids = torch.tensor([[2, 11, 12, 13, 4, 3]])
    before = model(input_ids=ids).logits.detach().clone()
    base = {k: v.detach().clone() for k, v in model.state_dict().items()}
    names = LORA.apply(model, suffixes=('q_proj', 'v_proj'), r=4, alpha=8)
    assert len(names) == 4 and all('.lora_' in n for n, _ in LORA.trainable(model))
    assert torch.allclose(model(input_ids=ids).logits, before)          # B=0: identical at start
    enc = encoded_pair()
    sft = T.train(model, enc, dict(mode='sft', lr=5e-2, epochs=6, accumulation=2, seed=7, margin=.5, lambda_pair=1.),
                  pad_token_id=0)
    assert sft['steps'] == 6 and sft['log'][-1]['nll_per_token'] < sft['log'][0]['nll_per_token']
    after = model.state_dict()
    assert all(torch.equal(base[k], after[k.replace('.base.', '.')] if k not in after else after[k])
               for k in base if 'q_proj' not in k and 'v_proj' not in k)


def test_paired_mode_raises_margin_same_steps_and_merge_matches(tmp_path):
    enc = encoded_pair()
    cfg = dict(lr=5e-2, epochs=8, accumulation=2, seed=7, margin=2., lambda_pair=1.)
    runs = {}
    for mode in ('sft', 'paired'):
        model = tiny_model(); LORA.apply(model, suffixes=('q_proj', 'v_proj'), r=4, alpha=8)
        runs[mode] = (model, T.train(model, enc, dict(cfg, mode=mode), pad_token_id=0))
    assert runs['sft'][1]['steps'] == runs['paired'][1]['steps']          # matched optimizer steps
    assert runs['paired'][1]['tokens']['negative'] > 0 == runs['sft'][1]['tokens']['negative']
    hinge = [x['hinge_mean'] for x in runs['paired'][1]['log']]
    assert hinge[-1] < hinge[0]
    model = runs['paired'][0]
    meta = LORA.save(tmp_path / 'ad', model, dict(suffixes=['q_proj', 'v_proj'], r=4, alpha=8))
    ids = torch.tensor([[2, 11, 12, 13, 4, 3]])
    model.eval(); want = model(input_ids=ids).logits
    fresh = tiny_model()
    info = LORA.merge(fresh, tmp_path / 'ad', expected_sha256=meta['adapter_sha256'])
    assert info['merged_modules'] == 4 and torch.allclose(fresh(input_ids=ids).logits, want, atol=1e-4)
    with pytest.raises(ValueError, match='bound identity'):
        LORA.merge(tiny_model(), tmp_path / 'ad', expected_sha256='0' * 64)


class FakeNative:
    """NativeTokenizer surface: chat_ids == the inference prompt; tok() for response text."""
    def __init__(self):
        self.t = ChatTok()
        outer = self

        class _Tok:
            all_special_ids = ChatTok.all_special_ids

            def __call__(self, text, add_special_tokens=False):
                return {'input_ids': outer.t._w(text)}
        self.tok = _Tok()

    def chat_ids(self, messages):
        return self.t.apply_chat_template(messages, add_generation_prompt=True) + [5]   # e.g. empty thought channel


def test_native_encoder_anchors_on_inference_prompt_and_turn_end():
    nat = FakeNative()
    msgs = [dict(role='user', content='dinner idea for me')]
    e = T.native_encoder(nat, turn_end_id=ChatTok.EOT, context_limit=64)(msgs, 'ramen tonight')
    prompt = nat.chat_ids(msgs)
    assert list(e.input_ids[:len(prompt)]) == prompt and e.input_ids[-1] == ChatTok.EOT
    assert all(x == -100 for x in e.labels[:len(prompt)]) and e.target_tokens == 3
    with pytest.raises(ValueError, match='input cap'):
        T.native_encoder(nat, turn_end_id=ChatTok.EOT, context_limit=5)(msgs, 'ramen tonight')
