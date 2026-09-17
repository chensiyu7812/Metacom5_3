# Paper-1 ESC Evaluator 双真人参考审计（2026-08-23）

状态：`FROZEN / TWO INDEPENDENT RATINGS COMPLETE / TARGETED OVERALL ADJUDICATION COMPLETE / ZERO OUTCOME`

机器结果：`project/data/paper1_authority/paper1_esc_evaluator_dual_human_reference_20260823_v1.json`

## 1. 结论

两名 reviewer 均完成冻结的 24-item blind package，评分可用于 evaluator qualification。分歧不构成无效数据：Overall 的 quadratic weighted kappa 为 `0.7571`、Spearman 为 `0.8007`、MAD 为 `0.625`，只有 `1/24` 项的 Overall 绝对分差达到 2 分。

不要求重评 24 项。两份原始提交按字节保存；后续必须等权报告 candidate evaluator 对 RATER_A、RATER_B 的 agreement，并将 reviewer disagreement 作为 sensitivity，不得静默选择其中一人为 primary。

## 2. v1 instrument 标签修复

历史 v1 instrument 把官方 scorer 中先出现的 `Humanoid` rubric 按位置配给了本地 `Skillful`，又把官方 `Skillful` rubric 配给本地 `Humanoid`。该错误只影响列名解释，不删除或改写任何人类判断。

机械 normalization 固定为：

- v1 `Skillful` score → official `Humanoid`；
- v1 `Humanoid` score → official `Skillful`；
- 其余五维原样保留。

旧 v1 instrument 和两份原始提交保持不可变；v2 instrument、两份 normalized JSONL 与 source/stored SHA-256 另行保存。此修复不需要真人重评。

## 3. 可用边界

这 24 项用于资格审查 candidate evaluator 是否接近两名真人，不是 PM/Top-k outcome，也不证明真实临床焦虑得到缓解。

controlled verbosity variants 除长度外还增加情绪确认、自主性支持和缓和表达，因此只能说明 reviewer 对“扩展后的支持性表达”的反应，不能识别纯 verbosity bias。redundant-suggestion 与 list-format 结果同样只作 sensitivity，不据此选择让 Ours 得分更高的 judge。

质量 reviewer 不需要知道 Generator 是否收到外部资源；资源是否被执行由独立 uptake review 判断。正式 ON/OFF 中不可感知的改善、non-use、misuse 或 harm 都是有效 end-to-end effect，这使 RS 与 memory heads 能学习 R0/M0，而不是只学习打开资源。

## 4. Targeted adjudication 与当前停止点

唯一 major-Overall disagreement `escq_0e49439a9e28fb56` 已在 identity blind、未显示两名原始分数的条件下裁决为 `Overall=4`。该裁决只解决这一格，不冒充完整 `24×7` 单一 gold。candidate evaluator 必须分别对 RATER_A、RATER_B 报告 agreement，并报告该 targeted Overall 格的 absolute error；其余分歧保留为 sensitivity。当前 24-item reference 不再需要额外人评。

ESC-RANK ≥24 GiB runtime、三种 proxy judge exact identities、judge scores 与 evaluator winner 仍未完成。四把 outcome lock 全部 `CLOSED`；本轮 paid API、formal outcome 与 PM training 均为 0。
