# WS-B S2 状态（2026-11-18）

- 证据等级：engineering_only
- 本轮运行范围：
  - **没有**：真实生成、GPU 推理、模型调用、判官调用、实验训练、付费调用；
  - **只有**：CPU 计算，以及读取 tokenizer、config 和 template 文件。

## 1. C0 冻结与 PR #7

| 项 | 实际状态（已用 `gh` 和 git 核对） |
|---|---|
| C0 0.2.0 | 正式冻结。代码验收 `b7dd11f6`，冻结记录 `d67f34ee`；冻结记录 HEAD 的 push CI 44100003645 成功 |
| CI 守卫修复 | 集成负责人在 `b7dd11f6` 修复（V3 步骤加 `-m "not gpu"`）。B 没有修改 workflow |
| PR #7 | **已由集成负责人合入**（`8bcd326e`）。合入前，集成负责人把冻结后的 C0 普通 merge 进 ws-b-s1（`dc2e493e`），并复核（`baa6059f`）。PR CI 44104027013 成功（head `baa6059f`），integration push CI 44106386903 成功（head `8bcd326e`） |
| 集成负责人复核中留给 B 的跨线修复 5 项 | 已在本分支完成，见 `B5/REAL_REPLAY_V2_ZH.md` 第 1 节 |

## 2. 分支

- `pmrl1-v3/ws-b-s2` **叠在** WS-A PR #8 的 head `a0771e1e` 上；PR #8 的父提交就是 integration 的 `8bcd326e`。
- 原因：A1/A1b 的 registry、bank、Reader 只在 PR #8 中，B 的真实回放和来源核对必须用它们。
- Draft PR 的 base 设为 `pmrl1-v3/ws-a-a1-bank-v0`，所以 diff 里只有 B 的改动。PR #8 合入后改指 integration，由集成负责人安排。
- 本分支没有修改 C0、WS-A 模块、workflow、`EXECUTION_STATE.json`、H0、main 或 PR #4。

## 3. 本轮产物

| 交付 | 文档 | 状态 |
|---|---|---|
| A1 与 B1 适配器的 cross_check | `B1/NEEDCARD_V2_CPU_PREFLIGHT_ZH.md` §1 | 内容零差异（401 个会话、4,119 个前缀）；集成前运行 |
| 24 个前缀的真实 B5 回放 | `B5/REAL_REPLAY_V2_ZH.md` | 24/24 通过；21 个前缀可达 16 个子集，3 个可达 8 个；集成前运行 |
| RS-v0 目录兼容性 | `B1/NEEDCARD_V2_CPU_PREFLIGHT_ZH.md` §2 | A 没有交付目录；B 机械整理出 8 个历史标签，定义均为 unknown，需要确认 |
| 20 个 NeedCard 试点的 CPU 预算 | 同上 §3 | 20/20 为 ready；prompt 3,739–27,009 token；未截断 |
| NeedCard 授权申请 | 同上 §4 | 已提交，**未运行** |
| I 类与 ER 修改 | `B2/PROTOCOL_V2_ZH.md` | 检查表、判官、ER、评价协议均升级到 v2，v1 保留；`B2/protocols_v2_frozen.json` 已冻结 |
| 档位附录 | `B1/APPENDIX_TIERS_v1_ZH.md` | S 288 / M 482 / L-realized 748 |
| B6e 方案 v2 | `B6e_plan/PLAN_V2_ZH.md` | 只是方案，不能启动 |

**PR #8 合入后的必做步骤**：

1. 把本分支改指 integration；
2. 重跑 `B5_real_replay_v2.py`、`B1_A1_cross_check.py`、`B1_needcard_cpu_preflight.py`；
3. 核对结果与本轮的集成前结果一致（摘要中的 status 会自动变为 `formal_on_integration`）。

## 4. 测试

见 PR 描述。CPU 测试会从 GitHub CI 和本地两边分别核对，以最终 head 的 CI 为准。
