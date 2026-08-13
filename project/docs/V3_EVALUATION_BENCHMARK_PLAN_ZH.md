# MetaCom V3 Evaluation Benchmark Plan

日期：2026-08-13
状态：`DRAFTED FOR V3-P0 FREEZE / NO API AUTHORITY`

机器合同：`data/v3_authority/v3_evaluation_freeze_contract_v1.json`

## 当前冻结裁定

整体状态为 `P0_NOT_COMPLETE_BLOCKS_HEAD_TUNING_AND_FORMAL_JUDGING`。这意味着目前的42/90 stress-test回复可以保留，冻结的48次 continuation 也可以在条件满足并重新批准后补齐，但不能继续按旧 Quality/Function 口径做最终判决，更不能从不完整 arm 或自建总分宣布 head pass/fail。

当前阻塞项是：ES-MemEval 1,209/1,427 的逐题身份、ESC-RANK 本地校准、same-stack reference、ESC-Judge position sensitivity、人类 anchor、ESC-Eval 与 ESConv/ExTES 重叠筛查、Quality/Risk NI margin 来源，以及 Risk 双评/裁决和不确定性上界。

## 考卷与主张映射

| 考卷 | 主张 | 主指标 | 单位 | 不允许的外推 |
|---|---|---|---|---|
| ESC-Eval | generator 的多轮 ESC 基础能力 | 官方七维、Average、完成率 | role card / dialogue | PM价值、临床效果 |
| ESC-Judge | generator 相对 reference 的 E-I-A 支持策略 | Exploration/Insight/Action pairwise | synthetic role | 绝对及格分、真实用户效果 |
| ES-MemEval | 长期记忆能力 | retrieval、Token F1、BERTScore、conflict、abstention、false answer | user | RS价值、独立于EvoEmo的新用户复现 |
| ESConv | RS/R0 单会话 PM | blind pairwise Quality、atomic Risk、Cost、selection | dialogue | 纵向 memory |
| EvoEmo response | RS/MP/MS/ME 与 joint policy | same-state Quality/Risk/Cost、marginal、interaction | 18 users | 204+ states 视为独立样本 |
| Atomic Risk Audit | 个性化完整性 | 8类事件 + uncertain | reply/exposure/owner | 完整临床安全 |

## 冻结前必须完成

1. 每个 benchmark 的官方仓库、tag/commit、许可证、文件 hash、样本数和语言；
2. role/user/dialogue/question 的统计单位与 cluster rule；
3. train/dev/test 与已使用开发数据的 source、dialogue、semantic overlap；
4. scorer/judge 的模型身份、prompt、版本、seed、turn cap、retry 和失败处理；
5. reference model 及同栈复跑，或无法复跑时的明确不可比边界；
6. noninferiority margin 的来源和 sensitivity；
7. primary/secondary outcomes 与 multiple-comparison 处理；
8. deterministic input/output token、latency、retry、USD 成本账本；
9. hard safety/integrity event 与 `UNCERTAIN` 的处理；
10. benchmark 运行只能决定是否通过，不能反向修改 selector、sample 或 treatment。

## ESC-Eval 资格方案

- 主运行必须保持官方 role cards、交互方式和七维完整报告；
- ESC-RANK 在本地需要用公开人工标注进行校准，若不能复现则 scorer 状态为 `UNQUALIFIED`；
- published Llama3-8B/ChatGPT/ESC-specialized 分数只作背景，不能与不同代码、模型版本和 prompt 的新分数直接作正式 NI；
- 至少一个 reference 在同一 V3 stack 中复跑；
- pass 用 cluster interval 与冻结 NI margin；
- low-burden guardrail 单独审计，防止建议数量奖励制造“高分但不合适”的系统。

## ESC-Judge 稳健性方案

- 以同一 synthetic role 分别运行 candidate 与 reference；
- 保持对称顺序或随机化顺序，报告 position sensitivity；
- Exploration、Insight、Action 分别报告，不用单一 Average 掩盖阶段差异；
- judge family 与 generator family 尽量分离，并保留一小批人工 anchor；
- 只作 robustness，不代替 ESC-Eval 绝对定位。

官方论文的实验边界也必须保留：25个合成角色、375个对话三元组、o1-mini judge；人工一致性只在随机抽取的100对、两位博士级标注者上验证。论文报告的85%/83%/86%是该设置下 Exploration/Insight/Action 的匹配率，不是跨 judge、跨语言或真实用户的通用可靠性保证。

## PM 自定义专项考卷

- 同一个 current context、candidate pool、retrieval、R0、generator、seed policy 和输出预算；
- 只改变资源选择或一个 component delta；
- Quality 用 state-specific checklist 的匿名 pairwise；
- Risk 用 source-aware atomic event；
- Function 看 current context、授权 source 与匿名回复，作为 mechanism evidence；
- Cost 使用实际 generator input/output tokens，并分开报告 retrieval/retry/latency/USD；
- 所有统计按 dialogue/user 聚类，重复 state/seed 只增加簇内精度。

## 通过线冻结原则

- 绝对分数与相对 reference 同时报告；
- margin 不能从正式结果倒推；
- 小开发 slice 允许方向性晋级，正式结论必须给 cluster uncertainty；
- critical integrity event 不被平均分掩盖；
- Function 非零、可归因、可复现，但不要求每次 ON 都有清晰可见的措辞；
- 任何无法验证的比较标 `INCONCLUSIVE`，不能强制判为 pass/fail。

当前唯一已有数值底线是相对 fixed-high 的实际 generator input tokens 至少降低10%；它仍不能抵消 Quality/Risk 恶化。其余 generator 与 Quality/Risk NI margin 不能从正式 outcome 反推，必须由公开人工标签上的 scorer calibration、same-stack reference 变异和 outcome-blind practical-effect 论证共同确定。
