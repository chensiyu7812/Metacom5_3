# B 工作线：WP2 必要修复与真实 GPU 运行

日期：2026-11-27 – 11-28（JST）。依据研究者决定原文 [WP2_RESEARCHER_DECISION_20261127_ZH.md](WP2_RESEARCHER_DECISION_20261127_ZH.md)。本文件中“模型结果”指真实 GPU 推理产生的输出；准确率由 A 的评价进程给出，B 不读取 evaluation sidecar。原文、请求、模型输出只保存在服务器 `/opt/tokkio-data0/naa/20261127/agent_b/`。

## 1. 保留与新版本

| 对象 | 旧版本（保留，未覆盖） | 执行版本 |
|---|---|---|
| Memory Writer / store | `naa-memory-writer-v1`，`task_stores.naa-memory-writer-v1.jsonl` | `naa-memory-writer-v2`，`task_stores.naa-memory-writer-v2.jsonl` |
| Reader / prompt | `naa-memory-reader-v1` / `naa-arms-prompt-v1` | `naa-memory-reader-v2` / `naa-arms-prompt-v2` |
| BGE 向量 | 300 个 v1 cache 文件 | 按“unit id + 文本 hash”核验完全一致后复用（300 个重新编键，重算 0 个） |
| manifest | `9839c088…`（43,200 s，未运行） | `c370103cc76f5ccc8b8e56b388764afe1a308e6eda1e287a8b3b535a058588d3` |
| A 逻辑槽位 | `wp2_v2` `6dbd6b13…` | 同一文件，1,920/1,920 一一绑定 |
| plumbing 账本 | `runs/*-plumbing*/plumbing/` | 真实运行只在 `runs/wp2-exec-v2-model/model/`，两者 `result_kind` 不同 |

## 2. 语义修复（确定性规则，无新增在线模型）

- 说话人与主体分开。`speaker`/`speaker_role` 是宿主事实；`fact_subject`（事实主体）和 `preference_holder`（偏好持有者）在 writer 中一律为 `not_determined`，不做推断。实测 69,261/69,261 个单元均为该值。所有单元的 `statement_kind=verbatim_statement`，没有任何系统推断被存为记忆。
- 用户发言提到他人（如“my mom / my friend / my colleague”）时，只标注 `third_party_mention` 线索，共 1,535 条，不据此决定主体。D 的说明为“may describe that person rather than the user”。
- 时间：去掉 v1 的 “Most recent user statement” 和 “later usually reflects the current preference”。`possible_update` 改名为 `explicit_change_statement`（94 条）。D 的说明为：只有同一人、同一属性、同一情境时，后者才替换前者，否则两者可能同时成立。
- 遗忘：5,130 条请求中 112 条为 `lexical_candidate`，5,018 条为 `unknown_not_linked`。不删除任何证据。D 的说明为：只适用于请求所指的信息，所指不明时不猜。本轮研究的是模型对历史中约束的理解，不是生产级删除功能。
- 原文行统一写明 `said by: <speaker>`（A/B/C/D 相同）。v1 的 “Statements by the user describe the user” 已删除，测试会断言它不再出现。
- A 改名为 **Recency Baseline**（`recency_baseline`）：近期历史窗口，不是“无记忆”。B 仍为 dense user_only@8192，覆盖几乎全部用户发言，但不覆盖 Direct span 中的 assistant 参考回复（Direct recall .500），因此 100% 用户陈述覆盖不等于 100% 证据覆盖。
- C/D：414/414 对的送达 id 与文本 hash 完全相同。新增的 “said by:” 使每行多几个 token：在 8192 预算边缘，A 有 85 个槽、B 有 47 个槽（每个模型）少装 1–2 个单元（A 的连续窗口偶尔少 7–10 个）；C/D 不变。构念不变，差异如实记录。

## 3. 运行器修复（runner/budget v2）

- 停止分为三类。ModelStop（本模型份额、加载上限、本模型连续失败、技术烟测）只停该模型并释放设备，下一个模型照常运行。GlobalStop（全局 GPU 秒、总物理尝试、范围完整性）和 SafetyStop（历史设备 guard 或存储 guard 拒绝）停止全部。RequestSkip（单请求 2 次尝试、全局 132 次重试余量）只跳过该请求，记为 EXHAUSTED。
- 每个 session 都在 finally 中写 MODEL_SESSION_END（中断时也写）。崩溃时若有在途的加载或请求，按其完整超时计入 GPU 秒，续跑不会多出时间。单请求超时取 min(300 s, 全局剩余, 本模型剩余)。设备 guard 拒绝不再被当作可重试失败。
- 测试：43 项 CPU 测试，包括“第一个模型份额耗尽后第二个模型在自己份额内跑满”、“全局物理上限或安全停止时第二个模型不加载”、“烟测失败只停该模型”、“崩溃保守计时”。

