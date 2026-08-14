# Paper 1 P2B 控制失败与标签来源改道

日期：2026-08-10  
状态：`P2B_CONTROL_MEASUREMENT_FAILED / PUBLIC CALLS=0 / PM NOT FIT`

## 已发生的事实

- 两位独立评审完成 48/48 个控制调用，全部首轮成功；物理尝试 48，失败 0，费用约 0.098877 美元。
- 24 个正式控制题覆盖 MP/MS/ME/RS 各 6 条。正式 132×2 公共盲评没有启动。
- 四个组件都没有通过预先冻结的逐轴准确率门，不能降低门槛、补题或把最终标签一致率代替逐轴门。
- 这不是 PM 学习失败：尚未创建公共训练标签，也没有拟合 PM。

## 根因

四个所谓“原子轴”在负例上并不独立：

1. `current_target_fit` 为否时，评审自然也会把 `component_minimum_possible_now` 判否；
2. 用户拒绝历史或建议时，评审会同时改变 target、minimum 与 boundary，而不只改变 boundary；
3. 候选内容已经出现在可见对话时，“资源没有新增信息”与“该事实仍能作为可靠前提改变回复”没有唯一答案；
4. 对 RS，问题已经明确或 validation 已做过时，target、increment 和 minimum 会一起塌缩；
5. 因此逐轴 gold 不是客观可复现事实。继续换 prompt、换 judge 或补控制题仍会重复过去的循环。

控制结果也支持这个诊断：Reviewer A 的 derived label 在四组件上都是 5/6 或 6/6，但逐轴只有 MP 15/24、MS 20/24、ME 16/24、RS 20/24；Reviewer B 的 derived label 是 4/6、4/6、5/6、4/6，逐轴为 19/24、15/24、17/24、18/24。问题集中在轴如何拆分，而不是所有案例都无法判断。

## 根本改法：公共作者标注作为训练 gold，LLM 不再造 gold

训练监督改为 `SOURCE_ANNOTATED_RESOURCE_SUITABILITY`：

- RS：ESConv 当前 seeker turn 后的首个真实 supporter strategy annotation 只作为监督标签；当前可见对话和 actual Rank-1 card 仍是唯一特征。Question 对应 AM01/AM02，Restatement 对应 AM04，Reflection/Affirmation 对应 AM05，Providing Suggestions 对应 AM10；无精确对应、普通卡与高风险冲突、以及实际 Rank-1 缺失均按冻结规则处理。
- MS：EvoEmo 当前 session 的 event `influenced_by` 递归祖先所指向的严格过去 source session 作为 evaluator-only 因果关联 gold。actual Rank-1 MS 若来自该祖先 session 才为正。
- ME：同一 event ancestry 规则，但还要求 actual Rank-1 是 typed action-result candidate；这保持为稀疏可失败 head。
- MP：只允许显式、可复算的 profile-field/current-event material relation；若该规则不能提供跨组双向支持，MP 固定 OFF，不用 LLM 猜。

这些字段只能在标签工厂读取，严禁进入 runtime、retriever、actual Rank-1、PM 特征、阈值或生成器。它们是标准监督学习里的 y，不是特征 x；因此不是数据泄漏。

现有公共数据的零 API 容量审计已经显示：

- RS exact strategy/closure-compatible：1,378 正 / 16,854 负，另有 117 个 structural absent；
- MS event-ancestry linked：832 正 / 3,610 负，17 个独立 connected groups 两类都有；
- ME event-ancestry linked：71 正 / 346 负，正类覆盖 10 groups、负类覆盖 15 groups。

这条路线直接解决“怎样知道调用对了”：调用对不是由模型主观想象，而是资源与公共作者给出的下一支持行为或纵向因果来源一致。随后端到端实验仍独立测：executor 是否真正用了资源、是否出现 material risk、回复质量是否非劣、成本是否下降。最早失败层继续分别归责给 source/retrieval/PM/projection/executor/measurement/system。

## 下一次只允许的一条链

1. 冻结上述 label factory 与 evaluator/runtime 物理隔离；
2. 零 API 物化 RS/MS/ME 标签并做 split/group、双向支持、shortcut 与 feature-only learnability 审计；
3. 只在 outer-train/development folds 做一次低容量 grouped OOF；
4. 若 RS 与至少一个 memory head 达到原有学习底线，再进入同栈 baseline 与端到端确认；
5. 若达不到，不再换 judge 或追加小包，而是据实终止该 head。

原 P2B 四轴结果保留为“构念分解不可可靠测量”的失败证据，不作为训练 gold，也不删除。
