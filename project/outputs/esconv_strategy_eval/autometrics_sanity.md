# ESConv Offline Autometrics Sanity Appendix

生成时间：2026-06-30T04:37:16.309980+00:00

这些指标只作为 appendix sanity check，不作为主实验结果。ESConv 主结论仍是 blind pairwise judge：always-on `M0+RS` 平均低于 `M0+R0` 且成本更高。

| Action | n | Len | Distinct-1 | Distinct-2 | BLEU-1 sanity | ROUGE-L sanity | Input tok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M0+R0 | 2275 | 48.6 | 0.034 | 0.243 | 0.103 | 0.103 | 316.7 |
| M0+RS | 2275 | 47.7 | 0.034 | 0.241 | 0.107 | 0.106 | 570.4 |

解释边界：BLEU/ROUGE 与人类支持质量不等价，且 ESConv gold response 不是唯一正确回复；这些数值只用于检查长度、多样性和表面重叠是否出现异常。
