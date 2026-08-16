# Policy Manager Paper 1 官方评价优先级冻结（2026-08-16）

状态：`ACTIVE / MEASUREMENT PRIORITY OVERRIDE / PAPER-1`

本文件只解决一个容易再次漂移的问题：**Paper 1 最终到底由谁判成绩。**

> **正式论文的能力结论，以先行研究已经定义并公开使用的 ESC-Eval / ES-MemEval 官方指标为主。**
>
> 我们自己定义的 Quality / Risk / Function / internal pairwise rubric，不得重新升级为 Paper-1 主指标、主结果表中的能力分数、或论文成功与否的最终裁判。

如果本文件与 `PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md`、`PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md` 或旧 V5.3 measurement 文档在“内部指标是否属于主评价”上产生歧义，**以本文件为准。**

---

## 1. 最终证据层级

### Tier A — 正式能力评价：官方 benchmark，最高优先级

#### RQ1 — Selective Strategy-RAG

正式能力评价只使用 ESC-Eval 官方维度：

- Fluency
- Expression
- Empathy
- Information
- Skillful
- Humanoid
- Overall

正式比较 arms：

- R0 / No Strategy-RAG
- RS Fixed-High
- RS Matched-Random
- Learned RS-PM

因为 Strategy Bank 来源于 ESConv，primary transfer analysis 使用 non-ESConv-source English role cards；完整冻结 English set 为 secondary；ESConv-derived role cards 为 overlap sensitivity。

#### RQ2 — Selective typed memory

正式能力评价只使用 ES-MemEval 官方 task / metric family：

**QA**
- F1
- BERTScore
- LLM-as-Judge
- Recall@k / nDCG@k 作为 retrieval diagnostics

**Summarization**
- ROUGE-1 / ROUGE-2 / ROUGE-L
- Event Precision / Recall / F1
- official LLM Score

**Dialogue Generation**
- Observation Recall
- Weighted Score
- LT-Memory
- Personalization
- Emotional Support

正式比较 arms：

- No Memory
- Full History
- Official RAG Top-4
- Typed Fixed-High
- Typed Matched-Random
- Learned Typed-Memory PM

`-MP / -MS / -ME` 是 component ablation，贡献也必须回到这些官方指标上解释。

**禁止：**

- 用我们自己的 Quality 总分替代 ESC-Eval；
- 用我们自己的 Risk 总分替代 ES-MemEval；
- 为了得到一个更漂亮结论重新发明跨任务 composite score；
- 看完结果后只选择对 PM 最有利的官方指标。

---

## 2. Tier B — 客观系统效率：Cost，不是能力评分

Cost 保留，因为 Paper 1 的研究问题包含 selective resource allocation / performance-cost tradeoff。

允许正式报告：

- generator input tokens
- resource injected tokens
- output / total tokens
- retrieval / embedding calls
- median / p95 latency
- retry / failure
- 可恢复的 API cost

但必须明确：

> **Cost 是客观系统效率轴，不是 ESC 能力指标，也不是自建 Quality 分。**

因此：

- Cost 可以与官方 benchmark 指标一起出现在主结果表 / Pareto 图；
- Cost 不能把官方能力上的 material degradation “抵消掉”；
- “更便宜”本身不能证明 PM 更好；
- 正确叙事是：在官方能力非劣/改善的前提下，是否减少不必要资源；或在相近成本下，官方能力是否更好。

---

## 3. Tier C — 内部 Quality / Risk：只用于训练监督与测量资格化

我们自己的 Quality / Risk rubric **不是正式 benchmark**。

它们允许存在，只因为原始数据集没有直接提供 PM 的 `worth_opening` ON/OFF gold，尤其 RS 必须通过 matched OFF/ON 反事实生成获得训练弱监督。

### Internal Quality

如果 RS training 需要匿名 pairwise scorer，可使用简化的正向 rubric：

- Goal Fulfillment
- Emotional Support Value
- Useful Contribution
- Clarity & Naturalness

