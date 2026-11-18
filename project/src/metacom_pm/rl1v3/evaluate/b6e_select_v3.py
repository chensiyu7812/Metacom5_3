"""B6e engineering preflight prefix selection v3 (``pmrl1v3-b6e-plan-v3``).  Plans v1/v2 are kept.

An engineering COVERAGE diagnostic, not a natural-distribution sample.  Pre-registered rule:
* candidates: the 20 fold-1..5 NeedCard pilot prefixes of ``coverage_sample_v1`` whose formal B5
  replay passed (fold 6 never used); a candidate is ``R16`` (all four heads readable, 16 reachable
  subsets) or ``MP8`` (MP has no legal candidate, 8 reachable); anything else is not selectable;
* target: exactly 7 R16 + 1 MP8, at most 1 prefix per owner, at most 2 per fold, every fold 1-5 at least once;
* order: ascending ``sha256(SALT + prefix_id)``, tie-break prefix_id;
* choice: the lexicographically first feasible set in that order - walk the order and keep a candidate
  iff the kept set can still be completed to a feasible set (exhaustive check).  Infeasible -> stop.
Inputs are replay facts only (reachability, fold, owner); no generation, judge or quality field is read.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations

from ..io import object_sha256, sha256_text

PLAN_VERSION = "pmrl1v3-b6e-plan-v3"
SALT = "pmrl1v3|b6e-preflight-v3|"
RULE = dict(plan=PLAN_VERSION, salt=SALT, candidates="needcard_pilot uses of coverage_sample_v1 (folds 1-5), B5 passed",
            classes=dict(R16="n_reachable == 16 and no unreachable head",
                         MP8="n_reachable == 8 and unreachable == {MP: unavailable:no_legal_candidates}"),
            target=dict(R16=7, MP8=1), max_per_owner=1, max_per_fold=2, folds_required=[1, 2, 3, 4, 5],
            order="ascending sha256(salt + prefix_id), tie-break prefix_id",
            choice="lexicographically first feasible set in that order; infeasible -> stop",
            terminals="per prefix = real reachable count (16 or 8)", j1_calls_per_terminal_max=3)


class SelectionInfeasible(RuntimeError):
    pass


def rule_sha256() -> str:
    return object_sha256(RULE)


def classify(rep: dict) -> str | None:
    if not rep["passed"]:
        return None
    if rep["n_reachable"] == 16 and not rep["unreachable_heads"]:
        return "R16"
    if rep["n_reachable"] == 8 and rep["unreachable_heads"] == {"MP": "unavailable:no_legal_candidates"}:
        return "MP8"
    return None


def _feasible(sel: list[dict]) -> bool:
    cls, folds, owners = Counter(c["class"] for c in sel), Counter(c["fold"] for c in sel), Counter(c["owner_id"] for c in sel)
    return (cls["R16"] == RULE["target"]["R16"] and cls["MP8"] == RULE["target"]["MP8"]
            and max(owners.values()) <= RULE["max_per_owner"] and max(folds.values()) <= RULE["max_per_fold"]
            and set(RULE["folds_required"]) <= set(folds))


def _partial_ok(sel: list[dict]) -> bool:
    cls, folds, owners = Counter(c["class"] for c in sel), Counter(c["fold"] for c in sel), Counter(c["owner_id"] for c in sel)
    return (cls["R16"] <= RULE["target"]["R16"] and cls["MP8"] <= RULE["target"]["MP8"]
            and (not owners or max(owners.values()) <= RULE["max_per_owner"])
            and (not folds or max(folds.values()) <= RULE["max_per_fold"]))


def _completable(kept: list[dict], rest: list[dict]) -> bool:
    need = sum(RULE["target"].values()) - len(kept)
    if need < 0 or not _partial_ok(kept):
        return False
    return any(_feasible(kept + list(extra)) for extra in combinations(rest, need))


def candidates(coverage_rows, replay_reports) -> list[dict]:
    rep = {r["prefix_id"]: r for r in replay_reports}
    out = []
    for c in coverage_rows:
        if c["uses"].get("needcard_pilot") is not True or c["fold"] not in RULE["folds_required"]:
            continue
        r = rep[c["prefix_id"]]
        out.append(dict(prefix_id=c["prefix_id"], owner_id=c["owner_id"], fold=c["fold"], rank_bucket=c["rank_bucket"],
                        n_reachable=r["n_reachable"], unreachable_heads=r["unreachable_heads"], passed=r["passed"],
                        order_key=sha256_text(SALT + c["prefix_id"])))
        out[-1]["class"] = classify(r)
    return sorted(out, key=lambda c: (c["order_key"], c["prefix_id"]))


def select(coverage_rows, replay_reports) -> dict:
    cands = candidates(coverage_rows, replay_reports)
    pool = [c for c in cands if c["class"] is not None]
    kept = []
    for i, c in enumerate(pool):
        if _completable(kept + [c], [x for x in pool[i + 1:]]):
            kept.append(c)
        if len(kept) == sum(RULE["target"].values()):
            break
    if not _feasible(kept):
        raise SelectionInfeasible(f"no feasible set: classes={Counter(c['class'] for c in pool)}, "
                                  f"folds={Counter(c['fold'] for c in pool)}")
    terminals = sum(c["n_reachable"] for c in kept)
    out = dict(plan=PLAN_VERSION, rule_sha256=rule_sha256(), rule=RULE, candidates=cands,
               selected=[dict(c, terminals=c["n_reachable"]) for c in kept],
               selected_ids=[c["prefix_id"] for c in kept], terminals=terminals,
               calls_upper_bound=dict(needcard_writer=0, checklist=0, g0_generation=terminals,
                                      j1_item_judge=RULE["j1_calls_per_terminal_max"] * terminals, j2_item_judge=0,
                                      paid_api=0),
               coverage=dict(folds={str(k): v for k, v in sorted(Counter(c["fold"] for c in kept).items())},
                             classes=dict(Counter(c["class"] for c in kept)),
                             rank_buckets=dict(Counter(c["rank_bucket"] for c in kept))),
               scope="engineering coverage diagnostic; NOT a natural-distribution sample", evidence_tier="engineering_only")
    return dict(out, selection_sha256=object_sha256(out))
