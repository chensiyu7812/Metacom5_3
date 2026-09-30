"""Small, fully specified PPO learning diagnostic. No real q/m or LLM calls.

Toy observations encode public task categories, acquired counts and budgets.
This is not the production BGE observation encoder or a trained PM checkpoint.
"""
from dataclasses import dataclass
from functools import lru_cache
import random

import torch
from torch import nn
from torch.distributions import Categorical


CASES = ('no_resource', 'one_helpful', 'two_complementary', 'harmful_distractor', 'budget_mask')


@dataclass(frozen=True)
class ToyState:
    case: int
    counts: tuple = (0, 0, 0, 0)

    @property
    def budget(self):
        return 2 if self.case == 4 else 4

    @property
    def costs(self):
        return (3, 1, 1, 1) if self.case == 4 else (1, 1, 1, 1)

    @property
    def used(self):
        return sum(n * c for n, c in zip(self.counts, self.costs))

    def mask(self):
        return [True] + [sum(self.counts) < 4 and n < 2 and self.used + c <= self.budget
                         for n, c in zip(self.counts, self.costs)]

    def observation(self):
        return [float(i == self.case) for i in range(5)] + [n / 2 for n in self.counts] + [self.used / self.budget, sum(self.counts) / 4]

    def utility(self):
        rs, mp, ms, me = self.counts
        return (1., float(rs >= 1), 1. if mp >= 2 else -.1 if mp else 0.,
                .8 * float(ms >= 1) - .5 * float(me >= 1), .7 * float(mp >= 1))[self.case]

    def step(self, action):
        if not 0 <= action < 5 or not self.mask()[action]:
            raise ValueError('illegal toy action')
        if action == 0:
            return self, self.utility() - ToyState(self.case).utility(), True
        counts = list(self.counts); counts[action - 1] += 1
        nxt = ToyState(self.case, tuple(counts))
        return nxt, -.05 * (nxt.used - self.used) / self.budget, False


@lru_cache(None)
def exact_value(state, uniform=False):
    values = []
    for action, legal in enumerate(state.mask()):
        if legal:
            nxt, reward, done = state.step(action)
            values.append(reward + (0. if done else exact_value(nxt, uniform)))
    return sum(values) / len(values) if uniform else max(values)


class ToyActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(11, 128), nn.Tanh(), nn.Linear(128, 128), nn.Tanh(), nn.Linear(128, 128), nn.Tanh())
        self.policy = nn.Linear(128, 5)
        self.value = nn.Linear(128, 1)

    def forward(self, observations, masks):
        if observations.shape[-1] != 11 or masks.shape[-1] != 5 or not masks.any(dim=-1).all():
            raise ValueError('invalid toy observation/mask')
        hidden = self.body(observations)
        logits = self.policy(hidden).masked_fill(~masks, -torch.inf)
        return Categorical(logits=logits), self.value(hidden).squeeze(-1)


def rollout(model, case, version, greedy=False):
    state, transitions = ToyState(case), []
    while True:
        obs = torch.tensor(state.observation(), dtype=torch.float32)
        mask = torch.tensor(state.mask(), dtype=torch.bool)
        with torch.no_grad():
            dist, value = model(obs, mask)
            action = dist.probs.argmax() if greedy else dist.sample()
        nxt, reward, done = state.step(int(action))
        transitions.append(dict(observation=obs, mask=mask, action=action.detach(),
                                old_log_prob=dist.log_prob(action).detach(), old_value=value.detach(),
                                reward=reward, done=done, forced=int(mask.sum()) == 1))
        state = nxt
        if done:
            break
        if len(transitions) > 4:
            raise RuntimeError('toy horizon exceeded')
    # gamma=1 and GAE lambda=1: Monte Carlo terminal return minus old value.
    remaining = 0.
    for transition in reversed(transitions):
        remaining += transition['reward']
        transition['return'] = remaining
        transition['advantage'] = remaining - float(transition['old_value'])
    return dict(case=case, policy_version=version, complete=True, transitions=transitions,
                total_return=sum(t['reward'] for t in transitions), final_counts=state.counts)


