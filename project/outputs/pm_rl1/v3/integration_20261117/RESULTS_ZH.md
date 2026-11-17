# 工程集成验收：失败保留，C0 未冻结（2026-11-17）

**PR #5、PR #6 已按依赖顺序合入 integration；正式冻结停止。** 实际测试提交为 `6f5deea313c9f116b983ba07dc787f1bf43a8d4c`。V3 在本地和 GitHub 均为 287 项全部通过，但完整 CPU 回归和实际 push CI 各有一项失败，不能宣布 C0 完成或正式冻结。

## 集成输入与所有权

| 项目 | 实际 SHA / 结果 |
|---|---|
| WS-A 原输入 / PR #5 | `94ebb80b0a897f5f2741a329798be6ed1e2cd9f8` |
| PR #5 merge | `f63a2e6097c58ae63f6d20eeab2a89d984fb9876` |
| WS-B 原输入 / PR #6 | `2ccad7be86ed1fe8a270562fc1a65468147a551c` |
| B 同步真实 integration | `bfa45ad3a28a94cdef686e9f0084cfe6b0075dd2`，普通 merge，无冲突 |
| B 同步后复审证据提交 | `f07770420961766539f4834a9da204a65f6a33fa`，278 V3 全通过 |
| 集成 CI 与 ignore 修改 | `4f6afdd5cc79287a47a79dcf07df5454dc578a0c` |
| PR #6 ready 后 merge / 本次实际测试提交 | `6f5deea313c9f116b983ba07dc787f1bf43a8d4c` |

B 正式 `test_rl1v3_c0_wsb_acceptance.py` 与原 `2ccad7be` 逐字节相同，SHA256 为 `ba9c1e3411ead9604a71c7907b289204be102fd8de6733e1343b7f84e220f6d2`。A 的验收保存在独立文件；复制的 B0 `census.py.txt` 已不存在。contracts/io/32 个当前 Schema 与 A 的 `94ebb80b` 完全一致。B 正式验收实际 14 项，B5 绑定实际 10 项；旧报告的 11 项误计已由 B 记录纠正，未修改断言。

401 会话的 A/B family 命名已经一致，84 个 ESConv seed family 与 `esc1198` 的 p13/p18 共享来源约束保留。没有重复处理旧报告中已解决的冲突。

`.gitignore` 为 `project/src/metacom_pm/rl1v3/env/` 添加了精确例外；该目录源码可追踪，普通根目录 `env/` 和源码目录内 `__pycache__/` 仍被忽略。没有改写研究方案、原始日志或旧协议。

## 实际验收

| 范围 | 通过 | 失败 | 旧环境 skip | GPU deselected | xfail |
|---|---:|---:|---:|---:|---:|
| 本地全部 V3 | 287 | 0 | 0 | 0 | 0 |
| 本地当前完整 CPU（Paper-1 + RL1 + V3） | 2119 | 1 | 1 | 11 | 0 |
| GitHub 实际 integration push：全部 V3 | 287 | 0 | 0 | 0 | 0 |
| GitHub 实际 integration push：完整 CPU | 2051 | 1 | 63 | 1 | 0 |

本地 V3 17.38 秒，完整 CPU 475.62 秒；GitHub V3 12.74 秒，完整 CPU 438.98 秒。计数来自保存的 JUnit XML；每条失败、每条跳过及模块计数见 `TEST_RESULTS.json`。本地与 CI 的 V3 testcase ID 集合 SHA 相同。32 份 Schema 检查、本地旧协议 integration-base 校验和 compileall 通过。GitHub 的 integration-base 步骤因前序失败而未执行，不冒充 CI 通过。

本地唯一旧环境 skip 是历史 Llama tokenizer 不在规定绝对路径。GitHub 63 项分别为：保留的旧 engine/relation 输入缺失 32、engine/task 输入缺失 28、缺少 `rg` 1、缺少 `sentence_transformers` 的模块 collection skip 1、历史 tokenizer collection skip 1。collection skip 按 pytest 报告计数，不能推算为已覆盖模块中的所有测试。旧环境跳过不算完整覆盖。

实际集成 [push CI 44084379612](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44084379612) **failure**，head 明确为 `6f5deea3`，不是 PR 虚拟合并或旧分支绿灯。GitHub artifact `14329561478` 的 ZIP SHA256=`7dc590737d79a97e6a254cf25e30f5996649a1c2b01fc73873f834d027f26e16`，下载后已核验。更早的集成准备 [44083822387](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44083822387) 及 B 同步 PR [44084115643](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44084115643) 也因同一项失败，均保存原日志，没有静默忽略。

## 唯一阻塞与修复交接

