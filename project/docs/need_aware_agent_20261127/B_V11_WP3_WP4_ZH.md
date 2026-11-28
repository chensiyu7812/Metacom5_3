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

## 7. 研究者 2026-11-28 决定后的实施

决定原文逐字保存在 `V11_RESEARCHER_DECISION_20261128_ZH.md`（提交 `9a08ee03`）。要点：W3 已批准；修订后的 W4-0 有条件批准；U2/U3 训练、训练后评测、额外 GPU 重排、正式测试都未批准。

### 7.1 W3 实际运行

批准文件 `agent_b/authorization/W3_V11_APPROVAL.json` 由 B 依据书面指令生成，注明“非签名”；运行器启动前用同一函数核验过它。

运行前核对（`runs/w3-v11/PRECHECK.json`）：

| 项 | 实际值 |
|---|---|
| manifest SHA | `be1a4b97…53950`（requests `0f505d50…`） |
| 物理请求 | 1,377 个（1,400 逻辑位置，其中 23 个 Direct 未定位，结构性不可评价） |
| 执行 HEAD | `9a08ee03`，单独的冻结 worktree `Metacom5_3-naa-exec-w3`，开发 worktree 的改动不影响运行 |
| 模型身份 | 与 WP2 批准时的 g_id 完全一致（Qwen `8ab8d77b…`，Gemma `09b4e265…`） |
| 设备 | A6000 空闲，无其他计算进程，独占锁空闲 |
| 磁盘 | 根分区 1.29 GiB（guard 下限 1 GiB，本次不写根分区），数据盘 270 GiB |
| 最坏 GPU 秒 | Qwen 4,384 s，Gemma 2,198 s（上限 5,500 s/模型、合计 8,000 s） |
| 预检 | plumbing 后端在最终 manifest 上 1,377/1,377，导出、封存、汇总均通过 |

运行情况：12:12 UTC 启动。Qwen 技术烟测通过（16/16，无截断，生成中位 1.9 s，显存峰值 20.7 GB）；到 12:31 时 Qwen 已完成 497/1,082，没有失败或截断。

结束后自动执行：导出 → 为 A 封存 → 运行统计 → `W3_DONE.json` → 公开安全的成本回执 `W3_COST_RECEIPT.json` → `handoff/B_W3_SEALED_FOR_A.json`。正确率由 A 用 `score_wp3.py` 在封存导出上评分，B 不读取 gold。

**固定证据供给基础的选择**：要等 A 的评分。按决定，综合考虑质量、完整来源覆盖、成本和不确定性，不把与 C 的差距当作可学习收益。已知成本事实：E0 的 CPU 重排约 77–86 s/题；B1/B1s 不需要重排。

### 7.2 WP4 条件修订（`agent/behavior.py` v3）

| 条件 | 输入 |
|---|---|
| U0 | 固定证据，原样呈现 |
| U1 | 同一批证据 + Reglos 式规则；只看送达的证据，不读整个历史库；**从不删除证据** |
| U1+ | U1 + 偏好持有者与当前请求服务对象的匹配：按请求措辞判断是为谁，提示每条涉及他人的记录可能属于谁，再加一条匹配规则 |
| NoMem | 同一请求，不给记录 |
| OptOnly | 只有四个选项，没有请求和记录 |
| U2/U3 | U0 的字节级相同输入，只换生成器 |

Reglos 原来的静默机制保留为 `reglos_silence_view`，只作历史系统级参照：它读取全库，不是同证据比较。

真实数据 CPU 演练：用 30 个 WP2 开发题（这些题已有 E0 供给；只是演练，不是 A 的冻结集合），E0s@1536，共 150 个请求，plumbing 150/150 通过。

| 条件 | 输入 token P50 |
|---|---:|
| U0 | 1,873 |
| U1 | 2,066 |
| U1+ | 2,162 |
| NoMem | 443 |
| OptOnly | 321 |

外推到 280 题：约 1,400 个请求，最坏约 4,700 s，在上限 10,000 s / 1,500 次之内。

W4-0 的执行条件：

1. A 冻结不超过 280 个开发任务（`--task-ids`）和评价规则；
2. W3 评分后，A/B 共同确定证据臂；
3. B 用 `naa_wp4.py manifest-w40` 生成 manifest，A 核对 SHA；
4. B 写批准文件，在 W3 结束后顺序执行。

### 7.3 训练执行器八项修复（回归：`tests/test_need_aware_w4_revision.py`）

