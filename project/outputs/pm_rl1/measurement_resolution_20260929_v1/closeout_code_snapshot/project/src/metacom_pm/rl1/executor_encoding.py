"""Response-only SFT tensor preparation, independent of semantic admission.

This module cannot qualify supervision. A future training runner must separately
bind accepted source-verification records, source splits and executor identities.
No source history, judge rationale or score is added to the inference messages.
"""
from dataclasses import dataclass
from .schema import digest


@dataclass(frozen=True)
class EncodedResponse:
    input_ids: tuple[int, ...]
    labels: tuple[int, ...]
    prompt_tokens: int
    target_tokens: int
    trailing_template_tokens_removed: int
    messages_identity: str
    response_identity: str


def encode_response(tokenizer, messages, response, *, context_limit, eos_token_ids):
    if not isinstance(messages, list) or not messages or any(
        set(m) != {'role', 'content'} or m['role'] not in ('system', 'user', 'assistant')
        or not isinstance(m['content'], str) for m in messages):
        raise ValueError('exact visible inference messages required')
    if messages[-1]['role'] != 'user':
        raise ValueError('prefix must end at the current user turn')
    if not isinstance(response, str) or not response.strip():
        raise ValueError('empty response is not supervision')
    if type(context_limit) is not int or context_limit <= 0 or not eos_token_ids:
        raise ValueError('explicit native context and EOS policy required')
    prompt = list(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    full = list(tokenizer.apply_chat_template(messages + [dict(role='assistant', content=response)],
                                             tokenize=True, add_generation_prompt=False))
    if not prompt or full[:len(prompt)] != prompt:
        raise ValueError('chat template changes the prompt boundary; do not guess a loss mask')
    # The frozen NousResearch Llama template always appends another assistant
    # header, even with add_generation_prompt=False. Infer only its exact fixed
    # footer from the same messages with an empty assistant, and retain its EOT.
    # Inference prompts/templates stay byte-identical; no reply text is cut.
    empty = list(tokenizer.apply_chat_template(messages + [dict(role='assistant', content='')],
                                               tokenize=True, add_generation_prompt=False))
    footer = empty[len(prompt):]
    if (empty[:len(prompt)] != prompt or not footer or footer[0] not in eos_token_ids
            or full[-len(footer):] != footer):
        raise ValueError('unsupported template footer; cannot isolate terminal marker')
    removed = len(footer)-1
    if removed:
        full = full[:-removed]
    target = full[len(prompt):]
    if len(target) < 2 or target[-1] not in eos_token_ids:
        raise ValueError('complete answer and genuine template EOS/EOT required')
    if any(t in set(tokenizer.all_special_ids) for t in target[:-1]):
        raise ValueError('response includes a control token before its terminal marker')
    if len(full) > context_limit:
        raise ValueError('training sequence exceeds native context; no truncation')
    return EncodedResponse(tuple(full), tuple([-100]*len(prompt) + target), len(prompt), len(target), removed,
                           digest(messages), digest(response))


def collate_responses(examples, *, pad_token_id):
    """Right-padding and prompt masking are explicit; audit metadata stays out."""
    if not examples or type(pad_token_id) is not int:
        raise ValueError('nonempty examples and an explicit padding token required')
    for e in examples:
        if (len(e.input_ids) != len(e.labels) or e.target_tokens < 2 or e.prompt_tokens < 1
                or e.target_tokens + e.prompt_tokens != len(e.input_ids)
                or any(x != -100 for x in e.labels[:e.prompt_tokens])
                or e.labels[e.prompt_tokens:] != e.input_ids[e.prompt_tokens:]):
            raise ValueError('invalid response-only mask')
    width = max(len(e.input_ids) for e in examples)
    return dict(input_ids=[list(e.input_ids)+[pad_token_id]*(width-len(e.input_ids)) for e in examples],
        attention_mask=[[1]*len(e.input_ids)+[0]*(width-len(e.input_ids)) for e in examples],
        labels=[list(e.labels)+[-100]*(width-len(e.labels)) for e in examples])


def response_nll_sum(logits, labels):
    """Causal, token-weighted NLL including terminal EOT; returns sum and count.

Aggregate sums/counts over all dev batches before choosing a checkpoint. A mean
of batch means would give short responses disproportionate validation weight.
"""
    import torch
    if logits.ndim != 3 or labels.shape != logits.shape[:2]:
        raise ValueError('logits/labels shapes differ')
    targets = labels[:, 1:]
    count = int((targets != -100).sum())
    if not count: raise ValueError('no response targets; not a zero-loss success')
    loss = torch.nn.functional.cross_entropy(logits[:, :-1].float().reshape(-1, logits.shape[-1]),
        targets.reshape(-1), ignore_index=-100, reduction='sum')
    return loss, count
