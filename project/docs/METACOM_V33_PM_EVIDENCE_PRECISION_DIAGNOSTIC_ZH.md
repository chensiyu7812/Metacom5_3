# MetaCom V3.3 PM 证据精度诊断

更新时间：2026-07-02  
状态：no-API diagnostic complete  
相关输出：

- `outputs/evoemo_balanced_paired_audit/pilot_summary.json`
- `outputs/evoemo_balanced_paired_audit/pilot_scores.jsonl`
- `outputs/evoemo_balanced_paired_audit/pm_evidence_precision_diagnostic.md`
- `outputs/evoemo_balanced_paired_audit/pm_evidence_precision_diagnostic.json`
- `scripts/17h_analyze_pm_evidence_precision_diagnostic.py`

## 1. 为什么做这个诊断

EvoEmo Response V4 已显示：PM 在回复质量上接近 Rule / Fixed All Structured，同时输入 token 更低。但后续 balanced paired audit pilot 暴露出一个新问题：

> 当 PM 选择较重的 memory action 时，具体检索出的 memory snippets 可能不够贴合当前 turn。

这个问题不能简单解释成“PM 整体变差”，因为 PM 的定义本来是 pre-evidence resource router，而不是 fine-grained evidence selector。诊断目的就是拆清楚：

- 问题是否集中在某些 PM action；
- 是 PM action 选择问题、retrieval 问题，还是 judge / rubric 问题；
- 当前结果是否推翻 PM 的 quality-cost tradeoff 主张；
- 后续是否应该加 evidence gate，以及如何解释它的归因。

## 2. Balanced paired audit pilot 结果

pilot 技术状态是通过的：

- expected calls: 48；
- completed calls: 48；
- raw rows: 48；
- raw rows limit: 52；
- successful raw calls: 48；
- output validation: ok；
- 估算实际费用约 0.53 USD。

但 pilot 内容上对 PM 不利：

| Policy | n | Acceptable | Minor | Major | Mean evidence misuse | Mean overall risk |
|---|---:|---:|---:|---:|---:|---:|
| PM | 12 | 8 | 1 | 3 | 0.583 | 0.583 |
| Rule Policy | 12 | 9 | 1 | 2 | 0.417 | 0.417 |
| Fixed All Structured | 12 | 9 | 1 | 2 | 0.333 | 0.333 |
| Session Retrieval | 12 | 11 | 0 | 1 | 0.000 | 0.000 |

这说明：如果目标是证明 “PM 在 audit risk 上最好”，当前 pilot 不支持这个强主张。

## 3. 问题集中在哪里

诊断发现：

- PM 全量 EvoEmo 生成中，最常见动作是 `MSE+RS`：521 / 1020 turns；
- balanced audit pilot 中，PM action 分布是：
  - `MSE+RS`: 6；
  - `MPMS+RS`: 5；
  - `MP+RS`: 1；
- PM pilot 中所有 risky cases 都发生在 `MSE+RS`：4 / 4。

因此问题不是 PM 全面失效，而是：

> PM 高资源 memory action，尤其 `MSE+RS`，更容易暴露 retrieval/source granularity 的噪声。

pilot 也不是总体随机样本，而是压力样本：

- pilot primary strata:
  - `pm_saves_but_quality_lower`: 6；
  - `pm_high_resource`: 3；
  - `pm_quality_tie_or_win_with_savings`: 2；
  - `session_quality_higher_cost_tradeoff`: 1；
- pilot 中 10 / 12 个 PM units 覆盖 `pm_high_resource`；
- full plan 中这一比例是 37 / 50。

所以 pilot 更适合作为 stress diagnostic，而不是总体风险率估计。

## 4. 问题来源判断

### 4.1 PM 本身是粗粒度 router

PM 输入只包含：

- current text；
- recent dialogue；
- session depth；
- memory inventory metadata；
- action id。

PM 不读取 actual memory snippets。因此它能学习的是：

> 当前 turn 是否值得调用某类 memory source / Strategy RAG。

它不能保证：

> 具体检索出来的每条 memory snippet 都相关。

这不是 PM “不够聪明” 的普通失误，而是 pre-evidence 设定下的信息边界。

### 4.2 Retrieval 层是主要技术来源

当前 `MemoryRetriever` 使用 lexical ranking，并按 source 固定 top-k：

- MP: 2；
- MS: 2；
- ME: 3。

没有 relevance threshold，也没有 “不够相关则不返回” 的机制。

因此，当 PM 选择 `MSE+RS` 时，retriever 会从 MS 和 ME 中固定返回若干条候选。长 ME 记忆可能因为少量词重合被排上来，但同时夹带旧关系、旧工作、旧家庭事件等不必要细节。

这解释了 pilot 中的典型问题：当前 turn 讨论 family balance、work opportunity 或 fear of failure，但 selected memory 中混入 breakup、old friend、blog feedback、workplace harassment 等弱相关历史。

### 4.3 Audit rubric 也存在指标混合

pilot 中有一条 schema/verdict mismatch：

- `verdict = major_issue`；
- `overall_risk = 0`；
- `selected_evidence_misuse = 0`。

这说明 judge 有时把 “source set 不合适 / evidence 不贴” 记成 major issue，但没有映射到 primary risk 字段。

因此后续报告应拆分：

- evidence relevance risk；
- actual response misuse risk；
- source excess；
- response support sufficiency。

不要再只用一个 `overall resource-risk` 暗示排名。

## 5. 是否推翻当前论文主张

不推翻 PM 的主主张，但要求收紧边界。

当前证据仍支持：

> PM 是一个 pre-evidence resource router，能在固定生成器之外学习较低成本的资源调用倾向，并保持与强 baseline 接近的回复质量。

当前证据不支持：

> PM 能精确选择具体 memory snippets。

更安全的表述是：

> PM 学到的是 coarse resource allocation，而不是 fine-grained evidence selection。Balanced audit pilot 显示，高资源 PM action 仍可能带来弱相关 memory，因此 evidence precision 需要独立的 retrieval / evidence-selection 层解决。

## 6. 后续解决方向

### 6.1 不建议把 evidence gate 归功于 PM

可以在工程上加入 post-retrieval evidence gate：

```text
PM chooses source action
retrieve candidate evidence
evidence gate filters weakly relevant snippets
fixed generator writes response
```

但这样得到的是 `PM + Evidence Gate` 系统结果，不能写成 PM 本体选对了具体证据。

### 6.2 更干净的系统分层

推荐把架构明确拆成两层：

1. Pre-evidence PM
   - 决定是否调用 memory / strategy；
   - 决定调用哪些 source；
   - 控制成本和延迟；
   - 不读取 snippets。

2. Post-retrieval Evidence Selector
   - 读取候选 snippets；
   - 判断 relevance / helpfulness / staleness / intrusiveness；
   - 过滤弱相关或不必要 evidence；
   - 这是独立模块，不归功于 PM。

### 6.3 当前论文建议

当前论文不应强行补成 “PM audit 最好”。更稳的写法是：

> PM provides the strongest current quality-cost tradeoff, but the paired audit pilot shows that high-resource PM actions can still retrieve weakly focused memories. This distinguishes coarse resource routing from fine-grained evidence selection and motivates a separate evidence-selection layer.

## 7. 当前结论

Balanced paired audit pilot 是一次有效的诊断：

- 技术执行可靠；
- API 成本可控；
- 结果暴露出 PM 的真实边界；
- 问题主要来自 PM action 粒度和 retrieval/source granularity，而不是 response generation 全面失败；
- 后续应把 evidence precision 作为独立模块或 future work，而不是把它混入 PM 本体主张。