class PPO:
    def __init__(self, model):
        self.model = model
        self.optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
        self.version = 0

    def update(self, episodes):
        if len(episodes) != 16 or any(not e['complete'] or e['policy_version'] != self.version for e in episodes):
            raise ValueError('requires 16 complete episodes from the current frozen behavior policy')
        for episode in episodes:
            ts = episode['transitions']
            if not ts or not ts[-1]['done'] or any(t['done'] for t in ts[:-1]):
                raise ValueError('invalid terminal trajectory')
        free_advantages = torch.tensor([t['advantage'] for e in episodes for t in e['transitions'] if not t['forced']])
        mean = free_advantages.mean() if free_advantages.numel() else torch.tensor(0.)
        scale = free_advantages.std(unbiased=False).clamp_min(1e-8) if free_advantages.numel() else torch.tensor(1.)
        losses, max_before_update_log_error = [], 0.
        with torch.no_grad():
            for e in episodes:
                ts = e['transitions']
                dist, _ = self.model(torch.stack([t['observation'] for t in ts]), torch.stack([t['mask'] for t in ts]))
                error = (dist.log_prob(torch.stack([t['action'] for t in ts])) - torch.stack([t['old_log_prob'] for t in ts])).abs().max()
                max_before_update_log_error = max(max_before_update_log_error, float(error))
        if max_before_update_log_error > 1e-5:
            raise ValueError('behavior policy changed during collection')
        for _ in range(4):
            order = torch.randperm(len(episodes)).tolist()
            for start in range(0, len(order), 4):
                ts = [t for i in order[start:start + 4] for t in episodes[i]['transitions']]
                dist, values = self.model(torch.stack([t['observation'] for t in ts]), torch.stack([t['mask'] for t in ts]))
                free = torch.tensor([not t['forced'] for t in ts])
                actions = torch.stack([t['action'] for t in ts])
                ratio = (dist.log_prob(actions) - torch.stack([t['old_log_prob'] for t in ts])).exp()
                adv = (torch.tensor([t['advantage'] for t in ts]) - mean) / scale
                policy_loss = -torch.minimum(ratio[free] * adv[free], ratio[free].clamp(.8, 1.2) * adv[free]).mean() if free.any() else values.sum() * 0.
                entropy = dist.entropy()[free].mean() if free.any() else values.sum() * 0.
                value_loss = (values - torch.tensor([t['return'] for t in ts])).square().mean()
                loss = policy_loss + .5 * value_loss - .01 * entropy
                self.optimizer.zero_grad(); loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), .5)
                self.optimizer.step()
                losses.append(float(loss.detach()))
        self.version += 1
        return dict(mean_loss=sum(losses) / len(losses), behavior_log_probability_max_error=max_before_update_log_error)

    def save(self, path, rng, episodes):
        torch.save(dict(model=self.model.state_dict(), optimizer=self.optimizer.state_dict(),
                        version=self.version, torch_rng=torch.get_rng_state(), python_rng=rng.getstate(), episodes=episodes), path)

    def restore(self, path, rng):
        state = torch.load(path, map_location='cpu', weights_only=False)
        self.model.load_state_dict(state['model']); self.optimizer.load_state_dict(state['optimizer'])
        self.version = state['version']; torch.set_rng_state(state['torch_rng']); rng.setstate(state['python_rng'])
        return state['episodes']


def evaluate(model, version):
    return [dict(case=name, greedy_return=(e := rollout(model, i, version, greedy=True))['total_return'],
                 acquired=e['final_counts'], oracle_return=exact_value(ToyState(i)),
                 uniform_random_expected_return=exact_value(ToyState(i), True), always_stop_return=0.)
            for i, name in enumerate(CASES)]
