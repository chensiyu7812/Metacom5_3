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
| 10 | atomic unit → 目录条目基数 | **单个 treatment 为一个 atomic unit；跨源卡重复策略待研究者决定** |

## 第 6 项的真实依据

2026-08-18 对 10 张真实 ESConv 卡做的 live smoke（`qwen3-235b-a22b-instruct-2507`，见 `/home/chenzhi/paper1_runs/rs_atomic_move_smoke_20260818/`）。**这 10 张卡全部来自同一个对话 esconv_0002**，属于单对话工程验证，不是跨对话的科学性证据：

- 19 个 extractor 提案，0 个 grounding 结构性拒绝，6 个 verifier 拒绝，13 个最终接受（接受率 68.4%）。13 个 accepted 里只有 **11 个不同渲染文本**，2 组完全重复（"acknowledge the user's difficult situation with empathy" ×2、"ask whether the user is receiving sick pay" ×2），另有近义重复未被去重机制捕捉。
- 6 个 verifier 拒绝里，至少 2 个疑似误判：`ask how the user is feeling` 被判 `leaked_source_specific_content`（文本本身没有姓名/亲属/数字），`ask if the user wants to talk about something on their mind` 被判 `multiple_distinct_actions`（单一提问）。extractor 和 verifier 用的是同一个 Qwen 模型、不同 prompt，不是独立的第二标注者，这些误判需要人工 rubric 复核。
- **2026-08-18 修正**：原先记录的"平均 16.2 token（`o200k_base` 计）、压缩约 87%"是用 OpenAI 分词器和旧数据（用 Llama 分词器算的 125/158）跨口径比较，无效。用冻结的 Llama-3.1-8B-Instruct 分词器（`NousResearch/Meta-Llama-3.1-8B-Instruct`，revision `d10aef7999a2b5ba950ab3974312feeedbfe0b77`，hash 校验通过）对同一批 13 张卡重新计算：中位数 **16 token**，最大 **21 token**。同口径下压缩比例 **87.2%**（(125-16)/125），结论不变，但这是修正后重新验证过的数字，不是原来那个跨口径拼出来的 87%。
- 旧 guidance-only 方案会让 12169 张卡坍缩成 8 个通用模板；旧 guidance+exemplar 方案保留卡片独立性，但 5963/605/594 张卡分别带有第一人称指代/亲属关系词/数字等他人具体细节。atomic-move 两个问题都不占。

