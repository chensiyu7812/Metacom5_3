"""Private episode data and a separate actor/critic whitelist.

No arbitrary dictionaries or provenance identifiers cross the observation boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from hashlib import sha256
from itertools import product
import json
import math

HEADS = ("RS", "MP", "MS", "ME")
Counts = tuple[int, int, int, int]
PLANS: tuple[Counts, ...] = tuple(sorted(
    (p for p in product(range(5), repeat=4) if sum(p) <= 4),
    key=lambda p: (sum(p), p),
))


def digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Action(IntEnum):
    STOP = 0
    GET_RS = 1
    GET_MP = 2
    GET_MS = 3
    GET_ME = 4


@dataclass(frozen=True)
class PublicTurn:
    role: str
    content: str

    def __post_init__(self):
        if self.role not in ("seeker", "supporter") or not self.content.strip():
            raise ValueError("invalid public turn")


@dataclass(frozen=True)
class PrefixSpec:
    owner_id: str
    session_id: str
    cutoff_rank: int
    cut_after_turn_index: int
    timestamp: str
    split: str
    turns: tuple[PublicTurn, ...]

    def __post_init__(self):
        if not self.turns or self.turns[-1].role != "seeker":
            raise ValueError("prefix must end immediately before a supporter reply")
        if self.cutoff_rank < 1 or self.split not in ("train", "dev", "test"):
            raise ValueError("invalid memory prefix")

    @property
    def identity(self) -> str:
        return digest(asdict(self))

    @property
    def query(self) -> str:
        return "\n".join(f"{t.role}: {t.content}" for t in self.turns)


@dataclass(frozen=True)
class Resource:
    candidate_id: str
    head: str
    content: str
    similarity: float
    raw_tokens: int
    owner_id: str | None
    source_rank: int | None
    source_time: str | None
    coarse_age: str
    source_ids: tuple[str, ...]

    def __post_init__(self):
        if self.head not in HEADS or not self.content.strip():
            raise ValueError("invalid resource")
        if not math.isfinite(self.similarity) or self.raw_tokens < 0:
            raise ValueError("invalid frozen metadata")


@dataclass(frozen=True)
class EpisodeSpec:
    prefix: PrefixSpec
    inventory: tuple[tuple[Resource, ...], ...]
    retrieval_identity: str
    executor_identity: str
    judge_identity: str
    draw_identity: str
    resource_budget: int = 2048
    alpha: float = 1.0
    cost_weight: float = .05

    def __post_init__(self):
        if len(self.inventory) != 4 or self.resource_budget <= 0:
            raise ValueError("invalid inventory/budget")
        if not all((self.retrieval_identity, self.executor_identity,
                    self.judge_identity, self.draw_identity)):
            raise ValueError("missing immutable identity")
        if not all(math.isfinite(x) and x >= 0 for x in (self.alpha, self.cost_weight)):
            raise ValueError("invalid reward coefficients")
        ids = set()
        for head, items in zip(HEADS, self.inventory):
            if tuple(items) != tuple(sorted(items, key=lambda r: (-r.similarity, r.candidate_id))):
                raise ValueError("inventory must be frozen cosine/id order")
            for r in items:
                if r.head != head or r.candidate_id in ids:
                    raise ValueError("head mismatch or duplicate item")
                ids.add(r.candidate_id)
                if head != "RS" and (r.owner_id != self.prefix.owner_id or
                        r.source_rank is None or not 0 <= r.source_rank < self.prefix.cutoff_rank):
                    raise ValueError("wrong-owner or non-past memory")

    @property
    def identity(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class CandidateMetadata:
    rank: int
    similarity: float
    raw_tokens: int
    coarse_age: str


@dataclass(frozen=True)
class AcquiredText:
    head: str
    rank: int
    content: str
    source_time: str | None


@dataclass(frozen=True)
class Observation:
    current_prefix: tuple[PublicTurn, ...]
    acquired: tuple[AcquiredText, ...]
    counts: Counts
    remaining_tokens: int
    remaining_gets: int
    remaining_items: Counts
    metadata: tuple[tuple[CandidateMetadata | None, ...], ...]
    action_mask: tuple[bool, ...]
    initial_plan_mask: tuple[bool, ...]


@dataclass(frozen=True)
class Score:
    q: int
    misuse: float
    evidence: tuple[str, ...]
    uncertain: bool = False

    def __post_init__(self):
        if type(self.q) is not int or self.q not in range(5) or self.misuse not in (0, .25, 1):
            raise ValueError("score is outside the frozen q/m scale")
        if not self.evidence:
            raise ValueError("score needs inspectable evidence")

    def utility(self, alpha: float) -> float:
        return self.q / 4 - alpha * self.misuse
