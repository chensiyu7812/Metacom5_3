# B 工作线实际交付：Memory Writer/Reader、四臂输入、批量运行器与联合 WP2 申请

日期：2026-11-27（JST）。执行结果，不改变 MASTER_PLAN。**没有任何模型推理结果；GPU、训练、付费 API、正式测试调用均为 0。** 文中所有“运行”均为 CPU 路径或标注为 plumbing 的干跑；plumbing 输出被 A 的 scorer 拒绝作为模型结果。原文、逐题请求、向量、账本全部只在服务器 `/opt/tokkio-data0/naa/20261127/agent_b/`；机器可读聚合见 [B_CPU_RECEIPT.json](B_CPU_RECEIPT.json)。

分支 `work/naa-agent-20261127`，worktree `/opt/tokkio-data0/tokkio_projects/Metacom5_3-naa-agent`，起点 `3dded9b2`；fast-forward 整合 `5c719598`（30 个恢复源码），并合并 A 的 `ddc4864c`（共享契约、scorer、WP2 逻辑槽位）。旧 worktree、main、历史实验、旧授权、旧 `WorkerCallBudget` 均未改。

## 1. 源码恢复与 CI：依赖已兼容；公开 CI 与严格私有回放均通过

| 检查 | 实际结果 |
|---|---|
| 30 个恢复文件 vs 历史实际执行快照 | 与 GE2/GSWS/dynamic/SC36/terminal/capability 各运行包 PLAN 中 `executor_files_sha256` **30/30 字节一致**（G6 工作树本身也缺这 30 个文件；历史运行使用的是 executor 快照） |
| executor 中存在、当前树缺失的其他文件 | 33 个；当前树任何代码/测试均不 import 它们，不属于运行依赖，未恢复 |
| 本地复现 CI（Py3.11、torch 2.3.1+cpu、`pip install -e .[dev]`） | V3：976 passed / 41 skipped → `verify_v3_junit.py` 因 skip 拒绝；与 GitHub run 45993476547（974/43）同因 |
| 同一套件 + 服务器私有根（12 个环境变量） | V3 **1017 passed / 0 skipped，junit 门通过**；Paper-1+RL1+V3 全套 2842 passed / 3 skipped；integration base 校验 `failed_checks=[]` |

结论：collection 已修复，恢复源码与真实历史产物兼容。PR #29 的剩余失败来自 journal 线 43 个私有回执测试：它们在公开 CI 中必然 skip，而严格门禁禁止 skip。这些测试在 b07db104 之后的 24 个提交里从未进过 CI。研究分支 `b05f5f21` 已把公开 CI 改为 `verify_v3_public_ci.py`（43 个具名延期项必须原因一致，不计为通过），原严格门禁保留为本地验收。我曾尝试 marker 方案，因与“不跳过测试”冲突已撤回，没有留下任何改动；现已整合 `b05f5f21`。合并后复验：公开门禁 `public_code_acceptance=passed`（986 passed）；带服务器私有根的严格回放 **1027/1027、0 skip，`verify_v3_junit.py` 通过**，即 CI_PUBLIC_PRIVATE 文档要求的本地严格验收。PR #31 的 `pytest` 与 `naa-cpu` 均为绿。

## 2. 复用 / 薄适配 / 不复用（任务 1）