| # | 实现 |
|---|---|
| 1 | 每个 LoRA 模块的初始值用 (seed, 模块名) 单独种子生成，与全局随机状态无关；记录 `init_adapter_sha256`；U2/U3 初始值不同则拒绝建评测 manifest |
| 2 | `LORA.WP4_LORA` 冻结为 q_proj/v_proj/in_proj_qkv、r8、α16，覆盖 32 层；批准文件必须原样复述；旧 v1.1 路径也不能再覆盖 |
| 3 | adapter 后的 g_id = digest(基座 g_id、adapter 字节、配置、初始值、数据、训练回执、trainer 版本)。基座 g_id 不变；请求 hash 包含 g_id，所以 U0/U2/U3 不会被互相去重；评测 manifest 构造时再检查一次碰撞 |
| 4 | `TrainGuard`：与推理共用独占锁；硬 deadline = 取锁时刻 + 批准秒数 − 10 s 关闭余量；每个分支前向之前都检查；保存余量 120 s；每 25 次检查做一次存储/设备 guard；看门狗线程到时直接 SIGKILL；每步日志落盘 |
| 5 | 前 20 步技术烟测：损失和梯度有限、梯度非零、只有 adapter 有梯度、显存 ≤46 GiB、预测总时长在预算内；不通过就停止并写回执；不看任何开发正确率 |
| 6 | `manifest-adapted`：输入与 W4-0 逐字节相同；核对 adapter 文件 SHA、回执 SHA，U2/U3 的初始值、数据、基座和 trainer 必须一致；backend 和 worker 加载时严格比对 adapter |
| 7 | `export-open`：自然开放任务输出盲评包（条件隐藏、顺序打乱），揭盲 key 另存；按 A 的评分规则评价回复本身；action 字段只作格式统计 |
| 8 | 训练的提示 = 推理时的 `chat_ids`，以 `<|im_end|>`(248046) 结尾，且该 token 在解码的 EOS 列表中；真实 tokenizer 检查通过。Gemma 的 `<eos>` 问题只记录，不训练 Gemma |

### 7.4 官方回复监督后端（主路径）

- **数据格式** `naa-wp4-reply-v1`：每行 `messages`（或 `task` + `evidence_ids`，此时由 B 用 U0 渲染器生成，与评测同一渲染器，只是不加 MCQ 指令）、`chosen`（官方回复）、`rejected`（官方非首选回复）、`split`、`owner_id`、`group_id`、`provenance`。
- **损失**：
  - U2：回复级 SFT；
  - U3：SFT + `rank_weight × mean_j softplus(margin − (lp̄_chosen − lp̄_j))`，lp̄ 是回复的平均 token 对数概率；
  - U2 也计算全部分支，只是排序项系数为 0，因此两者计算量相同，数据顺序、种子、初始 adapter、优化器和步数也都相同。
- A v1.1 的 4,772 条模板候选不再作为主要监督，保留作失败诊断资产。
- **真实长度**：用 PLUMBING 行测量（真实任务和证据，选项文本作占位回复；没有读 gold，训练会拒绝这类行），E0s@1536：
  - 官方回复序列 P50 1,640、最长 1,750 token；
  - 1 个官方回复 + 3 个非首选回复，每例约 6,500 token；
  - 上界约 4.9 s/例/方法。例如 3,700 个 fit 样本，每种方法约 18,000 s。
- **成本杠杆**（属于 A 的数据设计，提交申请前一次定下，不做损失竞赛）：
  - 每例的非首选回复数，3 个降到 1 个，成本约减半；
  - 训练提示中的证据预算。
- **训练数据的证据**：几千个训练任务用 CPU 重排不可行（约 80 s/题）。可选方案是 B1s（无需重排），或 GPU 重排器（需要单独申请）。与 W3 的证据选择一起决定，不改变已冻结的 WP3 证据。

### 7.5 完整 Agent 最小接线（`agent/companion.py`）

链路：当前输入 → 需求判断 → 按需读取记忆 / 适用的支持技能 → U1+ 适用性规则 → 生成器回复 → 带 hash 链的历史。

全部复用已有部件：

| 环节 | 复用的部件 |
|---|---|
| 需求判断 | J06 的可见规则 `visible_rule`（STOP/MS/RS/MS_RS） |
| 记忆 | NAA Writer + WP3 排序与 Reader 打包 |
| 支持技能 | TIP35 SkillRecord；仅在明确求助且技能文本与请求重叠时才提供，最多一个 |
| 生成器 | 任意 messages → text 端口 |

强对照：始终读记忆、从不读记忆、始终读记忆+技能、基座自主选择（一个提示，不训练选择器）。`run_episode` 是端到端评价接口。

CPU 回归覆盖：

- 历史防篡改；
- 需求判断与技能门控；
- 三轮对话 STOP → MS → RS，记忆与 U1+ 只在 MS 轮出现，技能只在 RS 轮出现。

尚未用真实生成器运行。学习式 PM 或序贯 RL 不在本链路中。

### 7.6 W4-T / W4-E 联合申请

旧申请的 21,600 s 训练和 49,600 s 合计已作废。等 A 的真实回复数据和训练候选（超参数、每例非首选回复数、证据方案）冻结后：

1. B 对 A 的数据运行 `naa_train.py check-reply`，得到真实 token 和时间上界；
2. 与 W4-E 的 `manifest-adapted` 规模合在一起，一次联合提交。

