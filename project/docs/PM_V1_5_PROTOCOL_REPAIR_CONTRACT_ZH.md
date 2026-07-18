# PM-v1.5_1 方法修复合同：Step-0、路由语义与三层 Gate

更新时间：2026-07-18
合同状态：**TARGET_NOT_ACTIVE / PAID_RUN_BLOCKED**
适用对象：下一次重新生成、重新训练、重新冻结的 PM-v1.5_1 运行

## 0. 状态与效力

本文是审查后冻结并完成代码实现的目标方法合同，不是实验结果。代码完成不等于实验
主张成立；在本文末尾的 clean dry-run、lineage 审查、配置哈希和新 run identity 全部
完成前：

- 不允许开始新的付费 development、judging 或 external 调用；
- 旧 dry-run、旧自动语义审核、旧 cost-estimate hash 和旧 pilot 不得复用；
- 当前 checkpoint、内部报告或外部结果均不能被描述为由本合同产生；
- 任一 gate 未通过只能输出 `NOT_SUPPORTED`，不能通过调阈值改写结论。

本文取代 `PM_V1_5_CORE_CHAIN_PLAN_ZH.md` 中“完全无目录观测的 pure
pre-retrieval router”定义，作为下一次运行的优先方法合同。旧文档继续保存历史背景，但
与本文冲突时以本文为准。

## 1. 方法身份与有限主张

方法正式称为：

> **基于固定来源级观测的监督式 pre-item-retrieval router**
> supervised pre-item-retrieval router with fixed source-level observations

它不是 RL、POMDP、在线学习或长期用户改善模型。训练数据来自完整 action sweep 的监督式
反事实结果；每轮只做一次前向选择，不从外部测试奖励继续更新。

允许检验的窄主张是：在冻结数据与生成合同下，learned router 是否相对强规则路由器和
竞争性固定策略获得更好的质量—风险—资源权衡，并在相对高资源固定策略保持回复质量、
不增加证据误用信号的同时减少生成器输入 tokens。它不支持临床疗效、真实用户改善、
长期强化学习或跨数据集普适性结论。

## 2. 冻结因果顺序

每个决策单元必须遵守同一顺序：

```text
current dialogue state
  -> deterministic Step-0 source observation
  -> requested_action_id
  -> retrieval_attempts
  -> realized_action_id
  -> prompt_equivalence_id
  -> supporter generation
  -> outcome judging
```

任何 item-level memory/strategy 检索结果、生成回复和 outcome label 都不得回流到
`requested_action_id`。Step-0 必须在动作之前一次性、确定性地产生并内容寻址；真正的
item-level retrieval 只能在动作之后执行。

## 3. Step-0 观测合同

### 3.1 PM 可见字段

对 MP、MS、ME，每个来源仅允许固定、任务相关、有限精度的标量：

- `available`；
- bounded `item_count`；
- bounded age summary；
- expected retrieval/prompt token cost；
- `representation_valid`；
- query-to-source-centroid similarity。

Strategy 只允许：

- query 与少量预冻结 strategy-family centroids 的相似度；
- 由当前对话文本确定性计算的 readiness 标量，例如明确请求建议、明确拒绝建议、
  listening/readiness 或指令性风险；
- family availability、bounded count 与 expected cost。

连续值必须冻结归一化、裁剪和量化规则。缺失表示必须显式产生 `valid=false`，不得用某个
来源特有的魔法数代替。

### 3.2 仅审计可见字段

以下字段只能进入 manifest、attestation 与日志，不能进入模型特征：

- representation/centroid algorithm version；
- encoder 或 model ID；
- embedding dimensionality；
- config/representation/catalog build SHA-256；
- 原始构建路径、环境名和 run identity。

### 3.3 明确禁止

Step-0 和 PM 输入不得包含：

- raw memory 或 Strategy Card 文本；
- item/card ID、top-k ID 或 snippet；
- item-level top-1、max、P90、top-k score；
- embedding vector、norm、mean、std；
- gold source、required source、regime label 或 judge label；
- 完整 Strategy Retriever 的先验执行结果。

若 Step-0 执行了完整 retriever，它就不再是 coarse observation，必须作为正式 retrieval
attempt 记账并缓存复用；本合同的主要机制不允许这种实现。

### 3.4 Strategy family 的冻结要求

Strategy family 必须在查看 internal-test 和 external outcome 前定义。family 构造只能使用
Strategy Bank 的开发侧信息，并记录 family 数、各 family 大小、构建算法和哈希。需要
审计单一 family 是否近似等于某个 synthetic regime，及相似度是否近似直接编码 RS
oracle；发现该 shortcut 时整次数据构造失效，而不是在结果后删除可疑 family。

## 4. 动作、尝试、实现与 prompt alias

四个概念必须分开保存：

