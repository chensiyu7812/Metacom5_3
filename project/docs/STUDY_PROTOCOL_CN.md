# 冻结研究协议

## 研究对象

PM 是固定生成器之外的监督式检索前资源路由器。输入仅包括当前用户文本、当前 session 上下文、资源可用性/数量/年龄、查询到来前缓存的 source catalog fingerprint 与动作成本。PM 不读取实际 memory/strategy snippets、检索分数、gold、role card、未来会话、回复或 judge 分数。

## 动作

八种记忆 mask：M0、MP、MS、ME、MPMS、MPE、MSE、MPMSME；两种策略动作：R0、RS。部署时只检索最终选择动作所需资源。

## 数据

- Synthetic：训练、交叉验证、judge 校准和机制分析。
- ESConv train：构建 Strategy RAG；validation：冻结检索参数；test：回复质量与 R0/RS 路由确认性评测。
- EvoEmo/ES-MemEval：全部 18 用户和 34 个 dialogue-generation scenarios，仅作外部长期记忆评测。

## 标签

- Response：同卡盲 A/B/tie。
- Response measurement 使用 `docs/MEASUREMENT_PROTOCOL_V3.md`：training-eligible pairs 采用 dual-order debiasing，不一致解析为 tie；pilot gate 使用分层 controls 与 debias 后 effective response signal；response quality 是非劣约束而非默认 superiority claim。
- M1：独立 memory opportunity audit。
- M2：独立 realized memory-use audit，不看 M1 评分或 Strategy。
- M0：单独 omission audit。
- Strategy：RS 相关性/利用/过度结构化诊断；主要 RS 效果来自同 memory 条件下 R0/RS 盲比较。

## 训练与决策

训练 pairwise response ranker，以及有界 memory-misuse/decision 辅助头。每张卡的 pair/action 总权重归一。部署时先保留 response score 在最佳值 epsilon 内且 misuse 不高于 tau 的动作，再选择预计成本最低者。

## 成功标准

A：回复质量优于 strongest baseline，misuse 不更差；或 B：回复质量非劣且成本更低或 memory/strategy 风险更低，misuse 不更差。Response 非劣主指标为 blind pairwise NetWin 的 95% CI 下界 `> -0.05`。不得使用混合 headline utility，也不得以弱规则作为唯一 baseline。

## 结论边界

不得声称临床安全、distress 降低、POMDP/RL、多模态、端到端生成优化、直接优于 D2RCU/RLFF-ESC，或在未运行全部三轨任务时声称完整通过 ES-MemEval。
