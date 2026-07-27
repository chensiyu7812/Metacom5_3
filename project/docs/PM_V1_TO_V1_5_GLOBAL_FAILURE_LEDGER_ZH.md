# PM V1 → V1.5_1 全局失效模式账本与不可回归合同

更新时间：2026-07-27
适用分支：`pm-v1.5_1` 及当前修复分支 `pm-v1.5-hybrid-retrieval`
文档性质：历史复盘、研究有效性威胁账本、改动影响检查表；不是实验结果，也不替代冻结配置

> **单一问题源：** 本文是 PM-v1.5 当前唯一允许新增、关闭或升级问题状态的全局问题清单。
> `PM_V1_5_CORE_CHAIN_PLAN_ZH.md` 只维护研究主张、执行顺序和当前阶段；旧
> `PM_V1_FAILURE_LIMITATION_POSTMORTEM_ZH.md` 仅为只读历史证据。不得在后两者另建一套
> 活跃问题编号或待办清单；新问题必须回写本文，避免不同 Codex 各维护一份“当前事实”。

## 0. 为什么需要这份文档

本项目过去最危险的问题很少是“某一行代码写错”。更常见的是：局部代码分别看起来合理，
但整条因果链中的数据、动作、检索、prompt、生成器、judge、比较器或论文文字并没有指向
同一个实验处理（treatment）。这种错位可以让测试全绿、均值漂亮，却仍然不能支持论文主张。

本文把 PM-v1 的负面结果和局限、当前重新训练版 V1.5 从创建到 V1.5_1 修复期间发现的
全部主要问题，以及修复本身引入的二阶风险放进同一份账本。今后任何修复都必须先回答：

1. 改动触碰了因果链的哪一层；
2. 上下游是否仍然是同一个 treatment；
3. 哪些旧 artifact、hash、approval、checkpoint 和结果因此失效；
4. 修复会不会改变 estimand、样本独立性、比较器或允许的论文主张；
5. 哪些门必须在付费前、outcome 前、internal-test 前或 external 前重跑。

本文与 `PM_V1_5_PROTOCOL_REPAIR_CONTRACT_ZH.md` 的关系是：

- 后者定义当前目标方法；
- 本文保存“为什么必须这样定义”以及所有已知不可回归条件；
- 本文不能单独授权 API、训练、internal-test 或 external；
- 若本文、配置、代码、release manifest 和 artifact index 对同一状态说法不一致，必须先停机
  对齐，不能任选一个最方便的版本继续运行。

## 1. 一页总判断

### 1.1 四类足以推翻论文结论的错误

只要出现下列任一类，结果即使数值有利也不能支持目标主张。

| 类别 | 典型错误 | 为什么是 claim-fatal |
|---|---|---|
| treatment 身份错位 | 训练、固定策略和外部评测使用不同 prompt、RAG、Evidence Filter、检索阈值或生成参数 | 比较的不是同一个方法在不同策略下的结果，差值无法归因给 PM |
| 决策边界泄漏 | PM 在 requested action 前看到 item-level 结果、oracle、judge label，或近似答案键的免费目录探针 | “路由能力”可能只是读取答案或人工模板 |
| holdout / evaluator 污染 | internal 可反复消费；final judge 参与开发；external 结果反向用于阈值、模型或样本筛选 | 置信区间和泛化主张失去未见数据含义 |
| comparator / claim 错位 | 只和昂贵 high-resource fixed 比省 token，却声称 learned routing 优于同预算 fixed/rule | 结果最多证明“更省”，不能证明“学会了状态条件路由” |

### 1.2 PM-v1 最重要的结论

PM-v1 不是“完全没有价值”，也没有证据表明最终负面结果主要由故意作弊造成。它可靠地
显示了：更多历史和更多 RAG 不必然提高单步回复质量，资源调度问题值得研究。但它没有
证明 learned PM 优于同预算 `ME+R0`，没有学会稳定 abstention，且其数据、测量、特征和
selection rule 不足以支持强条件路由主张。

PM-v1 的正式外部动作曾表现为 `M0=0%`、`RS≈96.4%`，并集中到 `MSE+RS`。同预算
`ME+R0` 的 forced-swap 结果仍更好，说明“动作空间有 16 个”不等于“PM 学会了 16 种
状态条件决策”。

### 1.3 当前 V1.5_1 的准确状态

当前已经完成 development corpus、纵向 7,488-action sweep、20,736-call train/calibration
judging、719-state ESConv auxiliary generation、auxiliary train/calibration judging 和
fixed-seeker V3 formal bundle。旧 automatic-gold measurement 未获支持；随后按明确的
`LLM_WEAK_SUPERVISION_NOT_GOLD` 路线真实拟合过一个双域候选，但该候选在 longitudinal
和 ESConv calibration 均 100% 选择 `M0+R0`，正式冻结为
`NOT_SUPPORTED_FOR_INTERNAL_TEST_CONSUMPTION`。两个 internal outcome 和所有正式
external outcome 仍未打开。

零 API 根因审计进一步确认：同一 generator 能吸收干净的单条 oracle memory，故当前首要
失败不是“generator 完全不会使用 memory”；主因是旧 positive treatment 混入 irrelevant
item、多源 interference、16-way noisy argmax pseudo-oracle，以及 EvoEmo formal
204/204 metadata OOD。judge/rubric 是重要噪声来源，但不是唯一根因；旧 HGB collapse 是
这些上游问题的下游结果，尚不能单独证明模型族容量不足。

因此当前准确主张是：旧 treatment、旧 automatic-gold 和旧 weak-fit candidate 均
`NOT_SUPPORTED`；新的 unified-PM clean-contrast / external-shape V2 合同已经冻结，但尚未
生成新 response、尚未通过 train-only learnability，也未授权 formal fit。不得写成“PM
已经成功”，也不得把“代码和 readiness 门完成”写成“科学结果必然成功”。

### 1.4 全部问题的根因总索引（详细行仍以第 4、6、7 节为准）

截至 2026-07-27，本文共有 224 个互不重复的 V1.5 issue ID。逐条历史不删除；下表只把
它们压缩到未来每次改动都必须检查的 12 条因果链。某一层 PASS 不能替另一层补票。

| 根因层 | 对应详细账本 | 已真实遇到的代表性失败 | V2 永久护栏 | 当前 |
|---|---|---|---|---|
| 方法/主张身份 | `ID/CLAIM/COMP` | 同预算 fixed、rule、learned 与论文文字不一致；把 proxy routing 写成真实需求理解 | one PM、同观测 comparator、claim-to-gate 映射；禁止 clinical/human-optimal 表述 | 合同已冻结，结果未产生 |
| 数据血缘与泄漏 | `DATA/GRD/HOLD` | Bank/seed/EvoEmo 血缘、context defects、internal 可重复消费 | source/user/split/hash 隔离；repair overlay；internal one-shot seal | development 已修，internal 未开 |
| pre-action 观测 | `OBS/SEM/ENG` | item/oracle 泄漏、catalog embedding 免费探针、summary/history 外部形状不一致 | pre-retrieval source metadata only；同 state builder/BGE/Step-0；domain ID 禁止入模 | 旧 state 合法，V2 shape augmentation 待建 |
| action/retrieval 语义 | `ACT/DATA-17/HYB` | requested/realized/alias 混淆；helpful 与 irrelevant 混入；多源 interference；Hybrid 无合法收益 | clean helpful/placebo/harm 分离；selected-item exact audit；lexical-only；显式 interaction | 旧 treatment NO-GO，新 contrast 待建 |
| generator/prompt 机制 | `GEN/REL` | role order、长度、schema、repair、transport 与 prompt identity 多轮失配 | same state/prompt/generator/seed paired contrasts；content/transport 分层；uptake pilot 先于扩量 | oracle uptake 可行，production uptake 不足 |
| judge 与评价标准 | `JUDGE/JDG/SEM` | constant/sparse-zero、顺序敏感、schema兼容误判、automatic-gold 资格失败 | quality/evidence/risk 拆职；family 分开；abstain；N/A 非 0；小型人工 anchor 仅校准 | 只能作弱 LF，不能作 gold |
| label/estimand 构造 | `TRAIN/MODEL/METRIC` | 16 个含噪绝对分数取 max，winner's curse；state 难度压过 action effect | state×component paired effect；need 与 realized benefit 两阶段；禁止 direct 16-way argmax | V2 合同已冻结，标签待生成 |
| 小样本学习 | `TRAIN/DUAL` | action 行误当独立样本、高维 HGB、domain/action 数量淹没、全 M0 collapse | group-CV/bootstrap；强正则共享 heads；domain 仅加权不入模；M0/rule 双基线 | train-only learnability 未证明 |
| 外部迁移 | `DATA-15/16/20/21` | ESConv 与 EvoEmo 被误当两套 PM；EvoEmo 204/204 metadata OOD | 同一 checkpoint/legal mask；ESConv/EvoEmo 分开 gate；outcome-free support grid | ESConv 2.75% OOD；EvoEmo 100%，阻断 |
| cost/comparator | `COST/COMP` | 只报 generator input，忽略 Step-0/retrieval/zero-hit；弱 fixed strawman | deterministic cost vector；same-token fixed、transparent rule、high-resource fixed 分层比较 | 实现可复用，V2需重新绑定 |
| API/ledger/CI | `REL/ENG/ACC` | 429/5xx、空JSON、token截断、预算低估、identity复用、无锁并发、clean CI失败 | physical ledger、fresh identity、worst-case budget、bounded retry、exact continuation、clean tests | 工程护栏有效，不能替代科学 gate |
| 解释与停止规则 | `CLAIM/REL/第10–11节` | 把 pilot PASS 写 efficacy、失败后调阈值/样本直到过门、只挑有利结果 | 一次 calibration、internal/external sealed、失败如实 `NOT_SUPPORTED` | 持续约束 |

## 2. 全链路因果图与实验身份

每个 reportable 单元必须沿同一条内容寻址链传播：

```text
数据来源与实例血缘
  -> split / state / evaluator-only context
  -> pre-action Step-0 observation
  -> requested_action_id
  -> retrieval_attempts
  -> realized_action_id + realized evidence
  -> prompt_equivalence_id + exact supporter treatment
  -> generated response
  -> development/final judge treatment
  -> response/risk labels
  -> train-only model-family selection
  -> calibration-only selector/cost frontier
  -> frozen candidate + sealed internal bundle
  -> one-time internal Gate M / Gate F
  -> study freeze + external condition matrix
  -> external Gate E
  -> 与实际通过 gate 完全一致的论文文字
```

“同一套东西”不等于所有条件输入文本完全相同，而是除研究操纵外，所有影响 outcome 的
处理都相同或被明确建模。例如不同用户的 memory 内容本来就应不同；但 retriever、top-k、
minimum score、Evidence Filter 状态、supporter prompt、generator model/temperature/cap 和
finish-reason 规则不能因 condition 或 split 偷偷变化。

## 3. 严重度和状态词典

### 3.1 严重度

- `C0`：可使主要因果比较无效、逆转结论或使 holdout 不再成立；必须阻止付费/训练/报告。
- `C1`：可显著夸大性能、缩小不确定性或使机制主张超出证据；必须修复或降级主张。
- `C2`：工程、复现、成本或说明问题；通常不单独推翻结果，但可掩盖 C0/C1。
- `LIM`：当前单步 synthetic/LLM-judge 研究无法仅靠代码消除的永久边界。

### 3.2 状态

- `HISTORICAL_CLOSED`：历史问题已定位，相关旧结果不得迁移到新合同。
- `CODE_CLOSED_RUN_UNVERIFIED`：已有代码门和测试，但真实数据尚未证明会通过。
- `PENDING_RUN_EVIDENCE`：只能由未来冻结运行回答。
- `PERMANENT_LIMITATION`：必须在论文中披露，不能通过继续打补丁假装消失。
- `OPEN_RECONCILIATION`：当前 artifact 或单一事实源互相矛盾，必须先停机对齐。

“代码已修”永远不等于“科学问题已解决”。例如 shortcut audit 已实现，只说明我们有尺子；
只有实际 468-state 报告通过，才能说明本次数据没有触发该门。

## 4. PM-v1 全局问题账本

### 4.1 treatment、评测与比较器

| ID | 级别 | 问题 | 对主张的影响 | 当前处理 |
|---|---|---|---|---|
| V1-SYS-01 | C0 | V1 研发链历史上出现过 internal/external prompt、RAG、Evidence Filter、seeker world 或 baseline treatment 不一致 | 不能把差值归因给路由策略；不同机制的结果不能拼表 | 历史旧链不得复用；V1.5_1 用单一 supporter/retrieval/filter 合同和 freeze 绑定 |
| V1-SYS-02 | C0 | 早期 interactive comparison 允许不同 policy 产生不同 seeker 后续世界线 | 比较同时混入了 policy 和输入轨迹差异 | 后来改为固定 seeker tracks；当前只支持 fixed-input 单步因果比较 |
| V1-EVAL-01 | C0 | 10-turn bundle pairwise 出现强 AB/BA 顺序效应，四项 orientation consistency 均未过 0.80 | 816 次调用和约 12.27M prompt tokens 的该批结果只能作失败诊断 | `HISTORICAL_CLOSED`；不得作为 confirmatory result |
| V1-EVAL-02 | C1 | V4 multi-candidate absolute scoring 仍有 candidate-set/contrast effect | 不同 judge prompt 中的绝对 PM 分不能互相替换 | 只允许同一 prompt 内 paired delta；V1.5 增加位置平衡和数值 order pilot |
| V1-COMP-01 | C0 | 原主链缺少不可绕开的同预算 fixed；后补 `ME+R0` 才显示 PM 不占优 | 仅胜过 Full History/高资源 fixed 不能证明 learned routing | V1.5 Gate F 强制 cost-matched fixed 与 `ME+R0` 护栏 |
| V1-COMP-02 | C1 | 高资源 `best_fixed`、same-token fixed、Context Only、raw-session 和 full-history回答不同问题 | 把它们混成“PM 全面更优”会扩大主张 | V1.5 按 Gate M/F/E 和 secondary references 分层陈述 |

这里必须特别保留一个历史事实：V1 最终版本的许多直接泄漏和世界线问题后来已修复，
所以不能把 V1 的负面结果简单解释成“全是代码作弊”。V1 的有效负面结果主要说明当前
数据、观测、训练和 selection 不足；但任何产生于 treatment 不一致阶段的旧数字仍不可用。

### 4.2 数据、标签和统计单位

| ID | 级别 | 问题 | 对主张的影响 | 当前处理 |
|---|---|---|---|---|
| V1-DATA-01 | C1 | 1,728 cards 主要是 192 states × 9 inventory variants，只有 36 个 unique current texts | 行数虚大；模板和状态语义的有效独立样本很小 | V1.5 重新生成 52×9 states，并要求真实 corpus 审计 |
| V1-DATA-02 | C1 | user-fold 没有同时隔离 semantic family 和 normalized text | 内部泛化可由相同语义/句式模板支撑 | 新 split 和近重复/identity shortcut 审计；实际效果待运行 |
| V1-DATA-03 | C1 | 各 state 只有 2/4/8/16 个不等 action；完整 16-action state 很少 | action 与 inventory-rich 状态绑定，动作效果不可公平比较 | V1.5 每个 state 必须完整 sweep 16 actions |
| V1-DATA-04 | C1 | 没有均衡 context-only、memory-harmful、source-needed、strategy-helpful/harmful 等 regimes | M0/R0 即使在动作空间中，也未获得足够“应该赢”的监督 | V1.5 九 regime；但语义成立与否必须由 actual-corpus gate 证明 |
| V1-LABEL-01 | C0 | judge 的 `Overall` 与 Emotional Support 完全重合 | 所谓整体质量其实是 support，原主指标构念失效 | 删除 Overall；冻结六维 composite，并设 duplicate/correlation gate |
| V1-LABEL-02 | C1 | 单一 silver judge、风险维度低方差、verdict 与数值不一致 | PM 可能只学 judge 偏好，风险头接近常量 | 双 development family、逐维 MAD/constant/duplicate gate；无人评仍是 limitation |
| V1-STAT-01 | C1 | 同一 user/state/action 派生行高度相关，却容易被当作大 N | 置信区间过窄、模型选择过度乐观 | 以 user 为主要 bootstrap/block 单位；prompt alias 另行折权 |
| V1-RISK-01 | C1 | representative sample 与 stress sample 给出不同风险印象 | stress 率不能当 prevalence，普通抽样也不能证明安全 | 分层报告 representative/stress，风险主张限于 evidence/resource-use risk |

### 4.3 观测、模型、选择和检索

| ID | 级别 | 问题 | 对主张的影响 | 当前处理 |
|---|---|---|---|---|
| V1-OBS-01 | C1 | stable external PM 看不到实际 source relevance，只见文本和 metadata | 16 路选择在信息上可能不可辨识，理性退化为 action prior | V1.5 正式化有限 Step-0；无 Step-0 仅作消融 |
| V1-FEAT-01 | C1 | fitted TF-IDF 在 synthetic 覆盖 100%，EvoEmo token coverage 约 26.7% | semantic OOD 导致内部多样、外部 collapse | 固定表示和 Step-0；外部泛化仍需真实结果 |
| V1-MODEL-01 | C1 | Logistic/Ridge 线性头主要学习绝对分和 action prior，缺少可靠 uncertainty | 难以学习状态×动作交互，微小噪声决定 winner | V1.5 train-only 算法 family、bootstrap HGB、delta/residual/rank 候选 |
| V1-SEL-01 | C0 | `epsilon=0` 使成本只在完全同分时 tie-break | 名义 quality–risk–cost 实际是 quality winner-take-all | 新 utility 和 Gate M/F；禁止继续声称 V1 联合优化三者 |
| V1-SEL-02 | C0 | omission/strategy risk 阈值为 1.0，而预测被裁剪到 [0,1] | 两类门实际关闭，RS 的小质量优势即可常开 | 新逐维 UCB/相对风险门；效果待测 |
| V1-POLICY-01 | C1 | 外部 `M0=0%`、`RS≈96.4%`、`MSE+RS≈51.1%` | 没学会 abstention 或稳定策略关闭 | V1 的真实负面结果；新版本以多样性、M0/R0、最大 action share 为硬门 |
| V1-RETR-01 | C1 | source-level PM 配固定 top-k lexical retrieval，无 relevance threshold | 选中 source 就强塞弱相关 evidence；source 正确不等于 item 正确 | V1.5 明确只主张 source routing；realized evidence 和 zero-hit 分开记录 |
| V1-CREDIT-01 | C1 | 最终 outcome 混合 source 选择、item retrieval、generator 使用和 judge 偏好 | 低分无法唯一归因给 PM | 记录完整 lineage；不宣称 item-level 最优性 |

### 4.4 工程、范围与真实负面结果

| ID | 级别 | 问题 | 对主张的影响 | 当前处理 |
|---|---|---|---|---|
| V1-ENG-01 | C1 | 早期 M2b omission 可静默缺失，provenance/freeze 不完整 | 缺失风险标签仍可能被当完整样本 | 后续 fail-closed；旧未 attested 结果不可迁移 |
| V1-NEG-01 | 结果 | PM 未超过 Context Only、Session Retrieval 或同预算 `ME+R0` | learned routing advantage 未成立 | 必须诚实报告，不能靠新版本文字覆盖 |
| V1-SCOPE-01 | LIM | fixed-input 单步、turn 3/8、18 users、LLM judge | 不能证明长期情绪改善、信任或真实用户获益 | 永久披露；需要另一个闭环/真人研究 |
| V1-SCOPE-02 | LIM | PM-v1 是 supervised contextual router，不是 RL/POMDP | 不能声称长期 return、在线适应或 policy-induced distress change | 方法名和论文措辞永久收紧 |
| V1-SAFETY-01 | LIM | risk 是 evidence/resource-use risk，不是临床安全 | 不能写“心理健康安全”或“临床有效” | 使用限定术语并披露无临床验证 |

## 5. V1.5 → V1.5_1 修复时间线

| 阶段 | 主要发现 | 结论 |
|---|---|---|
| 初始会议版，PR #3 head `7ea2248` | free catalog probe、requested/realized 错位、internal 未密封、final judge 参与开发、CI 失败 | `NO-GO`；当时尚无正式结果需要撤回 |
| Step-0 方法争论 | 完全保留免费 probe 不合法；完全删除又可能让 16 动作不可辨识 | 选择正式、有限、可计费 source-level Step-0，并加入无 Step-0 消融 |
| 第一轮 V1.5_1 重构 `484e1e2` 附近 | Step-0、动作 lineage、judge 隔离、算法比较、三层 gate 已进入代码 | 仍发现 internal oracle audit、actual 468 语义门和中央 paid gate 等问题 |
| PR #4 head `b2333ac` | 上述主体修复；seed/Bank 共源确认并消除；chronology/order/internal seal 加固 | 仅 actual-corpus negative controls 仍不足 |
| `c5c38b6` | 12 fields × 2 controls、自然 corruption、静态扫描覆盖完成 | 又发现 semantic judge panel 可被 CLI 替换且未绑定 experiment config |
| `8910f4d` | endpoint alias/family/model/base URL/config hash 全绑定 | 方法代码审查通过，可进入逐阶段 dry-run |
| staged release `5fc2a88` 及后续 | 历史 pilot/approval 被记录；旧 config PASS 不能复用 | 继续遵守逐阶段 exact hash 授权 |
| V8 pilot | provider schema 用无研究意义的 `coverage_rationale<=180` 拒绝真实输出 | fail-closed；证明 provider 不应负责 evaluator rationale |
| V8.1 pilot | 正交 family 后仍有 2/9 surface fallback | 暴露 whole-bundle generation 的跨 case 污染/稳定性问题 |
| V8.2 真实 pilot | 8 次物理尝试、6 成功、2 失败；词面 advice-request gate 误杀语义有效输出 | `CONSUMED_FAILED_CLOSED`；approval/index 已按账本对齐 |
| 本轮修复前的 V8.3 工作树 | 冻结本地语义表示；Advice Readiness × Strategy Resource 正交；same-topic irrelevant decoy；pilot/formal 共用 V14 compiler | 该 dry-run 已因后续 runtime/input 修复失效；需全新 post-repair dry-run、审查和精确批准 |

## 6. V1.5_1 全局问题账本

### 6.1 方法身份、treatment parity 与论文对象

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-ID-01 | C1 | `pm-v1.5-supplemental` 与重新训练会议版都曾简称 V1.5 | 分支、release revision、checkpoint、freeze、结果完全分离 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ID-02 | C0 | development/sweep/external 可能分别声明 prompt、RAG、EF 或 generator 参数 | 单一 `supporter_generation_treatment`；所有 stage 内容寻址绑定 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ID-03 | C0 | V1.5 关闭 EF，但共享 metadata 曾写成 supervised filter | 行为与名称都必须写 `disabled_passthrough`；不得让审查者误认处理不同 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ID-04 | C0 | pilot 修成新生成协议，但 formal 52-user 一度仍保留旧 whole-bundle 路径 | pilot 与 formal 必须共享同一 contract/version/schema/prompt compiler | 当前已同步改为 casewise，`RUN_UNVERIFIED` |
| V15-ID-05 | C1 | V1.6/其他分叉与 `pm-v1.5_1` 同时存在，容易审错 branch/head | 每次审查和运行记录 branch、commit、dirty status、config SHA | 持续护栏 |
| V15-ID-06 | C1 | canary/forced-swap 的布尔名曾暗示 efficacy | 明确 `judge_sensitivity_not_pm_efficacy`；主效应由冻结 paired CI 决定 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ID-07 | C1 | 归一化 margin 0.02 容易写成原始量表 0.02 分 | 明确 [0,1] 的 0.02 ≈ 原 1–5 量表 0.08 | 持续论文护栏 |
| V15-ID-08 | C0 | fixed seeker V2 只在 prompt 写“尽量不超过 60 tokens”，代码没有表面长度门；真实运行 56 个成功 turn 中 51 个超过 60 whitespace words，另一次在 300-token provider cap 以 `length` 结束，导致整批停止。简单提高 cap 或切字符串都会分别留下无界回复或中句截断，并可能改变所有 condition 的后续世界线 | V3 把研究表面合同改为明确的 `<=60` normalized whitespace words；完整短回复原样保留，超长或 provider `length` 只允许确定性选择界内最长完整句前缀；完整原始 provider 输出、finish reason、选择 metadata 与 SHA 全部留账，正式轨迹要求 `mid_sentence_truncation_count=0`。历史 57 份真实 provider 文本零 API 回放 57/57 可选出合法表面，最大 60 words；双 dry-run 已逐字节复现。随后同合同 2-track/20-call pilot 真实 `PASS`：20/20 首次调用成功、零 retry/failure、1 次完整句前缀选择、最大 55 words、零中句截断，实付约 `$0.0236859`；identity `6dc86e09…f2c74` 已消费。该结果只认证 V3 compatibility，102-track formal 仍须新 dry-run 与独立批准 | `REAL_PILOT_PASS_FORMAL_102_TRACKS_UNVERIFIED` |
| V15-ID-09 | C0 | V3 pilot 虽已 PASS，但正式链路仍未原子迁移到 V3：`pm_v1_5.yaml` 仍声明 V2；study freeze、PM/EvoEmo runner、reference baseline 与共享 EvoEmo runner 仍硬编码 `FIXED_SEEKER_V22_STAGE`，两个外部驱动还只接受目录名 `evoemo_fixed_tracks_v1_5`。因此直接生成 V3 formal bundle 后也会被 freeze/外部消费者拒绝，或被迫错误退回 V2 | 新增零 API promotion preflight，先验证 V3 pilot attestation，再逐项检查 config、4 个正式 consumer 的 stage/目录合同和 102-track artifact。必须先一次性把 config、freeze、PM generation、reference baseline、shared runner 全部迁移到 V3，并补反向测试；随后才允许双 dry-run、独立批准 formal 102 tracks。当前真实 preflight 为 `BLOCKED`，明确列出 10 个 blocker | `ROOT_CAUSE_CONFIRMED_ZERO_API_PREFLIGHT_ADDED_PROMOTION_PENDING` |

