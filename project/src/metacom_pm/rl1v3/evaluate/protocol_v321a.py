"""V3.2.1-A working-protocol candidate (WS-B, round 12).  PROPOSED_NOT_ADOPTED until the researcher approves.

Version A = implicit Step-2: the PM's Step-1 learns WHEN to get, WHICH resource and WHEN to STOP; Step-2 stays
no-plan (pmrl1v3-g0e-no-plan-1); the Generator decides implicitly whether a resource applies, whether to use it and
whether to mention it.  This module only *adds* to V3.2.1 (d2fde5db); #17 (b28cf37b), #20 and the frozen P2 v1
(2b6057c8) are untouched.

Contents: research boundary, FC-MS scientific questions and conclusion tiers, channel roles, analysis family and
multiplicity, S1-shortfall rule, design-change ledger, review mechanics, gate amendments, power/precision with the
cluster floor, screening-yield model and three budget plans, item-by-item diff.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict

from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
from metacom_pm.rl1v3.io import object_sha256

PROTOCOL = "pmrl1v3-v321a-working-protocol-candidate-1"
STATUS = "PROPOSED_NOT_ADOPTED"
BASE = dict(v321=dict(protocol=V.PROTOCOL, sha256="d2fde5db53185f8632b7489bfe21aea6a8ae7d5ace1ea9f55261bce3b3ed7cca"),
            v32_candidate=dict(protocol=V.BASE["protocol"], sha256_prefix=V.BASE["sha256"]),
            frozen_p2_v1=V.BASE["frozen_p2_v1"], pp1_v321_sha256="b23b91eb2a9d9abf849d481f5952d591abfd5fea8ec55f0bdcffb28da987d2e3")

# ------------------------------------------------------------------ 1 research boundary (researcher decision: version A)
BOUNDARY = dict(
    version="A：隐式 Step-2（研究者已确认）；本阶段不增加独立的 PM Step-2 规划器",
    pm_step1="学习何时获取、获取哪些资源、何时 STOP（GET_MS / GET_MP / GET_ME / GET_RS / STOP）",
    step2="维持 no-plan（pmrl1v3-g0e-no-plan-1）：不额外输出计划，不增加学习动作",
    generator="隐式判断资源是否适用、是否使用、是否显式提及；这是 G 的行为，不是 PM 的动作",
    not_errors=["Generator 没有提及历史本身不算错误", "资源真实、相关，不等于此刻必须引用"],
    applicability_prompt="若以后加入更强的 applicability 提示，必须作为新的 renderer/Generator 版本，单独作为一个因素评价；"
                         "不得并入现有实验族，也不得在正式比较之间临时修改",
    no_tuning="不得依据正式比较结果反复调整 prompt、资源内容、渲染方式或样本；任何此类修改都开启新的实验族并登记",
)

# ------------------------------------------------------------------ 2 FC-MS questions
ARMS = dict(
    OFF="真实 OFF：同一前缀、同一 G/decode/renderer，没有任何额外资源块",
    DP_MS="Direct Provision 诊断条件：生成前由独立选材者（不看检索排名、不看任何回复）从全部合法过去会话中选出的一段完整"
          "会话 RAW（#19 DP_PENDING 的 selection_policy）；它衡量“若把合适的历史直接给 G”能带来什么，"
          "不是检索成绩，也不是已经学会的 PM",
    RET_MS="真实检索条件：lexical-v0 Top-1 的完整会话 RAW（as-of 检索身份）；不得改名为 DP",
)
DP_SELECTION_V_A = dict(
    rule="选材者 = 该前缀的筛查整理者（非该前缀审阅者），在表单 S 中完成：DP 会话 = 含“必要”片段最多的合法过去会话；"
         "无“必要”片段时取含“相关但可选”片段最多者；仍无则取最近一次合法会话；并列取较近者",
    why="与 #19 的“独立选材、全部合法 RAW、生成前、无排名”一致，并把选材变成可复现的标签规则，不新增人工步骤",
    needs="WS-A 对齐（#19 DP_PENDING 的 selector 字段）；研究者确认",
    s0_note="S0 中的 DP 会话按同一规则取最近会话，它代表“直接给一段与此刻无关的真实历史”，用于检查打扰与误用",
)
QUESTIONS = dict(
    primary=dict(
        id="FC-MS-1-P", contrast="DP-MS − OFF", channel="QH", stratum="S1（生成前人工确认）",
        estimand="S1 前缀上，按 owner 组等权的配对净偏好均值 Δ = P(DP 更好) − P(OFF 更好)，两名审阅者取均值；"
                 "不确定按规则处理（见 missing）",
        question="当生成前人工确认此刻需要历史时，把合适的历史直接交给 G，是否提高了解此人过往的支持者眼中的回复质量？",
        reads_as="资源潜在价值（mechanism）；不是检索质量，也不是 PM 学习收益"),
    secondary=[
        dict(id="FC-MS-1-S1", contrast="RET-MS − OFF", channel="QH", stratum="S1",
             reads_as="真实检索条件下的增量（检索 + G 使用的联合效果）"),
        dict(id="FC-MS-1-S2", contrast="DP-MS − RET-MS", channel="QH", stratum="S1",
             reads_as="检索选材造成的差距（同一 renderer、同一 G 下只改变选中的会话）"),
    ],
    guards=[
        dict(id="FC-MS-1-G1", what="Q0（即时同理心、自然度、需求理解）：DP−OFF、RET−OFF，S1 与 S2/S0 分开",
             role="保护指标：报告效果与区间，不作为成功标准"),
        dict(id="FC-MS-1-G2", what="F 严重错误：各臂率与 Clopper–Pearson 上界；配对“仅该臂出现严重错误”的符号检验",
             role="约束：报告有害信号；不显著不等于安全"),
    ],
    strata=dict(S2="资源相关但不必主动提：看是否打扰、自然度与事实安全", S0="有历史但无关：看误用与侵入",
                S7="无合法 MS：DP-MS/RET-MS 的请求若与 OFF 字节相同，效应结构性为 0，只做请求同一性与确定性核验，"
                   "不做人评；若 renderer 插入“无记录”提示则属于 renderer 因素，另行评价",
                reporting="S2/S0 只报告估计与区间，不作显著性结论"),
    fixed_within_family=["G0e 身份（权重、tokenizer、chat template）", "decode（greedy，max_new_tokens 320）",
                         "合法前缀与 as-of 截断", "renderer 身份（含转义策略、证据块框架与标签，DP 与 RET 完全相同）",
                         "Step-2 no-plan", "评审规则与表单版本", "QH 背景（完整 as-of RAW + 中性索引，生成前冻结）"],
    correct_use_vs_mention="“正确使用资源”与“引用资源”是不同指标：主指标是 QH 偏好；F1–F5 记录误用；F6 记录强行提及；"
                           "提及率只在审计侧锁定后描述性计算，永不作为奖励或成功标准",
)
CONCLUSION_TIERS = [
    dict(tier="资源潜在价值", supported_by="DP-MS vs OFF（FC-MS-1-P）", fc_ms_1=True,
         limits="只对 S1、对 G0e、对本 renderer、对 18 个 EvoEmo 人物成立"),
    dict(tier="检索质量", supported_by="DP-MS vs RET-MS、RET-MS vs OFF", fc_ms_1=True,
         limits="lexical-v0 Top-1；换检索器是新实验族"),
    dict(tier="renderer 效应", supported_by="同一选材、两个 renderer 身份的配对比较（单独实验族）", fc_ms_1=False,
         limits="FC-MS-1 固定 renderer，不能回答"),
    dict(tier="PM Step-1 策略增益", supported_by="已学习的 PM 策略 vs Fixed/OneShot/Always/Never 基线，在留出 owner 上",
         fc_ms_1=False, limits="需要先有 FC 结果与合格奖励（G-RWD）；FC-MS-1 不回答"),
]

# ------------------------------------------------------------------ 3 channels
CHANNELS = dict(
    QH="主要：了解此人过往后的长期支持质量；背景 = 完整 as-of RAW + 中性索引，同一前缀所有条件相同，生成前冻结",
    Q0="保护：即时同理心、自然度、需求理解；不显示历史",
    F="约束：事实、历史误用（F1–F6）与安全（F7–F8）；每个“有”都要逐字引用回复并给出依据",
    rules=["三通道不合成总分", "未提及记忆不算遗漏错误", "需要标签与 span 角色只进入密封审计 ledger，不向审阅者或 G 暴露",
           "所有审阅者看不到条件、资源、读取内容、需要标签、旧分数和模型评判"],
    margins="−0.10 非劣界与 +0.05 严重错误率差不作为已成立门槛；报告效果量、区间、严重错误率上界与精度限制；"
            "不显著只能写 inconclusive",
)

# ------------------------------------------------------------------ 4 analysis family + multiplicity
ANALYSIS = dict(
    unit="owner 组（17 组：p13 与 p18 共享 esconv_1198 合并）；组内前缀不视为独立",
    estimator="每组先对其 S1 前缀的配对得分（+1/0/−1，两名审阅者取均值）求平均，再对组等权平均",
    primary_test="精确符号翻转检验（组均值，双侧 α = 0.05）；95% 区间用组 bootstrap（10,000 次，种子固定），"
                 "并报告 t 区间（df = 组数 − 1）作敏感性",
    family=dict(
        primary=["FC-MS-1-P"],
        secondary_gated=["FC-MS-1-S1", "FC-MS-1-S2"],
        gate_rule="固定顺序：主检验 superior 时，次要两项以 Holm（α = 0.05）检验；否则次要只报告估计与区间，不下检验结论",
        guards="Q0、F 各自报告估计与区间；F 的两个配对有害检验（DP−OFF、RET−OFF）在 F 族内 Holm",
        exploratory=["S2/S0 分层", "分项偏好", "QH 背景使用率", "盲态探针", "提及率", "任何事后切分"],
    ),
    decisions=V.DECISIONS,
    missing="技术失败记 pending，按臂报告；不确定按全胜/全负给出边界，不插补；缺一名审阅者的对只进入边界",
    lock="主比较、主指标、分析集、缺失处理在第一份 FC-MS 生成结果出现前冻结；之后的改动只能作为探索性分析报告",
)
S1_SHORTFALL = dict(
    trigger="只看生成前标签计数，在任何 FC-MS 生成之前判定",
    steps=["按冻结规则做 Phase B（162 内）与 Phase C（自然框架 cue 层，每 owner 最多 +8）",
           "仍不足：在 FC-MS 生成前，可用一次登记的修订把 Phase C 上限提高（例如每 owner +16）；修订只改变筛查数量，"
           "不改变 S1 定义、表单或判定标准",
           "按实际 k_S1（含至少 1 个 S1 的组数）和每组 S1 数重新计算精度并公布，然后才生成"],
    downgrade="若 k_S1 < 8 或 S1 前缀 < 17：主比较降为描述性机制估计（只报告估计与区间，不报告检验结论）；"
              "这一降级由标签计数决定，与任何回复无关",
    never=["把 S2 改称 S1", "放宽 S1 定义", "按回复质量挑选样本", "以 RET-MS 是否检索到相关会话来筛选前缀"],
)
DESIGN_CHANGE_LEDGER = dict(
    replaces="不再以“研究者是否看过数据”作为排除条件",
    record=["时间戳", "改动内容（设计、抽样、比较、参数、表单、renderer、prompt）", "改动人", "理由",
            "改动时该实验族是否已有任何生成结果", "是否已有任何人工或模型评价结果", "受影响的分析"],
    rule="生成结果出现前的改动正常生效；之后的改动，受影响的分析一律标为探索性；数据曝光（看过 RAW、旧评审等）照常登记，不排除",
    schema=dict(id="str", t="ISO-8601", family="FC-MS-1|PP1|...", change="str", by="str", why="str",
                outputs_existed="bool", evaluations_existed="bool", affected=["analysis id"]),
)
REVIEW_MECHANICS = dict(
    packages="按角色分包：整理者（S）/ 审阅者第一部分（Q0，无历史）/ 第二部分（QH、探针、F；含历史）/ 裁决者 / 审计侧 F-A",
    stage_gate="第二部分只能载入到“Q0 锁定事件哈希 = 协调人登记锚点”的记录中；锚点在收到 Q0 阶段文件时登记",
    positions="位置与页面顺序由审计侧秘密 salt 决定；每个通道恰好一半对照在“回复甲”，第二名审阅者为镜像（完全平衡）；"
              "salt 只先登记 sha256，全部锁定后公开",
    sealed_outputs="仓库是公开的：生成结果和审计映射在全部评审锁定前不得推送到仓库或任何审阅者可访问的位置；"
                   "只登记文件哈希",
    pseudonyms="审阅者以代码出现（R1、R2…），真实身份只在研究者处",
    translation="若提供中文译文：原文为准并始终显示；按句映射（原文 sha、译文 sha）；同一方法、同一译者完成全部条件；"
                "背景与前缀在生成前译好并冻结，回复在生成后由不知条件的译者翻译；不得润色或删减；"
                "译者不担任审阅者；本轮未提供译文（需要研究者决定由人或授权的 MT 完成）",
    display="回复按生成原文纯文本显示，不解释 HTML 实体",
)
PP1_STANCE = dict(
    prerequisite="PP1 保留为正式大规模人评的前置流程（研究者倾向），默认不豁免",
    not_blocking="PP1 不阻塞 FC-MS 的生成；生成结果在人评开始前封存、不查看",
    exploratory="PP1 的 Q0/QH/F 方向只作探索性记录，不改变正式研究的主比较、阈值、样本和缺失处理",
    pooling="默认不并入 FC-MS 统计",
    focus=["工具能否可靠运行", "实际单件耗时", "通读完整历史是否现实（与检索式略读对照：由 QH 页面的检索/展开记录得到）",
           "不确定率、分歧率、一致性", "证据引用是否准确（逐字引用 + 依据）", "Q0 先于 QH 的顺序效应风险"],
    order_effect="PP1 无法估计顺序效应（无反向顺序组）；只登记风险：Q0 先看到两份回复，QH 时已熟悉文本。"
                 "正式研究保留 Q0→QH 顺序（不让历史污染 Q0），并在 FC-MS 中把 QH 与 Q0 方向一致率作为描述性诊断",
)


# ------------------------------------------------------------------ 5 gates (amend V3.2.1)
def gates_v321a(f: dict) -> list[dict]:
    gates = V.gates_v321(f)
    by = {g["gate"]: g for g in gates}
    for g in gates:
        for it in g["items"]:
            if it["id"] == "C4":
                it.update(evidence="PP1 完成并通过程序验收（研究者倾向不豁免；书面豁免须另行登记）",
                          reason="PP1 未执行", unblock_owner="研究者 / WS-B")
            if it["id"] == "C2" and it["state"] != "PASS":
                it.update(reason="0 条标签；90 条初筛执行包已备（两名整理者，约 15–29 小时）",
                          unblock_owner="研究者（指派整理者）/ 整理者")
            if it["id"] == "P6":
                ok = f.get("instrument")
                it.update(state="PASS" if ok else "BLOCKED",
                          evidence="离线中文盲评工具 + 模拟端到端验收（填表、退出、导入、重开、锁定、导出、SHA、盲态）",
                          reason=None if ok else "工具未完成", unblock_owner=None if ok else "WS-B")
    eng = by["G-ENG"]
    eng["items"].append(V._item("E6", "最终执行器验收：加载守卫、持久日志、STOP 规则、请求 SHA 与获批协议绑定",
                                f.get("executor_accepted", False), reason="WS-A 的 CPU 参考状态机不是完整执行器；未验收",
                                owner="WS-A（实现）/ WS-B（验收）"))
    extra = [
        V._item("C7", "统一 renderer 候选通过 B 独立验收（实体、来源边界、单因素、原生 token、请求身份）并经研究者采纳",
                f.get("renderer_accepted", False),
                reason=("B 对 #21 候选的机械回执通过（8 前缀预览）；待研究者采纳，并在正式样本请求导出后复跑"
                        if f.get("renderer_receipt_pass") else "A 尚未提交统一 renderer 候选；验收计划已备"),
                owner="WS-A（候选）/ WS-B（验收）/ 研究者（采纳、决定转义）",
                pending=bool(f.get("renderer_receipt_pass"))),
        V._item("C8", "生成结果封存与设计改动 ledger 就位（公开仓库前不推送）", f.get("sealed_storage", False),
                reason="封存位置与 ledger 待协调人建立", owner="研究者 / WS-B"),
        V._item("C9", "主比较族与多重比较规则在生成前冻结", f.get("family_frozen", False), reason="版本 A 候选待批准",
                owner="研究者", pending=True),
        V._item("C10", "DP-MS 选材规则确认（选材者、规则、与 #19 对齐）", f.get("dp_rule", False),
                reason="版本 A 提议待 WS-A 对齐与研究者确认", owner="WS-A / 研究者", pending=True),
    ]
    for name in ("FC-MS", "FC-MP", "FC-ME", "FC-RS"):
        by[name]["items"] += [dict(x) for x in extra if name == "FC-MS" or x["id"] in ("C7", "C8", "C9")]
    for g in gates:
        states = [i["state"] for i in g["items"]]
        g["state"] = "PASS" if all(s == "PASS" for s in states) else ("BLOCKED" if "BLOCKED" in states else "PENDING")
    return gates


# ------------------------------------------------------------------ 6 power / precision
def t_q(q: float, df: int) -> float:
    if df <= 30:
        return V.t_quantile(q, df)
    z = {0.975: 1.959964, 0.95: 1.644854, 0.80: 0.841621}[q]
    return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df ** 2)


def mde(k: int, m: float, *, d: float = 0.5, icc: float = 0.1, power=0.80) -> float:
    se = math.sqrt(d * (1 + (m - 1) * icc) / (k * m))
    return (t_q(0.975, k - 1) + t_q(power, k - 1)) * se


def mde_floor(k: int, *, d: float = 0.5, icc: float = 0.1) -> float:
    """Limit of the MDE when every owner group gets infinitely many prefixes: only k reduces it."""
    return (t_q(0.975, k - 1) + t_q(0.80, k - 1)) * math.sqrt(d * icc / k)


def groups_needed(target: float, m: float, *, d=0.5, icc=0.1) -> int | None:
    for k in range(3, 400):
        if mde(k, m, d=d, icc=icc) <= target:
            return k
    return None


def precision_grid() -> dict:
    ks, ms, iccs = (8, 12, 17, 34, 51), (1, 2, 4, 8), (0.0, 0.05, 0.1, 0.2)
    rows = [dict(k=k, m=m, icc=i, mde=round(mde(k, m, icc=i), 3)) for k in ks for m in ms for i in iccs]
    floors = [dict(k=k, icc=i, floor=round(mde_floor(k, icc=i), 3)) for k in ks for i in iccs if i > 0]
    need = [dict(target=t, m=m, icc=i, groups=groups_needed(t, m, icc=i)) for t in (0.3, 0.2, 0.15, 0.1)
            for m in (2, 4) for i in (0.05, 0.1)]
    return dict(rows=rows, floors=floors, groups_needed=need, decisive=0.5,
                note="d = 决定率（非“一样/不确定”的比例）；ICC = 同组前缀配对得分的组内相关；MDE 为双侧 α 0.05、80% 把握")


# ------------------------------------------------------------------ 7 screening-yield model + budget plans
SCENARIOS = dict(low=dict(cue=0.15, other=0.03), mid=dict(cue=0.30, other=0.08), high=dict(cue=0.50, other=0.15))
EST = dict(label=3.0, prefix_skim=1.0, s7=1.0, q0_pair=1.5, qh_pair=3.0, f_reply=4.0, adj_item=3.0, fa_error=1.0)


def simulate_screen(owner_groups: dict[str, list[str]], cue_pop: dict[str, int], other_pop: dict[str, int], *,
                    m_target: int, cue_cap: int, other_cap: int, rate: dict, reps: int = 2000, seed: int = 20261119) -> dict:
    """Label-only sequential screening per owner group (cue first, then other), stopping at m_target S1 or the cap.
    Returns expectations over Monte-Carlo replicates (deterministic seed).  Also counts S2/S0 found along the way
    using fixed shares of non-S1 items (S2 0.35, S0 0.45, unclear 0.2) -- planning assumption only."""
    rng = random.Random(seed)
    tot = defaultdict(float)
    for _ in range(reps):
        k_s1 = s1 = screened = groups_s2 = groups_s0 = 0
        per_group = []
        for g, owners in owner_groups.items():
            cue = sum(min(cue_cap, cue_pop[o]) for o in owners)
            oth = sum(min(other_cap, other_pop[o]) for o in owners)
            found, n, s2, s0 = 0, 0, 0, 0
            for stratum, avail, r in (("cue", cue, rate["cue"]), ("other", oth, rate["other"])):
                for _i in range(avail):
                    if found >= m_target:
                        break
                    n += 1
                    if rng.random() < r:
                        found += 1
                    else:
                        u = rng.random()
                        s2 += u < 0.35
                        s0 += 0.35 <= u < 0.80
            # guarantee at least the initial 2 cue + 2 other + 1 S7 per owner are screened
            n = max(n, 4 * len(owners))
            k_s1 += found > 0
            s1 += found
            screened += n + len(owners)          # + S7 items (1 per owner)
            groups_s2 += s2 > 0
            groups_s0 += s0 > 0
            per_group.append(found)
        tot["k_s1"] += k_s1
        tot["s1"] += s1
        tot["screened"] += screened
        tot["groups_s2"] += groups_s2
        tot["groups_s0"] += groups_s0
        tot["mean_m_in_groups_with_s1"] += (s1 / k_s1) if k_s1 else 0
    return {k: round(v / reps, 2) for k, v in tot.items()}


def plan_cost(sim: dict, *, guard_prefixes: int, words_item: float, words_owner_full: float, n_groups: int) -> dict:
    """Hours.  Reading: 'per_item' = every prefix's as-of history read in full (upper bound);
    'incremental' = each person reads an owner's history once, in cutoff order (lower bound)."""
    rd = lambda w: w / 250.0                          # noqa: E731  minutes at 250 words/min
    s1 = sim["s1"]
    prefixes = s1 + guard_prefixes
    calls = 3 * prefixes
    pairs = 3 * s1 + 2 * guard_prefixes
    replies = 3 * prefixes
    owner_once = n_groups * 1.06 * rd(words_owner_full)          # every owner's full history read once
    screen_upper = sim["screened"] * (rd(words_item) + EST["label"])
    screen_lower = min(sim["screened"] * rd(words_item), owner_once) + sim["screened"] * (EST["label"] + EST["prefix_skim"])
    q_fixed = pairs * (EST["q0_pair"] + EST["qh_pair"])
    read_item = prefixes * rd(words_item)
    read_low = min(read_item, owner_once)
    rev_upper = 2 * (q_fixed + read_item) + replies * EST["f_reply"] + read_item
    rev_lower = 2 * (q_fixed + read_low) + replies * EST["f_reply"] + read_low
    audit = math.ceil(0.25 * replies) * EST["adj_item"] + 0.5 * replies * EST["fa_error"]
    h = lambda x: round(x / 60, 1)                    # noqa: E731
    return dict(fcms_prefixes=round(prefixes, 1), generator_calls=round(calls), pairs=round(pairs), replies=round(replies),
                screening_hours=dict(lower=h(screen_lower), upper=h(screen_upper)),
                review_hours=dict(lower=h(rev_lower + audit), upper=h(rev_upper + audit)),
                total_hours=dict(lower=h(screen_lower + rev_lower + audit), upper=h(screen_upper + rev_upper + audit)))


