# MetaCom V3.3 EvoEmo Response Eval V4 结果

更新时间：2026-06-30

## 1. 结论

EvoEmo Response Eval V4 已有效完成：

- output dir: `outputs/evoemo_response_v4/`
- final judge: GPT-4o
- expected calls: 204
- completed calls: 204
- raw rows: 204
- score rows: 1224
- artifact attestation: `outputs/evoemo_response_v4/artifact_attestation.json`
- status: `ATTESTED`

V4 结果支持的主张是：

> PM 在 fixed-input longitudinal response evaluation 中，相对 strong rule / best fixed 获得近似的 response quality，同时使用更少输入 token 和更少 memory resource；它不是 response quality 全面最优策略。

不能写成：

> PM 显著提升所有回复质量，或全面优于 rule / fixed baselines。

## 2. 运行完整性

V4 full-run 通过 exact output validation：

- judgment rows: 204 / 204
- score rows: 1224 / 1224
- raw successful calls: 204 / 204
- duplicate judgment keys: 0
- duplicate score keys: 0
- duplicate successful raw keys: 0

关键 freeze：

- generation freeze: `e3e0e33ce3227a3032dc7929eb6f615c42784630739c2b79351da7f4d904571f`
- evaluation freeze: `c9ccd1d21d1da8571710361ed9648b6696964edaf45d45067cea2887185c4bb3`
- full cost estimate hash: `74650cb61d42640ee673817b67953f3716e0c58c52f958c677706411d5650eb5`

Judge usage：

- prompt tokens: 1,468,275
- completion tokens: 147,644
- estimated cost without cache discount: about 5.15 USD

## 3. Response Quality

条件均值：

| Condition | n | Overall | Memory Appropriateness | Factual Grounding |
|---|---:|---:|---:|---:|
| session_rag_rs | 204 | 3.750 | 3.990 | 4.289 |
| no_memory_r0 | 204 | 3.745 | 3.995 | 4.284 |
| best_fixed | 204 | 3.662 | 3.946 | 4.270 |
| strong_rule | 204 | 3.662 | 3.951 | 4.275 |
| pm | 204 | 3.657 | 3.941 | 4.275 |
| full_history_rs | 204 | 3.618 | 3.951 | 4.240 |

PM paired overall deltas, using `(user_id, topic_index)` scenario-cluster bootstrap:

| Comparison | Mean PM - Baseline | 95% Cluster CI | P(delta < 0) | NI @ 0.05 | NI @ 0.10 |
|---|---:|---:|---:|---:|---:|
| PM - strong_rule | -0.005 | [-0.059, 0.044] | 0.564 | no | yes |
| PM - best_fixed | -0.005 | [-0.064, 0.054] | 0.559 | no | yes |
| PM - full_history_rs | +0.039 | [-0.064, 0.147] | 0.231 | no | yes |
| PM - session_rag_rs | -0.093 | [-0.167, -0.025] | 0.995 | no | no |
| PM - no_memory_r0 | -0.088 | [-0.167, -0.015] | 0.992 | no | no |

解释：

- PM 与 strong_rule / best_fixed 的 overall 差距非常小，不能说显著输了。
- 严格 `0.05` margin 下，PM 对 strong_rule / best_fixed 的 non-inferiority 没有被 cluster CI 确认，因为下界约为 `-0.06`。
- `0.10` practical margin 下，PM 对 strong_rule / best_fixed 可视为非劣。
- PM 在 overall 上低于 session_rag_rs / no_memory_r0；这说明 V4 不支持“PM response quality 最优”，但不推翻“PM 做资源质量成本 tradeoff”的主张。

## 4. Resource / Cost

V4 sampled turns 上的资源表：

| Condition | n | Mean Input Tokens | Mean Output Tokens | Mean Memory Tokens | RS Call Rate | Top Actions |
|---|---:|---:|---:|---:|---:|---|
| pm | 204 | 1294.6 | 68.1 | 683.3 | 0.941 | MSE+RS:103, MPMS+RS:31, MP+RS:26, MPE+RS:15 |
| strong_rule | 204 | 1627.4 | 69.5 | 1024.6 | 1.000 | MSE+RS:204 |
| best_fixed | 204 | 1654.8 | 70.5 | 1037.8 | 1.000 | MPMSME+RS:204 |
| session_rag_rs | 204 | 3233.2 | 72.2 | 2798.8 | 1.000 | SESSION_RAG+RS:204 |
| full_history_rs | 204 | 14079.8 | 69.4 | 14383.6 | 1.000 | FULL_HISTORY+RS:204 |
| no_memory_r0 | 204 | 395.5 | 59.9 | 0.0 | 0.000 | M0+R0:204 |

PM mean input token reductions:

| Comparison | Input Reduction |
|---|---:|
| PM vs strong_rule | 20.4% |
| PM vs best_fixed | 21.8% |
| PM vs session_rag_rs | 60.0% |
| PM vs full_history_rs | 90.8% |

PM is more expensive than `no_memory_r0`, as expected. `no_memory_r0` is a useful low-cost response baseline, not a long-term-memory policy.

## 5. Interpretation for Paper

可以写：

> In the EvoEmo-based fixed-input longitudinal evaluation, PM achieved response quality comparable to strong rule and best fixed policies while reducing resource use. It did not uniformly maximize response quality; rather, it learned a lower-cost allocation policy with similar quality against conservative structured-memory baselines.

更保守中文表述：

> V4 外部评测显示，PM 在 fixed-input response quality 上与 strong rule / best fixed 大体持平，同时降低资源成本；但 session_rag_rs / no_memory_r0 在 overall response score 上更高，因此论文应强调质量-成本-记忆风险的 tradeoff，而不是 PM 全面胜利。

不应写：

- PM 显著优于所有 baseline；
- PM 证明长期记忆会提升所有回复质量；
- no_memory_r0 分数高说明长期记忆无用；
- session_rag_rs 分数高说明 always-on RAG 是最佳系统。

## 6. Follow-up

下一步不建议直接跑全量 memory / strategy audit。应只做 sampled audit：

- memory misuse；
- unnecessary exposure；
- stale/conflict；
- unsupported personal claim；
- strategy over-structuring / premature advice。

审计样本应按 PM-vs-baseline disagreement、high-memory-cost turns、PM resource-saving turns 分层抽样。

## 7. Artifacts

- `outputs/evoemo_response_v4/response_summary.json`
- `outputs/evoemo_response_v4/response_statistical_summary.json`
- `outputs/evoemo_response_v4/response_resource_summary.json`
- `outputs/evoemo_response_v4/response_analysis_summary.md`
- `outputs/evoemo_response_v4/artifact_attestation.json`
- `scripts/17c_analyze_evoemo_response_v4.py`