## 4. 机器风险（实测，未删除任何他人文件）

根分区 879G，可用 1.2–1.5 GiB。本实验的所有 TMPDIR / HF / Triton / Torch / CUDA cache、worker 日志和账本都在数据盘（`runs/wp2-exec-v2-model/`），存储 guard（根分区 ≥1 GiB、数据盘 ≥4 GiB）会在每次请求前执行，拒绝即全局安全停止。我只删除了自己建的 53 MB 临时 venv。要让根分区达到约 5 GiB 余量，需要机器所有者在下列位置中选择处理（我只测量，未删除）：

| 位置 | 大小 | 性质 / 理由 |
|---|---|---|
| `~/.cache/pip` | 6.9 G | pip 下载缓存，可重新下载；`pip cache purge` 即可 |
| `/tmp/pmrl1-wsa-crossline-52_lv4nm`、`/tmp/pmrl1-{backend,local,publish,runtime-fix}-check-202610*` | 3.8 G + 约 2.6 G | 10 月的旧检查 worktree（已登记在 git worktree 中），应由所有者确认后执行 `git worktree remove` |
| `/tmp/pmrl1-publication-20261022-venv`、`/tmp/pmrl1-review-20261022-venv` | 1.4 G + 49 M | 10 月的临时 venv |
| `~/.cache/huggingface` | 27 G | 模型缓存（bge-m3、Qwen3-Embedding 等），可能仍在使用，建议迁到数据盘而不是删除 |
| `/var/log` | 4.3 G | 系统日志，需 root 处理 |

## 5. 批准与执行身份

批准文件 `/opt/tokkio-data0/naa/20261127/agent_b/authorization/WP2_EXEC_V2_APPROVAL.json`（`naa-wp2-approval-v1`）：manifest `c370103c…`、HEAD `96e5300316b941ee20b36ba0c9a3e83aed314a29`（干净）、models `["Qwen35","G0e"]`、物理尝试 ≤1,920、GPU ≤57,600 s、每模型 ≤28,800 s。`researcher` 字段注明“依据会话中的书面指令，不是研究者本人签名”；`decision_evidence` 指向决定原文及其 SHA-256 `ef587373…`。运行前离线 `authorize()` 通过。执行顺序先 Qwen3.5（从未实跑过的路径先经过烟测），再 G0e；模型内沿用 A 的冻结任务与四臂顺序。

## 6. 真实运行结果（GPU，result_kind=model）

运行：2026-11-27 13:52 UTC – 2026-11-28 05:04 UTC，单张 A6000（`GPU-ba5f65be…`），Qwen3.5-9B 先、Gemma-4-12B-it 后，顺序执行，GPU 上无其他作业。终态 `RUN_SUMMARY status=STOPPED`：Qwen 队列跑完；G0e 在自身 28,800 s 份额处 ModelStop；无 GlobalStop、无 SafetyStop、无加载失败。账本头 `be05bddd7f38…`，A 封存导出 `dd31f24df2e8…`。

### 6.1 请求与完成

| 模型 | 条件 | 逻辑位置 | not_evaluable | 可执行 | 完成 | 失败尝试 | 重试 | 未完成（预算） |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen35 | A Recency | 240 | 0 | 240 | 240 | 0 | 0 | 0 |
| Qwen35 | B dense user_only | 240 | 0 | 240 | 240 | 0 | 0 | 0 |
| Qwen35 | C Direct | 240 | 33 | 207 | 207 | 0 | 0 | 0 |
| Qwen35 | D Evidence+State | 240 | 33 | 207 | 207 | 0 | 0 | 0 |
| G0e | A | 240 | 0 | 240 | 194 | 0 | 0 | 46 |
| G0e | B | 240 | 0 | 240 | 194 | 0 | 0 | 46 |
| G0e | C | 240 | 33 | 207 | 168 | 1 | 0 | 39 |
| G0e | D | 240 | 33 | 207 | 168 | 0 | 0 | 39 |
| 合计 | | 1,920 | 132 | 1,788 | 1,618 | 1 | 0 | 170 |

