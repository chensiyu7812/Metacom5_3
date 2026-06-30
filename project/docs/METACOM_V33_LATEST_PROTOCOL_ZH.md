# MetaCom V3.3 最新研究方案与实验协议

更新时间：2026-06-30
状态：内部 full judging / M2b / stable PM 重训完成；ESConv strategy-only 外部评测完成；EvoEmo selective generation 已完成并生成 attestation；旧 EvoEmo pairwise-only response evaluation 已完成但 AB/BA gate 失败，仅作诊断；EvoEmo Response Eval V4 已完成 full-run / attestation / no-API statistical summary；sampled memory / strategy audit 已完成 full-run / attestation。下一步是写入论文结果表与 claim boundary。
项目目录：`/home/tokkio/esconv_experiment_bundle/policy_manager_35`

## 0. 这份文件是什么

这是当前 V3.3 的**最新整合版 protocol**。旧文件仍有用，但不是当前唯一入口：

- `docs/METACOM_V32_RESEARCH_PLAN_ZH.md`：V3.2 设计来源，已不是当前最终协议。
- `docs/MEASUREMENT_PROTOCOL_V3.md`：judge gate / dual-order 等测量协议，仍有效。
- `snap/METACOM_V33_EXTERNAL_EVALUATION_PLAN_FOR_GPT55_ZH.md`：外部评测计划，但写于 stable PM 重训前。
- `snap/METACOM_V33_STABLE_PM_EVOEMO_READINESS_ZH.md`：stable PM 与 EvoEmo readiness 的补充结果。

本文件把这些内容合并成当前版本。

## 1. 论文主张边界

本研究不是训练新的 ESC 生成器，也不是 RL / POMDP / 临床疗效实验。

当前论文主张应写成：

> 在固定回复生成器之外，学习式 pre-evidence Policy Manager 可以只基于当前对话和轻量 memory inventory metadata，选择要调用的长期记忆与 Strategy RAG 资源。在内部 development 与外部 controlled evaluation 中，我们评估它相对 fixed / rule 策略在回复质量、记忆误用、遗漏风险、strategy 风险和成本之间的权衡。

更安全的核心结论：

> PM 学到一种 resource-aware allocation 倾向：在内部 development 中 response / misuse / cost tradeoff 更有利；在 EvoEmo V4 外部 response evaluation 中，它相对 strong rule / best fixed 的 fixed-input response quality 大体持平，同时降低资源成本。但 strong rule 在 omission / strategy coverage 上更保守。因此论文应报告 tradeoff，而不能声称 PM 全面优于 rule。

不能主张：

- 真实用户 distress 改善；
- 临床疗效；
- RL / POMDP 已实现；
- ESConv 证明长期记忆；
- fixed seeker tracks 是 official ES-MemEval reproduction；
- PM 全面跑过 strong rule。

## 2. 系统定义

### 2.1 两阶段因果流程

```text
Step 1: Pre-evidence PM
  input: current text, recent dialogue, session depth, memory inventory metadata, action id
  output: memory_action + strategy_action

Step 2: Evidence execution and generation
  retrieve only selected memory source(s)
  retrieve Strategy RAG only if RS
  fixed generator writes response
```

PM 禁止读取：

- actual memory snippets；
- selected memory ids；
- retrieval scores；
- generated response；
- judge labels；
- future user state；
- gold action / private labels。

### 2.2 动作空间

Memory action:

- `M0`
- `MP`
- `MS`
- `ME`
- `MPMS`
- `MPE`
- `MSE`
- `MPMSME`

Strategy action:

- `R0`
- `RS`

完整动作是 8 × 2 = 16 个组合。

## 3. 当前 PM 版本

### 3.1 为什么从 `text_metadata` 改成 `text_metadata_stable`

原冻结 PM 在 EvoEmo fixed tracks 上触发 severe OOD：

- `1020 / 1020` states 被 blocked；
- 典型外部状态出现 `session_index=33`、ME 目录接近 `9935 tokens`；
- synthetic 训练域里 session index 最大约 13，ME count 最大约 1。

