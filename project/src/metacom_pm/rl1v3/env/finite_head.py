"""B5 core: Phase-1 FiniteHead GET/STOP transitions, masks and exact DP.

Contract-agnostic on purpose (C0 0.1.0 is under review, see
outputs/pm_rl1/v3/C0_review).  Shared types enter only through injected
callables:

* ``reader(head) -> ReadUnit | None``: WS-A ``retrieve.read`` for the static
  query; the only side effect a GET may have.  GET never calls G or a judge.
* ``observation_factory(**visible) -> obj``: becomes ``contracts.Observation``
  once C0 is frozen; tests use a dict.
* ``terminal_lookup(mask) -> TerminalOutcome``: versioned terminal table keyed
  by the acquired subset (C0 TerminalKey in production).  A missing terminal is
  *pending* and raises; it is never a zero reward.

Rules (V3.1 §6.9 Phase-1, RESOURCE_SPEC §5):
* actions STOP, GET_RS, GET_MP, GET_ME, GET_MS; each head at most once; the
  terminal depends only on the acquired subset (canonical head order);
* illegal actions (masked, repeated, empty head, over capacity/budget, after
  STOP) raise ``IllegalAction`` and leave state unchanged;
* reward only at STOP (gamma = 1); optional per-GET step cost for programmatic
  engineering tasks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Mapping, Sequence

HEADS: tuple[str, ...] = ("RS", "MP", "ME", "MS")  # canonical render/terminal order
STOP = "STOP"
GET = {h: f"GET_{h}" for h in HEADS}
HEAD_OF = {v: k for k, v in GET.items()}
ACTIONS: tuple[str, ...] = (STOP,) + tuple(GET[h] for h in HEADS)
BIT = {h: 1 << i for i, h in enumerate(HEADS)}
N_SUBSETS = 1 << len(HEADS)
FULL = N_SUBSETS - 1


class IllegalAction(ValueError):
    pass


class PendingTerminal(LookupError):
    """Terminal not generated/scored yet: pending, never reward zero."""


def heads_of(mask: int) -> tuple[str, ...]:
    return tuple(h for h in HEADS if mask & BIT[h])


def mask_of(heads: Sequence[str]) -> int:
    m = 0
    for h in heads:
        m |= BIT[h]
    return m


def canonical_path(mask: int) -> tuple[str, ...]:
    """Phase-1 terminal identity path: GETs in canonical head order, then STOP."""
    return tuple(GET[h] for h in heads_of(mask)) + (STOP,)


@dataclass(frozen=True)
class ReadUnit:
    """What a successful GET hands to the environment (from WS-A read)."""
    head: str
    reading_text: str
    tokens: int
    record_ids: tuple[str, ...]  # private; goes to TerminalKey, never to Observation
    cost_s: float = 0.0          # measured/predicted retrieval+read latency
    public_view: object = None   # the shared-contract ReadingView, when bound to C0


@dataclass(frozen=True)
class TerminalOutcome:
    reward: float
    key_sha256: str = ""
    detail: Mapping = field(default_factory=dict)


@dataclass(frozen=True)
class State:
    order: tuple[str, ...] = ()           # heads in acquisition order
    readings: tuple[ReadUnit, ...] = ()
    done: bool = False
    elapsed_s: float = 0.0
    input_tokens: int = 0

    @property
    def mask(self) -> int:
        return mask_of(self.order)


class FiniteHeadEnv:
    """``terminal_lookup`` receives the acquired subset mask, or the whole final
    ``State`` when ``lookup_takes_state`` (needed to build a full TerminalKey
    from the delivered record groups)."""

    def __init__(self, *, availability: Mapping[str, int], reader: Callable[[str], ReadUnit | None],
                 terminal_lookup: Callable[..., TerminalOutcome], prefix_tokens: int,
                 token_capacity: int | None = None, max_gets: int = len(HEADS),
                 step_cost: Mapping[str, float] | None = None,
                 unit_tokens: Mapping[str, int] | None = None,
                 observation_factory: Callable[..., object] | None = None,
                 visible_prefix: object = None, lookup_takes_state: bool = False,
                 reader_takes_tokens: bool = False, reader_takes_state: bool = False,
                 dynamic_mask: Callable[[State], object] | None = None):
        unknown = set(availability) - set(HEADS)
        if unknown:
            raise ValueError(f"unknown heads {unknown}")
        self.availability = {h: int(availability.get(h, 0)) for h in HEADS}
        self.reader = reader
        self.terminal_lookup = terminal_lookup
        self.prefix_tokens = prefix_tokens
        self.token_capacity = token_capacity
        self.max_gets = max_gets
        self.step_cost = {h: float((step_cost or {}).get(h, 0.0)) for h in HEADS}
        # private per-head size of the unit a GET would deliver (for capacity masks)
        self.unit_tokens = dict(unit_tokens or {})
        self.observation_factory = observation_factory or (lambda **kw: kw)
        self.visible_prefix = visible_prefix
        self.lookup_takes_state = lookup_takes_state
        # real readers (WS-A retrieve.read) charge against the CURRENT input size
        self.reader_takes_tokens = reader_takes_tokens
        # A1b Reader is stateless: it needs the state's acquired readings (v2 replay)
        self.reader_takes_state = reader_takes_state
        if reader_takes_tokens and reader_takes_state:
            raise ValueError("choose one reader calling convention")
        # dynamic GET legality from the real reader (full chat-template capacity);
        # intersected with the static rules, cached per acquisition order
        self.dynamic_mask = dynamic_mask
        self._dyn_cache: dict[tuple[str, ...], frozenset] = {}

    # ------------------------------------------------------------- masks
    def legal_actions(self, s: State) -> tuple[str, ...]:
        if s.done:
            return ()
        out = [STOP]
        if len(s.order) < self.max_gets:
            for h in HEADS:
                if h in s.order or self.availability[h] <= 0:
                    continue
                if self.token_capacity is not None and h in self.unit_tokens and (
                        s.input_tokens + self.unit_tokens[h] > self.token_capacity):
                    continue
                out.append(GET[h])
        if self.dynamic_mask is not None and len(out) > 1:
            dyn = self._dyn_cache.get(s.order)
            if dyn is None:
                dyn = self._dyn_cache[s.order] = frozenset(self.dynamic_mask(s))
            out = [a for a in out if a == STOP or a in dyn]
        return tuple(out)

    def reset(self) -> State:
        return State(input_tokens=self.prefix_tokens)

    def observe(self, s: State):
        return self.observation_factory(
            prefix=self.visible_prefix,
            acquired=tuple(dict(head=r.head, ordinal=i + 1, reading_text=r.reading_text,
                                tokens=r.tokens) for i, r in enumerate(s.readings)),
            availability=tuple(dict(head=h, available=self.availability[h] > 0,
                                    count=self.availability[h]) for h in HEADS),
            action_mask=self.legal_actions(s),
            input_tokens=s.input_tokens,
        )

    # -------------------------------------------------------- transitions
    def step(self, s: State, action: str) -> tuple[State, float, bool, dict]:
        legal = self.legal_actions(s)
        if action not in legal:
            raise IllegalAction(f"{action} not in {legal}")
        if action == STOP:
            outcome = self.terminal_lookup(s if self.lookup_takes_state else s.mask)
            if outcome is None:
                raise PendingTerminal(canonical_path(s.mask))
            return (State(s.order, s.readings, True, s.elapsed_s, s.input_tokens),
                    float(outcome.reward), True,
                    dict(terminal_mask=s.mask, path=canonical_path(s.mask),
                         key_sha256=outcome.key_sha256))
        head = HEAD_OF[action]
        unit = (self.reader(head, s.input_tokens) if self.reader_takes_tokens
                else self.reader(head, s) if self.reader_takes_state else self.reader(head))
        if unit is None or unit.head != head or not unit.record_ids:
            raise IllegalAction(f"{action}: reader delivered no unit; head must be masked")
        tokens = s.input_tokens + unit.tokens
        if self.token_capacity is not None and tokens > self.token_capacity:
            raise IllegalAction(f"{action}: exceeds native capacity; must be masked")
        nxt = State(s.order + (head,), s.readings + (unit,), False,
                    s.elapsed_s + unit.cost_s, tokens)
        return nxt, -self.step_cost[head], False, dict(head=head, record_ids=unit.record_ids)


# ------------------------------------------------------------------- exact DP

@dataclass(frozen=True)
class DPResult:
    value: Mapping[int, float]                 # optimal value-to-go per reachable subset
    optimal_actions: Mapping[int, tuple[str, ...]]
    optimal_terminals: tuple[int, ...]         # subsets reached by some optimal policy
    root_value: float


def _reachable(available: int, max_gets: int,
               feasible: Callable[[int], bool] | None = None) -> list[int]:
    """Subsets reachable under availability, GET budget and a subset-feasibility
    predicate (e.g. native token capacity; monotone, so order-independent)."""
    heads = heads_of(available)
    out = [mask_of(c) for k in range(min(max_gets, len(heads)) + 1)
           for c in combinations(heads, k)]
    return [m for m in out if feasible is None or feasible(m)]


def solve_dp(terminal_reward: Mapping[int, float], *, available: int = FULL,
             max_gets: int = len(HEADS), step_cost: Mapping[str, float] | None = None,
             feasible: Callable[[int], bool] | None = None, tol: float = 1e-9) -> DPResult:
    """Exact optimal values over the subset lattice; ties within ``tol`` kept."""
    cost = {h: float((step_cost or {}).get(h, 0.0)) for h in HEADS}
    reach = set(_reachable(available, max_gets, feasible))
    states = sorted(reach, key=lambda m: -bin(m).count("1"))
    missing = [m for m in states if m not in terminal_reward]
    if missing:
        raise PendingTerminal(f"terminal rewards missing for subsets {missing}")
    V: dict[int, float] = {}
    best: dict[int, tuple[str, ...]] = {}
    for m in states:
        q = {STOP: float(terminal_reward[m])}
        if bin(m).count("1") < max_gets:
            for h in heads_of(available & ~m):
                if m | BIT[h] in reach:
                    q[GET[h]] = -cost[h] + V[m | BIT[h]]
        v = max(q.values())
        V[m] = v
        best[m] = tuple(a for a in ACTIONS if a in q and q[a] >= v - tol)
    terms: set[int] = set()
    stack = [0]
    seen = set()
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        for a in best[m]:
            if a == STOP:
                terms.add(m)
            else:
                stack.append(m | BIT[HEAD_OF[a]])
    return DPResult(V, best, tuple(sorted(terms)), V[0])


def brute_force_best(terminal_reward: Mapping[int, float], *, available: int = FULL,
                     max_gets: int = len(HEADS), step_cost: Mapping[str, float] | None = None,
                     feasible: Callable[[int], bool] | None = None) -> tuple[float, set[tuple]]:
    """Enumerate every ordered GET sequence (<= 65 paths) as an independent check."""
    from itertools import permutations
    cost = {h: float((step_cost or {}).get(h, 0.0)) for h in HEADS}
    heads = heads_of(available)
    best, paths = float("-inf"), set()
    for k in range(min(max_gets, len(heads)) + 1):
        for seq in permutations(heads, k):
            if feasible is not None and not all(feasible(mask_of(seq[:i + 1]))
                                                for i in range(len(seq))):
                continue
            r = terminal_reward[mask_of(seq)] - sum(cost[h] for h in seq)
            if r > best + 1e-9:
                best, paths = r, {seq}
            elif abs(r - best) <= 1e-9:
                paths.add(seq)
    return best, paths


def interval_dp(lower: Mapping[int, float], upper: Mapping[int, float], **kw) -> dict:
    """Bounds on the optimum when terminal rewards are only known as [L, U].

    Returns root value bounds and, per root action, whether it is certainly
    optimal (its lower bound beats every other action's upper bound) or
    possibly optimal (its upper bound reaches the best lower bound).  Never
    claims an exact optimum when intervals overlap.
    """
    lo, hi = solve_dp(lower, **kw), solve_dp(upper, **kw)
    available = kw.get("available", FULL)
    cost = {h: float((kw.get("step_cost") or {}).get(h, 0.0)) for h in HEADS}

    def q(res, m, a):
        if a == STOP:
            return (lower if res is lo else upper)[m]
        return -cost[HEAD_OF[a]] + res.value[m | BIT[HEAD_OF[a]]]

    acts = [STOP] + [GET[h] for h in heads_of(available)
                     if kw.get("max_gets", len(HEADS)) > 0 and BIT[h] in lo.value]
    ql = {a: q(lo, 0, a) for a in acts}
    qu = {a: q(hi, 0, a) for a in acts}
    best_lower = max(ql.values())
    return dict(
        root_value=(lo.root_value, hi.root_value),
        certainly_optimal=tuple(a for a in acts
                                if all(ql[a] >= qu[b] for b in acts if b != a)),
        possibly_optimal=tuple(a for a in acts if qu[a] >= best_lower),
    )