PLANS = dict(
    conservative=dict(label="保守", m_target=1, cue_cap=4, other_cap=4, guard_per_group=1,
                      design="每组最多 1 个 S1；S2、S0 共约 1 个/组作保护样本；筛查限于冻结的 162"),
    medium=dict(label="中等", m_target=2, cue_cap=12, other_cap=4, guard_per_group=2,
                design="每组最多 2 个 S1；S2、S0 各约 1 个/组；筛查到 Phase C（每 owner cue 最多 4+8）"),
    extended=dict(label="扩展", m_target=4, cue_cap=20, other_cap=8, guard_per_group=2,
                  design="每组最多 4 个 S1；S2、S0 各约 1 个/组；需在生成前登记修订，把 Phase C 上限提到每 owner +16"),
)


def budget_plans(owner_groups, cue_pop, other_pop, words_item, words_owner_full) -> list[dict]:
    out = []
    for pid, p in PLANS.items():
        per_scen = {}
        for sname, rate in SCENARIOS.items():
            sim = simulate_screen(owner_groups, cue_pop, other_pop, m_target=p["m_target"], cue_cap=p["cue_cap"],
                                  other_cap=p["other_cap"], rate=rate)
            k = max(2, int(round(sim["k_s1"])))
            m = max(1.0, sim["mean_m_in_groups_with_s1"])
            guard = min(p["guard_per_group"] * len(owner_groups), sim["groups_s2"] + sim["groups_s0"])
            cost = plan_cost(sim, guard_prefixes=guard, words_item=words_item, words_owner_full=words_owner_full,
                             n_groups=len(owner_groups))
            prec = {f"icc_{i}": round(mde(k, m, icc=i), 3) for i in (0.05, 0.1, 0.2)}
            serious_upper = round(V.cp_upper(0, cost["fcms_prefixes"] / 1.1), 3)
            per_scen[sname] = dict(screen=sim, cost=cost, primary_mde=prec, k_s1=k, m_s1=round(m, 2),
                                   downgraded=bool(k < 8 or sim["s1"] < 17),
                                   serious_upper_0_events_per_arm=serious_upper)
        out.append(dict(id=pid, label=p["label"], design=p["design"], scenarios=per_scen,
                        cannot_support=cannot_support(pid)))
    return out


