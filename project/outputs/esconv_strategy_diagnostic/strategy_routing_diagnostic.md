# ESConv Strategy RAG 选择性路由诊断

本报告不调用 API，只分析已经完成的 `M0+RS` vs `M0+R0` pairwise judge 结果。

## 总体结论

- 样本数：2275 turns。
- RS wins / ties / R0 wins：696 / 457 / 1122。
- RS preference score：0.406。
- RS 平均额外输入 token：253.6。

这说明 always-on RS 在 ESConv 上不是好策略；但 RS 仍在一部分 turn 上胜出，所以更合理的问题是“何时开 RS”。

## Oracle 选择性上限

- Oracle selector vs always-R0 score：0.653。
- Oracle selector vs always-RS score：0.747。
- Oracle RS call rate：0.306。
- 相比 always-RS 可省 RS 调用：0.694。

Oracle 不是可部署策略，只用于证明选择性调用存在空间。

## RS 相对更有利的可见条件

- `03_long_21_plus_words`: n=560, score=0.473, RS wins/tie/R0 wins=204/122/234
- `advice_cue=yes`: n=96, score=0.469, RS wins/tie/R0 wins=31/28/37
- `04_late_turns_9_plus`: n=1628, score=0.434, RS wins/tie/R0 wins=553/308/767
- `03_mid_turns_5_8`: n=323, score=0.413, RS wins/tie/R0 wins=96/75/152
- `02_medium_9_20_words`: n=929, score=0.410, RS wins/tie/R0 wins=278/206/445
- `question_mark=no`: n=1986, score=0.410, RS wins/tie/R0 wins=614/400/972
- `distress_cue=no`: n=2061, score=0.408, RS wins/tie/R0 wins=639/405/1017
- `reflection_cue=no`: n=1830, score=0.407, RS wins/tie/R0 wins=565/358/907

## RS 相对更不利的可见条件

- `01_first_two_turns`: n=153, score=0.225, RS wins/tie/R0 wins=14/41/98
- `02_early_turns_3_4`: n=171, score=0.289, RS wins/tie/R0 wins=33/33/105
- `01_short_0_8_words`: n=786, score=0.354, RS wins/tie/R0 wins=214/129/443
- `question_mark=yes`: n=289, score=0.382, RS wins/tie/R0 wins=82/57/150
- `distress_cue=yes`: n=214, score=0.388, RS wins/tie/R0 wins=57/52/105
- `advice_cue=no`: n=2179, score=0.404, RS wins/tie/R0 wins=665/429/1085
- `reflection_cue=yes`: n=445, score=0.406, RS wins/tie/R0 wins=131/99/215
- `reflection_cue=no`: n=1830, score=0.407, RS wins/tie/R0 wins=565/358/907

## Gold Strategy 分组

- `Affirmation and Reassurance`: n=373, score=0.441, RS wins/tie/R0 wins=126/77/170
- `Information`: n=154, score=0.435, RS wins/tie/R0 wins=51/32/71
- `Providing Suggestions`: n=374, score=0.430, RS wins/tie/R0 wins=118/86/170
- `Others`: n=424, score=0.429, RS wins/tie/R0 wins=143/78/203
- `Restatement or Paraphrasing`: n=155, score=0.397, RS wins/tie/R0 wins=46/31/78
- `Self-disclosure`: n=217, score=0.371, RS wins/tie/R0 wins=60/41/116
- `Reflection of feelings`: n=161, score=0.360, RS wins/tie/R0 wins=45/26/90
- `Question`: n=417, score=0.360, RS wins/tie/R0 wins=107/86/224
