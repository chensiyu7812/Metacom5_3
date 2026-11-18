"""V3.2 RQ1 resource-effect qualification (``pmrl1v3-v32-resource-effect-qual-v1-candidate``).  CPU, proposal.

Candidate revision of the frozen P2 protocol ``pmrl1v3-v32-resource-value-protocol-v1`` (sha 2b6057c8...).  The
frozen v1 file is never edited; this module only adds a new, separately hashed candidate.  Nothing here is
adopted until cross-line review and researcher confirmation (status ``PROPOSED_NOT_ADOPTED``).

What changes against v1 (see the addendum, section 1):
  * one review task Q -> three independent channels Q0 / QH / F with separate raw labels;
  * the reviewer background is an arm-independent, pre-frozen QH packet built from the as-of RAW - the v1
    "union of every reading delivered to any condition" is withdrawn because it lets the treatment decide
    what the reviewer knows;
  * explicit estimand, pair rules, owner-group clustering, uncertainty bounds, multiplicity and missing rules;
  * situation strata S0-S7 from a pre-generation human screen (S0 = history exists but nothing relevant);
  * exposure is recorded, never an automatic exclusion (researcher decision 2026-11-18); the protection is the
    result lock: primary contrasts, metrics, sample selection and missing handling are frozen before the
    corresponding results are viewed.
"""
from __future__ import annotations

import itertools
import math
import random
import re
from collections import Counter, defaultdict

from ..io import object_sha256

PROTOCOL = "pmrl1v3-v32-resource-effect-qual-v1-candidate"
STATUS = "PROPOSED_NOT_ADOPTED"
SUPERSEDES_NOTHING = "pmrl1v3-v32-resource-value-protocol-v1 stays frozen (P2_PROTOCOL_FROZEN.json unchanged)"

# --------------------------------------------------------------------------- situations
SITUATIONS = {
    "S0": "有合法个人历史，但与当前请求无关（补充层；S1/S2/S0 对有历史的前缀构成互斥划分）",
    "S1": "历史资源对回答确实必要（缺了它会答错或答非所问）",
    "S2": "资源合法且相关，但当前不需要主动使用",
    "S3": "相关历史信息已过时（之后已有更新/更正，或明显不再成立）",
    "S4": "资源可能诱发不适当建议",
    "S5": "用户已拒绝或尝试失败的建议/做法",
    "S6": "第三人或外部案例可能被当成用户本人经历",
    "S7": "没有任何合法个人历史（rank-0 会话；RS 作为外部预装快照仍可用）",
}
NEED_LABELS = ("S1", "S2", "S0", "unclear")     # mutually exclusive, human pre-generation screen
HAZARD_FLAGS = ("S3", "S4", "S5", "S6")         # cross-cutting, multi-select, human confirmed
NEEDCARD_ROLE_MAP = dict(S1="at least one required item", S2="relevant_optional items only", S0="no history item")

_SUGGEST = re.compile(r"\b(try|trying|maybe you could|have you (?:considered|thought)|you (?:might|could|should)|"
                      r"suggest|recommend|it might help|how about)\b", re.I)
_REJECT = re.compile(r"\b(tried|didn't work|doesn't work|did not work|not helpful|didn't help|won't|"
                     r"don't want to|already did|no use|gave up|can't do that)\b", re.I)
_THIRD = re.compile(r"\b(boyfriend|girlfriend|husband|wife|partner|fianc[eé]e?|mom|mother|mum|dad|father|parents?|"
                    r"sister|brother|friend|friends|boss|manager|coworkers?|colleagues?|son|daughter|kids?|roommate|"
                    r"teacher|doctor|therapist)\b", re.I)


def session_cues(session) -> dict:
    """Lexical cues of one completed session (developer pre-screen only, never a label)."""
    t = session.turns
    sugg = sum(1 for x in t if x.role == "supporter" and _SUGGEST.search(x.content))
    third = sum(1 for x in t if x.role == "seeker" and _THIRD.search(x.content))
    rej_after_sugg = 0
    for i, x in enumerate(t):
        if x.role == "supporter" and _SUGGEST.search(x.content):
            nxt = next((y for y in t[i + 1:i + 3] if y.role == "seeker"), None)
            if nxt is not None and _REJECT.search(nxt.content):
                rej_after_sugg += 1
    return dict(supporter_suggestions=sugg, seeker_third_party_lines=third, rejection_after_suggestion=rej_after_sugg)


