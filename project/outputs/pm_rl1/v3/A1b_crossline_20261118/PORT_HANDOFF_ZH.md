# A1/A1b 端口交付（CPU）

原准备提交已通过本地安全引用保全，见 PREPARATION_PRESERVATION.json；A1 → A1b 父子关系及原 manifest SHA 均保留。现有 PR #8 基于冻结后的 integration 8bcd326e，正式移入提交为 7116b8bd、c9dd5aae。不重建、不覆盖准备资产。

稳定入口为 `metacom_pm.rl1v3.bank.v0_port.make_port_factory(root=repo)`。它只加载固定 source/bank/index 及本地 tokenizer，不加载模型权重。`factory.prefix(B0_row)` 校验前缀身份；`factory(prefix)` 返回 PrefixPort；`factory()` 返回按 prefix 路由的兼容端口。

PrefixPort 提供 `legal_sessions()`、`availability()`、`read(head, acquired=(), input_tokens_before=...)`、`unit_tokens(...)`、`records(ids)`、`verify_records(ids)`、`terminal_key(results)`、`execution_trace(results)`、`replay(key)`。非根 GET 必须传入真实成功 ReadingView 序列，不能用累计 token 数猜测轨迹。版本、伪造读取、容量及空候选失败均有类型化结果，失败不取得 ReadingView 或读取序号。`source()` 是私有审计端口，不是运行时历史输出。

`token_account(acquired)` 同时给出原生完整 prompt 的实际 token 数与 C0 保守计费。后者取 max(上一账单 + 本次阅读原生 token 数, 原生完整 prompt token 数)，为保持既有回放身份沿用 v0 规则。`measure()` 是私有计划：可测量超容量单位，但不是成功读取。

代码测试使用明确标为测试专用的 tokenizer；PORT_NATIVE_SMOKE.json 使用固定 Gemma tokenizer，仅 CPU 分词。跨线 B5 工具和最终 CI 证据另行记录，不能以本文件代替 B 验收。