- `requested_action_id`：路由器在 Step-0 后请求的 4-bit 动作；
- `retrieval_attempts`：逐来源调用、命中数、失败原因、tokens、latency 与 USD；
- `realized_action_id`：根据实际进入 prompt 的 memory 来源和 Strategy 证据重算；
- `prompt_equivalence_id`：对规范化后的实际生成器输入做内容寻址。

zero-hit 是合法结果。例如 `requested=ME+RS` 可在 ME 零命中、RS 三命中时得到
`realized=M0+RS`。非法的是把 requested 写成 realized，或声称没有进入 prompt 的证据已
经生效。

完整 action sweep 仍保留 requested-action 的 intention-to-treat estimand。若多个 requested
动作产生相同实际 prompt：

- 可以只生成/判断一次以避免重复付费；
- 所有 alias 行必须显式共享同一 `prompt_equivalence_id` 和 label lineage；
- 每行仍保留独立 requested action、attempt 和 realized action；
- 训练、bootstrap 和有效样本量不得把同一生成/判断复制成独立证据。

## 5. required-hit 只是一项 outcome 前数据有效性门

required-hit 不得根据 outcome 分数筛选样本。它只用于数据构造阶段预先声明的 positive
challenge cells：若某 cell 声称某来源存在必要且可检索的证据，则在生成任何候选回复和
judge outcome 前，确定性 retrieval preflight 必须证明有命中，否则整个 cell/state
作废并按预注册规则重新构造。

自然分布和 external 中的 zero-hit 不删除、不重抽，也不视为错误。报告必须分开：

- natural/effectiveness strata；
- required-hit challenge/data-validity strata。

## 6. 候选机制与训练算法

在 internal-test 前必须同时冻结以下候选：

1. learned router + Step-0（主要机制）；
2. 强透明 rule router + 完全相同的 Step-0（主要机制 baseline）；
3. learned router without Step-0（只作内部消融，不进入外部主矩阵）；
4. cost-matched fixed action；
5. 显式 `ME+R0` 固定策略；
6. `MPMSME+RS` structured high-resource fixed。

固定策略不读取 Step-0，也不被人为添加未执行的 Step-0 成本。learned 与 rule 必须执行
同一 Step-0；learned 的总成本包含 Step-0，cost-matched fixed 按该总预算匹配。

### 6.1 训练侧候选算法

模型 family 只能在 train users 的 group-aware CV 中选择：

- 当前 absolute-outcome factorized HGB，作为保守基线；
- state-centered / paired-delta factorized HGB，作为优先候选；
- rule-relative safe residual HGB；
- LambdaMART/group ranking，作为探索候选而非默认赢家。

动作必须表示为 MP/MS/ME/RS 四个 factors，并允许预声明的 pairwise interactions。比较中
保持相同特征、用户分组、bootstrap 数、风险头和评估预算，避免同时改变目标、模型和
不确定性算法后无法归因。

rule-relative residual 必须把 `a_rule(s)` 或等价 baseline-action 编码纳入训练，并保证
同一 state 的 paired rows 与同一 user 永不跨 fold。只有下列保守条件同时满足，learned
才允许覆盖 rule action：

```text
delta_quality_LCB >= -epsilon_quality
delta_support_LCB >= -epsilon_support
delta_risk_UCB <= epsilon_risk
delta_utility_LCB > 0
```

不满足时回退到规则动作。无论采用 delta 还是 ranking，绝对 quality/risk ceiling 继续
生效，不能因相对改善而放行绝对不可接受的动作。

### 6.2 shortcut 与可辨识性审计

在候选选择前必须报告：

- Step-0 单特征和简单阈值对 source/RS oracle 的可预测性；
- shuffled-label、permuted-source、centroid-noise 和 no-Step-0 消融；
- 各 action factor 主效应及预声明 pairwise interaction 的覆盖；
- user/regime/environment 对 representation 的可识别性；
- alias 后独立 prompt/outcome 的真实数量。

若简单单阈值几乎完美恢复 synthetic label，不能把 learned PM 的高分解释为复杂状态调度。

## 7. 分割、冻结与一次性 internal-test

数据角色必须硬隔离：

- `train`：选择模型 family、目标形式、interaction 与结构超参数；
- `calibration`：冻结不确定性、非劣 margin、风险 ceiling、rule 数值阈值与
  cost-matched fixed；
- `internal_test`：只消费一次，评估已冻结的唯一 primary candidate 和预注册消融；
- `external`：仅在 internal gates 通过并生成 study freeze 后执行。

internal-test 前写入内容寻址 candidate manifest，至少包含代码、配置、数据、Step-0、
模型、rule、阈值、checkpoint 和输出 schema 哈希。消费动作必须写入 append-only ledger；
同一 run identity 第二次读取 outcome 直接失败。查看 internal-test 后不得改变 primary
candidate、阈值、baseline 或外部 condition matrix。