| 原模块 | 处理 | 原因 |
|---|---|---|
| `semcap/identity.py` classify_source / attribute_history / is_current_user / system_prompt | **直接复用**（Writer 与 arms 的身份投影） | PersonaMem 的 assistant 轮由数据生成管线产生，不是本 agent：情形为 U（未确立），不把它说成本 agent 的经历 |
| `journal/ge2_retrieval.py` `_BM25` / tokens | **复用公式实现** | 同一 Robertson IDF、k1=1.2、b=.75；但 `SharedRetrieval.validate_record` 只接受 ESConv seeker/supporter 父会话，且“每父会话一窗口”不适用单会话长历史，因此不复用选择逻辑 |
| `ge2_worker.SubprocessGE2HF` 传输 / `limited_run.device_guard` / `require` / `storage_guard` / 固定 GPU 锁 / `runprep_checkpoint` / `pomdp_latency` 首 token 观察 | **复用**（NAA 后端继承 GE2 传输与 WIRE_FAILURE 证据） | 这是真正跑过 GE2 的加载、计时、资源与日志机制 |
| `limited_worker_guard` | **薄适配**（`need_aware/runtime/worker_guard.py`，复用 `pidfd_open`） | 原 guard 把作业限制在 1200 s 内，无法承载多小时批次；新 guard 的上限取自批准的 GPU 秒数（≤12 h），原 guard 不变 |
| `ge2_worker.WorkerCallBudget`、`limited_run.read_plan/authorize` | **不复用、不修改** | 硬编码两任务/A0/PP1 身份；NAA 另设 `NAABatchBudget` 与 `naa-wp2-approval-v1`，旧授权无法迁移（已实测拒绝 G1 approval） |
| `g4_context.memory_record` / `g6_context` | **构念并入新 Writer**（speaker_label、is_current_user、situation、报告时间），不 import | G6 只把它接在测试运行器上；本次接入了实际的 Writer→Reader→arms→请求链路。在线 CHECK 不恢复 |
| `evidence_state.revise` / T1i、GSWS、INSPECT_CLAIM、G7 | **不调用** | 尚无独立收益证据；首轮 D 只用确定性投影，不引入同步 LLM |
| `ge2_controller/runtime`、`pomdp_memory` | **保留为后续工具 Agent 对照**，不改 | 本轮不运行序贯控制 |

## 3. 实际 Memory Writer / Reader 接线

`need_aware/memory/writer.py`：输入**仅**是 A 的 `HistoryResolver.resolve(task)` 返回的 EvidenceRecord（hash/owner/cutoff 由 A 强制），签名中没有 query、options 和 eval（有 AST 测试）。真实 300 个任务的结果：

- 300 个 store / 300 个 owner；69,261 个单元（用户 34,748、assistant 34,513）；**300 条 message 0 system persona 档案全部排除**（只保留 hash），所有 arm 都看不到完整 persona。这与上游官方推理不同（上游会把它原样送入），记为版本化偏差。
- 时间：没有任何 wall-clock（`reported_at` 非空 0 条），只有消息顺序；状态均为 `reported`，从不标 `confirmed`。
- 遗忘/更新：用户显式遗忘请求 5,130 条（几乎每个 history 都有，中位 18 条，例如“Please forget that I …”；与 A 的 census 中 `ask_to_forget` 占 train 约 20% 相符）。经实物抽查，已剔除 ignore/delete/erase 类编辑语误报。只有 112 条能以确定性词汇重叠（≥0.6）链接到早前的用户陈述，其余所指内容在历史中没有字面陈述，保持未链接。只标注、从不删除。显式“变化”陈述 94 条（“lately I’ve…”不计）。
- 不可变 store id（`naamem:` + 内容 hash），磁盘缓存可防篡改（测试验证）。

`memory/reader.py`：在预算内按优先级打包（A 为连续 recency 窗口，B 为贪心）。raw 视图用于 A/B/C；state 视图用于 D，即**同一 raw 块**加上确定性的证据状态（主体绑定、最近用户陈述、已送达单元内的遗忘/变化候选）和固定的适用性指令（use/background/ignore、当前请求优先、不用被要求遗忘的内容、不复述无关记忆）。D 不额外调用模型，也不引入 C 之外的原文。

## 4. 检索与 240 个真实任务的 CPU 统计

查询只取 `user_query` 与可见 current_messages，选项从不进入查询（有测试）。Dense 使用本机 BGE-small-en-v1.5@5c38ec7（CPU，20 线程，69,261 个单元耗时 1,169 s；3,614 个单元在 512 token 处截断）。证据 token 按两个模型 native tokenizer 的较大值计，保证两个 G 看到同一份证据。

在 207 个 Direct 可定位任务上的覆盖诊断（Direct 只作诊断，从不进入 B）：

| 预算 | A recency | BM25 user_only | dense user_only | dense all+expand | hybrid user_only |
|---|---|---|---|---|---|
| 4096 any-hit / 用户陈述 recall | 0 / 0 | .816 / .664 | .908 / .842 | .638 / .494 | .899 / .796 |
| 8192 any-hit / 用户陈述 recall | .005 / .002 | 1.0 / .995 | **1.0 / 1.0** | .812 / .682 | 1.0 / 1.0 |

