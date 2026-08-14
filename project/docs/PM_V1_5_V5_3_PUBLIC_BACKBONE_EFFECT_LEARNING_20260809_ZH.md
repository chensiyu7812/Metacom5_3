# PM V1.5 V5.3 公共数据主干与 paired-effect 学习方案

> 2026-08-09 补充：指标、正确调用 oracle、逐阶段责任归因和 ESConv/EvoEmo/ES-MemEval 三外部实验的
> 统一权威版本见 `PM_V1_5_V5_3_METRIC_ORACLE_RESPONSIBILITY_AND_EXTERNAL_FREEZE_20260809_ZH.md`，
> 机器合同见 `v5_3_metric_responsibility_and_oracle_v1.json` 与
> `v5_3_external_complementary_evidence_v1.json`。旧 binary Brier registry 不再控制 V5.3 component learnability。

日期：2026-08-09  
状态：`96-GROUP DEVELOPMENT PASS / FORMAL 576-GROUP DESIGN FROZEN`  
机器权威合同：`data/pm_v1_5_contracts/v5_3_public_backbone_effect_learning_v1.json`

> 2026-08-09 更新：96 组真实 paired-effect development pilot 已完成，四个低容量 head
> 均通过预冻结的分组 OOF 扩量门。正式阶段冻结为每个 head 144 组、合计 576 组；不再允许
> 根据正式 outcome 改表示或补挑 state。完整结果与下一步见
> `docs/PM_V1_5_V5_3_PUBLIC_LEARNABILITY_PILOT_AND_FORMAL_FREEZE_20260809_ZH.md`。

## 结论

采用“ESConv + EvoEmo/ES-MemEval 公共数据为主干，只新生成 paired responses/effects”的方向，
停止为第一篇论文继续扩写 80 个长期合成用户。这个方向比继续 prompt 生成用户更自然、更省人力，
也更容易向同行解释数据来源和复现流程。

本次核查以“先让四个 head 有真实、可辨识的条件信号”为优先级，修正五个关键问题：

1. EvoEmo 论文明确说明每个 session 生成后补充 summary 和 turn-level observation；release 中
   observation 还有 `utt_id`。因此它们应在 source session 结束后进入 MS，而不是为了保守全部丢弃。
   Event 也全部带 `conv_id`，可在对应 session 结束后作为 ME_CONTEXT 开放；QA answer/evidence、跨
   session thematic grouping、未来或尚未结束 session 的注释仍不得进入 runtime。
2. `basic_info` 被明确当作会话开始前已授权的 onboarding profile，而不是声称它由历史对话在线
   推断出来。这个实验假设必须在论文中说明。
3. Quality/Risk/Cost 的测量应非冗余，但不能强行声称统计独立。Quality 改名为
   `positive_support_contribution`；overall acceptability、风险、功能和成本分别记录。Cost 只用于
   16 动作联合投影，不进入四个组件 head 的正负标签。
4. 用户互斥仍不足以防泄漏。EvoEmo 的 `esc1198` 同时出现在 p13 和 p18；两人必须绑定同一外折，
   session 主键必须是 `(user_id, session_id)`。
5. 单次随机 ON/OFF winner + 把 tie 塞进负类会制造高噪声、低正例标签。正式质量 target 改为三个
   预冻结 paired seeds 聚合后的连续/ordinal uplift；tie 表示 zero uplift/soft 0.5，risk 和 function
   分别学习/报告，不再与 quality 取稀疏交集。

因此，当前方案是“经过修正后可以启动下一门”，不是“已经保证 PM 会学会”。

## 数据身份与可观测边界

| 资源 | 正式来源 | runtime 可见 | 明确禁止 |
|---|---|---|---|
| MP | `basic_info` + `social_relationship` | basic 除 name 在 onboarding 开放；relationship 在其 `conv_id` 结束后开放 | name 注入、未来关系、偏好/profile 混合 |
| MS | 完成的严格过去 session | session summary + 带有效 seeker `utt_id` 的 observation | 当前未结束/未来 session 注释、跨 session gold |
| ME | `event_experience` + raw seeker turn | `conv_id` 结束后的 context event；strict exact action-result 为 reusable tier | 未来 event、QA gold、Rank-2 追题 |
| RS | ESConv + 六卡 definition bank | 当前对话前缀与冻结 actual Rank-1 card descriptor | 84 个 EvoEmo seed 对话、测试对话建库、outcome rerank |

