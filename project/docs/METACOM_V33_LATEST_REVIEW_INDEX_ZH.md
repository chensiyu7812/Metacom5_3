# MetaCom V3.3 最新结果入口索引

更新时间：2026-07-14

这份索引用于快速定位当前论文收口阶段最重要的结果口径，尤其是 Figure 2、Discussion 和 Limitations。

## 推荐阅读顺序

1. `project/docs/METACOM_V33_FIGURE2_REVISION_BRIEF_ZH.md`
   - 用于重画 Figure 2。
   - 核心：不要把 PM 画成已经解决最优资源选择，而是画成 pre-retrieval source-level router 原型。
   - 关键表述：强 LLM 生成器下，瓶颈从基础支持性生成转向外部资源校准。

2. `project/docs/METACOM_V33_FINAL_TABLES_UPDATED_ZH.md`
   - 用于论文主表和结果边界。
   - 包含 Table 4C cost-matched fixed-action diagnostic 与 Table 4D forced-swap blind probe。

3. `project/docs/METACOM_V33_COST_MATCHED_BASELINE_DIAGNOSTIC_ZH.md`
   - 用于详细解释 `ME+R0` 同预算固定动作为什么重要，以及它如何改变 PM 结论边界。
   - 包含 V4 pointwise scoring 和 forced-swap probe 的完整结果。

4. `project/scripts/17s_eval_cost_matched_forced_swap_probe.py`
   - forced-swap blind probe 的复现脚本。

## 当前最稳结论

当前结果不支持“监督式 PM 已经优于同预算固定路由”。但这不等于研究问题失败。更准确的结论是：

> 长期情感支持中的外部资源调用确实需要被建模为检索前资源分配问题；但在强 LLM 生成器条件下，真正困难的部分不是简单增加记忆或策略，而是校准何时不用、何时少用、何时使用哪类资源。

## Figure 2 应避免的误读

不要画成：

- PM 已经稳定优于 same-budget fixed routing；
- PM 已经学会 fine-grained memory relevance；
- 策略卡片开关已经被 PM 精细校准；
- 更多记忆一定更好。

应该画成：

- 当前 PM 是 source-level router；
- 动作空间包含 `M0+R0`，但当前外部选择校准不足；
- Context Only、Raw Session Top-4、ME+R0 都是强 baseline；
- 这些结果共同说明资源调用需要 abstention、strategy-off calibration 和 item-level filtering。