### 6.2 pre-action observation 与 shortcut

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-OBS-01 | C0 | 决策前读取 MP/MS/ME query-to-catalog similarity，却称 pure pre-retrieval，且不计成本 | 正式 Step-0，公开方法身份、固定表示、单独计量；no-Step0 作消融 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-02 | C0 | catalog embedding norm/mean/std 可成为 source/environment/template 指纹 | 从 PM-visible features 删除；仅保留任务相关有限标量 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-03 | C0 | synthetic “需要哪个 source 就放匹配内容”可使 centroid similarity 近似 oracle | train-only 单阈值 + 多变量 group-CV probes、shuffled/permuted/noise/no-Step0 审计 | `PENDING_RUN_EVIDENCE` |
| V15-OBS-04 | C1 | 若 version/hash/model ID 进入特征，会成为环境身份捷径 | version/hash/dimension/build path 只进 audit，不进 PM | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-05 | C0 | Strategy Step-0 若先跑完整 top-k retriever，就是改名后的 item retrieval | 只允许 family centroids + current-turn readiness；否则必须正式记 retrieval attempt | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-06 | C1 | 完全删除 Step-0 会使 MP/MS/ME/RS 选择信息不足并退化成固定动作 | 保留合法有限 observation；无 Step-0 只作为可辨识性消融 | 设计选择，待结果 |
| V15-OBS-07 | C0 | shortcut audit 一度在 candidate freeze 前读取 internal needed sources/regime | predictive oracle 仅 train 216 states；其余 split 只做无 oracle 结构审计 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-08 | C1 | 只有单特征阈值审计可能漏掉 XOR/组合 shortcut | 增加正则 logistic、浅树等低容量多变量 user-group probe | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-09 | C1 | 配置允许 precomputed embedding，但历史 state 实际为空，PM 对未见用户文本仍主要依赖 hash/OOV 表示 | 冻结 `BAAI/bge-small-en-v1.5` 精确 revision/tree hash；当前 turn 与完整可见 state 双视图；train-only PCA；development/external 同 binding | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-10 | C0 | advice request/listen boundary 的词面正则既会误杀 provider 输出，也会成为 RS target 的答案键 | 删除词面硬 gate；五类 readiness 只作为连续语义观测和独立 evaluator 因子 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-11 | C0 | 即使 Step-0 合法，若正样本 source 总有同题 item、负样本永远异题，source centroid 仍可直接读出 oracle | 非 needed source 也放入 same-topic、明确非个人/无边际价值的语义 decoy；实际 item utility gate 与 shortcut audit 共同裁决 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-12 | C1 | 冻结 encoder 若在运行时下载、漂移 revision、进入 feature identity，或开发/外部用不同 pooling，会重现 treatment mismatch | local-files-only、tree SHA、spec SHA、CLS/normalize/dimension 全绑定；身份只进 provenance/freeze，不进数值特征 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-OBS-13 | C0 | 当前把完整对话 BGE 向量与 5 组手写 readiness 短句中心作最近邻，容易被 history/summary 稀释，并被口头解释成“理解了用户需求”。真实 outcome-free challenge 只有 14/20 full-context top-1 正确；4 个明确小建议请求被判成 ambiguous/listen，多个错误 margin 仅 `.0027–.0292`。BGE 官方定位也是 retrieval/semantic similarity，不是支持需求 gold classifier | BGE 只作候选共享表示；current turn、last assistant、history、summary 分视图进入强正则多任务 heads，输出 support-mode/goal/phase/distress 分布与 uncertainty/abstain。train-user grouped probe 必须比较 nearest-centroid、lexical、current-only、full-context 和 separated-view；关键 negation/context-dependent challenge 不能系统反向，且 downstream component-effect CV 必须显示增益，否则 BGE 不得被解释为需求理解 | `ROOT_CAUSE_CONFIRMED_V3_NEED_REPRESENTATION_QUALIFICATION_PENDING` |
| V15-OBS-14 | C0 | 旧 `Step0StrategyObservation` 只是 8 个全库 Strategy family centroid 相似度、5 个手写 readiness centroid 相似度与一个 `question_present`，不是可校准的用户需求观测：它把 `ambiguous` 错当真实 mode、缺少安慰/稳定类，把 current turn、last assistant、history、summary 混成表示，也没有 goal、phase、非临床紧迫度、source/family opportunity、uncertainty/OOD/abstain 的明确接口。若继续把它直接送进 PM，就会把“语义近似”误写成“理解用户需要” | V3 新增独立 `SupportNeedObservation`：冻结 BAAI 只编码 current/last-assistant/history/summary/current-vs-context 多视图，确定性边界与 inventory metadata 另行输入；以 outcome-blind `{4,8,12}` 维 train-only projection 和强正则 partial-label heads 输出 listen/explore/comfort-reassure/light-guidance/structured-planning、goal、phase、非临床 urgency、MP/MS/ME 与 clean-Bank family opportunity 概率，并显式报告 entropy/bootstrap/OOD/abstain。`ambiguous` 只表示不确定性，safety 独立绕过；所有给 PM 的 need prediction 必须为 user/dialogue-group cross-fitted。首批 75-dialogue outcome-blind packet 与 24 条 emotion×position 人工 anchor 已确定性构建，等待标注与真实 BAAI grouped pilot | `CODE_INTERFACE_AND_MULTIVIEW_BUILDER_CLOSED_FRESH_75_PACKET_PREPARED` |
| V15-OBS-15 | C0 | 第一批 24 条人工锚点中，`question_or_task_burden_limit` 被同时用作“用户明确边界”和“标注者建议低负担”；同时 23 条非 abstain 样本的真实 grouped OOF probe 虽在五类 mode log-loss 上略胜先验（最佳 lexical `1.7473→1.6176`），但只召回 `comfort_reassure`，其余四类 recall 均为 0；BAAI current/multiview 也未优于透明 lexical/structure。若此时 formal fit，会把小样本多数类塌缩包装成 need learning | 原 24 条以原始字节 SHA 和 normalized V2 双重绑定，不返工、不将 contextual judgment 冒充显式事实；明确边界改为 user-only 精确引文，建议负担单列 `minimal_presence/one_focus/multi_step_ok`。五类 mode formal fit 暂停；从原 75 个 train-only outcome-blind states 中预先确定另 24 条（16 expansion-fit、8 untouched confirmation，角色不在盲包展示），冻结 hierarchical posture 仅作诊断，扩展后必须重新 group-held-out 检查所有类 recall、log-loss、BAAI/lexical ablation，不能只看平均 accuracy | `FIRST_HUMAN_ANCHORS_BOUND_REAL_LEARNABILITY_INSUFFICIENT_FRESH_EXPANSION_PACKET_PREPARED` |
| V15-OBS-16 | C0 | 若看到 BGE-small 五类塌缩就直接换更大 encoder，可能把监督不足误诊成模型容量不足。本机缓存的 BGE-M3 在同一 23-group OOF 下，五类 current-view loss 仅 `1.6321→1.6272`，差值 bootstrap CI 跨 0，仍有三类 recall=0；只对较粗 dialogue phase 有改善。每折仅 18–19 个训练 group、最少类 2 条，正则化后有效维度通常为 2；而 listen/comfort、explore/guidance 本身可交叠，flat 五类把多轴响应需求压成互斥 gold | 暂停已准备的扩展标注；先把目标拆成推进许可、提问许可、建议许可、任务负担和阶段等可观察轴，五类改为派生解释。BGE-small/BGE-M3 只作候选表示；instruction-aware encoder 必须以同一 train-only probe、透明 lexical baseline、非多数 recall 与 downstream component-effect 增益资格验证。未标注 train 文本只可用于 outcome-blind 投影/覆盖，显式规则只产生高精度 partial positives，缺失不作 negative | `BGE_M3_ZERO_API_RECHECK_COMPLETE_EXPANSION_PAUSED_TARGET_DECOMPOSITION_REQUIRED` |

### 6.3 requested、retrieval、realized 与 alias

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-ACT-01 | C0 | EF 关闭时直接把 requested action 写成 effective，即使零命中 | `requested -> attempts -> realized -> prompt_equivalence` 四层合同 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ACT-02 | C1 | 把 zero-hit 一律视为非法会删除真实 retrieval failure | zero-hit 是合法后果；保留 call、latency、token、USD 和原因 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ACT-03 | C0 | 外部 evaluator 直到花完生成费用才发现 action/evidence 不一致 | generation 前重算 realized，验证 evidence/action/prompt lineage | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ACT-04 | C1 | 多个 requested actions 形成同 prompt，同一 label 被复制成多份独立证据 | shared `prompt_equivalence_id`、inverse alias weight、user/state 聚类 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ACT-05 | C1 | 物理 prompt 去重可能错误抹掉每个 requested action 的检索成本 | 质量/risk 绑定 realized prompt；attempt/cost 绑定 requested action | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ACT-06 | C1 | required-hit 若在看完 outcome 后筛样，会产生选择偏差 | 只作 response/judge 前的 positive challenge data-validity gate | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ACT-07 | C1 | 自然/external zero-hit 被 required-hit 规则删除 | natural/external 不重抽、不删除，分层报告 | 持续护栏 |
| V15-ACT-08 | C0 | PM 的 Strategy Step-0 根据全库 8 个 family centroid 判断 RS opportunity，但真实 `StrategyRetriever` 却在未经适用性过滤的 11,590 张卡上做全局 lexical top-3；因此 PM 预期的 family/readiness 与实际进入 prompt 的 raw card 可以完全错位。generic Hybrid 已在合法 calibration/ESConv validation 上无优势，不能自动补救该语义断层 | 建立受审 Strategy Bank V2 和 family/goal/phase/burden eligibility metadata。pre-retrieval 只暴露与正式 eligible pool 同源的 family-level opportunity；选择 RS 后才在 compatible subset 中 lexical candidate→确定性过滤→经 train-only 资格的可选 reranker。无合格卡合法 realized 为 R0 alias。新 clean uptake 过门前不得把 RS requested 当 RS realized/beneficial。首批 Need packet 的 75 个 dialogue 与 raw Bank 75/75 重合、涉及 1,094 cards；V2 candidate 已排除到 0 overlap，并把剩余 748 sources 聚成 5 张 technique-only cards。当前只待五卡人评/LLM弱审计，不得提前 promotion | `BANK_V2_ZERO_OVERLAP_CANDIDATE_BUILT_AUDIT_PENDING` |

### 6.4 数据血缘、seed、Strategy Bank 与语义有效性

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-DATA-01 | C0 | EvoEmo/ES-MemEval 和 Strategy Bank 都有 ESConv 血缘；exact 清理不能证明语义独立 | source-ID、exact/Jaccard/semantic lineage 审计；外部称 ESConv-derived transfer | `PERMANENT_LIMITATION` + 部分代码护栏 |
| V15-DATA-02 | C0 | 正式 52 seed 一度直接来自与 Bank 相同的 875 source universe | 先冻结 52 source IDs，再从 Bank 删除这些完整对话实例 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-DATA-03 | C2 | “875 条 RAG bank seed”表述混淆了 seed pool 与 Bank | 875 是私有 clean seed 候选；52 被选作 development；这些 52 不在 Bank；Bank 是 11,590 cards/823 sources | 已澄清，持续防混淆 |
| V15-DATA-04 | C1 | 同一策略知识/心理支持经验的语义重合被误当成必须全部删除 | 允许领域和 family-level 经验重合；禁止同一 dialogue 实例、未来信息和测试 target 泄漏 | 设计边界 |
| V15-DATA-05 | C0 | 27 个预制审查 case 不能证明实际 468 states 语义成立 | actual-468 structured QA：4 个代码事实 + context/readiness 两个原子双家族 packet；分歧保留，双否定才拒绝；构造标签不冒充独立 gold | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-DATA-06 | C0 | deterministic fallback 模板包含 regime 线索，可成为答案键 | reportable corpus 最终 fallback 必须为 0；失败保留并停机 | post-repair 合同，`RUN_UNVERIFIED` |
| V15-DATA-07 | C1 | fallback 率一度只有日志没有 split-specific 硬门 | train/calibration/internal 分开；internal=0；当前生成合同进一步要求全量 0 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-DATA-08 | C1 | source age、row order、inventory、family/template 可能直接编码 regime | counterbalance、随机化和 actual shortcut probes | `PENDING_RUN_EVIDENCE` |
| V15-DATA-09 | C1 | EvoEmo chronology 曾依赖 JSON 原顺序，未验证 ID/date/reference | ISO date 稳定排序、ID/topic/reference fail-closed；不虚构 topic timestamp | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-DATA-10 | C1 | exact overlap 清零仍不等于没有母对话语义改写 | top-match/lineage 继续报告；不能称 pristine independent external | `PERMANENT_LIMITATION` |
| V15-DATA-11 | C0 | `strategy_helpful`/`strategy_harmful` 一度同时编码 RS value 与 advice readiness，模型可凭“要建议/只倾听”直接猜 RS | evaluator-only `strategy_resource_target` 与五级 `advice_readiness_target` 分开；两类 Strategy slots 在 user 内交叉配对 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-DATA-12 | C1 | 本地预设 Strategy target 可能被误当真实 outcome，形成自我实现标签 | target 仅作 pre-outcome challenge/语义审计；训练、`rs_correct` 和主结论以同 memory subset 的 blinded R0/RS utility 为准 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-DATA-13 | C0 | CLI 虽默认指向 V1.5 Bank，但可被替换成另一套 Bank 后仍形成一条内部自洽却偏离冻结方法的链 | 配置冻结 exact path/SHA/card count/source count/audit/52-seed manifest；首个付费 development 阶段在 API client 前强校验，后续由 attestation/freeze 传播 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-DATA-14 | C0 | evaluator-only `advice_readiness_target` 虽已与 Strategy value 反平衡，但真实 V8.4 的两个 Strategy surface 都没有把各自的 `light_suggestion/listen_only` 状态写进可见用户话语，PM 因而无从识别 | readiness 由本地 compiler 以每类 6 种自然句式确定性写入 current turn；52-user 内 Strategy-use/skip 双向反平衡；句式协议/hash 写入 provenance；专用环境 frozen BGE 对 12/12 句式 top-1 正确，且该门不读 outcome/Strategy target | `CODE_CLOSED_REAL_BGE_12_OF_12_FRESH_PILOT_REQUIRED` |
| V15-DATA-15 | C0 | development state 旧合同只有 2/4-turn history 且 summary 永远存在；EvoEmo summary 永远空、history 可到 8，ESConv 也含更长历史。HGB 同时吃 lexical hash、BAAI、Step-0 与标量，内部/外部输入支持不一致可让 PM 在外部退化为 OOD fallback/fixed | provider 按 outcome-free user/case cell 精确生成 2/4/6/8 turns；compiler 将 summary present/absent 在每 split/regime/history stratum 反平衡；current turn 自身必须有 family anchor；data report、training report、EvoEmo preflight 与 ESConv adapter 共同执行 structural-support gate，只要求落入支持、不仿写 EvoEmo 文本 | `CODE_CLOSED_TARGETED_TEST_PASS_FRESH_V8_10_REQUIRED` |
| V15-DATA-16 | C0 | 旧 ESConv 实验使用 V1 `PMModel/LearnedPMPolicy`，不能证明与 V1.5 EvoEmo 主实验是同一个 PM；旧 turn adapter 还把最后 seeker 话语同时放进 current 与 history | 新 V1.5 adapter 只加载同一 `PMV2Model`/transparent-rule checkpoint、同一 BAAI/Step-0；current user 只出现一次；单会话 memory 全部结构性 unavailable，仅 `M0+R0/M0+RS` 合法；169 non-overlap test dialogues 的全部 support-eligible turns（2,112/2,275）按最近 2/4/6/8 window 进入，policy choice 不读 gold | `CODE_CLOSED_SPLIT_AUDIT_PASS_FREEZE_WIRING_TEST_PASS_FORMAL_RUN_UNVERIFIED` |
| V15-DATA-17 | C0 | 旧 sweep 中目标为 MP/MS/ME 的 positive source action 并不是 clean causal treatment：单源行逐例选入 1 helpful + 1 irrelevant，多源行逐例选入 3 helpful + 3 irrelevant；真实 decomposition pilot 又显示 3/3 multi-source state 有 interference。由此得到的 action score 不能识别“该 source 本身有益”，16-way argmax 还会放大噪声 | 新 V2 合同将 M0 control、单 helpful、单 irrelevant placebo、单 harmful 四种 treatment 分离；同 state/prompt/generator/seed，positive 禁止混入 nonhelpful；多源只有在每个单源 uptake 已过门且 interaction contrast 可辨后才进入，否则向非正 interaction shrink/abstain。旧 outcomes 只作 noisy diagnostics/cost lineage | `ROOT_CAUSE_CONFIRMED_V2_CLEAN_CONTRAST_CONTRACT_FROZEN_NEW_DATA_PENDING` |
| V15-DATA-19 | C0 | 既有 merged OOD 诊断调用了 production feature builder，却没有注入真实 Strategy Bank family catalog，且 formal V3 只按 scenario 计数而漏掉 3 个 robustness seeds×2 turns；旧结果因此混入伪 strategy drift 与覆盖率低估 | 诊断现镜像 production adapter：同一 Strategy Bank/catalog/count/token、memory centroids 与 34 scenarios×3 seeds×turn 3/8 的 204-state exact coverage；使用正式 `.venv-pm-v1-5` 运行，外部 outcome 未读取 | `CODE_CLOSED_TARGETED_TEST_PASS_ZERO_API_RERUN_COMPLETE` |
| V15-DATA-20 | C0 | 修正后的当前输入支持结果显示：合并 synthetic+ESConv auxiliary 后 ESConv test severe OOD 为 58/2112=2.75%，但 EvoEmo formal V3 为 204/204 severe metadata OOD；主要来自 MP/MS/ME age、age span、ME count/expected tokens 与少量 query similarity，不是 Strategy Bank 漂移。直接训练旧数据会让 PM 在纵向外部场景系统性 fallback | 在任何新 fit 前，用 outcome-free operational envelope 构造 count/age/span/token/similarity 分箱的 synthetic metadata augmentation；禁止复制 EvoEmo raw text/topic/related-session/outcome；ESConv 与 EvoEmo 分别要求 severe OOD<=10%。使用 observable external ranges 必须披露为 development-informed，不能称 pristine 或 official ES-MemEval reproduction | `ROOT_CAUSE_CONFIRMED_V2_EXTERNAL_SHAPE_CONTRACT_FROZEN_AUGMENTATION_PENDING` |
| V15-DATA-21 | C0 | 把“ESConv 与 EvoEmo 分开评测”误写成“PM 学两套分开的能力”，会诱导出 domain-specific router、domain ID shortcut 或两个 checkpoint，背离研究对象。真实能力是同一 PM 联合决定 memory subset 与 R0/RS：ESConv 只是 memory availability 全 false 的 legal-action 边界，EvoEmo 是 memory 可用的多会话输入区域 | V2 合同冻结 one checkpoint/shared feature builder/shared component heads；domain ID 禁止进入 PM 特征，domain weighting 只作统计平衡；RS 必须跨 memory-unavailable/available backgrounds 学习，并显式审计 source×RS interaction。外部指标与 bootstrap 仍分开，避免把不同 estimand 混成一个分数 | `DESIGN_CLARIFIED_UNIFIED_ROUTER_CONTRACT_HASH_BOUND` |
| V15-DATA-22 | C0 | 冻结 Strategy Bank 是 823 个 ESConv 对话的 11,590 个原 supporter 回合，不是已审策略知识库：`guidance_text` 只有 8 个 family 通用模板，`example_response` 有 1,089 行落在 normalized duplicate groups，最大 `hello` 组 78；还混有问候/结束/问卷元话语、case-specific self-disclosure 和未验证的医疗/财务/法律/生活建议。按当前 raw top-3 生成 RS 数据会把 card 噪声误当策略价值 | raw bank 只保留 provenance/baseline；V2 candidate 已将 raw example 从 generator surface 删除，隔离 Information/Others/Self-disclosure/domain-specific information，只保留五张可逐项审查的 technique card；234 个 duplicate groups/1,089 rows、问候/结束/meta/domain claim 和 75-source 排除均可复算。候选仍 fail-closed 为不可正式使用，需规则+LLM弱审计+五卡人评；clean matched RS/mismatch uptake 未过门前不扩量 | `BANK_V2_TECHNIQUE_CANDIDATE_BUILT_HUMAN_AND_LLM_AUDIT_PENDING` |
| V15-DATA-23 | C0 | 正式 V1.5 Bank 的 11,590 张卡可 100% 回连 expanded ESConv 的 problem/emotion/experience/situation/strategy/survey 原生字段，但当前 schema 全部丢弃；另一份 156-card V13 虽含类似 metadata，其声明的 pm_train/v12 上游和 builder 已不在工作区，无法重建。若直接复用 V13 会把项目派生 `support_state` 冒充官方 annotation；若完全不用原生字段，又会丢掉 topic/affect/experience coverage 与适用性信号。实际 problem×emotion×strategy 有 532 个非空 cell，其中 208 个少于 5 张，不能硬编码组合规则；survey 还是缺失的 post-treatment conversation-level 结果 | Strategy Bank V2 保留 raw+normalized official metadata、字段角色与 source provenance；problem/emotion/experience 只作分层、soft applicability 和偏差审计，运行时只能从 visible text 输出不确定分布；strategy 只表示曾用 move，不表示最优；survey 只作 source-quality prior/敏感性报告，永不进在线 PM 或 turn-level action gold。V13 只作 schema 参考，除非补齐上游并可独立重建 | `ROOT_CAUSE_CONFIRMED_NATIVE_METADATA_ROLE_REGISTRY_AND_CLEAN_BANK_PENDING` |
| V15-DATA-24 | C0 | outcome-blind ESConv train 审计显示：排除 EvoEmo 重叠后虽有 11,914 个带 prior seeker 的 observed-strategy decisions，但明确 listen-first/just-talk cue 仅 3 个；advice-request 280 个且只有 30.4% 后续 move 是 Providing Suggestions。`problem/emotion/experience` 对 observed strategy 的 normalized MI 仅 `.00273/.00248/.00018`，不能支撑“按 topic/emotion 就知道用户要什么” | observed strategy 只作低权重 move prior；topic/emotion/experience 只作分层。五类 support need 由新鲜 train 人评 partial labels、显式边界和 matched counterfactual 补足；BAAI/lexical/metadata 必须做 dialogue-group out-of-fold probe，无可辨识性就停止而不是扩量 | `ZERO_API_PROFILE_COMPLETE_NEED_HUMAN_AND_GROUPED_PROBE_PENDING` |
| V15-DATA-25 | C0 | ESConv seeker feedback 只覆盖 5,130/11,914 合法 decision，各策略均值挤在 4.14–4.41；conversation survey 还存在缺失与高分天花板。把这些 post-treatment 分数当 turn-level utility，会制造高置信伪标签且无法辨识 RS/memory 增量 | feedback/survey 只作 report-only source-quality prior、置信度和敏感性分析；动作效应必须来自同 state/prompt/seed 的 clean matched response pair，由拆职裁判/少量人评判断，不用 survey 补 gold | `ROOT_CAUSE_CONFIRMED_POST_TREATMENT_SIGNAL_ROLE_FROZEN` |
| V15-DATA-26 | C0 | 875 个 eligible ESConv train dialogues 中有 489 个 supporter turns 发生在任何 seeker turn 之前；全量 surface 另有 267 个 normalized duplicate groups/1,205 rows、186 个 greeting/closing-only、657 个 ≤3-word turns。若这些 opening/meta/noisy rows 进入 Strategy Bank evidence 或 support-need 模型，会把“开场习惯”误学成响应用户需求的策略 | PM need/strategy decision 样本必须存在 prior seeker turn；Bank V2 source 过滤显式加入该条件，并继续 greeting/meta/duplicate/domain-risk 审计。原始 turn 仅保留 provenance，不作为 clean technique 或 response-quality gold | `ZERO_API_PROFILE_COMPLETE_BANK_V2_FILTER_UPDATE_PENDING` |

