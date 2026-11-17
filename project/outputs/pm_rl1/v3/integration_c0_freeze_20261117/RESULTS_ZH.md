# C0 0.2.0 正式工程冻结（2026-11-17）

唯一 CI 配置错误已修复。实际验证的 integration 代码提交为 `b7dd11f674d92384416e0745b9982101965433dc`，冻结接口为 `pmrl1v3-contracts-0.2.0` / `pmrl1v3-json-1`。本记录不修改研究方案、H0 或 main，也不宣布任何模型/生成/训练结果。

## 修复与历史

`.github/workflows/pm-v2-tests.yml` 的独立 V3 pytest 命令增加 `-m "not gpu"`，提交只改一行。原保护测试未修改；契约、A/B 业务代码、32 Schema 和 B 正式验收文件未修改。原失败提交 `d0bde000`、`integration_20261117/` 原日志及未应用补丁记录完整保留，不能以本结果覆盖旧失败。

## 依次实测

| 检查 | 结果 |
|---|---|
| 原失败单项保护 | 1 passed |
| 全部 V3 + JUnit 严格门禁 | 287 passed；0 skip/xfail/fail |
| 本地完整 CPU：Paper-1 + RL1 + V3 | 2120 passed；1 历史 skip；11 GPU deselected |
| GitHub 实际 integration push | [run 44097686749](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44097686749) success；V3 287 passed；完整 CPU 2052 passed、63 历史 skip、1 GPU deselected |
| 当前 Schema 一致性 | 32 schemas checked |
| integration-base | 本地 PASS；GitHub 步骤实际执行 success，未跳过 |

本地和 CI V3 testcase 身份集合相同；JUnit 和原日志、命令、耗时及逐项 skip 原因均保存。旧环境跳过不算完整覆盖：本地缺历史 Llama tokenizer；GitHub 缺旧 engine/relation 输入 32、engine/task 输入 28、rg 1、sentence_transformers 模块 collection 1、旧 tokenizer collection 1。详情以 `SKIP_REASONS.json` 为准。

## 冻结身份与状态

`C0_FREEZE_MANIFEST.json` 固定实际代码 SHA、34 份共享文件（contracts/io + 32 schemas）、逐文件 SHA、B 正式验收身份、B 审阅 manifest 和 99 项固定输入。共享接口集合 SHA256=`6262fdac86a611a13023736ec38711e2cf894b6af5fe4cde4be18e8f13490d82`。它们与 A 的 `94ebb80b` 相同。B0 前缀协议为 `pmrl1v3-b0-prefix-census-v1`。Phase-1 使用 `finite_head_v1` 的 16 子集身份并保留真实执行轨迹；`adaptive_v1` 为分域接口，不代表 Phase-2 已实现。

全局状态只将 C0 改为 completed；B0 保持 completed，A0/B5 保持 in_progress，A1/A1b 保持 pending。A0 GPU 实测、B1/B2/B6e/B8e 等没有提前完成。`adopted_by_researcher=false` 不变。

冻结记录提交的 SHA 无法写进自身内容；此 manifest 固定已验证的代码提交。该记录提交推送后，必须再核对其最终 HEAD 的实际 push CI，才向 A/B 发布冻结完成通知。最终 CI URL/HEAD 在交接与最终报告中提供，可通过 GitHub commit checks 独立核验。

## 后续集成

先通知 B 同步冻结提交并验收 Draft PR #7，然后接收 A 的独立 A1/A1b 准备提交，从最新 integration 创建正式功能分支/PR。A 的准备产物尚未合入，不能当作 integration 的 source_registry/bank 完成证据。A1/A1b 合入后，再由 B 运行真实 bank 回放并记录接口边界差异。不得把框架测试或历史 Judge/合成 fixture 当作新模型效果证据。

仅运行 CPU 回归，其中包含既有合成 optimizer 单元 fixture；没有独立实验训练、GPU、预训练模型推理或付费 API。完整输入输出 SHA 见 `MANIFEST.json`，重放命令见 `validation/EXECUTION.json`；Schema 与 integration-base 验证在实际 push CI 成功之后执行。
