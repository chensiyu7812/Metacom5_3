# B5 状态（2026-11-17）：已接入 C0 0.2.0 候选；真实 bank-v0 回放尚缺

- 证据等级：engineering_only；无模型、GPU 或付费调用
- **完成情况必须分开说：**

| 层级 | 状态 | 证据 |
|---|---|---|
| 环境核心（与契约无关） | 完成 | `env/finite_head.py`；`test_rl1v3_b5_env_core.py` 17 项。DP 与 300 张随机表、200 张带容量约束的表的暴力枚举一致；按 DP 策略执行能达到 DP 值；回放确定；非法动作抛错且状态不变；缺失终点报 `PendingTerminal` |
| 接入 C0 0.2.0（mock bank） | 完成 | `env/c0_binding.py`；`test_rl1v3_b5_c0_binding.py` 11 项，在与 ws-a `8aab9f25` 的试合并树上通过。Observation 即 C0 Observation；STOP 时用完整版本化 TerminalKey 的 sha256 查表；65 条实际顺序对应 16 个规范键；ExecutionTrace 保留实际顺序并通过 `verify_key`；更换 G 或前缀都不会复用奖励；ReadFailure 抛 `ReadRejected` 且状态不变；Phase-2 的 `EXPAND_MS(j)` 在本域非法 |
| 在合成任务上真实训练 | 完成（工程预检） | 见 `../B8e_preflight/RESULTS_ZH.md`。所有回合都经由 `env.step` 执行 |
| **真实 bank-v0 回放集成测试** | **尚缺** | 依赖 WS-A A1b 交付 bank-v0 和 `retrieve.read`（返回 ReadSuccess/ReadFailure）以及检索 manifest。mock bank 的结果不能代替真实 bank |
| 正式冻结 | 尚缺 | C0 0.2.0 需由集成负责人合入并通过 CI 后才算冻结 |

- GET 只调用注入的读取器（WS-A `read`），不调用 G/J；只有 STOP 查表。
- 下一步：A1b 可调用后，选 1–2 个真实 B0 前缀，构造 16 个子集的真实阅读单元，并用 `ExecutionTrace` 回放写入集成测试，同时确认读取器的 tokens、容量和 family 闭包。
