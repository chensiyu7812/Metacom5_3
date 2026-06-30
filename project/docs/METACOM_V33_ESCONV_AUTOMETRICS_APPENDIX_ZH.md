# MetaCom V3.3 ESConv Offline Autometrics Appendix

更新时间：2026-06-30

## 1. 目的

ESConv 主实验已经完成：

- comparison: `M0+RS` vs `M0+R0`
- n: 2275 turns
- dialogue clusters: 169
- final judge: GPT-4o
- RS wins / ties / R0 wins: 696 / 457 / 1122
- RS preference score: 0.406
- 95% dialogue-cluster bootstrap CI: [0.386, 0.425]
- mean input tokens: `M0+R0` 316.7 vs `M0+RS` 570.4

主结论仍然是：

> Always-on Strategy RAG hurts average ESConv response quality and increases cost; Strategy RAG has conditional value, so selective routing is needed.

本 appendix 只做传统 automatic metrics sanity check，避免和 ESConv 类先行研究完全脱节。

## 2. Offline Metrics

脚本：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/14c_esconv_autometrics_sanity.py
```

输出：

- `outputs/esconv_strategy_eval/autometrics_sanity.json`
- `outputs/esconv_strategy_eval/autometrics_sanity.md`

结果：

| Action | n | Len | Distinct-1 | Distinct-2 | BLEU-1 sanity | ROUGE-L sanity | Input tok |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0+R0 | 2275 | 48.6 | 0.034 | 0.243 | 0.103 | 0.103 | 316.7 |
| M0+RS | 2275 | 47.7 | 0.034 | 0.241 | 0.107 | 0.106 | 570.4 |

## 3. Interpretation

这些自动指标没有显示 `M0+RS` 和 `M0+R0` 在长度、多样性、BLEU-1/ROUGE-L 表面重叠上有巨大异常差异。`M0+RS` 的 BLEU-1/ROUGE-L 略高，但主 judge preference 仍显著偏向 `M0+R0`。

这正说明传统 overlap metrics 不足以判断情感支持质量：

- ESConv gold response 不是唯一正确回复；
- BLEU/ROUGE 主要测表面重叠，不测共情、时机、过度建议、语境适配；
- Distinct-1/2 只能做多样性 sanity，不等价于帮助质量；
- 本研究的主指标仍应是 blind pairwise preference / fixed-input scoring、memory misuse / omission / exposure risk、resource cost。

## 4. 与先行 ESConv 指标的关系

先行研究常见指标：

- `ACC↑`
- `PPL↓`
- `B-1↑`, `B-2↑`, `B-3↑`, `B-4↑`
- `D-1↑`, `D-2↑`
- `R-L↑`
- `s_norm↑`

本研究不训练新 ESC generator，因此不适合把这些指标作为主结果：

| Metric | 是否需要作为主指标 | 原因 |
|---|---|---|
| ACC | no | 本研究不是 strategy classifier；可用 strategy recall diagnostic 替代。 |
| PPL | no | 固定 API / generator 设定下不可自然比较。 |
| BLEU / ROUGE-L | appendix only | 表面重叠 sanity，不代表支持质量。 |
| Distinct-1/2 | appendix only | 多样性 sanity，不代表安全或情感支持质量。 |
| s_norm | no | 依赖上述自动指标组合，不适合作为核心 claim。 |

## 5. Paper Wording

可以写：

> We report BLEU-1, ROUGE-L and Distinct-1/2 only as appendix sanity checks for ESConv-style comparability. These overlap/diversity metrics did not explain the judge preference gap, reinforcing the need for response-quality and risk-oriented evaluation.

不应写：

> Our simple Strategy RAG beats ESConv state-of-the-art generation systems.

原因是：

- 我们比较的是同一固定 generator 下的 resource condition；
- ESConv 类先行研究通常比较训练模型 / 策略生成模型；
- 指标和实验对象不是同一个问题。