关键事实：PersonaMem history 约 44k native tokens，其中用户发言合计只有约 7.1k，**在 8192 预算下 user_only 几乎能送达全部用户陈述**；而 recency 窗口几乎从不覆盖 Direct 证据（偏好陈述位于 history 前部）。按预先写下的规则（mean Direct recall）会选 dense/all+expand（.687 / any-hit .812），但这个指标把 Direct span 中的 assistant 回复也算进分母，user_only 按构造无法检索到这部分。因此我把规则**一次性更正**为“用户陈述 recall → any-hit → 更简单”，B 取 dense/user_only@8192（`naaret:92cf81e8…`）。这次选择只依据证据覆盖，没有任何模型输出参与。原规则的结果在回执中公开。检索延迟（CPU）：查询编码平均 29 ms，排序平均 7–10 ms。

## 5. 四臂的实际输入与版本身份（最终 WP2 manifest）

共同契约：同一 system（身份合同 U），最终 user 轮为“证据块 + 当前请求 + 官方 MCQ 指令原文”。Qwen3.5 模板拒绝末尾的 system 消息，因此两个模型统一把官方指令放在最后一个 user 轮（`naa-arms-prompt-v1` 的偏差说明）。贪心解码，`max_new_tokens=1024`；stop/pad/suppress 与 A 的 native inventory 逐项一致（G0e [1,50,106] / pad 0 / suppress [258883,258882]；Qwen [248044,248046] / pad 248044）。

| 臂 | 就绪 / not_evaluable（每个 G） | native 输入 tokens 中位（G0e / Qwen） | 送达单元中位 |
|---|---|---|---|
| A context_only（recency 8192） | 240 / 0 | 8414 / 8413 | 34 |
| B strong_fixed_rag（dense user_only 8192） | 240 / 0 | 7639 / 7527 | 114 |
| C direct_evidence | 207 / 33 | 850 / 847 | 4 |
| D evidence_state（同 C 单元 + 投影） | 207 / 33 | 1052 / 1039 | 4 |

所有请求的最大输入为 8,972 tokens，均在 12,000 / 16,384 上限内，容量失败 0。C/D 送达的 id 与原文完全相同（断言 + 测试）。每个请求逐一绑定 A 的 `wp2_v2` 逻辑槽位（task sha、Direct manifest sha、可评估性、decode/上限），并按 A 的顺序排列（种子打乱任务、任务内四臂随机、模型为主序）。exact 请求 hash 覆盖 g_id+messages+native ids+decode，1,788 个均唯一，0 重复；两次物化得到的 1,788 个 hash 完全一致。

身份：manifest `9839c088aee11f1b0ae8f2b82ba39cbce8afbf904e4e4a216cd240ed09734996`；requests `0215976c…`；scope `9531e30e…`；A 槽位文件 `6dbd6b13…`；g_id G0e `naag:G0e:9fe67322…`、Qwen `naag:Qwen35:91bb1627…`；writer/reader/prompt/request/binding 版本均在 manifest 中。另外物化了 60 个开放任务（456 个就绪，C/D 各 6 个 not_evaluable），**本次不申请**。

## 6. 批量运行器：真实具备的能力与实测

- native tokenizer：物化时由真实 tokenizer 渲染并计数；worker 加载后**再次**用 native 模板重算并与 input_ids 比对，同时做容量检查。
- 批量 / 断点续跑：hash 链式追加账本，每个进程写新段，torn tail 保留；续跑从账本恢复，已完成不重算，重复请求记为 REUSE（不是独立观测）。
- 预算：只接受 manifest 中列出的 exact hash；物理调用、单请求 2 次尝试、总重试 ≤132、每模型 ≤3 次加载、GPU 秒数（每模型均分），续跑也受限。修复了一处 GPU 秒数重复计数 bug（有测试）。连续 3 次失败即停。
- 失败：ATTEMPT_FAILED / INVALID / LOAD_FAILED / EXHAUSTED / STOP 全部入账；GE2 传输的 WIRE_FAILURE 私有证据保留。
- 时延：记录 worker 单调钟下的生成 ns、首个生成 token 延迟（内部 streamer 观察，不是客户端 TTFT）、监督端往返、加载时间。
- 准入：没有批准，或传入旧实验的批准，都在**创建 run root 和访问设备之前**被拒绝（已对真实 manifest 实测）。
- 真实路径还包括：storage_guard、固定 GPU 锁、A6000 设备 guard、加载前对模型全部文件做新鲜 SHA-256 校验、checkpoint header 与 HF loading-info 检查（G0e 的 tied lm_head 会被实际验证；Qwen 允许 15 个 MTP 张量不使用）。