def cannot_support(pid: str) -> list[str]:
    common = ["PM Step-1 策略增益（FC-MS-1 不训练、不比较 PM）", "renderer 效应（renderer 固定）",
              "18 个 EvoEmo 构造人物之外的外推", "−0.10 非劣（ICC ≥ 约 0.04 时任何 m 都不可达）",
              "“没有显著差异 = 没有效果”"]
    spec = dict(
        conservative=["小于约 0.55–0.75 的净偏好差异（每组只有 1 个 S1）", "S2/S0 分层结论", "严重错误率低于约 0.12–0.15（0 例时）",
                      "任何检验结论：按 S1_SHORTFALL 预计会降为描述性估计"],
        medium=["小于约 0.37–0.45 的净偏好差异", "S2/S0 分层显著性", "严重错误率低于约 0.07–0.08（0 例时）"],
        extended=["小于约 0.28–0.34 的净偏好差异（再加前缀也降不到 17 组下限：ICC 0.1 约 0.16）", "严重错误率低于约 0.04–0.05（0 例时）"],
    )[pid]
    return spec + common


ANSWERS = dict(
    credible_effect="17 组、每组 2 个 S1 时，80% 把握可检出的净偏好约 0.38（ICC 0.1）；每组 4 个约 0.29；"
                    "实际可用组数 k_S1 若降到 12 或 8，MDE 分别升到约 0.36/0.47（m = 4）",
    more_prefixes_same_owner="不够：同一 owner 的前缀共享历史与人物，ICC > 0 时 MDE 有下限 √(d·ICC/k)×(t+t)。"
                             "17 组在 ICC 0.1 下限约 0.16、ICC 0.2 约 0.23；m 超过 4–6 后几乎不再下降",
    more_owners="需要：k 是唯一能压低下限的量（k = 34 时 ICC 0.1 下限约 0.11），也是外推性的来源；但现有数据只有 18 个人物"
                "（17 组），新增独立人物需要新的纵向数据与许可，属于后续工作；本轮结论限定在这 18 个构造人物上",
    s1_shortfall="见 S1_SHORTFALL：只用生成前标签决定扩筛和是否降级；不改定义、不放宽、不看回复",
    mechanism_first="先做机制验证：FC-MS-1 预注册单一主检验，结论限定为“对 G0e、本 renderer、18 个人物，直接提供合适历史"
                    "在 S1 上的 QH 增量”；不承担“系统有效”或“PM 有效”的确认性结论。理由：DP 是诊断条件；组数少；renderer"
                    "与转义尚未定；PP1 前没有评审一致性数据；S1 数量未知",
)


