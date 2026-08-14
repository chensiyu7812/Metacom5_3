# PM V1.5 V5.3 Step2 Q64 执行记录

日期：2026-08-08

## 已执行范围

- 冻结身份：`v53step2semexec_8f51ee42c67e85c41b3721b9d1b731fe`
- 用户授权上限：`$0.20`
- 实际逻辑调用：64 / 64
- 实际物理调用：64
- 模型：NVIDIA `meta/llama-3.1-8b-instruct`
- 实际代理费用：`$0.0100746`
- prompt tokens：42,880
- completion tokens：6,071

## 机器结果

- typed response 直接通过：50
- 确定性回退到 M0：14
- 主要机器错误事件：
  - `REQUIRED_EVIDENCE_NOT_USED`：10
  - `EVIDENCE_CLAIMED_USED_BUT_NO_WORD_TRACE_IN_REPLY`：5
  - 一条回复可同时触发两类错误。
- 未观察到：说话人/owner 错置、内部资源标签泄漏、虚构历史、自由二次 rewrite。

这些数字只能说明冻结机器 guard 的输出，不能自动等同于 50 条语义成功、14 条语义失败。

## 执行后发现的测量缺口

旧 runner 在 guard 触发确定性回退时只保存回退回复和错误码，没有保存付费端点产生的原始首轮回复。因此，14 条回退无法由人或独立语义评审判断究竟是：

1. generator 确实没有使用证据；还是
2. generator 已语义使用证据，但词面 trace guard 过严。

这属于测量记录缺口 `V15-ENG-25`，不属于看结果后调整模型或阈值。原 64 次机器计数仍可审计，但完整 Step2 语义资格结论暂缓。

## 一次性测量续跑

已冻结只覆盖上述 14 条的测量续跑计划：

- identity：`v53step2q64cont_85dc8093dd68f981bbee0968b7c8db3a`
- 最大物理调用：28
- 费用授权建议上限：`$0.05`
- 方法、模型、prompt、typed program 与 guard 不变；唯一变化是保存回退前的原始 provider text 与结构化审计面。

该续跑尚未获授权、API 调用为 0。不得复用已消费的原 Q64 身份。

## 解释纪律

- 不使用这 14 条结果修改生成 prompt、guard 阈值或 Step1 特征。
- 续跑只补齐缺失测量面；完成后做一次集中语义裁决。
- 若 guard 与语义裁决不一致，分别报告 machine guard specificity 与 generator semantic use，不把两者混成一个“通过率”。
