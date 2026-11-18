# NeedCard 20 前缀真实试点：可运行准备与 GPU 授权申请（**未获授权，未运行**）

- 证据等级：engineering_only。
- 本轮只做了 CPU 准备：重建输入、核对哈希、校验权重文件的 SHA。没有加载模型，没有调用 GPU，writer 调用 0 次。
- 计划文件：`needcard_pilot_v1_plan/RUN_PLAN.json`，只写一次，`plan_sha256 = 9a43a79bb76276a30d6c74992d476168240f7cac32bdd3ac14455658dd5b9f59`。
- 运行逻辑：
  - 核心：`needs/pilot.py`；
  - 脚本：`scripts/rl1v3/B1_needcard_pilot_run.py`；
  - 配置：`configs/rl1v3/B1_needcard_pilot_v1.yaml`。

## 1. 身份与输入

| 项 | 值 |
|---|---|
| 输入来源 | A1 正式 source registry `sources:c6ad9b15…`；完整、合法、严格早于切点的 RAW 历史；当前可见对话；A 提供的未验证 RS-v0 类别目录 `pmrl1v3-rs-v0-strategy-catalog-1:7323c7f4…` |
| 前缀 | 第 1–5 折固定的 20 个（`coverage_sample_v1` 的 needcard_pilot），按计划中的顺序执行 |
| 输入 SHA | 20 个 pack 的 `pack_sha256` 都与 WS-B 正式 integration 验收（`320a33d1`）的预检**逐字节相同**；所有输入的汇总哈希 `inputs_sha256 = 24fd8240…cbdb` |
| 验收绑定 | `ACCEPTANCE.json`（sha `d92c45b0…`，status 为 formal_integration_acceptance） |
| writer | `pmrl1v3-needcard-writer-v2\|qwen3.5-9b\|92578935…7b873c`；提示词 sha `90c1062c…3d37` |
| 模型 | Qwen3.5-9B，`/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b`；文件集合 sha `5f526cd0…6199`。12 个文件的 SHA256 已在 GPU 环境中重新计算，与资产审计一致（`check/check_gpu_env_cpu.log`） |
| tokenizer | `native-tokenizer:601f9509…`。在 CPU venv 和 GPU 环境中分别重建 pack，计数和 pack sha 都相同 |
| 解码 | 非思考模式、贪心（do_sample=false）、单次最多输出 800 token；停止 token 为 `<\|im_end\|>`(248046) 和 `<\|endoftext\|>`(248044)，pad 为 248044（模型目录里没有 generation_config，所以显式固定） |
| 运行环境 | `/opt/tokkio-data0/tokkio_envs/paper1-judges-py312`（torch 2.7.1+cu128，transformers 5.17.0）；HF、bf16、sdpa |
| 模型类 | `AutoModelForImageTextToText`，与 checkpoint 架构 `Qwen3_5ForConditionalGeneration` 一致；只输入文本。加载时缺失、多余或不匹配的权重键必须为空，否则停止 |
| 卡 | 只用 A6000 `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4` |

## 2. 可运行命令

CPU 复核（已执行，结果为空问题列表）：

```
cd <repo>/project && CUDA_VISIBLE_DEVICES='' PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python scripts/rl1v3/B1_needcard_pilot_run.py --mode check --verify-weights
```

GPU 运行（**获授权后才执行**）：

```
cd <repo>/project && CUDA_VISIBLE_DEVICES=GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4 PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python scripts/rl1v3/B1_needcard_pilot_run.py --mode run \
  --authorization outputs/pm_rl1/v3/B1/needcard_pilot_v1_plan/AUTHORIZATION.json
```

授权文件由研究者给出，B 不会自己写。必需字段：
- `authorized_by`、`granted_at`；
- `scope` = `B1_needcard_pilot_v1`；
- `plan_sha256` = 上面的值；
- `max_calls` ≤ 40；
- `gpu_uuid` = 上面的 A6000；
- `paid_api_calls` = 0。

`authorized_by` 不能是 WS-B 或 Codex。

## 3. 预算