这说明问题在特征域，不在 full judging 标签。

### 3.2 Stable PM 修正

新增特征模式：

```text
text_metadata_stable
```

它做：

- 使用 current text + inventory metadata；
- 不使用 actual memory snippets；
- 不使用 catalog fingerprint；
- 对 count / age / estimated tokens / session_index 按 training domain 上限 cap；
- 保持 pre-evidence 性质。

这一步不重跑 LLM judge，不重跑 ESConv，只用已有 full judging 与 M2b 标签重训 PM。

### 3.3 Stable PM artifact

当前 stable PM：

- checkpoint: `outputs/final_model_m2b_stable/pm_final.joblib`
- selection: `outputs/selection_stable.json`
- freeze: `outputs/study_freeze_stable.json`
- freeze sha256: `e3e0e33ce3227a3032dc7929eb6f615c42784630739c2b79351da7f4d904571f`

EvoEmo readiness：

- `outputs/evoemo_pm_readiness_stable_frozen.json`
- status: `READY`
- expected states: `1020`
- checked states: `1020`
- errors: `0`
- constraint fallback used: `False` for all 1020 states。

## 4. 内部 development 结果

数据：

- `data/synthetic/runtime_states.jsonl`
- 1728 cards = 192 base states × 9 inventory variants。

Judge / labels：

- full judging: `outputs/full_judging_gemini_flash_lite_v3/`
- M2b selected-set omission: `outputs/m2b_selected_set_omission_gemini_flash_lite_v3/`
- training judge: Gemini 2.5 Flash Lite；
- final judge: GPT-4o。

Stable PM validation summary：

| Policy | Response ↑ | Misuse ↓ | Omission ↓ | Strategy Risk ↓ | Safety Risk ↓ | Cost ↓ |
|---|---:|---:|---:|---:|---:|---:|
| PM stable | 0.576 | 0.063 | 0.298 | 0.242 | 0.517 | 553.3 |
| Strong rule | 0.542 | 0.125 | 0.152 | 0.022 | 0.272 | 673.7 |

Interpretation:

- PM stable response 更高；
- PM stable misuse 更低；
- PM stable cost 更低；
- strong rule omission / strategy risk 更低；
- 因此主张必须是 tradeoff，不是全面胜利。

## 5. ESConv 外部评测协议

### 5.1 ESConv 的作用

ESConv 是单 session 数据，不能证明长期记忆。

ESConv 只用于：

- Strategy RAG 在普通 ESC 中是否应该 always-on；
- 无长期记忆时是否避免 false-memory / unsupported personal claims；
- 普通 ESC response quality 是否被 Strategy RAG 损害或改善。

### 5.2 ESConv 已完成结果

生成：

- `outputs/esconv_sweep/action_outcomes.jsonl`
- 2275 turns × 2 actions = 4550 rows；
- actions: `M0+R0`, `M0+RS`；
- generator: `meta/llama-3.1-8b-instruct` via NVIDIA。

Judge:

- `outputs/esconv_strategy_eval/strategy_pair_judgments.jsonl`
- final judge: GPT-4o。

结果：

- n = 2275 turns；
- dialogue clusters = 169；
- RS wins / ties / R0 wins = 696 / 457 / 1122；
- RS preference score = 0.406；
- 95% dialogue-cluster bootstrap CI = [0.386, 0.425]；
- M0+R0 mean input tokens = 316.7；
- M0+RS mean input tokens = 570.4。

结论：

> Always-on RS 在 ESConv 上平均伤害回复质量且增加成本。

但 RS 不是完全无用：

- RS wins = 696；
- oracle selective selector vs always-R0 score = 0.653；
- oracle selective selector vs always-RS score = 0.747；
- oracle RS call rate = 0.306。

因此 ESConv 支撑的论点是：

> Strategy RAG 有条件价值，但不能 always-on；选择性路由是必要的。

ESConv 不证明：

> 当前 PM 已经在 ESConv 上学会 strategy routing。