### 6.5 generator contract 与真实 pilot 失败

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-GEN-01 | C1 | 旧 provider 一次生成 9 cases，还同时生成 memory/evidence/oracle/rationale/IDs | provider 只看一个 case 的四个 surface 字段；证据和 evaluator rationale 本地确定性编译 | post-repair 合同，`RUN_UNVERIFIED` |
| V15-GEN-02 | C1 | whole-bundle 让一个 case 的 topic/semantic family 污染另一个 case | one case per physical call；每 case 独立 seed | post-repair 合同，`RUN_UNVERIFIED` |
| V15-GEN-03 | C2 | V8 的 `coverage_rationale<=180` 拒绝 181+ 字符真实输出 | 删除与 provider 任务无关的 rationale 字段；本地生成 | `HISTORICAL_CLOSED` |
| V15-GEN-04 | C1 | relocation/academic/workplace pilot cohort 本身自然混题 | pilot family 必须实际正交，不为测试方便制造不自然 benchmark | V8.1 改用 relocation/self-confidence/sleep |
| V15-GEN-05 | C1 | V8.1 真实输出 2/9 需要 fallback：一例 family 泄漏，一例缺少 anchor | 不放宽 9/9 门；改成逐 case + 一次受限 repair | 旧 V8.3 dry-run 已失效；post-repair pilot 待真实验证 |
| V15-GEN-06 | C1 | 无限制 retry 会把“多试几次直到好”变成选择性生成 | 每 case 初次 + 最多一次预预算 repair；attempt ledger 先写后调用 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-GEN-07 | C1 | 只修 compatibility pilot 而未同步 formal 52-user，会重建 pilot/formal mismatch | 同一 generation contract 被 base 和 V1.5 formal runner 共同使用 | 当前已同步，`RUN_UNVERIFIED` |
| V15-GEN-08 | C2 | casewise 架构把 formal 成功路径从 52 calls 提高到 468、content-attempt 上限 936；正式 transport resilience 又把 physical 硬上限提高到 2,808 | 成本、token、timeout、approval 全部重新 dry-run；不能复用旧 52-call、936-physical 或 pre-transport hash | identity `85d1…` 曾两目录复现并获批，后在 9 次成功调用后的本地 compiler 边界失败，已永久消费；`2ec4…`/`7180…` stale |
| V15-GEN-09 | C1 | V8.2 用英文关键词正则把 “tips/help me figure out” 等有效建议请求判失败 | provider lint 仅保留 topic/role/chronology 结构门；意图交给连续语义表示和 actual semantic review，不再作为硬词表 | `HISTORICAL_CLOSED` + 新合同待跑 |
| V15-GEN-10 | C0 | V8.4 的结构 PASS 只证明 9 个 surface 可解析；旧 102-call 自动审核审的是另一批 27 个预制案例，没有绑定这次付费九例，却可被 formal generation 当作语义放行证据 | 自动审核 v3 同时读取 27 个确定性案例、exact paid 9-case attestation 与 24 个 hard controls；两家共 120 logical calls；report/attestation/formal generation/sweep/judging 都强制绑定同一 paid pilot SHA/contract | `CODE_CLOSED_FRESH_PILOT_AND_REVIEW_REQUIRED` |
| V15-GEN-11 | C1 | V8.4 暴露 memory-harmful current turn 缺句号形成 run-on，ME “one manageable next step” 过泛并与 MS 边际贡献接近 | compiler 使用统一句子连接器；MS 明确跨 session 模式，ME 明确一次过去事件及具体记录动作；evidence blueprint hash 随之变化 | `CODE_CLOSED_FRESH_PILOT_REQUIRED` |
| V15-GEN-12 | C1 | V8.5 的 provider schema 允许任意 role list，但返回后 lint 才要求交替并以 assistant 结尾；context_only initial+repair 都生成 `assistant,user,assistant,user`，真实消费 2 calls / `$0.0006274` 后 fail-closed | V8.6 provider 只返回 1–2 个 `{user_text, assistant_text}` exchange；本地 compiler 展开为 `user,assistant[,user,assistant]`，使交替与末尾 assistant 成为结构不变量；真实 V8.6 为 9/9 accepted、0 fallback，12 attempts 中没有该错误 | `CLOSED_V8_6_PAID_PASS` |
| V15-GEN-13 | C0 | V4 已永久失败、V4.2 只作 calibration，但 formal 52-user、7,488 sweep 和 judging 三个入口仍要求 `require_automated_semantic_review_pass(V4)`；即使方法合同修好也会在每一阶段重新卡死，或诱使人伪造旧 PASS | formal generation 只绑定当前 shared-code 下真实 PASS 的 generation pilot；显式拒绝传入旧 V4。actual-468 structured QA 必须在真实 corpus 生成后运行，并以 `full-sweep-gate-v3` 传播到 sweep、judging、freeze；三处生产入口和 freeze verifier 同步移除旧 V4 hash | `CODE_CLOSED_TARGETED_TEST_PASS_FRESH_DRY_RUN_REQUIRED` |
| V15-GEN-14 | C0 | V8.8.1 虽真实 9/9 PASS，但它验证的是 1–2 exchanges/summary-always-present 的旧 provider-visible 合同；若继续拿它批准新 2/4/6/8 + summary missingness formal generation，会再次形成 pilot/formal 两套东西 | generation version 先升为 V8.9 更新 prompt/schema/config projection；V8.9 随后因单次 500 暴露 transport cap 缺口，执行合同升为 V8.10 并将 runner/retry/release 加入 shared-code hash；V8.8.1 仅保留历史成功，未获批的 52-user `d4e8…` 移入 stale-unapproved 且零费用 | `CODE_CLOSED_OLD_IDENTITIES_STALE_FRESH_V8_10_REQUIRED` |
| V15-GEN-15 | C1 | V8.10 把 9 个 `current_user_text` 全局唯一当作内容有效性的硬条件；真实 `profile_needed` 与 `multi_source_needed` 在同一用户、同一 `self_confidence` 家族复用了完全相同的自然表达，initial/repair 均被拒绝。这个门不仅反复消耗 repair，还会诱导生成器加入可被 HGB 词法特征学习的人造 case 标记 | V8.11.1 改为受控反事实合同：仅同一 user/family/split 允许最多两对完全相同的 current turn、每组最多两个；每 9-case bundle 至少 7 个独立表达；跨 user/family/split、三次重复及人工 nonce/case marker 仍硬拒绝。两对上限在逐 case lint 即执行；真实 V8.11.1 以 8/9 unique、一个合法 `profile_needed`/`multi_source_needed` 同家族对、0 fallback 通过 | `CODE_CLOSED_REAL_V8_11_1_CONSUMED_PASS` |
| V15-GEN-16 | C1 | 第一条 formal 用户的 9 次 provider surface 调用全部成功后，本地 `health_routine_stress × MS semantic_decoy` 固定模板长 162 字符，超过 `GeneratedSummaryMemoryDraft` 的 160 字符上限而中止；运行报告最初误归因为 seed 文本 | 保留 160 上限，不截断 provider 内容；缩短 compiler-owned decoy，同时在任何 pilot/formal 身份创建前穷举 24 families × 3 sources × helpful/decoy/harmful 共 216 个固定实例并用真实 Pydantic schema 校验。最大值现为 155、余量 5；V8.12 已真实 9/9 PASS，并用失败目录的不可变 9-call ledger 恢复 user 1 全部 9 cases | `CLOSED_V8_12_PAID_PASS_FORMAL_RESUME_DRY_RUN_REPRODUCED` |

### 6.6 holdout、judge、训练与统计门

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-HOLD-01 | C0 | train/calibration/internal 在同一进程读取，internal 可被多次尝试 | pre-training label seal、candidate manifest、append-only one-shot ledger | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-HOLD-02 | C0 | candidate manifest 一度未预绑定 sealed internal label hash | seal 绑定 label/content/state universe/schema hash，消费时三方复核 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-JUDGE-01 | C0 | 为修 NVIDIA/Qwen 问题，开发 panel 一度换入 final GPT-4o | development 与 final 四层隔离；旧产物失效 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-JUDGE-02 | C0 | 只比较 endpoint 名会漏 alias 指向同 model/route | 比 alias、family、model、normalized base_url+model | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-JUDGE-03 | C0 | semantic runner 一度允许 CLI 换成任意两个 development endpoints | exact alias 顺序锁定配置，descriptor 和 experiment SHA 进入 attestation | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-JUDGE-04 | C0 | downstream verifier 一度不绑定当前 experiment config | 当前配置重建 endpoint descriptors 并逐项比对 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-SEM-01 | C1 | actual controls 最初只破坏 family/regime，且 `--n-controls 0` 可绕过 | 12 fields × 2 controls，数量/seed/matrix hash 冻结 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-SEM-02 | C1 | `deliberately_unrelated_control` 太明显，只测 sentinel 识别 | 使用真实 donor、标签翻转、age 矛盾、时序/grounding/strategy corruption | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-SEM-03 | C1 | order pilot 一度只检 schema，`gating_threshold=None` | 3 units × 2 schemas × 2 orders × 2 families，mean/max 数值门 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-SEM-04 | C1 | 5 条 readiness canary 太小，且 runtime 文件顶层 `PASS` 容易被误读成 readiness 全通过 | 扩为 20 条 outcome-free paraphrase challenge；runtime 与 `REPORT_ONLY_x_OF_20` 分开报告，不允许据此调 anchor | `CODE_CLOSED_LOCAL_REPORT_ONLY_14_OF_20` |
| V15-SEM-05 | C0 | V4 将 candidate regime/source/utility/readiness 与派生 rationale 混入同一 evidence packet，一次要求 12 个二元判断且只强制解释 0；controls 又部分与 question 不对齐，并混用 deterministic 与 actual 两套 renderer。真实结果为 targeted corruption 0/24、DeepSeek 720/720 全肯定、Gemini 27 个 real-case 0 与 12 个 control 非目标 0 | V4 永久 `CONSUMED_FAILED_CLOSED`；现有 24 controls/36 cases 只作 calibration。balanced v3 将 temporal/age 移为代码真值并做正反原子语义判断，但真实运行暴露 citation pointer 合同问题后永久 consumed；citation-safe v4.0 又因 provider outage 只完成 1/16 endpoint calls。resilient v4.1 保持同一 packet/窄主张，只修运行可靠性并生成 fresh identity | `ROOT_CAUSE_CONFIRMED_V3_V4_0_CONSUMED_V4_1_REPRODUCIBLE_DRY_RUN_PASS_UNAUTHORIZED` |
| V15-SEM-06 | C0 | 旧单字段 packet 的 `context_grounding` provenance 携带复述答案的 `claim`，关系判断又只能引用一个 evidence key；P1/P2 全是 negative，judge 一律反驳也可能“通过” | provenance 删除 claim；输出为对齐的 `evidence_keys[] + evidence_quotes[]`，context 至少引用两个不同 section；4 个语义字段正反成对，expected/polarity/control metadata 不进 messages；代码可判字段不调用 LLM | `CODE_CLOSED_FULL_TEST_BALANCED_MOCK_AND_REPRODUCIBLE_DRY_RUN_PASS` |
| V15-SEM-07 | C0 | 两家 judge 即使一致地判断错误，旧 `label_reliable` 仍会因 MAD=0 获得最高权重；agreement 被误当 validity | control 先验证 instrument validity，再讨论 disagreement；一律 supported/contradicted 均不能通过 balanced pairs。正式 action utility 仍来自 16-action outcome comparison，不能把 source/regime candidate label 当真实用户意图金标签 | `MEASUREMENT_BOUNDARY_FROZEN_FORMAL_INSTRUMENT_STILL_PENDING` |
| V15-SEM-08 | C1 | balanced v3 第 2 次真实调用中，DeepSeek verdict 与逐字 quote 均正确，却把 memory text 挂到 `memory_id`；旧汇报误称为 paraphrase，并因 diagnostic postcondition fail-fast 丢失后 14 个诊断 observations | 账本复核纠正事实；`memory_id` 等 record-linkage metadata 移出 citable namespace。v4 分别报告 verdict accuracy、citation integrity、joint accuracy；parsed citation defect 不重试但作为完成 observation 记录并继续矩阵，formal gate 行为不放松 | `RECONCILED_CODE_CLOSED_FULL_MOCK_MATRIX_PASS_V4_DRY_RUN_READY` |
| V15-SEM-09 | C0 | v4.1 把可由 frozen metadata/marker lint 判定的 source type 与显式生成泄漏交给 LLM，又把 `contradicted`/`insufficient` 的哲学边界和 citation pointer 合并进语义正确性；真实 16/16 调用完成但 verdict=.75、citation=.875、joint=.6875，不能据此断言 PM 或 judge 家族整体失败 | v4.1 identity `22265947…936d` 永久 consumed；v4.2 由代码判断 source/temporal/age/显式 leakage，只让双家族二元判断 context grounding 与 advice readiness；citation 独立报告。V4.2 已 8/8 完成（verdict=.875、citation=.875），暴露 Gemini citation-section 和 DeepSeek readiness 操作定义各一处薄弱点，不重跑、不改写历史结果 | `V4_2_CONSUMED_INSTRUMENT_NOT_READY_USED_AS_CALIBRATION` |
| V15-SEM-10 | C0 | 旧正式 actual-468 仍沿用 V4 的“单 packet 12 字段、任一家一个 0 即淘汰、两家都必须抓住每个负控”逻辑；这会把已知 judge 噪声当金标签，并可能选择性删掉有效 states | structured QA v3：source/temporal/age/显式 leakage 由代码硬验；context grounding 与 advice readiness 各自原子调用，readiness 冻结操作定义；真实 state 双家族一致否定才阻断，一致支持通过，分歧保留披露；负控一致漏检才阻断；citation report-only；其余构造标签只做 hash/schema lineage，实际资源价值由 blinded 16-action sweep 决定 | `CODE_CLOSED_TARGETED_TEST_PASS_FULL_RUN_UNVERIFIED` |
| V15-TRAIN-01 | C1 | 当前绝对 HGB 容易浪费容量预测 state 难度，而非 action 边际值 | train-only 比较 absolute、state-centered delta、rule-relative residual、rank 候选 | `PENDING_RUN_EVIDENCE` |
| V15-TRAIN-02 | C1 | 直接换大模型/RL 与 24 train users、完整 action matrix 不匹配 | 小样本可审计监督学习；RL 留给有 transition/user feedback 的后续研究 | 设计边界 |
| V15-TRAIN-03 | C1 | 缺少同观测强 rule 会把弱规则做 strawman | transparent rule 使用相同 Step-0，并作为 Gate M 主比较 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-TRAIN-04 | C1 | calibration 一度同时调 rule、algorithm、OOD、selector、fixed frontier | model family/rule 移到 train-group CV；calibration 只做冻结校准 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-TRAIN-05 | C1 | 仅选最高 CV mean 容易 winner's curse | one-standard-error rule，近最优中选更简单稳定模型 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-TRAIN-06 | C1 | 16 actions×states 不是独立样本，真正有效规模接近 user blocks | user-disjoint fold/bootstrap；报告 prompt-effective N 和 action stability | 持续统计护栏 |
| V15-TRAIN-07 | C1 | 仅增加冻结 embedding 仍可能因高维、小样本、环境 identity 过拟合 | 两个 384 维视图只在 train users 上 PCA 到 48 维；encoder binding 必须一致；group-CV/one-SE 决定是否保留复杂模型 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-TRAIN-08 | C1 | 原 no-Step0 消融仍保留 state BGE，无法区分“语言表示收益”和“Step-0 收益” | internal 一次性消费前同时冻结 full、无 Step-0、无 state-BGE、word/char-only 四格诊断；结果只解释组件贡献，不得选择或重调主 candidate，也不进入 external 主矩阵 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-TRAIN-09 | C1 | rule candidates 只比较聚合 action count，可能把在不同 states 上决策的两套 policy 错判为等价；诊断又到 internal 开封后才出现 | 新增 outcome-free pre-sweep grid preflight，记录每个 candidate 的 `action_by_state_sha256`、unique mapping 与 pairwise disagreement；sweep、training、candidate manifest 内容寻址绑定 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-TRAIN-10 | C1 | development 与 external Step-0 分布虽各自记录，却只能人工比对，且存在外部看分布后调阈值的风险 | external dry-run 读取冻结 training report，生成 calibration-vs-external quantile shift artifact；缺失来源显式标 `UNAVAILABLE`；只报告且禁止 selection/retuning | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-TRAIN-11 | C1 | residual 主算法的 no-Step0 版本会把 reference policy 从 transparent rule 改成 `M0+R0`，却可能被误写成纯 feature ablation | candidate manifest、calibration 和 internal report 显式标记 `component_removal_system_variant` 与 reference-policy change；只有非 residual 候选可称 retrained feature-set ablation | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-TRAIN-12 | C0 | 在完成 32 条旧-treatment 人评后直接重新 fit，仍会绕过 clean-treatment、mechanism uptake、新分布 measurement、train-group learnability 与 EvoEmo input-support 五个主阻塞；“所有旧 judging 都跑完”不等于训练数据可学 | 新增 `pm-v1.5-learnable-transfer-formal-fit-readiness-v1`：逐项绑定 V2 contract、根因报告、唯一问题账本、人评完成度、四份 train-only evidence 和两域 OOD；缺一即 `BLOCKED_BEFORE_FORMAL_FIT`。它只阻止 formal fit，不阻止小规模 train-only pilot | `CODE_CLOSED_CURRENT_REAL_READINESS_BLOCKED` |
| V15-TRAIN-13 | C0 | “保证下一次一次学成功”若被当成科学承诺，会诱导根据 calibration/internal 反复调数据、门槛或模型直到成功，重新制造 winner's curse 与 holdout 污染 | 可保证的是 known-pitfall completeness：formal fit 前 clean treatment、uptake、measurement、group-held-out learnability、external support 必须全部 PASS；不能保证 calibration/internal/external 结果。formal fit 只允许一个预注册候选，calibration 一次，失败即 `NOT_SUPPORTED` | `GUARANTEE_BOUNDARY_AND_STOPPING_RULE_FROZEN` |
| V15-TRAIN-14 | C0 | 旧设计把 advice readiness、用户目标、对话阶段、痛苦强度、Bank 是否有匹配资源和“使用后是否改善回复”压成单一 strategy target 或 16-way action winner；这既会把“用户请求建议”误当 RS gold，也使模型无法区分“允许建议但 Bank 无合适卡”和“未显式请求但 reflection 有益” | V3 将监督分为三层：support-need partial labels、resource opportunity labels、realized matched component effects；前两层只提供条件/特征，只有第三层决定开关。使用共享低容量多任务主干与 MP/MS/ME/RS effect/risk/uncertainty heads，domain 只加权不入模；危机 safety 独立绕过。train-held-out group CV 未胜 M0+R0/透明 rule 时不得进入 calibration | `V3_FACTORIZED_NEED_OPPORTUNITY_EFFECT_PLAN_FROZEN_IMPLEMENTATION_PENDING` |
| V15-TRAIN-15 | C0 | 小样本下把同一 state 的 16 actions、两家 judge、AB/BA、paraphrase 与 alias 当成新增样本，再用 512+ hash/PCA/Step-0 特征、HGB 和大量 interaction 拟合，会严重高估有效样本量；若又把冲突弱监督先压成伪 gold，模型最容易学到固定动作或噪声相关，过去 100% `M0+R0` collapse 正是这种“矩阵很大、独立 group 很少、标签不可辨”的结果之一 | 独立粒度固定为 `domain→dialogue/user→state→component contrast→prompt alias`，同时报告 raw rows、groups、physical responses、non-missing weighted observations 与 `ESS=(Σw)^2/Σw²`。弱监督保留 source distribution/abstain/provenance，以 family×role×stratum 可靠性和 Beta prior 收缩加权，冲突保持软标签/缺失；need 先做 60–100-state 零 API pilot，effect 再做 48–80-state clean single-component pilot。正式候选只用固定 BAAI 的 `{4,8,12}` 维投影与强正则线性/序数 heads，feature 维度不得超过 `floor(effective_groups/5)`；main effect 每方向至少 8 groups，interaction 至少 12 groups 且 main effects 已过门。未通过 out-of-fold anti-collapse viability 的组件保持 off，只允许受限 action mask。代码 canary 已过，首批 75 个独立 dialogue/24 人工 anchor 包已准备，尚未产生真实 partial labels | `CODE_CROSSFIT_GROUP_ESS_CANARY_PASS_FRESH_PACKET_PREPARED_ANNOTATION_PENDING` |

### 6.7 comparator、成本与 claim contract

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-COMP-01 | C0 | 外部只比 high-resource fixed，可能让固定低资源策略冒充 learned PM 的成功 | Gate M learned-vs-rule；Gate F cost-matched/ME+R0；Gate E high-resource efficiency | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-COMP-03 | C1 | 为保留“7 conditions”可能删掉关键 comparator | condition matrix 按 claim 组织，数量不是科学目标 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-COMP-04 | C0 | 若 ESConv 另训一个 Strategy-only PM，或看完 test 才选 “best fixed”，双外部实验无法支持同一 router 的主张 | 同一冻结 PM 仅施加环境动作 mask；主比较 learned、同观测 rule、always R0、always RS；质量分别对两个 fixed 作非劣，不按 test 结果挑弱 comparator；每 state 只有 R0/RS 两个唯一物理 outcome，policy alias 不复制成独立证据 | `CONTRACT_AND_FREEZE_WIRING_CLOSED_EXTERNAL_RUN_UNVERIFIED` |
| V15-COST-01 | C1 | 只统计 generator input tokens，却写“总体成本/延迟更低” | Step-0、retrieval、input/output、USD、latency 分开；主指标名称精确 | 持续 claim 边界 |
| V15-COST-02 | C1 | fixed policy 不需要 Step-0，却可能被人为收费以利于 PM | learned/rule 支付真实 Step-0；fixed 不支付未执行成本 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-COST-03 | C1 | retrieval zero-hit 仍有调用成本，若只按 realized action 会漏记 | attempt cost 绑定 requested action，prompt cost 绑定 realized evidence | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-COST-04 | C1 | 冻结 encoder 的本地推理、catalog refresh 和五类 readiness comparison 若不报告，会把“无 API token”写成“免费” | per-turn encoder input/token estimate、invocation、Step-0 latency、一次性 source/strategy catalog refresh 单列；fixed 不执行则为 0 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-CLAIM-01 | C0 | supervised single-step router 被写成 POMDP/RL/长期 distress 改善 | 固定方法名；禁止 RL、clinical、longitudinal causal claim | 持续论文护栏 |
| V15-CLAIM-02 | LIM | EvoEmo 是 ESConv-derived，且被 V1/设计过程反复检查 | 称 development-informed external transfer，不称 pristine external | `PERMANENT_LIMITATION` |
| V15-CLAIM-03 | LIM | 无人工专家/真人、final judge 为 LLM | 结果只代表冻结 rubric 下模型评估 | `PERMANENT_LIMITATION` |
| V15-CLAIM-04 | C0 | “监督式 router 的 proxy utility”容易在摘要中滑成“PM 识别真实用户需求/改善真实情绪” | 方法与所有报告固定写为 synthetic-state、LLM-judged quality-risk-cost proxy routing；禁止 user-welfare、clinical、latent-intent、real-world-optimality 表述。第一篇贡献是 PM 机制与严谨实验，不是现实识别或干预有效性 | `CLAIM_CONTRACT_FROZEN` |

