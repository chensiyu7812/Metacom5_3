# Policy Manager Paper 1 Semantic Memory Compiler 执行修正（2026-08-17）

状态：`ACTIVE / RESEARCHER-APPROVED / PRE-OUTCOME / SCOPED IMPLEMENTATION AMENDMENT`

机器合同：`project/data/paper1_authority/paper1_semantic_memory_compiler_amendment_20260817_v1.json`

本修正只覆盖 MP/MS/ME candidate construction、semantic factual extractor/verifier、BGE-M3 formal semantic similarity、旧 regex/Jaccard 的 diagnostic 地位，以及 compiler API/cache/cost contract。它不是 ontology、研究范围或论文主张变更。

若旧代码、旧 zero-outcome artifact、execution blueprint 或 training contract 隐含地把 regex/string matching 当成正式 memory candidate constructor，或把当前 regex coverage 当成 ontology ceiling，以本修正为准。其他事项继续由既有 Paper-1 authority 按 `AGENTS.md` 的 precedence 管理。

## 1. 不变项

- 四头仍为 `RS / MP / MS / ME`。
- `RS` = Strategy-RAG；`MP` = Profile Memory only；`MS` = strict-past same-user cross-session event/continuity memory；`ME` = strict-past user action -> user-observed outcome experience。
- Route A、四个 standardized L2 logistic-regression heads、canonical background、0.5 primary policy rule不变。
- Generator 仍为 NVIDIA hosted NIM `meta/llama-3.1-8b-instruct`。Semantic Compiler 不是 Generator。
- public-only、outcome-isolated cross-fitting、exact-mechanical primary grouping、official benchmark priority 与 outcome lock 不变。
- 不允许 synthetic rescue、MP_PREFERENCE、background component bits、formal outcome、gold/reference/future leakage。

## 2. 正式 Semantic Memory Compiler

正式 MP/MS/ME candidate constructor 改为冻结的两阶段 semantic factual compiler：

1. semantic factual extractor；
2. deterministic grounding validator；
3. semantic factual verifier。

Extractor 与 verifier 使用同一冻结模型：

```text
provider: Alibaba Cloud Model Studio OpenAI-compatible API
model: qwen3-235b-a22b-instruct-2507
role: semantic factual extractor + semantic factual verifier only
mode: non-thinking
structured output: JSON object mode + local strict schema/Pydantic validation
```

该模型支持 JSON Object structured output；不得声称 provider 对该模型执行 strict JSON Schema enforcement。正式实现必须本地进行严格 schema、type、enum、cross-field 与 provenance validation。

同一模型的 extractor/verifier 不是独立模型验证。Semantic verifier 是额外 factual QA；deterministic grounding validator 仍是 hard protection。

## 3. 合法与禁止的 semantic judgment

允许 semantic factual understanding、ontology membership、coreference/entity linking 与 factual grounding，包括：

- MP：explicit durable profile fact、stable social role/relationship、occupation、education、location 与 authority 允许的 Profile fields；只抽 atomic profile fact，不把周围 episodic event 整体写入 MP；
- MS：completed prior event、state/change、continuity/thread、entity/time/status lineage；
- ME：user actually performed action、explicit user-observed outcome、cross-turn coreference、action/outcome same experience lineage；
- 区分 user actor 与 third party、completed action 与 future plan、observed result 与 purpose/goal/prediction；
- 检查 normalized statement 是否加入 source 不支持的内容；
- 用当前明确 span 与已链接 prior state 建立可追溯的 conflict/supersession/version lineage。

Extractor/verifier 永久禁止输出、估计、过滤或决定：

- `usefulness` / `helpfulness` / `quality_effect`；
- `relevance_to_current_target` / `transferability`；
- `worth_opening` / `should_open` / ON/OFF；
- `continuity_need` / `response_feasibility` / `scope_specificity`；
- 任何 resource utility、current-target marginal benefit、effect label 或 benchmark verdict。

负面、失败、尴尬或有害的历史 experience，只要满足 user action -> user-observed outcome 与同一 lineage，不能因“不值得复用”在 compiler 层删除。它当前是否值得打开由 ME head 从 paired effects 学习。

## 4. 输入边界与顺序

全部 401 个 EvoEmo sessions 按 owner 内 `(timestamp, session_id)` 的稳定顺序处理。每个 session 的一次正式工作流成功后缓存，不得因中断重复付费。

Extractor 只允许输入：

- current source session raw dialogue、明确 role/turn id；
- owner id、source session id、timestamp；
- strictly-past、已接受并冻结的 compact canonical entity/state table，仅用于 coreference/entity linking。

禁止输入：

- ES-MemEval question、gold、reference、evidence label；
- future session、formal outcome、ON/OFF/usefulness label；
- evaluator-only `basic_info`；
- official `observation` / `social_relationship` / `event_experience` annotations；
- generated treatment response 或 official scorer output。

Canonical table 不能作为事实补全源、candidate seed 或 relevance context。若 normalized statement 依赖 prior memory，必须通过 `linked_prior_memory_ids` 形成递归可审计的 source-grounded support chain。

## 5. 输出与 provenance

每个 atomic typed memory unit 必须包含：

