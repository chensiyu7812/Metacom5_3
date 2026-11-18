# Paper 1 当前研究交接与责任矩阵

日期：2026-08-13  
发布状态：`CURRENT CLEAN PUBLICATION / ZERO API / NO LIVE EXECUTION AUTHORITY`

本目录是当前有效研究方案的干净交接面，不是实验失败档案。它从
`chensiyu7812/Metacom5_3:main` 建立，只加入当前仍有效的架构、测量、baseline、
外测设计、主张边界和必要实现；历史失败输出、失败人评、private packet、旧
execution/closeout 及尚未完成的 MP 草稿均未加入本次发布。

## 当前唯一结论

当前先完成 `SELECTIVE_RS_PLUS_MS_PM`：冻结 Llama 3.1 8B，保持完整 R0 基座，
只把 RS 与 MS 作为可选增量加入。Function 使用可观察贡献证据，不要求评审者
猜测模型隐藏推理，也不再由少量二元标签单独否决第一版 PM。

完整 Paper 1 条件仍不变：

`RS_pass AND count_pass(MP,MS,ME) >= 2`

因此 RS+MS 闭环是有意义的第一阶段成果，但不是完整 Paper 1 的最终通过。

## 责任矩阵

| 对象 | 负责证明什么 | 不负责什么 | 当前退出条件 |
|---|---|---|---|
| R0 foundation | current-turn grounding、安全边界、完整回复、适当 forward move | 不为任何 head 提供搭便车质量提升 | 所有 factorial arms 逐字共享同一 R0 |
| RS | 选择性策略增量是否在合适状态改善支持性回复 | 不承担纵向记忆 QA | ESConv + EvoEmo 上整体 Quality/Risk 不劣，learned-ON slice 有正增量，并胜过规则、随机和静态控制 |
| MS | 严格过去、同 owner 的 session memory 是否被安全使用、询问或忽略 | 不要求从单条回复恢复隐藏因果推理 | EvoEmo 有可复现的可观察贡献且无 critical misuse；ES-MemEval 相对 no-memory 提升、相对 fixed-high 降成本且准确率/风险不劣 |
| Function | 记录结构实现与 source-supported 可观察贡献 | 不能替代 Quality/Risk，也不能把 telemetry 当 gold | CLEAR/PLAUSIBLE/NONE/UNCERTAIN 盲评；clear-use slice 非全 NONE；hard-ignore controls 安全 |
| Quality/Risk | 决定同栈回复是否有用且安全 | 不负责证明 memory 的隐藏做功路径 | same-state blind comparison；absolute material-risk guardrail；按 owner/dialogue 正确聚类 |
| Cost | 证明选择性路由相对 fixed-high/always-on 节约资源 | 不能用低成本掩盖质量或风险退化 | token、retrieval、latency、USD 全部确定性核算，并通过 cost-matched 比较 |
| Baselines | 排除“少开就行”“随机开也行”“规则足够”“固定高配足够”等替代解释 | oracle 不作为可部署系统 | always-off、fixed-high、transparent-rule、cost-matched-fixed、cost-and-ON-rate-matched-random、16-action oracle 按合同分别比较 |
| Generator | 当前作为冻结环境验证 treatment | 当前阶段不比较更强 generator | 当前 treatment 成功后再做 generator moderator/robustness 研究，且 generator/judge 不同源 |
| MP/ME | 未来补足完整 Paper 1 的第二个 memory head | 当前不得抢占 RS/MS Panel V2 或冒充已完成 | RS/MS 外测闭环后另行冻结设计；加入最终系统时补跑受影响的最终系统比较 |

## 三项外测分工

1. ESConv：只关闭 RS/R0 响应主张；MS/MP/ME 结构性不适用。
2. EvoEmo：关闭 RS、MS 单独与联合的响应 factorial、Function、Quality、Risk 和 Cost。
3. ES-MemEval：关闭 typed-memory QA、temporal/conflict、abstention 与成本；RS 不适用。

三个 track 互补，不跨任务池化 effect，也不要求每个 head 在不适用的数据集上通过。

## 当前执行顺序

1. 零 API 重建 Function Observability / Four-Arm Panel V2。
2. 至少覆盖 4 个 CLEAR_USE owner、2 个 ASK owner、4 个 IGNORE owner，以及 wrong-owner、stale/conflict、echo、低信息和主题错配控制。
3. 至少 12 个状态拥有完整四臂；机器审计 owner、source、strata、hash 与调用上限。
4. 审计通过后再提交一个精确 run identity 和不超过 64 次调用的成本上限。
5. 当前不授权 generator、judge、fit 或 external call。

## 版本边界

- 方法：`PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2`，不变。
- compiler：`R0_DELTA_COMPILER_V4_0`。
- measurement：`FUNCTION_OBSERVABILITY_V2`。
- panel：`FOUR_ARM_PANEL_V2`，待重建。
- 当前 generator：`meta/llama-3.1-8b-instruct`，冻结。

机器可读发布范围见
`data/pm_v1_5_contracts/paper1_clean_publication_manifest_v1.json`。

