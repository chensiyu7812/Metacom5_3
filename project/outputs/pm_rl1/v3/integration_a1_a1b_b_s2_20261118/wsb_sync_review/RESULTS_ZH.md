# WS-B S2：同步已集成 A1/A1b 的真实验收（2026-11-18）

已在原 pmrl1-v3/ws-b-s2 分支普通 merge integration 的 PR #8 合入提交 b591863e4439014872dd076c72b20b99983a52e4。同步及最终 PR #9 HEAD 为 59607355b3751c87138b129a079eeb571152b7ce；双亲为 c089fce5 与 b591863e，未 force、未改业务、未自行合并 PR #9。工作区前后干净，未触碰外部 B 未提交工作。

相对 integration 只有 46 个 B-owned 代码/测试/脚本/配置/输出文件。A 资产与业务、C0 contracts/io、32 Schema、AGENTS、workflow、全局 EXECUTION_STATE 均无重复改动。34 个冻结共享文件及 B 正式 C0 验收文件逐 SHA 一致；输入和 B 文件运行前后哈希一致。

| 本次实际检查 | 结果 |
|---|---|
| 本地严格 V3 + JUnit 门禁 | 466 passed，0 fail/error/skip/xfail |
| Schema | 32 checked |
| 来源 cross_check | 401 会话、4119 前缀，内容/前缀差异 0 |
| NeedCard CPU 输入预检 | 20/20 ready，3739–27009 tokens，无截断，未调用 writer |
| B5 真实 A 端口回放 | 24/24 通过；21×16 子集、3×8（MP 无合法候选）；360 个终点、1413 顺序 |
| 独立重载、容量压力、失败状态保持 | 各 24/24；21 条 ready_at==cutoff 边界合法 |
| 与旧 173bed 回放比较 | 24/24 identity/key/reachability/input-token 等比较字段一致 |
| 最终 HEAD PR CI | V3 466 passed / 0 skip/xfail；完整 CPU 2231 passed / 63 历史 skip / 0 fail；integration-base success |

最终 HEAD [CI 44185528503](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44185528503) success。原始 run/jobs/logs、GitHub artifact ZIP、JUnit、逐项 skip 和 ATTESTATION 位于 ci/。ZIP SHA256=86efb4248a8c1982dbe6950ef6a4093b8d1cc4546fadab0eb7133b5c4261782e；远端与本地 V3 testcase ID 集合一致。历史 skip 单独列出，不视作完整覆盖。完整 CPU 在本轮由实际 PR CI 执行，未冒称本轮又跑了本地完整 CPU。

所有模型、Generator、Judge、GPU、训练实验、付费调用均为 0；仅已有 CPU fixture 测试与原生 tokenizer 计数。没有生成 NeedCard，不升级 B1/B2/B6e 状态。

注意 B 原脚本的 formal_on_integration 字段仅检查 A1/A1b 的 ancestor，实际测试代码仍是 WS-B 同步提交 59607355b3751c87138b129a079eeb571152b7ce，不能替代 PR #9 合入后 integration HEAD 的正式重验。本轮只提供合入前工程验收；最终合入和状态更新由集成负责人串行完成。无新冲突或测试失败，无自主修复。