实测（plumbing，bwrap 命名空间内，网络隔离，eval/training/source 不可见）：wp2-final 1,788/1,788 完成。中断续跑演练：SIGINT 时已有 365 个结果，续跑后在途的 1 个重试 1 次，已完成的未重算，132 个 not_evaluable 未重复记录。注入失败演练：失败请求重试 1 次后标为 EXHAUSTED，且不会为此加载模型。导出的 predictions 被 A 的 `score_predictions` 契约接受；作为模型结果则被拒（provenance mismatch）。测试：B 新增 27 项 + A 13 项，在仅装 pytest+pydantic 的最小环境中 40 passed。

## 7. 可执行命令

CPU（可重复执行，均在无 eval 命名空间中）：
```
cd /opt/tokkio-data0/tokkio_projects/Metacom5_3-naa-agent/project
B=/opt/tokkio-data0/naa/20261127/agent_b; RT=/opt/tokkio-data0/naa/20261127/artifacts/runtime; DI=/opt/tokkio-data0/naa/20261127/artifacts/direct/direct.jsonl
python3 scripts/need_aware/naa_sandbox.py --b-root $B -- write --runtime-root $RT --out $B
python3 scripts/need_aware/naa_sandbox.py --b-root $B -- embed --out $B --threads 20
python3 scripts/need_aware/naa_sandbox.py --b-root $B -- retrieve --runtime-root $RT --direct $DI --out $B
python3 scripts/need_aware/naa_sandbox.py --b-root $B -- materialize --runtime-root $RT --direct $DI --out $B \
  --manifest-dir $B/manifests/wp2-final --inventory /opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json \
  --retrieval '{"backend":"dense","unit_filter":"user_only"}' --budget 8192 \
  --logical-slots /opt/tokkio-data0/naa/20261127/wp2_v2/logical_requests.jsonl --gpu-seconds 43200 --max-physical-calls 1920
```
GPU（**仅在研究者写入批准后**；未批准时会在设备访问前拒绝）：
```
R=/opt/tokkio-data0/naa/20261127/agent_b/runs/wp2-final-model; mkdir -p $R/tmp $R/cache
export PYTHONPATH=src PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  TMPDIR=$R/tmp TMP=$R/tmp TEMP=$R/tmp HF_HOME=$R/cache HF_HUB_CACHE=$R/cache/hub TRANSFORMERS_CACHE=$R/cache/tf \
  XDG_CACHE_HOME=$R/cache TORCH_HOME=$R/cache/torch TORCHINDUCTOR_CACHE_DIR=$R/cache/inductor \
  TRITON_CACHE_DIR=$R/cache/triton CUDA_CACHE_PATH=$R/cache/cuda PYTHONPYCACHEPREFIX=$R/cache/pyc
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python scripts/need_aware/naa_agent.py infer \
  --manifest-dir /opt/tokkio-data0/naa/20261127/agent_b/manifests/wp2-final --run-root $R --approval <研究者批准 JSON>
# 中断后用同一命令续跑；结束后：
python3 scripts/need_aware/naa_agent.py export --manifest-dir ... --run-root $R --out $R/export   # 交 A 的 score_mcq.py
python3 scripts/need_aware/naa_agent.py aggregate --manifest-dir ... --run-root $R
```

## 8. 失败、风险与待研究者决定的事项

