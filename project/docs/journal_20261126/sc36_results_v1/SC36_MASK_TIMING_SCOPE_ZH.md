# SC36 原始 mask 计时字段的解释

保留冻结 worker 的原始 `constraint_measurement.cpu_mask_seconds` 字段及数值；计量脚本中的 `grammar_cpu_mask_seconds` / `grammar_mask_cpu_seconds` 是其逐请求值及累加值。字段名不代表已经隔离出纯 CPU matcher 开销。

`StructuredConstrainedProcessor.__call__` 在开始计时后调用 `int(input_ids[0,-1])`。实际运行时 `input_ids` 位于 GPU，这一步可能包含上一 token 的 GPU→CPU 取值及流同步等待。因此，该字段测量的是 **processor 内部这段代码的墙钟时间**，其中有 CPU matcher/bitmask 工作，也可能有 GPU 同步等待。

计时在最后的 `allowed.to(scores.device)` 和 `masked_fill` 之前结束，故不包含这两步。它已包含于完整 `generation_seconds`，不能再次相加，也不能独立解释为“新增 CPU 延迟”或约束解码相对旧运行的因果开销。旧 S 与新 SC 的逐请求 generation/job 时间差另行报告，仍受输出长度及运行差异影响。

此前 CPU 兼容检查在 CPU tensor 上进行，其计时不包含这次 GPU 同步情形，不能直接替代实际 GPU 路径的计量。本说明只校正计时解释；没有修改冻结 worker、plan、decode、评分器、输出或原始计时，也没有触发任何模型、GPU 或兼容性重跑。
