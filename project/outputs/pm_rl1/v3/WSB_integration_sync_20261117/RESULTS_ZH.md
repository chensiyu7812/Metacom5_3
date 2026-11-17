# WS-B 同步真实 integration 后的 C0 复审（2026-11-17）

结论：**本次同步与 C0 复审通过，可由集成负责人将 PR #6 转为可审阅并继续集成。** 本记录不是 C0 正式冻结；完整 CPU 回归和实际 integration 提交上的 GitHub CI 由集成负责人完成。

输入：WS-B 原 HEAD `2ccad7be86ed1fe8a270562fc1a65468147a551c`；PR #5 已实际合入 integration，commit `f63a2e6097c58ae63f6d20eeab2a89d984fb9876`。检查现有 WS-B 工作树干净、远端与本地一致后，以普通 merge 同步，未重建分支、未 force push。

实际同步提交：`bfa45ad3a28a94cdef686e9f0084cfe6b0075dd2`，无冲突。测试针对这一提交运行。

## 文件所有权、接口与旧障碍

- B 正式 `project/tests/test_rl1v3_c0_wsb_acceptance.py` 保持原样，SHA256=`ba9c1e3411ead9604a71c7907b289204be102fd8de6733e1343b7f84e220f6d2`，与 `2ccad7be` 逐字节一致。
- A 的 `test_rl1v3_c0_a_acceptance.py` 独立存在；`tests/fixtures/rl1v3/wsb/census.py.txt` 不存在，没有复制 B0 代码。
- `contracts.py`、`io.py` 和 32 个当前 Schema 与已集成 C0 完全一致，没有再改共享字段。
- 版本：`pmrl1v3-contracts-0.2.0`；canonical JSON=`pmrl1v3-json-1`；B0 prefix protocol=`pmrl1v3-b0-prefix-census-v1`；B5 域=`finite_head_v1`。
- 18 owner、401 会话逐条比较 A/B family 函数，全部一致：ESConv 为 `esconv:esconv_XXXX`，EvoEmo 生成为 `evoemo_owner:pN`；共 102 family，其中 84 个 ESConv seed family。
- 因此旧报告中的 add/add 冲突和 family 命名障碍已经由 A 的 `94ebb80b` 解决，本次只验证，没有重做。仍需实际最终 integration 提交的验收与 CI，不能沿用分支绿灯替代。
- `.gitignore` 和 CI 触发/零 skip guard 由集成负责人在 integration 负责；本次 WS-B 不修改这些文件。

## 实际验收

`project/tests/test_rl1v3_*.py`：**278 passed / 0 failed / 0 errors / 0 skipped / 0 xfailed，17.95 秒**。完整日志与 XML 在同目录，TEST_COUNTS.json 按模块列出真实计数。

其中 B 正式 C0 验收 14 项全部通过；B5 C0 绑定为 **10 项** 全部通过。旧 B 报告曾写成 11 项，本次 XML 与 `2ccad7be` 未改动的源码均为 10 个测试函数。首次结果后处理沿用旧报告的 11 项预期，触发 AssertionError；pytest 本身没有失败。已按源码声明数核对 XML 并记录 COUNT_RECONCILIATION.json，没有修改测试、跳过或弱化任何断言。

R1–R6、观察隔离、全部 4,119 个 B0 前缀身份、固定检查表、pending 终点与 B5 mock-bank 绑定均实际执行。真实 bank-v0/read 仍未交付，不能把 mock 测试声称真实资源回放。

CPU 回归中执行了既有合成 fixture/优化器单元自检；没有另开实验训练脚本，没有预训练语言模型推理、GPU、付费 API。全局 EXECUTION_STATE、H0、研究方案和 main 未改动。B8e-preflight 不因此升级为正式 B8e。
