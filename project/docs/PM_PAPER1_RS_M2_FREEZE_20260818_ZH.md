# Policy Manager Paper 1 RS M2 决策冻结（2026-08-18）

状态：`RESEARCHER_DECISIONS_APPROVED / EXACT_IMPLEMENTATION_FREEZE_PENDING / PRE_OUTCOME`

机器合同：`project/data/paper1_authority/paper1_rs_m2_freeze_20260818_v1.json`

本文件冻结 `paper1_m2_decision_packet_draft_v1.json` 中 RS 相关的 9 项决策（order 1-9）。取代该 draft 里对应的记录，其余非 RS 决策（memory census、outer folds、official RAG runtime 等）不受影响。

**2026-08-18 状态修正**：这 9 项的"FROZEN"指的是研究者在几个备选方案里的**选择**已锁定（比如"用 BGE-M3""用 atomic-move compiler"），不代表**精确机械实现**已经冻结——第5项的 Hub revision/pooling、第9项五个特征各自的精确窗口/parser/tokenizer/缺失值处理，都还没定。之前标注得不够清楚，容易被误读成完整 M2 full-stack freeze，现已在下方说明。

## 冻结结果

| # | 决策 | 结果 |
|---|---|---|
| 1 | RS 卡片来源 | dialogue-only v2，已落地 |
| 2 | EvoEmo overlap 排除 | 保守版：12169 张卡 / 11883 states（不用 12906 的完整版） |
| 3 | RS 决策粒度 | 一次连续 supporter run = 一个决策状态 |
| 4 | 候选打包 | Top-1 单卡，不用 bundle |
| 5 | Retriever | BGE-M3，Top-1，leave-current-dialogue-out |
| 6 | 卡片内容表示 | **atomic-move compiler**，取代旧的 guidance-only / guidance+exemplar 二选一 |
| 7 | exemplar 政策 | 并入第 6 项 |
| 8 | 显式边界 | current-run-only |
| 9 | PM 观测特征 | `rs_state_candidate_similarity` / `rs_atomic_move_type` / `rs_recent_same_move_count` / `rs_explicit_request_flags` / `rs_candidate_token_cost` |

## 第 6 项的真实依据

2026-08-18 对 10 张真实 ESConv 卡做的 live smoke（`qwen3-235b-a22b-instruct-2507`，见 `/home/chenzhi/paper1_runs/rs_atomic_move_smoke_20260818/`）。**这 10 张卡全部来自同一个对话 esconv_0002**，属于单对话工程验证，不是跨对话的科学性证据：

- 19 个 extractor 提案，0 个 grounding 结构性拒绝，6 个 verifier 拒绝，13 个最终接受（接受率 68.4%）。13 个 accepted 里只有 **11 个不同渲染文本**，2 组完全重复（"acknowledge the user's difficult situation with empathy" ×2、"ask whether the user is receiving sick pay" ×2），另有近义重复未被去重机制捕捉。
- 6 个 verifier 拒绝里，至少 2 个疑似误判：`ask how the user is feeling` 被判 `leaked_source_specific_content`（文本本身没有姓名/亲属/数字），`ask if the user wants to talk about something on their mind` 被判 `multiple_distinct_actions`（单一提问）。extractor 和 verifier 用的是同一个 Qwen 模型、不同 prompt，不是独立的第二标注者，这些误判需要人工 rubric 复核。
- **2026-08-18 修正**：原先记录的"平均 16.2 token（`o200k_base` 计）、压缩约 87%"是用 OpenAI 分词器和旧数据（用 Llama 分词器算的 125/158）跨口径比较，无效。用冻结的 Llama-3.1-8B-Instruct 分词器（`NousResearch/Meta-Llama-3.1-8B-Instruct`，revision `d10aef7999a2b5ba950ab3974312feeedbfe0b77`，hash 校验通过）对同一批 13 张卡重新计算：中位数 **16 token**，最大 **21 token**。同口径下压缩比例 **87.2%**（(125-16)/125），结论不变，但这是修正后重新验证过的数字，不是原来那个跨口径拼出来的 87%。
- 旧 guidance-only 方案会让 12169 张卡坍缩成 8 个通用模板；旧 guidance+exemplar 方案保留卡片独立性，但 5963/605/594 张卡分别带有第一人称指代/亲属关系词/数字等他人具体细节。atomic-move 两个问题都不占，但"跨对话是否依然不坍缩、不泄漏"还没测过。

## 尚未冻结的部分

本文件只冻结上述 9 项的**研究者选择**，不是精确机械实现的完整冻结。以下仍待后续步骤：

- BGE-M3 具体 Hub revision / pooling / normalization 参数冻结，以及与 NVIDIA NIM tokenizer 的 provider parity 核对。
- **跨对话多样性 compiler QA**——10 张卡全来自一个对话，是工程验证不是科学泛化证据。需要一次固定、hash-bound 的跨对话分层抽样（8 个 strategy family、16-24 个不同对话、长短/单动作/多动作/无动作、姓名/亲属/数字/组织/地点压力例、重复近重复回复），并用预先写好的 rubric 人工审计 false accept/false reject，这是冻结 exact compiler/prompt/schema/renderer 之前必须做的一步。
- **RS atomic-move 全量编译**——目前只跑过 10 张卡（单对话）的 live smoke，全部 12169 张卡还没编译，跨对话 QA 通过后才重新估算全量预算。
- 第 9 项五个特征各自的精确机械定义（`rs_recent_same_move_count` 的窗口、`rs_explicit_request_flags` 的 parser、`rs_candidate_token_cost` 的 tokenizer、缺失值处理）仍是审计草案，未精确冻结，见 `data/paper1_public_rs/esconv_rs_zero_outcome_census_summary_v1.json#feature_readiness`。
- cross-fit K/seed、task-specific effect anchor、Generator/Step2 full-stack manifest、seed schedule、matched-random construction、API call plan——这些是 execution blueprint Phase 2 的通用项，不是 RS 专属，仍需单独走完。

## 12403 → 12169 卡片数对不上的说明

`data/paper1_authority/esconv_strategy_source_summary_v1.json`（commit 91855fa，同样声称排除 EvoEmo overlap）记录的是 **12403** 张卡，和本文件第 2 项的 **12169** 不一致。这不是数据丢失或未解释的缺口：commit 993f6a9 把 `StrategySourceCard.retrieval_text` 从 `situation+context` 改成了纯 `context`（即第 1 项 dialogue-only v2），这让 `(retrieval_text, response)` 去重 key 碰撞增多，机械性地多去掉了 234 张卡。12169 是当前 `build_strategy_source_catalog()` 的真实输出，12403 那份 summary 已经过时，现已在自己文件里标注 `SUPERSEDED_20260818_DO_NOT_USE_FOR_M2_FREEZE` 并指回本文件和 `esconv_rs_zero_outcome_census_summary_v1.json`。

## 下一步

先跑一次 ~$0.10 硬顶的 64-card 跨对话多样性 compiler QA smoke（不触碰 outcome lock），人工审计通过、用 Llama 分词器重算长度分布后，再重新估算并批准全量 12169 张卡的正式编译预算，然后重建 RS 的 zero-outcome census。**不会在完成 public-only zero-outcome census 并生成 freeze manifest 前调用任何 ON/OFF effect outcome**（`PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md` 第 7 节，最高优先级冻结文件）。