因为 ESConv 是 single-session，与 longitudinal PM 训练域不匹配。

## 6. EvoEmo / ES-MemEval-style 外部评测协议

### 6.1 EvoEmo 的作用

EvoEmo / ES-MemEval-derived 数据用于长期记忆外部验证。

当前数据：

- `data/external/evo_emo.json`
- 18 users；
- 401 historical sessions；
- 34 subsequent topics。

注意：

- 401 是历史 session 规模，不是 401 个独立测试题；
- 当前正式 dialogue-generation evaluation 是 34 topics × 3 seeds × 10 turns；
- fixed seeker tracks 是 controlled extension，不是 official ES-MemEval reproduction。

论文应称为：

> EvoEmo-based / ES-MemEval-style fixed-input longitudinal evaluation

### 6.2 Fixed seeker tracks

已完成：

- `outputs/evoemo_fixed_tracks/fixed_seeker_tracks.jsonl`
- 102 tracks = 34 topic combos × 3 seeds；
- 每个 track 10 seeker turns；
- policy-independent；
- all policies see the same seeker input。

### 6.3 EvoEmo generation 条件

当前 `scripts/15_run_evoemo.py` 默认 conditions：

- `no_memory_r0`
- `no_memory_rs`
- `session_rag_rs`
- `full_history_rs`
- `all_structured_rs`
- `best_fixed`
- `strong_rule`
- `pm`

这些将生成：

```text
34 scenarios × 3 seeds × 8 conditions = 816 dialogues
816 dialogues × 10 turns = 8160 evaluated turns
```

当前已完成：

- output dir: `outputs/evoemo_selective/`
- freeze: `outputs/study_freeze_stable.json`
- checkpoint: `outputs/final_model_m2b_stable/pm_final.joblib`
- selection: `outputs/selection_stable.json`
- `dialogues.jsonl`: 816 / 816；
- `turns.jsonl`: 8160 / 8160；
- `generation_summary.json`: 已生成；
- `artifact_attestation.json`: 已生成；
- malformed / failures: 0。

评价阶段新增单独 freeze：

- evaluation freeze: `outputs/evoemo_pairwise_eval_freeze.json`
- evaluation freeze sha256: `6603d334484e93d282170600811faf8629e682c6b60b23fa0914cccce7b25819`
- generation freeze sha256: `e3e0e33ce3227a3032dc7929eb6f615c42784630739c2b79351da7f4d904571f`
- 目的：保留已完成 generation 的旧 freeze，同时锁住新增 `--pairs-only` evaluator code/config。

### 6.4 EvoEmo pairwise-only 评价结果

Pairwise-only response evaluation 已完成所有 API calls：

- output dir: `outputs/evoemo_selective_metrics/`
- expected rows: 816；
- actual rows: 816；
- final judge: GPT-4o；
- usage rows: 816；
- prompt tokens: 12,267,429；
- completion tokens: 90,529；
- 估算费用：约 31.57 USD。

但是最终没有生成正式：

- `outputs/evoemo_selective_metrics/selective_summary.json`
- `outputs/evoemo_selective_metrics/artifact_attestation.json`

原因是 confirmatory dialogue-pair judge gate 失败。预设门槛：

```text
min_orientation_consistency = 0.80
```

实际结果：

| Comparison | Orientation Consistency | Raw PM Score | Disagreement-as-tie PM Score |
|---|---:|---:|---:|
| pm_vs_best_fixed | 0.647 | 0.488 | 0.490 |
| pm_vs_full_history_rs | 0.745 | 0.853 | 0.853 |
| pm_vs_session_rag_rs | 0.402 | 0.461 | 0.466 |
| pm_vs_strong_rule | 0.569 | 0.458 | 0.461 |

解释：

- 本轮 pairwise 结果只能作为诊断；
- 不能作为论文 confirmatory 外部 response-quality 结果；
- 不能写 EvoEmo pairwise 证明 PM response quality 非劣或更好；
- 失败原因是 10-turn bundle pairwise prompt 对候选顺序敏感，AB/BA 稳定性不足。

