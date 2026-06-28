# MetaCom V3.3 外部评测方案审查说明

生成日期：2026-06-28  
目的：提交给 GPT-5.5 Pro / 外部审计者检查当前 ESConv 与 EvoEmo 外部评测设计是否足以支撑论文主张，以及是否存在数据逻辑、泄露、评价闭环或指标不匹配风险。

## 1. 当前论文主张边界

本论文不主张训练新的 ESC 生成器，也不主张 RL、POMDP、临床疗效或真实用户 distress 改善。

当前可主张的中心问题是：

> 在固定回复生成器不变的情况下，一个 pre-evidence Policy Manager 是否能只基于当前对话状态和轻量 memory inventory metadata，选择是否调用长期记忆与 Strategy RAG，从而在回复质量、记忆误用风险、遗漏风险和资源成本之间取得更好的权衡？

更保守且当前最稳的主张是：

> 学习型 PM 能学到一种比强规则更高质量、更低成本、更少记忆误用的资源分配倾向；但强规则在 omission / strategy coverage 上更保守。因此最终系统应报告 PM 与 PM+guardrail 两种策略：前者展示学习到的质量-成本-误用权衡，后者展示更适合部署的安全边界。

论文不能写成：

- PM 全面优于 strong rule；
- ESConv 证明长期记忆能力；
- fixed seeker tracks 是官方 ES-MemEval leaderboard reproduction；
- 当前系统实现了 RL 或真实闭环长期疗效。

## 2. 内部开发结果的角色

内部 synthetic/support-gradient 数据用于：

- 训练 PM；
- 调 prompt / judge / gate；
- 选择 thresholds；
- 分析 PM 与 rule 的 tradeoff；
- 做 ablation 和 guardrail 设计。

内部数据不作为最终外部效果证明。

当前内部 5-fold 结果的大意是：

- PM response score 高于 strong rule；
- PM misuse risk 和 token cost 明显低于 strong rule；
- PM omission risk 与 strategy risk 高于 strong rule；
- PM+guardrail 可以把部分安全风险拉回到接近或优于 rule 的区域。

因此外部评测必须验证：

1. 回复质量是否真的不下降或提升；
2. Strategy RAG 在普通 ESC 中是否有帮助；
3. 长期记忆场景下 PM/PM+guardrail 的 cost / misuse / omission tradeoff 是否仍成立；
4. 外部评测是否避免训练 judge / final judge 同源闭环。

## 3. ESConv 外部评测设计

### 3.1 ESConv 的定位

ESConv 是单 session 情感支持对话数据。它没有跨 session 长期记忆。

因此 ESConv 只用于评估：

1. Strategy RAG 是否改善或至少不伤害普通 ESC 回复质量；
2. Strategy RAG 是否引入 premature advice / over-structuring；
3. 在没有长期记忆时，系统是否避免 unsupported personal claims；
4. ESConv single-session OOD 情况下，不强行使用长期记忆 PM。

ESConv 不用于证明：

- 长期记忆能力；
- PM 在 longitudinal memory allocation 上优于 rule；
- ES-MemEval 风格的跨 session 记忆效果。

### 3.2 ESConv 数据范围

当前本地数据：

- `data/external/ESConv.json`
  - 官方 ESConv 文件；
  - 1300 dialogues；
  - sha256: `aa0556c5b330562ba009c1cd5137486bfa2a7255f33225a6524cd58f7efdd9af`。

当前 test runtime：

- `data/esconv_test/runtime_states.jsonl`
  - 2275 test turns；
  - 169 dialogues；
  - 每个 state 仅允许 `M0+R0` 与 `M0+RS`。

Strategy bank：

- `data/strategy/strategy_cards.jsonl`
  - 12429 strategy cards；
  - 只从 ESConv train split 构建；
  - 已对 EvoEmo overlap 做 exact / near-duplicate audit；
  - 81 个 ESConv dialogues 因 exact 或 high shingle Jaccard overlap 被排除。

### 3.3 ESConv 当前已完成生成

已完成：

- `outputs/esconv_sweep/action_outcomes.jsonl`
  - 4550 rows = 2275 states × 2 actions；
  - actions: `M0+R0`, `M0+RS`；
  - generator: `meta/llama-3.1-8b-instruct` via NVIDIA API；
  - NVIDIA generator 成本对当前用户为免费；
  - attestation: `outputs/esconv_sweep/artifact_attestation.json`。

未完成：

- GPT-4o final judge 的 ESConv pairwise evaluation 尚未正式运行。

