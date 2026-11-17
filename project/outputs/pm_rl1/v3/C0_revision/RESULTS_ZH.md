# C0 修订实际结果（0.2.0，待 WS-B 复审）

R1–R6 已实现，N1–N7 逐项处置，另处理 PR 评论 N8；接口与迁移见 INTERFACE_ZH.md。未修改 B 业务目录、全局状态、H0 或旧实验产物。

- 定向 CPU：185 passed / 0 failed / 0 skipped / 0 xfailed（targeted.xml/log），包含 B 的 7 项保证、6 项必改验收及 4,119 条 B0 前缀身份核验。
- 终点枚举：65 条实际轨迹 → 恰好 16 个有限域键；轨迹仍为 65 个不同身份。跨 owner、bank/index/renderer/step2/G/decode/context/domain 隔离；检查表固定分母、判官分歧、pending、跨度与家族闭包、读取容量/失败类型、原子登记均有实际拒绝测试。
- 回放：31 正例接受、33 反例拒绝；fixtures.json/replayed.json 及 manifest SHA 可检查。
- 首轮适配测试 145 passed，增加行为覆盖后 183 passed，最终 185 passed。无失败被跳过或降格。compileall、git diff --check、integration base/outcome locks 检查通过。
- CPU 全量回归正在独立进程运行；完成后追加单独记录和 XML/log，不能将前轮 1,950 项结果冒充本轮结果。PR CI 同样须按本轮实际提交 SHA 核查。
- 无 GPU/真实生成/训练/付费调用。本轮任何模型吞吐、生成质量、检索召回和资源效益均未测。

旧 0.1.0 身份不兼容，显式拒绝加载；旧 Schema 原样保留在 v0.1.0 子目录，历史结果使用旧 commit 回放。本轮候选仍未冻结，须 B 复审和集成负责人合入后再交付 A1b bank-v0/read 实现。A1 旧资产审计可依用户本轮要求先行，不把它声称为已完成来源库迁移。
