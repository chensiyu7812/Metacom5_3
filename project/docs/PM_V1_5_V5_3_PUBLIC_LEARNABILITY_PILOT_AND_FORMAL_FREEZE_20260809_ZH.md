# PM V1.5 V5.3 公共数据可学习性 Pilot 与正式冻结

日期：2026-08-09  
状态：`PASS_FORMAL_EXPANSION_AUTHORIZED`  
机器冻结：`data/pm_v1_5_contracts/v5_3_public_formal_effect_freeze_v1.json`

## 结论

现在可以进入正式 effect 扩量，但不能写成“已经数学保证正式 PM 必然及格”。本轮已经完成比
结构验收更关键的一步：用真实 endpoint 生成 96 个预先冻结的 paired-effect groups，并证明四个
低容量 head 在按用户/对话分组的 OOF 预测中，都能从输入特征预测未见组上的连续 quality uplift，
且均超过 fold-training-mean 常数基线。

这说明当前数据至少已经具备四项必要条件：ON/OFF 确实产生可测边际效应；效应不只是随机正负；
冻结特征中有可运输的条件信号；四个组件不需要依靠 cost 或风险标签才能学。此前最危险的情况——
“生成很多数据，但 label 与 state/candidate 无关，所以模型永远只能学常数”——已被 development
pilot 实际排除。

## 96 组真实 Pilot 结果

每个 head 24 组，每组使用 3 个预冻结 generator seeds；总计 576 个 ON/OFF generator arms。
其中 561 个直接 clean，15 个按冻结规则 deterministic fallback。Quality 和 function 最终均为
96/96 完整；历史上 4 次 structured-output failure 被保留记录，没有静默删除样本或重选 state。

| Head | 正/负/零效应组 | OOF MSE / 常数基线 MSE | MSE 降幅 | OOF Spearman | 扩量门 |
|---|---:|---:|---:|---:|---:|
| MP | 22 / 1 / 1 | 0.793 | 20.7% | 0.378 | PASS |
| MS | 16 / 4 / 4 | 0.830 | 17.0% | 0.152 | PASS |
| ME | 16 / 6 / 2 | 0.573 | 42.7% | 0.528 | PASS |
| RS | 18 / 6 / 0 | 0.846 | 15.4% | 0.270 | PASS |

门槛在正式扩量前固定为：每个 head 的 grouped OOF MSE 至少比 fold-training-mean predictor
低 5%，且 OOF Spearman 至少 0.15。这里的 binary balanced accuracy 只作诊断；MP 的真实 uplift
绝大多数为正，硬切正负会把一个可学习的幅度问题错误变成类别平衡问题。

本轮 Q/F judge（含一次只修缺失 F 的定向重试）共用 301,686 input tokens、217,963 output
tokens，按冻结的 Gemini 2.5 Flash-Lite 标准付费率估算为 0.117354 美元。Generator 使用已冻结的
NVIDIA hosted endpoint；成本计算不进入任何 head 标签。

## 为什么这更接近“保证 PM 学会”

没有合同能保证未知正式数据必然及格，但以下机制把可控的失败源逐项消掉：

1. **先证实效应存在，再扩量。** 不是先生成 80 个用户再祈祷；96 组真实结果已经证明四个组件均有
   非常数、可预测的连续边际效应。
2. **同 state、同 seed、只切一个组件。** 每个 group 的 ON/OFF 共享 current state 和 generator seed，
   label 是组件的 paired uplift，不再混入 state-action 差异。
3. **三个 seeds 聚合。** 单次 generator 运气不会直接成为标签；tie 保持 zero，negative 保持 negative。
4. **低容量且组件专用。** 冻结模型只有 5–6 维、Ridge alpha=10；MP/MS/ME/RS 使用不同但已冻结的
   语义表示，避免用同一组粗糙 scalar features 强迫四种机制共享错误归纳偏置。
5. **按独立 cluster 做 OOF。** memory head 按用户隔离，RS 按 ESConv dialogue 隔离；PCA、scaler 和
   calibration 只在 outer-training groups 内拟合。这个约束不是为了形式公平，而是防止得到一个
   训练集高分、换用户立即失效的假及格。
6. **正式阶段禁止继续调题。** 如果某个 formal head 失败，不得看 outcome 后补 state、换 encoder、
   改维数或改门槛；该组件 fail closed 到 OFF/transparent rule。这样 development PASS 才有含义。