详细报告：

- `docs/METACOM_V33_EVOEMO_PAIRWISE_GATE_FAILURE_ZH.md`
- `outputs/evoemo_selective_metrics/pairwise_gate_failure_diagnostic.json`

### 6.5 下一版 EvoEmo 评价要求

下一版已落地为 EvoEmo Response Eval V4，并已完成 full-run：

- module: `src/metacom_pm/evo_response_v4.py`
- script: `scripts/17b_eval_evoemo_response_v4.py`
- offline analysis: `scripts/17c_analyze_evoemo_response_v4.py`
- freeze script: `scripts/20c_freeze_evoemo_response_v4_eval.py`
- plan: `docs/METACOM_V33_EVOEMO_RESPONSE_V4_PLAN_ZH.md`
- result: `docs/METACOM_V33_EVOEMO_RESPONSE_V4_RESULT_ZH.md`
- note to GPT-5.5 Pro: `docs/METACOM_V33_EVOEMO_RESPONSE_V4_NOTE_TO_GPT55_ZH.md`

核心设计：

- single-turn fixed-input absolute scoring；
- 每个 turn 内多候选匿名评分；
- 默认 sample = 34 topics × 3 seeds × turns `{3, 8}` = 204 units；
- 默认 conditions = `pm`, `strong_rule`, `best_fixed`, `session_rag_rs`, `full_history_rs`, `no_memory_r0`；
- 候选顺序 deterministic balanced；
- pilot 同一 unit 跑两个 order variants，检查 order sensitivity 和 position bias；
- API 模式必须接受对应 dry-run `cost_estimate_sha256`；
- full-run 必须有 `pilot_summary.json`，且 status = `PASS`；
- full-run 前强制检查 pilot summary 与当前 full-run 的 judge / conditions / turns / ground truth / generation freeze / evaluation freeze / pilot thresholds 完全兼容。

V4 dry-run / pilot / full-run 状态：

- evaluation freeze: `outputs/evoemo_response_v4_eval_freeze.json`
- evaluation freeze sha256: `c9ccd1d21d1da8571710361ed9648b6696964edaf45d45067cea2887185c4bb3`
- pilot API: PASS；
- full-run: COMPLETE；
- artifact attestation: `outputs/evoemo_response_v4/artifact_attestation.json`
- full-run output validation: ok；
- completed calls: 204 / 204；
- score rows: 1224 / 1224；
- raw rows: 204；
- successful raw calls: 204。

Dry-run budget：

| Target | Calls | Total Input Tokens | Mean / P95 / Max Input Tokens | Estimated Cost | Hash |
|---|---:|---:|---:|---:|---|
| pilot | 48 | 333,436 | 6,947 / 11,021 / 11,289 | 1.31 USD | `3f4c38cdb21d3e0e545bafd652cf6b7fcaedc159f83ef0919b9dfcd24ca3b661` |
| full | 204 | 1,421,967 | 6,970 / 10,706 / 11,289 | 5.59 USD | `74650cb61d42640ee673817b67953f3716e0c58c52f958c677706411d5650eb5` |

这确认：

- GPT-5.5 Pro 原先约 3000 tokens/call 的估算偏低；
- `max_input_tokens_per_call=6000` 太低；
- V4 默认 hard gate 改为 `12000`；
- full-context V4 仍可控制在约 5–6 USD 量级，而不是旧 pairwise 的 31.57 USD。

实际 full-run judge usage：

- prompt tokens: 1,468,275；
- completion tokens: 147,644；
- estimated cost without cache discount: about 5.15 USD。

V4 response result:

| Condition | Overall | Memory Appropriateness | Factual Grounding |
|---|---:|---:|---:|
| session_rag_rs | 3.750 | 3.990 | 4.289 |
| no_memory_r0 | 3.745 | 3.995 | 4.284 |
| best_fixed | 3.662 | 3.946 | 4.270 |
| strong_rule | 3.662 | 3.951 | 4.275 |
| pm | 3.657 | 3.941 | 4.275 |
| full_history_rs | 3.618 | 3.951 | 4.240 |