- 物理尝试 1,619 / 1,920；重试 0 / 132；每模型加载 1 / 3。
- 唯一失败：`pm2-val-01476-mcq|C|G0e`，份额边缘截断。该请求开始时 G0e 只剩 8.98 s，超时按剩余份额设定，worker 到截止时间被终止（`worker exited without complete response`）；随后 ModelStop，没有重试。这不是模型或运行环境错误。
- 170 个未完成位置全部属于 G0e，原因是份额耗尽，从未调用模型。完整清单在 `RUN_SUMMARY.pending_logical` 和 `MODEL_STOP.pending`。执行顺序按任务分块、块内四臂随机，所以 G0e 四臂完成的是同一段任务前缀（168 个共同 Direct 任务、194 个共同全集任务），可以完整配对。
- 132 个 not_evaluable 是 C/D 中 Direct 未定位的 33 题 × 2 臂 × 2 模型，结构性跳过，从未调用模型。

### 6.2 Token、时延、GPU 时间

| | Qwen3.5-9B | Gemma-4-12B-it |
|---|---:|---:|
| 完成请求 | 894 | 724 |
| 输入 token 合计（native） | 4,291,051 | 3,490,280 |
| 输出 token 合计 | 540,982 | 367,497 |
| 长度停止（1,024） | 181（A 35 / B 80 / C 22 / D 44） | 11（5 / 3 / 1 / 2） |
| 加载（worker 内 / 含 spawn+guard+IPC） | 28.2 s / 38.0 s | 36.1 s / 45.5 s |
| 生成时延 P50 / P95 | 26.0 / 48.6 s | 38.4 / 61.5 s |
| 内部首 token P50 / P95 | 1.29 / 1.61 s | 3.37 / 4.92 s |
| 输出吞吐（输出 token / 生成秒） | 21.07 tok/s | 12.86 tok/s |
| 每请求占用（GPU 秒 / 完成数） | 29.0 s | 39.8 s |
| 显存峰值（reserved） | 21.0 GB | 31.8 GB |
| 账本 GPU 占用 | 25,921.6 s | 28,800.5 s |

- 两模型合计 54,722.2 s（上限 57,600 s）。在同一 1,024 上限和同样输入下，Qwen 的输出吞吐是 G0e 的 1.64 倍，每小时完成 124 个请求，G0e 为 90 个。
- 按条件分：A/B 输入约 7.9–8.4k token，首 token 约 1.3–1.6 s（Qwen）/ 4.3–4.6 s（G0e）；C/D 输入约 0.85–1.15k token，首 token 约 0.18–0.43 s。逐条件的 P50/P95 在 `AGGREGATE.json.by_model_arm`。
- **时延口径**：所有时延都是 worker 侧单调时钟：生成时间，以及 worker 内部观察到的第一个生成 token。它们**不是** Tokkio 客户端端到端响应时间，不含网络、前端、排队或流式传输。
- **teardown 计时（A 审查发现）**：本次账本的 MODEL_SESSION_END 写在关闭 worker 之前，因此 teardown 不在账本内。按账本事件间隔，Qwen 的 teardown ≤1.48 s，G0e ≤1.19 s，所以实际 GPU 占用 ≤54,724.9 s。G0e 的账本戳 28,800.53 s 比份额多 0.53 s，原因是最后一个请求的终止延迟。两处都已在运行后修复（3bd31d6c、5482fff7：teardown 计入占用；会话和请求都在“剩余 − teardown 预留”内结束）。修复只影响以后的运行，本次账本不改。

### 6.3 来源隔离

真实输出只在 `runs/wp2-exec-v2-model/model/` 和 `export/`，`result_kind=model`，run_id 为 `naarun:a19662b8…`。旧 plumbing 输出只在 `runs/*-plumbing*/plumbing/`，`result_kind=plumbing`，A 的评分器拒绝把它们当作模型结果。两者 manifest、账本目录和 run_id 都不同，评分只用 A 从 model 账本封存的导出。B 全程未读取 evaluation sidecar；准确率全部由 A 的 watcher 进程在 RUN_SUMMARY 之后自动计算，B 只读取 A 的聚合报告。

## 7. A 的评分（摘自 A `MODEL_STATISTICS.md`，规则 `18d863f6…`）

共同可评价的 207 个 Direct 任务，完成准确率（解析失败按错误计）：

| | A Recency | B dense | C Direct | D Evidence+State |
|---|---:|---:|---:|---:|
| G0e（168 完成） | 33.9% | 47.6% | **69.6%** | 67.3% |
| Qwen35（207 完成） | 31.9% | 26.1% | **63.8%** | 57.0% |

