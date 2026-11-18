# NeedCard 20 前缀试点：计划补充 v2（20 次首次调用，不重问），提交研究者审阅（**未获授权，未运行**）

- 证据等级：engineering_only。
- 这份计划只是按研究者建议提交的版本，**本身不是 GPU 授权**。没有加载模型，writer 调用 0 次。
- 计划文件：`needcard_pilot_v2_plan/RUN_PLAN.json`，只写一次，**`plan_sha256 = b1d3225b4e9b9442c2d2e7c1730ea7645e2168bd5987a2d9138fa77adca1598f`**。
- 原计划 `needcard_pilot_v1_plan/RUN_PLAN.json`（`9a43a79b…`，40 次）保留，没有覆盖，而且仍能通过校验（本轮重新执行了 `--mode check`，没有发现问题）。两份计划各自需要独立授权。
- 代码：
  - 核心：`needs/pilot_v2.py`；
  - 脚本：`scripts/rl1v3/B1_needcard_pilot_run_v2.py`，复用 v1 的输入构造、GPU 检查和 HF 生成器，这些部分没有改动；
  - 配置：`configs/rl1v3/B1_needcard_pilot_v2.yaml`。

## 1. 与 v1 的差别

只有调用策略不同。输入、模型、解码和停止规则与 v1 完全相同。

| 项 | v1（保留） | v2（本次提交） |
|---|---|---|
| 首次调用 | ≤ 20 | **max_first_calls = 20** |
| 重问 | 每个前缀 ≤ 1 次（原样重问） | **max_retry_calls = 0** |
| 总调用 | ≤ 40 | ≤ 20 |
| 第一次失败后 | 原样重问一次 | 直接记为 writer_failed（贪心解码下重问只会得到相同输出） |
| 调用前阻塞 | 视为前置条件不满足（S1） | 单独记为 `pre_call_blocked`，不调用（这 20 个都是 ready） |
| 输出上限 | 32,000 token | 16,000 token |

## 2. 绑定的身份与输入（与 v1 相同，均已核验）

| 项 | 值 |
|---|---|
| 输入 | 20 个 pack 的 SHA 与正式 integration 验收（`320a33d1`）逐字节相同 |
| 输入来源 | A1 正式 registry、完整合法的严格过去 RAW、当前可见对话、A 提供的未验证 RS-v0 类别目录 |
| writer | `pmrl1v3-needcard-writer-v2\|qwen3.5-9b\|92578935…`；提示词 sha `90c1062c…` |
| 模型 | Qwen3.5-9B，文件集合 sha `5f526cd0…`。本轮在 GPU 环境中重新计算了 12 个文件的 SHA，都与资产审计一致（`check/check_gpu_env_cpu.log`） |
| 模型类 | `AutoModelForImageTextToText`，与 checkpoint 一致；加载时缺失或多余的权重键必须为空 |
| 解码 | 非思考、贪心、最多输出 800 token；EOS 固定为 248046 和 248044，pad 为 248044 |
| 顺序 | 按计划中的固定顺序；历史不截断；不改提示词；不挑选结果；失败后不重跑 |

## 3. 命令

```
# CPU 复核（已执行，问题列表为空）
cd <repo>/project && CUDA_VISIBLE_DEVICES='' PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python scripts/rl1v3/B1_needcard_pilot_run_v2.py --mode check --verify-weights
# GPU 运行（获得独立授权后才执行）
cd <repo>/project && CUDA_VISIBLE_DEVICES=GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4 PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python scripts/rl1v3/B1_needcard_pilot_run_v2.py --mode run \
  --authorization outputs/pm_rl1/v3/B1/needcard_pilot_v2_plan/AUTHORIZATION.json
```

授权文件由研究者给出，B 不会自己写。必需字段：
- `authorized_by`、`granted_at`；
- `scope` = `B1_needcard_pilot_v2`；
- `plan_sha256` = 上面的值；
- `max_first_calls` ≤ 20；
- `max_retry_calls` = 0；
- `gpu_uuid` = A6000；
- `paid_api_calls` = 0。

## 4. 每次调用的记录

每次调用都记录：
- 输入身份：pack sha、messages sha、输入 token；
- 实际输出原文及其 sha；
- 结束原因、输出 token、耗时、峰值显存；
- 错误；
- 是否因此记为 writer_failed。

`summary.json` 中的 `a0_handoff` 汇总耗时、token 和峰值显存，并标明属于 **NeedCard writer 工作负载（Qwen3.5-9B，输出 ≤ 800 token），不是 J1 判官吞吐**。

## 5. 停止条件

- **S1**：任一前置条件不满足 → 不加载模型。
- **S2**：调用数达到上限（20 / 0 / 20）。
- **S3**：生成时出现异常 → 立即停止，不重试。
- **S4**：前 5 个前缀中 writer_failed ≥ 3 → 停止。
- **S5**：总墙钟超过 7200 秒 → 在下一次调用前停止；单次调用超过 600 秒 → 这张卡记为 writer_failed（timeout）。

命中任何一条都不改提示词、不扩大规模。

## 6. 运行后的人工开发核查（核查协议 v2：`needs/pilot_audit_v2.py`，`scripts/rl1v3/B1_needcard_pilot_audit_v2.py`）

- 6 项检查与已预注册的 v1 **完全相同**，判定规则也相同；v2 只把结论标签对齐到本轮指令。

| 结论 | 何时判定 |
|---|---|
| valid | 6 项都为"是"或"不适用" |
| evidence_error | ①证据、④建议/尝试/完成/更正/拒绝、⑤method、⑥RS 标签，任一项为"否" |
| stratum_error | 否则，②required 是否必要、③required 与 optional 是否混淆，任一项为"否" |
| uncertain | 否则，有任一项无法判断 |
| writer_failed | writer 调用过，但没有产出有效的卡 |
| pre_call_blocked | 调用前阻塞，从未调用 |

- 每张卡保留：机器预填的证据（每个引文的会话、rank、说话人、原文）、6 项的答案、逐项的审查备注、错误类型、修复原因和审查者。
- **两道门，门槛不放宽**：
  1. 整体证据错误率 ≤ 10%（分母为实际产出的卡）；
  2. B6e-v3 选中的 8 个前缀**各自**都有 valid 卡。
  任一道门不通过，**B6e 暂停**。
- 只有 valid 的卡，才能在任何候选回复出现之前冻结检查表 v3；冻结后不能根据候选回复修改。
- RS-v0 的 method 标签仍是未经验证的对话行为标签，不能作为 GET_RS 必需性的标准答案。
- 20 张卡**不能**代替正式 B1。正式 B1 仍须按 V3.1 完成训练折抽样、40 张卡的开发核查，以及需求层比例和权重审计；口径保持 S=288、M=482、L-realized=748，每个会话最多两个前缀。