PM paired overall deltas, scenario-cluster bootstrap:

| Comparison | Mean PM - Baseline | 95% Cluster CI | NI @ 0.05 | NI @ 0.10 |
|---|---:|---:|---:|---:|
| PM - strong_rule | -0.005 | [-0.059, 0.044] | no | yes |
| PM - best_fixed | -0.005 | [-0.064, 0.054] | no | yes |
| PM - full_history_rs | +0.039 | [-0.064, 0.147] | no | yes |
| PM - session_rag_rs | -0.093 | [-0.167, -0.025] | no | no |
| PM - no_memory_r0 | -0.088 | [-0.167, -0.015] | no | no |

V4 resource result on sampled turns:

| Condition | Mean Input Tokens | RS Call Rate | Top Actions |
|---|---:|---:|---|
| pm | 1294.6 | 0.941 | MSE+RS:103, MPMS+RS:31, MP+RS:26, MPE+RS:15 |
| strong_rule | 1627.4 | 1.000 | MSE+RS:204 |
| best_fixed | 1654.8 | 1.000 | MPMSME+RS:204 |
| session_rag_rs | 3233.2 | 1.000 | SESSION_RAG+RS:204 |
| full_history_rs | 14079.8 | 1.000 | FULL_HISTORY+RS:204 |
| no_memory_r0 | 395.5 | 0.000 | M0+R0:204 |

PM input token reduction:

- vs strong_rule: 20.4%；
- vs best_fixed: 21.8%；
- vs session_rag_rs: 60.0%；
- vs full_history_rs: 90.8%。

Token accounting note:

> `total_input_tokens` 是主成本指标；`base_prompt_tokens`、`memory_tokens`、`strategy_tokens` 等 component fields 是诊断估计，不假定在同一个 tokenizer / accounting path 下严格可加。

解释：

- PM 对 strong_rule / best_fixed 的 response quality 大体持平，不能说显著输了，也不能在严格 0.05 margin 下声称已确认非劣；
- `0.10` practical margin 下，PM 对 strong_rule / best_fixed 可视为非劣；
- session_rag_rs / no_memory_r0 的 overall 分数更高，说明 V4 不支持“PM response quality 最优”；
- PM 的优势主要在相近 response quality 下减少 structured-memory / full-history resource use；
- `no_memory_r0` 分数高说明很多 fixed-input turn 不需要资源，不说明长期记忆无用；
- `session_rag_rs` 分数高但成本更高，不说明 always-on memory/RAG 是最佳系统。

Memory / strategy audit 仍禁止 all-turn 全量直接跑：

- 必须使用 stratified sampled audit；
- memory omission audit 只在少量关键 turn 上使用完整 memory；
- misuse audit 尽量只给 selected memory；
- strategy audit 单独轻量 prompt。

当前 sampled audit no-API plan:

- script: `scripts/17d_plan_evoemo_sampled_audit.py`
- evaluator: `scripts/17e_eval_evoemo_sampled_audit.py`
- freeze script: `scripts/20d_freeze_evoemo_sampled_audit_eval.py`
- plan doc: `docs/METACOM_V33_EVOEMO_SAMPLED_AUDIT_PLAN_ZH.md`
- output dir: `outputs/evoemo_sampled_audit_plan/`
- selected items: 40；
- unique users: 18；
- unique scenarios `(user_id, topic_index)`: 34 / 34；
- estimated audit calls: 80；
- estimated input tokens: 178,975；
- estimated output tokens: 36,000；
- estimated cost: about 0.81 USD。

当前 sampled audit evaluator freeze / dry-run:

