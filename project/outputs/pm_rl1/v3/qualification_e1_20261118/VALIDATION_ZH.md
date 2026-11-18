# CPU 验证与证据范围

| 范围 | passed | failed/error | skip | GPU 排除 |
|---|---:|---:|---:|---:|
| 完整 CPU（Paper-1 + RL1 + V3） | 2422 | 0 | 1 | 11 |
| 最终 V3 严格套件 | 589 | 0 | 0 | 0 |
| 本轮专项最终复验 | 9 | 0 | 0 | 0 |

完整 CPU 耗时 565.14 秒；V3 106.64 秒，严格 JUnit gate 通过。唯一 skip 为历史冻结 Llama tokenizer 不存在于 `/home/chenzhi/paper1_runs/frozen_tokenizers/llama31_8b_instruct_tokenizer.json`；没有把跳过计作覆盖。环境变量禁止 CUDA/模型联网。既有优化器 fixture 单元测试不是研究 SFT/PPO，没有研究检查点。

69 个干净重跑文件（包括新 native token IDs）逐字一致；16 snapshot hash 独立标准库复算通过；8 对持久化快照分别重新做 native RAW 读取后结果一致；来源/owner/span、固定前缀、body 逐条重建与私有字段检查通过。参考检查器由 A 编写，不替代 B 独立签收。

原 346 个关键受保护文件逐字节一致；base 已有文件没有修改，新 PR 只有新增。原 65 snapshot、旧 bank-v0 / 324 MP、54 固定输入、五项 pending 和 C0/全局状态保持。integration-base/outcome-lock 检查 PASS。

失败/限制：初次独立 synthetic source 构造漏填必需 source_split，在机制执行前报 ValidationError，修为 unassigned 后重跑通过；该错误说明保存在 DEVELOPMENT_AND_FAILURES.json，未伪称为真实 RAW 失败。cpu_v1/v2 是生成前表示迭代，原文件保留共享 validation 目录；最终 cpu_v3 不覆盖它们。语义隔离 21 条、SUM 不可用 8 条、p3 MP 无候选 1 条，以及真实更正链资格不足均保留。

原始成功日志、JUnit、gate、standalone 收据见 validation/；完整 SHA、代码内容身份和环境见 VALIDATION_RECEIPT.json。最终 Git commit SHA 与远端 HEAD CI 绑定写在 PR，不在本文件中循环引用自己的 commit。若 CI 有环境 skip，将另在 PR 中报告其实际数量和理由，不能复用本地数量冒充 CI。

本轮没有 GPU、Generator、Judge、研究训练或付费 API，也没有 PR 合并。
