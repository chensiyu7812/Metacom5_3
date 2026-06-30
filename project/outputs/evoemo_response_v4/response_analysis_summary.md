# EvoEmo Response V4 离线统计与资源汇总

生成时间：2026-06-30T04:37:17.183418+00:00

## 结论摘要

- V4 full-run 输出完整，后续统计不调用 API。
- PM 的 overall response quality 与 `strong_rule` / `best_fixed` 非常接近；严格 `0.05` margin 下需要看 CI，不应写成全面质量胜利。
- PM 在同一 V4 sampled turns 上显著降低输入 token / 检索资源，尤其相对 `session_rag_rs` 和 `full_history_rs`。
- `no_memory_r0` 在 response score 上最高之一且成本最低，说明很多 fixed-input turn 并不需要额外资源；这正是“资源选择”问题，而不是 always-on RAG 胜利。

## 条件均值

| Condition | n | Overall | Emotional | Memory appr. | Factual |
| --- | --- | --- | --- | --- | --- |
| best_fixed | 204 | 3.662 | 3.662 | 3.946 | 4.270 |
| full_history_rs | 204 | 3.618 | 3.618 | 3.951 | 4.240 |
| no_memory_r0 | 204 | 3.745 | 3.745 | 3.995 | 4.284 |
| pm | 204 | 3.657 | 3.657 | 3.941 | 4.275 |
| session_rag_rs | 204 | 3.750 | 3.750 | 3.990 | 4.289 |
| strong_rule | 204 | 3.662 | 3.662 | 3.951 | 4.275 |

## PM Pairwise Deltas

Delta 为 `PM - baseline`。CI 使用 `(user_id, topic_index)` scenario-cluster bootstrap。

| Comparison | n | Mean delta | 95% cluster CI | P(delta<0) | NI margins |
| --- | --- | --- | --- | --- | --- |
| pm - strong_rule | 204 | -0.005 | [-0.059, 0.044] | 0.564 | 0.05:no, 0.1:yes |
| pm - best_fixed | 204 | -0.005 | [-0.064, 0.054] | 0.559 | 0.05:no, 0.1:yes |
| pm - session_rag_rs | 204 | -0.093 | [-0.167, -0.025] | 0.995 | 0.05:no, 0.1:no |
| pm - full_history_rs | 204 | 0.039 | [-0.064, 0.147] | 0.231 | 0.05:no, 0.1:yes |
| pm - no_memory_r0 | 204 | -0.088 | [-0.167, -0.015] | 0.992 | 0.05:no, 0.1:no |

## V4 Sampled Resource Cost

| Condition | n | Input tok | Output tok | Memory tok | Strategy tok | RS rate | Top actions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| best_fixed | 204 | 1654.8 | 70.5 | 1037.8 | 261.3 | 1.000 | MPMSME+RS:204 |
| full_history_rs | 204 | 14079.8 | 69.4 | 14383.6 | 261.3 | 1.000 | FULL_HISTORY+RS:204 |
| no_memory_r0 | 204 | 395.5 | 59.9 | 0.0 | 0.0 | 0.000 | M0+R0:204 |
| pm | 204 | 1294.6 | 68.1 | 683.3 | 245.4 | 0.941 | MSE+RS:103, MPMS+RS:31, MP+RS:26, MPE+RS:15 |
| session_rag_rs | 204 | 3233.2 | 72.2 | 2798.8 | 261.3 | 1.000 | SESSION_RAG+RS:204 |
| strong_rule | 204 | 1627.4 | 69.5 | 1024.6 | 261.3 | 1.000 | MSE+RS:204 |

## PM Resource Reductions

| Comparison | PM input | Baseline input | Input reduction | Memory reduction | Retrieval reduction |
| --- | --- | --- | --- | --- | --- |
| pm vs strong_rule | 1294.6 | 1627.4 | 0.204 | 0.333 | 0.095 |
| pm vs best_fixed | 1294.6 | 1654.8 | 0.218 | 0.342 | 0.321 |
| pm vs session_rag_rs | 1294.6 | 3233.2 | 0.600 | 0.756 | -0.358 |
| pm vs full_history_rs | 1294.6 | 14079.8 | 0.908 | 0.952 | -0.358 |
| pm vs no_memory_r0 | 1294.6 | 395.5 | -2.273 | NA | NA |

## Judge Cost

- raw rows: 204
- prompt tokens: 1468275
- completion tokens: 147644
- estimated cost without cache discount: $5.15

## 写作边界

可以写：V4 supports comparable fixed-input response quality relative to strong rule / best fixed, while using fewer resources.

不应写：PM universally improves response quality, 或 RAG 本身解决了 ESC generation。