- evaluation freeze: `outputs/evoemo_sampled_audit_eval_freeze.json`
- evaluation freeze sha256: `c17cd2077a75f0c250091022e80d4a88c1322b73d52760789eafd990e11b4d8c`
- prompt leakage fix: judge prompt 不暴露 `covered_strata` / `planner_reason` / `pm_vs_*` / policy condition name；target/comparison 用匿名 id；
- pilot dry-run: `outputs/evoemo_sampled_audit/cost_estimate_pilot.json`
- pilot calls: 16；
- pilot estimated cost: about 0.20 USD；
- pilot input tokens: total 49,703 / mean 3,106 / max 3,570；
- pilot cost hash: `0ec60d02a5ac4d501c1d29d9037aec5a3cf2f0d7ddfdd9bcb2fb3533ff98ec46`
- full dry-run: `outputs/evoemo_sampled_audit/cost_estimate_full.json`
- full calls: 80；
- full estimated cost: about 0.96 USD；
- full input tokens: total 239,834 / mean 2,998 / max 4,313；
- full cost hash: `164e5c6aa3aaa84cce45e30439e00ef70ed473d9c9d988fc182f53e39af3fa45`

Audit plan focus:

- PM vs strong_rule：质量接近，PM 更省资源；
- PM vs best_fixed：质量接近，PM 更省资源；
- PM vs session_rag_rs：session_rag 分数略高但成本更大；
- PM vs no_memory_r0：检查 PM 是否引入 unnecessary exposure / over-structuring；
- PM high-resource / low-resource / rare-action turns：检查 PM 边界行为。

Sampled audit full-run result:

- output dir: `outputs/evoemo_sampled_audit/`
- full-run status: `COMPLETE`
- attestation: `outputs/evoemo_sampled_audit/artifact_attestation.json`
- attestation status: `ATTESTED`
- attestation sha256: `3ed5147dcb2dfafd07f1d0ad483e76d3333e520e1cbe4d1422d23ef04443ba7d`
- expected / completed calls: 80 / 80；
- score rows / judgment rows / raw rows: 80 / 80 / 80；
- raw rows gate: 80 <= 88；
- successful raw calls: 80；
- duplicate rows: 0；
- actual prompt tokens: 260,634；
- actual completion tokens: 13,349；
- estimated actual GPT-4o cost: about 0.79 USD；
- verdicts: acceptable 77；minor_issue 1；major_issue 2。

Sampled audit condition summary:

| Condition | n | Misuse ↓ | Exposure ↓ | Stale/Conflict ↓ | Unsupported Claim ↓ | Source Set ↑ | Strategy Omission ↓ | Support ↑ | Risk ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PM | 50 | 0.000 | 0.000 | 0.000 | 0.000 | 2.140 | 0.020 | 3.680 | 0.020 |
| Strong rule | 14 | 0.143 | 0.000 | 0.000 | 0.000 | 2.071 | 0.000 | 3.571 | 0.143 |
| Best fixed | 10 | 0.000 | 0.000 | 0.000 | 0.000 | 1.800 | 0.000 | 3.700 | 0.000 |
| Session RAG RS | 6 | 0.333 | 0.000 | 0.000 | 0.000 | 1.667 | 0.000 | 3.667 | 0.333 |

Sampled audit interpretation:

- PM sampled audit 中未观察到 selected-evidence misuse、unnecessary exposure、stale/conflict 或 unsupported personal claim；
- PM 有 1 个 minor strategy omission / insufficiently targeted support case；
- omission-with-authorized-context 子审计 10 / 10 为 acceptable，omission severity = 0；
- strong_rule 与 session_rag_rs 各出现 major selected-evidence misuse case，主要是检索或规则选择了与当前 turn 不相关的记忆；
- 这支持 PM 在 sampled audit 中更少误用证据、保持较低风险，但仍只能作为 stratified sampled evidence，不能写成全量安全保证。

## 7. 当前任务状态

EvoEmo selective generation 已完成：

```bash
scripts/15_run_evoemo.py \
  --freeze outputs/study_freeze_stable.json \
  --checkpoint outputs/final_model_m2b_stable/pm_final.joblib \
  --selection outputs/selection_stable.json \
  --protocol selective \
  --interaction-mode fixed
```

完成状态：