# ------------------------------------------------------------------ 8 item-by-item diff
DIFF = [
    dict(id="A1", area="研究边界", v321="未单列 Step-2 与 G 的分工", version_a="版本 A：Step-1 学获取与 STOP；Step-2 no-plan；"
         "G 隐式决定适用/使用/提及；不提及不算错；applicability 提示须版本化单独评价；禁止按正式结果调 prompt/资源/样本",
         why="研究者确认版本 A", gate="FC-* C9；G-RWD"),
    dict(id="A2", area="FC-MS 主比较", v321="FC-MS 比较 OFF/DP-MS/RET-MS，按 S1/S2/S0/S7 分层，未指定唯一主比较",
         version_a="主：S1 中 DP-MS − OFF 的 QH 净偏好；次：RET−OFF、DP−RET（S1，门控 Holm）；保护：Q0、F；S2/S0 描述",
         why="先冻结主比较，避免按结果方向换主指标", gate="FC-MS C9"),
    dict(id="A3", area="结论分层", v321="未区分", version_a="资源潜在价值 / 检索质量 / renderer 效应 / PM 策略增益 四类；"
         "FC-MS-1 只回答前两类", why="防止把 DP 结果写成 PM 成绩", gate="—"),
    dict(id="A4", area="臂定义", v321="DP-MS = MS-RAW-direct（固定规则）", version_a="DP-MS = 生成前独立选材（采用 #19 "
         "selection_policy），B 提议用表单 S 的 span 标签确定性选材；RET-MS = lexical-v0 Top-1，不改名；OFF = 真实无资源",
         why="DP 应是“合适历史”的诊断条件；规则可复现", gate="FC-MS C10"),
    dict(id="A5", area="S7", v321="S7 作为 FC-MS 分层之一", version_a="MS 族中 S7 无合法 MS：请求与 OFF 相同即结构性零效应，"
         "只核验请求同一性与确定性，不做人评", why="节省人工，避免评审同一回复", gate="—"),
    dict(id="A6", area="正确使用 vs 引用", v321="未明确", version_a="主指标 QH 偏好；F1–F5 误用；F6 强行提及；"
         "提及率只作锁定后描述，永不作奖励", why="未提及 ≠ 遗漏", gate="G-RWD"),
    dict(id="A7", area="margin", v321="−0.10/+0.05 为讨论候选", version_a="不采纳为门槛；只有研究者事先确认的 margin "
         "才能给出 non_inferior", why="17 组下不可达", gate="C1"),
    dict(id="A8", area="多重比较", v321="未定", version_a="单一主检验；次要固定顺序 + Holm；F 族内 Holm；其余探索", why="生成前冻结", gate="C9"),
    dict(id="A9", area="S1 不足", v321="Phase B/C 扩展，仍不足即报告缺口", version_a="增加：生成前一次登记的上限修订；"
         "k_S1 < 8 或 S1 < 17 时主比较降为描述性；从不改定义", why="标签驱动、与结果无关", gate="C2"),
    dict(id="A10", area="曝光 vs 设计改动", v321="曝光只登记不排除", version_a="新增设计改动 ledger：生成结果出现后的改动，"
         "受影响分析一律探索性", why="真正需要控制的是结果出现后的设计改动", gate="C8"),
    dict(id="A11", area="评审机制", v321="位置 sha256(协议|pair|通道)，表单结构", version_a="分包与阶段锚点；秘密 salt "
         "（先登记 sha）；每通道完全平衡 + 第二名审阅者镜像；生成结果在锁定前封存（公开仓库）；审阅者代码化", why="盲态与锁定可核验",
         gate="P6、C8"),
    dict(id="A12", area="翻译", v321="未规定", version_a="原文为准；按句映射；同一方法同一译者；背景生成前冻结；回复由不知条件者翻译；"
         "译者不兼审阅者", why="防止译文成为提示", gate="P5"),
    dict(id="A13", area="PP1 地位", v321="PP1 可书面豁免", version_a="保留为正式大规模人评的前置流程（默认不豁免）；"
         "不阻塞生成；默认不并入统计", why="研究者倾向", gate="C4"),
    dict(id="A14", area="表单 S", v321="S-4 摘录 + S-5 主题", version_a="S-4 span 只进审计 ledger；删除 S-5 主题（QH 不再"
         "使用整理者文字）；样本层（cue/other）对整理者隐藏；同一 owner 按时间顺序", why="避免层信息诱导 S1", gate="C2"),
    dict(id="A15", area="Gate", v321="G-ENG E1–E5；FC C1–C6", version_a="G-ENG 增 E6 执行器验收；FC 增 C7 renderer 验收、"
         "C8 封存与 ledger、C9 主比较族冻结、C10 DP 规则；P6 由工具完成转为 PASS", why="补齐本轮新增要求", gate="全部"),
]


def build(power_inputs: dict) -> dict:
    """Protocol identity covers rules and plans only; gate states (which change with PR status) live elsewhere."""
    body = dict(protocol=PROTOCOL, status=STATUS, base=BASE, boundary=BOUNDARY, arms=ARMS, dp_selection=DP_SELECTION_V_A,
                questions=QUESTIONS, conclusion_tiers=CONCLUSION_TIERS, channels=CHANNELS, analysis=ANALYSIS,
                s1_shortfall=S1_SHORTFALL, design_change_ledger=DESIGN_CHANGE_LEDGER, review=REVIEW_MECHANICS,
                pp1=PP1_STANCE, answers=ANSWERS, diff=DIFF,
                not_authorised="本文件不授权 GPU、Generator、Judge、奖励训练或合并",
                supersedes="nothing; V3.2.1 d2fde5db, #17 b28cf37b, P2 v1 2b6057c8 unchanged")
    body["gate_amendments"] = [d for d in DIFF if d["id"] == "A15"]
    body["power"] = dict(grid=precision_grid(), plans=budget_plans(**power_inputs))
    return dict(body, protocol_sha256=object_sha256(body))
