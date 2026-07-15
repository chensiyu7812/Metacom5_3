# MetaCom V3.3 图 2 修订口径

更新时间：2026-07-14

这份 brief 用于指导论文 Figure 2 的新版绘制。核心目标是避免把当前系统画成“已经解决资源选择的最优 PM”，而是准确表达：

> 在强 LLM 生成器条件下，情感支持系统的瓶颈从基础回复生成转向外部资源校准。当前 Learned PM 是一个 pre-retrieval source-level router 原型，能降低高资源上下文成本，但尚未证明优于强同预算固定动作。

## 1. 图 2 应该传达的主线

建议图 2 表达三层逻辑：

1. **Strong generator baseline**
   - 当前 seeker turn + recent dialogue 已经能让 Llama 3.1 8B Instruct 生成很强的支持性回复；
   - 因此 Context Only 是强 baseline；
   - 这和早期 ESConv / BlenderBot-Joint 系列设置不同：当生成器较弱时，策略或示例增强更容易直接带来质量提升。

2. **Resource calibration problem**
   - 长期陪伴系统仍需要 profile / session summary / event memory / strategy cards；
   - 但资源不是越多越好，All Raw Sessions + Strategy 成本极高且支持评分更低；
   - 关键问题是何时不用、何时少用、何时用哪一类。

3. **Current PM boundary**
   - 动作空间包含 `M0+R0`，即 no memory + no strategy；
   - 当前监督式 PM 在 EvoEmo 上几乎不选择 M0/R0，说明 abstention 与 strategy-off 校准不足；
   - `ME+R0` 同预算固定动作表现强，forced-swap 后仍小幅优于 PM，但多数样本为 tie；
   - 因此 PM-v1 是 source-level routing prototype，不是最终自适应策略。

## 2. 图中建议保留的模块

Figure 2 可以分成 online inference 和 offline learning 两个 panel。

Online panel 建议保留：

- Current dialogue state
- Memory inventory metadata
- Policy Manager
- Selected memory sources and strategy mode
- Retrieval / prompt assembly
- Frozen generator
- Response

Online panel 需要明确写：

```text
PM sees source availability / count / age / estimated token cost, not memory content.
```

Offline panel 建议保留：

- Synthetic development states
- Action sweep over 16 resource actions
- Frozen generator responses
- Blind LLM judges
- Silver utility labels
- Train PM

## 3. 图中不建议表达的内容

不要把图画成：

- PM 已经学会 fine-grained memory relevance；
- PM 已经稳定优于同预算 fixed routing；
- strategy support 被 PM 成功精细开关；
- current PM 是最终 optimal policy。

这些都不是当前结果能支持的。

## 4. 建议图注核心句

英文图注可用：

```text
Overview of the pre-retrieval resource routing framework. A frozen support generator receives the current dialogue plus selected external resources. The Policy Manager selects memory source types and optional strategy support from metadata before retrieval, while the generator remains fixed. Results show that this source-level router reduces high-resource context cost, but same-budget fixed event-memory routing remains a strong baseline, motivating future calibration for abstention, strategy-off decisions, and item-level filtering.
```

中文解释：

> 图 2 不应该讲“PM 已经赢了”，而应该讲“我们把长期情感支持中的外部资源调用建模成检索前路由问题，并展示当前监督式 PM 的能力边界”。

## 5. 可放入论文 Discussion 的总结句

```text
With a stronger instruction-tuned generator, the bottleneck shifts from basic supportive generation to calibrated resource use. Context-only responses are already competitive, full-history context is costly and often unhelpful, and a same-budget event-memory baseline is strong. These results suggest that future long-term emotional-support agents need stronger abstention, strategy-off calibration, and item-level memory filtering rather than simply more retrieved context.
```

对应中文：

> 在强指令模型条件下，系统瓶颈已经从“能否生成支持性回复”转向“是否能校准外部资源调用”。当前上下文回复已经很强，全历史注入成本高且不稳定，同预算事件记忆 baseline 又很强。这说明未来长期情感支持系统需要重点解决 abstention、strategy-off 和细粒度记忆过滤，而不是简单增加上下文。