### 3.4 ESConv 正式评价入口

新增脚本：

- `scripts/14a_eval_esconv_strategy_only.py`

该脚本只做：

- 读取 frozen ESConv runtime；
- 读取 `M0+R0` / `M0+RS` 已生成 replies；
- 用 final judge 做 blind pairwise comparison；
- 不加载 PM checkpoint；
- 不调用 LearnedPMPolicy；
- 不触发 ESConv single-session OOD；
- 不把 action id / evidence 暴露给 response judge。

dry-run 已通过：

- expected pairs: 2275；
- dialogue clusters: 169；
- new study freeze sha256: `0e6cb4e2c84da57532d04bb98bf23379acd70c9d00014ee18b96a99666d28798`；
- preflight: `CONFIRMATORY_READY`。

### 3.5 ESConv 主指标

ESConv 主指标：

1. `M0+RS` vs `M0+R0` pairwise response preference
   - blind judge；
   - W/T/L；
   - preference score；
   - dialogue-cluster bootstrap 95% CI。

2. Unsupported personal claim / false-memory rate
   - 因 ESConv 没有长期记忆，任何编造长期个人事实都应被视为风险；
   - 可由 final judge 或人工子集审查。

3. Strategy risk
   - strategy relevance；
   - premature advice；
   - over-structuring。

4. Cost
   - prompt tokens；
   - strategy tokens；
   - retrieval calls；
   - output tokens。

ESConv 辅助指标：

- BLEU-1/2/3/4；
- ROUGE-L；
- Distinct-1/2；
- response length；
- strategy label recall@retrieved-k。

这些辅助指标只用于和 ESConv 传统生成论文接轨，不作为本文主结论。PPL 不适合当前 black-box API generator，除非后续使用可返回 logprobs 的本地模型。

### 3.6 ESConv 全量还是抽样

推荐：全量。

理由：

- 2275 pairwise calls 规模可控；
- ESConv 是普通 ESC 外部稳定性证据；
- 抽样会削弱“Strategy RAG 是否普遍有帮助”的可信度。

若预算受限，可做预注册抽样：

- 按 dialogue cluster 抽样；
- 固定随机种子；
- 保持 strategy label 分布；
- 不在看到结果后重抽。

但当前建议全量跑 `M0+R0` vs `M0+RS`。

## 4. EvoEmo / ES-MemEval-style 外部评测设计

### 4.1 EvoEmo 的定位

EvoEmo / ES-MemEval-derived 数据用于长期记忆外部验证。

当前本地数据：

- `data/external/evo_emo.json`
  - 18 users；
  - 401 historical sessions；
  - 34 subsequent topics；
  - sha256: `f30698e87fddaeff51270a666c654da604f487a3456ec60d2b6ae08a6fecd420`。

注意：

- 401 是 historical session 规模，不是 401 个独立正式测试题；
- 当前 dialogue-generation 评测核心是 34 user-topic scenarios × seeds × turns；
- fixed seeker tracks 是 controlled extension，不是官方 ES-MemEval 原流程。

论文应称为：

> EvoEmo-based / ES-MemEval-style fixed-input longitudinal evaluation

不应称为：

> official ES-MemEval reproduction

### 4.2 Fixed seeker tracks

已完成：

- `outputs/evoemo_fixed_tracks/fixed_seeker_tracks.jsonl`
  - 102 tracks；
  - 34 user-topic combos × 3 seeds；
  - 每条约 10 seeker turns；
  - failures: 0；
  - attestation: `outputs/evoemo_fixed_tracks/artifact_attestation.json`。

fixed tracks 的目的：

- 所有 policy 面对完全相同 seeker inputs；
- 避免不同 policy 触发不同 seeker 后续反应导致评价不可比；
- 牺牲真实闭环交互，换取政策间公平对比。

这支持的是：

> fixed-input policy comparison

不支持：

> policy changes user future state / distress in a live environment

### 4.3 EvoEmo 条件与 baselines

建议正式条件：

1. PM；
2. PM+guardrail；
3. Strong Rule；
4. Best Fixed；
5. Budget-Matched Fixed；
6. M0+R0；
7. All structured memory / full structured diagnostic；
8. Strategy-only / memory-only diagnostic if needed。

最小可报告条件：

- PM；
- PM+guardrail；
- Strong Rule；
- Best Fixed or Budget-Matched Fixed；
- M0+R0。

### 4.4 EvoEmo 主指标

EvoEmo 主指标：

