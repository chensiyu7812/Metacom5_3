# Paper‑1 二元实质收益范围与 API 硬预算修订（2026‑09‑03）

状态：`ACTIVE RESEARCHER-AUTHORIZED SCOPED PRE-OUTCOME AMENDMENT`。研究者已明确批准：Paper‑1 保持简洁的二元实质收益路线；收益幅度、期望效用、动态 amount/top‑k 与 sequential/RL 留作后续。formal outcome=0、PM training=0，四把 outcome lock 继续 CLOSED。

## Paper‑1 到底学习什么

四个 standardized L2 logistic heads 分别学习：在其他可选资源全部 OFF、只切换当前 focal head 的成对反事实中，该资源产生 task-defined material positive effect 的概率。

运行时 ON 必须同时满足：机械 eligible、OOF 概率达到冻结 threshold、调用前预测 latency 可行、组合预算可行。Threshold V4 会用各候选策略实际选中回复的 task-specific official primary quality 选择总体 operating point，所以准确表述是：

> binary effect learning + magnitude-aware aggregate operating-point calibration。

这不等于 PM 已经学会逐请求预测“能提高几分”。论文主张限于：**根据出现实质收益的预测概率，在延迟可行时选择性打开资源。** 不主张逐请求最大化 `expected gain - cost`，也不主张 16 个组合的全局最优、动态 top‑k 或全对话 sequential optimum。

## 为什么这一区分重要

当前模型能区分“较大把握达到最低有意义改善”和“没有足够证据达到改善”，但不能直接比较：一个 90% 概率提高 1 分的状态，和一个 45% 概率提高 3 分的状态。后者需要 magnitude regression、expected-utility/contextual-bandit learner，互动式全对话还可能需要 sequential policy learning 或 RL。这些都是后续研究，不在 Paper‑1 临时扩张。

## 免费保留的幅度诊断

所有正式成对样本继续保存 task-specific `Q_ON`、`Q_OFF` 和 `ΔQ`。只在已经生成的 grouped cross-fitted pairs 与冻结 sealed decision-audit pairs 上做下列 secondary diagnostics，不因此新增 API 调用：

- OOF/held-out 预测概率分箱后的 realized gain；分箱规则在 sealed outcomes 前冻结并报告每箱 N。
- Benefit Capture：PM 选择 ON 捕获的正向 `ΔQ` 总量占全部可获得正向 `ΔQ` 的比例。
- net selected gain、harmful-open rate、false-open harm、PM-OFF 正向 gain 的分布/ECDF。
- `max(Q_ON,Q_OFF)-Q_selected` 的 local counterfactual regret；ESC/DG 只能称 one-step/local regret，不能称全局 policy regret。

这些指标必须按 `task × head` 分开报告。ESC、QA、Summary、DG 的量纲不同，禁止相加成跨任务 composite。Benefit Capture 不能单独报告，因为 Always‑ON 会天然捕获全部正收益；必须同时报告 ON rate、resource tokens、net selected gain 与误开伤害。若正向收益分母为零则记 `NA`，不填 0 或 1。只有 teacher ordinal preference、没有两臂有效 scalar official primary quality 时，不伪造数值 `ΔQ`。

不把“missed large benefit”设为新的主指标或门；优先报告正收益捕获、PM-OFF 的正向收益分布和 local regret。如确需报告 `large`，阈值只能来自任务自然单位或 calibration-only 数据，并在 sealed outcome 前冻结。

## 全流程 API 预算

所有当前 Paper‑1 路线的付费 LLM API 累计目标为 USD 25–35，绝对硬上限 USD 50；已发生 v9 `$0.03079930` 计入。NVIDIA hosted NIM（若收费）、OpenAI、Gemini、Claude、Qwen 或任何其他收费 Generator/判卷调用都计入；本地 A6000、ESC‑RANK、Mistral observation scorer、BGE 与 PM 训练不计 API 账，但仍记录计算身份。

冻结阶段 envelope：401-session 编译/验证 `$1.50`、96-pair teacher qualification `$0.10`、token/call/latency pilots `$1.00`、amount/top‑k `$4.00`、训练 effect labels 官方评分 `$8.00`、Gemini residual pairwise `$2.00`、六个主要 RQ2 系统正式官方评价 `$22.00`、component-minus/必要 secondary `$5.00`、失败重试和价格波动储备 `$5.00`，加已发生 v9 后共 `$48.63`。这是上限分配，不是花费目标或调用授权。

每次付费调用前必须满足：

```text
已结算费用 + 未结算预留 + 本次最坏费用 <= USD 50
```

累计达到 `$43` 后禁止启动 optional analysis，并至少保留 `$5` 给主实验失败重试。同一成功 prompt hash 不得重复付费；parser/transport 最多重试一次；不能因结果不好重跑。预算紧张时依次放弃 optional secondary、component-minus，再压缩非必要校准；六个主系统的官方评价和主学习所需 effect labels 优先保留。

## Teacher 省钱路线

96-pair reference 的总数已经包含约 20% reverse duplicates，不再额外追加。先由冻结 task-specific official anchors 处理明确病例；只有 official tie/conflict residual cases 交给冻结的 Gemini Flash‑Lite judge；仍不确定则保留 `uncertain` 并排除出监督 likelihood。

Claude 不做第二套全量并行判卷，只能在 Gemini 无法胜任时，在同一既有 cap 内作为替代方案，不能叠加花费。不能按 ON label 多、PM 得分好或论文结果漂亮来选择 judge。

## 官方评价不因预算降级

预算不能把 ESC‑Eval / ES‑MemEval 的官方 scorer 换成便宜代理。QA/Summary 的离线独立 OpenAI 评分可使用官方 Batch 机制；DG 的有依赖多轮调用不假定可直接 batch。Hosted NIM 与本地同权重也不是可静默互换的同一 measurement stack；若配额不足，必须先版本化 provider/backend amendment。

本修订新增的是范围边界、次要诊断边界与财务 hard stop，不新增任何 accuracy、precision、agreement 或 effect-size PASS gate。下一步仍是 active Multi‑View runtime → 401 zero-outcome census → amount surfaces → teacher/effects → four L2 heads → OOF Threshold V4 → sealed audit → official benchmark。
