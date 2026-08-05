# MS 同栈资格赛——发现（单标注员，全部138状态已过标，仍未满足完整协议）

状态：**探索性、机器对比同栈可信，人工4类标签仍是单标注员单遍（全部138条，非仅50条子样本）**，
没有20%独立重叠评审和集中裁决，不满足Codex提出的正式资格赛完整协议。**2026-08-06更新：已从50
条扩展到全部138条**，见下方新增的"全部138状态"一节；结论方向与50条初步结果一致且更强（p值从
0.0019降到9.3e-5），但仍然只是单标注员单遍，没有第二标注者。**本文档取代
`PM_V1_5_V5_3_MS_RETRIEVAL_SCORING_DIAGNOSTIC_ZH.md`里对"生产环境=裸lexical"的旧表述**，那份
文档的其余内容（候选池因果边界核实方法、MP/ME发现）仍然有效，但baseline选择已被下面的结果修正。

复现：`scripts/v1_5/45_ms_qualifying_trial_same_stack_v1_5.py`，产出：
`outputs/pm_v1_5_v5_3_ms_qualifying_trial_v1/`（gitignore，未进git）。人工标签的sanitized副本
（不含私有内容，只有state_id/user_id/标签）已存进docs：50条子样本见
`PM_V1_5_V5_3_MS_QUALIFYING_TRIAL_MANUAL_LABELS_50_SAMPLE_20260806.jsonl`，全部138条见
`PM_V1_5_V5_3_MS_QUALIFYING_TRIAL_MANUAL_LABELS_FULL_138_20260806.jsonl`。

## 机器对比部分：同栈可信，硬约束已验证

用的是真实生产函数，不是简化版：
- 候选构造：`evoemo.build_evo_memory(user)`（不是自己拼summary字段）；
- 排序baseline：`v1_5_candidate_discovery.discover_final_typed_memory_candidates`（真实P2/runtime
  selector：内容词零匹配过滤→粗粒度content-match tier→typed tier→lexical仅tie-break），**不是
  裸`lexical_score`**；
- 因果边界：`session_index = len(dialog_history) + 1`，对138个状态**逐条**验证——生产代码自带
  `describe_memory_candidate`硬断言（选中当前/未来记忆会直接抛`ValueError`），**跑了138次，
  0次触发**。这不是"我事后检查没问题"，是生产代码自己的fail-closed guard被实际执行验证过。

138个状态里，生产selector和BGE-MS的Rank-1选择有114/138（82.6%）不一致。

## 人工判定部分：50条随机抽样，配对统计

标签体系：exact_fit / related_but_wrong_detail / unrelated / stale_conflicting（wrong_owner_entity
本次未出现——候选池按用户隔离，结构上不会跨用户）。

| | exact_fit | related_but_wrong_detail | unrelated/stale_conflicting |
|---|---:|---:|---:|
| 生产selector | 18%(9) | 42%(21) | **40%(20)** |
| BGE-MS | 32%(16) | 64%(32) | **4%(2)** |

配对胜负（排除7条平局，43条有效对比）：**BGE胜32、生产selector胜11**，双侧符号检验
**p≈0.0019**，统计显著。

## 跟Codex建议的门槛对照

- owner/time违规=0：**通过**（生产代码assertion验证，非人工检查）。
- 完全无关候选≤5%：BGE=4%，**通过**；生产selector=40%，远超此线（这本身也是一个新发现，见下）。
- exact-fit相对提升≥15个百分点：18%→32%，**+14个百分点，压线未达**（样本噪声下基本在边界上）。
- exact-fit绝对值≥70%：BGE=32%，**未通过**——这条不该被当真理，Codex自己也说不要用无依据的
  固定阈值，但如实报告：达不到这个数。

## 结论：不是"70%精确匹配"，是"大幅降低灾难性错误"

跟第一版（错误baseline）比较出来的画面不一样：这次真正的信号不在"exact fit提升多少"（只有14个
百分点、压线），而在**"完全文不对题"这个最坏情况的比例**——生产selector 40% vs BGE 4%，10倍差距，
配对检验显著。生产环境的粗粒度content-match虽然比裸lexical好，但依然会被"stress/anxious/work"这类
高频治疗话术词的零散重合骗过、导致选到完全不相关的旧记录；BGE在这个维度上改善明显。