1. CI：已由 `b05f5f21` 解决（第 1 节）。今后新增的私有测试需要修订具名清单，这里只是提醒，B 没有新增任何私有测试。
2. **根分区仅剩 1.4 GiB**：真实运行的 storage_guard 要求 ≥1 GiB，余量很小，需要机器所有者处理。本次没有清理任何文件。
3. **Qwen3.5-9B 的 HF 路径在本项目中从未实跑过**（依赖已安装的 `fla` Triton kernel；没有 generation_config.json）。G0e 路径与 GE2 相同。首个技术烟测可能暴露加载或确定性问题，修复后在同一授权内续跑。
4. 偏差已版本化并公开：排除 system persona 档案；MCQ 指令放在最后一个 user 轮；B 的选择规则一次性更正（第 4 节）。
5. 续跑时，“已返回但未校验”的在途请求会重新调用一次（计入重试上限），而不是复用已落盘的输出。
6. Direct 未定位的 33 个任务（31 sensitive、2 forget）中 C/D 为 not_evaluable，A/B 照常报告；困难层的比例不能当作自然发生率。

## 9. 联合 WP2 有界申请（A 与 B 一致，等待一次批准）

- 范围：A 冻结的 240 个 val MCQ（240 persona）× G0e（Gemma-4-12B-it@707f0a3）与 Qwen3.5-9B@c2022362 × 四臂 = 1,920 个逻辑槽位；1,788 个可运行，132 个 not_evaluable 不调用。B manifest `9839c088…` 已与 A 槽位 `6dbd6b13…` 一一绑定。
- 上限：物理尝试 ≤1,920（含 ≤132 次重试），GPU 墙钟 ≤43,200 s（单张 A6000，两个模型顺序加载，每模型 21,600 s），每模型 ≤3 次加载；零付费、无外传、不训练、不开 test，开放生成 0 次（后续 ≤180 次/G 另行申请）。
- 技术烟测：G0e 的前 16 个物理调用（A 顺序中前 4 个任务 × 4 臂），计入上限；技术成功则同一授权内继续，失败则修复后续跑。到硬上限即停，并报告完成的配对前缀（任务顺序为预先声明的随机排列，前缀仍有代表性）。
- 预算核算（G0e 实测：GE2 的 139 次调用，解码约 0.074 s/token，预填充约 0.43 ms/token；Qwen 未测）：G0e 全部 894 次调用约为 15,100 s（平均输出 200 tokens）/ 21,700 s（300）/ 41,500 s（600）。因此 12 h 只在平均 MCQ 推理输出 ≲290 tokens 时能完整跑完。**唯一的等比例替代**：批准 57,600 s（16 h，每模型 28,800 s），可覆盖约 400 tokens 的平均输出。两种方案都不会自动扩容。
- 批准文件字段（由研究者写入，B 不会生成）：`protocol=naa-wp2-approval-v1, authorized=true, manifest_sha256=9839c088aee11f1b0ae8f2b82ba39cbce8afbf904e4e4a216cd240ed09734996, max_physical_calls≤1920, max_gpu_seconds（43200 或 57600）, models=["G0e","Qwen35"], researcher, decision_evidence, executor_checkout_head=<PR 合并后的干净 HEAD>`。
- 完成后交付：逐槽位终局/失败/重试账本、export → A scorer 的分组准确率与 persona 聚类 CI、A→B / B→C / C→D / 模型×(C,D) 的配对修复与退步、真实 GPU 秒数与时延 P50/P95，以及按第 10 节自动确定的单一修复候选。

## 10. WP3/WP4 实现候选（不提前训练）

- B→C 有缺口：B 已在 8k 内送达几乎全部用户陈述，因此缺口若出现，更可能来自“噪声/选择”而非召回。修复候选是更小预算下的 hybrid 重排或从 train 合法证据构造检索监督（一次），并以 B 原配置作对照。
- C→D 有增益：把 D 的投影从“仅限已送达单元”扩展为离线 Writer 的 store 级状态（遗忘链接、变化候选），作为可部署的“B 证据 + 状态”方法臂。它与 C 不再同信息，必须单独标注，并计入写入成本。
- C 已送证但仍然答错，且另一 G 能修复：交 A 做一次 G 适配（官方 train 3–5k，按 persona 分组）。
- 同信息下仍需应用控制：把当前目标、有效偏好与遗忘约束映射为 use/background/ignore/clarify，先规则、后监督；只有在同预算下出现可重复的序贯优势时才考虑 RL。