初始的 6 个手工 scalar features 实际没有通过 OOF 门。随后只在 development pilot 内完成一次表示
选择，并冻结为：MP=current-state BGE→outer-train PCA3 加 3 个结构特征；MS=candidate BGE→
outer-train PCA5；ME=candidate BGE→固定随机投影 3 维加 3 个结构特征；RS=state×candidate BGE→
outer-train PCA5。正式阶段不得再改。

## 正式 effect 数量已经冻结

正式第一版不是 1,095 个用户，也不再生成 80 个长期用户：

- MP：18 个 EvoEmo 用户 × 每人 8 个 outcome-blind、factor-balanced actual Rank-1 states = 144 组；
- MS：同样 18 × 8 = 144 组；
- ME：同样 18 × 8 = 144 组；
- RS：144 个互不重复且排除 84 个 EvoEmo seed 的 ESConv train dialogues；
- 合计 576 groups，每组 3 个 paired generator seeds；96 个 development states/dialogues 全部排除。

memory 的统计独立 cluster 仍然只有 18 个用户，因此论文中的 CI/bootstrap 必须按用户聚类；144 个
state 不能冒充 144 个用户。多 state 的作用是让 head 学到同一用户内部“什么时候该开”的条件边界，
不是凭空把样本量伪装成更多人。

正式门通过后，另冻结 32–48 个 common states，每个 state 跑完整 16 动作，用于检验四个独立 head
组合后是否存在 interaction；cost 只在这一步参与联合投影。

## Risk 的决定

自动 risk judge 没有资格进入标签。第二版 canary 在仅 8 组中仍报出 20 个 R2 和 13 个 R3，人工
定向检查发现它会把当前可见对话的正常复述、无害问题以及 fallback 共情句误报为风险。因此它被
整体淘汰，不参与 head target、正式扩量授权或 PM 是否及格的判定。

正式风险评估改为两层：可机器确定的 owner/time/version、边界、scaffold exposure 等事件全量检查；
其余 R2/R3 做预冻结分层抽样和盲人工复核。这个决定不会削弱 PM 的 quality 学习，因为 quality target
从一开始就是 `positive_support_contribution`，不是 `quality AND no-risk AND function-used` 的稀疏交集。

## 正式 manifest 已完成

上述第 1 步已经执行完毕且零 API 审计 PASS：576/576 groups、每 head 144、三个 memory
head 均为 18 用户×8、RS 为 144 个 distinct dialogues 且每个外折 24 个。全部 candidate 通过
typed executable 校验，96 个 development source states/24 个 RS dialogues 在选择前排除。

RS 首次机械抽样虽结构 PASS，但 144 组中有 127 组集中于两个 move，不利于学习。由于这在任何
正式 outcome 产生之前发现，已按候选池真实支持范围冻结六个 move 配额为
`27/12/27/27/27/24`；每条仍是 production retrieval 的 actual Rank-1，没有晋升 Rank-2 或改题。

正式调用预算为 3,456 generator calls、1,152 quality judge calls 和 576 function calls，共 5,184
base calls；automatic risk judge 为 0。按 development 实耗外推 Q/F judge 约 0.704 美元，20%
headroom 后硬上限 0.84 美元。当前 `live_execution_allowed=false`，需先独立复核 manifest hash、
配额和预算。

## 后续执行顺序

1. 独立复核 manifest hash、预计费用、RS move 配额和调用顺序，审核通过后才启动 paid generation。
2. 按冻结 runner 一次完成所有组；失败只能走已声明 retry/fallback，禁止换 state。
3. 产生一次 OOF prediction，逐 head 应用正式门；失败组件回退，成功组件才进入 16-action interaction。
4. 最后比较 learned PM、always-off、fixed-high、transparent rule、旧 V1.0 和 cost-matched fixed。

机器证据：

- `outputs/pm_v1_5_v5_3_public_qf_development_pilot_20260809/completion_assessment.json`
- `outputs/pm_v1_5_v5_3_public_formal_effect_freeze_20260809/learnability_report.json`
- `outputs/pm_v1_5_v5_3_public_formal_effect_freeze_20260809/formal_effect_freeze.json`
- `outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/audit.json`
- `outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/contract.json`
- `outputs/pm_v1_5_v5_3_public_learnability_canary_20260809/risk_v2/report.json`
