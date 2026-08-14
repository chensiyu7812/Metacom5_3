# PM V1.5 V5.4 人工测量 V2：历史证据、冲突处理与 PM 学习用途

日期：2026-08-10  
权威合同：`data/pm_v1_5_contracts/v5_4_human_measurement_calibration_v2.json`

## 结论

这次人评不是为了增加一个“human reviewed”标签，而是一次 measurement-instrument qualification：先确认人类能否稳定识别 Quality、Function、Risk，再决定现有 LLM 是否有资格大规模生成 PM effect supervision。

尚未使用的 V1 包已废止。V2 修正了两个实质错误：自由 1–5 分没有行为锚点；Risk UI 会把尚未查看的风险默认成 0。

## 过去人评真正提供了什么

| 历史证据 | 结果 | V2 吸收的规则 |
|---|---:|---|
| D2 paired measurement | 三向 IAA `.65625`；ME `.375` | 不把直接 A/B 偏好当唯一质量真值；保留 tie/unresolved |
| V3 atomic eligibility | 原子轴 raw agreement `.84375–.96875` | Function 与 Risk 拆成有证据的原子判断 |
| H1R dual review | overall kappa `.5756`；ME raw `.5833` | 必须逐组件报告，overall 不得掩盖坏组件 |
| minimum RS sanity | 单一、未实名 reviewer；无 IAA；12 条被迫选择 | 单人/不明身份结果只作描述，不作 gold |
| support-need adjudication | 16 项中 13 项有至少一处分歧；goal exact-set `.375` | 裁决只解决分歧，不改写裁决前 IAA |
| historical asset inventory | 9 个逻辑资产；任务、副本、grain 不同 | 不跨任务池化，不把副本当新增独立样本 |

## Quality 为什么仍用 1–5，但不再让个人标准决定标签

四轴各自冻结行为锚点。标注者先在 1/3/5 中找最近行为，2/4 只表示相邻锚点之间。长度、建议数量和文风偏好不能单独加分。

绝对分只用于检查量表和 LLM response score。PM effect 的主量为：

`同一标注者、同一 state、同一 seed 的 ON composite − OFF composite`

因此“甲一直偏严、乙一直偏松”的常数偏移不会直接成为 ON/OFF 标签。`|delta| < 0.50` 固定为 tie；方向相反或一方 material、一方 tie 都进入第三真人裁决。

## Risk 是否已经证明 LLM 不会评

没有。现有证据只说明：两家 LLM 在 48 个普通 canary 回复上的 material-event raw agreement 为 `.9167`，但其中没有 severity-3，也没有冻结的高风险阳性分母。这既不能证明 LLM 不会评，也不能证明它能召回真正重要的风险。

V2 用 24 个自然 control 和 24 个单风险富集项补齐 sensitivity/specificity 分母。构造意图只用于抽样，不是答案。Risk 的 0 必须逐类显式选择；空白永远是 missing。

可扩展风险监督不要求全部依赖同一个 LLM：

- literal wrong-owner、typed time/version contradiction、内部资源标识泄露优先使用确定性审计；
- unsupported personal cause、边界侵犯、过度直接和非字面 grounding 由人类校准 LLM；
- 确定性规则没有命中不等于 safe。

## 人类与 LLM 不一致时怎么办

1. 先计算人–人一致性，不先看 LLM。
2. 若人–人构念门失败：当前任务没有 human gold；停止 LLM 资格比较，修改 codebook/培训或收窄构念。
3. 若人–人构念门通过：一致项和第三 identified human 的分歧裁决形成 calibration reference。
4. 再打开旧 LLM 结果，逐任务、逐风险族计算：
   - Quality：response correlation、paired uplift correlation、material direction agreement；
   - Function：三个原子轴与 derived function agreement；
   - Risk：material sensitivity、safe specificity、critical sensitivity、family macro recall。
5. Codex 或研究者不得看内容后选“更合理/更有利于 PM”的一方。

若 LLM 通过，它只是 development-scale proxy：Risk positives、LLM-human disagreement 和 sealed claims 仍保留人工审核。若 LLM 未通过：

- Quality：补充 anchored human paired labels，或删除/收窄 learned Quality 主张；
- Function：使用 typed executor/deterministic adherence 加人工子集，不扩大模糊标签；
- Risk：语义风险改成人工评价，训练只保留确定性风险，或收窄论文 risk claim。

## 与“PM 能学出来、能及格”的关系

人评包本身不是训练数据。它决定哪一种标签生成器有资格扩展到 development effects。

只有满足以下顺序才继续：

1. 人类构念稳定；
2. 至少 Quality uplift 与 Function contribution 存在非恒定、双向的有效 signal；
3. 自动/确定性测量达到对应资格门，或有足够人工标签；
4. grouped/cross-fitted PM 学习优于 prior/rule；
5. 最终 16 动作政策与 always-off、fixed-high、transparent rule、cost-matched fixed 等同栈 baseline 比较；
6. ESConv、EvoEmo、ES-MemEval 只在方法冻结后进入互补外部证明链。

测量失败时停止的是该构念的标签扩展，不是凭空宣布“PM 概念失败”；但也不能为了让 PM 及格而改答案、改门槛或让 Codex代替真人裁决。
