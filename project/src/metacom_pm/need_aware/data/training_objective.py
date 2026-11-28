"""Backend-neutral U2/U3 CPU contracts. No model loading or optimizer here."""
import json
from .contracts import digest


def encode_target(tokenizer,row,max_length=2048):
    """Exact chosen sequence shared by U2 and U3, no silent truncation.

    Action alternatives share the exact assistant prefix; score only action
    tokens, not whole alternative replies. Native tokenizer boundary receipts
    verify the label's true token extent (prefix merges are explicitly handled).
    """
    try:prompt=tokenizer.apply_chat_template(row['messages'],tokenize=False,add_generation_prompt=True,enable_thinking=False)
    except TypeError:prompt=tokenizer.apply_chat_template(row['messages'],tokenize=False,add_generation_prompt=True)
    prefix=tokenizer.encode(prompt,add_special_tokens=False)
    chosen=tokenizer.encode(row['target_text'],add_special_tokens=False)+[tokenizer.eos_token_id]
    if len(prefix)+len(chosen)>max_length:raise ValueError('training example exceeds frozen cap; no truncation')
    alternatives={}
    for action in (row['action_target'],row['rejected_action']):
        start='{"action":"';full=start+action+'"'
        before=tokenizer.encode(start,add_special_tokens=False);after=tokenizer.encode(full,add_special_tokens=False)
        common=0
        while common<min(len(before),len(after)) and before[common]==after[common]:common+=1
        alternatives[action]=dict(input_ids=prefix+after,action_mask=[0]*(len(prefix)+common)+[1]*(len(after)-common))
    return dict(variant_id=row['variant_id'],group_id=row['group_id'],input_ids=prefix+chosen,
                labels=[-100]*len(prefix)+chosen,attention_mask=[1]*(len(prefix)+len(chosen)),
                chosen_action=alternatives[row['action_target']],rejected_action=alternatives[row['rejected_action']],
                pair_loss_mask=row['pair_loss_mask'],chosen_sequence_sha256=digest([prefix,chosen]))


def masked_action_logp(logits,input_ids,action_mask):
    import torch
    # Causal shift: position t predicts token t+1. Average over action tokens
    # to avoid a tokenization-length advantage for one action word.
    logp=logits[:,:-1].log_softmax(-1).gather(-1,input_ids[:,1:].unsqueeze(-1)).squeeze(-1)
    mask=action_mask[:,1:].to(logp.dtype)
    if bool((mask.sum(-1)==0).any()):raise ValueError('empty action token mask')
    return (logp*mask).sum(-1)/mask.sum(-1)


def objective(sft_per_example,chosen_action_logp,rejected_action_logp,pair_mask,*,method,weight=.1,margin=.5):
    import torch
    import torch.nn.functional as F
    if method not in ('U2','U3'):raise ValueError('only authorized candidate target definitions U2/U3')
    if sft_per_example.ndim!=1:raise ValueError('per-example SFT loss required')
    for v in (chosen_action_logp,rejected_action_logp,pair_mask):
        if v.shape!=sft_per_example.shape:raise ValueError('loss shape mismatch')
    if method=='U2':
        # B uses the same three forward passes and backward graph for both
        # methods. Zero-weight auxiliary branches keep U2's gradient exactly
        # ordinary SFT, while matching processed tokens and physical compute.
        return sft_per_example.mean()+0.*(chosen_action_logp+rejected_action_logp).mean()
    mask=pair_mask.to(sft_per_example.dtype)
    # Zero masked rows contribute zero pair loss, not a division-by-zero NaN.
    pair=(F.softplus(margin-chosen_action_logp+rejected_action_logp)*mask).sum()/mask.sum().clamp_min(1)
    return sft_per_example.mean()+weight*pair