当前 state 粒度为每个 seeker turn；recent dialogue 只到该 turn 为止。MP 是预先授权 profile，
MS/ME 只能来自已经结束的更早 session，不能从当前 session 的未来 turn 或未来 session 取证。
候选层只执行机器可证的 eligibility、owner/time/version、exact extraction 和 frozen ranking；它不得用
“看起来会有帮助”筛候选，也不得把 candidate present 当作 should-open gold。

## 零 API 全量资格审计结果

审计读取的是当前仓库固定文件，未调用 generator 或 judge：

| 项目 | 结果 | 正确解释 |
|---|---:|---|
| EvoEmo 用户 | 18 | 推断 cluster 是 user，不是 state |
| sessions | 401 | 全局 session ID 仅 400 个；`esc1198` 被两个用户共享 |
| seeker turns | 4,689 | 可构造 state 的原始 turn 数，不是 4,689 个独立用户 |
| ESConv dialogues | 1,300 | 其中 84 个是 EvoEmo seed，全部隔离 |
| ESConv seed 隔离后 | 1,216 | train/validation/test 分别 875/172/169 |
| MP profile items / Rank-1 | 258 / 842 states，18/18 用户 | 105 次 onboarding、737 次 relationship Rank-1 |
| MS summary+observation items | 2,691 | source session 结束后开放；observation 需要 seeker `utt_id` |
| MS preliminary actual Rank-1 | 3,270 states，18/18 用户 | 666 summary、2,604 observation Rank-1 |
| ME strict exact action-result | 24 items，15/18 用户 | p15/p16/p18 没有 strict item |
| ME event+reusable items / Rank-1 | 470 / 2,000 states，18/18 用户 | 1,652 context-event、348 reusable Rank-1 |
| MP/MS/ME 同时有 Rank-1 | 770 states | 可构造同状态完整 16 动作 interaction 面板 |

数据 hash、84-seed quarantine、用户折、共享源会话绑定和 forbidden-field 门均通过。paired-effect
label 尚不存在，因而 `pm_learnability_established=false` 是正确结果，不是审计失败。

## 训练、交叉拟合与不作弊规则

正式效果数据必须在一次性冻结后产生。六个 outer folds 每折 3 个 held-out 用户、15 个训练用户；
p13 与 p18 因共享 `esc1198` 永远同折。inner validation 只能在对应的 15 个 outer-training 用户内
选择正则、阈值和 calibration。任何会从数据学习的词表、表示、标准化器或校准器也必须在 outer
training 内拟合；如果使用全局第三方 encoder，它必须在看 paired outcome 前固定且不再微调。

所有 fold 必须由同一个冻结程序连续运行，不允许看完 fold 1 后改 prompt/feature/threshold 再跑
fold 2。每个 held-out 用户只产生一次 OOF prediction。EvoEmo 的报告只能称 cross-fitted
development-benchmark result。若未来要写 independent confirmation，必须另找未触碰的新用户或新数据。

RS 另在 ESConv 上按 dialogue group 切分；84 个 seed 永久隔离。此前 `696/457/1122` 是 2,275
个 turn 的 RS胜/平/败，真正 cluster 只有 169 个 dialogue。`696/2275=30.6%` 不是 30.6% 独立用户，
也不是已证明可学习的正类率。

## Quality、Risk、Function、Cost 的正式关系

`positive_support_contribution` 只回答 ON 相对 OFF 是否增加了正向支持价值，分四项：goal advance、
emotional support、specific useful contribution、clarity/naturalness。它不再冒充完整 overall quality。
overall acceptability 另报；显式边界本来就是用户目标的一部分，所以不能要求质量 judge 假装边界违规
对帮助性毫无影响，但同一个风险事件不能再被复制成另一条隐含风险标签。

风险单独记录两个 arm 的绝对事件和资源可归因的增量方向：

- R1：explicit boundary violation；
- R2：unsupported/wrong-owner/stale personal grounding；
- R3：excessive directiveness or burden；
- scaffold/resource exposure：独立 system-integrity 事件，不与 R1–R3 混成一个分数。