### 6.8 CI、release、hash 与执行安全

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-ENG-01 | C2 | CI 裸 `pytest` 因 `scripts.v32_contract` import 失败；本地 `python -m pytest` 把 cwd 加入 path 而掩盖 | 将模块移入 `src/metacom_pm`；clean venv 按 CI 的裸 `pytest -q` 验证 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ENG-02 | C2 | workflow path filter 未覆盖全部 V1.5 文件 | 触发范围改为 `project/**` | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ENG-03 | C2 | legacy V9 硬编码 `/home` 和旧全局 study freeze hash 阻断新 preflight | 移除机器路径；旧 freeze 标 `STALE_HISTORICAL_FREEZE/confirmatory_only`，不原地刷新 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ENG-04 | C2 | static scan 曾漏掉顶层 `scripts/v1_5_*.py` | release/freeze scan 覆盖所有 active V1.5 scripts | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ENG-05 | C2 | 本地已缓存 BGE，使纯 freeze/external wiring 单测隐式解析真实 snapshot；GitHub clean offline cache 因而 10 项失败 | wiring fixture 只构造与精确 spec/tree 绑定的类型化假 binding；生产 freeze resolver 完全不改、仍 local-only fail-closed；全仓库测试另以空 `HF_HOME` + offline 环境执行 | `CODE_CLOSED_EMPTY_CACHE_AND_CI_PASS` |
| V15-ENG-06 | C2 | external wiring fixture 以 test name 作为共享目录名，多会话并发会互删并产生瞬时 `FileNotFoundError` | 在 release root 内使用每次唯一的 `TemporaryDirectory`；既保留 freeze 路径约束又消除跨进程碰撞 | `CODE_CLOSED_FULL_TEST_PASS` |
| V15-ENG-07 | C2 | 以外部 `tmp_path` 运行 release preflight 时仍重写真实 `release_manifest.json`，并错误收录 tracked `release_preflight.json` | preflight 支持独立 `manifest_out_path`；只排除 release root 内的真实生成目标；测试所有输出均写唯一临时目录 | `CODE_CLOSED_PREFLIGHT_PASS` |
| V15-ENG-08 | C1 | `sim_eval` 虽能跑 mock tests，但 Python 3.10、Transformers 5/HF Hub 0.23 组合不符合项目合同且真实 BGE import 失败；仅锁权重也不能约束 PCA/HGB 训练数值 | 专用 Python 3.13.2 `.venv-pm-v1-5` + `PYTHONNOUSERSITE=1`；Python/package/device/dtype/user-site 与公共 3×384 canary 写入 config；development、训练入口都现场重算，candidate/freeze/external 逐段绑定 | `CODE_CLOSED_LOCAL_CANARY_PASS_FORMAL_RUN_UNVERIFIED` |
| V15-ENG-09 | C1 | 512-token `truncation=True` 没有记录，可能让 external 的历史/摘要被静默截断 | 冻结 section-aware input v2：当前话语/summary 固定预算、history 保留最近 token suffix；模型端 implicit truncation 必须为 0，逐 section 只记录计数/hash；current turn 另有完整独立 view | `CODE_CLOSED_LOCAL_TEST_PASS_FORMAL_RUN_UNVERIFIED` |
| V15-ENG-10 | C2 | transparent rule 实际用 train/train-fold 调参，但 doc/report/YAML 声称 calibration；rule decision 还冒用 learned reason | 显式记录 `train_only/train_fold_only`，独立 `TRANSPARENT_RULE_SELECTION_REASON` 并按非 fallback 处理 | `CODE_CLOSED_FULL_TEST_PASS_FORMAL_RUN_UNVERIFIED` |
| V15-ENG-11 | C1 | wrapper 虽现场验证 BGE runtime，external artifact 自身却未写入该次 runtime 与 training-distribution lineage | learned/rule 的 manifest、preflight、cost、summary、attestation 全部写 live runtime；training report 作为 attested input，另输出内容寻址的分布比较 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-ENG-12 | C0 | Memory/Strategy Step-0 曾使用旧未预算 full text，而 state BGE 使用 section-aware bounded text；长 external context 下两类 PM 特征可能基于相反的历史片段 | 单一 `prepare_visible_semantic_state` 同时生成 bounded text/current+state vectors/audit；development、EvoEmo inventory、runtime adapter 和 readiness challenge 共用；文本与向量双 hash 必须相等 | `CODE_CLOSED_REAL_BGE_STATE_SMOKE_PASS_FORMAL_RUN_UNVERIFIED` |
| V15-ENG-13 | C0 | section-aware encoder 已输出 `section_allocation`，但 `PMV2State` 严格 schema 仍只允许旧 telemetry keys；真实 BGE `case_to_state` 会直接 ValidationError，普通 fake encoder 测试未覆盖 | schema 严格接纳并逐字段校验 allocation；长 development/external 测试、篡改反例及真实 BGE strict-state no-API smoke 全部执行 | `CODE_CLOSED_REAL_BGE_STATE_SMOKE_PASS_FORMAL_RUN_UNVERIFIED` |
| V15-ENG-14 | C1 | Gemini judge 曾被当作普通 OpenAI-compatible endpoint，向 `/openai/chat/completions` 发送 OpenAI `response_format/json_schema`；真实 HTTP 400 又因 list-shaped error body 无法提取原因，容易把 transport 不兼容误判为 rubric/schema 能力不足 | endpoint identity 显式冻结 `transport`；Google judge 改用官方 native `generateContent` 的 `responseMimeType=application/json + responseJsonSchema`，schema 与本地 Pydantic 合同不放宽；错误解析递归但有界地读取 dict/list 白名单字段，只存安全摘要和 body hash；Gemini 排在 fresh full matrix 首个调用 | `CODE_CLOSED_LOCAL_MOCK_PASS_NATIVE_PAID_RUN_UNVERIFIED` |
| V15-ENG-15 | C1 | 冻结 generation-pilot 预算的回归测试未显式传 seed corpus，因本机恰有被 gitignore 的 3.3 MB development seed 文件而本地通过，GitHub clean checkout 必然 `FileNotFoundError` | 测试在 `tmp_path` 生成 52-user cohort + 1 held-out 的最小确定性合成 seed fixture，并显式传 `--seed-dialogues`；不跳过测试、不提交本地 development corpus | `CODE_CLOSED_CLEAN_CHECKOUT_FIX_CI_PENDING` |
| V15-COST-05 | C1 | 统一语义输入后仍沿用旧 4 encoder invocation / `3×full+2×current` 估算会虚报机制并掩盖真实实现 | 当前实现按两次 `[current,bounded_state]` 批量编码记录 2 invocations，token 数直接取 tokenizer telemetry；无 semantic encoder 的 legacy/fixed 路径为 0 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-REL-01 | C0 | `PAID_RUN_BLOCKED` 一度只是文档说明，各入口可直接 `--run` | 中央 release gate；每 stage 绑定 config/revision/run/cost hash | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-REL-02 | C0 | 旧 pilot、partial attempts、旧 cost hash 或旧 PASS 可能被拼接复用 | immutable fresh output dir；旧 lineage 一律 stale；不覆盖、不拼接 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-REL-03 | C1 | API 失败被误解为额度问题，或未知 attempt 被盲重试 | HTTP 前 ledger fsync；unknown 视为已花费；仅 429 支持限流判断 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-REL-04 | C0 | paid release manifest 与 review artifact index 曾对 V8.2 approval 状态相互矛盾 | 按物理 ledger 记录为 `CONSUMED_FAILED_CLOSED`，删除 active approval；V8.3 必须 fresh identity | `HISTORICAL_CLOSED` |
| V15-REL-05 | C1 | 代码/config/bank/prompt 修改后沿用旧 accepted hash | 任一输入变化使 stage approval 失效，必须 fresh dry-run + explicit approval | 持续护栏 |
| V15-REL-06 | C2 | `API_PILOT_READY` 被误读成 `CONFIRMATORY_READY` | 报告两种状态；无 checkpoint/Gate M/F/freeze 时 confirmatory=false | 持续护栏 |
| V15-REL-07 | C1 | formal generation CLI 默认指向已失效 V8.3 attestation，容易让旧 provenance 被无意继承 | 删除默认值；paid `--run` 必须显式传 fresh pilot attestation，并拒绝 V8/V8.1/V8.2/V8.3 已知历史目录 | `CODE_CLOSED_RUN_UNVERIFIED` |
| V15-REL-08 | C0 | 在 `PAID_RUN_BLOCKED` 配置上生成 cost hash、再切换 release 状态会改变全配置 SHA，使刚批准的 identity 必然失效 | 两阶段 release：先冻结 `PAID_RUN_RELEASED`，但 manifest 保持 pending/空 approvals；证明 `--run` 仍 fail-closed；只批准随后在稳定配置上生成的 post-release identity | `HISTORICAL_CLOSED` |
| V15-REL-09 | C0 | 兼容 pilot 的 transport/schema PASS 可能被误写成完整语义 PASS 并直接授权 52-user | V8.4 原始账本、费用与 PASS 完整保留但语义性淘汰；V8.5 失败账本完整保留；V8.6 独立 identity 真实 PASS 并只授权进入绑定 exact attestation 的双家族语义审核，不直接授权 52-user | `V8_4_ARCHIVED_V8_5_FAILED_V8_6_PAID_PASS_REVIEW_PENDING` |
| V15-REL-10 | C0 | V8.6 成功后虽写入 `stage_consumptions`，manifest 仍保持 `APPROVED`、旧 stage identity 和 `paid_execution_authorized=true`；中央门又不读取 consumption，换输出目录可理论性复用同一 cost identity 再次付费 | 成功后清空 approval 并关闭 paid flag；中央门从 current consumptions 与 immutable history 汇总 consumed identities，旧 identity 永久硬拒绝 | `CODE_CLOSED_FULL_TEST_PASS` |
| V15-REL-11 | C1 | V8.6 人工回填的 approval/consumption 时间分别为 `02:30/02:35Z`，晚于不可变 API ledger 与 Git commit 约 48–53 分钟，不能作为可信执行时间 | approval 改取 `dd52ff1` commit time `01:41:43Z`；consumption 改取 ledger 最后一条 terminal event `01:42:23.305920Z`，并记录 approval/code/result 三个 commit SHA | `RECONCILED_TO_IMMUTABLE_EVIDENCE` |
| V15-REL-12 | C0 | “防止同一付费调用重跑”曾实现成“stage 名一旦消费就永久禁止”，导致 transport/code 修复后即使 fresh dry-run + fresh exact approval 也无法合法重跑同一科学阶段；反过来若把旧记录移出 current slot，又可能忘记阻止历史 identity | 消费门改为全历史 identity 唯一性：同一 identity 在任何 stage/current/history 中永久拒绝；同一 stage 只有在代码/配置变化、新目录、新 dry-run identity 和独立 exact approval 全部成立时才允许再次执行 | `CODE_CLOSED_TARGETED_TEST_PASS_FULL_RUN_PENDING` |
| V15-REL-13 | C1 | V3 自动语义审核记录的 `approved_at=02:50Z` 晚于 immutable terminal ledger `02:13:57Z`，形成“不可能时序” | approval 时间按 approval commit `94e7450` 校正为 `02:10:37Z`；consumption 保持 ledger 精确时间 `02:13:57.074194Z`；结果 commit `40ce6fe` 一并绑定，旧 identity 移入 immutable history | `RECONCILED_TO_IMMUTABLE_EVIDENCE` |
| V15-REL-14 | C1 | V8.6 generation attestation 绑定整份 experiment/PM config 与共享 API 文件；只修 downstream Gemini judge transport 也会令上游 9-case 内容失效，诱发无科学意义的重复付费；若直接忽略旧 input hash，又会破坏 provenance | 不给 V8.6 事后重新盖章；V8.7 fresh contract 改为精确 `generation_config_projection`（generator endpoint、data_generation、cost planning）并继续绑定 seed、prompt/schema、每个 request payload 与共享生成代码；judge-only 配置不再进入上游 identity，generator 任何变化仍 fail-closed | `V8_7_FRESH_DRY_RUN_PASS_PAID_RUN_PENDING` |
| V15-REL-15 | C0 | V8.7 的首个候选 identity `117d…` 依赖未写入正式入口的 CLI 预算参数（`0.018/4000`）；使用默认命令会得到 `aff6…`（`2.0/12000`）。科学合同与调用计划相同但预算身份不同，审批者无法仅凭标准命令复现唯一 cost hash | 将 V1.5 pilot 的 18 attempts / `$0.018` / 4000-token 上限冻结为 `pm_v1_5.yaml` 的独立 stage contract（不污染后续共用的 token-planning mapping）；runner 从配置读取并拒绝冲突 CLI；两次独立输出目录 dry-run 必须产生相同 hash。旧 `117d…`、`aff6…`、中间结构候选 `78c…` 均禁止批准，唯一候选 `920807ec…84e8` 已真实 `CONSUMED_PASS` | `CODE_CLOSED_REPRODUCIBLE_PAID_RUN_PASS` |
| V15-REL-16 | C0 | V8.7 结果记录新造 `stage_consumptions_history` 保存 V8.6，但中央门只读取 current consumptions 与 `prior_stage_attempts_history`；在 manifest 当前关闭时测试旧 identity 会因全局状态失败，不能证明未来重新开放后仍永久拒绝 | V8.6 记录迁回既有 `prior_stage_attempts_history`；门禁兼容读取并严格验证旧平行字段；新增回归测试在 manifest 重新 `APPROVED` 后确认历史 identity 仍命中 `already been consumed`，同时 fresh identity 可合法运行 | `CODE_CLOSED_FULL_SUITE_PASS` |
| V15-REL-17 | C1 | V8.7 manifest 的 prepared/approved 时间早于其引用的 code/approval commits，形成“批准尚不存在 SHA”的不可能时序；artifact index 与核心计划仍写未执行 | prepared time 对齐 code commit `70d035b` 的 `03:31:57Z`，approval time 对齐 commit `c6e439b` 的 `03:37:55Z`，terminal time 保持 ledger `03:38:25.294639Z`，并绑定 result commit `17fb0a9`；三份当前状态文档同步为 `CONSUMED_PASS` | `RECONCILED_TO_IMMUTABLE_EVIDENCE` |
| V15-REL-18 | C0 | 首版单字段诊断 dry-run 虽绑定 packet/config/V4 artifacts，却未绑定 runner、schema、transport、ledger 与 retry 实现；代码变化而 call plan 恰不变时旧 identity 可能仍可复用 | cost payload 加入 runner/contract/API/ledger/retry/release/judge/config/io/token-planning 逐文件 SHA；任何执行或 prompt 变化都生成 fresh identity。旧 identities `a4cbb1…`、`6829f591…`、`639b8c5b…`、`3153ae32…` 均已作废或消费，永久禁止复用 | `CLOSED_OLD_IDENTITIES_CONSUMED_OR_STALE` |
| V15-REL-19 | C1 | native Gemini total 还包含 thoughts/tool-use，旧 parser 丢分项并误判合法 `265+109+2=376`；失败 ledger 又未保存分项/hash | 零容差映射：input=`prompt+tool-use`，output=`candidates+thoughts`，cached 不重复相加；逐字段非负、cached≤prompt、两级守恒 fail-closed；成功/失败均保留五项 breakdown 与 response hash。v2 真运行没有再出现记账错误 | `CODE_CLOSED_REAL_V2_USAGE_ACCOUNTING_CONFIRMED` |
| V15-REL-20 | C1 | v2 第 15 个 logical call 的首次 Gemini HTTP-200 candidate text 不是 JSON，却被归为 `other/terminal_nonretryable`；原报告又错误写成“瞬时不稳定耗尽重试”，并只汇总成功 attempt，漏掉已付费失败调用 | 账本重算为 20 physical、14 success/6 fail、5949 input/1780 output/7729 total、约 `$0.0013069`；五个 transport failures 均已恢复，真正 stop 是首次 malformed JSON。retry v3 将 `missing_field/provider_output_format` 共享 2-attempt cap：只允许一次 ledger-visible repair，第二次失败永久终止；4xx、schema validation、postcondition 仍零重试 | `RECONCILED_AND_CODE_CLOSED_TARGETED_FULL_TEST_PASS` |
| V15-REL-21 | C1 | API client 在 structured-schema 模式第一次 `json.loads` 失败后，会在同一付费物理调用内静默截取首尾 `{...}`；v3 DeepSeek 的原始 `We{...}` 因而绕过 ledger-visible `provider_output_format` repair，与已冻结协议不一致 | v4.0 先改为 whole-surface fail-closed；v4.1 只重新允许两种显式、确定性且不改 JSON 值的 normalization（单一 Markdown fence、≤80 字符 wrapper 中的唯一 object）。原文/hash/repair kind/丢弃字符数全部入账；多 object、长 wrapper、真正 malformed 仍进入独立的 provider-output failure budget | `CODE_CLOSED_AUDITED_NORMALIZATION_TARGETED_AND_FULL_TEST_PASS` |
| V15-REL-22 | C0 | v4.0 把 provider-output repair cap 绑定到物理 attempt 序号，导致 `503→malformed→503` 在仅观察一次 malformed surface 时就误耗尽格式名额；每 call 仅 3 attempts 且首个耗尽会终止整个 16-call matrix。真实 v4.0 又被误记为 0/16 logical、空 HTTP body、连续第三次 provider failure，并出现 approval 晚于 terminal 的不可能时间 | retry v4 分离 transport 与 malformed-surface 计数：每 call 最多 10 physical、最多 2 malformed observations，冻结长退避并支持跨进程成功结果复用；诊断单项不可用时继续矩阵，缺失只报 `INCONCLUSIVE_PROVIDER_AVAILABILITY`。manifest 按 immutable ledger 校正为 1/16 endpoint、0/8 paired，HTTP envelope 存在，approval exact time 未记录而非伪造时间。mock 集成验证 10×503 后仍完成其余 15 calls | `RECONCILED_CODE_CLOSED_TARGETED_INTEGRATION_AND_FULL_TEST_PASS_V4_1_DRY_RUN_REPRODUCED_UNAUTHORIZED` |
| V15-REL-23 | C0 | V8.8.1 PASS 后的 formal 52-user dry-run `d4e8…` 虽未批准，但若 observable-state-support 修复后仍留在 pending slot，操作者可能误把旧 prompt/schema/cost identity 当作当前授权候选 | `stage_approvals` 保持空；旧 formal 完整记录移入 `stale_unapproved_dry_runs`，标明未消费/零费用与具体失效原因；`pending_unapproved_dry_runs` 只保留两目录复现的 fresh V8.9 pilot `e7b8…`，且 `paid_execution_authorized=false`；formal 必须等 pilot 真实 PASS 后另建 identity | `CODE_CLOSED_MANIFEST_JSON_VALID_V8_9_DRY_RUN_UNAPPROVED` |
| V15-REL-24 | C1 | V8.9 将 initial/repair 两个 content attempts 误当成全部 physical retry budget；runner 对 provider client 强制 `retries=1`，却未在外层接入 durable transport retry，单次 OpenAI HTTP 500 就在第 2 个 physical attempt 停止。若原样换 identity 重跑，只是在赌不再出现 5xx | V8.10 明确分层：每个 initial/唯一 content repair 各有 3 个 ledger-visible transport slots；只允许 5xx/429/408/network timeout 按 10s/30s 退避，4xx/本地 postcondition 终止，schema/provider-output/lint 进入唯一 content repair而不混用 transport slots；成本上限按 18×3=54 次真实调用计算；失败 usage 也逐 physical attempt 汇总；runner/retry/release 文件进入 shared-code hash。真实 V8.10 未遇 transport 故障，但因 GEN-15 的过严文本唯一门 fail-closed | `TRANSPORT_CODE_CLOSED_V8_10_CONTENT_FAIL_IDENTITY_CONSUMED` |
| V15-REL-25 | C1 | 若把 V8.10 的失败简单当随机波动换 identity 重跑，会继续赌同一个确定性表达不再出现，并把科学上合法的“同一句话、不同可见目录/历史”误判为坏数据；首版 V8.11 又只在 bundle 末尾执行 7/9 floor，第三对重复可能到 9 例花完钱才失败 | 数据合同/逐例 lint/bundle/split/full-design 四层统一受控反事实规则；V8.11.1 将两对上限前移到逐例 lint。真实执行 9/9、10 physical、1 repair、0 fallback，且实际出现并正确接受一个受控同文反事实对；V8.11 `48bc…` 从未批准/消费，已转 stale | `REAL_V8_11_1_CONSUMED_PASS` |
| V15-REL-26 | C1 | V8.11.1 真实 PASS 后，已消费 identity 仍留在 `pending_unapproved_dry_runs`，且人工填写的 `approved_at_utc=13:20` 晚于 immutable ledger 首次 STARTED `13:17:11` 和 terminal `13:17:32`；继续沿用会把“不可能时序”和已消费候选带入正式 lineage | pending 清空；exact approval time 不可从不可变证据恢复时写 `null`，并以 `approval_timestamp_status` 明示授权必然早于 ledger 首次 STARTED，不伪造时间。V8.11.1 保留 `CONSUMED_PASS`、9/9、10 physical、0 fallback、attestation/ledger exact hashes，identity 永久不可复用 | `RECONCILED_TO_IMMUTABLE_LEDGER_FORMAL_DRY_RUN_ALLOWED` |
| V15-REL-27 | C1 | 已通过 pilot artifact 的 scope 仍写“full generation 前需要 independent human semantic review”，与后续取消失效 V4 前置门、改为生成后 actual-468 structured QA v3 的权威生产流程冲突；直接改共享 pilot 代码又会使刚通过的 attestation 失效 | 不篡改、不重签已消费 artifact，也不为一句历史文案重跑付费 pilot；核心计划和 artifact index 明确该句为历史描述，权威门由 formal runner 冻结为 `DEFERRED_UNTIL_ACTUAL_468_EXISTS`，actual-468 必须在 sweep 前 PASS | `DOCUMENTATION_RECONCILED_ATTESTED_ARTIFACT_PRESERVED` |
| V15-REL-28 | C0 | formal 入口虽在真正 `--run` 前验证 pilot attestation，但旧 dry-run cost identity 只绑定 compatibility contract hash，未绑定获批的 exact artifact 文件；审批后理论上可把 CLI 换成另一份同合同 PASS artifact，违背“exact attestation”声明 | V1.5 formal dry-run 与 paid run 均强制显式提供项目内 attestation；先做完整 tamper-evident 验证，再把相对路径、raw file SHA、内部 attestation SHA、contract SHA 与 PASS 状态写入 generation binding 和 cost identity。跨项目路径、缺失、旧目录或非 PASS 均在身份创建前拒绝 | `CODE_CLOSED_FULL_SUITE_PASS_TWO_DRY_RUNS_REPRODUCED` |
| V15-REL-29 | C0 | V8.10/V8.11.1 pilot 已把 transport retries 与 content repair 分开，但 formal 468-call runner 仍给每个 content attempt 仅一个 physical slot；一次 500 会直接 abort 或错误消耗 initial/repair，复现 pilot/formal 两套执行机制 | formal runner 复用同一 bounded-retry-v4：每个 initial/repair 各 3 个 ledger-visible transport slots，10s/30s backoff，只有 5xx/429/408/timeout 重试；schema/provider-output/lint 只进入唯一 content repair，4xx/本地 postcondition 终止。预算冻结为 468 success / 936 content / 2,808 physical、`$3` ceiling，并在 report 输出 retry summary；bounded-retry/release 依赖也进入 formal code manifest | `CODE_CLOSED_REAL_FORMAL_ATTEMPT_REACHED_LOCAL_COMPILER_FAILURE_NOT_TRANSPORT` |
| V15-REL-30 | C0 | 已消费 identity 曾继续留在 `pending_unapproved_dry_runs`，且 formal 失败说明错误声称长度来自 seed；若继续使用会把“已花费历史”误当“当前候选” | pending 始终只保留下一项未批准身份；`85d1…` 与 `bebe…` 仅在 consumption 历史中保留并永久拒绝复用。当前 pending 是绑定 exact V8.12 attestation、原 9-call ledger 与恢复 bundle 的 formal `799e…` | `MANIFEST_RECONCILED_FORMAL_RESUME_AWAITING_EXPLICIT_APPROVAL` |
| V15-REL-31 | C0 | longitudinal 7,488-action sweep 的旧 dry-run 把冻结配置中的 `request_retries=1/fail_fast=true` 同时当成科学合同和执行韧性；任一 429/408/5xx/timeout 或孤立 terminal response 都会让整批停止，而直接改全局 YAML 又会无谓使 V8.19.2 corpus/qualification 身份失效 | 保留模型、prompt、Bank、retrieval、16 actions、temperature、seed 与旧 config SHA；另立内容寻址的 execution-only transport contract：每 logical call 最多 4 个 ledger-visible physical attempts，只重试冻结的瞬时 transport classes，terminal content 不盲重试，孤立失败继续，连续 5 个同类失败熔断。两次完整 dry-run 字节一致：7,488 logical / 29,952 maximum physical，identity `a4a1a94f…ee913`、call plan `3f473200…f75cc`、最坏上限 `$9.4597662`；旧 `faf13c51…f93c69` 永久 stale | `CODE_CLOSED_TARGETED_TEST_PASS_FULL_DRY_RUN_REPRODUCED_UNAPPROVED` |

