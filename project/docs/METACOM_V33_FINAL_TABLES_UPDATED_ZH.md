# MetaCom V3.3 最终表格体系与结果口径

更新时间：2026-07-14

这份文件统一当前论文中的方法命名、表格口径和结果解释。之后论文、组会和 rebuttal 草稿中建议全部使用这一版，避免继续混用旧名。

## 0. 关键修正

V4 response judge schema 原本包含 `overall` 和 `emotional_support` 两个字段，但在本轮 `outputs/evoemo_response_v4/response_scores.jsonl` 中二者逐行完全相同。因此：

- 不再把 `overall` 写成独立的 holistic quality；
- 主表使用 `Support Rating` 表示原 `overall/emotional_support` 字段；
- 同时报告多个子维度，避免用单一总分掩盖结果结构；
- 原始 JSON 字段不改，以保证可复现；论文表格和解释口径改。

`Support Rating` 的含义是 judge 对回复情感支持性的评分，主要反映共情、承接、安抚和支持表达。它不是 personalization、memory appropriateness、factual grounding 等维度的数学综合分。

## 1. Final Naming Convention

| Internal condition | Final paper name |
|---|---|
| `no_memory_r0` | Context Only |
| `pm` | Learned PM (Ours) |
| `strong_rule` | Rule Source Selector |
| `best_fixed` | Structured Memory Top-k + Strategy |
| `session_rag_rs` | Raw Session Top-4 + Strategy |
| `full_history_rs` | All Raw Sessions + Strategy |
| `cost_matched_me_r0` | Cost-Matched Event Memory |
| `pm_evidence_selector` | Learned PM + Context Filter (prototype) |

命名原则：

- `PM` 保留为 Policy Manager，不写成 “best selector”；
- `Strategy` 指 strategy-card retrieval，不表示更换生成器；
- `Context Filter` 是 post-retrieval prototype，用于过滤已检索出的弱相关记忆条目，不代表 PM 本体已经学会 item-level 精筛。

## 2. Table 1. Evaluation Conditions and Resource Definitions

| Condition name | Structured memory context | Raw session context | Strategy cards | What the generator sees |
|---|---|---|---|---|
| Context Only | None | None | Off | Current seeker turn and recent dialogue only |
| Learned PM (Ours) | PM-selected MP/MS/ME sources; top-k items retrieved within selected sources | None | PM-selected On/Off | Current context plus PM-selected structured memories and optional strategy cards |
| Rule Source Selector | Rule-selected structured memory sources using source-catalog similarity, with at most two sources; top-k items retrieved within selected sources | None | Threshold-based On/Off | Current context plus rule-selected structured memories and optional strategy cards |
| Structured Memory Top-k + Strategy | MP + MS + ME all enabled; top-k items retrieved from each source | None | On | Current context plus top-k profile, session-summary, and event memories, plus strategy cards |
| Raw Session Top-4 + Strategy | None | Top 4 prior raw dialogue sessions ranked by query similarity to session summary plus dialogue text | On | Current context plus four retrieved historical dialogue sessions and strategy cards |
| All Raw Sessions + Strategy | None | All prior raw dialogue sessions | On | Current context plus all historical dialogue sessions and strategy cards |
| Cost-Matched Event Memory | ME only; top-k event memories retrieved | None | Off | Current context plus top-k event memories only |

Table note:

Current context denotes the current seeker turn and recent dialogue. MP, MS, and ME denote profile memory, session-summary memory, and event memory. Structured-memory conditions retrieve concrete memory items from selected sources using source-specific top-k retrieval. Raw-session conditions inject prior dialogue sessions directly as raw text rather than structured memory items. When strategy cards are On, retrieved strategy cards are added to the prompt. In the EvoEmo run, the Rule Source Selector selected MS+ME+Strategy for all evaluated turns. Cost-Matched Event Memory is a post-hoc diagnostic fixed action (`ME+R0`) chosen because its observed input-token cost closely matches PM on the V4 sample.

## 3. Table 2. Data Sources and Evaluation Roles

| Source | Role | Used to train PM? | What it tests |
|---|---|---|---|
| Synthetic development states | Internal action sweep and PM supervision | Yes | Learns resource-action preferences from silver utility labels |
| ESConv | External strategy diagnostic | No | Tests whether strategy-card retrieval should be always on under a fixed generator |
| EvoEmo fixed-input longitudinal tracks | External longitudinal evaluation | No | Tests response quality, resource cost, observed latency, and selected-context risk |
| Stratified selected-context audit | Diagnostic risk analysis | No | Tests context misuse, unnecessary exposure, stale/conflicting use, unsupported personal claims, and strategy-use errors |

Table note:

Synthetic development states are used for offline PM supervision. ESConv and EvoEmo-based evaluations are not used to train the PM.

## 4. Table 3. Evaluation Criteria and Judge Visibility