预定配对比较（右减左；persona 聚类 bootstrap；Holm 校正 8 组）：

- B→C：G0e +22.0 pp，[14.3, 30.4]，修复/退步 45/8，p=1.7e-6；Qwen +37.7 pp，[29.5, 45.4]，86/8，p=9.9e-17。
- A→B（240 题全集）：G0e +12.9 pp，p=0.011；Qwen −5.0 pp，[−12.1, 1.7]，p=0.56。
- C→D：G0e −2.4 pp，p=0.57；Qwen −6.8 pp，[−12.1, −1.9]，p=0.081。
- 只看以 EOS 结束的输出：Qwen 的 B 为 39.4%（A 36.6%），D 为 71.8%（C 70.8%）。因此 Qwen 的 A→B、C→D 下降主要来自长度截断后无法解析（B 解析失败 71/240，D 35/207），不是选择错误。
- Direct 缺失的 33 题是非随机缺失（31 个 sensitive、2 个 forget）：C/D 对 sensitive 类别没有测量。官方题面要求“回忆偏好”，所以本轮不证明自主需求识别、自然陪伴或开放生成质量。

## 8. 后续瓶颈提案（B 草案，待 A 结合错误审阅确认）

**瓶颈：运行时证据选择。** 系统拿到了证据，但没能把正确的那几条交给模型。

- 现象：B 以约 7.9k token 覆盖几乎全部用户陈述；C 用约 0.85k token 的离线定位原文（同样的原文格式和 “said by” 行），两模型都提升 22–38 pp。B→C 的修复集中在更新和遗忘类任务：G0e 41 对中修复 22、退步 0；Qwen 54 对中修复 31、退步 2。也集中在 `who:self`。D 的指导在 C 之上没有增益。
- 混杂（A 的归因说明）：B 同时缺少 assistant 参考回复，并且噪声更多，所以 B→C 无法区分“证据不可得”和“证据被淹没”。
- **具体路径：**
  1. 代码：在 `agent/retrieval.py` 增加 `locator` 检索。候选池为 writer 的全部单元（user + assistant；在 `RetrievalSpec` 增加 `pool=all`）。先用 BGE dense 召回 top-64，再用 CPU cross-encoder 重排，得到约 1k token 的证据，格式与 C 相同。
  2. 训练：在 A 的 4,000 个训练候选上（persona 与 dev 不重叠），用 A 的同一 Direct 定位器离线生成证据标签，训练这个重排器（pairwise 或 listwise，只用 CPU 或单卡短训）。
  3. 先做 CPU 门槛：在 240 个 dev 任务上，用已有 Direct span 离线计算 Direct span recall@1k（只用 A 的离线文件，不调用模型）。达到预定门槛后，才申请一次 WP3 GPU 对照：B（user_only@8k）、B+assistant@8k、locator@1k、C。这同时拆开 A 指出的混杂。
- 不在本轮执行：不启动新的语义能力实验，不恢复 G7、INSPECT_CLAIM、GSWS 或 PPO。上述 WP3 需要研究者另行批准。

另一个需要在下一版协议中处理的测量问题：Qwen 在 1,024 token 上限下有 181 次长度截断，在长上下文的 B 中最多（80 次）。这使 Qwen 的 B/D 数字偏低。是否放宽 `max_new_tokens` 或改为先答后述，属于解码协议变更，应作为新版本冻结，不回写本轮结果。

## 9. 可复跑命令（服务器内，PYTHONPATH=src）

```bash
PY=/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python
M=/opt/tokkio-data0/naa/20261127/agent_b/manifests/wp2-exec-v2
R=/opt/tokkio-data0/naa/20261127/agent_b/runs/wp2-exec-v2-model
# 真实运行（需要与 manifest、干净 HEAD 绑定的批准文件；断点续跑与精确去重）
bash $R/RUN.sh   # = $PY scripts/need_aware/naa_agent.py infer --manifest-dir $M --run-root $R --approval .../WP2_EXEC_V2_APPROVAL.json
$PY scripts/need_aware/naa_agent.py aggregate --manifest-dir $M --run-root $R   # -> $R/model/AGGREGATE.json
$PY scripts/need_aware/naa_agent.py export    --manifest-dir $M --run-root $R --out $R/export
# 评分在 A 的评价进程（B 不运行）：A 仓库 scripts/need_aware/watch_wp2_evaluation.py -> seal_wp2_export + evaluate_wp2
```

模型输出、请求原文、账本和权重只在服务器；仓库只含代码与本文中的聚合数字。