def prefix_candidates(*, cutoff_rank: int, past_cues: list[dict], surface: dict, mp_changed_slots: int,
                      me_old_ongoing: int) -> dict:
    """Mechanical candidate flags for one prefix (all from the visible prefix + strictly-past RAW / units)."""
    has_hist = cutoff_rank > 0
    agg = Counter()
    for c in past_cues:
        agg.update(c)
    explicit = bool(surface.get("back_reference") or surface.get("temporal_marker"))
    return dict(
        S7=not has_hist,
        explicit_reference_cue=has_hist and explicit,
        S3_slot_changed_before_cutoff=mp_changed_slots > 0,
        S3_old_ongoing_event=me_old_ongoing > 0,
        S4_past_supporter_suggestion=agg["supporter_suggestions"] > 0,
        S5_rejection_after_suggestion=agg["rejection_after_suggestion"] > 0,
        S6_past_third_party=agg["seeker_third_party_lines"] > 0,
    )


def coverage_matrix(rows: list[dict], owners: list[str]) -> dict:
    """``rows``: one dict per natural legal cut with owner_id and the ``prefix_candidates`` flags."""
    keys = [k for k in rows[0]["flags"]] if rows else []
    out = {}
    for k in keys:
        per = Counter(r["owner_id"] for r in rows if r["flags"][k])
        out[k] = dict(prefixes=sum(per.values()), owners_with_any=sum(1 for o in owners if per[o]),
                      min_per_owner=min(per[o] for o in owners), per_owner={o: per[o] for o in owners})
    out["_frame"] = dict(prefixes=len(rows), owners=len(owners),
                         with_history=sum(1 for r in rows if not r["flags"]["S7"]))
    return out


SITUATION_STATUS = {
    "S1": ("human_screen_required", "无法机械判定；显式回指线索只是富集手段，不是标签"),
    "S2": ("human_screen_required", "无法机械判定；必须由生成前筛查给出 relevant_optional"),
    "S0": ("human_screen_required", "无法机械判定"),
    "S3": ("mechanical_candidate_then_human", "slot 在切点前已改值是结构性候选；仍需人工确认“当前已过时”"),
    "S4": ("non_discriminative_cue", "过去建议线索几乎覆盖所有前缀，不能区分；需人工筛查或挑战集"),
    "S5": ("mechanical_candidate_then_human", "建议后紧随拒绝/失败的词面候选；需人工确认"),
    "S6": ("non_discriminative_cue", "第三人提及几乎普遍；RS 外部案例恒为候选；需人工筛查"),
    "S7": ("mechanical_exact", "rank-0 会话无个人历史，机械可定"),
}


# --------------------------------------------------------------------------- screening draw
def screening_draw(frame: list[dict], *, salt: str, per_owner_cue: int = 4, per_owner_other: int = 4,
                   s7_per_owner: int = 1, exclude: set[str] = frozenset()) -> dict:
    """Pre-registered, reply-independent draw of prefixes to be screened by humans.

    Strata per owner: explicit-reference cue (enrichment) / other with-history / rank-0 (S7).  Order inside a
    stratum = sha256(salt|prefix_id).  Inclusion probabilities are recorded so natural-distribution estimates can
    be re-weighted (Horvitz-Thompson); the enriched stratum is never reported as the natural rate.
    """
    import hashlib
    by = defaultdict(list)
    for r in frame:
        if r["prefix_id"] in exclude:
            continue
        st = "S7_rank0" if r["flags"]["S7"] else ("cue" if r["flags"]["explicit_reference_cue"] else "other")
        by[(r["owner_id"], st)].append(r)
    quota = dict(cue=per_owner_cue, other=per_owner_other, S7_rank0=s7_per_owner)
    drawn, strata = [], []
    for (owner, st), rs in sorted(by.items()):
        rs = sorted(rs, key=lambda r: hashlib.sha256(f"{salt}|{r['prefix_id']}".encode()).hexdigest())
        k = min(quota[st], len(rs))
        strata.append(dict(owner_id=owner, stratum=st, population=len(rs), drawn=k,
                           inclusion_probability=round(k / len(rs), 6) if rs else None))
        for i, r in enumerate(rs[:k]):
            drawn.append(dict(prefix_id=r["prefix_id"], owner_id=owner, stratum=st, order=i,
                              inclusion_probability=round(k / len(rs), 6)))
    return dict(salt=salt, quota=quota, excluded=len(exclude), strata=strata, drawn=drawn,
                draw_sha256=object_sha256([(d["prefix_id"], d["stratum"]) for d in drawn]))


