# B1：A1 来源 cross_check、RS-v0 目录兼容性、20 个 NeedCard 试点的 CPU 输入预算与授权申请

- 证据等级：engineering_only。只用 CPU，只读 tokenizer/config/template 文件，**没有加载权重，writer 调用 0 次**
- 代码提交：`d06715bf`。WS-A 输入取自 PR #8 的 `a0771e1e`（A1 `7116b8bd`、A1b `c9dd5aae`），这些提交**尚未合入 integration**。所以本文是集成前结果；PR #8 合入后用同一脚本重跑，并核对结果逐字节相同
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

## 2. RS-v0 "策略类别目录"的兼容性与限制

**A 实际交付了什么**：bank-v0 中有 875 个 ESConv train 完整对话案例（view=case），每个案例的 body 列出旧 `strategy_ids` 和 `treatment_ids`。A 明确说明"RS 完整案例不能冒充 B1 所需 MethodCatalog"。**A 没有交付独立的策略类别目录文件。**

**B 做了什么**：`needs/rs_catalog.py` 机械地整理出标签列表（`rs_v0_label_catalog.json`）：

- 从 bank-v0 RS 案例的 strategy_ids，到 A1 资产审计固定哈希的 `strategy_cards_v1_5`，再到 ESConv 的 8 个策略标签；
- 没有写任何定义，也没有生成任何方法卡。

| 标签 | 含该标签的案例数 | 策略轮数 | writer 是否可选 |
|---|---:|---:|---|
| question | 782 | 2374 | 是 |
| affirmation_and_reassurance | 732 | 1846 | 是 |
| others | 720 | 2127 | **否**（残余类，没有内容） |
| providing_suggestions | 683 | 1866 | 是 |
| self_disclosure | 587 | 1069 | 是 |
| reflection_of_feelings | 547 | 901 | 是 |
| restatement_or_paraphrasing | 466 | 654 | 是 |
| information | 423 | 753 | 是 |

**限制（逐条核实）**：

1. 每个标签的定义都记为 `unknown`。原 `guidance_text` 对全部 11,590 行都是同一句通用模板，只是标签名不同，不能算定义。
2. 这些标签描述的是对话动作，不是方法。823 个有策略的案例平均每个含 6.0 个不同标签（中位 6），例如 question 出现在其中 782 个，所以**标签不能区分案例**；另有 52 个案例没有任何 strategy_id。
3. A 的 RS 检索（v0 词面检索）完全不使用标签，所以 NeedCard 的 method 标签**只是评价侧的注记**，不影响读到哪个案例。
4. 没有专家审核，也没有方法有效性的结论。

**因此修改了 writer 的输入要求**（writer 协议 v2，`pmrl1v3-needcard-writer-v2`；v1 保持不变）：

- `method_need` 只能取三类值：null、一个可选标签，或 `unknown`。它只表达"当前可能需要方法性资源"：只有当当前对话显示求助者在要办法、主意、步骤或信息时才填写。
- 提示中写明这些标签是历史对话策略标签，"NOT validated or professional methods"，定义未知；只有当某个标签明显就是所求帮助的类型时才可选用，否则填 `unknown`。
- method 必须引用当前对话中经过核验的原话，否则删除。
- 检查表 v2 的 R 项不写标签名。

**仍需确认**：这份标签列表是 B 根据 A 的数据机械整理出来的，并非 A 正式交付的目录。请 A 或研究者确认是否接受它作为 RS-v0 的 writer 输入；如果不接受，method 字段只允许 null 或 `unknown`，其他 CPU 结论不变。

## 3. 20 个试点前缀的 CPU 输入预算（`needcard_cpu_preflight_v2/`）

- 前缀：`coverage_sample_v1.jsonl` 中第 1–5 折的固定 20 个（每折 4 个，按 early、mid、late 分段），第 6 折不进入。
- **原生 tokenizer**：Qwen3.5-9B，文件哈希由 A1 资产审计固定；身份 `native-tokenizer:601f9509…`。按 writer 的完整 chat prompt 计数：非思考模式，加生成提示。
- **原生 context**：262,144（来自模型 config）；单次最大输出 800。
- **writer 身份**：`pmrl1v3-needcard-writer-v2|qwen3.5-9b|92578935…`。模型文件集合的 SHA 为 `5f526cd0…`，来自审计清单，没有读取权重。

| 项 | 最小 | 中位 | 最大 | 20 个合计 |
|---|---:|---:|---:|---:|
| 完整 prompt token | 3,739 | 13,980 | 27,009 | 277,880 |
| 其中严格过去 RAW | 2,348 | — | 25,620 | — |
| 其中标签目录 | 248 | 248 | 248 | — |
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
| blocked_catalog | 调用前 | 否 | 没有标签目录 | 0（如果没有目录，则 20 个都是此状态） |
| over_budget_native | 调用前 | 否 | prompt + 800 超过原生 context | 0 |
| over_budget_operational | 调用前 | 否 | prompt 超过运营上限 | 0 |
| ready | 调用前 | 是 | 可以运行 | **20** |
| writer_failed | 调用后 | 已调用 | 输出不合规，重问 1 次后仍不合规；**不记为 none** | — |

超预算不算 writer 失败，也绝不截断后再运行。

## 4. 模型调用预算与授权申请（**尚未获得授权，没有运行 Qwen**）

| 项 | 申请上限 |
|---|---|
| 范围 | 上述固定的 20 个试点前缀，writer v2，只生成 NeedCard；不生成终点，不运行 J1/J2，不跑 B6e |
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
2. 确认是否接受第 2 节中的标签列表；
3. A0 在 A6000 上实测 Qwen 的显存，或者授权本次运行顺带记录峰值显存。
