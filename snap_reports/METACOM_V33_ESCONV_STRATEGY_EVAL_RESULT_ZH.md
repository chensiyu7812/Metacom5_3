# MetaCom V3.3 ESConv Strategy-Only 外部评测结果

日期：2026-06-29  
实验入口：`scripts/14a_eval_esconv_strategy_only.py`  
评价模型：GPT-4o final judge  
比较对象：`M0+RS` vs `M0+R0`

## 1. 实验定位

该实验不评估长期记忆，也不评估 PM 或 PM+guardrail。

ESConv 是单 session 情感支持数据，因此本实验只回答：

> 在普通单会话情感支持对话中，always-on Strategy RAG 是否改善回复质量，还是会增加成本并伤害回复质量？

## 2. 完整性

- 状态：`COMPLETE`
- pairwise comparisons：2275 / 2275
- dialogue clusters：169
- API / schema errors：0
- attestation：`outputs/esconv_strategy_eval/artifact_attestation.json`

## 3. 主要结果

| 指标 | 数值 |
|---|---:|
| `M0+RS` wins | 696 |
| ties | 457 |
| `M0+R0` wins | 1122 |
| RS preference score | 0.4064 |
| dialogue-cluster bootstrap 95% CI | [0.3857, 0.4251] |
| strategy recall@retrieved-k | 0.4145 |

解释：

`M0+RS` 的 preference score 明显低于 0.5，且 95% CI 上界只有 0.4251。因此，在当前 ESConv setting 下，always-on Strategy RAG 不是质量提升项，反而显著低于不使用 Strategy RAG。

## 4. 成本

| Action | mean input tokens | retrieval calls | strategy tokens | mean output tokens |
|---|---:|---:|---:|---:|
| `M0+R0` | 316.7 | 0.0 | 0.0 | 58.0 |
| `M0+RS` | 570.4 | 1.0 | 259.2 | 56.6 |

`M0+RS` 显著增加输入 token 和检索调用，但没有带来质量收益。

## 5. 对论文主张的含义

该结果支持以下主张：

> Strategy RAG 不能 always-on。即使在普通 ESC 单会话中，额外检索策略资源也可能增加成本并降低 blind pairwise response quality，因此需要选择性资源分配。

该结果不能单独证明：

- PM 能正确选择 RS；
- PM+guardrail 优于 strong rule；
- 长期记忆资源分配有效；
- ES-MemEval-style 记忆能力。

这些需要在 EvoEmo / longitudinal setting 中继续评估。

## 6. 下一步

推荐下一步在 EvoEmo 中评估：

1. PM；
2. PM+guardrail；
3. Strong Rule；
4. Best Fixed / Budget-Matched Fixed；
5. M0 baseline。

EvoEmo 才是长期记忆资源分配的主外部实验。

