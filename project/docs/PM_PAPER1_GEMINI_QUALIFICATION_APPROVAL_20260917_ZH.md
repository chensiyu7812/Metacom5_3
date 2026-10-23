# 待审批：Gemini 裁判资格测试（2026-09-17）

历史审批提案，以下保留批准前的内容。研究者随后批准 `$0.10`，本批已执行并收口；当前状态以[资格测试结果](PM_PAPER1_GEMINI_QUALIFICATION_RESULTS_20260917_ZH.md)为准。

执行器和现有试卷的对照流程已完成，现在停在计费生成之前。无需新增或重做人评。

本次请审批两项相连的内容：

1. **沿用已完成的人评。** 如实记录两名评审共同完成的 A 卷；原始 A、六题人工复核和助手事实核查分别报告。AI B 单列为探索性比较，不写成人类评审，也不选择一致率最高的视图作为唯一结果。
2. **运行冻结的 96 题 Gemini 资格测试。** 模型 `gemini-2.5-flash-lite`，模型元数据版本 `001`；沿用 V2 英文 rubric 和原始题面，不加入人工答案或复核理由。每题最多一次重试，全部实际结算及未结算预留合计不超过 **$0.10**。

## 已核验的执行范围与费用

| 项目 | 结果 |
|---|---|
| 试题 | 80 个 base + 16 个翻转呈现；ESC 32、QA 16、Summary 16、DG 32 |
| 原始请求 | 96/96 hash、题面、参考资料与方向一致 |
| 官方模型元数据 | `models/gemini-2.5-flash-lite`，version `001` |
| 官方 countTokens | 96/96 成功；输入合计 586,850 token |
| 首轮按最大输出计算 | $0.0685154 |
| 首轮含每题 256 输入 token 计费余量 | **$0.0709730** |
| 阶段总上限 | **$0.10，含重试**；不足时停止并保留部分结果，不扩大预算 |
| Paper-1 已核对累计账本 | $1.44178151；剩余 $48.55821849 |
| 本阶段已有 generateContent 调用 | **0** |

计数已覆盖完整生成请求。固定计费余量用于应对 provider 计数与最终 usage 的差异；若 usage 超出预留的 token 范围，保存原始响应并停止核对。两轮全部按上限执行会超过 $0.10，因此重试仍受逐次预算控制，不能承诺 192 次调用全部执行。模型元数据与 countTokens 成功不等于已验证生成权限；首次生成也属于待批准的 96 题，不额外增加探测题。

费率来自 [Google 官方 Standard 文本价格](https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash-lite)：输入 $0.10 / 百万 token，输出 $0.40 / 百万 token，2026-09-17 核查。计数使用 [官方 countTokens 接口](https://ai.google.dev/api/tokens)。

## 已完成的执行保护与分析

- 原始请求不可变；成功请求不重复付费；最多一次规定原因的重试。
- 每次调用先进入现有累计预算账本，未知费用保守按预留上限记账；裁判重试也受累计 $43 可选调用停止线约束。
- 已落盘响应可在结算前中断后恢复；只有预留而缺少响应记录时停止核对，避免重复调用。
- 身份、模型版本、结构化输出、超出 token 范围、认证/配置失败均留记录；不隐藏失败。
- 已解析的 `uncertain`、操作失败和未尝试请求分别统计。
- 自动产生三个参照视图的逐任务 agreement、macro recall、equivalent recall、翻转一致性、位置描述、解析情况和费用；bootstrap 按 memory owner / ESC source dialogue 聚类，2,000 次、seed 20260917。不引入经验性 PASS 阈值。
- 75 项针对性测试通过，涵盖模拟 HTTP 错误、超时、重试耗尽、预算上限、缓存恢复、模型漂移和审批绑定；集成及编译检查通过。完整 public-only 测试结果另存验证记录。

## 参照流程的局部变更

**PROPOSED RESEARCH CHANGE — NOT AUTHORIZED**，审批前不激活。

变更条款：原 V2/V3 两份独立 primary 人评及 consensus 流程，调整为实际已完成的联合 A 人评与明确标记的复核/助手敏感性分析。原因是实际评审方式已明确，研究者要求不再增加人评。不能再报告原定 192 份独立 primary judgments 或独立人评一致率；原始资料、142 个回复、80/16 样本和请求身份仍保留。

不重做人评、不重生成回复；仅执行尚未开始的 Gemini 资格测试。论文官方 RQ1/RQ2 能力指标与 PM 主张不变，裁判一致性按实际参照来源解释。本次不授权 top-k outcome、正式 effect labels、PM training 或打开四把 outcome lock。

## 审批依据与复现

仓库 [AGENTS.md](../../AGENTS.md) 要求研究流程变更先写成提案并等待明确批准；现行 [Gemini 身份文件](../data/paper1_authority/paper1_gemini_pairwise_teacher_identity_20260908_v2.json) 明确 `paid_calls_authorized_by_this_identity: false`。因此现在暂停的事项是上述两项具体批准。

执行计划：`project/outputs/paper1_pairwise_teacher/gemini_qualification_v2/execution_plan.json`，绑定全部请求、参照文件、provider preflight 与执行代码的 hash。`authorization.pending.json` 保持 `PENDING/false`；研究者批准后，由执行者记录授权并绑定这份计划，不需要研究者修改 JSON。

入口：`python scripts/paper1/64_run_gemini_teacher_qualification.py` 默认只做离线准备；`--mode provider-preflight` 仅核查模型与计数；`--mode live --authorization <已批准文件>` 才能执行本批生成。
