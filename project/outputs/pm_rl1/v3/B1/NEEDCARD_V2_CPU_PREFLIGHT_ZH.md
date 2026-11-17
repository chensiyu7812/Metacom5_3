# B1：A1 来源 cross_check、RS-v0 目录兼容性、20 个 NeedCard 试点的 CPU 输入预算与授权申请

- 证据等级：engineering_only。只用 CPU，只读 tokenizer、config 和 template 文件，**没有加载权重，writer 调用 0 次**
- 代码：`d06715bf`（cross_check），`173bed23`（以 A 的目录作为正式输入的预检）
- WS-A 输入来自 PR #8，head `a26998f0`，**尚未合入 integration**，所以本文都是集成前结果。PR #8 合入后用同一脚本重跑，核对一致
- 来源版本 `sources:c6ad9b15…`，bank `bank:02d0a4b1…`

## 1. A1 与 B1 临时 census 适配器的逐项 cross_check（`A1_cross_check_c6ad9b15/`）

| 比较项 | 范围 | 差异 |
|---|---|---:|
| 会话内容：rank、日期、dataset、family、祖先 family、transcript 哈希、原始文件哈希、complete | 401 个个人会话 | **0** |
| 逐轮：turn_index、角色、原文、raw_turn_sha256 | 401 个会话的全部轮次 | **0** |
| A1 的原始轮次编号 vs 普查原文中的 idx | 401 | **0** |
| 两边会话覆盖（一边有、另一边没有） | 双向 | **0** |
| 前缀：prefix_id、runtime_sha256、cutoff_rank、时间、family、祖先 family、fold、可见轮次 | 全部 4,119 个 | **0** |
| 每个前缀的严格过去会话列表，以及 A1 `visible()` 集合 | 4,119 | **0** |

- **派生字段**：`excluded_for_overlap` 由 A1 计算，B 的适配器从未设置过。它是 RS 侧的 family 排除标记，不是内容，所以不按"缺失"计；改为逐条核对它与 B0 自身的 family 规则（来自 ESConv 的会话，family 为 `esconv:*`）是否一致。85 个会话（84 个 family，p13 和 p18 共享 esc1198）全部一致。
- **元数据标签**（license、provenance_version、source_uri、source_split）在 401 个会话上都与 A1 不同。原因是适配器有意写了自己的来源标签，正文和身份都不受影响。这一项如实列出，不隐藏。
- **结论**：内容零差异。B1 从现在起改用 A1 来源（`needs.sources.a1_context`），已有的 B0 和 B1 框架文件不变。

## 2. A 提供的 RS-v0 策略类别目录：兼容性与限制

- 目录：A 在 PR #8 的 `a26998f0` 中交付 `RS_V0_STRATEGY_CATALOG.json`，身份 `pmrl1v3-rs-v0-strategy-catalog-1:7323c7f4…`。
- 来源：bank-v0 中 875 个 ESConv train 案例里**每个 supporter 轮次的原始策略标注**，共 12,403 个，逐条绑定 A1 source 和 SourceSpan。
- 标注字段：`quality=unverified`、`is_a4_method_catalog=false`，所有 definition 都为 unknown。
- B 用 A 自己的 `load()` 加载，它会按固定的原始标注重建目录并逐项比对。

**按 writer v2 输入要求逐项检查**（`rs_catalog.check_compat`，结果在 `needcard_cpu_preflight_v2_a1b_catalog/rs_v0_label_catalog.json`）：

| 要求 | 结果 |
|---|---|
| 每个条目都有 family_id、label、definition、writer_selectable | 满足 |
| 所有定义都是 unknown，没有把未核验案例描述成方法 | 满足（8/8） |
| 残余类 Others 不可选 | 满足；可选 7 类 |
| 声明 `unknown` 取值 | 满足 |
| 不是方法卡目录、质量未核验 | 满足 |
| 传给 writer 的只有 id、label、definition，没有案例正文、案例 ID、来源 ID | 满足 |
| 与 B 独立整理的标签列表核对：标签集合、可选集合 | 一致（B 的列表只用于核对；计数单位不同，不作比较） |

结论：**兼容**，作为 writer v2 的正式标签输入。

**各类别计数（A 的口径：原始 supporter 标注）**：

| 类别 | 含该类别的案例数 | 标注轮数 | writer 是否可选 |
|---|---:|---:|---|
| question | 834 | 2,568 | 是 |
| affirmation_and_reassurance | 774 | 1,953 | 是 |
| others | 761 | 2,252 | 否 |
| providing_suggestions | 728 | 1,991 | 是 |
| self_disclosure | 628 | 1,149 | 是 |
| reflection_of_feelings | 586 | 976 | 是 |
| restatement_or_paraphrasing | 493 | 706 | 是 |
| information | 452 | 808 | 是 |

**限制（逐条核实，不影响兼容性结论，但限制了 method 字段的含义）**：

1. 这些是对话动作标签，不是方法。每个案例平均含 6.0 个不同类别（中位 6；可选类别 5.1 个），question 出现在 875 个案例中的 834 个，所以**类别几乎不能区分案例**。
2. A 的 RS 检索（v0 词面检索）不使用类别，所以 NeedCard 的 method 类别**只是评价侧的注记**，不影响读到哪个案例。
3. 没有专家审核，也没有临床、因果或有效性的结论；这些数据此前已在研究中使用过，不是独立证据。

