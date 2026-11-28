"""WP4 generator adaptation backend: ordinary SFT (U2) vs paired applicability supervision (U3).

Both modes see the same examples, order, optimizer, LoRA config, steps and seed; U3 only adds
a margin term on pairs whose opposite behaviour is uniquely and verifiably wrong for the
anchor input (contrast.unique_opposite). Reasonable alternatives are never negatives.

  L_sft    = sum_t NLL(y_t | x) / #target tokens                         (accumulation group)
  L_paired = L_sft + lambda * mean_pairs max(0, m - (lp(y+ | x) - lp(y- | x)))
             lp = mean token log-prob of a response under the SAME anchor input x

Supervision content (targets, behaviours, contrasts, splits) is A's responsibility; this
module validates the contract, renders inputs with the U0 renderer, encodes and trains.
Encoding anchors on the EXACT inference prompt ids (NativeTokenizer.chat_ids, the ids every
WP2/WP3 request carries) + response tokens + the model's native end-of-turn token. The
history-rendering path of rl1.executor_encoding cannot be used for these generators: Gemma-4
opens the generation turn with an empty thought channel that history rendering drops, and
transformers 5 returns a dict from apply_chat_template(tokenize=True). No truncation.
Nothing here starts a GPU job: the CLI refuses without a bounded researcher approval.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import random
import time

from ..data.contracts import digest
from ...rl1.executor_encoding import EncodedResponse, collate_responses, encode_response, response_nll_sum

TRAIN_SCHEMA = 'naa-wp4-train-v1'
TRAINER_VERSION = 'naa-wp4-trainer-v1'
BEHAVIORS = ('USE', 'IGNORE', 'CLARIFY', 'BACKGROUND')
REQUIRED = ('example_id', 'group_id', 'owner_id', 'split', 'origin', 'behavior', 'task', 'evidence_ids',
            'target', 'contrast', 'provenance')


class ContractError(ValueError):
    pass


def validate(rows, *, forbidden_owners=()):
    """Structural/leakage contract only; it cannot qualify labels (A's audit does)."""
    ids, groups, split_of_owner = {}, defaultdict(list), {}
    forbidden = set(forbidden_owners)
    for r in rows:
        missing = [k for k in REQUIRED if k not in r]
        if missing:
            raise ContractError(f"{r.get('example_id')}: missing {missing}")
        if r['example_id'] in ids:
            raise ContractError('duplicate example_id ' + r['example_id'])
        if r['split'] not in ('fit', 'tune') or r['origin'] not in ('natural', 'constructed') \
                or r['behavior'] not in BEHAVIORS:
            raise ContractError(r['example_id'] + ': split/origin/behavior vocabulary')
        if r['owner_id'] in forbidden:
            raise ContractError(r['example_id'] + ': owner belongs to a development/confirmation/test family')
        if r['task'].get('persona_group') != r['owner_id'] or r['task'].get('options'):
            raise ContractError(r['example_id'] + ': task owner mismatch or MCQ options in training input')
        if split_of_owner.setdefault(r['owner_id'], r['split']) != r['split']:
            raise ContractError('owner ' + r['owner_id'] + ' appears in both fit and tune')
        if not isinstance(r['target'], str) or not r['target'].strip():
            raise ContractError(r['example_id'] + ': empty target')
        ids[r['example_id']] = r
        groups[r['group_id']].append(r)
    pairs = []
    for r in rows:
        c = r['contrast']
        opp = c.get('opposite_example_id')
        if opp is None:
            if c.get('unique_opposite'):
                raise ContractError(r['example_id'] + ': unique_opposite without an opposite example')
            continue
        o = ids.get(opp)
        if o is None or o['group_id'] != r['group_id']:
            raise ContractError(r['example_id'] + ': opposite must exist in the same group')
        if c.get('unique_opposite'):
            if o['behavior'] == r['behavior'] or o['target'] == r['target']:
                raise ContractError(r['example_id'] + ': a unique opposite must be a different behaviour')
            pairs.append((r['example_id'], opp))
    return dict(examples=len(rows), groups=len(groups), owners=len(split_of_owner),
                split=dict(Counter(r['split'] for r in rows)), origin=dict(Counter(r['origin'] for r in rows)),
                behavior=dict(Counter(r['behavior'] for r in rows)), unique_opposite_pairs=len(pairs),
                rows_sha256=digest(rows)), pairs


@dataclass(frozen=True)
class Encoded:
    example_id: str
    positive: object            # EncodedResponse for (x, y+)
    negative: object = None     # EncodedResponse for (x, y-) when a unique opposite exists


TURN_END = {'Qwen35': 248046, 'G0e': 106}    # <|im_end|>, <turn|>: the generated end-of-turn markers


def native_encoder(native, turn_end_id, context_limit):
    """encode_one(messages, response) -> EncodedResponse on the inference prompt ids."""
    specials = set(native.tok.all_special_ids)

    def encode_one(messages, response):
        if not isinstance(response, str) or not response.strip():
            raise ValueError('empty response is not supervision')
        prompt = native.chat_ids(messages)
        body = [int(x) for x in native.tok(response, add_special_tokens=False)['input_ids']]
        if not body or any(t in specials for t in body):
            raise ValueError('response includes a control token')
        full = prompt + body + [turn_end_id]
        if len(full) > context_limit:
            raise ValueError('training sequence exceeds the common input cap; no truncation')
        return EncodedResponse(tuple(full), tuple([-100] * len(prompt) + body + [turn_end_id]), len(prompt),
                               len(body) + 1, 0, digest(messages), digest(response))
    return encode_one


def template_encoder(tokenizer, context_limit, eos_token_ids):
    """Historical RL1 path (templates whose history rendering extends the generation prompt)."""
    return lambda m, r: encode_response(tokenizer, m, r, context_limit=context_limit, eos_token_ids=eos_token_ids)


def encode(rows, messages_of, encode_one, *, pairs):
    """messages_of(row) -> exact U0 inference messages for that row (same renderer as evaluation)."""
    by = {r['example_id']: r for r in rows}
    neg = dict(pairs)
    out = []
    for r in rows:
        msgs = messages_of(r)
        pos = encode_one(msgs, r['target'])
        n = encode_one(msgs, by[neg[r['example_id']]]['target']) if r['example_id'] in neg else None
        out.append(Encoded(r['example_id'], pos, n))
    return out


def _mean_logprob(model, enc, pad, device):
    torch = __import__('torch')
    b = collate_responses([enc], pad_token_id=pad)
    t = {k: torch.tensor(v, device=device) for k, v in b.items()}
    logits = model(input_ids=t['input_ids'], attention_mask=t['attention_mask']).logits
    nll, n = response_nll_sum(logits, t['labels'])
    return -nll / n


def train(model, encoded, cfg, *, pad_token_id, device='cpu', clock=time.monotonic, max_steps=None,
          max_seconds=None, on_epoch=None):
    """cfg: mode sft|paired, lr, epochs, accumulation, seed, margin, lambda_pair. Returns a receipt.
    Microbatch is 1 sequence (no cross-example padding); accumulation groups set the step size."""
    import torch
    from . import lora as LORA
    if cfg['mode'] not in ('sft', 'paired'):
        raise ValueError('mode')
    torch.manual_seed(cfg['seed'])
    params = [p for _, p in LORA.trainable(model)]
    if not params:
        raise ValueError('no trainable adapter parameters')
    opt = torch.optim.AdamW(params, lr=cfg['lr'], betas=(.9, .999), eps=1e-8, weight_decay=0.)
    t0, step, log = clock(), 0, []
    tokens = dict(positive=0, negative=0)
    stop = None
    for epoch in range(cfg['epochs']):
        order = list(range(len(encoded)))
        random.Random(cfg['seed'] * 1000 + epoch).shuffle(order)
        model.train()
        for g in range(0, len(order), cfg['accumulation']):
            group = [encoded[i] for i in order[g:g + cfg['accumulation']]]
            denom = sum(e.positive.target_tokens for e in group)
            opt.zero_grad(set_to_none=True)
            nll_sum, hinge_sum, n_pairs = 0., 0., sum(e.negative is not None for e in group)
            for e in group:
                b = collate_responses([e.positive], pad_token_id=pad_token_id)
                t = {k: torch.tensor(v, device=device) for k, v in b.items()}
                logits = model(input_ids=t['input_ids'], attention_mask=t['attention_mask']).logits
                nll, n = response_nll_sum(logits, t['labels'])
                loss = nll / denom
                tokens['positive'] += len(e.positive.input_ids)
                if cfg['mode'] == 'paired' and e.negative is not None:
                    lp_pos = -nll / n
                    lp_neg = _mean_logprob(model, e.negative, pad_token_id, device)
                    hinge = torch.clamp(cfg['margin'] - (lp_pos - lp_neg), min=0.)
                    loss = loss + cfg['lambda_pair'] * hinge / n_pairs
                    hinge_sum += float(hinge)
                    tokens['negative'] += len(e.negative.input_ids)
                loss.backward()
                nll_sum += float(nll)
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            step += 1
            log.append(dict(step=step, epoch=epoch, nll_per_token=nll_sum / denom,
                            hinge_mean=(hinge_sum / n_pairs) if n_pairs and cfg['mode'] == 'paired' else None))
            if max_steps is not None and step >= max_steps:
                stop = 'max_steps'; break
            if max_seconds is not None and clock() - t0 >= max_seconds:
                stop = 'max_seconds'; break
        if on_epoch:
            on_epoch(epoch, step)
        if stop:
            break
    return dict(version=TRAINER_VERSION, mode=cfg['mode'], steps=step, stop=stop or 'epochs_done',
                seconds=round(clock() - t0, 3), tokens=tokens, log=log, cfg=cfg)


def estimate(*, base_params, lora_params, weight_bytes, examples, mean_tokens, epochs, accumulation,
             train_tokens_per_s, paired_fraction=0., mode='sft'):
    """Planning arithmetic only (verified by the approved technical smoke, never a result).
    Memory: bf16 weights + fp32 LoRA params/grads/2 Adam moments; activations bounded by
    sequence length with gradient checkpointing (reported separately as a measured smoke item)."""
    neg = paired_fraction * examples if mode == 'paired' else 0.
    per_epoch_tokens = (examples + neg) * mean_tokens
    return dict(weights_GB=round(weight_bytes / 1e9, 2), lora_state_GB=round(lora_params * 16 / 1e9, 3),
                steps=epochs * -(-examples // accumulation), tokens_per_epoch=int(per_epoch_tokens),
                train_seconds=int(epochs * per_epoch_tokens / train_tokens_per_s),
                assumption=f'{train_tokens_per_s} train tok/s (fwd+bwd+recompute ~= 4x measured prefill)')


# ---------------------------------------------------------------- v1.1: A's U2/U3 objective (data.training_objective)
def group_order(rows, seed):
    """A's rule: groups in a fixed hash order, every variant kept, identical for U2 and U3."""
    import hashlib
    groups = defaultdict(list)
    for r in rows:
        groups[r['group_id']].append(r)
    key = lambda g: hashlib.sha256(f'{seed}|{g}'.encode()).hexdigest()
    return [r for g in sorted(groups, key=key) for r in groups[g]]


def _tail_logits(model, ids, keep):
    """Logits for the last `keep` positions only (identical values, far less memory than the full
    vocabulary over the whole sequence); falls back to slicing when logits_to_keep is unsupported."""
    try:
        return model(input_ids=ids, logits_to_keep=keep).logits[:, -keep:]
    except TypeError:
        return model(input_ids=ids).logits[:, -keep:]


def branch_terms(model, e, device):
    """Three forward branches per example (both methods): chosen-sequence SFT, chosen action, rejected action."""
    import torch
    from ..data.training_objective import masked_action_logp
    ids = torch.tensor([e['input_ids']], device=device)
    labels = torch.tensor([e['labels']], device=device)
    n_t = int((labels != -100).sum())
    lg = _tail_logits(model, ids, n_t + 1)
    tgt = labels[:, -n_t:]
    sft = torch.nn.functional.cross_entropy(lg[:, :-1].float().reshape(-1, lg.shape[-1]), tgt.reshape(-1))
    out = [sft.reshape(1)]
    for k in ('chosen_action', 'rejected_action'):
        a = e[k]
        k_ids = torch.tensor([a['input_ids']], device=device)
        mask = torch.tensor([a['action_mask']], device=device)
        keep = len(a['input_ids']) - a['action_mask'].index(1) + 1
        tl = _tail_logits(model, k_ids, keep)
        out.append(masked_action_logp(tl.float(), k_ids[:, -keep:], mask[:, -keep:]))
    return out, dict(tokens=len(e['input_ids']) + len(e['chosen_action']['input_ids']) + len(e['rejected_action']['input_ids']),
                     target_tokens=n_t)


def group_loss_terms(sft, chosen, rejected, pair_mask, *, method, weight, margin, group_size, group_pairs):
    """Per-example share of A's objective over one accumulation group: summing these over the group equals
    objective(stack(sft), stack(chosen), stack(rejected), stack(mask)) exactly (tested), so microbatch-1
    backward reproduces the group objective without holding every graph."""
    import torch.nn.functional as F
    if method == 'U2':
        return sft / group_size + 0. * (chosen + rejected) / group_size   # same three branches, zero-weight aux
    pair = F.softplus(margin - chosen + rejected) * float(pair_mask)
    return sft / group_size + weight * pair / max(group_pairs, 1)


def train_v11(model, encoded, cfg, *, device='cpu', clock=time.monotonic, max_steps=None, max_seconds=None):
    """cfg (A TRAINING_CANDIDATE): method U2|U3, learning_rate, weight_decay, warmup_steps, gradient_accumulation,
    pair_weight, pair_margin, seed. Linear warmup to the base LR, then constant (A specifies no decay)."""
    import torch
    from . import lora as LORA
    torch.manual_seed(cfg['seed'])
    params = [p for _, p in LORA.trainable(model)]
    opt = torch.optim.AdamW(params, lr=cfg['learning_rate'], betas=(.9, .999), eps=1e-8, weight_decay=cfg['weight_decay'])
    acc, t0, step, log, stop = cfg['gradient_accumulation'], clock(), 0, [], None
    tokens = dict(processed=0, target=0)
    model.train()
    for g in range(0, len(encoded), acc):
        group = encoded[g:g + acc]
        pairs = sum(bool(e['pair_loss_mask']) for e in group)
        for pg in opt.param_groups:
            pg['lr'] = cfg['learning_rate'] * min(1., (step + 1) / max(1, cfg['warmup_steps']))
        opt.zero_grad(set_to_none=True)
        total = 0.
        for e in group:
            (sft, ch, rj), info = branch_terms(model, e, device)
            loss = group_loss_terms(sft, ch, rj, e['pair_loss_mask'], method=cfg['method'], weight=cfg['pair_weight'],
                                    margin=cfg['pair_margin'], group_size=len(group), group_pairs=pairs)
            loss.sum().backward()
            total += float(loss.sum())
            tokens['processed'] += info['tokens']; tokens['target'] += info['target_tokens']
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        step += 1
        log.append(dict(step=step, loss=total, lr=opt.param_groups[0]['lr']))
        if max_steps is not None and step >= max_steps:
            stop = 'max_steps'; break
        if max_seconds is not None and clock() - t0 >= max_seconds:
            stop = 'max_seconds'; break
    return dict(version=TRAINER_VERSION + '+a-v11-objective', method=cfg['method'], steps=step,
                stop=stop or 'epoch_done', seconds=round(clock() - t0, 3), tokens=tokens, log=log)


# ---------------------------------------------------------------- 2026-11-28: reply-level supervision (main WP4 path)
# U2 = ordinary reply-level SFT on the official reply; U3 = the same SFT + a reply-level ranking term
# (official reply vs official non-preferred replies under the SAME prompt). Both methods run the same
# forward/backward branches (U2's ranking coefficient is 0), the same data order, seed, adapter init,
# optimizer and step count. No USE/IGNORE/CLARIFY template, no state classifier.
REPLY_SCHEMA = 'naa-wp4-reply-v1'
REPLY_TRAINER_VERSION = 'naa-wp4-reply-trainer-v1'
REPLY_REQUIRED = ('example_id', 'group_id', 'owner_id', 'split', 'messages', 'chosen', 'rejected', 'provenance')


def validate_reply(rows, *, forbidden_owners=(), allow_plumbing=False):
    """Structural/leakage contract of A's reply rows (labels/quality are A's audit). PLUMBING rows (placeholder
    replies for length/encoding checks) are accepted only by CPU checks, never by training."""
    seen, split_of_owner, forbidden = set(), {}, set(forbidden_owners)
    for r in rows:
        missing = [k for k in REPLY_REQUIRED if k not in r]
        if missing:
            raise ContractError(f"{r.get('example_id')}: missing {missing}")
        if r['provenance'].get('plumbing') and not allow_plumbing:
            raise ContractError(r['example_id'] + ': PLUMBING row is never supervision')
        if r['example_id'] in seen:
            raise ContractError('duplicate example_id ' + r['example_id'])
        seen.add(r['example_id'])
        if r['split'] not in ('fit', 'tune'):
            raise ContractError(r['example_id'] + ': split must be fit|tune')
        if r['owner_id'] in forbidden:
            raise ContractError(r['example_id'] + ': owner belongs to a development/confirmation/test family')
        if split_of_owner.setdefault(r['owner_id'], r['split']) != r['split']:
            raise ContractError('owner ' + r['owner_id'] + ' appears in both fit and tune')
        m = r['messages']
        if not m or m[-1]['role'] != 'user' or any(x['role'] not in ('system', 'user', 'assistant') for x in m):
            raise ContractError(r['example_id'] + ': prompt must end with the user turn')
        if any('Final Answer:' in x['content'] for x in m):
            raise ContractError(r['example_id'] + ': MCQ answer instruction inside a reply-training prompt')
        reps = [r['chosen'], *r['rejected']]
        if not all(isinstance(x, str) and x.strip() for x in reps) or len(set(reps)) != len(reps):
            raise ContractError(r['example_id'] + ': empty or repeated reply')
    ranked = sum(bool(r['rejected']) for r in rows)
    return dict(schema=REPLY_SCHEMA, examples=len(rows), owners=len(split_of_owner),
                groups=len({r['group_id'] for r in rows}), split=dict(Counter(r['split'] for r in rows)),
                with_rejected=ranked, rejected_per_row=dict(Counter(len(r['rejected']) for r in rows)),
                rows_sha256=digest(rows))


def encode_reply(rows, encode_one, *, eos_ids, turn_end_id):
    """Encode every reply on the exact inference prompt; returns (encoded, alignment receipt)."""
    out, prompts = [], Counter()
    for r in rows:
        ch = encode_one(r['messages'], r['chosen'])
        rj = [encode_one(r['messages'], x) for x in r['rejected']]
        for e in (ch, *rj):
            if e.input_ids[-1] != turn_end_id or e.input_ids[:e.prompt_tokens] != ch.input_ids[:ch.prompt_tokens]:
                raise ContractError(r['example_id'] + ': prompt/turn-end differs between replies')
        prompts[ch.prompt_tokens] += 1
        out.append(dict(example_id=r['example_id'], chosen=ch, rejected=rj))
    if turn_end_id not in eos_ids:
        raise ContractError('training turn end is not an inference stop token')
    lens = sorted(len(e['chosen'].input_ids) for e in out)
    return out, dict(prompt_equals_inference_chat_ids=True, ends_with_turn_end=turn_end_id, turn_end_in_decode_eos=True,
                     rows=len(out), chosen_len_p50=lens[len(lens) // 2] if lens else None, chosen_len_max=lens[-1] if lens else None,
                     branch_tokens=sum(len(e['chosen'].input_ids) + sum(len(x.input_ids) for x in e['rejected']) for e in out))


def _reply_logp(model, enc, device):
    """(nll_sum, mean token log-prob) of one reply under its prompt, logits for the reply positions only."""
    import torch
    ids = torch.tensor([list(enc.input_ids)], device=device)
    n = enc.target_tokens
    lg = _tail_logits(model, ids, n + 1)[:, :-1].float()
    tgt = ids[:, -n:]
    lp = torch.log_softmax(lg, -1).gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
    return -lp.sum(), lp.mean()


def reply_loss(sft, lp_chosen, lp_rejected, *, method, weight, margin):
    """U2: sft (+ 0 x ranking); U3: sft + weight * mean_j softplus(margin - (lp_c - lp_j)). Mean token log-probs."""
    import torch
    import torch.nn.functional as F
    if not lp_rejected:
        return sft
    rank = torch.stack([F.softplus(margin - (lp_chosen - x)) for x in lp_rejected]).mean()
    return sft + (0. if method == 'U2' else weight) * rank


class TrainStop(RuntimeError):
    def __init__(self, reason):
        super().__init__(reason); self.reason = reason


class TrainGuard:
    """Hard bound for one training process. check() runs before EVERY branch forward (not only at the end
    of an optimizer step); the watchdog kills the process at the hard deadline even if a call hangs.
    Times are on the monotonic clock from the moment the exclusive GPU lock was taken."""

    def __init__(self, *, started, max_seconds, save_reserve, close_reserve, storage=None, device=None,
                 guard_every=25, clock=time.monotonic, on_kill=None, watchdog=True):
        self.clock, self.started = clock, started
        self.hard = started + max_seconds - close_reserve           # process must be gone after this
        self.train_end = self.hard - save_reserve                   # last moment a new forward may start
        self.storage, self.device, self.every, self.calls = storage, device, guard_every, 0
        self.on_kill = on_kill
        if watchdog:
            import threading
            self._t = threading.Thread(target=self._watch, daemon=True); self._t.start()

    def _watch(self):
        import os
        import signal
        while True:
            left = self.hard - self.clock()
            if left <= 0:
                if self.on_kill:
                    try:
                        self.on_kill()
                    finally:
                        os.kill(os.getpid(), signal.SIGKILL)
                os.kill(os.getpid(), signal.SIGKILL)
            time.sleep(min(1., max(left, 0.01)))

    def elapsed(self):
        return self.clock() - self.started

    def left(self):
        return self.train_end - self.clock()

    def check(self):
        self.calls += 1
        if self.clock() >= self.train_end:
            raise TrainStop('hard deadline (save/close reserve)')
        if self.calls % self.every == 0:
            if self.storage:
                self.storage()
            if self.device:
                self.device()


SMOKE_STEPS = 20


def evaluate_smoke(log, *, planned_steps, guard, peak_bytes=None, peak_cap_bytes=46 * 2 ** 30, base_grads=0):
    """Technical only: finite losses and grad norms, adapter-only gradients, memory and projected time.
    Never looks at development accuracy or task outputs."""
    import math as _m
    w = log[:SMOKE_STEPS]
    sec = [x['seconds'] for x in w]
    per = sorted(sec)[len(sec) // 2] if sec else None
    projected = guard.elapsed() + per * (planned_steps - len(w)) if per is not None else None
    checks = dict(steps=len(w) == SMOKE_STEPS, finite_loss=all(_m.isfinite(x['loss']) for x in w),
                  finite_grad=all(_m.isfinite(x['grad_norm']) for x in w), nonzero_grad=all(x['grad_norm'] > 0 for x in w),
                  adapter_only=base_grads == 0,
                  memory=peak_bytes is None or peak_bytes <= peak_cap_bytes,
                  time=projected is not None and guard.started + projected <= guard.train_end)
    return dict(passed=all(checks.values()), checks=checks, step_seconds_p50=per, projected_total_seconds=projected,
                peak_reserved_bytes=peak_bytes, scope='technical smoke: run/memory/gradients/finite/speed/budget only')


def train_reply(model, encoded, cfg, *, guard, device='cpu', clock=time.monotonic, max_steps, log_path=None,
                peak=lambda: None, smoke_steps=SMOKE_STEPS):
    """cfg: method U2|U3, learning_rate, weight_decay, warmup_steps, gradient_accumulation, rank_weight,
    rank_margin, seed. Data order is the caller's (identical for U2/U3). Returns the receipt; raises nothing on
    a typed stop (deadline / smoke failure / max_steps): the caller saves what was trained and records why."""
    import json as _json
    import torch
    from . import lora as LORA
    if cfg['method'] not in ('U2', 'U3'):
        raise ValueError('method must be U2 or U3')
    torch.manual_seed(cfg['seed'])
    named = LORA.trainable(model)
    params = [p for _, p in named]
    if not params or any('.lora_' not in n for n, _ in named):
        raise ValueError('only adapter parameters may be trainable')
    opt = torch.optim.AdamW(params, lr=cfg['learning_rate'], betas=(.9, .999), eps=1e-8, weight_decay=cfg['weight_decay'])
    acc, step, log, stop, smoke = cfg['gradient_accumulation'], 0, [], None, None
    tokens = dict(processed=0, chosen_target=0)
    sink = open(log_path, 'a') if log_path else None
    model.train()
    try:
        for g in range(0, len(encoded), acc):
            if step >= max_steps:
                stop = 'max_steps'; break
            s0 = clock()
            group = encoded[g:g + acc]
            denom = sum(e['chosen'].target_tokens for e in group)
            for pg in opt.param_groups:
                pg['lr'] = cfg['learning_rate'] * min(1., (step + 1) / max(1, cfg['warmup_steps']))
            opt.zero_grad(set_to_none=True)
            total = 0.
            for e in group:
                guard.check()
                nll, lp_c = _reply_logp(model, e['chosen'], device)
                lps = []
                for x in e['rejected']:
                    guard.check()
                    lps.append(_reply_logp(model, x, device)[1])
                loss = reply_loss(nll / denom, lp_c, lps, method=cfg['method'], weight=cfg['rank_weight'] / len(group),
                                  margin=cfg['rank_margin'])
                loss.backward()
                total += float(loss)
                tokens['processed'] += len(e['chosen'].input_ids) + sum(len(x.input_ids) for x in e['rejected'])
                tokens['chosen_target'] += e['chosen'].target_tokens
            gn = float(torch.nn.utils.clip_grad_norm_(params, 1.0))
            opt.step()
            step += 1
            entry = dict(step=step, loss=total, grad_norm=gn, lr=opt.param_groups[0]['lr'], seconds=clock() - s0,
                         elapsed=guard.elapsed())
            log.append(entry)
            if sink:
                sink.write(_json.dumps(entry) + '\n'); sink.flush()
            if step == smoke_steps and smoke is None:
                base_grads = sum(p.grad is not None for n, p in model.named_parameters() if '.lora_' not in n)
                smoke = evaluate_smoke(log, planned_steps=min(max_steps, -(-len(encoded) // acc)), guard=guard,
                                       peak_bytes=peak(), base_grads=base_grads)
                if not smoke['passed']:
                    stop = 'technical smoke failed'; break
    except TrainStop as exc:
        stop = exc.reason
    finally:
        if sink:
            sink.close()
    return dict(version=REPLY_TRAINER_VERSION, method=cfg['method'], steps=step, stop=stop or 'epoch_done',
                seconds=round(guard.elapsed(), 3), tokens=tokens, smoke=smoke, log=log, cfg=cfg)