失败：`test_paper1_authority.py::test_ci_never_runs_local_gpu_tests_on_github_cpu_runner`，第 107 行。

根因属于**集成负责人**：`4f6afdd5` 新增独立 V3 CI 命令时遗漏 `-m "not gpu"`，违反仓库已有的每条 pytest CI 命令显式排除 GPU 的保护断言。V3 本身全部通过不抵消该保护失败；本轮没有占用 GPU。

按研究者“实际合并出现新冲突或 CI 失败，停止冻结，记录原因并交还相关负责人修复”的要求，不生成正式冻结记录，不修改或弱化历史断言，不通过 skip/xfail 获得绿色。`REPAIR_PROPOSAL.patch` 给出一行未应用的配置修复，`git apply --check` 通过，但没有宣称修复后测试成功。该问题不交给 A 修改契约或 B 修改业务实现。

后续由集成 CI 负责人应用修复，先运行失败的保护测试，再在新真实 integration commit 上重新运行全部 V3、完整 CPU 和 GitHub push CI；所有必需检查通过后才能生成 C0 正式冻结。证据提交只记录本次失败，不等于修复提交。

## 状态与可依赖接口

- C0：`in_progress`，已合入但未冻结。精确候选接口为 `pmrl1v3-contracts-0.2.0` / `pmrl1v3-json-1`，代码提交 `6f5deea3`；Schema 的逐文件 SHA 见 `INPUT_MANIFEST.json`。`finite_head_v1` 与 `adaptive_v1` 分域；B5 当前只提供 Phase-1。
- B0：`completed`。实际集成 23 项 B0 测试通过，原 manifest 的 7 项来源/输出 SHA 核验通过；18 owner、401 会话、4119 合法前缀。前缀协议为 `pmrl1v3-b0-prefix-census-v1`；`prefixes.census` 的普查/合法前缀接口可按该提交调用，旧曝光限制保留。
- A0：`in_progress`，仅已合入 CPU 准备；未完成 GPU 吞吐、显存或规模档位实测。
- A1：`pending`；`A1_reuse` 仅作为准备证据登记，未冒充 source_registry。A1b、B1、B2、B6e 均保持 pending。
- B5：`in_progress`。`env.finite_head` 的有限环境/DP 和 `env.c0_binding.C0FiniteHeadEnv`、`subset_key` 已合入，17+10 项测试通过，但真实 bank/read 仍待 A1b。不能声称已实现真实资源回放。
- B8e：`pending`，仅保留既有 `B8e_preflight` 证据，不升级为正式真实 bank 训练。

A 下一项在 C0 修复验收冻结后是 A1 source_registry → A1b；B 可继续以 B0 和候选 0.2.0 做接口准备，但 B1 仍依赖真实 A1b，正式 B8e 仍依赖 B6e。不得把本记录当作 C0 已冻结依据。

PR #4 仍 open；main 核验保持 `10307c62f5175fcad62558e9e20d4d881b3d9238`。`adopted_by_researcher=false`，H0 未通过。全局状态仅由本集成负责人更新，30 项任务及原依赖 DAG 未改。

本轮只运行 CPU 回归（包含既有合成 fixture/优化器单元自检），没有启动独立实验训练、预训练模型推理、GPU 或付费 API。

## 重放与证据

在实际测试提交 `6f5deea3` 的独立工作树使用本地 `acceptance/ENVIRONMENT.json` 记录的 CPU Python 环境：

```bash
export PYTHONPATH=project/src:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103
export CUDA_VISIBLE_DEVICES=''
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
python -m pytest -q project/tests/test_rl1v3_*.py -ra -o addopts= -o xfail_strict=true --junitxml=/tmp/rl1v3.xml
python project/scripts/rl1v3/verify_v3_junit.py /tmp/rl1v3.xml
python -m pytest -q -m 'not gpu' project/tests/test_paper1_*.py project/tests/test_rl1_*.py project/tests/test_rl1v3_*.py -ra -o addopts= -o xfail_strict=true --junitxml=/tmp/rl1v3-full.xml
```

`INPUT_MANIFEST.json` 的 99 项输入哈希已对实际测试 commit 的 Git 对象逐条校验；其中状态文件对应测试时旧状态，新状态另作为本次输出记录。`MANIFEST.json` 固定本次输入、脚本、原日志、XML、CI 元数据、失败说明与状态文件的 SHA。本目录是追加证据，原 A/B 结果未被改写。

原始 GitHub 日志保留下载字节，包括行尾空白；因此全路径 `git diff --check` 报告日志空白。源码、状态与说明文件单独检查通过，没有为了格式检查改写原日志。