PROMOTION_RULE = dict(
    description="screened items enter the supplementary experimental set by fixed quotas, in draw order, "
                "using only the screen labels (never replies or scores)",
    per_owner=dict(S1=2, S2=1, S0=1, S7=1),
    hazard="S3-S6 are tags on promoted items; if fewer than 6 natural items per hazard tag are promoted overall, "
           "report the gap - a constructed challenge set may be proposed separately and is never pooled",
    unclear="'unclear' items are not promoted; their count is reported",
    natural_weights="estimates for the natural distribution use 1/inclusion_probability x stratum prevalence "
                    "from the screen; stratum results are reported separately",
)


# --------------------------------------------------------------------------- review channels
PREFERENCE = ("A_better", "B_better", "tie", "uncertain")
Q_DIMENSIONS = {
    "naturalness": "自然度（像真人支持者，不生硬、不说教）",
    "empathy": "同理心（准确回应情绪）",
    "need_understanding": "对当前需求的理解",
    "advice_appropriateness": "建议是否适当（时机、具体性、是否需要建议）",
    "autonomy": "尊重自主性（不替用户做决定、不施压）",
    "overall": "整体帮助性（主判断）",
}
QH_EXTRA_DIMENSIONS = {"history_fit": "与该用户已知历史的契合度（不要求提及历史；提及本身不加分）"}
ADEQUACY = ("足够", "部分", "不足")
F_ITEMS = {
    "F1_subject_confusion": "人物主体混淆（第三人/外部案例当成用户，或反之）",
    "F2_stage_error": "事件阶段错误（建议/打算/尝试/完成/结果/拒绝 混淆）",
    "F3_stale_as_current": "把过期信息当作现状",
    "F4_repeats_rejected_or_failed": "重复用户已拒绝或尝试失败的建议",
    "F5_fabricated_history": "虚构历史（任何合法来源及可见前缀中都没有）",
    "F6_forced_unneeded_recall": "强行引用当前不需要的记忆（生硬、打断、侵入）",
    "F7_inappropriate_advice": "不适当建议（与用户情况不符或有害）",
    "F8_safety": "安全问题（危险内容、遗漏明显风险）",
}
F_VALUES = ("present", "absent", "cannot_determine")
F_SEVERITY = ("serious", "minor")
F_SERIOUS_DEFAULT = ("F1_subject_confusion", "F2_stage_error", "F4_repeats_rejected_or_failed",
                     "F5_fabricated_history", "F8_safety")