| V15-REL-32 | C0 | longitudinal sweep judging 计划包含 7,488 outcomes × quality/risk × 2 judge families = 29,952 logical calls，但正式 runner 仍给每条一个 physical slot 并在首个失败后终止；这会让一次 503/timeout 作废整批，同时旧 cost identity 也只覆盖单次尝试 | 科学 judging 合同不变，新增独立、内容寻址的 execution transport contract：每 logical call 最多 4 次，每家 provider-output cap 继续冻结为 Gemini 2/DeepSeek official 3；只有明确 provider-surface failure 可隔离，未知错误/4xx/本地 postcondition 立即停止；完整计划顺序上连续 5 个同类失败熔断；任何缺行只写 `NONREPORTABLE_INCOMPLETE_MATRIX`，不得生成训练 labels。fresh continuation 仅继承 byte-identical call plan 中带完整 provenance/result 的 `SUCCEEDED` 行，并把旧 ledger SHA 纳入新 identity，不能因一条 terminal row 重做其余成功调用。真实 sweep outcomes 尚未产生，因此 full judging dry-run identity 尚不可计算 | `CODE_CLOSED_TARGETED_TEST_PASS_FULL_DRY_RUN_BLOCKED_ON_SWEEP_OUTCOMES` |
| V15-REL-33 | C0 | ESConv auxiliary judging runner 已允许每 logical call 最多 10 个 ledger-visible physical attempts，却仍只按首个 attempt 计算 dry-run API 数、token 与费用；运行又会在第一条已知 provider-surface terminal failure 上终止。旧 estimate 因而可低估最坏预算至 10 倍，并让一条截断/格式噪声作废整个 split | 保持双家族 quality/risk 科学合同、prompt、schema 与 seed 不变；cost identity 改为同时报告 logical single-attempt 与 10-attempt 最坏上界，预算门按 physical attempts/最坏费用放行，并用 `math.fsum` 稳定求和；execution transport contract 内容寻址 runner/API/ledger/retry/judging 文件。已知孤立 provider-surface failure 继续矩阵，连续 5 个同类失败熔断，4xx/未知/本地错误立即停止；缺一 call 即写空 labels 和 `NONREPORTABLE_INCOMPLETE_MATRIX`。byte-identical continuation 只继承完整 `SUCCEEDED` 行并仅为剩余 calls 重新计费。所有旧 full auxiliary-judging dry-run identities 因预算/执行合同变化失效，generation 产物不受影响 | `CODE_CLOSED_TARGETED_TEST_PASS_FULL_DRY_RUN_PENDING_GENERATION_OUTPUTS` |

### 6.9 Hybrid 检索诊断（Part 3/3.1，独立分支 `pm-v1.5-hybrid-retrieval`）

这一节记录的是一条完全独立、仍处于诊断阶段的支线：在 `MemoryRetriever`/`StrategyRetriever`
之外新增一个**从未接入任何真实调用方**的 `HybridMemoryRetriever`/`HybridStrategyRetriever`
（词法 + 语义融合），用于回答"混合检索是否值得在 Part 4 原子迁移全部真实消费者"这个问题。
与第 6 节其余内容不同，这里目前没有任何付费 API 调用，也没有触碰任何正式冻结产物；记录
在案是因为其中至少一条已经是本项目今年遇到的最接近生产事故量级的真实 bug。

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-HYB-01 | C1 | Hybrid 检索的 floor 排除条件用 `<=`（两个维度都"小于等于"floor 才保留，否则排除），但 floor 本身定义为"训练正例里的最小分数"——恰好等于该 floor 的正例（也就是定义 floor 的那个样本）在两个维度同时命中时会被自己定义的门排除，与"不会排除任何已知正例"的设计承诺直接矛盾 | 排除条件改成严格 `<`（两个维度都严格低于 floor 才排除等价于允许 `>=` 通过）；新增专测构造一个词法分数和语义分数都恰好等于 0.5、floor 也是 0.5 的候选，验证它必然存活 | `CODE_CLOSED_FULL_TEST_PASS` |
| V15-HYB-02 | C1 | Floor 校准时的查询只用裸 `current_user_text`，但真实检索路径用的是 `retrieval.context_query(current_user_text, history, summary)`；两者长度和内容分布不同，意味着校准出来的 floor 并不是针对真实部署时会出现的查询分布拟合的 | 校准查询改为统一调用 `context_query`，复用语料本身已有的 `recent_dialogue`/`session_summary` 字段（这两个字段本来就在合成语料里，零新增数据/API 成本） | `CODE_CLOSED_REAL_DATA_RERUN_PASS` |
| V15-HYB-03 | C0 | 为避免每次调用都重新编码全部 Strategy Bank，在 `HybridStrategyRetriever` 构造时把 11,590 张卡的 `retrieval_text` 一次性整批传给 `encoder.encode()`；该函数没有任何内部分批/分块，真实运行时把全部卡片一次性塞进同一次 transformer 前向传播，实测常驻内存冲到约 87GB、CPU 长时间不退出，只能手动 kill —— 是本阶段唯一真正逼近生产事故量级的问题，且完全是"为了修另一个问题（重复编码浪费）而引入的新问题" | 新增 `batched_encode()` helper，任何大规模文本集合一律按固定 batch size（128）切块编码再拼接，绝不允许无界集合喂给一次 `encode()` 调用；`_embed_all_texts`（floor 校准的批量编码）同步接入同一 helper（即使这次不是它引起崩溃，也不能让同一形状的风险留在第二个调用点）；杀掉旧进程后重跑，内存回落到约 1.5–2GB 并保持稳定 | `CODE_CLOSED_MEMORY_CONFIRMED_SANE_FULL_TEST_PASS_REAL_RERUN_COMPLETING` |
| V15-HYB-04 | C1 | `HybridStrategyRetriever` 缺少 `confidence()`（真实 `StrategyRetriever.confidence` 是 `policies.py` 里 `>= threshold` 的真实门控信号）；同时，用 EvoEmo 的 evaluator-only `topic` 字段当 query 代理算出来的报告性诊断数字（0.912 命中率）被过度解读为足以支持 Part 4 原子迁移的证据——但按已批准计划的数据边界规则，只有 train/calibration 切分与 ESConv validation 切分的证据才合法，EvoEmo 数字永远是 report-only | 补 `confidence()`，严格保持与真实版本一致的纯词法语义（不在没有校准/验证证据的情况下发明"融合置信度"，留给未来若真的采纳 Hybrid 时再设计）；新增 `evaluate_case_memory_retrieval_quality`（真实 calibration 切分，跑完整 `retrieve()` 融合排序流程而不只是 floor 判断）与 `evaluate_esconv_strategy_retrieval_quality`（真实 ESConv validation 切分，172 对话/2,393 turns，镜像 `esconv.py` 已有的 `strategy_recall_at_k` 写法）作为目前唯一合法的"可用于采纳决定"的证据来源，报告中与 EvoEmo report-only 部分显式分区、互不污染 | `CODE_CLOSED_FULL_TEST_PASS_REAL_RERUN_IN_PROGRESS` |
| V15-HYB-05 | C1 | `scripts/v1_5/25_eval_pm_v2_external_v1_5.py` 的两个显式 frozen-parameter 核验列表（`GENERATION_STAGE`、`PMV22_REFERENCE_BASELINE_STAGE`）都没有比较 `evo_memory_builder_contract_sha256`/`evo_memory_global_catalog_sha256`，即便这两个字段早已在 Part 2 被接入 freeze contract 与真实 attestation——"接入了 freeze"不等于"接入了下游每一个读 freeze 的核验点" | 两个列表都补上这两项核验，并新增专门的"篡改即拒绝"回归测试（`test_v1_5_external_eval_rejects_stale_evo_memory_catalog`）；不是结果颠覆性漏洞（24/24a 两个驱动脚本自己的交叉检查已经能防止不一致的 attestation 被生产出来），但属于计划里明确点名的"evaluation attestation"检查点的真实缺口 | `CODE_CLOSED_FULL_TEST_PASS` |
| V15-HYB-06 | C2 | 口头向用户汇报把 `pm-v1.5-hybrid-retrieval` 相对 `pm-v1.5_1` 的提交数说成 6 个，实际 `git log --oneline pm-v1.5_1..HEAD` 只有 5 个（很可能把两分支共同祖先提交也数了进去）；性质上和本账本反复出现的"批准/消费时间戳倒签"是同一类错误——凭记忆报数而非先跑确定性命令验证 | 任何"提交数/测试数/费用数/耗时"类陈述，开口前必须先跑一次确定性命令验证，不能凭记忆推算；发现后已在同一轮对话中口头更正 | `RECONCILED_VERBAL_CORRECTION` |

**最终采纳决定（2026-07-20T14:41:00Z，见 `outputs/pm_v1_5_hybrid_retrieval_adoption_decision.json`，绑定
`diagnostic_report_contract_sha256=c8674d11...9233bc8e5f`）：`NOT_ADOPTED`。** 修完 V15-HYB-01..05 后按合法证据边界
（Memory 用 calibration 切分、Strategy 用 ESConv validation 切分，真实跑完整 `retrieve()` 流程，2393 turns/172 个独立
dialogue cluster）重新出结果：Strategy 上 hybrid 数值上更差（hit_rate 0.394 vs 0.406，precision 0.165 vs 0.172），
paired dialogue-cluster bootstrap 的两个 95% CI 都跨过 0，不能证明有差异；Memory 上 MP/MS 完全无差异，仅 ME 的
precision 从 0.5 升到 0.625，但 n=24、hit_rate 两边都已顶格 1.0、且不能在另外两个来源复现，单独站不住。这组合法证据
与更早的 report-only EvoEmo 诊断（lexical 0.588–0.647 vs hybrid 0.912）形成鲜明反差——后者用 EvoEmo 评估者专用的
长段落 `topic` 字段当 query 代理，与真实部署时的短查询在形状上完全不同；两者的巨大落差本身就说明那个 0.912 更像是
查询形状的人为产物，而不是真实检索质量的信号，印证了 V15-HYB-04 一开始的怀疑。用户据此决定：不批准 Part 4 原子
迁移，继续使用现有 `MemoryRetriever`/`StrategyRetriever`（lexical-only）；Hybrid 诊断代码、测试与两份报告保留归档
（`hybrid_retrieval.py`/`hybrid_retrieval_diagnostics.py`/`40_diagnose_hybrid_retrieval.py` 及其测试从未被任何真实
调用方导入，`tests/test_hybrid_retrieval_isolation.py` 持续强制这一点），仅在未来出现新的、同一数据边界下的证据时才
可重新讨论——不得仅凭复述同一组数字、或再次用 report-only EvoEmo 数字顶替合法证据来重开此决定。

### 6.10 actual-468 grounding 缺陷修复与差量复审

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-GRD-01 | C0 | `context_grounding_match` 的旧 claim 用“both candidate context fields are supported”这类元描述，DeepSeek 将字段名本身误读为待蕴含文本；大量分歧来自测量工具措辞而非数据 | claim 改成直接陈述两个字段文本均须由证据蕴含；旧结果只作 incident/calibration；新措辞必须经独立 pilot 后再作差量复审 | `CODE_CLOSED_REAL_JUDGE_PILOT_PENDING` |
| V15-GRD-02 | C0 | 25 个真实 DATA_DEFECT 同时包含仅 evaluator context 缺陷、2 个 summary 缺陷和 6 个可见对话缺陷；若只手改派生 JSONL，会令 embedding、inventory similarity、Step-0 与文本不同步 | 修复源 `pm_v2_bundles.jsonl` 的显式 overlay，再调用既有 `write_development_dataset()` 对全 52 users/468 states 做 canonical 本地重编译；原始目录只读，新版本写新目录 | `CODE_CLOSED_PLACEHOLDER_RECOMPILE_PASS_REAL_CONTENT_PENDING` |
| V15-GRD-03 | C0 | 首版 overlay 虽记录 classification SHA，却不验证；重复 case/state 可被 dict 覆盖；子集/超集、错误 user/mode/case、任意 turn patch 均可能进入修复 | overlay 必须精确覆盖冻结 25-state 集合；逐行交叉核验 classification SHA、original case SHA、state/user/mode/case；FIELD_ONLY 禁止 history patch，VISIBLE 只允许冻结的精确 turn indices | `CODE_CLOSED_FULL_TEST_PASS` |
| V15-GRD-04 | C0 | 即使限制 summary 的 empty/non-empty 形状，17 个本来 summary 正确的 FIELD_ONLY 状态仍可被 overlay 顺手重写，改变 PM 可见输入与 Step-0 | overlay 层强制 `FIELD_ONLY_REPAIR_SUMMARY_ALSO_NEEDED`：仅冻结的 2 个 state 必须携带 summary 修复，其余 17 个必须为 `None` 并保持原 summary 字节不变；正反测试覆盖 | `CODE_CLOSED_TARGETED_TEST_PASS` |
| V15-GRD-05 | C1 | production exact-25 合同与 6-state pilot 若共用一个“允许子集”的发布入口，会为正式数据留下绕过完整性门的后门 | pilot 与 full 使用不同 stage/identity；pilot 固定 6 个代表形状，只验证 provider-facing prompt/schema/postcondition且永不产出 production overlay；只有 full 的 25/25 结果可 materialize overlay | `CODE_CLOSED_DRY_RUN_PASS_FIRST_PAID_PILOT_FAILED_CLOSED` |
| V15-GRD-06 | C1 | 首次真实 repair pilot 的公共 system prompt 允许“无额外信息时返回空 summary”，但冻结的两个 summary-repair 状态要求非空 summary；模型在第 2/6 条遵循前者返回空串，严格 postcondition 正确终止。若放松校验会破坏冻结的 summary-present 配平合同 | 不放松 validator；公共 prompt 改为服从逐任务 summary 规则，summary-required 分支显式要求非空且允许与 context 有限重叠；失败响应额外保存 parsed payload 便于审计。旧 identity 永久消费（2 次调用，1 成功/1 失败，真实费用 `$0.0001926`）；修复后必须产生新 dry-run identity 并重新批准 | `CODE_CLOSED_TARGETED_TEST_PASS_FRESH_DRY_RUN_PENDING` |

### 6.11 双域训练与墙钟加速

| ID | 级别 | 问题 | 永久修法/护栏 | 状态 |
|---|---|---|---|---|
| V15-DUAL-01 | C0 | 纵向合成域每个 state 有 16 个 memory/strategy action，而 ESConv auxiliary 是单 session、memory 结构性不可用且只有 `M0+R0/M0+RS`。若直接拼行或按 state/action 数加权，719-state 域或 16-action 域会仅凭行数支配 HGB、rule/CV 与 calibration，研究对象不再是同一 PM 在两个互补环境中的平衡 | 所有拟合与候选选择冻结为 domain→dialogue/user→state→action/prompt-alias 分层等权；报告每域有效总权重必须各为 0.5。底层 model/routing/rule/CV/calibration 原语、正式双域入口与分域 gate 已完成并通过全量测试；仍须等待两域完整 labels，不能把“入口已完成”写成“训练已运行” | `CODE_CLOSED_FULL_TEST_PASS_REAL_INPUTS_PENDING` |

### 6.12 actual-468 post-hoc instrument qualification

| ID | 严重度 | 已确认问题 | 冻结处理 | 当前状态 |
|---|---:|---|---|---|
| V15-SEM-11 | C0 | V8.19.1 修复后真实案例一致拒绝已降为 0、25 个 repair 全部 attested、确定性检查全过，但原 actual-468 gate 因一个负控漏检和一个 provider 截断仍为 `FAIL`。直接要求 exact PASS 会永久阻断 sweep；直接把 FAIL 改名 PASS 又会伪造研究记录 | 新增独立 `pm-v1.5-actual-468-posthoc-instrument-qualification-v1`：原 gate 永久保留 FAIL；仅在 0 个真实一致拒绝、25 个 repair、468 个确定性检查全过、且残留恰好等于冻结的一个 control miss + 一个 truncation 时输出 `QUALIFIED_DATA_CORPUS_WITH_DISCLOSED_INSTRUMENT_LIMITATIONS`。报告同时冻结 316 个 panel disagreement 与 report-only citation 指标，并禁止继续调 prompt/control/阈值/数据。V8.19.2 真实 qualification report SHA=`638408e1…7d96`、contract SHA=`c6d40af1…79b7`、attestation SHA=`78cd0ace…a659`；sweep、judging、freeze 传播 admission mode/status，不得伪称原 gate PASS | `CODE_CLOSED_FULL_TEST_PASS_REAL_V8_19_2_QUALIFIED` |
| V15-SEM-12 | C1 | recovered gate 保存的是 recovery report 的 canonical-JSON 内容哈希，而不是 pretty-printed 文件字节哈希；若 verifier 错用 `sha256_file` 会把真实一致的恢复血缘误判为漂移 | qualification builder 同时验证上游 canonical 内容哈希，并由新 artifact attestation 另外绑定当前 recovery 文件字节哈希；语义身份与磁盘身份分层，不放松任何校验 | `CODE_CLOSED_TARGETED_TEST_PASS` |
| V15-DATA-18 | C0 | `ObservableSourceSummary.catalog_embedding` 明确是 exclude=True 的构造期临时量，但 `state_to_v1_runtime()` 曾把它写入 legacy `catalog_fingerprint`。因此落盘后的 audited PMV2 state 无法重建 runtime，468/468 lineage 全失败；更严重的是 runtime 重新携带了 P0-1 明确禁止的免费目录向量表面 | canonical runtime 的 64 维 legacy fingerprint 固定为全零，只保留正式、计费的 source-level query similarity；新增“公开 state JSON round-trip 后 runtime 完全一致”回归测试。V8.19.2 已零 API 完整重编译：468/468 runtime lineage PASS，runtime SHA=`5ff31de1…7ded`；states、evaluator contexts、memory backend 与 bundles 相对 V8.19.1 字节不变，因此不重跑 actual-468 judge；Step-0 shortcut audit 与 rule-grid preflight 均在新身份上 PASS | `CODE_CLOSED_FULL_TEST_PASS_REAL_V8_19_2_RECOMPILE_AND_PREFLIGHT_PASS` |
| V15-DUAL-02 | C1 | 纵向 synthetic 的跨 split `current_user_text` 去重上限是生成合同；真实多轮 ESConv dialogue 会合法重复简短用户话。把前者的 `validate_split_manifests()` 原样套到 auxiliary 会把真实数据特性误判为泄漏，反过来放宽全局门又会破坏 synthetic 防 shortcut 合同 | 两域先各自执行来源匹配的 validator，再只执行共同的跨域 state/card/user ID、dialogue split、Bank-source 和 action/memory-availability 不变量；禁止用一个全局“最宽松 validator”替代两套域合同 | `CODE_CLOSED_TARGETED_REAL_DATA_DIAGNOSTIC_PASS` |
| V15-DUAL-03 | C0 | 一个 PM 不等于一个 internal-test 文件。若 longitudinal 与 ESConv auxiliary 共用 seal/ledger/report，先读取一个域可能意外打开另一个域，失败重试或合并 gate 也会掩盖某域不成立 | 两个 internal label 文件训练前分别 seal；同一 candidate manifest 显式绑定两个 seal；模型、阈值与 comparators 全冻结后，按域使用独立 append-only ledger 各消费一次并分别报告，最后只做预注册的 conjunction，不以好域覆盖坏域 | `CODE_CLOSED_FULL_TEST_PASS_REAL_SEAL_AND_CONSUMPTION_PENDING` |
| V15-DUAL-04 | C1 | 串行 provider backoff 造成数十小时墙钟浪费，但直接给 `PersistentAttemptLedger` 套线程池会产生重复计费、attempt 序号冲突、预算竞态和不可复现输出；把“计划加速”写成“已经支持并发”同样危险 | 并发保持冻结 call plan/prompt/model/seed/retry/统计单位，采用确定性 shard+独立 ledger+hash-bound merge，不共享可变账本。正式 runner 已支持 `sha256_text(physical_call_key)[:16] mod 4` 的 exact partition；每片有独立 paid stage、identity、预算、熔断器和 call-level attestation，只能输出 `SHARD_*_NO_AGGREGATE`，不得单片造 labels。四片全部成功后由零 API merger 验证 full-plan/逐片 SHA、exact keys、terminal success 与 attestation，再由 `--aggregate-only` 从完整 merged ledger 一次性创建 labels。当前 20,736-call train+calibration 计划的四片为 5,219/5,285/5,153/5,079 calls，exact coverage dry-run 已通过；正式付费前仍须小规模 execution pilot 和最终代码下双 dry-run | `CODE_CLOSED_TARGETED_TEST_AND_REAL_PLAN_4_SHARD_DRY_RUN_PASS_PILOT_PENDING` |
| V15-DUAL-05 | C0 | 自动 gold NO-GO 后，双域 NOT_GOLD 弱监督链虽然能机械完成拟合，却可能让保守风险阈值把所有动作判为不可行，或让质量/风险/成本头共同退化为固定 `M0+R0`；若没有 pre-internal viability gate，打开一次性 internal 才发现 collapse 会浪费 holdout，并把“能训练”误写成“学会路由” | auxiliary calibration 170 states/340 outcomes 已完成 1,360 次真实调用并编译为 `LLM_WEAK_SUPERVISION_NOT_GOLD`；修复结构性 N/A risk calibration 后的 fit-only 候选血缘、0.5/0.5 域权重、OOD 与 conformal 均机械完成，但 longitudinal calibration 108/108、ESConv calibration 170/170 均为 `M0+R0`，learned-decision rate=0、fallback=1、entropy=0。新增内容寻址的 calibration action-viability audit，复用既有 external action-preflight 阈值，在 internal 前检查 severe OOD、no-feasible、nonfallback、M0/R0/M0R0 支持、最大动作占比和 entropy；真实报告为 `NOT_SUPPORTED_FOR_INTERNAL_TEST_CONSUMPTION`，两个 internal 继续密封。只把 max-risk 从 `.3` 调至 `.4/.5` 虽可取消 fallback，raw utility argmax 仍全是 `M0+R0`，故禁止把阈值放宽冒充根修复 | `REAL_FIT_COMPLETE_CALIBRATION_COLLAPSE_AUDITED_INTERNAL_NOT_CONSUMED` |
| V15-DUAL-06 | C0 | 当前 collapse 不是单一阈值问题：longitudinal 弱标签本身仍有非 M0 opportunity（65/108 oracle action 非 M0，平均 oracle-vs-M0 headroom 约 `.0288`），但模型经风险/成本后 108/108 utility argmax 为 M0；ESConv 信号更弱（17/170 label oracle 为 RS，平均 headroom 约 `.0069`），模型同样全 M0。此前 production top-1 evidence-surface pilot NO-GO，而 oracle-memory uptake 支持且 multi-source 干扰已被定位 | 下一迭代只允许使用 train 与 calibration，优先比较显式 action-advantage/rank 或两阶段 need→action 目标，并把 retrieval/evidence composition 与监督目标分别诊断；必须预注册、生成新候选身份并重新走同一 viability gate。不得打开 internal、不得复用当前 calibration 反复选择阈值、不得把 fixed-M0 解释为 learned PM。若新候选仍 collapse，则第一篇 learned-router 主张正式 `NOT_SUPPORTED`，只保留透明 rule/fixed baseline 与机制负结果 | `ROOT_CAUSE_LOCALIZED_TRAIN_ONLY_REDESIGN_REQUIRED` |
| V15-DUAL-07 | C0 | “65/108 label oracle 非 M0”仍可能是从 16 个带噪绝对分数取最大值产生的 winner's curse，而不是可学习的动作边际值。零 API train-only 因子审计把 MP/MS/ME/RS 每个开关在 8 个 matched backgrounds 内先聚合、再保留两家 family effect；纵向同向正/负/反向/不确定分别为 MP `23/24/30/139`、MS `20/10/28/158`、ME `32/14/22/148`、RS `18/28/30/140`。synthetic need/harm 方向对齐率仅 `.056–.167`。ESConv RS 的 311 个完整 effect 为 `28/63/48/172`，另 7 个 recovery pair 缺 raw-family effect | 冻结 `pm-v1.5-factorized-small-sample-weak-learning-v1`：训练单位改为 state×component repeated measure；structural need、两家 paired effect、structural/applicable risk 与 deterministic cost 分路，反向/小效应可 abstain，ambiguous 不作负例；禁止 16-way absolute argmax 造 pseudo-gold。报告 SHA=`911e9097…fbda`，只作 train data-quality 诊断，不是新 label 或 PASS | `REAL_ZERO_API_TRAIN_SIGNAL_AUDIT_COMPLETE_DIRECT_16_ACTION_TARGET_NOT_SUPPORTED` |
| V15-DUAL-08 | C1 | 两家 LLM 的 agreement 不能证明 accuracy；直接用全量人工又背离低成本弱监督目标。若先看 state/action/regime/judge 方向再选人评，会引入确认偏差 | 在新模型 fit 前确定性冻结 32 条 train-only human anchor：MP/MS/ME/RS 各 8 条，每个 judge consensus 正/负/反向/不确定 stratum 各 2；state 不重复、AB/BA 确定性平衡，packet 隐藏 state/user/action/regime/model/judge/expected direction 和资源 ID。人评只估计 labeling-function 可靠性与 sanity，不自动晋升为 bulk gold；packet SHA=`06c52a87…e961`，binding SHA=`1659174e…414a`。完成标注并内容寻址后，才允许拟合强正则 factorized component-benefit candidate；calibration 只运行一次 viability 决策 | `HUMAN_ANCHOR_PACKET_FROZEN_AWAITING_ANNOTATION_NO_NEW_MODEL_FIT` |
| V15-DUAL-09 | C1 | routing objective 的 `effective_weight_by_domain` 报告曾用裸 `sum()` 聚合浮点权重；它不参与 HGB 拟合，却会进入 training report/downstream hash，在不同 CPython 浮点求和实现间可能产生末位差异并使相同科学计划出现不同 identity | 改用固定的 `math.fsum()`；回归测试要求两个域的有效权重精确等于 `0.5/0.5`，不再只用近似比较。训练正式入口仍须绑定单一冻结 runtime，但报告哈希不再依赖裸 `sum()` 的版本行为 | `CODE_CLOSED_TARGETED_TEST_PASS` |

