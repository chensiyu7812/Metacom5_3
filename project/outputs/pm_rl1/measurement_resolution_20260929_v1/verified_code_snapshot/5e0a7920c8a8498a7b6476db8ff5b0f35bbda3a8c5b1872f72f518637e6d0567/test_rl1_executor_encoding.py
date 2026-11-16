from dataclasses import replace
import pytest
import torch
from metacom_pm.rl1.executor_encoding import encode_response, collate_responses, response_nll_sum


class Tokenizer:
    all_special_ids = [1, 2, 3]
    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        ids = [1]
        for m in messages:
            ids += [3] + [4+ord(c)%8 for c in m['content']] + [2]
        return ids + [3] if add_generation_prompt else ids


def example(response='Yes.'):
    return encode_response(Tokenizer(), [dict(role='user', content='Help')], response,
                           context_limit=100, eos_token_ids=[2])


def test_prefix_is_exact_and_only_current_response_plus_eos_is_supervised():
    e = example()
    assert e.labels[:e.prompt_tokens] == (-100,)*e.prompt_tokens
    assert e.labels[e.prompt_tokens:] == e.input_ids[e.prompt_tokens:] and e.labels[-1] == 2
    assert e.target_tokens == 5


def test_padding_masks_attention_and_loss_and_excludes_audit_metadata():
    a, b = example('Yes.'), example('Longer reply.')
    batch = collate_responses([a,b], pad_token_id=2)
    assert set(batch) == {'input_ids','attention_mask','labels'}
    assert batch['attention_mask'][0][-1] == 0 and batch['labels'][0][-1] == -100
    with pytest.raises(ValueError):collate_responses([replace(a, labels=a.input_ids)], pad_token_id=2)


def test_causal_nll_predicts_first_answer_from_final_prompt_position():
    e = example(); batch = collate_responses([e], pad_token_id=2)
    logits = torch.zeros(1,len(e.input_ids),12, requires_grad=True)
    loss,count = response_nll_sum(logits,torch.tensor(batch['labels'])); loss.backward()
    assert count == e.target_tokens
    assert logits.grad[0,:e.prompt_tokens-1].abs().sum() == 0
    assert logits.grad[0,e.prompt_tokens-1].abs().sum() > 0
    assert logits.grad[0,-1].abs().sum() == 0
    assert float(loss) == pytest.approx(count*torch.log(torch.tensor(12.)).item())


def test_nll_aggregation_is_invariant_to_batch_partition():
    examples = [example('Y.'), example('Much longer.')]
    batch = collate_responses(examples,pad_token_id=2)
    loss,count = response_nll_sum(torch.zeros(2,len(batch['labels'][0]),12),torch.tensor(batch['labels']))
    pieces = [response_nll_sum(torch.zeros(1,len(e.input_ids),12),torch.tensor([e.labels])) for e in examples]
    assert count == sum(n for _,n in pieces)
    assert float(loss) == pytest.approx(sum(float(v) for v,_ in pieces))


def test_context_overflow_and_empty_target_are_failures():
    with pytest.raises(ValueError,match='no truncation'):
        encode_response(Tokenizer(),[dict(role='user',content='Help')],'Yes.',context_limit=3,eos_token_ids=[2])
    with pytest.raises(ValueError,match='empty response'):example(' ')
    with pytest.raises(ValueError,match='no response targets'):
        response_nll_sum(torch.zeros(1,3,12),torch.full((1,3),-100))


def test_unstable_template_boundary_is_not_silently_repaired():
    class Broken(Tokenizer):
        def apply_chat_template(self,messages,tokenize,add_generation_prompt):
            ids = super().apply_chat_template(messages,tokenize,add_generation_prompt)
            if not add_generation_prompt:ids[0] = 11
            return ids
    with pytest.raises(ValueError,match='prompt boundary'):
        encode_response(Broken(),[dict(role='user',content='Help')],'Yes.',context_limit=100,eos_token_ids=[2])


def test_legacy_template_always_appending_assistant_header_excludes_next_turn():
    class Legacy(Tokenizer):
        def apply_chat_template(self,messages,tokenize,add_generation_prompt):
            return super().apply_chat_template(messages,tokenize,True)
    e = encode_response(Legacy(),[dict(role='user',content='Help')],'Yes.',context_limit=100,eos_token_ids=[2])
    assert e.input_ids == example().input_ids and e.labels == example().labels
    assert e.trailing_template_tokens_removed == 1 and e.input_ids[-1] == 2