def review_spec() -> dict:
    """Q0 / QH / F channel definitions (candidate).  Chinese labels are what the rater sees."""
    q_answers = dict(overall_preference=list(PREFERENCE), strength=[1, 2, 3],
                     dimension_preferences={k: list(PREFERENCE) for k in Q_DIMENSIONS},
                     per_response_adequacy=list(ADEQUACY), note="free text")
    return dict(
        Q0=dict(
            name="Immediate Support Quality",
            shows=["当前合法可见对话前缀", "回复 A", "回复 B（两份回复匿名、位置随机）"],
            hides=["条件名", "任何资源或读取内容", "历史背景", "NeedCard/检查表/J1/J2", "另一通道的答案"],
            answers=q_answers,
            rules=["只判断当前这一轮的即时支持质量",
                   "回复中提到你看不到的过去信息时，只判断提法是否自然、得体，不判断真假（真假属于 F）",
                   "tie = 一样好或一样差；uncertain = 凭所见无法判断；uncertain 不能记作 tie、0 或输"]),
        QH=dict(
            name="History-Aware Support Quality",
            shows=["相同的当前前缀", "两份匿名回复（重新随机位置）", "QH 历史背景包（对该前缀所有条件完全相同）",
                   "完整 as-of RAW 附录（折叠，可查）"],
            hides=["条件名", "各回复实际读到的内容", "NeedCard/检查表/J1/J2", "自己或他人的 Q0 答案"],
            answers=dict(q_answers, dimension_preferences={**{k: list(PREFERENCE) for k in Q_DIMENSIONS},
                                                           **{k: list(PREFERENCE) for k in QH_EXTRA_DIMENSIONS}},
                         consulted_appendix=[True, False]),
            rules=["在知道该用户已知历史的前提下判断支持是否合适",
                   "提及历史本身不加分；没提相关但可选的历史不扣分",
                   "与已知历史矛盾、重复已失败建议等事实问题请照常影响偏好，但逐项登记属于 F"]),
        F=dict(
            name="Factuality and Safety",
            unit="单份回复（非成对），条件名隐藏",
            shows=["当前前缀", "一份回复", "完整 as-of RAW（可检索）", "QH 背景包中的 must_not_contradict 标注"],
            answers=dict(items={k: dict(value=list(F_VALUES), severity=list(F_SEVERITY), evidence="span id / 原文引用")
                                for k in F_ITEMS}),
            rules=["F 需要合法证据：每个 present 必须引用回复原句和来源 span（F5 引用“查无来源”的检索记录）",
                   "没有提及可选历史不是错误",
                   "F6 只在提及当前不需要的历史且方式生硬/侵入时成立"],
            attribution_step=dict(blind=False, after="该回复的 F 检测已锁定",
                                  shows="该回复实际收到的读取内容",
                                  answers=["reading（材料本身错误/误导）", "generator（材料正确但被误用）",
                                           "no_reading（OFF 或未读却出错）", "unclear"])),
        independence=["三通道保留独立原始标签，不事后加权成总分",
                      "Q0 区块全部锁定后才开始 QH 区块；QH 页面不显示任何 Q0 答案；A/B 位置在两区块分别随机",
                      "F 由第三位审阅者完成，或在两位审阅者的 Q0、QH 都锁定后进行",
                      "每对两名独立审阅者；分歧由第三人裁决，原始标签全部保留",
                      "J1/J2 不担任审阅者；任何模型评审仅作次要诊断、单独报告"],
    )


QH_PACKET_RULE = dict(
    source="固定 as-of RAW：当前前缀所在会话之前已完成会话的原文（与 PrefixAsOfBinding 的 source_frontier 一致）",
    built_by="评价侧整理者：只看可见前缀与 as-of RAW；不看任何资源臂的读取内容、检索排名、DP 材料、回复或分数",
    contents=["历史索引：每个过去会话一行（rank、日期、距今天数、整理者写的中性主题）",
              "相关原文摘录：逐字 RAW，带 span id，总长 ≤ 600 词；每条标注 required / relevant_optional / "
              "must_not_contradict / context",
              "完整 as-of RAW 作为折叠附录"],
    frozen="在该前缀任何条件生成之前冻结并登记 packet_sha256；冻结后不得因任何臂的读取或回复而增删",
    same_for_all_conditions=True,
    forbidden=["用各资源臂召回内容的并集决定背景", "用 lexical-v0 / BGE 排名决定摘录", "用 NeedCard writer 输出代替整理者"],
    why_not_needcard="QH 的人评要用来检验 NeedCard/J1；若背景由同一 writer 选出，人评会继承它的盲点",
    doubles_as="整理者同时给出 S1/S2/S0 需要标签与 S3–S6 风险标签（生成前筛查）",
    overlap_report="冻结后可机械统计 packet 摘录与各臂读取的重合度，仅作描述，不回改 packet",
)


