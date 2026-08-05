# MS 同栈资格赛——初步发现（单标注员，未满足完整协议）

状态：**探索性、机器对比同栈可信，人工5类标签目前仍是单标注员单遍**，没有20%独立重叠评审和
集中裁决，不满足Codex提出的正式资格赛完整协议。这是决定"值不值得投入完整资格赛"的初步证据，
不是最终结论。**本文档取代`PM_V1_5_V5_3_MS_RETRIEVAL_SCORING_DIAGNOSTIC_ZH.md`里对"生产环境=裸
lexical"的旧表述**，那份文档的其余内容（候选池因果边界核实方法、MP/ME发现）仍然有效，但baseline
选择已被下面的结果修正。

复现：`scripts/v1_5/45_ms_qualifying_trial_same_stack_v1_5.py`，产出：
`outputs/pm_v1_5_v5_3_ms_qualifying_trial_v1/`（gitignore，未进git，见同目录`manual_labels_50_sample.jsonl`
的sanitized副本已存进docs）。

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

## 仍然缺失、不能跳过的部分

1. **只有单标注员**，没有20%独立重叠、没有集中裁决——这是Codex协议里明确要求、我这次没有条件
   满足的部分。50条的信号方向和显著性值得投入正式资格赛，但不能替代它。
2. **只测了50/138**，不是全部裁定。
3. **exact-fit提升压线未过15个百分点**，如果正式资格赛用这条作为门槛，需要更大样本才能判断
   是真实效应还是噪声。

## 建议

这个初步结果支持"值得投入一次正式同栈资格赛"，但还不能直接冻结BGE-MS。下一步如果继续，应该是：
扩大到全部138个状态、找第二个独立标注员做20%重叠、正式跑bootstrap CI而不是单次符号检验。这些超出
了这次单人单遍的产出范围，如实标注为未完成。
