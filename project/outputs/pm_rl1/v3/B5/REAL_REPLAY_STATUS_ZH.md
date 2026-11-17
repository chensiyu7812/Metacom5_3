# B5 真实 bank-v0 回放：工具就绪，等待 A1b（2026-11-17）

- 证据等级：engineering_only
- **真实回放结果：无。** integration `d0bde000` 上 A1 和 A1b 都还是 pending，没有可导入的 `bank_v0` 或 `retrieve.read`
- `scripts/rl1v3/B5_real_replay.py` 实际运行后退出码为 3，状态为 blocked：两个候选模块都不存在，没有写出任何结果
- 本轮没有用 mock 或 fixture 冒充真实 bank 结果
- 原 `PREP_STATUS_ZH.md` 保持不变（其中"11 项"应为 10 项，见 `../WSB_S1/INTEGRATION_CHECK_ZH.md`）

## 回放工具：`env/bank_replay.py`（协议 `pmrl1v3-b5-bank-replay-v1`）

对固定覆盖样本中的每个前缀，经由 C0FiniteHeadEnv 执行。**环境始终遵守动作掩码，从不越过它。**

| 用户要求 | 实现 |
|---|---|
| 1 固定覆盖样本 | `B1/coverage_sample_v1.jsonl`，24 个前缀，每折 4 个 |
| 2 逐头真实 GET | 从初始状态对每个头 GET 一次；同时核对 availability 与读取结果是否一致（availability 非空但读取返回 empty，计为失败） |
| 3 核对来源、owner、时间、family、token、record 绑定 | 对每条交付的 record：<br>• bank 版本、所属头；<br>• owner（RS 必须没有 owner）；<br>• reported_at 和 ready_at 必须严格早于当前会话，且日期不晚于前缀时间；<br>• 每个来源跨度都过 `verify_legal_span`；<br>• family：个人资源必须在前缀的 family 闭包内，RS 必须与之不相交（T24）；<br>• 计费 token 必须等于掩码用的单元大小，`input_tokens_before` 必须与状态一致 |
| 4 完整 TerminalKey | `TerminalKey.for_prefix` 包含 bank、index、renderer、Step-2、G、decode 的版本身份。G0 尚未冻结，配置中这几项显式写为 `unbound-*` |
| 5 读取顺序只改变 ExecutionTrace | 同一子集的所有合法读取顺序必须只得到 1 个 key；不同顺序的 ExecutionTrace 个数必须等于 k! |
| 6 缺失终点为 pending | 终点表为空时，每个可达子集 STOP 都抛 PendingTerminal；表中只放 OFF 时，只有 OFF 有奖励 |
| 7 同版本读取与回放完全一致 | 新建一个 port 重新运行，比较 record id、正文哈希、token 和 key |
| 可达终点数 | 如实报告 `n_reachable`（可能少于 16）；不可达的头写明原因：empty_pool、读取被拒的原因，或从初始状态起就因容量被屏蔽 |
| 容量 | 被容量屏蔽的头会单独探测一次，确认读取器确实返回 `capacity`；探测结果**不进入**环境状态 |

**用手写 fixture port 测试**（`tests/test_rl1v3_b5_bank_replay.py`，11 项）：

- 正常 port：16 个终点、65 条顺序、16 个不同的 key，两次回放完全一致；
- 加容量限制：11 个终点；
- 空头：8 个终点；
- 以下每类故障都被检出：
  - 外部 owner；
  - 来源晚于切点；
  - RS 的 family 与前缀谱系重叠；
  - 掩码单元大小与实际计费不符；
  - 两次读取到的 record 不同（回放漂移）；
  - 合法 GET 被读取器拒绝；
  - 读取器的 token 回显与状态不符。

## A1b 交付后的立即步骤

1. 由 A（或集成负责人）提供薄适配层 `make_port_factory(census_sources)`，模块路径写进 `configs/rl1v3/B5_real_replay.yaml`，这样 B 不需要改 A 的检索排序；
2. 运行 `python project/scripts/rl1v3/B5_real_replay.py`，得到 24 个前缀的回放报告、可达终点分布、失败原因和 manifest；
3. 用 A1 的 SourceSession 对 B1 适配器跑 `cross_check`，必须零差异。