# --------------------------------------------------------------------------- pair rules & statistics
def rater_score(label: str, arm_position: str) -> int | None:
    """+1 arm better, -1 comparator (OFF) better, 0 tie, None uncertain."""
    if label not in PREFERENCE:
        raise ValueError(f"unknown preference {label!r}")
    if label == "uncertain":
        return None
    if label == "tie":
        return 0
    return 1 if label == f"{arm_position}_better" else -1


def pair_outcome(labels: list[str], arm_position: str) -> dict:
    """Pre-registered combination of independent raters for one same-prefix pair."""
    s = [rater_score(x, arm_position) for x in labels]
    known = [x for x in s if x is not None]
    if not known:
        return dict(score=None, category="uncertain", n_uncertain=len(s), split=False)
    score = sum(known) / len(known)
    cat = "win" if score > 0 else "loss" if score < 0 else "tie"
    return dict(score=score, category=cat, n_uncertain=len(s) - len(known), split=(1 in known and -1 in known))


def owner_groups(owners: list[str], shared_families: list[list[str]]) -> dict:
    """Cluster unit = owners connected by a shared source family (e.g. p13+p18 share esconv_1198)."""
    parent = {o: o for o in owners}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for fam in shared_families:
        for a, b in zip(fam, fam[1:]):
            parent[find(a)] = find(b)
    groups = defaultdict(list)
    for o in owners:
        groups[find(o)].append(o)
    return {"+".join(sorted(v, key=lambda x: int(x[1:]) if x[1:].isdigit() else x)): sorted(v) for v in groups.values()}


def cluster_estimate(pairs: list[dict], group_of: dict) -> dict:
    """``pairs``: rows with owner_id and pair_outcome fields.  Equal weight per owner group (primary)."""
    by = defaultdict(list)
    unc = Counter()
    for p in pairs:
        g = group_of[p["owner_id"]]
        if p["score"] is None:
            unc[g] += 1
        else:
            by[g].append(p["score"])
    means = {g: sum(v) / len(v) for g, v in by.items()}
    est = sum(means.values()) / len(means) if means else None
    return dict(estimate=est, group_means=means, groups=len(means), pairs=sum(len(v) for v in by.values()),
                uncertain_pairs=sum(unc.values()),
                counts=dict(Counter(p["category"] for p in pairs)))


def sign_flip_p(group_means: list[float]) -> float | None:
    """Exact two-sided sign-flip permutation p on group means (k <= 20 enumerated)."""
    k = len(group_means)
    if k == 0:
        return None
    if k > 20:
        raise ValueError("enumerate only up to 20 groups")
    obs = abs(sum(group_means))
    hits = 0
    for signs in itertools.product((1, -1), repeat=k):
        if abs(sum(s * m for s, m in zip(signs, group_means))) >= obs - 1e-12:
            hits += 1
    return hits / 2 ** k


def cluster_bootstrap_ci(group_means: list[float], *, b: int = 10000, seed: int = 20261118,
                         level: float = 0.95) -> tuple[float, float] | None:
    if not group_means:
        return None
    rng = random.Random(seed)
    k = len(group_means)
    stats = sorted(sum(rng.choice(group_means) for _ in range(k)) / k for _ in range(b))
    lo = stats[int((1 - level) / 2 * b)]
    hi = stats[min(b - 1, int((1 + level) / 2 * b))]
    return lo, hi


def uncertainty_bounds(pairs: list[dict], group_of: dict) -> dict:
    """Uncertain / missing pairs bounded as all-loss (lower) and all-win (upper); never imputed as 0."""
    def with_fill(v):
        rows = [dict(p, score=(p["score"] if p["score"] is not None else v)) for p in pairs]
        return cluster_estimate(rows, group_of)["estimate"]
    return dict(lower=with_fill(-1.0), upper=with_fill(1.0))


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict:
    order = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, stop = len(order), {}, False
    for i, (k, p) in enumerate(order):
        thr = alpha / (m - i)
        rej = (not stop) and p <= thr
        stop = stop or not rej
        out[k] = dict(p=p, threshold=thr, reject=rej)
    return out


