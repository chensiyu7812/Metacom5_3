"""Re-plan FC-MS-1 from real pre-generation screening labels (no outcome data may enter).

Called once the 90 (+ expansion) labels are frozen and BEFORE any FC-MS generation.  Produces the sample the medium
plan can actually field, the precision it buys under a range of ICC / decisive-rate assumptions, the calls and hours,
the S1-shortfall decision (descriptive downgrade), and the conclusions it cannot support.  Inputs are labels and
word counts only.
"""
from __future__ import annotations

from collections import defaultdict

from metacom_pm.rl1v3.evaluate import protocol_v321a as P
from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V

PLAN_CAPS = dict(conservative=dict(s1=1, guard_per_group=1), medium=dict(s1=2, guard_per_group=2),
                 extended=dict(s1=4, guard_per_group=2))


def replan(labels: list[dict], *, plan: str = "medium", iccs=(0.05, 0.1, 0.2), decisive=(0.4, 0.5, 0.6),
           words: dict[str, int] | None = None, owner_words: dict[str, int] | None = None) -> dict:
    """labels: [{prefix_id, owner_id, group, need}] (need in S1/S2/S0/unclear/S7).  Deterministic choice inside a
    group: labels are taken in the given order (the frozen screening order), never by any reply quality."""
    if any("reply" in k or "score" in k or "outcome" in k for r in labels for k in r):
        raise ValueError("re-planning must not read outcome fields")
    caps = PLAN_CAPS[plan]
    by = defaultdict(lambda: defaultdict(list))
    for r in labels:
        by[r["group"]][r["need"]].append(r["prefix_id"])
    chosen_s1, guards = {}, {}
    for g, d in sorted(by.items()):
        chosen_s1[g] = d["S1"][:caps["s1"]]
        gs = (d["S2"][:1] + d["S0"][:1]) if caps["guard_per_group"] >= 2 else (d["S2"] + d["S0"])[:1]
        guards[g] = gs
    s1_groups = {g: v for g, v in chosen_s1.items() if v}
    k = len(s1_groups)
    n_s1 = sum(len(v) for v in s1_groups.values())
    n_guard = sum(len(v) for v in guards.values())
    m = n_s1 / k if k else 0
    downgraded = k < 8 or n_s1 < 17
    prefixes = n_s1 + n_guard
    w = words or {}
    rd = lambda pid: w.get(pid, 0) / 250.0                              # noqa: E731
    all_pids = [p for v in s1_groups.values() for p in v] + [p for v in guards.values() for p in v]
    read_item = sum(rd(p) for p in all_pids)
    read_owner = sum(v / 250.0 for v in (owner_words or {}).values()) if owner_words else read_item
    pairs = 3 * n_s1 + 2 * n_guard
    q = pairs * (P.EST["q0_pair"] + P.EST["qh_pair"])
    f = 3 * prefixes * P.EST["f_reply"]
    audit = 0.25 * 3 * prefixes * P.EST["adj_item"] + 0.5 * 3 * prefixes * P.EST["fa_error"]
    hours = dict(lower=round((2 * (q + min(read_item, read_owner)) + f + min(read_item, read_owner) + audit) / 60, 1),
                 upper=round((2 * (q + read_item) + f + read_item + audit) / 60, 1))
    grid = [dict(icc=i, decisive=d, mde=round(P.mde(k, max(m, 1), d=d, icc=i), 3) if k >= 3 else None,
                 floor=round(P.mde_floor(k, d=d, icc=i), 3) if k >= 3 and i > 0 else None)
            for i in iccs for d in decisive]
    serious = round(V.cp_upper(0, prefixes / 1.1), 3) if prefixes else None
    return dict(
        plan=plan, k_s1=k, s1_prefixes=n_s1, mean_s1_per_group=round(m, 2), guard_prefixes=n_guard,
        s1_per_group={g: len(v) for g, v in sorted(chosen_s1.items())},
        groups_without_s1=sorted(g for g, v in chosen_s1.items() if not v),
        generator_calls=3 * prefixes, pairs=pairs, review_hours=hours, mde_grid=grid,
        serious_error_upper_if_zero_events_per_arm=serious,
        primary_mode="descriptive mechanism estimate (S1 shortfall rule)" if downgraded else "single pre-registered test",
        downgraded=downgraded,
        cannot_support=(["任何检验结论（已按 S1 不足规则降级）"] if downgraded else []) + [
            f"小于约 {min(x['mde'] for x in grid if x['mde']):.2f}–{max(x['mde'] for x in grid if x['mde']):.2f} 的净偏好差异"
            if k >= 3 else "任何量化结论（S1 组数不足 3）",
            "PM Step-1 策略增益", "renderer 效应", "18 个人物之外的外推", "−0.10 非劣",
            f"严重错误率低于 {serious}（每臂 0 例时的上界）" if serious else "严重错误率的任何上界"],
        freeze_rule="本结果必须在第一份 FC-MS 生成结果出现前冻结；冻结后改动记入设计改动 ledger 并使受影响分析转为探索性")