- `owner_id`；
- `source_session_id`；
- `source_turn_ids`；
- exact supporting seeker span(s)，以及无歧义的 turn-local location；
- normalized semantic representation；
- typed memory class / subtype；
- entities；
- timestamp/status；
- `linked_prior_memory_ids`，仅在 cross-session resolution 必需时使用；
- compiler/verifier schema、prompt、request、source 与 response identity hashes。

ME 必须 reject：third-party action、future plan、hypothetical、advice-only、purpose clause masquerading as outcome、非 user-observed prediction、无法绑定到同一 experience lineage 的 action/outcome。

旧脚本 `project/scripts/v1_5/51_me_semantic_extraction_pilot_v1_5.py` 已发现的 third-party action、future-plan-as-action、purpose-as-outcome 三类错误必须成为 regression fixtures。旧脚本的 regex heuristics 只能作为 diagnostic，不是正式 semantic proof。

## 6. Deterministic grounding 与最终接受

Grounding validator 必须 fail closed 地检查：

- source/owner/session/turn IDs 存在；
- supporting spans 在对应 seeker turn 中逐字存在；
- seeker/supporter ownership 正确；
- timestamp、strict-past、wrong-owner、future 检查通过；
- 无 question/gold/reference/basic_info/official-annotation leakage；
- linked prior IDs 存在且递归指向已接受、source-grounded memory；
- normalized representation 没有 unsupported entity、state、time、actor、causal 或 outcome 内容。

最终接受规则固定为：

```text
schema valid
AND deterministic grounding pass
AND semantic factual verifier pass
```

Verifier rejection 不是 classifier negative，也不能影响 official target grouping。LLM semantic link 不得替代 primary exact-mechanical target/evidence grouping；broad semantic/shared-session union 仍只属于 sensitivity。

## 7. Cache、resume、retry 与 USD 5.00 hard budget

总 hard budget `USD 5.00` 覆盖 extractor、verifier、20-session smoke 与所有 retry。

> **2026-08-18 研究者批准的预算修正：`USD 2.00` → `USD 5.00`。** 原因：v6 20-session live smoke 实测单 session 真实成本约 $0.007–0.011（首个 session 因内容特别丰富略高），按此外推完成剩余 381 个 session 会超出原 $2.00 上限。此次修正只改预算数字，不改模型、prompt、schema 或研究范围。旧 `USD 2.00` 数字仅作历史 provenance 保留于 change log（`data/paper1_authority/paper1_semantic_memory_compiler_amendment_20260817_v1.json` 的 `cost_and_resume.hard_budget_usd_change_log`）。

正式实现必须：

- 每次 physical API attempt 记录 model/provider/region、phase、request hash、source/prior-table hash、prompt/schema/version、input/output/total tokens、latency、finish reason、retry reason 与按冻结官方价格估算的 USD cost；
- 使用 provider-reported usage；price snapshot、region 与公式进入 aggregate ledger；
- 调用前做 remaining-budget reservation；任何下一调用可能突破 hard cap 时停止；
- client 内部 retries 固定为 1；不允许 silent retry；
- 外层 retry 必须有明确 reason、独立 attempt record 与预算；
- 成功 cache content-addressed、append-only/atomic；resume 时不得重复成功调用；
- cache key 至少绑定 source、prior table、model/mode、prompt、schema、request parameters 与 compiler version；
- 前 20 sessions 是 runtime/semantic smoke，不是模型选择或 hyperparameter bakeoff；成功 cache 直接继续剩余 381，不重跑前 20。

任何 secret、API key、secret path/value 不得写入 repo、manifest、cache 或日志。向 external provider 发送 public EvoEmo raw dialogue 的 data egress 已由研究者仅为本 semantic compiler 明确批准。

## 8. BGE-M3 与旧 diagnostic

- BGE-M3 是 RS/MP/MS/ME formal semantic similarity encoder；首次正式物化前必须冻结 exact revision、pooling、normalization、query construction 与 artifact identity。
- Lexical Jaccard 降级为 diagnostic/baseline，不是正式 semantic similarity。
- 旧 MP/ME regex/string compiler 与旧 MS candidate surface 保留 diagnostic/baseline，不再作为正式 MP/MS/ME candidate constructor。
- 旧 `MP=3`、`ME=3` census 及 B21/B29/B30 blocker 保留历史 provenance，但统一标记：`pre-semantic-compiler diagnostic / not ontology ceiling / not active learnability evidence`。
- `current compiler coverage != ontology ceiling`。正式 semantic compiler 全量完成前，不得以旧覆盖宣称 head learnability failure。

## 9. 全量 compiler 后的报告与 official reference audit

全量完成后重新构建 MP/MS/ME candidate census，报告 unique candidates、owner coverage、target eligibility coverage、per-type distribution、cross-turn ME、conflict/supersession、verifier rejection reasons、grounding failure rate、actual token usage/estimated cost，以及 old-vs-new candidate yield/eligibility coverage。

在没有 reference denominator 时不得把 candidate-count difference 称为 recall。Official EvoEmo `observation` / `social_relationship` / `event_experience` 只能在 primary compiler output hash 已冻结后做 annotation-relative audit/reference，不得作为 main candidate 输入，也不得按 official annotations 反向调 prompt、筛选或补 candidate。

## 10. 当前停止点

截至本修正落盘时，Semantic Compiler 尚未实现或调用；smoke、formal outcome、training 与 benchmark 均未运行。Outcome lock 继续关闭。下一机器从本修正、remote-to-local handoff 与现有 Git branches 恢复。