在此之前，不提交未经实测的训练上限。

## 8. W3 终局结果、固定证据选择与 W4-0 联合核验（2026-11-28 13:00–13:40 UTC）

### 8.1 W3 成本（B 运行，`runs/w3-v11/W3_COST_RECEIPT.json`）

| 项 | 实际 | 上限 |
|---|---:|---:|
| GPU 秒（含加载、teardown） | 3,083.9 | 8,000 |
| Qwen3.5-9B | 1,991.7 s，1 次加载（42.6 s），1,082 个请求 | 5,500 s |
| Gemma-4-12B-it | 1,092.2 s，1 次加载（59.4 s），295 个请求 | 5,500 s |
| 物理调用 | 1,377，0 失败，0 重试 | 1,450 |

两个模型的技术烟测都通过。达到 64 token 上限被截断的共 16 个，按协议计入结果，不重跑。

### 8.2 W3 质量（A 评分，`a_response/wp3_terminal/CONFIRM_AGGREGATE.json`；B 只读汇总，不读 gold）

Qwen3.5-9B，140 题新确认集，修改版短答案协议：

| 臂 | 正确 / 完成 | 正确率 |
|---|---:|---:|
| B0（WP2 dense user_only @8192） | 55/140 | 39.3% |
| B1（全角色 @8192） | 58/140 | 41.4% |
| B1s（全角色 @1536） | 53/140 | 37.9% |
| E0（Raw-RAG 式 @8192） | 63/140 | 45.0% |
| E0s（@1536） | 53/140 | 37.9% |
| C（Direct，诊断） | 83/131 | 63.4% |
| C+noise | 57/131 | 43.5% |

预定的配对比较（差值，95% CI）：

| 比较 | 差值 | 95% CI |
|---|---:|---|
| B0→B1 | +2.1 pp | [−4.3, +8.6] |
| B1→E0 | +3.6 pp | [−2.1, +9.3]；修复 12 / 退步 7 |
| B1→B1s | −3.6 pp | [−10.7, +3.6] |
| E0→E0s | −7.1 pp | [−14.3, −0.7] |
| E0s→C | +25.2 pp | |
| C→C+noise | −19.8 pp | [−28.2, −11.5] |

Gemma 60 题复验：B0 30/60、E0s 25/60、C 39/55。

解读（只限这些数）：

- 可部署臂之间差距小，在 140 题上无法区分 E0 与 B1。
- 把证据压缩到 1536 会显著降低正确率。
- 在完整 Direct 证据中加入同一 owner 的合法背景（可能含更新或冲突信息，不能简单当作纯噪声）后，正确率下降近 20 pp。这说明“在大量合法记录中找到并用对证据”本身是瓶颈，与 WP4 的研究问题一致。
- C 的差距不当作可学习收益。

### 8.3 固定证据供给的共同选择：B1 全角色 dense @8192

A 的候选（`naa-response-b1-all8192-qwen-native-v1`）与 B 的判断一致：

- **质量**：E0 比 B1 高 3.6 pp，但 CI 跨 0；
- **成本**：E0 每题需要约 80 s 的 CPU 重排，训练侧几千个任务做不了，除非另行申请 GPU 重排器；
- **预算**：短预算显著更差，所以保持 8192；
- **一致性**：训练和评测都用同一种无需重排的供给。

与 WP3 的 B1 只有一处不同：预算只按 Qwen 原生 tokenizer 计数，因为 W4 只用 Qwen。

E0 的确认集覆盖统计还在 CPU 作业中，完成后补报，不影响这一选择。

### 8.4 W4-0 manifest 联合核验（`agent_b/wp4/W40_JOINT_CHECK.json`）

A 冻结了 14 个完整 owner 共 272 个开发题（`development_frozen/`）和评价政策（`POLICY.json`，主要比较 U3−U2，次要比较预先固定），并用 B 的 `behavior.mcq_messages`（v4）加 B1@8192 构建了 manifest（`a18daa8a…` 文件，requests `2a05ddae…`）。

B 用 `naa_wp4.py verify-w40` 独立复算，16 项全部通过：

- requests SHA、基座 g_id、64 token 解码；
- 行内没有额外字段；
- 272 题，每题恰好 5 个条件，task_sha256 正确；
- U0/U1/U1+ 送达的证据 id 完全相同，NoMem 和 OptOnly 不含证据；
- 各条件的版式正确；
- 1,360 个请求全部用 Qwen native tokenizer 重新编码，并重算了请求 hash；
- 上限在研究者范围内（10,000 s / 1,500 次 / 每模型 2 次加载）；
- 开发集 owner 与训练 fit/tune 不重叠，且都在训练禁用名单中。

GPU 时间：最坏 5,639 s；按 W3 实测速率约 2,150 s。

B 没有读取开发集的 gold（`development_frozen/evaluation`）。