**2026-08-18 跨对话多样性 smoke(64 张卡，62 个不同对话，8 个 strategy family 全覆盖）**：第一轮(verifier 有 bug)接受率 40.7%，抽查发现 verifier 把 supporting_spans 里的具体内容错当成 action_description 泄漏，误判率高。修 prompt 后第二轮：接受率升到 63.8%（44→67 accepted units），44 个 accepted units **零重复**（跨对话真实验证了"不坍缩"）。抽查剩余误判发现根因是 verifier 语义判断和已有的确定性正则检查(`grounding.py` 的 `check_action_description_not_leaking`)重复判同一件事，于是做了架构修复——把 `leaked_source_specific_content` 和 `ambiguous_span` 从 verifier 的输出 schema 里结构性移除，只交给确定性正则层。用之前所有误判过的 13 张卡做针对性复核，全部通过或换成更站得住脚的理由被拒，一个都没再被"leaked"卡住。跨对话不坍缩、不泄漏，现在是真实验证过的，不是假设。

## 第 10 项：atomic unit → 目录条目基数规则

- **0 个 accepted unit**：这张源卡对目录没有任何贡献，不生成占位条目。
- **1 个 accepted unit**：变成恰好一个目录条目。
- **多个 accepted unit**：每一个都是独立的目录条目，**不合并成一张"多动作"卡**——和第4项(Top-1单卡、不用bundle)一致：检索时挑的是单张最匹配的候选卡，一个源turn产出多个不同动作，就是贡献多个各自独立可检索的候选，不是一张复合卡。
- **token 成本**：按每个 accepted unit 的 `rendered_card_text`，用冻结的 Llama-3.1-8B-Instruct 分词器计算（第6项验证 87.2% 压缩比用的同一个），不用 o200k_base，也不用空格切词代理。
- **跨源卡 exact/near duplicate：`PROPOSED RESEARCH CHANGE — NOT AUTHORIZED`**。全量 compiler output 尚未产生，真实重复频率未知；是否 canonicalize 不能由实现者静默决定。后续方案必须保留全部来源 `source_dialogue_ids` 的并集，并避免重复 treatment text 获得人为更高的检索先验，待研究者显式批准后再冻结。
- 卡内(同一源卡内)的语义重复，本来就已经被 `duplicate_semantic_content_count` 机制处理，这条决策不改变这部分。
- 每个独立 unit 的检索文档由 `build_atomic_move_retrieval_document` 确定性构造为 `source retrieval_text + "\\n" + unit rendered_card_text`；构造器会核对 source turn 和完整 dialogue lineage，并绑定文档 hash。BGE-M3 的实际批量编码与接线仍须等待 v2 binding hardening。

## 尚未冻结的部分

本文件只冻结上述 10 项的**研究者选择**，不是精确机械实现的完整冻结。以下仍待后续步骤：

- BGE-M3 具体 Hub revision / pooling / normalization 参数冻结——工程验证已经做了(`paper1_bge_m3_formal_binding_v1.json`)，但那份文件自己也明确写着还没到能叫"冻结"的程度，还有 6 个已知缺口。
- **RS atomic-move 全量编译**——verifier 架构修复(把 `leaked_source_specific_content` 从 verifier 能选的 schema 里彻底移除，交给已有的确定性正则层)已经用 13 张卡的针对性复核实测验证过；目前已有两次 64 张跨对话多样性 smoke + 一次 13 张针对性复核作为真实跨对话证据，不再是单对话孤证。还差一份精确的调用数/预算/resume plan 提交，等待批准后才能跑。
- 跨源卡 exact/near-duplicate accepted-unit 的 canonicalization / 保留策略尚待研究者显式决定；不得把未批准的 `no dedup` 写成冻结事实。
- 第 9 项五个特征各自的精确机械定义（`rs_recent_same_move_count` 的窗口、`rs_explicit_request_flags` 的 parser、`rs_candidate_token_cost` 的 tokenizer、缺失值处理）仍是审计草案，未精确冻结，见 `data/paper1_public_rs/esconv_rs_zero_outcome_census_summary_v1.json#feature_readiness`。
- cross-fit K/seed、task-specific effect anchor、Generator/Step2 full-stack manifest、seed schedule、matched-random construction、API call plan——这些是 execution blueprint Phase 2 的通用项，不是 RS 专属，仍需单独走完。

## 12403 → 12169 卡片数对不上的说明

`data/paper1_authority/esconv_strategy_source_summary_v1.json`（commit 91855fa，同样声称排除 EvoEmo overlap）记录的是 **12403** 张卡，和本文件第 2 项的 **12169** 不一致。这不是数据丢失或未解释的缺口：commit 993f6a9 把 `StrategySourceCard.retrieval_text` 从 `situation+context` 改成了纯 `context`（即第 1 项 dialogue-only v2），这让 `(retrieval_text, response)` 去重 key 碰撞增多，机械性地多去掉了 234 张卡。12169 是当前 `build_strategy_source_catalog()` 的真实输出，12403 那份 summary 已经过时，现已在自己文件里标注 `SUPERSEDED_20260818_DO_NOT_USE_FOR_M2_FREEZE` 并指回本文件和 `esconv_rs_zero_outcome_census_summary_v1.json`。

## 下一步

跨对话多样性 QA 和 verifier 架构修复都已完成并实测验证。下一步是提交全量 12169 张卡编译的精确调用数/预算/resume plan，等待批准后跑，然后用编译产物重建 RS 的 zero-outcome census。**不会在完成 public-only zero-outcome census 并生成 freeze manifest 前调用任何 ON/OFF effect outcome**（`PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md` 第 7 节，最高优先级冻结文件）。
