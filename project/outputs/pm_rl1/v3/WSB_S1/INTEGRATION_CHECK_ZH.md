# WS-B 下一阶段起点：集成版本核验（2026-11-17）

- 证据等级：engineering_only；只做 CPU 检查，没有模型、GPU 或付费调用
- 新工作分支：`pmrl1-v3/ws-b-s1`，从 `pmrl1-v3/integration` 的 `d0bde000` 新建。没有重建或覆盖 `pmrl1-v3/ws-b`（仍停在 `f0777042`）
- **C0 状态**：已合入，但**未冻结**。集成负责人在 `d0bde000` 记录了失败：一项 CI 保护测试失败，原因是新 V3 CI 命令缺少 `-m "not gpu"`，修复归集成负责人。因此本分支依赖的是**候选** `pmrl1v3-contracts-0.2.0`，不是冻结版

## 核验结果（在 `d0bde000` 上自行复跑）

| 检查项 | 结果 |
|---|---|
| B 正式验收测试 `test_rl1v3_c0_wsb_acceptance.py` 保留 | 与 B 原提交 `2ccad7be` 的 git blob 相同 |
| B5 代码（`finite_head.py`、`c0_binding.py`）与测试 | 与 `2ccad7be` 相同。仍使用完整 TerminalKey（`for_prefix` 加规范顺序）和真实 ExecutionTrace（`verify_key`） |
| 读取失败与 PendingTerminal 语义 | 未改：ReadFailure 会抛 `ReadRejected` 且状态不变；缺失终点抛 `PendingTerminal`，不计 0 分 |
| B0 代码 | `census.py`、`exposure.py` 与 `2ccad7be` 相同 |
| B0 输出与 manifest | 4 个输出文件的 SHA256 与 `B0/manifest.json` 一致：`prefix_census.jsonl`、`folds.json`、`exposure_registry.jsonl`、`census_summary.json` |
| 全部 V3 测试（`-m "not gpu"`，xfail_strict） | 287 通过，0 失败，0 跳过，0 xfail；`verify_v3_junit.py` 门禁通过 |

## 本阶段对 B5 的唯一改动（向后兼容）

- `FiniteHeadEnv` 新增 `reader_takes_tokens`，`C0FiniteHeadEnv` 新增 `read_takes_tokens`，两者默认都关闭，原有 17 项和 10 项 B5 测试不受影响。
- 打开后，GET 调用的是 `read(head, input_tokens_before=n)`，用于对接 A1b 真实读取（读取要按当前已用 token 计算容量）：
  - 回包中的 `input_tokens_before` 必须等于 `n`，否则抛 `ReadRejected`，状态不变；
  - 状态按实际计费 `input_tokens_after - n` 累加。

## 计数更正

- 上轮报告把 B5 绑定测试写成"11 项"，实际是 **10 项**（集成负责人已指出）。断言本身没有改。