| Evaluation target | Judge input | Hidden from judge | Metrics | Scale |
|---|---|---|---|---|
| Response support quality | Fixed seeker turn, recent dialogue, authorized user context, anonymous responses | Policy name, action code, token cost | support rating, personalization, memory appropriateness, factual grounding, temporal consistency, non-intrusiveness | 1-5 |
| Selected-context risk | Response, selected memory/strategy context, relevant user context | Policy name, sampling reason, cost | context misuse, unnecessary exposure, stale/conflicting use, unsupported personal claim | 0-3 |
| Strategy-use risk | Response, selected strategy card if any, dialogue context | Policy name, action code | over-structuring, premature advice, missed strategy opportunity | 0-3 |
| Resource cost | Generation logs | Not judged by LLM | input tokens, retrieval calls | numeric |
| Observed response time | Generation logs | Not judged by LLM | mean latency, p95 latency | seconds |

Table note:

Response time and token cost are log-based metrics, not LLM-judged metrics. Policy names, action codes, and token costs are hidden from quality and risk judges. The raw `overall` field in V4 is not used as an independent holistic aggregate because it exactly matched `emotional_support` in this run.

## 5. Table 4. Controlled Longitudinal Evaluation

### Table 4A. Support rating, resource cost, and observed latency

| Method | Support Rating ↑ | Input tokens ↓ | Mean time ↓ | P95 time ↓ |
|---|---:|---:|---:|---:|
| Context Only | 3.745 | 393 | 0.66s | 1.10s |
| Learned PM (Ours) | 3.657 | 1292 | 1.95s | 2.63s |
| Rule Source Selector | 3.662 | 1624 | 3.23s | 4.08s |
| Structured Memory Top-k + Strategy | 3.662 | 1651 | 2.02s | 2.60s |
| Raw Session Top-4 + Strategy | 3.750 | 3237 | 2.17s | 2.98s |
| All Raw Sessions + Strategy | 3.618 | 14076 | 2.40s | 3.05s |

Table note:

Input tokens are the primary resource-cost metric. Observed response time is reported from generation logs as a deployment diagnostic, not as a randomized latency benchmark. `Support Rating` is the raw `overall/emotional_support` field and should not be read as a holistic aggregate over all response dimensions.

### Table 4B. Response subdimensions

| Method | Support ↑ | Personalization ↑ | Memory Approp. ↑ | Factual ↑ | Temporal ↑ | Non Intrusive ↑ |
|---|---:|---:|---:|---:|---:|---:|
| Context Only | 3.745 | 3.451 | 3.995 | 4.284 | 4.314 | 4.319 |
| Learned PM (Ours) | 3.657 | 3.353 | 3.941 | 4.275 | 4.304 | 4.294 |
| Rule Source Selector | 3.662 | 3.382 | 3.951 | 4.275 | 4.304 | 4.299 |
| Structured Memory Top-k + Strategy | 3.662 | 3.387 | 3.946 | 4.270 | 4.299 | 4.314 |
| Raw Session Top-4 + Strategy | 3.750 | 3.441 | 3.990 | 4.289 | 4.319 | 4.333 |
| All Raw Sessions + Strategy | 3.618 | 3.377 | 3.951 | 4.240 | 4.275 | 4.279 |

Interpretation:

- Context Only is a strong local-response baseline, showing that many fixed-input turns do not require extra memory or strategy resources.
- Raw Session Top-4 + Strategy obtains the highest support rating, but at substantially higher token cost than PM.
- Learned PM is close to Rule Source Selector and Structured Memory Top-k + Strategy in support rating while using fewer input tokens.
- All Raw Sessions + Strategy is much more expensive and lower in support rating under the fixed 8B generator.
- Cost-Matched Event Memory is a strong same-budget fixed-action diagnostic. It does not prove event memory is universally optimal, but it shows that the current supervised PM has not demonstrated a robust external advantage over same-budget fixed routing.

### Table 4C. Cost-matched fixed-action diagnostic

| Comparison | n | PM Support | Fixed Support | PM - Fixed | 95% cluster bootstrap CI | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| Learned PM vs Cost-Matched Event Memory | 204 | 3.755 | 3.926 | -0.172 | [-0.250, -0.093] | PM lower at matched cost |

Table note:

Cost-Matched Event Memory uses fixed `ME+R0`: top-k event memories, no Strategy RAG. It is not a trained policy. This diagnostic was added to test whether PM's external value exceeds a same-budget constant action. Table 4C is scored in a separate two-condition V4 diagnostic prompt, so its absolute scores should not be merged into Table 4A/4B; the paired PM minus fixed delta is the key statistic.

### Table 4D. Forced-swap blind probe for the cost-matched comparison

| Probe | n units | calls | PM - ME+R0 Support | PM - ME+R0 Personalization | Resolved preference |
|---|---:|---:|---:|---:|---|
| PM vs Cost-Matched Event Memory | 40 | 80 | -0.150 [-0.250, -0.050] | -0.138 [-0.238, -0.050] | PM 2 / tie 27 / ME+R0 11 |

Table note:

The forced-swap probe judges each sampled unit twice, once with PM first and once with ME+R0 first. A resolved preference is counted only after considering both orders; order disagreement is resolved to tie. The result confirms that the direction of the cost-matched diagnostic is not purely an order artifact, while also showing that most sampled units are ties.

