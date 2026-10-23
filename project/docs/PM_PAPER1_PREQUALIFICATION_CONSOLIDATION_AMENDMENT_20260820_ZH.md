# Policy Manager Paper 1 资格审查整合修订（2026-08-20）

状态：`ACTIVE / SCOPED PRE-QUALIFICATION EXECUTION AMENDMENT / ZERO OUTCOME`

机器合同：`project/data/paper1_authority/paper1_prequalification_consolidation_amendment_20260820_v1.json`

本修订只收束资源、执行与测量资格审查顺序，不重写四头、Route A、L2 learner、0.5 primary rule、公开数据边界、冻结 Generator 或官方 benchmark 层级。与旧文本冲突时，本修订仅在本页列出的 scope 内优先；execution reconciliation 对 soft/binomial effect supervision 与无 empirical PASS gate 的覆盖继续有效。

## 1. 唯一执行顺序

```text
Resource Qualification
→ Treatment / Execution Qualification
→ Measurement / Evaluator Qualification
→ Resource Amount Calibration
→ PM effect construction and training
→ Confirmatory Evaluation
```

前一层未完成不得把后一层称为已冻结。资格审查是测量与完整性前门，不是用 qualification 样本预估 PM/Ours 正式收益。

## 2. 四把独立 outcome lock

以下四锁当前均为 `CLOSED`：

- `RQ1_RS_CALIBRATION_OUTCOME_LOCK`
- `RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK`
- `RQ1_CONFIRMATORY_OUTCOME_LOCK`
- `RQ2_CONFIRMATORY_OUTCOME_LOCK`

RS 与 memory 的 calibration 可分别获批；任何一条 calibration 解锁都不隐含 confirmatory 解锁，也不授权另一条研究线。旧 umbrella lock 仅作 fail-closed 兼容入口，必须同时验证四锁。

## 3. 决策状态词表

机器 Master Decision Register 的 `status` 只能取：

`FROZEN / READY / EXPERIMENT_REQUIRED / AUDIT_REQUIRED / IMPLEMENTATION_PENDING / BLOCKED`。

`FROZEN` 仅表示已有 authority 或研究者显式批准且身份已绑定；代码存在、离线测试通过或材料已生成最多只能证明 `READY`。`RESEARCHER-READY-TO-FREEZE` 作为 readiness label，只能搭配机器状态 `READY`。

## 4. RS canonical retrieval 与 amount protocol

15,061 个 atomic units 按 **byte-exact rendered treatment identity** canonicalize 为 13,172 个 ranking tickets。每个 ticket：

- 只保留一个确定性 representative retrieval document 和一个 BGE 分数；
- union 全部 source-card / dialogue / atomic-unit provenance，用于 leave-dialogue-out；
- occurrence 次数不得形成额外 retrieval prior；
- near duplicate 全部保留，不用任意语义阈值删除。

正式 zero-outcome 检索物化必须从 canonical tickets 直接排名 Top-8，不能把 raw Top-4 结果事后 collapse 当 Top-8。报告 `k={1,2,3,4,6,8}` 的 coverage、相似度、family diversity、same-source-card、token、alias/backfill 和完整身份 hash。

Generator calibration 协议继续为 pure-k：初始 `k={0,1,2,3,4}`，共同 non-binding cap=`384`，实际 injected tokens 另记；只有 calibration best 位于 k=4 边界且未平台化时，才按预注册规则扩展 `{6,8}`。本修订不授权任何 Generator outcome。

## 5. 三层 qualification

### 5.1 RS Resource-Semantics Qualification

qualification pool 必须与未来 ESC calibration/confirmatory role cards 隔离，优先来自 ESConv train/dev 或专门公开 qualification pool。审查对象包含 visible state/query、canonical move、完整 provenance、family、rank/similarity 与 exact rendered treatment。rubric 固定检查 atomicity、state appropriateness、boundary compatibility、executability、leakage、redundancy/near-duplicate。机器包与 rubric 可先物化，但 LLM 不得冒充最终 human qualification。

### 5.2 RS Treatment / Execution Qualification

同一隔离 state 构造 OFF（无 RS）与 ON（恰好一个指定 exact move）。记录 treatment/prompt/response/hash/trace、是否反映 intended move、额外动作、mechanical failure、tokens/latency。Step2 只做 deterministic validity 与 typed execution，不增加 learned/LLM utility filter。semantic non-use 或 misuse 在正确 delivery 后属于真实 effect，不得事后过滤；qualification 的 blind adherence review 只验证执行层是否可测。

### 5.3 Measurement / Evaluator Qualification

ESC-RANK 是官方 anchor 与 primary candidate，但在 runtime qualification 前不得声明为唯一获胜 evaluator。候选集合保留 ESC-RANK、Qwen general judge、DeepSeek general judge，以及一个待研究者指定的独立模型家族。选择顺序固定为 validity/agreement first，bias/sensitivity second，cost/latency third；严禁按哪个 judge 让 PM/Ours 分高来选。

## 6. Semantic Memory compiler 精度修复

Qwen Semantic Compiler、MP/MS/ME ontology 与数量目标不变。本轮只允许一般化 prompt/schema/deterministic gate 精度修复：

- MP 必须由当前 exact support 直接蕴含；prior memory 只能帮助消歧，不能补出缺失事实；排除 transient episode、future plan 与仅情境叙述。health 需 enduring/recurrent/diagnosed/currently-persistent evidence；social role 必须直接陈述；occupation 与 education 分开；catch-all 采用 fail-closed durability evidence，不用样本黑名单。
- ME 必须是 owner 的 agentive/intentional action，随后出现语义不同的 user-observed outcome，并且 action→outcome 属于同一 experience lineage；同一症状不得同时充当 action 与 outcome；不用样本黑名单。
- MS 保持 strict-past owner episodic/continuity event or state，排除 profile、greeting、trivia、future、current 与 malformed ME；必须有可追溯 event/thread。

旧 `MP20 + ME12` 只作为 DEV regression，不构成最终 qualification。修复后另建 held-out qualification IDs：MP 按 subtype 分层新 seed；MS event/thread 新 seed；ME 因稀少应覆盖全部或近全部，并显式预算。不得为追求数量放松 ontology 或 synthetic rescue。

## 7. ESC-RANK runtime qualification

必须在 `>=24 GiB` GPU 上测试 pinned official repo/version。允许的 patch 只限 dependency/path compatibility，且需 exact patch manifest；不得修改 rubric、模型、7维 adapter 语义。harness 必须记录 VRAM、cold/warm latency、七维解析成功、重复性和代码/model/adapter hash。本地 RTX 2070 不能伪装成完成该实验。

未来 evaluator qualification set 不得由未来 RS top-k outcome 组成；优先用公开 baseline dialogues/overlap-only material，配小型 human blind reference，比较 weighted kappa、Spearman、MAD、pairwise winner consistency、dynamic range、verbosity/suggestion/family bias、latency 与 cost。

## 8. split/fold

ESC `large_52` 与 RQ2 `K=5, seed=0` 当前机器状态为 `READY`，readiness label=`RESEARCHER_READY_TO_FREEZE`，不是 `FROZEN`。不读 outcome、不 seed shopping；待研究者显式批准后才写入正式 freeze manifest。

## 9. 本轮明确禁止

- calibration/confirmatory/formal outcome；
- PM effect construction 或训练；
- 正式 ESC-Eval / ES-MemEval；
- 用旧 DEV 样本冒充 held-out qualification；
- 为数量扩 ontology、改模型或 synthetic rescue；
- Step2 utility filter；
- outcome 导向的 evaluator、k、split 或 seed 选择。
