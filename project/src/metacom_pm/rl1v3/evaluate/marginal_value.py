"""Marginal resource value on a fixed prefix (``pmrl1v3-marginal-value-proposal-v0``).  PROPOSAL, not adopted.

Written for the round-8 reward review (``outputs/pm_rl1/v3/B2/REWARD_MARGINAL_VALUE_REVIEW_ZH.md``).
It changes no frozen protocol: ER-v3, checklist v3, judge v3 and the B6e plan are untouched.

Every value is a pair (lower, upper) on ONE prefix whose item set and denominator are fixed
before any candidate reply exists (V3.1 6.8.2).  ``None`` = the terminal is pending; a pending
terminal makes every marginal that needs it pending - it is never read as 0.

  delta(S, B)            = [L(S) - U(B), U(S) - L(B)]                      (S, B two terminals)
  marginal(h | B)        = delta(B + h, B)        relative to an already-read set B
  marginal(h | OFF)      = delta({h}, OFF)
  interaction(h1,h2 | B) = V(B+h1+h2) - V(B+h1) - V(B+h2) + V(B)            (interval arithmetic)

A marginal is ``benefit`` only if its whole interval is above +margin, ``harm`` only if it is
below -margin, ``equivalent`` if it lies inside [-margin, +margin], otherwise ``undetermined``.
``margin`` must be pre-registered on train/dev; a midpoint difference is never enough.

``attribute`` separates the chain need -> retrieval -> generator uptake -> effect so that a G
that ignores a correct reading, or a retriever that misses the needed record, is not counted
as "the resource has no value".  NeedCard need is unverified evaluation-side evidence: it is
used for attribution only, never as a reward or as a GET_RS/GET_MP/... necessity label.
GET success, retrieval relevance and method-call rates are diagnostics, never rewards.
"""
from __future__ import annotations

from itertools import combinations
from typing import Mapping, Optional

PROTOCOL = "pmrl1v3-marginal-value-proposal-v0"
STATUS = "proposed_not_adopted"
Interval = Optional[tuple]
EFFECTS = ("benefit", "harm", "equivalent", "undetermined", "pending")
CHAIN = ("pending", "need_unverified", "unneeded_read", "unneeded_read_harm", "unanticipated_value",
         "retrieval_miss", "generator_not_used", "realized_value", "used_no_gain", "misuse_or_harmful_use",
         "undetermined")


def delta(s: Interval, b: Interval) -> Interval:
    """Interval of V(s) - V(b); pending if either side is pending."""
    if s is None or b is None:
        return None
    return (s[0] - b[1], s[1] - b[0])


def classify(iv: Interval, margin: float) -> str:
    if margin < 0:
        raise ValueError("margin must be >= 0")
    if iv is None:
        return "pending"
    lo, hi = iv
    if lo > margin:
        return "benefit"
    if hi < -margin:
        return "harm"
    if lo >= -margin and hi <= margin:
        return "equivalent"
    return "undetermined"


def midpoint_delta(s: Interval, b: Interval, u: float = 0.5) -> Optional[float]:
    """What a point-valued reward (ER-v3 primary, u = 0.5) would report; for comparison only."""
    if s is None or b is None:
        return None
    return (s[0] + u * (s[1] - s[0])) - (b[0] + u * (b[1] - b[0]))


def interaction(table: Mapping[frozenset, Interval], h1: str, h2: str, base: frozenset = frozenset()) -> Interval:
    keys = (base | {h1, h2}, base | {h1}, base | {h2}, base)
    if any(k not in table or table[k] is None for k in keys):
        return None
    v12, v1, v2, v0 = (table[k] for k in keys)
    return (v12[0] - v1[1] - v2[1] + v0[0], v12[1] - v1[0] - v2[0] + v0[1])


def marginals(table: Mapping[frozenset, Interval], heads, margin: float) -> list[dict]:
    """Every reachable (base, head) pair: the marginal of adding ``head`` to ``base``.

    ``table`` holds only reachable subsets; an unreachable B + h is skipped (not a 0), a reachable
    but pending terminal gives ``pending``."""
    out = []
    for n in range(len(heads)):
        for base in combinations(sorted(heads), n):
            b = frozenset(base)
            if b not in table:
                continue
            for h in sorted(set(heads) - b):
                s = b | {h}
                if s not in table:
                    continue
                iv = delta(table[s], table[b])
                out.append(dict(base=sorted(b), head=h, delta=iv, effect=classify(iv, margin),
                                midpoint=midpoint_delta(table[s], table[b])))
    return out


def attribute(*, effect: str, need: Optional[bool], retrieval_hit: Optional[bool], uptake: Optional[str]) -> str:
    """need -> retrieval -> uptake -> effect, for ONE marginal (head h given base B).

    need           NeedCard says the head's information is required now (None = no verified card)
    retrieval_hit  the read text contains the NeedCard evidence (mechanical span check; None = n/a)
    uptake         'used' | 'not_used' | 'uncertain': the reply states something grounded in the read text
    """
    if effect not in EFFECTS:
        raise ValueError(f"unknown effect {effect!r}")
    if effect == "pending":
        return "pending"
    if need is None:                                     # no verified NeedCard: effect is reported, cause is not
        return "need_unverified"
    if not need:
        if effect == "harm":
            return "unneeded_read_harm"
        if effect == "benefit" and uptake == "used":
            return "unanticipated_value"                 # value the NeedCard did not foresee (a recall gap)
        return "unneeded_read"
    if retrieval_hit is False:
        return "misuse_or_harmful_use" if effect == "harm" else "retrieval_miss"
    if uptake == "not_used":
        return "generator_not_used"
    if effect == "undetermined" or uptake != "used":
        return "undetermined"
    return {"benefit": "realized_value", "equivalent": "used_no_gain", "harm": "misuse_or_harmful_use"}[effect]


def decision_label(*, quality: Interval, margin: float, new_hard_factual_fail: Optional[bool],
                   safety: Optional[str], added_latency_s: Optional[float], latency_budget_s: Optional[float]) -> str:
    """Paper-1 decision-correctness rule (beneficial AND no material harm AND latency-feasible), interval-aware.

    -> 'beneficial' | 'nonbeneficial' | 'infeasible' | 'undetermined' | 'pending'"""
    if quality is None or safety is None or new_hard_factual_fail is None:
        return "pending"
    if safety == "fail" or new_hard_factual_fail:
        return "infeasible"
    if safety == "uncertain":
        return "pending"
    eff = classify(quality, margin)
    if eff in ("harm", "equivalent"):
        return "nonbeneficial"
    if eff == "undetermined":
        return "undetermined"
    if added_latency_s is None or latency_budget_s is None:
        return "undetermined"                              # latency not measured (B4 pending): no formal label
    return "beneficial" if added_latency_s <= latency_budget_s else "infeasible"