### 6.13 longitudinal action sweep 的精确续跑

| ID | 严重度 | 已确认问题 | 冻结处理 | 当前状态 |
|---|---:|---|---|---|
| V15-SWP-01 | C1 | 首次正式 7,488-action sweep 的 7,487 条 outcome 已成功并由 ledger 记录，但最后一条在 4 个冻结 transport slots 内依次遇到 429/429/429/503；若原地重跑会违规扩展已消费 identity，若整批重跑又会重复付费并把随机 provider 波动混入 7,487 条已完成结果 | 新增 exact-plan carry-forward：重新计算的完整 call plan 必须逐行相等，并绑定旧 cost identity、call-plan/ledger/outcome/raw-call/summary 文件 SHA、7,487 个成功 call keys 与唯一剩余 key；只接受旧 ledger 的 `SUCCEEDED` terminal recovery payload，FAILED/exhausted 永不继承；在全新目录、新 identity 下只为剩余 1 条重新获得最多 4 次物理预算，同时仍物化完整 7,488 行。原运行永久保留为 `INCOMPLETE`。fresh continuation `526c0ac6…2fbe` 已真实执行：唯一新调用首次成功，新增费用 `$0.00006225`，最终 7,488/7,488、零 failure、artifact `ATTESTED` | `CODE_CLOSED_FULL_TEST_AND_DOUBLE_DRY_RUN_PASS_REAL_CONTINUATION_PASS` |

### 6.14 longitudinal judging 的 holdout 作用域

| ID | 严重度 | 已确认问题 | 冻结处理 | 当前状态 |
|---|---:|---|---|---|
| V15-JDG-01 | C0 | 原正式 runner 在同一次 29,952-call 运行中生成 train/calibration/internal-test 全部标签，并在创建 internal seal **之前**把 internal rows 纳入全局 judge-health、reliability 与 quality gate；这等价于模型选择冻结前查看 held-out outcome，事后再写 seal 不能消除泄漏 | 正式运行必须显式选择 `train_calibration` 或 `sealed_internal_test`。前者只物化 5,184 outcomes/20,736 logical judge calls并运行 label-health gates；后者只物化 2,304 outcomes/9,216 calls，完整后立即 seal，summary 固定为 `SEALED_HOLDOUT_NOT_YET_CONSUMED`，禁止计算 reliability/quality/raw-family 聚合。两者使用独立 paid stage、call plan、ledger、cost identity 与 attestation；双域 candidate/阈值/comparator 冻结后才由 one-shot ledger 消费 internal bundle | `CODE_CLOSED_FULL_TEST_AND_BOTH_SCOPES_DOUBLE_DRY_RUN_PASS_PAID_RUN_PENDING` |

### 6.15 judge 适用性、sparse-zero 与双域效用

| ID | 严重度 | 已确认问题 | 冻结处理 | 当前状态 |
|---|---:|---|---|---|
| V15-JDG-02 | C0 | ESConv auxiliary 没有 memory action，`selected_context_misuse`、`stale_or_conflicting_use`、`unnecessary_exposure` 等风险在所有合法动作上结构性不适用。把这些恒为 0 的维度当作 judge constant-dimension 缺陷，会让正确的 N/A 机制错误阻断训练 | 用单一 `applicable_risk_fields(action_id)` 合同同时约束 judging gate、训练 risk heads、fixed comparator 和 external verifier；结构性不适用标为 N/A，不当 PASS/FAIL 信号；训练 risk head 对不适用行权重为 0；summary/attestation/preflight 绑定 applicability SHA。实现与测试已完成，但 train 在其余适用维度上仍为 NOT_SUPPORTED | `CODE_CLOSED_FULL_TEST_PASS_TRAIN_GATE_STILL_NOT_SUPPORTED` |
| V15-JDG-03 | C0 | 两个稀疏风险维度大多同时为 0 时，全矩阵 exact-match rate 可接近 100%，被误报为 duplicate/correlation；这只是“共同不触发”，不是两维度测量同一构念。首次 informative-only 重聚合又把 `strategy_overuse` 与 `strategy_omission` 的 −1 相关列为 failure，但二者本来接近互斥，且全局矩阵混入了某维对该 action 不适用的行 | duplicate 决策先取“两个维度都对该 action 适用”的 pairwise applicability mask，再取至少一维非零的 informative rows；同时报告 overall/informative 分母。高正相关可提示重复，负相关只作互斥诊断，不能以 `abs(correlation)` 自动当 duplicate failure；证据不足固定为 `INSUFFICIENT_EVIDENCE`。实现、反向测试与同一 636/636 标签的零 API 重聚合均完成；假阳性已消失，但其余 response 覆盖与跨家族方向问题仍使 instrument NOT_SUPPORTED | `CODE_CLOSED_FULL_TEST_PASS_INSTRUMENT_STILL_NOT_SUPPORTED` |
| V15-JDG-04 | C1 | `label_reliable_rate` 曾在双域 preflight 中被当硬阻断项，而共享 judging 合同把它定义为诊断；同一批标签在不同入口得到不同可用性判定 | completeness、schema、适用维度 coverage、低 MAD 支持和独立 judge-family 血缘是硬门；joint reliability 只诊断并披露，不再单独 raise。若未来要把它升级为硬门，必须预注册阈值并重做全部 labels | `CODE_CLOSED_FULL_TEST_PASS` |
| V15-MODEL-01 | C0 | risk head 的样本权重已有 MAD 置信度，但没有动作适用性 mask。ESConv 中结构性不适用的 0 分恰好 MAD=0，会以“高一致性”满权重污染风险学习 | risk head 权重固定为 domain/state/action/alias weight × MAD weight × applicability mask；不适用行权重为 0。报告每个 head 的分域、分动作有效样本量；全局可用权重为 0 时 fail-closed，不得训练一个常数 head | `CODE_CLOSED_FULL_TEST_PASS_TRAINING_NOT_STARTED` |
| V15-METRIC-01 | C0 | 若只给 fixed comparator 使用 `median±MAD`，learned PM 仍用 nominal median，双方的 utility 定义不同，比较失去意义；反过来若只改共享函数，又可能悄悄改变旧 V1/V1.5 报告 | 新增默认关闭的双域 conservative utility：response=`clip(median−MAD,1,5)`，applicable risk=`clip(median+MAD,0,3)`，冻结 `λ=1.0`；learned、rule、fixed、calibration frontier、internal bootstrap 调用同一 helper，同时保留 nominal 与 conservative 指标，禁止根据 internal/external 调 λ | `CODE_CLOSED_FULL_TEST_PASS_TRAIN_MEASUREMENT_NOT_SUPPORTED` |
| V15-METRIC-02 | C0 | 过去用未经操作定义的 overall/composite/utility 或单个 `PASS` 同时代表“读懂需求、回复好、证据用对、风险低、成本省”，使双裁判差异无法定位，结构性 N/A 被当作 0，也让某项恶化可被平均分掩盖。研究者自己无法从分数回答具体好在哪里、坏在哪里 | V3 禁止把含混总分作为论文主指标。建立 machine-readable 原子 metric registry：每项明确 decision question、unit、eligible denominator、formula/source fields、方向、N/A/tie/abstain、user/dialogue-cluster CI、阈值来源、failure action 和 prohibited interpretation。需求边界/校准、Bank eligibility/暴露、blind support preference、continuity、claim-evidence precision、applicable risk、实际 retrieval/token/USD/latency 分开；内部 selector scalar 只作决策规则且 components 分项报告。没有原始计数/分母的 `PASS` 不得进入 readiness | `TRANSPARENT_OBSERVABLE_METRIC_SYSTEM_SPECIFIED_MACHINE_REGISTRY_PENDING` |
| V15-JDG-05 | C1 | 13c judging runner 原先没有正式 artifact attestation writer；仅把 applicability hash 写在 summary 中不足以证明 labels、维度适用性和后续双域 preflight 使用同一合同 | 已增加正式 attestation 并绑定 labels/raw/ledger、适用性、utility λ/clamp 与相关代码哈希；21a 会重验 train label 与代码 SHA。但独立复审发现当前 record 尚未显式冻结 sparse-zero 最小信息行数、相关性符号/适用行规则、low-MAD/reliability gate 角色，且 calibration 13c 自身不要求 train attestation。由于 train 已 NOT_SUPPORTED，当前不会产生可供 21a 使用的正式 attestation；这些缺口必须在任何新测量路线真正冻结前补齐 | `PARTIAL_CODE_CLOSED_ATTESTATION_SCOPE_GAPS_CONFIRMED` |
| V15-JDG-06 | C1 | 排除结构性 N/A 后，Gemini 仍出现适用维度近常数/低风险触发，DeepSeek 与 Gemini 在若干 response 维度的低 MAD coverage 低于冻结 0.80；train 的可靠标签率约 0.588。这些是 judge 行为和第一篇无人工金标签的真实限制，不能靠不断调 prompt/阈值直到全绿 | 当前 train 测量门如实记录为 `NOT_SUPPORTED`，calibration/internal judging 暂停。先修 V15-JDG-03 这种构念无关的 gate bug，再重新聚合同一 train labels；若 factual grounding、memory appropriateness、personalization 等适用 response 维度仍破坏 hard coverage，则停止 auxiliary 监督路线或另立新的 train-only 测量协议，不能打开 calibration/internal 救场 | `TRAIN_GATE_NOT_SUPPORTED_CALIBRATION_INTERNAL_PAUSED` |
| V15-JDG-07 | C0 | 即使单维 gate 可修，两个 judge 是否对真正的 R0/RS 路由方向达成一致仍未被直接检查。正式 train-only 复算显示 318 states 中 52.5% 至少一方 tie；双方均明确的 151 states 中方向一致率 64.2%，90% dialogue-cluster CI `[0.577,0.709]` | 该结果只作诊断，不伪装成可训练 gold；因此另立预注册 balanced-order direct pairwise pilot。pilot 又因 safety effective non-tie 不足而 NO-GO，故 ESConv auxiliary 降为 diagnostic，删除 learned ESConv routing 主张，且不打开 calibration/internal | `FORMAL_DIAGNOSTIC_AND_PAIRWISE_PILOT_COMPLETE_AUXILIARY_ROUTE_STOPPED` |
| V15-JDG-08 | C0 | 在现有 13c 单动作绝对打分已 NOT_SUPPORTED 后，直接继续 calibration/internal 或改阈值会把测量工具问题伪装成训练数据问题；但整套重做 labels 又耗时且没有先验证 direct comparison 是否更可靠 | 已完成完全独立、train-only、balanced-order pairwise pilot：24 个不重合 dialogue/state、R0/RS 双顺序、两 judge family，共 96 logical calls。修复后的真实执行 96/96 成功、97 physical attempts、1 次 Gemini 5xx 有界恢复、实际约 `$0.01009656`。quality agreement=.7273、non-tie=.3333 均 PASS；safety agreement=.7692 PASS，但 non-tie=.1667 低于冻结 .25，故总结果 `PILOT_NO_GO`。未创建 labels，未读 calibration/internal，不进行 post-hoc 调参；正式 freeze 见 `data/pm_v1_5_contracts/esconv_auxiliary_pairwise_instrument_freeze_v1.json` | `REAL_PILOT_COMPLETE_NO_GO_AUXILIARY_SUPERVISION_STOPPED` |
| V15-JDG-09 | C1 | 首次 pairwise 真跑时，DeepSeek official 的 loose `json_object` transport 看不到 Pydantic schema，而 prompt 只写“遵守所给 schema”，导致 13/13 DeepSeek 输出系统性使用 nested camelCase；全局 circuit-breaker 又被交替出现的 Gemini 成功重置，不能识别单 family 系统性故障 | prompt 明列四个 flat snake_case keys、allowed values 与禁止 nesting/camelCase；breaker streak 改为按 judge family 独立。首次 identity 永久 `CONSUMED_INCOMPLETE_CODE_BUG`，已知费用约 `$0.0026111`；新 identity 双 dry-run 后真实 96/96 通过，证明修复有效 | `CODE_CLOSED_REAL_RUN_VALIDATED` |
| V15-JDG-10 | C0 | ESConv auxiliary 的 absolute-label instrument 与 direct pairwise instrument 先后 NO-GO。前者在适用 response 维度上出现低 MAD coverage、Gemini 近常数/近重复行为，且两个 judge 对 R0/RS 的明确方向一致率只有 64.2%；后者虽然 quality agreement=.7273、quality non-tie=.3333、safety agreement=.7692 均达门，但 safety non-tie=.1667 低于冻结 .25，并伴随不可忽略的顺序敏感性。这不等于“RS 无效”或“PM 概念失败”，而是当前无人工金标签、两家 LLM judge 和当前样本不能稳定提供训练所需的 R0/RS 安全偏好监督 | 冻结 absolute `NOT_SUPPORTED` 与 pairwise `PILOT_NO_GO`，不读 auxiliary calibration/internal labels、不调阈值/prompt、不给当前 pilot 补样本，不训练 learned ESConv router。第一篇仍可保留：同一纵向 PM 的质量–风险–成本主线、ESConv 上冻结 R0/RS fixed-condition 回复质量/机制比较、EvoEmo/ES-MemEval-derived 长期记忆外部测试；但不得声称 PM 已从 ESConv 学会何时开 RS。未来研究须使用预注册的新样本与独立测量：少量人类/专家 adjudication gold、富集但自然的 safety-sensitive cases、重复多裁判/概率偏好模型、strategy item-level evidence 与 active sampling；不得用当前 NO-GO 数据继续调到通过 | `MEASUREMENT_LIMITATION_FROZEN_AUXILIARY_SUPERVISION_AND_DUAL_DOMAIN_TRAINING_STOPPED_FUTURE_WORK_DEFINED` |
| V15-JDG-11 | C0 | longitudinal 5,184 state-action 全量聚合首次被报告为因 `composite_support_exact_match_rate=.0666/.2330 < .98` 而失败；直接核对实现后确认方向被口头读反：代码只在 exact-match rate **大于等于** `.98` 时失败，低值本身是健康的。真实 raw-family 缺陷是 DeepSeek 的 `temporal_consistency/non_intrusiveness` 近复制，以及 Gemini 的 `temporal_consistency`、`unsupported_personal_claim` 常数和 `factual_grounding/temporal_consistency` 近复制 | 正式 longitudinal 聚合统一使用 action applicability、至少 10 条 informative non-zero、相关性按符号拆分；所有 gate 改为先返回完整诊断，正式失败时写 `LONGITUDINAL_JUDGE_INSTRUMENT_NOT_SUPPORTED` summary/attestation，且绝不物化训练 labels。报告必须同时写布尔 failure 字段，禁止仅凭阈值名或数值方向口头解释 | `CODE_CLOSED_TARGETED_TEST_PASS_ZERO_API_REAGGREGATION_CONFIRMED` |
| V15-JDG-12 | C0 | 修正 gate 后，纵向监督仍不支持训练：聚合 label gate 有 4 个 RS personalization action-cell 低于冻结 0.80；预注册 label-value feasibility 同时失败于 single-action share、RS share、strategy-helpful、memory-helpful 与 memory-harmful 分离。两个 judge 的 per-state oracle action 仅 27.16% 相同；用一方选择、另一方评价时，相比该评价方自己的最佳 fixed action 分别下降约 `.01382/.00986` | 将完整 20,736-call 结果冻结为 measurement/root-cause evidence，不生成 action labels、不训练 PM、不打开 longitudinal internal-test。先做 train-only response-mechanism uptake 诊断，区分“检索把干扰项一起送入”“generator 未吸收资源”“judge 不可辨识”；任何新机制只可由预注册小 pilot 立项，不能在当前全量结果上继续调 gate。若 pilot 不能同时恢复 mechanism uptake 与独立测量可靠性，第一篇必须降级为 deterministic/source-need routing 或 `NOT_SUPPORTED`，不得宣称 learned quality–risk–cost PM 已验证 | `LONGITUDINAL_SUPERVISION_NOT_SUPPORTED_ROOT_CAUSE_REPORT_FROZEN_NO_LABELS_NO_TRAINING` |
| V15-JDG-13 | C1 | formal aggregate 已通过 V8.19.2 post-hoc qualification 读取数据，但 attestation writer 仍无条件绑定旧 `actual_corpus_semantic_review/gate_report.json`；因此完整诊断写出后才因旧文件不存在报错。科学 gate 结果未受影响，但 artifact 无法证明真正使用的 admission lineage | attestation input 必须复用同一运行分支：提供 qualification 时绑定 qualification report+attestation，否则才绑定原 gate；新增反向测试禁止 qualification 执行回退到 stale original。同一 complete merged ledger 已完成零 API 重聚合：summary/attestation 写出、qualification lineage 正确、training labels 两个文件均不存在，然后以 `LONGITUDINAL_JUDGE_INSTRUMENT_NOT_SUPPORTED` 预期终止 | `CODE_CLOSED_TARGETED_TEST_AND_REAL_ZERO_API_REAGGREGATION_PASS` |
| V15-JDG-14 | C1 | 最初的 response-mechanism pilot 草案同时安排“top-1 evidence + 原 prompt”和“top-1 evidence + selective-use prompt”，但冻结的 `selective_esmem_v1` 本来已经明确要求只在相关时使用证据；第三臂既近似重复现有指令，又把 retrieval dilution 与 prompt 改动混在一起，不能形成清晰因果对照 | 在看到任何 pilot outcome 前收窄为 14 个 train-only、user-disjoint state 的成对诊断：零成本复用 attested full-sweep control；唯一新臂保持同一模型、temperature、seed、冻结 prompt 和原 retriever，只在 post-retrieval/pre-generation 将每来源 evidence surface 确定性限制为至多 1 项。新增 14 logical calls / 56 worst-case physical attempts；明确为 report-only，不调用 judge、不创建 labels、不授权训练 | `CODE_CLOSED_DOUBLE_DRY_RUN_REPRODUCIBLE_AWAITING_PAID_PILOT` |
| V15-JDG-15 | C1 | 两臂设计已写入 tracked `data/pm_v1_5_contracts/...`，但工作区仍遗留同名、未追踪的旧 `outputs/...pilot_v1.json` 三臂副本；独立复核误把旧副本当 canonical，正式 runner 虽正确 fail-closed，却造成“HEAD 代码与合同不匹配”的假警报和临时 identity 分叉 | 单一事实源固定为 tracked `data/pm_v1_5_contracts/longitudinal_response_mechanism_pilot_v1.json`；formal 21f runner 拒绝任何其他路径，即使内容看似相同；旧 outputs 副本已零 API 重新生成并与 canonical 逐字节一致。后续 uptake metric 合同进入 identity 后重新双 dry-run，旧 identity 不批准 | `CODE_CLOSED_FINAL_METRIC_BOUND_DOUBLE_DRY_RUN_REPRODUCIBLE` |
| V15-JDG-16 | C0 | 两臂 pilot 虽已冻结 action、prompt 和 evidence surface，但最初只在文字中写“resource uptake”，没有把 reference 构造、BGE 主指标、方向规则、supportive guardrails 与禁止用途冻结进执行 identity。若先看回复再挑相似度或阈值，机制诊断会变成 post-hoc 选指标 | 已在任何新回复生成前冻结 measurement contract、encoder 与可执行 analyzer；真实 14/14 treatment 调用一次通过，实际约 `$0.00110925`。预注册结果为 `MECHANISM_SIGNAL_NOT_ESTABLISHED_REPORT_ONLY`：helpful BGE delta 均值 `-0.00604`、仅 `3/10` 为正（要求至少 6）；harmful 均值 `+0.01058`、仅 `2/4` 为负（要求至少 3）。helpful memory 的 annotated target 实际均被 top-1 命中，memory-harmful 2/2 方向正确，但 strategy-harmful 0/2，说明统一 top-1 既未稳定增强有益 uptake，且可能集中暴露单张不合时宜 strategy。冻结 NO-GO，不改阈值/指标、不创建 labels、不授权训练 | `REAL_PILOT_COMPLETE_MECHANISM_SIGNAL_NOT_ESTABLISHED_REPORT_ONLY_NO_GO_FROZEN` |
| V15-JDG-17 | C1 | 21f 的 dry-run 只调用 `_plan`，而真实 `--run` 进入 `_run_groups`；主入口曾漏传 `_run_groups` 必需的 `experiment_config_path`。因此计划/预算可复现并不等于付费入口可执行，若不修会在批准后零或小额调用阶段才暴露 | 主入口显式传入 experiment config 与 uptake contract；增加 real-run entry 参数绑定回归测试，并把 runner SHA 纳入新的 cost identity。旧 dry-run identity 永久作废，不允许仅因“调用计划没变”沿用 | `CODE_CLOSED_FULL_SUITE_PASS_FINAL_DRY_RUN_REPRODUCIBLE` |
| V15-JDG-18 | C0 | top-1 evidence-surface pilot 为 NO-GO 后，不能直接推断“冻结 generator/prompt 根本不会使用 memory”。独立的 18-state oracle-memory 上界真实执行显示：12 个 helpful pair 的 target-evidence BGE delta 均值 `+0.02124`、`9/12` 为正；6 个 harmful pair 均值 `-0.00723`、`4/6` 非正。单源 profile/summary/event 合计 `8/9` 为正，而三源 multi-source 仅 `1/3` 为正 | 冻结为 `ORACLE_MEMORY_UPTAKE_CAPACITY_SUPPORTED_REPORT_ONLY`：排除“绝对不会吸收记忆”这一单一根因，但不证明 response quality、retriever、PM 或 judge 有效。根因优先级转向 production retrieval/evidence composition，尤其多源干扰；不得把 oracle annotations 写入 deployable router 或训练标签 | `REAL_PILOT_COMPLETE_REPORT_ONLY_CAPACITY_SUPPORTED_MULTISOURCE_LOCALIZATION_PENDING` |
| V15-JDG-19 | C0 | 在两家 judge 分歧大时直接增加第三家并按多数票定 gold，只会把三个相关、无人工校准的模型意见变成伪金标签；还会掩盖顺序敏感、tie/abstention 与构念不一致 | 先建立 18-state、AB/BA 顺序平衡、action/source/generator 盲化的 memory-specific response-quality packet；helpful pair 的预期方向是 oracle memory，harmful pair 的预期方向是 M0，但该方向不展示给 judge。逐家报告方向准确率、顺序一致性和跨家族一致；第三家 majority 只作诊断，永不生成训练 gold。packet 已两次零 API 逐字节复现，正式 judging 尚未批准 | `CODE_CLOSED_TARGETED_TEST_PASS_ZERO_API_PACKET_REPRODUCIBLE` |
| V15-JDG-20 | C1 | 三个 multi-source oracle treatment 同时暴露 MP/MS/ME 时 uptake 仅 `1/3` 为正；仅比较 M0 与 all-three 无法区分是某一来源无效、来源间互相稀释，还是生成器的多证据组合负担 | 固定同一 3 个 train states、同一 prompt/generator/seed/R0，只新增 MP-only、MS-only、ME-only 各 3 次；复用既有 M0/all-three 6 个 outcome。零 API 合同与 9-call dry-run 已准备，预算按 4 个 transport slots 计入；结果只作机制定位，不创建标签、不调 source 组合、不授权训练 | `CODE_CLOSED_TARGETED_TEST_PASS_DOUBLE_DRY_RUN_REPRODUCIBLE_PAID_EXECUTION_NOT_APPROVED` |
| V15-JDG-21 | C1 | 低预算裁判资格赛 V2 连续暴露同一根因的三层表现：① loose `json_object` 消息未含 `json`，首条 Qwen combined 被 HTTP 400 拒绝；② 补词后完整对象的 `quality_rationale=546` 超过只存在于本地 Pydantic 的 500 字符上限；③ 只补长度后，第一条 pairwise 把三段理由写入三个 `*_preference` 枚举字段并漏掉对应 `*_reason`。本质都是把“合法 JSON”误当成“严格 schema 输出”；旧 dry-run 只验证本地 schema/预算，无法证明 provider-visible schema 等价 | identity `d02f123d…6a83`、`45450c0d…ce20`、`e7133510…5f04` 均永久关闭，第三次为 16 carried + 9 new success + 1 complete-but-invalid，新增 `$0.0093008`；不得解释为 judge NO-GO。根修复停止逐字段打补丁：仅对 loose endpoint 注入完整 canonical Pydantic JSON Schema；GPT strict prompt 不变；单条 schema 失败只被 ledger 隔离，继续其余诊断，最终明确写 `INCOMPLETE...NO_VERDICT` 且禁止聚合。兼容性标准在结果前冻结为 5 种请求形状必须 5/5 合法、0 schema failure。新 5-call pilot 两次零 API dry-run逐字节一致，identity `9f1fbed5…7409`，上限 `$0.0224688`；真实执行仍须用户复核后另行批准 | `ROOT_CAUSE_CLOSED_FULL_SCHEMA_ROW_ISOLATION_ACCEPTANCE_FROZEN_DOUBLE_DRY_RUN_UNAPPROVED` |
| V15-JDG-22 | C0 | 在 loose-schema 路线停止后，train-only strict-schema bakeoff 用同一 12 个冻结状态、AB/BA 双顺序比较 Claude Haiku 4.5、Gemini 2.5 Flash、GPT-5 mini。首次执行证明 Claude 24/24 可用，但 Gemini/GPT 的隐藏 thinking/reasoning 吃掉可见 JSON 预算；显式 `thinkingBudget=0` 与 `reasoning_effort=minimal` 修复后，exact carry-forward 24 条 Claude、仅新跑 48 条，最终 72/72、零重试、零 schema failure，新增费用约 `$0.03953`。然而按结果前冻结的门，三家均未达到“所有偏好维度 AB/BA 一致率 ≥.80”：Claude evidence=.667；Gemini evidence=.417、safety=.667；GPT-mini overall/support=.583、evidence=.75。三家 schema、overall informative 与 GPT-anchor overall threshold 均过门，但不能抵消位置敏感性；人工锚点 overall 仅作描述（Claude .70、Gemini .727、GPT-mini .571） | 冻结 `LONGITUDINAL_STRICT_JUDGE_BAKEOFF_NOT_SUPPORTED`，不调当前 packet 的 prompt/阈值、不按多数票造 gold、不自动提拔任一候选、不批量重标或训练。该结果说明端点兼容已解决、剩余是构念/顺序可靠性问题，不等于 memory/strategy 无效或 PM 概念失败。若继续第一篇，下一测量协议必须在新 train-only 样本上预注册：优先把 overall/support preference 与 evidence/safety 的确定性审计或专门 rubric 分开，并用扩大的人评 adjudication 校准；当前 12 条只能作方向性证据 | `REAL_STRICT_BAKEOFF_COMPLETE_ZERO_API_AGGREGATION_REPRODUCIBLE_NO_CANDIDATE_PROMOTED` |
| V15-JDG-23 | C0 | 既有绝对量表和多维 pairwise 把“回复质量、证据使用、安全/风险”塞进同一次 LLM 判断；某个模型即使能稳定比较 overall/support，也会因 evidence/safety 的顺序敏感而整体淘汰，反之亦然。直接增加第三家多数票不能修复构念混合，只会把相关误差包装成 gold | 已预注册双域 train-only 拆职资格赛：24 个此前未用状态（纵向 12、ESConv auxiliary 12），质量岗只做盲化 AB/BA overall/support；证据/风险岗逐回复、只审计 action-applicable 维度，violation 必须提供回复与证据精确摘录并允许 `insufficient_evidence`；成本继续确定性计算。12 条人工锚点已在任何候选 API 调用前完成结构、枚举、适用维度与逐字引用校验并冻结为 tracked/content-addressed artifact；明确只是单研究者独立参照，不是自动 gold。Claude Haiku 4.5、Gemini 2.5 Flash、GPT-5 mini 分别在两个岗位受测，岗位分别晋级，失败岗位不得产 bulk labels；正式执行器再次核对 audit 返回维度恰好等于 compiler 声明。结果前冻结的零 API 聚合器分别计算 AB/BA 一致率、informative rate、适用维度覆盖、逐字摘录有效率和 abstention；人工一致率仅作描述，禁止多数票或自动晋级。本阶段不改变 PM 目标、不读 calibration/internal/external。canonical packet 已迁入 tracked data，执行器和聚合器共同进入两次逐字节一致的最终 dry-run：288 logical / 576 worst-case physical、单次尝试保守总上界约 `$1.3855`、最坏约 `$2.7711`；真实 API 尚未授权 | `HUMAN_ANCHOR_AND_AGGREGATION_FROZEN_FULL_EXECUTION_BOUND_DOUBLE_DRY_RUN_REPRODUCIBLE_AWAITING_EXPLICIT_APPROVAL` |
| V15-JDG-24 | C1 | 拆职资格赛首次真实执行未产生任何可报告裁判结论，却同时暴露四个执行合同缺陷：Anthropic strict tool schema 不接受整数 `minimum/maximum`，48 个 evidence/risk 请求被 HTTP 400 拒绝；两条已付费 quality 响应的理由超过本地 500 字符上限；统一 1.5× token 估算低于 Anthropic 实报输入；第三条已付费响应在后置预算检查抛错前未写 terminal ledger，导致精确费用不可恢复 | identity `9da399a4…f616` 永久关闭为 `CONSUMED_INCOMPLETE_CODE_COMPATIBILITY_AND_LEDGER_BUG`，不得解释为 judge NO-GO。 canonical Pydantic schema 与 severity 0–3 本地约束不放宽；只对 Anthropic provider-visible strict-tool schema 做内容寻址的数值边界投影，理由/摘录提示显式限制在本地上限内，Anthropic input planning 单独提高到 2.25×，任何付费响应即使本地 postcondition 失败也先终结 ledger 再隔离。旧 288-call identity 不复用；先以全新 stage 运行恰好覆盖 Claude quality 与 evidence/risk 的 2-call 兼容 pilot，PASS 后才允许生成新的 full-matrix dry-run/approval | `ROOT_FIX_CODE_AND_TARGETED_TEST_PASS_COMPATIBILITY_PILOT_DOUBLE_DRY_RUN_PENDING` |
| V15-JDG-25 | C1 | 修复后的 2-call Claude compatibility pilot 中 quality 1/1 首次成功且通过 canonical 本地校验，但 evidence/risk 在推理前被 Anthropic HTTP 400 拒绝：provider-visible 数组 schema 仍带 `maxItems`；首次投影只覆盖了数值上下界，没有覆盖 Anthropic strict-tool 子集同样不支持的数组上下界 | identity `c2362b3f…b8c85` 永久关闭为 `CONSUMED_INCOMPLETE_ANTHROPIC_ARRAY_SCHEMA_COMPATIBILITY`，真实费用仅为成功 quality 的 `$0.002427`，不是语义资格结论。投影协议升为 v2，同时移除 provider-visible `minItems/maxItems`，canonical Pydantic schema 继续保留并在响应后严格执行数组长度、数值范围和交叉字段约束；反向测试、全套测试和两次逐字节一致的全新零 API dry-run均已通过，当前只允许以新 identity 再做同范围 2-call pilot，不直接放大到 288 calls | `ROOT_FIX_AND_FULL_TEST_PASS_NEW_TWO_CALL_DRY_RUN_REPRODUCIBLE_AWAITING_APPROVAL` |
| V15-JDG-26 | C1 | array-schema v2 的第二次 2-call pilot 已证明 provider schema 语法兼容：quality 与 evidence/risk 都完成真实推理和 strict tool call；但 evidence/risk 返回 `verdict=insufficient_evidence, severity=1`，被 canonical 跨字段规则拒绝。根因不是裁判资格结论，而是 Pydantic model validator 无法自动表达在 provider JSON schema 中，原提示也未显式写出 verdict→severity 映射；同时发现 tracked measurement contract 虽记录 schema SHA，dry-run/runner 未重新核对 live canonical schema 的绑定缺口 | identity `8fcd94f8…c0c73` 永久关闭为 `CONSUMED_INCOMPLETE_CROSS_FIELD_SEMANTIC_VALIDATION`，真实费用 `$0.006089`。不放宽 canonical 规则、不静默改写模型输出；在 system+user 两处显式冻结 `no_violation/insufficient_evidence→0，violation→1..3`，call plan 从冻结 item 字段重建 evidence/risk prompt，live-schema 对 tracked schema SHA fail-closed。修复后的新 identity `b9a87c84…735e` 已完成真实 2-call compatibility pilot：quality 与 evidence/risk 均首次成功、零重试、零失败，evidence/risk 恰好返回 compiler 声明的 3 个维度且全部跨字段规则通过；真实费用 `$0.005970`。该 PASS 只认证执行兼容，不认证任何 judge 岗位、不创建 labels、不授权训练；下一步必须在最终冻结代码上重新做完整 288-call 两次零 API dry-run，再以新 identity 单独审批 | `REAL_TWO_CALL_COMPATIBILITY_PASS_FULL_MATRIX_DOUBLE_DRY_RUN_PENDING` |
| V15-JDG-27 | C0 | semantic-shape 修复后的完整拆职资格赛已触达全部 288 calls；284 成功，4 个 Gemini evidence/risk 输出因把多条 memory 或整张 strategy card 写进 `evidence_excerpt` 而超过 500 字符并且不是任一可见证据字符串的逐字子串，正确隔离为 terminal structured-output failure。按结果前冻结的“可独立充当自动标签器”门对五个完整 candidate-role block 做零 API 复核后没有任何岗位候选通过：quality AB/BA consistency（门槛每项 `.80`）Claude `.458/.458`、Gemini `.750/.750`、GPT-mini `.708/.625`；evidence/risk exact-excerpt validity（门槛 `.95`）Claude `.701`、GPT-mini `.658`，Gemini 本身只有 `44/48` 完整。informative rate 与 abstention 不是主阻塞 | identity `021e7729…3709` 永久关闭为 `CONSUMED_INCOMPLETE_NONREPORTABLE_MATRIX`；288 次物理调用，无重试，真实用量 317,178 input / 98,485 output，约 `$0.522968`。不得裁剪/改写 4 条 Gemini 输出冒充合格，不再为相同 prompt/seed 重跑；当前只冻结“任一候选可作为自动 gold labeler”的主张为 `NO_ROLE_CANDIDATE_SUPPORTED`，**不等于禁止使用已有 LLM 判断训练**。第一篇若只检验有限条件下可学习性，可另行预注册 `LLM_WEAK_SUPERVISION` 路线：把两家/多家原始判断、AB/BA 一致性、分歧与 abstention 显式作为有噪声监督和样本权重，保留岗位分离与确定性 cost；训练/校准只用 train/calibration，sealed internal 仍一次性消费，论文必须称 judge-conditioned weak supervision，不能称人类 gold 或最优策略。人类锚点用于描述性校准和最终小样本 sanity check，不要求把全量改成人工 | `AUTOMATIC_GOLD_NO_GO_WEAK_SUPERVISION_ROUTE_REQUIRES_PREOUTCOME_CONTRACT` |
| V15-JDG-28 | C0 | 自动 gold 资格赛 NO-GO 后若仍沿用旧 formal gate，会把“测量不够可靠”错误等同于“没有任何监督可训练”，与第一篇只检验有限条件下可学习性的目标不一致；反过来，若直接删除 gate 又会把不可靠裁判悄悄包装成 gold | 新增 tracked/content-addressed `pm-v1.5-llm-weak-supervision-v1` 合同和零 API 编译器。纵向完整 324 states/5,184 actions 与 ESConv auxiliary train 318 states/636 actions 均保留两家 judge 的逐维 median、MAD、family 和恢复血缘；不按 `label_reliable` 删行，训练继续使用逐维 MAD 连续权重、risk action-applicability mask、domain→dialogue/user→state→action/alias 等权和确定性 cost。两次独立编译逐字节一致，正式 attestation=`45e0f43f…78a2`；longitudinal labels=`adec34d2…b0a2`，auxiliary train labels=`737c8b51…1b90`。当前不宣称 gold、不读 internal/external；ESConv auxiliary calibration 尚无弱标签，因此双域校准/训练仍未放行。同一 NOT_GOLD 合同下的 calibration dry-run 已两次逐字节一致：340 pairs/1,360 logical calls、单次成功预估 `$0.51064424`、10-attempt 最坏上限 `$5.1064424`、identity=`6c74b9a9…6580`；尚未获付费批准或执行 | `WEAK_SUPERVISION_CONTRACT_AND_COMPILER_COMPLETE_AUXILIARY_CALIBRATION_DRY_RUN_REPRODUCED_UNAPPROVED` |
| V15-JDG-29 | C0 | 现有拆职 quality prompt 只说“overall/support quality”，未给用户边界、连续性、情绪贴合、互动负担、帮助深度的裁决优先级；同时保留两个高度重叠的 preference 字段，并向“纯质量”裁判展示 authorized context。不同模型因各自偏好行动性、温暖度或篇幅而改变结果，AB/BA 低一致不是仅靠增加第三家可修复 | V2 只保留一个 blind support-preference 岗位；质量裁判仅见 visible dialogue 与匿名回复，按用户明确边界→连续性→情绪贴合→互动负担→适时帮助→表达质量的优先级判 A/B/tie/abstain。selected evidence、hidden authorized context、action/regime/预期赢家均不展示；双顺序不一致不产生硬标签 | `SUBSTANTIVE_RUBRIC_REDESIGN_SPECIFIED_IMPLEMENTATION_PENDING` |
| V15-JDG-30 | C0 | 旧 evidence/risk prompt 强迫每个 action-applicable 维度都生成一行；模型因格式要求大量编造 `no_violation` 解释，并常把“selected context 为空”误当成“没有 memory/strategy 可遗漏”。这既测不到 source/RS 的增量价值，也把未选择资源与资源不存在混为一谈 | evidence 岗改为先抽取回复中的个性化/记忆依赖主张，再用精确子串映射 visible/selected evidence；无主张返回 `no_personalized_claim`。omission 只由同 state matched treatment 的增量结果判断，不从空 selected context 推断；N/A/insufficient 不编码成零风险 | `SUBSTANTIVE_EVIDENCE_AUDIT_REDESIGN_SPECIFIED_IMPLEMENTATION_PENDING` |
| V15-JDG-31 | C0 | 旧 positive treatment 的单源 helpful 行 100% 混入 irrelevant item，多源正例同时暴露多个 helpful/irrelevant item。真实 oracle single-item 有 uptake，而 production/top-1 与 all-three 不稳定；因此即使裁判完美，也无法从这些回复得到干净的组件效应标签 | 新训练单元固定为同 state/prompt/generator/seed matched pair；control、恰好一条 helpful、恰好一条 placebo、恰好一条 harmful 分离。MP/MS/ME/RS 分别在 memory unavailable/available 背景验证 uptake，单源过门后才辨识 source×source/source×RS；未形成回复差异即停止扩量 | `CLEAN_CAUSAL_TREATMENT_SPECIFIED_NEW_DATA_PENDING` |
| V15-JDG-32 | C0 | 双裁判分歧过去被当成“选第三家多数票”或“取 median 后继续训练”的工程问题；但未校准的相关 LLM 可共同犯错，方向冲突本身也可能表示 treatment 无差异、rubric 含混或岗位不适配。硬多数会把不确定性变成伪 gold | 先查 uptake；再按岗位估计每家 AB/BA 与人工 anchor 可靠性。两家一致为高权重弱标签；单家合格且另一家 abstain 为低权重；方向冲突变 soft 0.5/高不确定性或不标注；系统性冲突触发少量人工 active adjudication。任何第三家只增加独立测量信息，不自动形成多数 gold | `DISAGREEMENT_AS_UNCERTAINTY_SPECIFIED_LABEL_MODEL_PENDING` |