## 8. 三层 Gate

所有差值方向统一为 `PM - comparator`，以 user 为主要独立 bootstrap block。精确 margin、
置信水平和 utility 权重必须在新配置中于付费运行前冻结；未填写时状态保持
`TARGET_NOT_ACTIVE`。

### Gate M：机制价值（learned vs strong rule）

必须同时满足：

- quality 与 emotional support 非劣；
- resource-use risk 不增加；
- total utility 的配对 CI 下界严格大于 0；
- 回退、多样性、最大 action share 和严重 OOD 预注册护栏通过。

Gate M 不通过，不能声称 learned routing 比透明规则更有价值，也不能进入外部 learned
机制主验证。

### Gate F：竞争性固定策略护栏

分别对 cost-matched fixed 和 `ME+R0` 检查：

- quality/support 非劣；
- risk 不增加；
- utility 至少非劣；
- 成本和 action usage 完整报告。

只有 utility 严格优势通过预注册 CI 时，才可写“优于”相应 fixed comparator；仅非劣时
只能写“未全面弱于/保持竞争力”。若 PM 相对任一硬护栏明显劣化，不得只用相对
`MPMSME+RS` 省 token 来包装成功。

### Gate E：外部效率（learned vs structured high-resource）

必须同时满足：

- quality 非劣；
- 分层 evidence-risk audit 不显示增加；
- observed generator input tokens 的配对 CI 上界严格小于 0；
- Gate M 与 Gate F 已通过且 lineage 完整。

Gate E 只支持“保持质量并减少生成器输入”的窄效率主张。它不自动证明总美元、总延迟或
learned routing 优于同预算 fixed。

## 9. 成本与资源报告

不得再把不同资源折成一个未经验证的“token cost”。至少分别报告：

- Step-0 compute/lookup 次数与耗时；
- item-level memory/strategy retrieval attempts、hits 与耗时；
- observed generator input/output tokens；
- judge tokens（实验成本，不混作部署推理成本）；
- wall-clock latency；
- 按冻结价格计算的 USD。

主要效率指标暂保留 `observed generator input tokens`，因为它可直接观测且与当前主张
一致。总成本和 latency 只能描述性报告，除非另行冻结真实计价与 interleaved latency
设计。

## 10. 外部 condition matrix

外部主要矩阵按主张组织，不为保留“七条件”而添加弱 baseline：

- learned + Step-0；
- strong rule + Step-0；
- cost-matched fixed；
- `ME+R0`；
- `MPMSME+RS` structured high-resource。

`M0+R0`、raw-session top-k、full-history 可作为预注册 secondary references。no-Step-0
learned 只留在 internal ablation。任何 secondary condition 不得替代 Gate M/F/E 的指定
comparator。

## 11. Judge 角色隔离

development semantic gate、完整 action judging 与 final external judging 的端点必须在
以下四层完全不相交：

- endpoint alias；
- declared family；
- model identifier；
- normalized base URL + model route。

当前允许的 development panel 是 Gemini Flash Lite + DeepSeek Flash；final panel 是
GPT-4o + Claude。任何使用 `final_judge` 或同 family/model 的历史 development 自动审核
均不满足本合同，不能继承 PASS。隔离报告必须进入 dry-run hash、run manifest 和 artifact
attestation，并在 API key 解析与付费调用前 fail closed。

## 12. 失效与新 run identity

本合同改变方法身份、judge panel、成本计划和比较矩阵，因此以下材料全部只保留作历史：

- 旧 automated-semantic-review partial attempts 与判断；
- 旧 generation compatibility pilot；
- 所有旧 dry-run、call plan 和 accepted cost hash；
- 旧 candidate/freeze/config/attestation hash；
- 基于纯 pre-retrieval/free-probe 定义形成的 checkpoint 或结果。

新运行必须使用新的输出目录和 run identity；不得覆盖、拼接或抽取旧成功调用。

## 13. 激活清单

- [x] 本目标合同写入仓库；
- [x] CI 的 installed-package import 修复；
- [x] development/final judge 四层隔离实现与单元测试；
- [x] Step-0 schema、构建、成本和 shortcut audit 实现；
- [x] requested/attempted/realized/prompt-equivalence 全链路实现；
- [x] required-hit pre-outcome validity gate 实现；
- [x] transparent rule router 与 no-Step-0 ablation 实现；
- [x] train-only algorithm comparison 与 candidate manifest 实现；
- [x] append-only internal-test consumption ledger 实现；
- [x] Gate M/F/E 数值配置与测试实现；
- [x] 新 external condition matrix、freeze 与 claim wording 实现；
- [ ] 完整 clean-environment CI、dry-run 和 lineage 审查通过。

在最后一项完成前，合同状态不得改为 `ACTIVE`。