## 仍然缺失、不能跳过的部分（50条子样本阶段）

1. **只有单标注员**，没有20%独立重叠、没有集中裁决——这是Codex协议里明确要求、我这次没有条件
   满足的部分。50条的信号方向和显著性值得投入正式资格赛，但不能替代它。
2. **只测了50/138**，不是全部裁定。
3. **exact-fit提升压线未过15个百分点**，如果正式资格赛用这条作为门槛，需要更大样本才能判断
   是真实效应还是噪声。

## 全部138状态（2026-08-06新增）

剩余88条按同一套4类标签体系（exact_fit / related_but_wrong_detail / unrelated / stale_conflicting
→ winner: bge/production/tie）由同一标注员单遍补标。**方法学口径差异**：50条子样本保留了
`production_label`/`bge_label`两侧独立4类标签；新补的88条**只记录了`winner`**（bge/production/
tie三选一），没有保留双侧4类细分标签——这是本次补标为节省时间做的简化，如实记录在
`PM_V1_5_V5_3_MS_QUALIFYING_TRIAL_MANUAL_LABELS_FULL_138_20260806.jsonl`的
`label_granularity`字段里（`full_4way_production_and_bge_labels` vs
`winner_only_no_per_side_4way_label`），不假装两者粒度相同。

全部138条胜负汇总：

| | bge胜 | production胜 | 平局 |
|---|---:|---:|---:|
| 50条子样本 | 32 | 11 | 7 |
| 新增88条 | 33 | 16 | 39 |
| **合计138条** | **65** | **27** | **46** |

排除46条平局，92条有效配对比较：**bge胜65 (70.7%)，production胜27 (29.3%)**。

- 双侧符号检验（对92条有效配对）：**p ≈ 9.3×10⁻⁵**（比50条子样本的p≈0.0019更显著，样本量增大后
  信号更稳）。
- 对bge胜率（65/92）做10000次自助法（bootstrap）重采样：**95% CI = [60.9%, 79.3%]**，区间整体
  远高于50%，不包含"无差异"。
- 对"bge=1分/平局=0.5分/production=0分"的整体得分（覆盖全部138条，不只是92条有效比较）也做了
  bootstrap：点估计0.638，95% CI = [0.572, 0.703]。

**新增88条比50条子样本"平局"多得多**（39/88=44.3% vs 7/50=14%）——这是补标时的真实观察，不是
数据错误：第二批88条里相当一部分state的生产selector和BGE-MS选中了同一条MS候选（`agree=True`时
自动记为平局，与50条子样本一致的判定规则），或者两边都是同等质量的"同域细节有误"，判定难分伯仲。
这提示"完全不搭边"这个最坏情况的10倍差距（生产40% vs BGE 4%，来自50条子样本，138条全量未重新
逐条统计四类细分标签)是本次结果里最站得住脚的部分，而不是"BGE整体压倒性更好"这个更强的说法——
138条里几乎1/3是平局，说明多数情况下两个打分函数选的候选质量相近，只有当生产selector的粗粒度
content-match被"stress/anxious/work"一类高频治疗话术词骗到完全无关候选时，BGE才显出明显优势。

## 建议

138条全量结果支持**认真考虑切换MS排序打分函数到BGE-M3**：合并样本下的胜负比（70.7% vs 29.3%）、
显著的符号检验（p≈9.3e-5）、以及不包含"无差异"的bootstrap CI，三者方向一致。但在正式冻结前，
仍然需要：(1) 第二个独立标注员至少覆盖20%重叠以估计标注者间一致性，因为138条仍是单人单遍；
(2) 决定是否要为新增88条补齐双侧4类细分标签，以便报告完整138条的"完全不搭边"比例而不仅是
50条子样本的比例；(3) 把这个改动放进真实Step2生成链路里做一次端到端可用性检查（见Step2
generator-compatibility gate文档），因为本资格赛只验证了排序/选中，没有验证换成BGE候选后
下游生成质量是否也变好。
