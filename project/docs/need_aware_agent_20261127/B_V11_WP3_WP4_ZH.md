# B 工作线 v1.1：共同集成、WP3 强证据供给、WP4 后端接线

日期：2026-11-28（JST）。依据权威提交 [65424fd8](https://github.com/chensiyu7812/Metacom5_3/blob/65424fd807e5e14284b70a9a184288bf0ce7a95e/project/docs/need_aware_agent_20261127/WORK_ORDERS_ZH.md) 中 B 线的职责。本轮只做 CPU 开发与合法材料准备：没有新的 GPU 推理、训练、付费 API 或正式测试解封，也没有任何模型生成。私人原文、请求、向量、重排分数和逐题选择只保存在服务器 `/opt/tokkio-data0/naa/20261128/agent_b/`；本文只含代码和聚合数字。

## 1. 共同集成起点

| 项 | 值 |
|---|---|
| 权威方案 | `65424fd8`（AGENTS/README/MASTER_PLAN/WORK_ORDERS 与集成树逐字节一致） |
| A 最终头 | PR30 `eb33d363`（`219e62d6` 以 `--no-ff` 合入） |
| B 最终头 | PR31 `e05ecb0e`，含 teardown 修复 `3bd31d6c`/`5482fff7`（`51b385b8` 合入） |
| 集成 HEAD | `51b385b8`，分支 `integration/naa-v1.1-20261128` |
| 冲突 | 0。两线自共同基点 `ddc4864c` 起改动的文件互不相交（A 25 个、B 30 个），集成树中每个文件与各自责任方的头逐字节一致 |
| 回归 | 公开 CI 规则：V3 986 passed / 41 具名跳过，`verify_v3_public_ci.py` 通过；全套 paper1/rl1/rl1v3 2,811 passed / 44 skipped / 1 deselected；`00_validate_integration_base.py` 通过；NAA 66 passed（A+B） |

历史分支、PR30/31、两个本地 worktree 都未改动，也没有 force/reset。下一轮两线从 `51b385b8` 分头开分支；B 的 v1.1 工作在 `work/naa-agent-v11-20261128` 上。第一次跑回归时误用了缺少 `jsonschema` 的环境，收集阶段失败。那次的日志保留在服务器 `integration/attempt1_wrong_env/`，随后改用 CI 等价环境重跑，所有门禁都没有放宽。

## 2. WP3：一次强固定证据供给

### 2.1 复用而非重造

| 机制 | 来源 | NAA 中的用法 |
|---|---|---|
| 原文区间并集 / 去重 | GE2 `union_intervals` | E0 展开后的轮次按区间合并，重复轮次只渲染一次 |
| 完整原轮次、原角色、来源顺序 | GE2 渲染约束 + NAA reader `record_line`（"said by"） | 七个臂共用，绝不在轮次中间截断 |
| 相邻话轮 | GE2 ±1 窗口 | 由跨越话轮边界的 token 窗口自然覆盖；不额外 ±1，以保持 Raw-RAG 的原定义 |
| 父会话展开 | GE2 `scope='parent'` | PersonaMem-v2 的历史是一条没有会话边界、也没有日期的扁平消息列表，所以父会话就是整段历史。我们不造边界，如实记为不适用 |
| dense / BM25 / owner 隔离 / 查询不含选项 | NAA `retrieval.py` | B0/B1/B1s 直接复用 WP2 的 BGE 向量，无需重建 |

### 2.2 七个臂（代码：`agent/arms_wp3.py`、`agent/evidence.py`）

| 臂 | 实际输入 | 定位 |
|---|---|---|
| B0 | WP2 B：dense user_only@8192 | 历史参照 |
| B1 | 同一排名与打包，all roles@8192 | 全角色可用范围 |
| B1s | B1@1536 | 预算 / 紧凑化 |
| E0 | Raw-RAG 式：256 token 窗口、32 重叠 → BGE top-128 → Qwen3-Reranker-0.6B top-15 → 展开为完整重叠轮次 → 并集去重 → 按时间顺序；原生上限 8192（整窗跳过，不截断） | 强可部署基线 |
| E0s | 同一 E0 排名@1536 | 同方法的预算比较 |
| C | A 的合法 Direct 坐标，全部保留 | 诊断；不可部署，也不是真上界 |
| Cn | C 不变，加入固定种子抽取的同 owner/cutoff 非参考记录，补到约 8192；按来源顺序渲染 | 证据不丢失时的背景、长度和位置效应 |

**E0 是 Raw-RAG 的等价适配，不是复现**（arXiv 2610.30755，附录 B.1）。全部偏差都在任何模型调用之前固定，并逐条写在模块 docstring 中：

1. 窗口 token 用本地 BGE tokenizer 计数，论文用 GPT-4 tokenizer。
2. 第一阶段用 BGE-small，论文用 Qwen3-Embedding-4B 或 text-embedding-3-small。CPU 实测：Qwen3-Embedding-0.6B 约 780 tok/s，嵌入全部窗口需要十几个小时；BGE-small 约 17,900 tok/s。
3. 重排器用 Qwen3-Reranker-0.6B（Apache-2.0，revision `e61197ed`，按模型卡官方的 yes/no 打分，CPU fp32），论文用 4B 或 Cohere。4B 在 CPU 上处理 128 个候选不可行。这是本轮唯一新下载的模型，1.2 GB，存放在数据盘。
4. 展开后的轮次做去重、按时间排序。论文默认保留重复，LoCoMo/LongMemEval 按相关性排序。
5. 论文没有证据上限；E0 使用共同原生上限 8192。

重排指令只固定了一次，之后不再调整。重排分数的绝对值普遍很低，但排序信息仍然可用；我们不据此做任何参数搜索。

**短答案协议 `naa-mcq-short-v1`（modified）**：题面、选项顺序和合法信息都与官方相同，只把“先推理”换成只输出一行 `Final Answer: A`（不带括号），`max_new_tokens=64`。A 的官方解析器可以直接读出这个格式（有测试断言）。官方 WP2 的结果永不与它合并。

### 2.3 真实 CPU 统计（旧开发集 240 题，两个模型的 native tokenizer 取较大值）

| 臂 | 就绪 | Direct 参考召回 | 用户 / 非用户参考召回 | 完整证据组 | 证据 token P50 | Qwen 输入 P50 / max |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 240 | 0.500 | 1.000 / 0.000 | 0/207 | 7,536 | 7,880 / 8,661 |
| B1 | 240 | 0.636 | 0.604 / 0.668 | 85/207 | 8,184 | 8,539 / 9,069 |
| B1s | 240 | 0.348 | 0.321 / 0.374 | 35/207 | 1,529 | 1,971 / 2,585 |
| C | 207 | 1.000 | 1.000 / 1.000 | 207/207 | 394 | 849 / 1,553 |
| Cn | 207 | 1.000 | 1.000 / 1.000 | 207/207 | 8,184 | 8,544 / 8,798 |

- B0 精确复现了 WP2 B：用户参考召回 1.0、Direct 召回 0.500。
- 所有请求都在 12,000 输入上限内，最大 9,270（Gemma B1）。
- Cn 的背景记录 P50 为 52 条。其中 201/207 题的背景含遗忘或变化陈述，114/207 题含第三方提及；这些都如实保留，不过滤。参考记录的首个位置 P50 为第 21 条。
- 结论：同为 8192 预算，B1（全角色）比 B0 多覆盖约 1/7 的参考证据，完整证据组从 0 增加到 85，但用户陈述的召回从 1.0 降到 0.60，因为 assistant 回复很长，挤占了预算。所以不能把 B1 相对 B0 的变化解释为单纯的覆盖率效应。
- E0/E0s 的统计由后台 CPU 作业生成（第 4 节）。重排约 82 s/题，240 题约 5.7 小时，训练侧 80 题约 1.9 小时。作业完成后写出 `wp3/JOB_DONE.json` 和两份 `WP3_STATS.json`；按 AI 每小时最多检查一次的规则，在下一次检查时补入本表。

## 3. WP4：同证据行为比较与训练后端

- **U0/U1/U2/U3**（`agent/behavior.py`）：
  - U0/U2/U3 对同一任务和证据产生逐字节相同的输入，只有生成器身份不同（U2/U3 必须带 adapter 身份，否则拒绝）。
  - U1 是 Reglos（arXiv 2611.06049）式的确定性规则层：记录前放使用政策、遗忘墓碑（不删除任何证据）、变化、第三方、assistant 标记，以及静默规则（所有用户记录都关联遗忘请求或只描述他人时，不给记录）。
  - Reglos 的所有权标注、替代裁决、遗忘匹配都依赖 LLM 调用；按方案不新增在线 LLM，所以 U1 只用 writer 的确定性信号，标为“适配”。U1 也不是 D 的改写：D 只有指导语，U1 有完整的规则管线。
- **训练后端**：
  - `runtime/lora.py`：自写的最小 LoRA，基座冻结；adapter 带 SHA-256 保存，推理时合并。hf_worker/backend 接受 manifest 绑定的 `{path, sha256}`。
  - `runtime/training.py`：
    - 数据契约：owner 只能属于 fit 或 tune 之一；禁止出现开发、确认、测试 owner；唯一反例必须是不同行为，而且在同组内。
    - SFT 与配对 margin 使用相同的样本、顺序、步数、种子和优化器。
    - 配对项只用于 `unique_opposite` 的样本对，合理替代绝不当作负例。
  - `scripts/need_aware/naa_train.py`：inspect / check-data / estimate / train。train 在访问设备之前就检查批准文件与数据、配置、模型、干净 HEAD 和上限是否一致，否则拒绝。
- **真实 native tokenizer 检查发现的问题**：RL1 的 `encode_response` 不能用于这两个生成器。一是 Gemma-4 的生成提示以空 thought channel 开头，而历史对话渲染会去掉它；二是 transformers 5 的 `apply_chat_template(tokenize=True)` 返回 dict。所以训练编码改为锚定推理时实际的 `chat_ids` 加原生回合结束 token（Qwen `<|im_end|>` 248046，Gemma `<turn|>` 106）。两模型都已验证提示与推理请求的 ids 完全相同。
- **真实架构**（meta device，不加载权重）：

  | | Qwen3.5-9B | Gemma-4-12B-it |
  |---|---|---|
  | 基座参数 | 9,409,813,744 | 11,959,730,176 |
  | LoRA r=16 参数（attn+mlp） | 128 个模块，2,910 万 | 328 个模块，6,557 万 |
  | 只对 q/v 做 LoRA | 16 个模块 | 88 个模块 |
  | WP2 实测 prefill | 5,298 tok/s | 1,825 tok/s |

  Qwen3.5 是混合线性注意力，只有 8 层有标准 q/k/v/o，所以 LoRA 目标应选 attn+mlp。
- **真实 CPU 数据接线**：80 个训练侧 owner（种子 `naa-wp3-train-diagnostic-v1`，每个 owner 取 1 个已定位任务），用 A 已核验的 Direct 单元作为证据，配上明确标注为 PLUMBING 的目标，共 160 行。契约与泄漏检查通过（与 300 个开发 owner 无交集），两模型 native 编码的序列 P50 为 580/588、max 为 1,175。PLUMBING 目标不是监督，不可训练；真实标签由 A 交付。
- **测试**：NAA 共 78 passed（A 21、B 原有 45、WP3 6、WP4 6）。WP4 测试用小型随机 Llama 在 CPU 上验证：LoRA 初始时与基座输出相同、基座参数不变、NLL/hinge 下降、两种模式步数相同、合并后的 logits 等于包装后的 logits、错误的 adapter SHA 被拒绝。

## 4. 长任务与监督

`/opt/tokkio-data0/naa/20261128/agent_b/wp3/RUN_WP3_CPU.sh` 是一个确定性的 CPU 作业：可断点续跑，`CUDA_VISIBLE_DEVICES` 为空，所有缓存和临时目录都在数据盘，根分区未写入。它按 prepare-train → supply（开发集）→ supply（训练侧）→ 物化七个臂 → `JOB_DONE.json` 的顺序执行，每一步写 `JOB_STEPS.log`。代码与提交 `fcc84ae5` 一致，运行期间不修改它依赖的模块。AI 每小时最多检查一次，异常时由作业自身的退出状态和日志记录。

## 5. 复跑命令（服务器内）

```bash
cd project; export PYTHONPATH=src
PY=/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python
A=/opt/tokkio-data0/naa/20261127/artifacts
$PY scripts/need_aware/naa_wp3.py materialize --store-root /opt/tokkio-data0/naa/20261127/agent_b \
    --tasks $A/runtime/tasks.mcq.jsonl --direct $A/direct/direct.jsonl --out <out> --supply-out <supply_dev>
bash /opt/tokkio-data0/naa/20261128/agent_b/wp3/RUN_WP3_CPU.sh          # E0 supply + all arms
$PY scripts/need_aware/naa_train.py inspect --model Qwen35 --out <wp4>
$PY scripts/need_aware/naa_train.py check-data --train <A training JSONL> --store-root <stores> \
    --forbidden-owners <dev+confirm+test owners> --out <wp4>
PYTHONPATH=project/src python -m pytest project/tests/test_need_aware_*.py -o addopts=   # repo root
```

## 6. 与 A v1.1 交付的对接（2026-11-28 下午）

A 的头 `2d8bba1d`（PR #34）已以 `--no-ff` 合入 B 的 v1.1 分支（`cc064139`），没有冲突，合入后 NAA 共 101 项测试通过。A 列给 B 的四项待办处理如下：

1. **实际 native 请求 manifest**（`22949ae4`）：
   - WP3 的短答案指令改用 A 的共享模块 `data.short_protocol`（`naa-short-mcq-v1`），保留共同 recall 后缀；B 的草案文本作废。
   - `naa_wp3.py manifest` 把 A 的 1,400 个 `WP3_SLOTS` 一一绑定：逐条核对 `task_sha256`/`history_sha256` 和 logical id；请求索引带 `scoring_protocol`、`task_sha256`、`structural_reason`（`direct_unlocated`，或 `direct_over_cap` 并附 `full_direct_tokens`/`evidence_cap`/`input_cap`）。其他容量失败仍记为技术性 `capacity_exceeded`。
   - 衔接集 240 个请求的送达单元与 WP2 B/C 完全相同；运行器 plumbing 在该 manifest 格式上 240/240 完成。
   - `naa_wp4.py manifest` 生成开放任务 480 个请求：构造 180 × U0/U1，用 A 的 messages；自然 60 × U0/U1，用 E0s 证据并去掉回忆后缀。
   - 两份最终 manifest 由 CPU 作业 `RUN_V11_CPU.sh` 生成（确认集 E0 supply 约 3.3 h，自然 60 约 1.4 h），完成时写出 `MANIFESTS_DONE.json`。
2. **U1 规则绑定**：
   - 政策只保留 Reglos 的规则列表，删掉了我先前加的“请求为他人时可用”。受益对象判断是 U3 要检验的假设，不能放进规则基线。
   - `u1_messages` 用 writer 的同一组词汇线索（第三方、遗忘、变化）作用在 A 已渲染的行上。
   - 静默规则在构造变体中触发 96/180（都是只有第三方陈述的证据），这是规则本身的行为，按原样保留。
3. **LoRA 后端契约**（`195f3cd3`）：
   - `train_v11` 直接调用 A 的 `encode_target`/`masked_action_logp`/`objective`。U2 和 U3 走同样三个分支，U2 辅助系数为 0；组顺序按固定哈希；AdamW + weight decay + warmup；用 `logits_to_keep` 只计算尾部 logits。逐例累积的损失严格等于 A 的组目标（有测试）。
   - `check-v11` 在真实数据和真实 tokenizer 上检查：全部行的提示 = 推理时的 chat_ids，结尾 = `<|im_end|>`；与开发集和确认集 owner 无重叠。fit 只有 5 个 owner_id，A 的隔离实际按 620 个 source_family 进行。
   - 真实架构上，A 的 q/v 目标只覆盖 8/32 层，所以提出 `qv_all_layers` 供共同冻结。
   - 时间上界为每种方法 9,382 s。
4. **合并可执行申请**：见 [JOINT_WP3_WP4_RESOURCE_REQUEST_ZH.md](JOINT_WP3_WP4_RESOURCE_REQUEST_ZH.md)。合计 49,600 s，替换 A 的 115,200 s 候选上限。

此外发现一个需要告知 A 的问题：A 的 `encode_target` 对 Gemma 会以 `<eos>`(1) 而不是 `<turn|>`(106) 结尾。当前不影响，因为训练候选只有 Qwen。