- `outputs/evoemo_selective/generation_summary.json`
- `outputs/evoemo_selective/artifact_attestation.json`
- status: `COMPLETE`
- expected dialogues: 816；
- completed dialogues: 816；
- expected turns: 8160；
- completed turns: 8160；
- failures: `[]`；
- malformed: `[]`；
- `external_ood_preflight.json`: ok。

评价 freeze：

- `outputs/evoemo_pairwise_eval_freeze.json`
- status: `FROZEN`
- scope: `evoemo_pairwise_response_evaluation`
- freeze sha256: `6603d334484e93d282170600811faf8629e682c6b60b23fa0914cccce7b25819`
- bound generation freeze: `e3e0e33ce3227a3032dc7929eb6f615c42784630739c2b79351da7f4d904571f`

Pairwise-only 评价状态：

- `outputs/evoemo_selective_metrics/selective_dialogue_pairs.jsonl`
- rows: 816 / 816；
- gate: FAILED；
- `selective_summary.json`: 未生成；
- `artifact_attestation.json`: 未生成；
- 结论：诊断可用，confirmatory 不可用。

V4 准备状态：

- `outputs/evoemo_response_v4/sample_plan.json`
- `outputs/evoemo_response_v4/cost_estimate_pilot.json`
- `outputs/evoemo_response_v4/cost_estimate_full.json`
- `outputs/evoemo_response_v4_eval_freeze.json`
- `outputs/evoemo_response_v4/response_summary.json`
- `outputs/evoemo_response_v4/response_statistical_summary.json`
- `outputs/evoemo_response_v4/response_resource_summary.json`
- `outputs/evoemo_response_v4/response_analysis_summary.md`
- `outputs/evoemo_response_v4/artifact_attestation.json`
- pilot dry-run: PASS；
- pilot API: PASS；
- full dry-run: PASS；
- full API: COMPLETE / ATTESTED；
- fail-closed 修正：artifact attestation 绑定 V4 evaluation freeze；summary / attestation 前强制 exact output validation；full-run 前强制 pilot compatibility check；

Sampled audit no-API plan：

- `outputs/evoemo_sampled_audit_plan/audit_sample_plan.json`
- `outputs/evoemo_sampled_audit_plan/audit_items.jsonl`
- `outputs/evoemo_sampled_audit_plan/audit_sample_plan.md`
- status: `PLANNED_NO_API`

Sampled audit evaluator：

- `scripts/17e_eval_evoemo_sampled_audit.py`
- `scripts/20d_freeze_evoemo_sampled_audit_eval.py`
- `outputs/evoemo_sampled_audit_eval_freeze.json`
- `outputs/evoemo_sampled_audit/cost_estimate_pilot.json`
- `outputs/evoemo_sampled_audit/cost_estimate_full.json`
- pilot dry-run: PASS；
- pilot API: PASS；
- pilot expected / completed calls: 16 / 16；
- pilot score rows: 16；
- pilot raw rows: 16；raw rows limit: 17；
- pilot actual usage: prompt 53,863 tokens；completion 2,683 tokens；estimated GPT-4o cost about 0.16 USD；
- pilot verdicts: acceptable 15；minor_issue 1；
- full dry-run: PASS；
- full API: COMPLETE / ATTESTED；
- full expected / completed calls: 80 / 80；
- full score rows / judgment rows / raw rows: 80 / 80 / 80；
- full raw rows gate: 80 <= 88；
- full actual usage: prompt 260,634 tokens；completion 13,349 tokens；estimated GPT-4o cost about 0.79 USD；
- full verdicts: acceptable 77；minor_issue 1；major_issue 2；
- PM sampled audit: selected-evidence misuse 0；unnecessary exposure 0；stale/conflict 0；unsupported personal claim 0；overall risk 0.020；
- full attestation: `outputs/evoemo_sampled_audit/artifact_attestation.json`
- full attestation sha256: `3ed5147dcb2dfafd07f1d0ad483e76d3333e520e1cbe4d1422d23ef04443ba7d`

下一步：