| 项 | 上限 |
|---|---|
| 首次调用 | 20 |
| 重问 | 20（每个前缀最多 1 次，原样重问） |
| 总调用 | 40 |
| 预填充 | 277,880 token（首轮）；全部重问时最多 555,760 |
| 输出 | ≤ 32,000 token |
| 付费 API | 0 |
| 显存 | bf16 权重 18.0 GiB；KV ≤ 0.9 GiB（27k token）。激活和工作区**未实测**，运行时会记录每次调用的峰值显存 |
| 时间 | **未实测**；墙钟上限 2 小时 |

说明：贪心解码下，原样重问通常会得到相同的输出，所以重问的实际作用只是排除非确定性故障。如果研究者愿意，可以只授权 20 次调用并取消重问（这时 `max_calls` = 20）。

## 4. 停止条件（写在计划中，命中后不重试、不改提示词、不扩大规模）

- **S1**：任何前置条件不满足 → 不加载模型。前置条件包括：计划、代码或输入哈希；跟踪的文件有改动；授权；GPU 不是 A6000、空闲不足 30 GiB 或有其他进程；权重键不一致；输入 token 数与计划不同。
- **S2**：调用数达到上限（首次 20、重问 20、总共 40）。
- **S3**：生成时出现异常（OOM、CUDA 等）→ 立即停止。
- **S4**：前 5 个前缀中 writer_failed ≥ 3 → 停止。这说明输出格式存在系统性问题。
- **S5**：总墙钟超过 7200 秒 → 在下一次调用前停止；单次调用超过 600 秒 → 这次尝试记为失败（timeout）。

其他规则：
- 输出达到 800 token 或超时都算失败的尝试；两次尝试都失败 → **writer_failed**，不会记成 stratum none；`unknown` 不会被强行归为 none；
- 历史从不截断；
- 输出目录 `outputs/pm_rl1/v3/B1/needcard_pilot_v1/` 只写一次：`runtime.json`、`calls.jsonl`（每次调用后都 fsync）、`envelopes.jsonl`、`summary.json`；
- NeedCard 只在评价侧使用，**永远不进入 PM 或 G 的观察**。有静态测试守护：env、render、policies、train、generator、retrieve 都不 import needs、checklist 或 judge。

## 5. 运行后的逐卡开发核查（`needs/pilot_audit.py`，规则已预先固定）

```
python scripts/rl1v3/B1_needcard_pilot_audit.py --prepare   # 机器事实 + 空白答案
python scripts/rl1v3/B1_needcard_pilot_audit.py --report    # 人工答案 → 结论（按固定规则推出）
python scripts/rl1v3/B1_needcard_pilot_audit.py --freeze    # 只给 valid 的卡冻结检查表 v3
```

不止检查引文能否定位（组装时已经保证）。每张卡逐项回答下面 6 个问题：

1. 证据是否真的说明了它所对应的角色；
2. required 是否真的是当前任务不可缺少的历史；
3. relevant_optional 有没有被误标为 required，或者反过来；
4. 更正、拒绝、尝试和实际完成有没有混淆；
5. method_need 是否由当前对话的原话支持；
6. 有没有把 RS-v0 的对话动作标签当成经过验证的方法。

结论按固定规则推出，不自由选择：
- writer_failed；
- 证据错误（1、4、5、6 任一项为否）；
- 层级错误（2、3 任一项为否）；
- 无法判断；
- 有效。

非有效的卡必须写明修复原因。报告给出各类数量、证据错误率（门槛 ≤ 10%）和逐项统计。

RS-v0 的 `method_need` 以及由它推出的 RS 头需求，**不能**作为 GET_RS 必需性的标准答案。

只有核查为 valid 的卡，才能在任何候选回复出现之前冻结检查表 v3；冻结后不能根据候选回复修改（`ChecklistLedger` 会拒绝）。

20 张试点卡只能证明小规模生成是可行的。正式完成 B1 仍须满足原任务的抽样要求和 40 张卡的开发核查。

## 6. 需要研究者决定

1. 是否按上述计划授权（≤ 40 次，或者取消重问只授权 ≤ 20 次）；
2. 是否允许本次运行顺带记录 Qwen 的峰值显存和时间，作为 A0 的一部分实测，还是等 A0 单独测完。