四个主 head 学的是三个 paired seeds 聚合后的条件性 quality uplift。Risk 是独立 auxiliary；功能使用
是 post-treatment mechanism diagnostic，不是 quality 正标签的必要交集，也不是 runtime feature。
成本记录 incremental tokens、latency、fallback/recovery 和金额，只在四 head 输出后参与 16-action
projection。这样不会因 `quality gain AND no risk AND function=yes` 的多重交集把正例压得过稀。

Primary judge 必须与 generator 属于不同模型家族，prompt、模型版本、双顺序配对和阈值在 effect
产生前冻结。另对预声明的分层盲样本做两位独立人类 reviewer 复核，报告一致性和仲裁结果；这批
人评只验证测量可信度，不能拿来回改 judge prompt 或重新挑 state。

## 怎样最大限度保证“能学”，又不作弊

不存在能在看 outcome 前保证模型及格的数据合同。能保证的是：若真实世界里存在可识别的条件效应，
管线不会因为泄漏、错误标签、候选混杂或 fold 调参把它伪造或毁掉；若效应不存在，系统会 fail closed，
论文如实报告哪个 head 不可学习。

按以下顺序执行：

1. **结构门（已通过）**：来源 hash、严格过去、exact spans、84-seed quarantine、共享源绑定、候选覆盖。
2. **测量门（下一步）**：在与正式 effect state 不重合的资格题上冻结 generator/typed executor、Q/R/F
   judges、双顺序 pairwise、风险证据定位和 deterministic fallback。不能用 cost 改 head 标签。
3. **状态冻结门**：从当前 outcome-blind 候选池冻结 exact state IDs、actual Rank-1、组件、fold、arm seed
   和费用上限；任何 outcome 产生后禁止补题、换 Rank-1 或调正负配额。
4. **可学习性分层**：只按 outcome-blind 条件平衡抽样，不平衡结果标签。MP 分 profile/relationship，
   MS 分 summary/observation，ME 分 context/reusable 与三态 action readiness，RS 分 move、对话阶段、
   candidate-state semantic fit、advice/readiness 和 burden。每 head 只保留 4–7 个非恒定可部署特征。
5. **一次性 paired effects**：同 state、同 candidate、同 generator 只切一个组件 ON/OFF；每组使用三个
   预冻结 paired seeds，先保存两侧原始 output，再跑 blind judges并聚合。失败和 fallback 按预先规则
   保留，不能只删难例。
6. **OOF 学习门**：四个低容量 head 分开训练连续/ordinal uplift，再做预声明阈值诊断。BA≥0.65、
   recall/specificity≥0.60、Brier
   优于 prevalence constant 和 transparent rule、OOF 同时产生 ON/OFF，只是工程采用门，不是统计证明。
   必须同时报告每类来自多少不同用户和 cluster CI。失败 head 在对应 fold 回退为 OFF/透明规则。
7. **系统比较**：先固定一个 primary comparator，再比较 always-off、fixed-high、transparent rule、旧 V1.0
   和 cost-matched fixed。质量、风险、成本分别报告；用户级 bootstrap/permutation，不能把 state 当 n。

这种设计让“及格”来自未参与该 fold 拟合的真实用户效果，而不是人工 construction condition、未来 QA、
候选是否存在、cost 或看完结果后的补题。它不能制造不存在的信号，但能最大限度降低再次因训练数据
定义错误而学不会的风险。

## 当前 Go / No-Go

- **Go**：停止新增 80 个主样本用户；保留现有 11 人做工程压力测试；采用公共主干；继续完成
  revised Q/R/F judge 资格和 outcome-blind exact state manifest。
- **No-Go**：现在直接付费跑全量 effects、直接训练、把 summary/observation 在 source session 完成前
  暴露、把 single stochastic winner 当稳定标签、把 tie 强迫为负类、仅靠低召回 regex 训练 RS、把
  30.6% turn wins 当用户正例率、把 cost 写进 head label。

当前准确状态是：扩大后的公共目录让 MP/MS/ME 全部覆盖 18 用户，候选稀疏不再是首要问题。首要
问题变成 effect label 的稳定性和 candidate-state 条件特征是否能解释 uplift；这两项由三 seed 聚合、
outcome-blind factor strata 和 4–7 维低容量 head 解决。真实 uplift 是否足以过门仍需 paired outcomes。