它只回答：

> 对这一对训练 response，哪一个提供了更多即时支持价值？

**它不进入 RQ1 正式能力主表，不作为 Paper-1 成功分。**

### Internal Risk

只做训练 pair / execution 的 material guard，例如：

- explicit boundary violation
- grounding / personal-evidence violation
- excessive directiveness / interaction burden

它只用于：

- 排除明显不可信/不可接受的训练 treatment；
- 防止“质量看起来高但发生明显 violation”的 pair 被标为 positive_open；
- supplemental error analysis。

**它不形成正式 Risk 总分，不与 ESC-Eval / ES-MemEval 并列当主评价。**

### Memory training 的优先顺序

MP/MS/ME 因为 ES-MemEval 已经有 task-specific official outcomes，正式 effect-label construction 应优先锚定相应官方任务指标，而不是再造一套万能内部 Quality judge。

内部 Q/R 在 memory 侧只作为：

- measurement qualification；
- integrity / safety guard；
- 无法由官方 scorer覆盖的补充诊断。

---

## 4. Tier D — 工程完整性：fail-closed audit，不是能力分数

以下内容单独记录：

- wrong owner
- future leakage
- gold/reference leakage
- stale / superseded misuse
- scaffold exposure
- treatment execution failure
- candidate/action mismatch

这些属于实验合法性 / 系统完整性检查。

它们可以使某个 treatment、effect row、甚至整次 run invalid，但**不能被合成为新的“Risk 总分”再与官方 benchmark 竞争主导权。**

---

## 5. `OPEN = ...` 公式的正确位置

以下逻辑：

```text
Eligible
AND measured marginal benefit
AND no disqualifying material violation
AND benefit worth added cost
→ positive_open training label
```

只属于：

> **内部训练标签派生规则 / resource-utility supervision。**

它不是：

- 论文主评价公式；
- Paper-1 总分；
- 最终 benchmark；
- 用来替代 ESC-Eval / ES-MemEval 的判决器。

最终论文问的是：

> 用这种内部监督训练出来的 PM，在完全同栈条件下，是否真的在 **ESC-Eval / ES-MemEval 官方指标**上形成有意义的能力—成本 tradeoff？

如果没有，内部 label accuracy 再漂亮也不能宣布 Paper 1 成功。

---

## 6. 主结果表与附加结果的边界

### 主结果必须出现

RQ1：ESC-Eval 官方七维 + 客观 Cost。

RQ2：ES-MemEval 官方 QA / Summary / DG 指标 + 客观 Cost。

Ablation：`-MP/-MS/-ME` 对官方指标的变化。

### 不应作为主能力结果出现

- internal Quality score
- internal Risk score
- Function score
- worth_opening accuracy 作为论文最终能力结论
- 自建 composite utility

这些最多进入：

- training-data qualification；
- method appendix；
- supplemental diagnostics；
- failure analysis。

---

## 7. Codex 实现规则

Codex 在迁移 measurement/evaluation 代码时必须遵守：

1. formal RQ1/RQ2 runner 的 capability-output schema 以 official scorer 字段为准；
2. internal pairwise Q/R scorer 只能被 training-effect / qualification pipeline 调用，formal benchmark runner 不得把它作为主结果 scorer；
3. formal result aggregation 不得生成 internal Q/R composite；
4. 主结果表生成器应把 official metrics 与 objective cost 分列；
5. internal Q/R/integrity 输出必须带 `diagnostic_only` / `training_only` provenance；
6. 任何代码若把 internal Quality/Risk 当作 Paper-1 final verdict，应作为 Phase-0 conflict 修复。

---

## 8. 一句话冻结

> **Paper 1 最终“好不好”，由 ESC-Eval / ES-MemEval 的同行官方指标判断；Cost 只负责客观效率；我们自己的 Quality/Risk 只负责训练弱监督、资格化和补充诊断，绝不重新升级成主评价体系。**
