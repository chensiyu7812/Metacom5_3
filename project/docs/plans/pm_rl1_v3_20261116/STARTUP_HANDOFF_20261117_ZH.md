# PM-RL1 V3.1：Codex A / Codex B 开工交接（2026-11-17）

> **用途**：集成负责人维护的协同说明，不改变研究方案、任务依赖、PR #4 采用规则或现有 Paper-1 冻结资产。以 [V3.1 主方案](../../PM_RL1_SOLUTION_PLAN_V3_20261116_ZH.md)、[四资源技术规范](RESOURCE_SPEC_ZH.md)和 [状态 DAG](EXECUTION_STATE.json) 为最高执行依据。本文件仅记录启动协调。

## 0. GitHub 共同基线

- 仓库：`chensiyu7812/Metacom5_3`。
- 只读检查时：`main=10307c62f5175fcad62558e9e20d4d881b3d9238`。
- 方案 PR：[PR #4](https://github.com/chensiyu7812/Metacom5_3/pull/4)，head=`pmrl1-v3-solution-plan`，所验证 commit=`75689002846996555724307039649c656f3c1e71`；**当时未合并**，不要擅自声明 H0 已完成。此状态可能随 GitHub 后续更新改变，开工时必须重新核对。
- GitHub Actions：在上述 `7568900` 提交上，`PM tests` 的 [run #43861251309](https://github.com/chensiyu7812/Metacom5_3/actions/runs/43861251309) 为 **success**。这仅证明该计划提交的既有 CPU 测试成功，**不代表新代码、bank 或训练已实现/通过**。
- 集成分支：`pmrl1-v3/integration`，从 `7568900` 创建，专供两条工作线合入；不等于 main 合并和研究者 H0 采用。
- **研究者 H0**：仅在研究者明确合并 PR #4 后，由集成负责人另行记录合并 SHA 和 `adopted_by_researcher=true`。即使工程预备分支先施工也不得绕过此规则。

## 1. 分支及互斥文件

| 角色 | 工作分支 | 代码所有权 | 不得动的文件 |
|---|---|---|---|
| Codex A / WS-A | `pmrl1-v3/ws-a`（由 A 自行创建，基于最新可验证的方案提交） | `project/src/metacom_pm/rl1v3/{sources,bank,compile,retrieve,render,generator,g1}/`；共享 `contracts.py` + Schema + `io.py` 的初稿 | B 的业务目录、全局 `EXECUTION_STATE.json`、Paper-1 冻结资产 |
| Codex B / WS-B | `pmrl1-v3/ws-b`（由 B 自行创建，基于同一方案提交） | `project/src/metacom_pm/rl1v3/{prefixes,needs,checklist,judge,latency,env,policies,train,evaluate,external,deploy}/` | A 的业务目录、共享契约的未协调修改、全局 `EXECUTION_STATE.json`、Paper-1 冻结资产 |
| Integration owner | `pmrl1-v3/integration` | 合并冲突、接口登记、状态机串行更新、同步点合入、版本冻结 | 不得冒充 H0/H1 人工签字 |

A、B 的本地分支若已建立，不要重新创建或用远端同名分支强制覆盖。先读 `git status`、HEAD/远端 SHA 和未提交工作，再协调安全合入。

## 2. 两线可以**现在**并行做什么

### A 开工队列

1. **C0（ready）**：统一数据类、Schema、canonical JSON/hash、≥10 正/≥10 负契约测试；完整覆盖 `SourceSpan`、`TemporalClaim`、`TemporalRelation`、`IndexManifest`、`RetrievalTrace`；注意 `invalid_at`（系统得知的失效时间）与 `valid_to`（状态实际有效期）不可混同。
2. **A0（ready）**：CPU 环境盘点、模型可用性/身份和 GPU 资源状态只读查询；真实 A6000 推理、模型下载、吞吐实测和训练须遵守现行 GPU/支出权限，不要替代实测值。
3. C0 经过 B 接口审核并进入共享集成后，**A1 → A1b**：合法原始来源 registry、bank v0 adapter；旧 MP/ME/SUM/RAW/RS 派生不得擅自标为已验证。
4. 后续按 DAG 执行 A2–A6（时序/图/四头检索/真实 BGE dense+BM25/RRF/reading_view/25 测试），再按资格门推进 A7–A11 的 G0/G1。

### B 开工队列

1. **B0（ready）**：owner/family 分组、严格过去切点、合法前缀、曝光登记、自然分布和过采样拆分；交付 `prefix_census.jsonl`、`folds.json`、反例测试。
2. **C0 审阅**：提出 Observation、ReadingView、action mask、TerminalKey 的可执行接口验收。不要复制另一套 `contracts.py`。
3. 在 C0 完成后执行 **B5**：16 终点 Phase-1 GET/STOP 确定性环境 + DP + 观察隔离和非法动作测试。
4. 在 A1b 完成后执行 **B1 → B2**：严格来源 NeedCard、同前缀固定分母 checklist、pass/fail/uncertain 上下界、J1/J2 代理。
5. 依赖满足且计算权限允许时执行 **B6e → B8e**：**engineering_only** 终点表、真实 BC/PPO optimizer 更新、检查点、日志；B3 软质量校准不应无限期阻塞工程，但不具备资格不得作自然帮助主张。
6. 后续 B3/B4、正式 B6–B13 按 DAG 及人评/科研资格展开。

## 3. 第一个交接点：C0

1. A **独立 commit** 共享接口（可提交到其 WS-A 分支）。
2. B 只做契约审阅，列出字段冲突、可见性泄漏和具体测试建议，**不在 WS-B 分支自行抢写 C0**。
3. 集成负责人审查差异与 CI，先将审核后的 C0 合入 `pmrl1-v3/integration`。
4. B 从集成分支获取这一版契约到自己的工作分支，再写 B5；A 同样使用冻结 C0 继续 A1。
5. 若 C0 必须变更 Observation/TerminalKey，需要跨线协调并形成独立 schema-version commit；不得静默改变旧终点的身份。

## 4. 首次 S1 完成定义

须有代码、可重建来源和 bank v0、真实 B0 前缀、同源 NeedCard 与检查项、有限环境和缓存终点、工程 BC/PPO（若 GPU/模型权限未满足则明确记录尚未运行）：

- `C0, A0, A1, A1b, B0, B1, B2, B5, B6e, B8e`；
- 所有工程调用记录 `input_hash / code_sha / model_id / bank_version / index_version / renderer_id / decode_id / terminal_key`；
- 单项 `RESULTS_ZH.md`、manifest、正/负测试、可复现命令与失败修复记录；
- `engineering_only` 不等于 `research_qualified`，更不等于 `human_confirmed`。

**CI 与状态**：所有变更需触发并通过适用 CPU pytest；原有失败必须报告和修复，不能简单禁用测试。双方仅向集成负责人提交任务完成证据；只有集成负责人串行更新 `EXECUTION_STATE.json`。

## 5. 开工时对用户的简短回报格式

- WS-A：`C0=<commit/状态>, A0=<状态>, A1/A1b=<状态>, tests=<通过数/失败数>, blocked=<具体授权/依赖>, next=<任务>`。
- WS-B：`B0=<commit/状态>, C0-review=<结果>, B5=<状态>, B1/B2=<状态>, tests=<通过数/失败数>, blocked=<具体授权/依赖>, next=<任务>`。
- 集成负责人：记录 branch HEAD、代码身份、已合入任务、CI、下一轮 DAG ready 列表；不可凭计划文件推断模型已经训练。

> 当前最重要的交付不是再写一版总方案，而是让 C0、B0、source_registry、bank v0 和受约束的 GET/STOP 环境真正运行；随后继续四头 v1、G1 和 BC/PPO，并使用独立证据判断支持质量。