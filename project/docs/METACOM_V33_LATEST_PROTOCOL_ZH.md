# MetaCom V3.3 最新研究方案与实验协议

更新时间：2026-06-30
状态：内部 full judging / M2b / stable PM 重训完成；ESConv strategy-only 外部评测完成；EvoEmo selective generation 已完成并生成 attestation；EvoEmo pairwise-only response evaluation 已完成 816/816 calls，但 AB/BA orientation consistency gate 失败，因此不能作为 confirmatory 外部结果。
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

> PM 学到一种 response 更高、memory misuse 更低、成本更低的资源分配倾向；但 strong rule 在 omission / strategy coverage 上更保守。因此论文应报告 PM 与 PM+guardrail / safety-first 变体，而不能声称 PM 全面优于 rule。

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

下一版 API 评价必须先过 pilot，不允许直接全量跑：

1. no-API dry-run
   - 统计调用数；
   - 统计 token；
   - 估算费用；
   - 超过预算直接拒跑。

2. 小样本 pilot
   - 先跑少量 turns；
   - 检查 JSON 成功率；
   - 检查候选顺序稳定性；
   - 检查 position bias；
   - pilot 不过，不进入正式跑。

3. 正式 response evaluation 改用更短、更稳的设计
   - 单 turn 为评价单位；
   - 同一 turn 内多候选打分；
   - 不再使用 10-turn bundle pairwise 作为 confirmatory 主评测；
   - 候选顺序固定 seed 随机并平衡；
   - 预注册抽样规模；
   - 保留 budget gate。

4. memory / strategy audit 禁止全量直接跑
   - 必须使用 stratified sampled audit；
   - memory omission audit 只在少量关键 turn 上使用完整 memory；
   - misuse audit 尽量只给 selected memory；
   - strategy audit 单独轻量 prompt。

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

下一步：

1. 先设计 EvoEmo Response Eval V4；
2. no-API dry-run 估算 token / cost；
3. 小样本 pilot 检查稳定性；
4. pilot 通过后才允许正式抽样评价；
5. 更新外部评测结果表与论文 claim boundary。

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

核心 artifacts：

- `outputs/study_freeze_stable.json`
- `outputs/final_model_m2b_stable/pm_final.joblib`
- `outputs/selection_stable.json`
- `outputs/evoemo_pm_readiness_stable_frozen.json`
- `outputs/esconv_strategy_eval/summary.json`
- `outputs/evoemo_selective_metrics/pairwise_gate_failure_diagnostic.json`

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
