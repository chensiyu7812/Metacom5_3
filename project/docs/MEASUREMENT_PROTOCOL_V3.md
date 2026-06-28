# Measurement Protocol V3: Stratified Controls and Effective Response Signal

版本：2026-06-23  
状态：development measurement protocol；用于 full judging 前的 judge pilot gate。

## 1. 为什么从 V2 更新到 V3

V2 将所有 held-out controls 混成一个 accuracy，并将 dual-order raw agreement rate 作为硬门槛。后续多个 judge pilot 显示两个问题：

- 11 个 controls 太少，一个边界样本会造成 9.1 个百分点波动；
- 部分 controls 同时测量多个主观维度，不适合作为一票否决的 hard gate；
- training-eligible response pairs 已经采用 dual-order debiasing，不一致的 A/B verdict 会解析为 `tie`，因此 raw agreement 低会降低可用 response signal，但不一定污染训练标签。

V3 的目标不是让某个模型“过关”，而是让 pilot gate 对齐实际训练标签的可靠性：

1. 明确区分 hard calibration controls 和 boundary diagnostics；
2. 保留 dual-order debiasing；
3. 用 debias 后的 effective non-tie rate 判断 response preference 是否仍有训练信号；
4. 将 raw dual-order agreement、raw reversal 和 position bias 作为 diagnostics 报告。

该协议必须在 full judging、PM training、validation selection 和 external evaluation 前冻结，不能根据后续结果再修改。

## 2. Control 分层

### Hard Controls

Hard controls 只包含预期判断足够清楚、失败会说明 judge 没有掌握基本任务的样本，包括：

- clear response preference / exact tie；
- intrusive unsupported personal reference；
- grounded memory use；
- overgeneralized unsupported memory claim；
- clearly missed critical memory preference；
- good strategy use；
- premature strategy misuse。

V3 默认要求 hard control accuracy `>= 1.0`。换句话说，当前 small pilot 中所有 hard controls 必须通过。

### Boundary Diagnostics

Boundary diagnostics 必须报告，但不作为一票否决：

- `resp_authorized_unseen_neutral`：它要求 blind response judge 不因看不到 evidence 而惩罚“授权但不可见”的记忆事实；但它同时混入了 naturalness / non-intrusiveness 偏好，因此不是干净的 hard control。
- `m0_correct_optional`：它测试“记忆可用但可不提”的可选 omission；这类场景本身允许合理 judge 分歧。

Boundary diagnostics 的失败不能直接证明 judge 不可用，但必须在论文或 run report 中透明报告。

## 3. Response Pair Reliability

Training-eligible response pairs 使用 dual-order debiasing：

1. forward: A=`action_a`, B=`action_b`；
2. reverse: A=`action_b`, B=`action_a`；
3. 若两个顺序选择同一 underlying response，保留该偏好；
4. 若两个顺序不一致，最终 label 设为 `tie`。

因此，raw dual-order agreement 是重要诊断，但不是唯一硬门。V3 使用：

```text
effective_non_tie_rate =
  count(final debiased preference != tie) / count(training-eligible pairs)
```

默认 hard gate：

```text
effective_non_tie_rate >= 0.25
```

理由：若 debias 后几乎全是 tie，response ranker 无法学到可用的 response-quality signal；若仍保留足够非 tie pair，response head 可用于非劣约束和排序诊断。低 raw agreement 会自然转化为更多 tie，不会作为偏好噪声直接进入训练。

## 4. Pilot Gate V3

### Hard Gates

Pilot 必须满足：

- judging complete；
- pair graph audit ok；
- hard control accuracy `>= 1.0`；
- same-order repeat consistency `>= 0.80`；
- effective non-tie response signal `>= 0.25`；
- strategy pairs have response signal：strategy pair tie rate `< 0.50`；
- M1 / M0 / M2 / strategy / strategy omission / response outputs complete。

### Diagnostics, Not Blocking

以下必须报告，但不阻塞 full judging：

- aggregate control accuracy；
- boundary control pass/fail；
- raw dual-order agreement；
- raw reversal consistency；
- raw position bias；
- overall and by-pair-type tie rate；
- dual-order disagreement resolved-to-tie count；
- response preference distribution。

Raw position bias 只在 single-order audit rows 上计算。Dual-order rows 的 `A/B` 表示 `action_a/action_b` identity，不再是 presentation position。

## 5. 论文解释边界

V3 gate 只说明 measurement pipeline 可以进入 full development judging，不证明 PM hypothesis 成立。

Response quality 在本研究中仍是非劣约束，而不是默认 superiority claim：

```text
lower 95% CI of NetWin(PM vs strongest preregistered baseline) > -0.05
```

Memory / strategy 质量来自独立 audit head：

- M0 omission appropriateness；
- M2 source utilization / unnecessary exposure / stale-conflict / unsupported personal claim；
- strategy relevance / utilization / over-structuring / premature advice。

若 response preference 信号在 full judging 中仍然偏弱，论文应强调 resource reliability / cost trade-off，而不能声称 response quality improvement。

## 6. Freeze Rule

Protocol V3 必须在以下步骤前冻结：

1. full synthetic judging；
2. PM training；
3. validation threshold / baseline selection；
4. ESConv / EvoEmo external evaluation；
5. final LLM judge or human blind evaluation。

冻结后不得根据 validation、test、external 或 human-eval 结果修改 hard gates、non-inferiority margin、baseline selection rule 或 success criteria。