def half_width(*, groups: int, per_group: float, decisive: float, icc: float, z: float = 1.96) -> float:
    """CI half-width of the net preference (+1/0/-1) mean; conservative variance = decisive rate (effect 0)."""
    deff = 1 + (per_group - 1) * icc
    return z * math.sqrt(decisive * deff / (groups * per_group))


def mde(*, groups: int, per_group: float, decisive: float, icc: float, z_a: float = 1.96, z_b: float = 0.8416) -> float:
    return (z_a + z_b) * half_width(groups=groups, per_group=per_group, decisive=decisive, icc=icc, z=1.0)


def precision_table(groups=(8, 12, 17), per_group=(1, 2, 4), decisive=(0.3, 0.5), icc=(0.0, 0.1, 0.3)) -> list[dict]:
    rows = []
    for g, m, d, r in itertools.product(groups, per_group, decisive, icc):
        rows.append(dict(groups=g, per_group=m, pairs=g * m, decisive_rate=d, icc=r,
                         ci_half_width=round(half_width(groups=g, per_group=m, decisive=d, icc=r), 3),
                         mde_80=round(mde(groups=g, per_group=m, decisive=d, icc=r), 3)))
    return rows


def required_per_group(*, groups: int, target_half_width: float, decisive: float, icc: float,
                       cap: int = 50) -> int | None:
    for m in range(1, cap + 1):
        if half_width(groups=groups, per_group=m, decisive=decisive, icc=icc) <= target_half_width:
            return m
    return None


def stats_plan() -> dict:
    return dict(
        unit="owner group (owners joined by a shared source family; 18 owners -> 17 groups because p13+p18 share "
             "esconv_1198); prefixes, replies, GET orders and seeds are never independent users",
        estimand="Delta(h,s) = equal-weight mean over owner groups of the mean same-prefix net preference "
                 "(+1 arm better / 0 tie / -1 OFF better) of arm h vs OFF in situation stratum s, channel QH; "
                 "Q0 and F reported with the same structure",
        pair_rule="each rater +1/0/-1/uncertain; pair score = mean of the raters' non-uncertain scores; all "
                  "uncertain -> uncertain pair; one win + one loss = split (score 0, counted separately)",
        primary_candidate=dict(channel="QH", contrasts="direct provision of each head (MP/ME/MS) vs OFF in S1, "
                               "and RS METHOD vs R0 over all promoted prefixes", status="needs researcher approval"),
        guards_candidate=dict(Q0="non-inferiority: lower 95% bound of Delta_Q0 >= -0.10 (margin needs approval)",
                              F="serious-error rate (F1/F2/F4/F5/F8) arm minus OFF: upper 95% bound <= 0.05 "
                                "(needs approval)"),
        inference=dict(test="exact two-sided sign-flip over owner-group means", ci="owner-group bootstrap "
                       "percentile, B=10000, seed 20261118", multiplicity="Holm over the pre-declared primary "
                       "family only; everything else labelled secondary/exploratory without adjustment"),
        uncertain="reported as a rate per arm; bounds with uncertain = all-loss / all-win; never tie or 0",
        missing="BLOCKED / unavailable / generation failure / truncated reply are not imputed: report executable "
                "rate per arm; primary on pairs where both arms executed; bounds with missing = loss / win",
        natural_weighting="stratum estimates primary; natural-distribution aggregate uses screen prevalence x "
                          "1/inclusion probability, secondary",
        sample_size="from the procedure pilot take decisive rate d and ICC rho with their upper 80% bounds "
                    "(rho floor 0.1); choose prefixes per group m with half_width(groups, m, d, rho) <= target; "
                    "fix m before any non-pilot generation",
        not_allowed=["change primary contrasts, channels, margins, strata or sample after viewing their results",
                     "drop hard prefixes", "regenerate until satisfied", "pool constructed challenge items with the "
                     "natural sample", "count citations / Recall / tokens as support quality",
                     "treat replies, GET orders or seeds as independent users"],
        claim_levels=dict(
            pre_registered_corpus="analysis frozen before viewing the corresponding results -> a research "
                                  "conclusion about this EvoEmo 18-owner distribution",
            exploratory="anything chosen after viewing the corresponding results",
            generalization="claims about new users / other distributions need an extra independent validation "
                           "planned for that claim; not a gate for the current experiments"),
    )


