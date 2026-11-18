"""V3.2 main-comparison arms and fairness contract (``pmrl1v3-v32-baselines-v1``).  CPU proposal.

Every arm is evaluated on the SAME prefixes, as-of binding, resource versions, Generator, renderer
(except F-resident, which is its own renderer identity by definition), evaluator identity, split and
fold rule.  ``check_fair`` refuses a comparison that violates the contract.  Non-learning arms are
implemented here as pure functions over a terminal table so they can run on fixtures and later on
complete real tables; learning arms reuse ``train.supervised`` / ``train.ppo``.  Fixture rewards are
engineering_only and never evidence of support-quality improvement.
"""
from __future__ import annotations

import numpy as np

from ..env import finite_head as E
from ..io import object_sha256

PROTOCOL = "pmrl1v3-v32-baselines-v1"

ARMS = {
    "OFF": dict(kind="fixed", sees="nothing beyond the prefix", feedback="none", rule="STOP at once"),
    "ALL": dict(kind="fixed", sees="availability", feedback="none", rule="GET every reachable head, canonical order"),
    "Fixed-best": dict(kind="fixed", sees="availability", feedback="train-fold terminal rewards only",
                       rule="the single subset with the best mean train reward; unreachable heads dropped"),
    "F-resident": dict(kind="fixed", sees="nothing beyond the prefix", feedback="none",
                       rule="STOP at once under the F-resident renderer identity (resident method list on "
                            "every request); its own terminal table; never called OFF"),
    "Rule": dict(kind="fixed", sees="visible prefix cues + availability", feedback="none",
                 rule="pre-registered on B0 visible surface cues: RS if advice_request; ME+MS if back_reference "
                      "or temporal_marker; MP if history exists and back_reference; else STOP"),
    "Random": dict(kind="fixed", sees="availability", feedback="none",
                   rule="uniform over reachable subsets of size k; headline k = round(mean GETs of PPO on dev), "
                        "all k reported"),
    "OneShot": dict(kind="learned", sees="prefix + availability (no reading text)",
                    feedback="complete train tables", rule="choose a subset once before reading"),
    "Seq-BC": dict(kind="learned", sees="prefix + availability + delivered reading text",
                   feedback="complete train tables", rule="imitate exact-DP optimal actions"),
    "BC-union": dict(kind="learned", sees="as Seq-BC",
                     feedback="exactly the terminal rewards PPO's rollouts queried (same count)",
                     rule="Seq-BC on DP targets recomputed from PPO's queried feedback only"),
    "PPO": dict(kind="learned", sees="as Seq-BC", feedback="rollout rewards (counted)", rule="clipped PPO, gamma 1"),
    "PPO-NoText": dict(kind="learned", sees="as PPO minus the delivered reading text",
                       feedback="as PPO", rule="identical to PPO except the text features"),
}
DIAGNOSTIC_ONLY = {"Oracle": "exact DP on the complete table of the evaluated prefix; privileged, never deployed"}
CONTRASTS = (
    ("PPO", "Fixed-best", "does context-dependent choice beat not learning"),
    ("Seq-BC", "OneShot", "does reading before deciding add value"),
    ("PPO", "OneShot", "sequential RL vs one-shot"),
    ("PPO", "BC-union", "RL update rule with the feedback count controlled"),
    ("PPO", "PPO-NoText", "is the delivered text used for the next decision"),
    ("Fixed-best", "OFF", "does any fixed resource use help"),
    ("F-resident", "OFF", "resident skill text vs true OFF"),
)
SHARED = ("prefixes", "binding_sha256", "bank_version", "index_version", "g_id", "decode_id", "step2_id",
          "evaluator_id", "split_rule", "fold_rule")