## 6. Table 5. Stress-test Audit of Selected Context and Context Filter Prototype

### Panel A. Baseline comparison on 12 matched high-resource units

| Method | n | Source-set fit ↑ | Context misuse ↓ | Sufficiency ↑ | Major issues ↓ |
|---|---:|---:|---:|---:|---:|
| Learned PM (Ours) | 12 | 2.08 | 0.583 | 3.42 | 3 |
| Rule Source Selector | 12 | 2.42 | 0.417 | 3.25 | 2 |
| Structured Memory Top-k + Strategy | 12 | 2.17 | 0.333 | 3.42 | 2 |
| Raw Session Top-4 + Strategy | 12 | 2.75 | 0.000 | 3.08 | 1 |

### Panel B. Filter ablation on 24 PM-selected cases

| Method | n | Source-set fit ↑ | Context misuse ↓ | Sufficiency ↑ | Major issues ↓ |
|---|---:|---:|---:|---:|---:|
| Learned PM (Ours) | 24 | 2.13 | 0.542 | 3.42 | 5 |
| Learned PM + Context Filter (prototype) | 24 | 2.04 | 0.125 | 3.58 | 1 |

Table note:

Source-set fit is judge-rated source-set appropriateness on a 1-5 scale. Context misuse is a 0-3 severity score measuring observed misuse of selected context in the response. Sufficiency is the response support sufficiency score on a 1-5 scale. Major issues are based on the overall audit verdict and may reflect misuse, inappropriate source selection, or insufficient support. Panel A and Panel B use different sampled sets and should not be interpreted as a single matched experiment. Panel A is a stress-test diagnostic, not a population-level safety estimate.

Suggested results wording:

> Table 5 shows that selected-context reliability involves multiple dimensions. In Panel A, Raw Session Top-4 + Strategy obtains the highest source-set fit and the lowest observed context misuse, but also the lowest response sufficiency, indicating that avoiding context misuse does not necessarily yield sufficient support. Learned PM provides stronger sufficiency but shows higher selected-context misuse in these high-resource stress cases, suggesting that source-level PM decisions are still coarse. Panel B evaluates a diagnostic item-level Context Filter. The filter reduces context misuse from 0.542 to 0.125 and major issues from 5 to 1, while slightly improving sufficiency from 3.42 to 3.58. This suggests that source-level PM and item-level filtering are complementary.

中文解释：

Learned PM 是粗粒度 source router；在压力样本中，它能做资源分配，但仍可能选到弱相关 context。Context Filter prototype 能减少这种 item-level failure mode，而且不是靠简单删光 memory 取胜。

## 7. Appendix Table A1. Filtering Behavior of the Context Filter Prototype

| Filtering statistic | Value |
|---|---:|
| Prototype cases | 24 |
| Cases retaining memory | 18 |
| Cases dropping all memory | 6 |
| Mean memories before filtering | 4.21 |
| Mean memories after filtering | 1.54 |
| Mean memory tokens before filtering | 676.3 |
| Mean memory tokens after filtering | 64.5 |
| All-dropped cases with major issue | 0/6 |
| All-dropped cases response sufficiency | 3.67 |

Table note:

This diagnostic table checks whether the Context Filter reduces risk simply by deleting all memory. The filter retains memory in most cases while substantially reducing memory-token load.

## 8. Result Boundaries

可以写：

> The experiments show that external memory and strategy resources are not uniformly beneficial. Learned PM provides a deployable source-level routing mechanism and reduces cost relative to high-resource raw-history baselines, but a cost-matched fixed event-memory action remains a strong same-budget baseline under the current LLM-judge setting. Stress-test diagnostics further show that item-level context filtering is still needed for memory precision.

> With a stronger instruction-tuned generator, context-only responses are already highly competitive. This shifts the bottleneck from basic supportive generation to calibrated use of external resources: when to use memory, which source to use, how much to retrieve, and when to turn strategy support off.

不应写：

- PM is the highest-quality method overall.
- PM is non-inferior to all baselines.
- PM outperforms same-budget fixed routing.
- Context Only proves long-term memory is unnecessary.
- Raw Session Top-4 + Strategy proves always-on memory is the best system.
- Context Filter proves PM itself learned fine-grained memory selection.

最稳中文主张：

> 当前结果支持将长期情感支持中的记忆和策略调用建模为检索前资源分配问题，但不支持“当前监督式 PM 已经优于同预算固定路由”。PM 相对全历史等高资源 raw-history 基线能降低成本，但 `ME+R0` 同预算固定动作在 EvoEmo V4 与 forced-swap probe 中均表现为强 baseline。这说明当前 PM 更应被解释为粗粒度 source router 原型，而不是已经完成外部校准的自适应策略；no-memory、raw-session 和 cost-matched fixed baseline 的强表现共同说明，在强 LLM 生成器条件下，核心瓶颈已经从“能否生成支持性回复”转向“何时、如何、以多大成本调用外部资源”。