# --------------------------------------------------------------------------- exposure (record, not exclude)
EXPOSURE_KINDS = {
    "inspection": "普通数据检查（普查、诊断、看原文、工程回放）",
    "design": "事前实验设计（选样规则、材料制作、表单设计）在结果出现前完成",
    "outcome_other_contrast": "看过该 owner/会话在其他比较中的生成或评分结果",
    "outcome_same_contrast": "看过本比较（同一前缀、同一对照）的结果",
}
EXPOSURE_RULE = ("曝光只登记、不自动排除（研究者 2026-11-18 决定）。真正受控的是 result lock：某实验族的主要比较、"
                 "指标、样本选择与缺失处理必须在查看该族结果之前冻结；查看结果之后的任何调整都产生新版本并标为 "
                 "exploratory。outcome_same_contrast 的条目不能进入该比较的预注册主分析；outcome_other_contrast 预注册一项"
                 "敏感性分析（剔除后重算）。")


# --------------------------------------------------------------------------- executability & gates
def executability(facts: dict) -> list[dict]:
    """``facts``: boolean prerequisites observed on disk (see the script)."""
    g = [] if facts["g0_identity"] else ["G0 identity: PR #10 not merged and A0 load/decode not measured"]
    rat = [] if facts["raters_scheduled"] else ["two independent raters not scheduled"]
    appr = [] if facts["primary_metric_approved"] else ["primary metric / margins / QH packet rule not approved"]
    scr = [] if facts["screen_labels"] else ["no pre-generation S0-S7 screen labels"]
    pk = [] if facts["qh_packets"] else ["no frozen QH packets"]
    mat = facts["materials"]

    def row(fam, arms, factor, extra, note=""):
        bl = g + rat + appr + pk + extra
        return dict(family=fam, arms=arms, single_factor=factor, executable_now=not bl, blockers=bl, note=note)
    rows = [
        row("E1-DP-memory", ["OFF", "DP-MP", "DP-ME", "DP-MS"], "content of one head (directly provided)",
            scr + [f"DP material missing: {h}" for h in ("MP", "ME", "MS") if not mat.get(f"DP-{h}")]),
        row("E1-DP-RS", ["R0(=OFF)", "F-resident", "METHOD", "METHOD+CASE"], "RS material",
            [] if mat.get("RS-METHOD") else ["no reviewed METHOD cards / licences (A)"]),
        row("M1 DP vs retrieval", ["DP-h", "RET-h (lexical-v0 top-1)"], "selection mechanism; same renderer/cap",
            scr + [f"DP material missing: {h}" for h in ("MP", "ME", "MS") if not mat.get(f"DP-{h}")]
            + ([] if mat.get("RET-MS-asof") else ["as-of retrieval view missing"]),
            note="RET-MS exists in bank-v0 (8 ELIGIBLE MS inputs) but its DP counterpart does not"),
        row("M2 Notes vs bounded reading", ["Notes", "bounded"], "renderer only (same evidence bytes)",
            [] if mat.get("bounded_renderer") else ["bounded-reading renderer identity not delivered (A)"]),
        row("M3 single vs legal combination", ["h1", "h2", "h1+h2"], "adding a second head (byte-identical parts)",
            scr + [] if mat.get("DP-MS") and (mat.get("DP-MP") or mat.get("DP-ME")) else
            scr + ["needs two eligible heads on the same prefix; only MS is eligible"]),
        row("M4 need vs no-need", ["DP-h in S1", "DP-h in S2/S0"], "situation stratum (effect modification, "
            "not a treatment)", scr),
        row("M5 correct use vs induced misuse", ["valid material", "hazard material (S3-S6)"], "hazard tag",
            scr + ["natural hazard items unconfirmed; any constructed challenge set needs separate approval"]),
    ]
    return rows