def check_fair(runs: dict) -> list[str]:
    """``runs``: arm -> dict with the SHARED fields (+ renderer_id, feedback_terminals)."""
    p = []
    unknown = set(runs) - set(ARMS) - set(DIAGNOSTIC_ONLY)
    if unknown:
        p.append(f"unknown_arms:{sorted(unknown)}")
    ref = next(iter(runs.values()))
    for arm, r in runs.items():
        for k in SHARED:
            v, w = r.get(k), ref.get(k)
            if (tuple(sorted(v)) if k == "prefixes" else v) != (tuple(sorted(w)) if k == "prefixes" else w):
                p.append(f"{arm}:{k}")
    ren = {a: r.get("renderer_id") for a, r in runs.items()}
    base = {v for a, v in ren.items() if a != "F-resident"}
    if len(base) > 1:
        p.append("renderer_differs_outside_F_resident")
    if "F-resident" in ren and ren["F-resident"] in base:
        p.append("F_resident_must_have_its_own_renderer")
    if "BC-union" in runs and "PPO" in runs and runs["BC-union"].get("feedback_terminals") != runs["PPO"].get("feedback_terminals"):
        p.append("BC-union_feedback_not_matched_to_PPO")
    if any(r.get("pending_as_zero") for r in runs.values()):
        p.append("pending_as_zero")
    return sorted(set(p))


# --------------------------------------------------------------- non-learning arms (pure)
def subsets_of_size(reachable, k):
    return [m for m in reachable if bin(m).count("1") == k]


def arm_off(reachable, **_):
    return 0


def arm_all(reachable, **_):
    return max(reachable, key=lambda m: (bin(m).count("1"), m))


def fixed_best(train_tables: list[dict]) -> int:
    """Best mean reward over train prefixes, each prefix scored on the reachable part of the subset."""
    best, best_v = 0, -np.inf
    for m in range(E.N_SUBSETS):
        vals = []
        for t in train_tables:
            reach = [x for x in t if x & m == x]
            vals.append(t[max(reach, key=lambda x: (bin(x).count("1"), x))])
        v = float(np.mean(vals))
        if v > best_v + 1e-12:
            best, best_v = m, v
    return best


def arm_fixed(reachable, *, fixed_mask, **_):
    reach = [x for x in reachable if x & fixed_mask == x]
    return max(reach, key=lambda x: (bin(x).count("1"), x))


def arm_rule(reachable, *, cues: dict, history_sessions: int, **_):
    want = set()
    if cues.get("advice_request"):
        want.add("RS")
    if cues.get("back_reference") or cues.get("temporal_marker"):
        want |= {"ME", "MS"}
    if history_sessions > 0 and cues.get("back_reference"):
        want.add("MP")
    m = E.mask_of(sorted(want, key=E.HEADS.index))
    return arm_fixed(reachable, fixed_mask=m)


def arm_random(reachable, *, k: int, rng: np.random.Generator, **_):
    pool = subsets_of_size(reachable, k) or subsets_of_size(reachable, max(bin(m).count("1") for m in reachable))
    return int(pool[rng.integers(len(pool))])


def evaluate_fixed_arms(test: list[dict], train_tables: list[dict], *, k_random: int, seed: int) -> dict:
    """``test`` rows: {table: mask->reward (complete), cues, history_sessions}.  Returns mean reward per arm
    and the Oracle diagnostic.  Incomplete tables must be removed BEFORE (same set for every arm)."""
    for t in test:
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in t["table"].values()):
            raise ValueError("incomplete table: pending terminals are never 0; drop the prefix for every arm")
    rng = np.random.default_rng(seed)
    fm = fixed_best(train_tables)
    out = {}
    for arm, fn in (("OFF", arm_off), ("ALL", arm_all), ("Fixed-best", arm_fixed), ("Rule", arm_rule),
                    ("Random", arm_random)):
        vals = [t["table"][fn(sorted(t["table"]), fixed_mask=fm, cues=t["cues"], history_sessions=t["history_sessions"],
                               k=k_random, rng=rng)] for t in test]
        out[arm] = float(np.mean(vals))
    out["Oracle(diagnostic)"] = float(np.mean([max(t["table"].values()) for t in test]))
    return dict(protocol=PROTOCOL, n=len(test), fixed_best_subset="+".join(E.heads_of(fm)) or "OFF", means=out,
                evidence_tier="engineering_only (fixture or engineering reward)")


def manifest() -> dict:
    spec = dict(protocol=PROTOCOL, arms=ARMS, diagnostic=DIAGNOSTIC_ONLY, contrasts=CONTRASTS, shared=SHARED,
                multiplicity="Holm over the 7 pre-registered contrasts; owner-cluster bootstrap CIs; "
                             "S288/M482/L-realized748 are planned tiers only (L960 infeasible)",
                missing="prefixes with any pending terminal are excluded for every arm and reported")
    return dict(spec, sha256=object_sha256(spec))

