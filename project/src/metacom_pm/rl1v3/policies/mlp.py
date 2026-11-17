"""Two-layer MLP policies (V3.1 §6.10: 512 -> 256) with masked action logits."""
from __future__ import annotations

import torch
from torch import nn

from ..env import finite_head as E

NEG = -1e9


def mlp(inp: int, out: int, act=nn.Tanh) -> nn.Sequential:
    return nn.Sequential(nn.Linear(inp, 512), act(), nn.Linear(512, 256), act(),
                         nn.Linear(256, out))


def masked_logits(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    if not bool(mask.any(-1).all()):
        raise ValueError("every state needs at least one legal action")
    return logits.masked_fill(~mask, NEG)


class ActorCritic(nn.Module):
    def __init__(self, obs_dim: int):
        super().__init__()
        self.actor = mlp(obs_dim, len(E.ACTIONS))
        self.critic = mlp(obs_dim, 1)

    def dist(self, x: torch.Tensor, mask: torch.Tensor) -> torch.distributions.Categorical:
        return torch.distributions.Categorical(logits=masked_logits(self.actor(x), mask))

    def value(self, x: torch.Tensor) -> torch.Tensor:
        return self.critic(x).squeeze(-1)


class OneShotNet(nn.Module):
    """Initial observation -> one of the 16 subsets (committed up front)."""
    def __init__(self, obs_dim: int):
        super().__init__()
        self.net = mlp(obs_dim, E.N_SUBSETS, act=nn.ReLU)

    def forward(self, x: torch.Tensor, subset_mask: torch.Tensor) -> torch.Tensor:
        return masked_logits(self.net(x), subset_mask)