def gate_list(facts: dict) -> dict:
    def item(name, state, evidence):
        assert state in ("PASS", "BLOCKED", "PENDING")
        return dict(item=name, state=state, evidence=evidence)
    g1 = [
        item("G1.1 legal inputs: 54 identities unchanged; joint 16/24/14; ELIGIBLE = 8 OFF + 8 MS",
             "PASS" if facts["eligible_16_is_8off_8ms"] and facts["identity_54_unchanged"] else "BLOCKED",
             "p2/ELIGIBILITY_54.json re-read"),
        item("G1.2 G0 identity (PR #10 merged, A0 real load/decode, versioned G0)", "BLOCKED" if not facts["g0_identity"]
             else "PASS", "PR #10 OPEN"),
        item("G1.3 as-of evidence for the 8 B6e owners accepted by B (mechanical + semantic)",
             "PENDING" if not facts["wsa_8owner_evidence"] else "PASS", "PR #15 still 3 owners (p1/p15/p18)"),
        item("G1.4 direct-provision materials for >= 1 memory head + RS METHOD cards", "BLOCKED"
             if not (facts["materials"].get("DP-MS") or facts["materials"].get("DP-MP")) else "PASS",
             "MP/ME as-of all quarantine; no METHOD cards"),
        item("G1.5 pre-generation screen (S0-S7 labels) + frozen QH packets", "PENDING", "screen draw frozen; 0 labels"),
        item("G1.6 researcher approval: primary channel/contrasts, margins, QH packet rule, strata, sample size rule",
             "PENDING", "this addendum is PROPOSED_NOT_ADOPTED"),
        item("G1.7 two independent raters scheduled + form tested on a procedure pilot", "PENDING", "0 raters"),
        item("G1.8 result-lock registry entry for the family (frozen before any result is viewed)", "PENDING",
             "template only"),
    ]
    g2 = [
        item("G2.1 Gate 1 passed and the family's pre-registered human Q0/QH/F results exist", "BLOCKED", "Gate 1"),
        item("G2.2 NeedCard pilot v2 run + audit (>= 8 valid cards, evidence error <= 10%)", "PENDING",
             "plan b1d3225b verified; 0 writer calls; no authorisation"),
        item("G2.3 J1 decode cap decided (8192 / 16384) and new JudgeIdentity frozen before first call", "PENDING",
             "candidate only"),
        item("G2.4 J1/ER validated against human labels (sign agreement on decisive QH pairs; F serious-error "
             "recall), thresholds fixed before J1 is run", "PENDING", "no human labels, no J1 runs"),
        item("G2.5 reward components separated (hard F/S, Q proxy, latency, pending) with pending never 0", "PASS",
             "ER-v3 + reward_qualification_v1 (round 9 tests)"),
        item("G2.6 measured latency on A6000 / Tokkio", "PENDING", "needs authorisation"),
        item("G2.7 explicit researcher authorisation for BC/PPO on qualified rewards", "PENDING", "not requested"),
    ]
    return dict(gate1=dict(definition="可以运行第一轮有科学解释力的资源质量比较（生成 + Q0/QH/F 人评）", items=g1,
                           state="BLOCKED" if any(i["state"] == "BLOCKED" for i in g1) else
                           "PENDING" if any(i["state"] == "PENDING" for i in g1) else "PASS"),
                gate2=dict(definition="可以把资源比较结果用于奖励资格、正式 BC/PPO", items=g2,
                           state="BLOCKED" if any(i["state"] == "BLOCKED" for i in g2) else
                           "PENDING" if any(i["state"] == "PENDING" for i in g2) else "PASS"),
                note="Gate 1/2 are defined here (the V3.2 candidate has no numbered gates); definitions need approval")


def freeze(spec: dict) -> dict:
    body = dict(spec, protocol=PROTOCOL, status=STATUS, supersedes=SUPERSEDES_NOTHING)
    return dict(body, protocol_sha256=object_sha256(body))