1. Response quality
   - blind pairwise final judge；
   - PM / PM+guardrail vs strong rule；
   - W/T/L；
   - preference score；
   - user-topic clustered or hierarchical bootstrap CI。

2. Memory misuse risk
   - unsupported personal claim；
   - stale/conflicting use；
   - unnecessary exposure；
   - selected source relevance/utilization。

3. Omission risk
   - M0 omission appropriateness；
   - M2b selected-set omission：非 M0 动作用了记忆但是否漏掉关键 memory source。

4. Strategy risk
   - relevance/utilization；
   - over-structuring；
   - premature advice。

5. Cost
   - retrieval calls；
   - memory tokens；
   - strategy tokens；
   - total prompt tokens；
   - output tokens；
   - latency if available。

6. OOD / fallback diagnostics
   - PM 是否处于训练 feature domain；
   - fallback 触发率；
   - fallback 后是否仍可公平比较。

### 4.5 EvoEmo 全量还是抽样

推荐生成阶段：全量 fixed tracks × selected policies。

理由：

- 34 topics 本身不大；
- 18 users 必须完整覆盖；
- 长期记忆 claim 依赖 user-level coverage；
- 不应只抽 n=30 当作长期记忆外部主证据。

推荐评价阶段分层：

第一阶段，低成本：

- 全量 response pairwise；
- 至少 PM / PM+guardrail vs strong rule；
- 用 GPT-4o final judge；
- 用 user/topic cluster bootstrap。

第二阶段，若预算允许：

- full selective memory/strategy audit；
- 或按 user-topic cluster 预注册抽样 audit。

若 selective audit 需要抽样，抽样规则：

- 以 user-topic scenario 为 cluster；
- 每个 user 至少覆盖一个 scenario；
- 固定随机种子；
- policy 条件成对保留；
- 不根据 response pairwise 结果重抽；
- 抽样前写入 protocol / freeze notes。

### 4.6 EvoEmo official-style 指标

Official observation recall / observation usage 类指标可以作为 future extension 或 appendix，但当前不建议作为第一篇主证据。

原因：

- 当前 fixed tracks 不是官方 ES-MemEval 原流程；
- official observation audit 调用量可能很高；
- 本文核心是资源分配 tradeoff，而不是复现 leaderboard。

第一篇主证据应以 selective-memory protocol 为主：

- response quality；
- memory misuse；
- omission；
- strategy risk；
- cost。

## 5. Judge 与模型家族设置

生成器：

- NVIDIA `meta/llama-3.1-8b-instruct`；
- family: llama；
- 当前用户 NVIDIA API 免费。

Training judge：

- Gemini Flash-Lite；
- family: google_gemini。

Final judge：

- GPT-4o；
- family: openai_gpt4o。

Seeker simulators：

- Mixtral / Mistral family；
- Qwen alternative family present in config。

Model-family independence 已进 preflight：

- generator ≠ training judge；
- training judge ≠ final judge；
- generator ≠ seeker；
- seeker simulators 至少两个 family。

## 6. 需要 GPT-5.5 Pro 重点检查的问题

请重点审查：

1. ESConv strategy-only eval 是否足够回答“Strategy RAG 是否帮助普通 ESC 回复”；
2. ESConv 不使用 PM 是否会削弱论文主张；
3. EvoEmo fixed-input longitudinal evaluation 是否足以支撑长期记忆资源分配 claim；
4. 是否必须运行 full selective memory/strategy audit，还是 pairwise + sampled audit 足够；
5. PM+guardrail 是否应作为主系统，PM 单独作为分析变体；
6. 是否还存在 data leakage / overlap / future memory 风险；
7. 当前指标是否覆盖 response quality、misuse、omission、strategy risk、cost；
8. 是否需要补传统 ESConv 指标 BLEU/ROUGE/Distinct；
9. 是否应避免使用 PPL / ACC / s_norm 这类不匹配本文任务的指标；
10. 当前 claim 是否过强，是否应进一步收缩。

## 7. 当前下一步建议

推荐先运行：

```bash
scripts/14a_eval_esconv_strategy_only.py --endpoint final_judge
```

这会完成 ESConv 的 `M0+RS` vs `M0+R0` 全量 pairwise final judge。

之后再运行 EvoEmo：

1. selective dialogue generation；
2. pairwise-only final judge；
3. 若结果正常，再补 memory / strategy audit。

不建议现在运行：

- full official ES-MemEval observation scoring；
- ESConv PM-vs-rule evaluation；
- 未预注册抽样的 selective audit；
- 同 family final judge。

