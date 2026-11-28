"""U2 reply SFT / U3 same SFT + ONE vetted reply ranking loss. No action labels.

Backend-neutral, no model loading, optimizer, GPU or authorization side effects.
Unknown negatives never reach the loss. Positive order and weights are identical.
"""
from .contracts import digest

VERSION='naa-reply-sft-rank-v1'
PAIR_WEIGHT=.1
MARGIN=.5
MAX_LENGTH=10240


def encode_reply(tokenizer,row,messages,*,max_length=MAX_LENGTH):
    if not row['sft_eligible']:
        raise ValueError('source-unsupported candidate is masked')
    if digest(messages)!=row['messages_sha256']:
        raise ValueError('runtime prompt changed')
    prefix=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
        enable_thinking=False,return_dict=False)
    prefix=list(prefix)
    def sequence(text):
        body=tokenizer.encode(text,add_special_tokens=False)
        if not body or set(body)&set(tokenizer.all_special_ids):
            raise ValueError('empty reply or injected control token')
        target=body+[tokenizer.eos_token_id]
        if len(prefix)+len(target)>max_length:
            raise ValueError('native length exceeds cap; no truncation')
        return dict(input_ids=prefix+target,labels=[-100]*len(prefix)+target,
            attention_mask=[1]*(len(prefix)+len(target)),reply_mask=[0]*len(prefix)+[1]*len(target))
    positive=sequence(row['positive'])
    indices=row['pair_negative_indices']
    # One preselected checked negative per positive; no loss search or extra positive exposure.
    rejected=sequence(row['negatives'][indices[0]]) if indices else None
    return dict(task_id=row['task_id'],positive=positive,rejected=rejected,
        pair_mask=bool(indices),chosen_sequence_sha256=digest(positive),
        positive_tokens=len(positive['input_ids'])-len(prefix),prompt_tokens=len(prefix),
        negative_index=indices[0] if indices else None,class_weight=row['class_weight'])


def reply_logp(logits,ids,mask):
    logp=logits[:,:-1].log_softmax(-1).gather(-1,ids[:,1:].unsqueeze(-1)).squeeze(-1)
    weights=mask[:,1:].to(logp.dtype)
    if bool((weights.sum(-1)==0).any()):raise ValueError('empty reply')
    return (logp*weights).sum(-1)/weights.sum(-1)


def loss(chosen_logp,rejected_logp,pair_mask,*,method,weights=None):
    import torch
    import torch.nn.functional as F
    if method not in ('U2','U3'):raise ValueError('unknown reply objective')
    if chosen_logp.ndim!=1 or rejected_logp.shape!=chosen_logp.shape or pair_mask.shape!=chosen_logp.shape:
        raise ValueError('per-example likelihood vectors required')
    w=torch.ones_like(chosen_logp) if weights is None else weights.to(chosen_logp.dtype)
    if w.shape!=chosen_logp.shape or bool((w<=0).any()):raise ValueError('invalid class weights')
    sft=-(w*chosen_logp).sum()/w.sum()
    if method=='U2':return sft
    mask=pair_mask.to(chosen_logp.dtype)*w
    ranking=(F.softplus(MARGIN-chosen_logp+rejected_logp)*mask).sum()/mask.sum().clamp_min(1)
    return sft+PAIR_WEIGHT*ranking


def step_loss(model,encoded,*,method,device='cpu'):
    """Actual differentiable causal-LM loss; caller owns optimizer and permission.

    Positive pass is reused by U3. Only checked negatives add one forward pass.
    Batch size 1 avoids padding over these long histories; B may accumulate grads.
    """
    import torch
    def forward(seq):
        ids=torch.tensor([seq['input_ids']],device=device)
        mask=torch.tensor([seq['reply_mask']],device=device)
        keep=int(mask.sum())+1
        try:
            logits=model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False,
                logits_to_keep=keep).logits[:,-keep:]
        except TypeError:
            logits=model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).logits[:,-keep:]
        return reply_logp(logits.float(),ids[:,-keep:],mask[:,-keep:])
    pos=forward(encoded['positive'])
    pair=encoded['pair_mask'] and method=='U3'
    neg=forward(encoded['rejected']) if pair else torch.zeros_like(pos)
    value=loss(pos,neg,torch.tensor([pair],device=device),method=method,
        weights=torch.tensor([encoded['class_weight']],device=device))
    return value,dict(positive_forwards=1,negative_forwards=int(pair),
        processed_tokens=len(encoded['positive']['input_ids'])+
            (len(encoded['rejected']['input_ids']) if pair else 0))