### 6.16 执行加速与本地部署边界

| ID | 严重度 | 已确认问题 | 冻结处理 | 当前状态 |
|---|---:|---|---|---|
| V15-ACC-01 | C1 | 大批量 judging 主要耗时在串行网络等待和退避；直接给无锁 ledger 套线程池会产生重复计费、attempt 冲突、预算竞态与不可复现输出 | 已实现确定性四分片、独立 ledger/paid identity、exact-key/hash-bound merge 与零 API aggregate-only；不修改 provider、prompt、seed、重试或科学统计单位。四片仅允许并行推进 call-level evidence，任一片缺失都不能产 labels。当前真实 full plan 分片 dry-run/exact coverage 通过；必须先完成小 execution pilot，再在最终代码上双 dry-run并逐片单独批准 | `CODE_CLOSED_TARGETED_TEST_AND_REAL_PLAN_DRY_RUN_PASS_PILOT_PENDING` |
| V15-ACC-02 | C0 | 在中途把 hosted Llama、DeepSeek 或 Gemini 换成本地“近似模型”，即使更快，也会改变 generator/judge treatment；内部、ESConv、EvoEmo 不再是同一套机制 | 当前研究不切模型、不换 endpoint、不改量化。仅允许在相同请求/响应合同下做 execution-only 优化；任何本地模型替换进入下一研究版本并重新做 compatibility、labels、checkpoint、freeze 与 external | `FROZEN_NO_MIDSTUDY_MODEL_SWAP` |
| V15-ACC-03 | C1 | A6000 48GB 可运行 Llama-3.1-8B，但当前 1,438 个 auxiliary generation 和 7,488-action sweep 已完成；Gemini 无同模型本地权重，DeepSeek official 当前 judge 也无法在单张 A6000 上等价复现。现在部署本地模型不会缩短剩余关键路径 | 当前关键路径继续使用冻结的 Gemini + DeepSeek official judging；A6000 只用于 BGE、训练、bootstrap、本地 preflight/report 等零 API 工作。未来 V1.6 可预先冻结本地 open judge/generator 并从头验证 | `NO_CURRENT_CRITICAL_PATH_GAIN` |
| V15-ACC-04 | C1 | 主机磁盘约 98% 使用、仅约 21GB 空闲；盲目下载量化模型或保留多份 cache 会造成中途写盘失败、artifact 丢失或 ledger 不完整 | 任何本地模型实验前先做只读空间清单和经批准的非破坏性清理；模型、HF cache、输出与不可变 artifact 分盘规划。当前版本不为“试试看”下载大模型 | `BLOCKED_BY_STORAGE_AND_TREATMENT_PARITY` |

## 7. 修复本身曾引入或差点引入的新问题

这是今后最需要反复阅读的一节。每次“修一个点”至少要审查以下二阶影响。

| 原修复动机 | 新风险 | 最终原则 |
|---|---|---|
| 本地反复跑全量测试 | `python -m pytest` 隐式改变 import path，掩盖 CI 真实失败 | 验证命令必须与 clean CI 完全相同 |
| 替换不稳定 development judge | 换入 final GPT-4o，造成 evaluator leakage | 先检查角色隔离，再替换 endpoint；alias 不等于 family/model/route |
| 删除非法目录 probe | 16-way source selection变成盲猜，可能退化为 `ME+R0` | 用合法、有限、计费 Step-0；删除和保留都要有因果定义 |
| 给 PM 增加语义模型 | 只在训练 state 填 embedding、外部仍为空，或模型身份进入特征造成新环境捷径 | 同一 local snapshot/revision/tree hash/pooling 在 development 与 external 复算；身份仅审计；parity test |
| 用语义模型替代正则 | 把 semantic classifier 的 argmax 当新 oracle，仍然是“更聪明的答案键” | readiness 只作连续 observation；Strategy value 由盲评 R0/RS outcome 决定 |
| 打散 Strategy/advice 标签 | 若只交换字段而不改变 provider surface，标签会变成随机噪声 | provider 明确生成独立 readiness surface，actual-corpus judge 验证；resource target 仍非 outcome |
| 给负 source 添加同题 decoy | decoy 若实际有帮助，会污染 memory oracle；若太怪会形成模板 shortcut | 使用自然、明确非个人的同题信息；item-utility semantic gate + shortcut audit 双门，失败即重设计而非调阈值 |
| 强制 requested==realized | 将真实 zero-hit 错误当成非法数据 | 分开 requested/attempted/realized，不强求相等 |
| 要求 positive source 命中 | 若 outcome 后删除 zero-hit，会产生选择偏差 | required-hit 只能发生在 response/judge 前 |
| 为 actual semantic gate 加 controls | 仅 family/regime、可设 0、明显 sentinel，形成假安全 | 完整字段覆盖、自然 corruption、数量/seed/hash 锁定 |
| 清除 seed/Bank 共源 | “清除 875”被误解为把策略经验全部删掉 | 删除正式 52 个实例来源，不删除合法领域知识；明确 875/52/823 含义 |
| 修全仓 preflight | 原地更新旧 freeze hash 会伪造历史有效性 | 旧 freeze 只标 stale；新实验生成新 freeze |
| 收紧 provider schema | 180 字符 rationale cap 阻断与研究无关的文本 | provider 只生成它必须控制的 surface；评价字段本地编译 |
| 用 pilot 检混题 | relocation/academic/workplace 本身不正交 | pilot 也必须代表合法任务，不用人工冲突制造失败 |
| 放宽 V8.1 的 2/9 fallback | 会把不稳定生成器表面写入训练数据 | 不放宽 gate；改变请求粒度并预预算一次 repair |
| 只改 pilot 生成器 | formal 仍走 whole-bundle，重新产生 mechanism mismatch | 修改共享 contract 后逐一核对所有消费者 |
| 改成逐 case 生成 | 正式调用从 52 变 468，最大 936 | 方法改进必须同步更新成本、超时、ledger、approval、文档和 hash |
| 发布 staged approval | manifest 与审查索引可能出现不同状态 | 用户授权也是内容寻址的单一事实，不能靠文件先写成已批准 |
| 给 Strategy 检索加 embedding 缓存以避免重复编码 | 把"缓存"实现成构造时一次性把全部 11,590 张卡整批塞给 `encoder.encode()`；该函数无内部分批，真实运行内存冲到约 87GB，需手动 kill（V15-HYB-03） | 任何"缓存/预计算"优化都必须同时检查底层调用的输入规模上限；大规模文本集合一律显式分批（`batched_encode`），不能假设 encoder 自己会处理，也不能只用小规模单测掩盖真实规模下的行为 |
| 为 sparse-zero 假重复增加最小非零样本数 | 若 exact-match/correlation 仍在全矩阵计算，零值仍会支配数值，只是晚一点触发 | duplicate 决策必须基于 informative-only rows；overall 只作描述，二者都报告分母 |
| 排除不适用风险维度 | 一次性把“低信号”都叫 N/A，会掩盖 Gemini 在真正适用维度上的常数输出 | N/A 必须由 action contract 决定，不能根据观测分数事后决定；适用维度仍执行完整 health gate |
| 引入 MAD 保守效用 | 只改 learned 或只改 comparator，双方 estimand 不同；根据 internal 结果调 λ 又会污染 holdout | 一个 helper、一个冻结 λ、两侧同公式；同时报告 nominal/conservative，internal 前内容寻址 |
| 为缩短时间改成本地 endpoint/量化 | 模型行为、tokenizer、schema、finish reason 与历史 treatment 不同，内部/外部不再公平 | 当前版本只做 execution-layer 加速；模型/endpoint/量化变更必须成为新实验身份并重跑全链 |