为此，writer 协议 v2（`pmrl1v3-needcard-writer-v2`，v1 不变）把 `method_need` 限定为三类值：null、一个可选类别，或 `unknown`。它只表达"当前可能需要方法性资源"：

- 只有当前对话显示求助者在要办法、主意、步骤或信息时才填写，并且必须引用当前对话中经过核验的原话；
- 提示写明类别是历史对话策略标签，"NOT validated or professional methods"，定义未知；
- 只有当某个类别明显就是所求帮助的类型时才选它，否则填 `unknown`，不生成任何方法卡；
- 检查表 v2 的 R 项不写类别名。

B 在 A 的目录出现之前自行整理过一份标签列表（`needcard_cpu_preflight_v2/`，`d06715bf`）。它现在只作核对，该目录已被下面的结果取代，保留作历史记录；两次的 token 数完全相同。

## 3. 20 个试点前缀的 CPU 输入预算（`needcard_cpu_preflight_v2_a1b_catalog/`）

- 前缀：`coverage_sample_v1.jsonl` 中第 1–5 折的固定 20 个（每折 4 个，按 early、mid、late 分段），第 6 折不进入。
- **原生 tokenizer**：Qwen3.5-9B，文件哈希由 A1 资产审计固定；身份 `native-tokenizer:601f9509…`。按 writer 的完整 chat prompt 计数：非思考模式，加生成提示。
- **原生 context**：262,144（来自模型 config）；单次最大输出 800。
- **writer 身份**：`pmrl1v3-needcard-writer-v2|qwen3.5-9b|92578935…`。模型文件集合的 SHA 为 `5f526cd0…`，来自审计清单，没有读取权重。

| 项 | 最小 | 中位 | 最大 | 20 个合计 |
|---|---:|---:|---:|---:|
| 完整 prompt token | 3,739 | 13,980 | 27,009 | 277,880 |
| 其中严格过去 RAW | 2,348 | — | 25,620 | — |
| 其中 RS-v0 类别列表 | 248 | 248 | 248 | — |
| 过去会话数 | 2 | — | 20 | — |
| 过去原文字符 | 4,422 | — | 46,530 | — |

- 加上 800 输出后，最多只占原生 context 的 **10.6%**。没有任何截断；运营上限暂设为 32,768 输入 token（等 A0 实测再定），也全部低于。
- **合法性**（20 个前缀全部为真）：
  - prefix_id 等于 B0；
  - A1 的 `verify_source_context` 通过；
  - 过去会话同一 owner、严格早于切点，且是完整会话；
  - 当前窗口不超过 cut_turn；
  - A1 `visible()` 中没有未来会话。
- 每个前缀都记录了来源版本、全部 source_id 的哈希和 pack_sha256。输入包本身可从固定输入重建，因此没有另存。

### 状态定义（互不混用）

| 状态 | 何时判定 | 是否调用 writer | 含义 | 本次 20 个前缀 |
|---|---|---|---|---:|
| blocked_catalog | 调用前 | 否 | 没有类别目录 | 0（如果没有目录，则 20 个都是此状态） |
| over_budget_native | 调用前 | 否 | prompt + 800 超过原生 context | 0 |
| over_budget_operational | 调用前 | 否 | prompt 超过运营上限 | 0 |
| ready | 调用前 | 是 | 可以运行 | **20** |
| writer_failed | 调用后 | 已调用 | 输出不合规，重问 1 次后仍不合规；**不记为 none** | — |

超预算不算 writer 失败，也绝不截断后再运行。

## 4. 模型调用预算与授权申请（**尚未获得授权，没有运行 Qwen**）

| 项 | 申请上限 |
|---|---|
| 范围 | 上述固定的 20 个试点前缀，writer v2，A 的 RS-v0 目录，只生成 NeedCard；不生成终点，不运行 J1/J2，不跑 B6e |
| 模型 | 本地 Qwen3.5-9B（文件集合 SHA `5f526cd0…`），非思考、贪心解码，max_new_tokens=800 |
| 调用次数 | ≤ 40（20 次首次调用 + 最多 20 次重问） |
| 预填充 token | 277,880（首轮）；如果全部重问，最多 555,760 |
| 输出 token | ≤ 32,000 |
| 显存 | bf16 权重 18.0 GiB（A0 按文件大小记录）；8 个全注意力层的 KV 约 32 KiB/token，27.8k token 时 ≤ 0.9 GiB；24 个线性注意力层的状态约 48 MiB。激活和工作区**未实测**。按 A0 规则，要求空闲 ≥ 30 GiB |
| 卡 | 只用 A6000 `GPU-ba5f65be…`，与 WS-A 错开使用 |
| 时间 | **未实测**。按 vLLM 批处理估计约 10–30 分钟，HF 单流约 30–60 分钟，都只是假设 |
| 付费 API | 0 |
| 失败处理 | 停止并记录，不扩大规模；writer_failed 如实计入，不重跑挑选 |
| 运行之后 | 由 B 逐张核对 20 张卡的 history 证据是否真实存在、是否严格过去（错误率须 ≤ 10%）；然后为这 20 个前缀冻结 v2 检查表 |

**授权前还需要**：

1. PR #8（A1/A1b）由集成负责人正式合入，并在 integration 上重跑本预检，确认结果一致；
2. A0 在 A6000 上实测 Qwen 的显存，或者授权本次运行顺带记录峰值显存。
