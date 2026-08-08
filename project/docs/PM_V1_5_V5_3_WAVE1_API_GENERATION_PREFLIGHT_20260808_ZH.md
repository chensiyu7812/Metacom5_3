# PM V1.5 V5.3 Wave 1 API 生成预检

日期：2026-08-08

> 2026-08-08 更新：用户决定改为 Wave 1A（2 人 canary）与 Wave 1B（11 人扩展），并优先使用网页端生成。下述整批 API identity 从未获批、API=0，现标记为 `SUPERSEDED_UNAPPROVED_FULL_BATCH_IDENTITY`，不得执行。若未来改回 API，将分别冻结两个新 identity。

## 冻结执行面

- identity：`v53wave1gen_97e54c624611f1d4915a85a69c7d71ea`
- 状态：等待独立费用与 identity 授权
- 新用户：13
- 逻辑/最大物理调用：52 / 52（每用户 4 次、无隐藏 retry）
- 最大代理费用：`$7.338`
- 建议硬授权上限：`$7.50`
- sampling：temperature `0.2`，无 seed

作者端点：

- `chatgpt_pro` 家族标签：OpenAI `gpt-4o` API，6 人，最高 `$2.76`
- `claude` 家族标签：Anthropic `claude-sonnet-4-6` API，7 人，最高 `$4.578`

这里的 `content_author` 是模型家族来源标签，不声称 API 端点与网页端 ChatGPT Pro/Claude 产品表面完全相同。

## 单用户四阶段

1. 先生成紧凑的 world/chronology plan；
2. 分三段生成连续会话、exact spans 与 typed candidates；
3. Python 只负责冻结配额、拼装、来源绑定和调用正式 V2 validator，不代写语义内容；
4. 不提供第五次自由修复调用。

优先执行 `p2r_formal_gpt_u010` 与 `p2r_formal_claude_u005` 两个跨提供商 canary。两者都达到 `MACHINE_PASS_BATCH_AND_SEMANTIC_REVIEW_PENDING` 后才继续其余 11 人；任一 schema、配额、lineage 或时间错误都会 fail-closed 停止。

## 数据与评测隔离

- author model 不读取 ESConv、EvoEmo、ES-MemEval 原文、答案或实验 outcome；
- world seed、style pack 和构造 assignment 不进入后续 Step1 特征；
- 当前 11 人不可修改，Wave 1 偏好类型由剩余全局配额确定性分配，以维持每作者每类 20 条的最终可达性；
- 生成成功仅表示单用户机器通过，仍需整批 duplicate/external-overlap 与集中 semantic review。

## 费用依据

- OpenAI GPT-4o 官方价格页：<https://developers.openai.com/api/docs/models/gpt-4o>
- Anthropic Claude Sonnet 官方价格页：<https://www.anthropic.com/claude/sonnet>

Wave 1 与已经执行的 Step2 `$0.20` 身份属于不同付费阶段；不得挪用或合并授权。