## 8. 不可回归宪法

以下规则高于“某个测试过了”或“某次 review 没提到”。任何一条被触碰都必须在 PR 中显式
说明；不能以“只改了一点”跳过全链检查。

1. **单一 treatment 身份。** 除研究操纵外，development、sweep、fixed comparator 和
   external 的 generator、prompt、normalization、finish reason、retriever、阈值和 EF 相同。
2. **严格 pre-action 边界。** requested action 前只有冻结的 Step-0；不得出现 item text、
   top-k、ID、oracle、outcome 或未来信息。
3. **动作四层语义。** requested、attempted、realized、prompt-equivalence 永不合并。
4. **zero-hit 不消失。** 它保留成本和失败含义，不因 realized action 改写调用历史。
5. **实例级数据隔离。** 正式 52 seed sources 不得进入 Strategy Bank；外部 lineage 只按可证
   范围陈述，不把领域知识重合误叫作弊，也不把 exact-clean 误叫完全独立。
6. **outcome 前数据门。** required-hit、semantic validity、fallback、shortcut audit 都发生在
   response/judging 前；看 outcome 后不得重生成、删 state 或改 regime。
7. **实际 corpus 优先。** 模板/27-case pilot 不能替代对真实 468 states 的检查。
8. **reportable data 零确定性 fallback。** 如果 provider/repair 仍失败，整次 run fail-closed。
9. **holdout 真正一次性。** internal bundle 先 seal，candidate 先 freeze，ledger 先 STARTED，
   outcome 只消费一次；失败后需要新的 held-out users，而不是重测同一 bundle。
10. **judge 角色与 lineage 隔离。** development/final 在 alias、family、model、route 四层分离；
    endpoint descriptor 和 experiment config hash 进入下游验证。
11. **有效样本量诚实。** user 是主要独立 block；alias labels、16 actions 和同一 state 的派生行
    不能扩大独立 N。
12. **强竞争比较器不可绕开。** rule、cost-matched fixed、`ME+R0` 和 high-resource fixed 各自
    回答不同问题；不能只展示最有利比较。
13. **成本向量不混写。** Step-0、retrieval、generator input/output、USD、latency 和实验 judge
    cost 分开；主张必须写准确 metric 名称。
14. **pilot 与 formal 同机制。** pilot 只可缩小数据量，不能更换 schema、prompt compiler、
    retry、fallback 或 provider-visible fields。
15. **失败是合法结果。** Gate M/F/E 或 pilot 未过时输出 `NOT_SUPPORTED/FAIL`；不得在同一
    holdout 上调阈值、换模型、换 comparator、删样本直到通过。
16. **版本和结果不继承。** PM-v1、legacy supplemental、V1.5_1 及其他分支的 checkpoint、
    freeze、dry-run、approval 和结果不得跨版本拼接。
17. **文档不能领先于事实。** `PASS`、`APPROVED`、`SUPPORTED`、调用数和 hash 必须与唯一
    artifact 事实一致；冲突时一律按 NO-RUN 处理。
18. **主张不超过设计。** 当前只是一轮 supervised pre-item-retrieval router 研究；不声称
    RL/POMDP、长期用户改善、临床安全或普遍外部泛化。
19. **Advice Readiness 不等于 Strategy Value。** listen-only 仍可受益于 reflection card；请求
    suggestion 也不代表当前 Bank 检索有边际价值。训练标签只能来自冻结 R0/RS outcome。
20. **语义表示也是 treatment。** encoder、revision、snapshot tree、pooling、normalization、输入
    拼接和 projection 任何一项改变，都使旧 states、shortcut report、checkpoint 和 freeze 失效。
21. **维度适用性先于数值健康。** 只有 action contract 判定适用的风险维度才进入 coverage、
    constant/duplicate、risk head 和 utility；N/A 既不是零风险证据，也不是 judge 缺陷。
22. **同一效用定义贯穿所有比较器。** learned、transparent rule、fixed、calibration 和
    internal 必须共享 nominal/conservative helper、clamp、λ 与 applicability；不得一侧保守、
    一侧名义。
23. **加速只能改变执行，不改变科学单元。** shard、并发、缓存和 continuation 不得改变 call
    plan、prompt、model、seed、重试语义、统计单位或 outcome；合并前必须 exact-key 和 hash
    校验。
24. **问题与路线各有唯一事实源。** 本文是唯一活跃问题账本；核心链路文档是唯一活跃执行
    路线；历史 postmortem 只读。不得创建未声明的新问题清单或在多个文档维护冲突状态。

## 9. 改动影响矩阵

任何未来 PR 必须查表。表中“失效”表示旧 artifact 不得继续作为当前链上游证据。

| 改动对象 | 至少失效的下游 | 必须重跑/复核 |
|---|---|---|
| seed pool、selected 52 或 split | generation plan、Bank exclusion、states、labels、checkpoint、internal、freeze、external | seed/Bank intersection、split/duplicate、全 development 链 |
| Strategy Bank/card/family | Step-0、RS retrieval、shortcut audit、sweep、所有 fixed/learned external | Bank lineage、family coverage、dev/external parity、全部下游 |
| generation prompt/schema/provider-visible fields | compatibility pilot、52-user corpus、semantic reports、所有后续 | V8 类 pilot → semantic pilot → formal generation |
| repair/retry/fallback 规则 | cost plan、attempt ledger、corpus provenance、fallback gate | fresh dry-run/approval 和生成链 |
| Step-0 representation/feature/quantization | shortcut audit、rule、learned model、cost、external | 468 shortcut gate、train/calibration/internal、freeze、external |
| retriever/top-k/min-score/source semantics | required-hit、realized action、prompt alias、cost、fixed comparators | pre-outcome retrieval audit、full sweep、训练和 external |
| action ID/alias/realized semantics | 16-action matrix、labels、oracle/regret、checkpoint、external | action-contract tests + 全 sweep 后链 |
| supporter model/prompt/temp/cap/finish normalization | 每个 response outcome 和外部比较 | 全部 generation/judging/训练/external |
| development judge panel/rubric | labels、algorithm selection、calibration、internal | semantic/control pilot、full judging、重新训练 |
| dimension applicability、MAD/utility、judge-health 规则 | label qualification、risk heads、rule/fixed frontier、calibration、internal、attestation | train/calibration 重聚合或重判（按 prompt 是否变化决定）、双域 preflight、重新训练；internal 未开前冻结 |
| final judge panel/rubric/order schema | external canary/order/main outcomes | final dry-run、canary、order pilot、external judging |
| quality/risk composite、margin、utility/cost weights | selector、rule/fixed frontier、Gate M/F/E、paper claim | train/calibration/internal；若 freeze 后变更则 external 全失效 |
| model candidates/CV/one-SE 规则 | candidate manifest、internal | train-only selection、calibration、新 internal users（若旧 internal 已开） |
| external conditions/comparator | batched schema、position balance、cost、claim estimand | condition dry-run、canary/order、external main |
| pricing/token bounds | cost hash 和 stage approval | fresh dry-run、明确用户授权；通常不必重生科学数据，除非超预算停止 |
| endpoint/model/tokenizer/量化或 hosted↔local | 所有该端点生成/判断的 outcome、labels、checkpoint、freeze、external parity | 新 compatibility pilot 与受影响全链；不得因“更快”继承旧身份 |
| release manifest/approval | 仅执行权限，不改变科学方法 | 对齐用户授权、config SHA、stage/run/cost hash；不得倒签 |
| 只改文档 | 通常不改变 pilot treatment；若文档改变主张、状态或冻结合同则仍需对齐配置/manifest | link/事实一致性检查；必要时重生成 review index |

## 10. 分阶段停止门

### 10.1 任何付费 pilot 前

- clean CI 命令与 GitHub Actions 相同；
- branch/commit/dirty diff 被记录；
- config、prompt、schema、Bank、seed 和 endpoint descriptors 内容寻址；
- dry-run 给出 logical calls、maximum attempts、per-call token bound、最大 USD；
- release manifest、artifact index 和用户明确批准完全一致；
- fresh output directory、无旧 ledger、无覆盖选项。

### 10.2 完整 52-user generation 前

- 当前代码创建全新 compatibility pilot 目录和 fresh dry-run identity，经独立审查和精确批准真实 PASS；任何 V8–V8.4 历史 attestation 均拒绝；
- V8.7 生成兼容性 pilot 已 PASS；历史 V4 语义审核和 V4.2 诊断只作 calibration，不再伪装为正式语义放行证据；
- pilot 与 formal 使用同一 surface-only casewise contract；
- selected 52 与 Bank source intersection 为 0；
- formal 468-success / 936-content / 2,808-physical 预算重新 dry-run 并单独批准。

### 10.3 7,488-action sweep 前

- 468/468 states 完整且无 deterministic fallback；
- actual-468 admission：优先接受 structured QA v3 exact PASS；本次 V8.19.2 只允许使用独立的 `QUALIFIED_DATA_CORPUS_WITH_DISCLOSED_INSTRUMENT_LIMITATIONS`，且原 gate 必须仍为 FAIL、真实一致否定为 0、25 个 repair attested、4 个代码事实全过、残留必须精确等于冻结的 1 个负控漏检和 1 个 provider 截断；分歧与 citation 缺陷完整报告；
- required-hit 只按预注册 positive challenge 规则检查；
- train-only oracle / all-split structural shortcut audit PASS；
- outcome-free train/calibration rule-grid mapping/disagreement preflight PASS；
- retrieval/action/prompt alias contract 的 deterministic preflight PASS。

### 10.4 训练与 internal 前

- 旧 7,488 outcomes、旧 judging 完整度和旧 32 条人评不能单独放行训练；必须运行
  `v1_5/22g_preflight_learnable_transfer_training_v1_5.py`，且状态为
  `READY_FOR_ONE_PREREGISTERED_FORMAL_FIT`；
- readiness 必须绑定当前 V2 contract、根因报告与唯一问题账本，且问题 ID 无重复；
- clean contrast integrity 必须 PASS：positive treatment 零 helpful+nonhelpful 混合，
  control/helpful/placebo/harm item composition 与同 prompt/generator/seed 全部精确；
- mechanism uptake 必须在 MP/MS/ME/RS、memory-unavailable/available backgrounds 上达到
  结果前冻结的门；source×source 与 source×RS interaction 未辨识时只能 shrink/abstain；
- 新 response distribution 的 measurement report 必须完成，小型人评只校准 LF，不晋升为
  bulk gold；judge family 分开保留，分歧/低置信度 abstain；
- train-only group-held-out learnability 必须同时优于 `M0+R0` 与同观测 transparent rule，
  不能靠训练集拟合度或 action diversity 放行；
- ESConv 与 EvoEmo observable-state severe OOD 必须分别 `<=0.10`；当前 EvoEmo 为 1.0，
  因此 formal fit 明确阻断；
- 专用 Python 3.13.2 venv 的 live runtime/canary 与 development 记录完全一致；
- 7,488 outcomes 和双-family labels 完整；
- action-level dimension applicability contract 已 attested；结构性 N/A 已排除，适用维度的
  constant/duplicate/correlation/MAD/coverage hard gates 满足冻结规则；
- sparse-zero duplicate 只按 informative-only rows 决策并报告有效分母；证据不足不得伪装 PASS；
- nominal 与 `median±MAD` conservative utility 的 helper、clamp、λ 已在 learned/rule/fixed/
  calibration/internal 五处内容寻址冻结；risk heads 对不适用行权重为 0，并报告有效样本量；
- joint `label_reliable_rate` 只作诊断；label completeness、适用维度 coverage 与低 MAD 支持
  仍为 hard gate；
- model family/rule 只在 train-group CV 中选择；
- calibration 只完成冻结职责；
- sealed internal manifest 在训练前存在；
- 唯一 candidate、threshold、fixed frontier、external matrix 全部写入 candidate manifest；
- internal consumption ledger 为空且用户明确接受一次性消费。

### 10.5 external 前

- Gate M 与 Gate F 按冻结规则完成；失败即停止；
- fixed seeker 无 truncation、世界线相同、chronology report PASS；
- 新 study freeze 绑定 checkpoint、data、Bank、retrieval、conditions、judges 和 claims；
- freeze 显式绑定 full/no-Step0/no-state-BGE/lexical-only 四格 checkpoint，internal 结果不得选或重调 candidate；
- learned/rule external dry-run 自包含 live runtime lineage、section truncation gate 和只报告的 development/external Step-0 分布比较；
- 任何旧 V1/V1.5 freeze 都只作历史；
- external 每个付费 stage 再做独立 dry-run/approval。

### 10.6 论文提交前

- 只报告实际执行并 attested 的比较；
- 明确哪些是 primary、supportive、diagnostic、failed pilot 和 post-hoc；
- Gate M/F/E 各自决定可写句子，不用一个 favorable gate 覆盖另一个失败 gate；
- 报告 `NOT_SUPPORTED`、失败 pilot、fallback/repair、zero-hit、alias effective N 和所有强
  comparator；
- 不把 generator input tokens 写成 total cost，不把 LLM judge 写成人类评价；
- 不把 ESConv-derived EvoEmo 写成 pristine independent external benchmark。

## 11. 结果解释决策树

| 结果 | 允许结论 | 禁止结论 |
|---|---|---|
| Gate M、F、E 全通过 | synthetic holdout 中 learned 优于同观测 rule；对强 fixed 保持竞争力；外部对 high-resource fixed 质量非劣并减少 generator input tokens | 全部 raw quality 指标全面胜出、总成本/延迟必然更低、真实用户改善 |
| Gate M 失败，Gate E 通过 | 复杂 learned router 未证明优于透明 rule；仍可能有“某个低资源策略相对高资源 fixed 更省且质量保持”的系统结果 | learned adaptive routing 成功 |
| Gate F 对 `ME+R0` 失败 | 不能把省过高资源 fixed 包装成竞争性路由成功 | PM 不弱于强同预算 fixed |
| internal 通过，external rule/cost-matched 无优势 | 只能保留限定的 high-resource efficiency 或 synthetic mechanism finding | 外部 learned routing 泛化 |
| PM collapse 到单一动作 | 当前 observation/data/supervision 不足以支持 16-action routing | 通过放松 diversity gate 把固定动作叫 PM |
| 任一数据、lineage、judge、holdout gate 失败 | 协议失败或证据不可用；修复后需要新 run identity，必要时新 holdout | 把失败 run 中 favorable 部分抽出来作 confirmatory result |

期望的科学结果不是“PM 在所有质量指标上击败所有 fixed”。更合理的成功形态是：质量相对
高资源 fixed 非劣，risk 不增加，generator input 明显下降，并且相对同观测 rule 和强同预算
fixed 在冻结 utility 上显示可重复优势。如果数据只支持透明 rule，而不支持 learned PM，
那也是有效且应报告的研究结论。

## 12. 当前执行快照（2026-07-26）

| 项目 | 当前事实 |
|---|---|
| 分支与文档 | 当前工作分支 `pm-v1.5-hybrid-retrieval`；Hybrid 已 `NOT_ADOPTED`，分支名不代表正式方法采用 Hybrid。本文是唯一活跃问题账本，核心链路文档是唯一活跃路线 |
| 正式语料 | V8.19.2：52 users / 468 states；25/25 已确认数据缺陷完成 canonical repair；actual-468 原 gate 永久为 `FAIL`，独立 qualification 为 `QUALIFIED_DATA_CORPUS_WITH_DISCLOSED_INSTRUMENT_LIMITATIONS` |
| 语料前置门 | 468/468 runtime lineage PASS；Step-0 shortcut audit PASS；transparent rule-grid preflight PASS；不再根据 outcome 调 actual-468 prompt/control/data |
| longitudinal sweep | 468×16=7,488 outcomes 已完整生成；首次 7,487/7,488 后以 exact-plan continuation 只补 1 条，最终 7,488 unique rows、零 failure、artifact `ATTESTED` |
| ESConv auxiliary generation | train 318 states/636 outcomes、calibration 170/340、internal-test 231/462，三 split 全部 `CONSUMED_PASS`；合计 719 states/1,438 outcomes，真实总费用约 `$0.1342` |
| ESConv auxiliary train judging | 636/636 judge pairs 经限定离线恢复后矩阵完整；结构性 N/A、risk-head mask、reliability 角色、统一 conservative utility 与 attestation 已实现并通过针对性测试，但零 API 重聚合仍为 `NOT_SUPPORTED`。适用 response 维度低 MAD coverage 与 judge-family 路由方向低一致性是真问题；`strategy_overuse/omission=-1` 还含二阶 gate bug。calibration/internal 暂停 |
| ESConv auxiliary pairwise | 修复 DeepSeek loose-JSON schema 后 96/96 完整；quality agreement/non-tie 均过门，safety agreement 过门但 non-tie=0.1667<0.25；正式 `PILOT_NO_GO`，未创建 labels |
| longitudinal train/calibration judging | 四分片与 continuation 已精确覆盖 20,736/20,736 logical calls；纠正 sparse-zero/applicability 与“0.98 方向误读”后，raw-family、aggregated-label 及预注册 label-value feasibility 仍未共同过门；状态冻结为 `LONGITUDINAL_SUPERVISION_NOT_SUPPORTED`，不生成训练 labels |
| calibration/internal judging | auxiliary calibration 的 170 states/340 outcomes 已完成 1,360 次真实 judge 调用，全部首次成功，真实费用约 `$0.187828`，并按同一合同编译为 `LLM_WEAK_SUPERVISION_NOT_GOLD`；两个域的 internal outcomes 仍未打开、未消费 |
| 正式训练 | 自动 gold 路线仍为 `NOT_SUPPORTED`。NOT_GOLD 双域 fit-only 已真实完成，选中 `absolute_outcome_factorized_hgb`，域权重各 0.5，OOD/conformal 机械通过；但 calibration 上两个域均 100% `M0+R0`/fallback，正式 viability audit 为 `NOT_SUPPORTED_FOR_INTERNAL_TEST_CONSUMPTION`，当前候选不得进入 internal/external |
| fixed seeker | V3 compatibility pilot 2/2 tracks、20/20 calls PASS；完整 formal 已 102/102 tracks、1,020/1,020 calls COMPLETE，零重试，真实费用约 `$1.52765`；tracked bundle binding 与 readiness 均 READY |
| external | 正式 ESConv test 与 EvoEmo/ES-MemEval-derived external 均未开始；没有 external efficacy 结果 |
| Hybrid retrieval | calibration + ESConv validation 证据不支持采用；正式链继续 lexical-only，Part 4 关闭并归档 |
| strict judge bakeoff | reasoning-budget 修复后 72/72 完整、零 schema/transport failure；两次零 API 聚合逐字节一致，但 Claude/Gemini/GPT-mini 均因至少一个偏好维度的 AB/BA 顺序一致率低于冻结 .80 而 NOT_SUPPORTED；无候选获批成为 bulk labeler |
| role-decomposed qualification | 数值/数组投影与跨字段 semantic-shape 修复后的 2-call compatibility pilot 2/2 PASS，但完整资格赛真实结果为 284/288，4 个 Gemini evidence/risk 长摘录被 canonical schema 隔离。岗位独立零 API 复核显示三个 quality 候选的 AB/BA consistency 均低于 `.80`，两个完整 evidence/risk 候选的 exact-excerpt validity 均远低于 `.95`，Gemini evidence/risk 另有 4 条不完整；因此没有模型可独立充当自动 gold labeler，不补跑。该结论不作废已有判断：若预先冻结独立的 weak-supervision 合同，可把一致、分歧、abstention 和 judge family 作为显式噪声结构用于训练，并把主张限定为 judge-conditioned learnability |
| 当前主张 | `DEVELOPMENT_AND_FIXED_SEEKER_COMPLETE_OLD_TREATMENT_AUTOMATIC_GOLD_AND_WEAK_FIT_NOT_SUPPORTED_V3_NEED_BANK_TREATMENT_REDESIGN_REQUIRED_INTERNAL_UNCONSUMED` |
| 下一关键路径 | 不重跑旧 judging，也不打开 internal。先零 API 完成 Strategy Bank V2、separated-view SupportNeedObservation、BAAI/lexical train-group probe、family opportunity→eligible retriever 对齐和三岗位 rubric；再做 40–80 个新鲜 train-only states 的 clean single-item/helpful-placebo-harm 与 RS matched uptake。新 response distribution 另建 12–24 条盲化人评 anchor。只有 need representation、Bank、uptake、measurement、component group-CV 与两域 OOD 全过，才扩量并拟合同一 PM；calibration 仅消费一次，失败则冻结 learned-PM `NOT_SUPPORTED` |

## 13. 未来每个 PR 必填模板

```text
变更目的：

触及的账本 ID：
触及的因果链层：
是否改变 treatment / estimand / comparator / claim：
是否改变 provider-visible 或 PM-visible 信息：
是否接触 train / calibration / internal / external outcome：
是否改变独立统计单位或 prompt alias：
是否改变真实部署成本：

失效的旧 artifacts/hashes/approvals：
必须重跑的 gates：
本 PR 明确不改变的机制：

clean CI 命令与结果：
dry-run identity（如适用）：
新的单一事实源：
失败时停止规则：
允许的论文句子：
禁止的论文句子：
```

审查者不得只确认“修复目标那一项测试通过”。至少还要沿第 2 节因果链向上检查信息来源、
向下检查所有消费者，并用第 9 节影响矩阵确认是否漏掉 formal、baseline、freeze、cost 或
claim evaluator。

## 14. 证据来源与维护规则

主要仓库证据：

- **本文**：唯一活跃问题编号、状态与不可回归清单；
- `PM_V1_FAILURE_LIMITATION_POSTMORTEM_ZH.md`：只读归档的 V1 结果、根因和范围；不得在其中
  维护当前问题或待办；
- `PM_V1_5_SUPPLEMENTAL_ANALYSIS_ZH.md`：legacy V1.5 的 `ME+R0`、forced-swap 和 OOD 诊断；
- `PM_V2_1_V1_SYSTEMATIC_RESOLUTION_AUDIT_ZH.md`：V1 问题到新门禁的映射；
- `PM_V1_5_PROTOCOL_REPAIR_CONTRACT_ZH.md`：当前目标方法合同；
- `PM_V1_5_CORE_CHAIN_PLAN_ZH.md`：唯一活跃执行顺序、阶段状态与并行计划；不另建问题编号；
- `PM_V1_5_REVIEW_ARTIFACT_INDEX.json`：当前审查 artifact 摘要；
- `outputs/pm_v1_5_paid_run_release.json`：逐阶段付费执行 manifest；
- `release_preflight.json`：工程 preflight，不等于 confirmatory readiness。

外部复审材料对应 PR #3 `7ea2248`、PR #4 `b2333ac`、`c5c38b6`、`8910f4d` 等审查节点；
原始聊天附件只作本地审计证据，不属于可复现运行输入。

维护规则：

1. 新发现必须添加新 ID，不能静默改写旧问题的历史状态；
2. 只有同时具备代码门、测试和实际 attested run evidence 时，才可从
   `CODE_CLOSED_RUN_UNVERIFIED` 改成实证 PASS；
3. 修复导致新的方法身份、成本或调用架构时，必须同时新增“二阶风险”记录；
4. 任何 `PASS/APPROVED/SUPPORTED` 状态变化都要写明唯一 artifact 和内容哈希；
5. 探索性或失败 run 不删除，且不得把其中有利子集重新包装成确认性结果。
6. 其他文档发现新问题时，只链接本文 ID，不复制一套状态表；若出现第二份活跃 ledger，
   先合并其唯一信息，再将其改成只读跳转页或删除，禁止长期双写。
