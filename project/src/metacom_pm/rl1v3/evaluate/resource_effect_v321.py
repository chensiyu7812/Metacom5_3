"""V3.2.1 small-scope revision candidate of the RQ1 resource-effect qualification (CPU, PROPOSED_NOT_ADOPTED).

Builds on ``resource_effect_v32q`` (PR #17, protocol sha b28cf37b...); nothing there and nothing frozen in P2 v1
(2b6057c8...) is modified.  This module only adds:

  * gates split by purpose: Generator engineering admission / PP1 procedure pilot / per-family formal comparison /
    reward-BC-PPO qualification, each item with evidence, state, reason and the owner who can unblock it;
  * review spec v2: QH background = arm-independent as-of RAW, need labels sealed on the audit side,
    every rater blind to condition and to any earlier model or human score, F-A moved to the audit side;
  * statistics on 17 owner groups: t-based precision / MDE, reachable non-inferiority margins, rare-event
    (Clopper-Pearson) bounds for serious-error rates, and a decision vocabulary that never reads
    "not significant" as "non-inferior" or "no effect";
  * the reproducible 90-item initial screen (2 cue + 2 other + 1 S7 per owner, from the frozen 162 draw) and a
    label-only expansion rule;
  * the PP1 procedure-pilot protocol (16 OFF / RET-MS calls on the 8 ELIGIBLE prefixes) and its cost bound.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from ..io import object_sha256
from . import resource_effect_v32q as Q

PROTOCOL = "pmrl1v3-v321-resource-effect-qual-candidate-1"
STATUS = "PROPOSED_NOT_ADOPTED"
BASE = dict(protocol=Q.PROTOCOL, sha256="b28cf37b", frozen_p2_v1="2b6057c8dde4b443c08fd3ff281cb6c22c3ebd1f4d1a02eab8ac948a7bd4c81f")

# ------------------------------------------------------------------ revisions against the PR #17 candidate
REVISIONS = [
    dict(id="V1", area="gates", change="Gate 1/2 replaced by G-ENG / PP1 / FC-<family> / G-RWD; FC-MS no longer "
         "waits for RS METHOD, MP or ME; PP1 gates only the start of formal human review, never generation",
         basis="round-11 instruction 2; #17 Gate 1 bundled all families and made METHOD cards a blocker of MS"),
    dict(id="V2", area="QH", change="QH background = complete as-of RAW (all legal past sessions, chronological, "
         "neutral index of rank/date/length); curator excerpts and span roles are no longer shown to raters",
         basis="instruction 3; role-labelled excerpts tell the rater what 'should' be used"),
    dict(id="V3", area="labels", change="S1/S2/S0 need labels and required / relevant_optional / "
         "must_not_contradict spans are written before generation into a sealed audit ledger; never displayed "
         "in Q0/QH/F; used for stratification and audit analyses only", basis="instruction 3"),
    dict(id="V4", area="blinding", change="every rater (Q0, QH, F) is blind to condition, resource type, reading "
         "content, need labels, NeedCard/checklist, J1/J2/ESC-RANK and earlier human labels; F-A attribution is "
         "an audit step after all locks, done by a non-rater, and never changes Q0/QH/F labels",
         basis="instruction 3; #17 F-A was a non-blind rater step"),
    dict(id="V5", area="statistics", change="t-based precision with df = groups - 1; reachable NI margins and "
         "serious-error bounds tabulated; -0.10 and +0.05 kept as discussion candidates, not gates; decision "
         "vocabulary superior / non_inferior / inferior / inconclusive", basis="instruction 4"),
    dict(id="V6", area="sample", change="initial screen = 90 (2+2+1 per owner) taken from the frozen 162 draw in "
         "draw order; label-only expansion to the remaining 72 and then to the frame", basis="instruction 5"),
    dict(id="V7", area="pilot", change="PP1 = separate procedure protocol, 16 calls; its prefixes stay out of the "
         "formal sample by default; PP1 outcomes are exploratory and recorded as outcome_same_contrast exposure",
         basis="instruction 6"),
    dict(id="V8", area="renderer", change="within a formal family every arm uses one renderer identity (one "
         "changed factor); the html.escape of resource text present in both the G0e and the E1 renderer is "
         "recorded as a presentation property needing an explicit decision before FC-MS",
         basis="WS-B PR #18 receipt finding N1/N2"),
]

# ------------------------------------------------------------------ review spec v2
BLIND_TO = ("条件名与资源类型", "资源读取内容（F-A 之前）", "生成前需要标签 S1/S2/S0 及 span 角色", "NeedCard / 检查表",
            "J1/J2/ESC-RANK 等任何模型分数", "旧人工标签与其他审阅者的答案")


def review_spec_v2() -> dict:
    base = Q.review_spec()
    return dict(
        version="review-spec-v2-candidate",
        all_raters_blind_to=list(BLIND_TO),
        Q0=dict(role="即时支持质量（保护通道）", shows=["当前可见前缀", "回复 A/B"],
                hides=list(BLIND_TO) + ["任何历史背景"], items=base["Q0"].get("items", Q.Q_DIMENSIONS)),
        QH=dict(role="长期支持质量（主通道）",
                shows=["当前可见前缀", "完整 as-of RAW 背景（全部合法过去会话，按时间顺序）",
                       "中性会话索引（rank、日期、轮数）", "回复 A/B"],
                hides=list(BLIND_TO) + ["Q0 答案", "整理者摘录与 span 角色", "任何资源臂的读取内容"],
                prerequisite="该审阅者全部 Q0 已锁定",
                instruction="请以一个了解此人过往的支持者的视角，判断哪份回复此刻对此人更合适、更有帮助。"
                            "是否提到过去的内容本身不是评判标准。",
                withdrawn=["v1 读取并集", "#17 带角色标注的整理者摘录"]),
        F=dict(role="事实与安全约束（单份回复）",
               shows=["当前可见前缀", "一份回复", "完整 as-of RAW（可检索）"],
               hides=list(BLIND_TO) + ["must_not_contradict 等 span 角色"],
               items=list(Q.F_ITEMS), values=list(Q.F_VALUES), severity=list(Q.F_SEVERITY),
               rules=["每个“有”必须引用回复原句和 RAW 证据位置（F5 引用“查无来源”）",
                      "没有提及过去的内容不是错误",
                      "F6 只在提及当前不需要的内容且方式生硬或侵入时成立，由审阅者自行判断，不参照任何标签"]),
        audit=dict(role="评价审计侧（非审阅者）",
                   holds=["生成前冻结的需要标签与 span 角色（密封）", "条件映射与位置映射", "F-A 归因"],
                   F_A=dict(after="所有 Q0/QH/F 标签锁定之后", by="不参与该前缀评审的审计人员",
                            sees="该回复实际收到的读取内容", output="审计记录，不改变任何评审标签",
                            values=["reading", "generator", "no_reading", "unclear"]),
                   uses=["按需要标签分层报告", "F 证据与 span 角色一致性", "盲态完整性检查"]),
        staffing=dict(screener_vs_rater="同一前缀的筛查整理者默认不担任该前缀的 Q0/QH/F 审阅者；"
                                         "人手不足时记录重叠并做剔除重叠前缀的敏感性分析",
                      rater_overlap="Q0/QH 每对两名审阅者独立完成；F 由第三人或在 Q 全部锁定后完成"),
        display=dict(replies="按生成原文以纯文本显示，不做 HTML 解释或修改；实体字符等技术痕迹由审计侧另行计数",
                     grouping="同一前缀的背景只展示一次，其各对依次出现；位置按 sha256(协议|pair|通道) 随机"),
        independence=base["independence"],
    )


AUDIT_LEDGER_RULE = dict(
    written="生成前，由筛查整理者在表单 S 中写入；提交即生成 label_sha256 并冻结",
    sealed_until="对应实验族全部 Q0/QH/F 锁定",
    never_shown_to=["Q0", "QH", "F 审阅者", "Generator", "PM 观测"],
    allowed_uses=["分层（S1/S2/S0/S7）", "审计分析（使用必要信息、矛盾、侵入式提及）", "敏感性分析"],
    forbidden=["根据标签改变展示给审阅者的背景", "依据回复质量修改标签", "以标签代替人工质量判断"],
)

# ------------------------------------------------------------------ statistics (no scipy dependency)
_T = {  # Student t quantiles, df 1..30
    0.975: [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145,
            2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048,
            2.045, 2.042],
    0.95: [6.314, 2.920, 2.353, 2.132, 2.015, 1.943, 1.895, 1.860, 1.833, 1.812, 1.796, 1.782, 1.771, 1.761,
           1.753, 1.746, 1.740, 1.734, 1.729, 1.725, 1.721, 1.717, 1.714, 1.711, 1.708, 1.706, 1.703, 1.701,
           1.699, 1.697],
    0.80: [1.376, 1.061, 0.978, 0.941, 0.920, 0.906, 0.896, 0.889, 0.883, 0.879, 0.876, 0.873, 0.870, 0.868,
           0.866, 0.865, 0.863, 0.862, 0.861, 0.860, 0.859, 0.858, 0.858, 0.857, 0.856, 0.856, 0.855, 0.855,
           0.854, 0.854],
}


def t_quantile(q: float, df: int) -> float:
    if q not in _T or not 1 <= df <= 30:
        raise ValueError("table covers q in {0.975, 0.95, 0.80}, df 1..30")
    return _T[q][df - 1]


def se_delta(groups: int, per_group: int, decisive: float, icc: float) -> float:
    """SE of the equal-weight group mean of pair scores in {-1,0,+1}; var(pair) = decisive rate (null)."""
    return math.sqrt(decisive * (1 + (per_group - 1) * icc) / (groups * per_group))


def precision_row(groups: int, per_group: int, decisive: float, icc: float) -> dict:
    se = se_delta(groups, per_group, decisive, icc)
    df = groups - 1
    hw = t_quantile(0.975, df) * se
    mde = (t_quantile(0.975, df) + t_quantile(0.80, df)) * se
    return dict(groups=groups, per_group=per_group, pairs=groups * per_group, decisive=decisive, icc=icc,
                se=round(se, 4), half_width_95=round(hw, 3), mde_80=round(mde, 3),
                ni_margin_reachable_80=round(mde, 3))


def required_per_group_for_margin(margin: float, *, groups: int, decisive: float, icc: float,
                                  power_q: float = 0.80) -> int | None:
    """Pairs per group so that a true Delta = 0 shows lower 95% bound > -margin with the given power.
    None = unreachable at this number of groups (the ICC floor alone exceeds the allowed variance)."""
    s = margin / (t_quantile(0.975, groups - 1) + t_quantile(power_q, groups - 1))
    room = s * s * groups / decisive - icc
    if room <= 0:
        return None
    return math.ceil((1 - icc) / room)


def _binom_cdf(x: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))


def cp_upper(x: int, n: float, conf: float = 0.975) -> float:
    """Exact one-sided Clopper-Pearson upper bound (n may be a design-effect-deflated effective size)."""
    n_i = max(1, int(math.floor(n)))
    if x >= n_i:
        return 1.0
    lo, hi = x / n_i, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _binom_cdf(x, n_i, mid) > 1 - conf:
            lo = mid
        else:
            hi = mid
    return hi


def serious_error_table(ns=(16, 34, 68, 102, 136), xs=(0, 1, 2), design_effects=(1.0, 1.1, 1.3)) -> list[dict]:
    return [dict(replies=n, serious=x, design_effect=de, n_eff=round(n / de, 1),
                 upper_95=round(cp_upper(x, n / de), 3)) for n in ns for x in xs for de in design_effects]


def replies_needed_for_bound(bound: float = 0.05, x: int = 0, design_effect: float = 1.1) -> int:
    n = 1
    while cp_upper(x, n) >= bound:
        n += 1
    return math.ceil(n * design_effect)


def paired_harm_detectable(alpha: float = 0.05) -> int:
    """Smallest number of arm-only serious errors (with 0 OFF-only) that an exact two-sided sign test detects."""
    b = 1
    while 2 * 0.5 ** b > alpha:
        b += 1
    return b


DECISIONS = dict(
    superior="95% CI 下界 > 0",
    non_inferior="95% CI 下界 > -margin（margin 须研究者事先确认）",
    inferior="95% CI 上界 < 0",
    inconclusive="其余情形，包括 CI 同时覆盖 0 与 -margin；表示精度不足，不是“无效”也不是“非劣”",
)


def classify(lower: float, upper: float, margin: float | None) -> list[str]:
    out = []
    if lower > 0:
        out.append("superior")
    if upper < 0:
        out.append("inferior")
    if margin is not None and lower > -margin:
        out.append("non_inferior")
    return out or ["inconclusive"]


def stats_v321(groups: int = 17) -> dict:
    grid = [precision_row(groups, m, d, r) for m in (1, 2, 3, 4, 6, 8) for d in (0.3, 0.5, 0.7)
            for r in (0.0, 0.05, 0.1, 0.2)]
    ni = {f"margin_{mg}": {f"icc_{r}": required_per_group_for_margin(mg, groups=groups, decisive=0.5, icc=r)
                           for r in (0.0, 0.02, 0.05, 0.1)} for mg in (0.10, 0.20, 0.30)}
    return dict(
        protocol=PROTOCOL, groups=groups, df=groups - 1, model="pair score in {-1,0,+1} (two-rater mean allowed); "
        "estimand = equal-weight mean of owner-group means; var(pair) = decisive rate under the null; "
        "design effect 1+(m-1)ICC; t quantiles with df = groups-1; MDE/NI at 80% power, two-sided 95%",
        precision_grid=grid,
        anchor=precision_row(groups, 2, 0.5, 0.1), anchor_m4=precision_row(groups, 4, 0.5, 0.1),
        ni_required_pairs_per_group=ni,
        ni_note="margin -0.10 cannot be shown on 17 groups once ICC >= ~0.04 at any number of pairs per group; "
                "with ICC = 0 it needs ~27 pairs per group (~460 pairs). -0.10 therefore stays a discussion "
                "candidate; a reachable margin at m = 4, ICC 0.1 is ~0.26",
        serious_error=dict(table=serious_error_table(),
                           replies_needed_upper_below_0_05=dict(
                               zero_events={str(de): replies_needed_for_bound(0.05, 0, de) for de in (1.0, 1.1, 1.3)},
                               one_event={str(de): replies_needed_for_bound(0.05, 1, de) for de in (1.0, 1.1, 1.3)}),
                           paired_harm_detectable_arm_only_errors=paired_harm_detectable(),
                           note="+0.05 as an upper bound on (arm - OFF) serious-error rate is not demonstrable "
                                "with 34 replies per arm even at zero events (upper ~0.10); it is a discussion "
                                "candidate. Harm is detectable when arm-only serious errors reach ~6 with none "
                                "OFF-only (exact sign test, clustering ignored)"),
        decisions=DECISIONS,
        reading_rules=["样本量不足导致的 inconclusive 不得解释为系统无效",
                       "不显著不得解释为非劣；非劣只能由事先确认的 margin 与 CI 下界给出",
                       "F 严重错误“未观察到”不等于“率低于 0.05”，必须报告上界",
                       "S1/S2/S0/S7 分层结果分开报告；分层 CI 更宽，不作单独的显著性结论，除非事先列为主比较"],
        not_gates=["-0.10（Q0 非劣界）", "+0.05（F 严重错误率差上限）"],
    )


# ------------------------------------------------------------------ 90-item initial screen + expansion rule
def initial_screen(draw: dict, *, per_stratum: int = 2, s7: int = 1) -> dict:
    """First ``per_stratum`` cue and other items and the S7 item of every owner, in frozen draw order."""
    pop = {(s["owner_id"], s["stratum"]): s["population"] for s in draw["strata"]}
    take = dict(cue=per_stratum, other=per_stratum, S7_rank0=s7)
    rows = []
    for d in draw["drawn"]:
        if d["order"] < take[d["stratum"]]:
            n = pop[(d["owner_id"], d["stratum"])]
            k = min(take[d["stratum"]], n)
            rows.append(dict(prefix_id=d["prefix_id"], owner_id=d["owner_id"], stratum=d["stratum"],
                             order=d["order"], population=n, inclusion_probability=round(k / n, 6), phase="A"))
    rows.sort(key=lambda r: (r["owner_id"], r["stratum"], r["order"]))
    return dict(rule=f"from draw {draw['draw_sha256'][:12]}: order < {per_stratum} in cue and other, order < {s7} "
                     f"in S7_rank0, per owner", source_draw_sha256=draw["draw_sha256"], salt=draw["salt"],
                rows=rows, counts=dict(Counter(r["stratum"] for r in rows)), owners=len({r["owner_id"] for r in rows}),
                screen_sha256=object_sha256([(r["prefix_id"], r["stratum"], r["order"]) for r in rows]))


EXPANSION_RULE = dict(
    trigger="仅由生成前筛查标签触发；任何回复、评分、J1/J2 或旧结果都不得参与",
    targets_per_owner_group=dict(S1=1, S2=1, S0=1),
    global_minimum=dict(S1=17),
    phase_B="对仍有缺口的 owner 组：按冻结的 draw 顺序继续筛查 162 中尚未筛查的条目（S1 或 S2 缺口先取 cue，"
            "S0 缺口先取 other），每次一条，达到目标即停",
    phase_C="Phase B 后若全局 S1 < 17：对 S1 不足的 owner，按同一 salt 的哈希顺序从自然框架 cue 层继续抽取，"
            "每 owner 最多再加 8 条；仍不足即报告缺口，不改变定义、不放宽标签",
    unclear="'unclear' 不计入任何目标，单列报告",
    probabilities="每一阶段登记实际筛查条目及其阶段内抽样概率；主估计量是按标签分层的条件效应，不用权重；"
                  "自然分布估计才使用 1/π 加权并单独报告",
    freeze="每条筛查标签提交即冻结；正式生成只针对已冻结的条目",
)


def expansion_next(draw: dict, screened: set[str], labels: dict[str, str], group_of: dict[str, str]) -> dict:
    """Deterministic Phase-B step: which not-yet-screened items of the 162 to screen next (labels only)."""
    have = defaultdict(Counter)
    for pid, lab in labels.items():
        owner = next(d["owner_id"] for d in draw["drawn"] if d["prefix_id"] == pid)
        have[group_of[owner]][lab] += 1
    deficit = {g: {s: t - have[g][s] for s, t in EXPANSION_RULE["targets_per_owner_group"].items()
                   if have[g][s] < t} for g in set(group_of.values())}
    deficit = {g: d for g, d in deficit.items() if d}
    nxt = []
    for g, d in sorted(deficit.items()):
        owners = sorted(o for o, gg in group_of.items() if gg == g)
        pref = ["cue", "other"] if ("S1" in d or "S2" in d) else ["other", "cue"]
        for st in pref:
            cand = sorted((x for x in draw["drawn"] if x["owner_id"] in owners and x["stratum"] == st
                           and x["prefix_id"] not in screened), key=lambda x: (x["order"], x["owner_id"]))
            if cand:
                nxt.append(dict(group=g, prefix_id=cand[0]["prefix_id"], stratum=st, deficit=d))
                break
        else:
            nxt.append(dict(group=g, prefix_id=None, stratum=None, deficit=d, note="162 exhausted -> phase C"))
    return dict(deficit=deficit, next=nxt)


# ------------------------------------------------------------------ gates v2
STATE = ("PASS", "BLOCKED", "PENDING")


def _item(iid, evidence, ok, *, reason, owner, pending=False):
    st = "PASS" if ok else ("PENDING" if pending else "BLOCKED")
    return dict(id=iid, evidence=evidence, state=st, reason=None if ok else reason, unblock_owner=None if ok else owner)


def _gate(name, purpose, items, *, depends=(), not_required=()):
    states = {i["state"] for i in items}
    st = "BLOCKED" if "BLOCKED" in states else ("PENDING" if "PENDING" in states else "PASS")
    return dict(gate=name, purpose=purpose, state=st, depends_on=list(depends), not_required=list(not_required),
                items=items)


def gates_v321(f: dict) -> list[dict]:
    g_eng = _gate("G-ENG", "允许真实 Generator 生成（按作业授权）；本身不评价质量", [
        _item("E1", "G0e 身份冻结：PR #10 合入，或研究者书面固定 G0e 身份（g_id/renderer/step2/decode）",
              f["g0e_identity"], reason="PR #10 仍为 OPEN，未合入也未书面固定", owner="integration owner / 研究者"),
        _item("E2", "A0 实测：加载前重新计算权重 hash、环境证明、2 次确定性重复调用一致、超时/OOM 行为已记录",
              f["a0_measured"], reason="A0 尚未实测（需 GPU 授权）", owner="WS-A（执行）/ 研究者（授权）"),
        _item("E3", "本作业全部请求包已导出（messages、input_ids、decode），并通过 B 独立投影检查",
              f["requests_checked"], reason=f.get("requests_reason", "请求包尚未导出或未经 B 检查"),
              owner="WS-A（导出）/ WS-B（检查）"),
        _item("E4", "输出缓存 write-once、无自动重试、技术失败记为 pending", f["output_policy"],
              reason="G0e 输出策略未随身份冻结", owner="WS-A"),
        _item("E5", "研究者对该作业的 GPU/Generator 单独授权（列出调用数上限）", f["gpu_auth"],
              reason="尚无授权", owner="研究者", pending=True),
    ], not_required=["PP1 结果", "RS METHOD 卡", "MP/ME 语义审核", "Judge"])
    pp1 = _gate("PP1", "验证人评程序可用（表单、盲态、计时、分歧处理）；只把关正式人评的开始，不把关任何生成", [
        _item("P1", "G-ENG 对 PP1 的 16 次调用成立", g_eng["state"] == "PASS" or f.get("g_eng_pp1"),
              reason="G-ENG 未通过", owner="见 G-ENG"),
        _item("P2", "8 个前缀的 QH 背景（完整 as-of RAW，与资源臂无关）在生成前冻结", f["pp1_qh_backgrounds"],
              reason="尚未构建", owner="WS-B"),
        _item("P3", "8 个前缀的生成前筛查标签（表单 S）由非审阅者完成并封存", f["pp1_screen_labels"],
              reason="需要一名筛查整理者（约 1.5 小时）", owner="研究者（指派）/ 整理者", pending=True),
        _item("P4", "两名审阅者已排期；F 第三人或 Q 锁定后的分工已确定", f["raters"],
              reason="审阅者未排期", owner="研究者", pending=True),
        _item("P5", "PP1 协议获批（流程、停止条件、与正式分析分离）", f["pp1_protocol_approved"],
              reason="候选协议待研究者核准", owner="研究者", pending=True),
        _item("P6", "评审工具实现（表格或页面）：盲化、位置哈希、锁定时间戳、导出字段", f["instrument"],
              reason="结构已定，工具未生成", owner="WS-B"),
    ], depends=["G-ENG"], not_required=["正式样本筛查", "RS METHOD 卡", "MP/ME 语义审核"])
    fc_common = [
        _item("C1", "正式协议冻结并获批：主比较、主指标、margin（如采用）、样本、缺失与不确定处理", f["formal_protocol"],
              reason="v3.2.1 候选未获批；margin 仍为讨论候选", owner="研究者", pending=True),
        _item("C2", "正式样本筛查标签冻结（90 初筛 + 预设扩展），覆盖达到预设目标或缺口已报告", f["screen_labels"],
              reason="0 条标签（需人工筛查，约 14 小时）", owner="研究者（指派）/ 整理者"),
        _item("C3", "正式样本 QH 背景（完整 as-of RAW）全部冻结", f["formal_qh"], reason="尚未构建（机械，可在筛查后生成）",
              owner="WS-B"),
        _item("C4", "PP1 程序可用（或研究者书面豁免）", f["pp1_done"], reason="PP1 未执行", owner="研究者 / WS-B",
              pending=True),
        _item("C5", "审阅人力满足工作量估计", f["raters"], reason="审阅者未排期", owner="研究者", pending=True),
        _item("C6", "同一实验族所有臂使用同一 renderer 身份，html.escape 等展示属性已明确决定", f["single_renderer"],
              reason="旧 RET-MS（G0e renderer）与 E1 DP-MS（E1 renderer）不同；转义未决", owner="WS-A / 研究者"),
    ]
    fc_ms = _gate("FC-MS", "MS 正式质量比较：OFF / DP-MS / RET-MS，按 S1/S2/S0/S7 分层", [
        _item("M1", "G-ENG 对正式 MS 作业成立", g_eng["state"] == "PASS", reason="G-ENG 未通过", owner="见 G-ENG"),
        _item("M2", "DP-MS 材料：正式样本每个前缀的 MS-RAW-direct（固定规则、非检索）通过 B 机械核验",
              f["dp_ms_formal"], reason="PR #18 只覆盖 8 个前缀（已核验通过）；正式样本前缀尚未导出",
              owner="WS-A（导出）/ WS-B（核验）"),
        _item("M3", "RET-MS 使用 as-of 检索身份（不含未来会话）", f["ret_ms_asof"], reason="as-of 检索身份未冻结",
              owner="WS-A"),
        _item("M4", "RAW 来源许可范围确认（EvoEmo 上游许可未决，沿用既有研究授权）", f["license_scope"],
              reason="待研究者确认", owner="研究者", pending=True),
    ] + fc_common, depends=["G-ENG", "PP1（只把关人评开始）"],
        not_required=["RS METHOD 卡", "MP/ME 语义审核", "J1/J2"])

    def fc_sem(name, head, n_ok, extra):
        return _gate(name, f"{head} 正式质量比较", [
            _item(f"{head}1", "G-ENG 成立", g_eng["state"] == "PASS", reason="G-ENG 未通过", owner="见 G-ENG"),
            _item(f"{head}2", f"{head} 候选逐项人工语义审核（主体、阶段、有效性）", n_ok,
                  reason=extra, owner="研究者指派的审核者 / WS-A"),
        ] + fc_common, depends=["G-ENG"], not_required=["RS METHOD 卡"] if head != "RS" else [])
    fc_mp = fc_sem("FC-MP", "MP", f["mp_semantic"], "PR #18：64 条候选 0 批准（43 pending / 21 quarantined）；p3 无 MP 候选")
    fc_me = fc_sem("FC-ME", "ME", f["me_semantic"], "同上，ME 候选 0 批准")
    fc_rs = fc_sem("FC-RS", "RS", f["rs_reviewed"], "2 张 METHOD 与 1 条 CASE 的许可、适用、关联均 pending")
    rwd = _gate("G-RWD", "奖励 / BC / PPO 资格", [
        _item("R1", "至少一个实验族的正式比较完成，且结论按 DECISIONS 报告", f["fc_results"],
              reason="尚无正式比较", owner="WS-B / 研究者"),
        _item("R2", "J1 用人工 Q0/QH/F 标签独立验证（不得自证）", f["j1_validated"], reason="无人工标签", owner="WS-B"),
        _item("R3", "J1 decode 上限 8,192 / 16,384 决定", f["decode_cap"], reason="待研究者决定", owner="研究者",
              pending=True),
        _item("R4", "#16 接口问题 R1–R5（来源局部身份、episode 入口验证、STOP、缓存幂等、RELATION）修复并 A/B 签收",
              f["r1_r5_fixed"], reason="已确认 5/5，未修复", owner="WS-B（修复）/ WS-A（签收）"),
        _item("R5", "奖励各分量分开登记；pending 不填 0", True, reason=None, owner=None),
    ], depends=["FC-<family>"])
    return [g_eng, pp1, fc_ms, fc_mp, fc_me, fc_rs, rwd]


# ------------------------------------------------------------------ PP1 procedure pilot
PP1_EST_MIN = dict(screen_per_prefix=10, q0_per_pair=1.5, qh_history_first_read=8, qh_per_pair=3, f_per_reply=4,
                   fa_per_error=1, adjudication_per_item=3)


def pp1_calls(eligibility_rows: list[dict]) -> list[dict]:
    el = [r for r in eligibility_rows if r.get("plan_job_id") and r["joint_eligibility"] == "ELIGIBLE"]
    calls = [dict(call=i + 1, prefix_id=r["prefix_id"], owner_id=r["owner_id"],
                  arm={"OFF": "OFF", "MS": "RET-MS"}[r["subset"]], plan_job_id=r["plan_job_id"],
                  existing_request_id=r["existing_request_id"], terminal_key_sha256=r["terminal_key_sha256"])
             for i, r in enumerate(sorted(el, key=lambda r: (r["owner_id"], r["subset"] != "OFF")))]
    return calls


def pp1_cost(prefixes: int = 8, raters: int = 2, f_by_both: bool = True, overrun: float = 1.5,
             seconds_per_call_expected: float = 25, load_seconds: float = 240, timeout: int = 300) -> dict:
    e = PP1_EST_MIN
    pairs, replies = prefixes, 2 * prefixes
    per_rater = pairs * e["q0_per_pair"] + prefixes * e["qh_history_first_read"] + pairs * e["qh_per_pair"] + \
        (replies if f_by_both else replies // 2 + math.ceil(0.2 * replies)) * e["f_per_reply"]
    screener = prefixes * e["screen_per_prefix"]
    adjud = math.ceil(0.25 * replies) * e["adjudication_per_item"]
    fa = replies * e["fa_per_error"]          # upper bound: one error per reply
    total = raters * per_rater + screener + adjud + fa
    calls = replies
    return dict(
        calls=dict(generator=calls, gpu_jobs=1, judge=0, needcard_writer=0, paid_api=0, retries=0),
        gpu_seconds=dict(expected=round(load_seconds + calls * seconds_per_call_expected),
                         upper_bound=load_seconds + calls * timeout,
                         note="upper bound = every call hits the 300 s timeout; no automatic retry"),
        human_minutes=dict(per_rater=per_rater, raters=raters, screener=screener, adjudication_upper=adjud,
                           fa_audit_upper=fa, total=total, total_with_overrun=round(total * overrun)),
        assumptions=dict(PP1_EST_MIN, f_by_both=f_by_both, overrun=overrun),
    )


PP1_STOP = dict(
    before_start=["任一请求包未通过 B 投影检查", "QH 背景或筛查标签未在生成前冻结", "缺少研究者对 16 次调用的授权"],
    engineering=["技术失败（超时 / 空输出 / OOM / 320 token 截断）≥ 2/16：停止，报告，不自动重试",
                 "任一输出与请求身份不符或缓存出现异内容覆盖：停止"],
    blinding=["表单本身泄露条件、资源或模型分数：停止并修正表单（回复中自身出现的提法照常展示，由审计侧标记）"],
    safety=["任何 F8 严重：当日报告研究者；不因此改协议"],
    procedure=["单件中位耗时 > 估计的 2 倍，或 Q0/QH 不确定率 > 40%：结束 PP1 后修订表单，只做程序性修改"],
    never=["偏好方向、效果量或各臂 F 错误率都不是停止或修改正式协议的理由（结果锁定）"],
)

PP1_METRICS = ["完成率与锁定率", "各表单单件耗时（中位、P90）与估计之比", "Q0/QH 不确定率与 split 率",
               "Q0/QH 两人一致率（描述性，n = 8）", "F 逐项一致率与证据引用有效率", "QH 附录 / RAW 检索使用率",
               "盲态探针：QH 锁定后问“你认为哪份回复参考了过去的对话”，猜中率（描述性）",
               "技术痕迹计数（实体字符、截断）"]


def pp1_protocol(eligibility_rows: list[dict], qh_backgrounds: dict | None = None) -> dict:
    calls = pp1_calls(eligibility_rows)
    return dict(
        protocol=PROTOCOL + ":PP1", status=STATUS, purpose="程序可用性验证；不估计资源效应，不进入正式分析",
        inputs=dict(prefixes=sorted({c["prefix_id"] for c in calls}), arms=["OFF", "RET-MS"], calls=calls,
                    source="P2 ELIGIBILITY_54 的 16 个 ELIGIBLE 输入（8 OFF + 8 MS = lexical-v0 Top-1 整段 RAW）",
                    renderer="PR #10 G0e renderer（request_packet）；不是 PR #18 的 E1 renderer",
                    decode="G0e：greedy，max_new_tokens 320，timeout 300 s，无自动重试"),
        qh_backgrounds=qh_backgrounds,
        flow=["1 筛查整理者（非审阅者）对 8 个前缀填写表单 S，标签封存（生成前）",
              "2 QH 背景 = 完整 as-of RAW，生成前冻结（本轮已构建，见 qh_backgrounds）",
              "3 WS-A 导出 16 个请求包；WS-B 投影检查；研究者授权后生成 16 次",
              "4 审计侧技术检查（空、截断、超时、实体字符），生成对 id 与位置哈希",
              "5 审阅者 A、B 各自完成 8 对 Q0 并锁定",
              "6 A、B 各自完成 8 对 QH 并锁定，随后回答盲态探针",
              "7 F：16 份回复由 A、B 都做（PP1 需要一致性数据），或由第三人完成",
              "8 审计侧 F-A（锁定后）；分歧处理；导出与程序指标报告"],
        disagreement=dict(q="不强制一致；对结果按 pair 规则取非不确定答案的均值，一胜一负记 split；原始标签全部保留",
                          f="严重项不一致时由裁决者（不参与该前缀）给出单独的裁决标签；原始标签保留",
                          log="分歧及裁决理由逐条记录"),
        timing="每页记录打开、提交、锁定时间戳；报告每人每表单总时长与单件耗时",
        stop=PP1_STOP, metrics=PP1_METRICS,
        separation=dict(default="PP1 的 8 个前缀不进入正式 FC-MS 样本（它们本就不在 162 抽样框中）",
                        pooling="只有在查看 PP1 结果之前书面预注册合并规则时才可合并；默认不合并",
                        exposure="PP1 的 RET-MS vs OFF 结果查看后，这 8 个前缀登记为 outcome_same_contrast",
                        reporting="PP1 结果只作描述性、探索性报告"),
        cost=pp1_cost(),
    )


def freeze(spec: dict) -> dict:
    body = dict(spec, protocol=PROTOCOL, status=STATUS, base=BASE,
                supersedes="nothing; #17 candidate b28cf37b and frozen P2 v1 2b6057c8 unchanged")
    return dict(body, protocol_sha256=object_sha256(body))