1. 将 V4 response / cost / sampled audit 结果整理进论文结果表；
2. claim boundary 写成 comparable response quality + lower resource cost + lower observed sampled-audit misuse/risk；
3. 不再继续 API 评测，除非明确需要额外 targeted audit。

## 8. 当前文件索引

最新 protocol：

- `snap/METACOM_V33_LATEST_PROTOCOL_ZH.md`

关键补充报告：

- `snap/METACOM_V33_ESCONV_STRATEGY_EVAL_RESULT_ZH.md`
- `snap/METACOM_V33_ESCONV_STRATEGY_ROUTING_DIAGNOSTIC_ZH.md`
- `snap/METACOM_V33_EVOEMO_PM_READINESS_ZH.md`
- `snap/METACOM_V33_STABLE_PM_EVOEMO_READINESS_ZH.md`
- `snap/METACOM_V33_EXTERNAL_EVALUATION_PLAN_FOR_GPT55_ZH.md`
- `docs/METACOM_V33_EVOEMO_PAIRWISE_GATE_FAILURE_ZH.md`
- `docs/METACOM_V33_EVOEMO_RESPONSE_V4_PLAN_ZH.md`
- `docs/METACOM_V33_EVOEMO_RESPONSE_V4_RESULT_ZH.md`
- `docs/METACOM_V33_EVOEMO_RESPONSE_V4_NOTE_TO_GPT55_ZH.md`
- `docs/METACOM_V33_ESCONV_AUTOMETRICS_APPENDIX_ZH.md`
- `docs/METACOM_V33_EVOEMO_SAMPLED_AUDIT_PLAN_ZH.md`

核心 artifacts：

- `outputs/study_freeze_stable.json`
- `outputs/final_model_m2b_stable/pm_final.joblib`
- `outputs/selection_stable.json`
- `outputs/evoemo_pm_readiness_stable_frozen.json`
- `outputs/esconv_strategy_eval/summary.json`
- `outputs/evoemo_selective_metrics/pairwise_gate_failure_diagnostic.json`
- `outputs/evoemo_response_v4/sample_plan.json`
- `outputs/evoemo_response_v4/cost_estimate_pilot.json`
- `outputs/evoemo_response_v4/cost_estimate_full.json`
- `outputs/evoemo_response_v4/response_summary.json`
- `outputs/evoemo_response_v4/response_statistical_summary.json`
- `outputs/evoemo_response_v4/response_resource_summary.json`
- `outputs/evoemo_response_v4/artifact_attestation.json`
- `outputs/esconv_strategy_eval/autometrics_sanity.json`
- `outputs/evoemo_sampled_audit_plan/audit_sample_plan.json`
- `outputs/evoemo_sampled_audit_eval_freeze.json`
- `outputs/evoemo_sampled_audit/cost_estimate_pilot.json`
- `outputs/evoemo_sampled_audit/cost_estimate_full.json`
- `outputs/evoemo_sampled_audit/pilot_summary.json`
- `outputs/evoemo_sampled_audit/pilot_scores.jsonl`
- `outputs/evoemo_sampled_audit/pilot_artifact_attestation.json`
- `outputs/evoemo_sampled_audit/audit_summary.json`
- `outputs/evoemo_sampled_audit/audit_scores.jsonl`
- `outputs/evoemo_sampled_audit/audit_judgments.jsonl`
- `outputs/evoemo_sampled_audit/audit_raw_calls.jsonl`
- `outputs/evoemo_sampled_audit/artifact_attestation.json`

## 9. 投稿写法提醒

可以写：

> PM improves response-oriented allocation and reduces misuse/cost relative to a strong rule, while conservative rule/guardrail remains better at omission and strategy overuse control.

不应写：

> PM is universally better than rule.

可以写：

> ESConv shows always-on Strategy RAG is harmful on average, motivating selective routing.

不应写：

> ESConv proves PM long-term memory ability.

可以写：

> EvoEmo fixed-input evaluation tests longitudinal memory allocation under controlled identical seeker inputs.

不应写：

> This is official ES-MemEval reproduction.
