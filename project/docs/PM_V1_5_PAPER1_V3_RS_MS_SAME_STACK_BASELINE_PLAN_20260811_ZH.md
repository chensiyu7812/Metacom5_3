# Paper 1 V3 RS+MS 同栈 baseline 物化结果

日期：2026-08-11

## 结论

16 个冻结状态、每状态四个动作的 64 条已有回复已经全部复用并绑定到 baseline；本阶段没有重新生成、没有重新训练、没有改 MS 的 0.5 阈值。

当前最准确的实验名称是 **RS fixed ON + learned MS**，而不是“jointly learned RS+MS”。RS 的正式 grouped OOF 已通过，但对应方法没有为这 16 个 EvoEmo 状态保存同合同 full-fit checkpoint。因此本轮把 RS 固定为 ON，直接检验：已经有 RS 时，冻结的 MS selector 是否能增加有效纵向记忆贡献。

## 当前出现的信号

- MS selector 在 16 个状态中开 7、关 9。
- 这 16 个 qualification 状态来自模型训练过的开发池，不能把 7/8 suitable 命中、8/8 not-suitable 关闭写成 OOF 或外部性能；它只证明动作物化与 checkpoint 推理一致。
- `RS fixed ON + learned MS` 的 7 个 MS-ON 回复中，现有部分代理盲评覆盖 6 个，6/6 为 FUNCTIONAL。
- 同样开 7 次 MS、成本几乎完全相同的随机位置对照，覆盖的 6 个中仅 4 个 FUNCTIONAL，另有 1 个 NOT_USED_FINAL、1 个 BOUNDARY_FAILURE。
- fixed-high 在 16 个状态全部开 MS；已覆盖 11 个，其中 7 个 FUNCTIONAL、2 个 NOT_USED_FINAL、1 个 SURFACE_ECHO_ONLY、1 个 BOUNDARY_FAILURE。

这组结果只可解释为开发性方向信号：**选择哪 7 个状态，比单纯“开 7 次”更有希望。** Function 仍是 24/32 的单代理部分测量，不能替代论文终值。

## 成本

| 策略 | MS ON | RS ON | 平均估计输入 tokens |
|---|---:|---:|---:|
| always-off | 0 | 0 | 846.8 |
| RS-only | 0 | 16 | 983.6 |
| RS fixed ON + learned MS | 7 | 16 | 1113.5 |
| transparent rule | 9 | 16 | 1147.2 |
| fixed-high RS+MS | 16 | 16 | 1263.7 |
| cost/on-rate matched random | 7 | 16 | 1110.8 |

learned 策略相对 RS-only 多约 13.2% 估计输入成本，相对 fixed-high 少约 11.9%。cost/on-rate matched random 与 learned 的总成本仅差 0.247%，MS ON 次数同为 7，且 8/16 状态的开关位置不同，因此它是本轮最重要的“选择能力而非稀疏度”对照。

单一固定动作中最接近的是 `MS+R0`，但成本差 5.40%，超过冻结的 5% 门，只能叫 `closest-cost fixed`，不能冒充 cost-matched fixed。

## 已冻结的策略

1. always-off：`M0+R0`。
2. RS-only：`M0+RS`。
3. fixed-high RS+MS：`MS+RS`。
4. transparent RS+MS：actual Rank-1 不是 low-information、也不是 current echo 才开 MS。
5. RS fixed ON + learned MS：冻结 checkpoint、阈值 0.5。
6. learned MS 的 R0 切片：用于检查 MS 与 RS 的交互，不作为主策略。
7. closest-cost fixed：`MS+R0`，匹配不合格，只作描述。
8. cost/on-rate matched random：RS 全开、MS 仍开 7 次，冻结哈希置换。

## 下一道唯一门

所有主比较可压缩为同一个 RS 切片的 16 对 `M0+RS` / `MS+RS` 回复。已经物化：

- 16 个盲 Quality pair；
- 32 个两臂绝对 Risk item；
- 16 个 source-aware MS Function item。

不需要新生成，也不需要补训。只有这 16 对完成冻结盲评后，才能判断 learned MS 相对 RS-only、fixed-high、transparent rule 和 matched random 的 Quality / Risk / Function / Cost。现阶段不能宣布 baseline 胜负。

## 机器权威与数据边界

- 四动作仍是完整 16-action 系统中 `MP=0, ME=0` 的二维切片，不改变全局 16 动作设计。
- teacher class、negative stratum 和 checkpoint 训练池命中只保留在私有开发审计中。
- Function 代理标签只作开发诊断；论文终值必须对 learned 实际选中的回复执行 source-aware 人工裁决。
- MP、ME 在本阶段保持关闭，不因本轮结果更改状态。

