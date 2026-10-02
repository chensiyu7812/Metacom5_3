# Paper-1：端到端延迟约束下的选择性资源策略修订（2026-09-03）

状态：`ACTIVE / RESEARCHER-AUTHORIZED SCOPED PRE-OUTCOME AMENDMENT`

机器合同：`project/data/paper1_authority/paper1_latency_constrained_selective_policy_amendment_20260903_v1.json`

研究者在确认 formal outcome、formal PM training 均仍为 0 后授权本修订。授权意图是恢复 Paper-1 最初的系统主张：PM 不只预测资源是否可能改善回复，还应在用户可接受的端到端响应时间内，仅为真正需要额外策略或长期记忆的状态打开资源；简单状态若 `R0+M0` 已足够，应保持关闭。

## 1. 修订的核心区分

本修订将两个此前混淆的对象分开：

1. `quality-effect estimand`：资源是否在冻结 stack 下产生 material response-quality benefit。Cost/latency 不改变这个事实，因此不进入该 label 或 learner loss。
2. `deployment action-worthiness`：即使资源有质量收益，本次是否仍值得打开。端到端 latency 必须进入该决策。

正式语义为：

```text
quality_effect_positive
AND no_material_quality_or_integrity_harm
AND predicted_end_to_end_latency_is_SLA_feasible
    -> action-worthy ON
otherwise
    -> OFF or a cheaper feasible resource subset
```

因此，“Cost 不进入 label”只限于纯质量 effect label；它不再意味着 Cost 与 ON/OFF policy 无关。

## 2. scoped precedence

本修订具有以下有限优先级：

- 覆盖 2026-08-31 threshold amendment 中“one-SE admissible 后按 minimum Generator-input tokens 选择”的 primary tie-break；
- 覆盖 2026-08-16 execution reconciliation 中任何可被解释为 Cost 仅报告、不参与部署 action 的条款；
- 恢复但重写旧 execution blueprint 的 `benefit worth cost`：不构造 `Quality-lambda*Cost`，改用可解释的 hard latency feasibility + lexicographic selection；
- 不改变 four-head L2 benefit learner、Route A、public-only、official metric hierarchy、cross-fitting、Generator、benchmark arms 或 confirmatory outcome isolation。

## 3. primary operating-point 选择

每个 grouped-OOF / outer-training-inner-OOF candidate policy 先计算用户体感 latency distribution。primary 选择顺序改为：

1. 丢弃违反冻结 hard latency SLA 的 candidate；
2. 在 latency-feasible candidates 中形成 quality-first one-standard-error admissible set；
3. 在 quality-admissible set 中依次最小化：p95 request-to-completion、median request-to-completion、p95 time-to-first-token、mean Generator-input tokens、realized ON rate；
4. 再以 higher threshold、canonical order消除完全并列。

Cost 不能抵消 material quality/integrity failure。API 美元成本不进入 primary action；它与 tokens 继续作为可移植效率指标报告。

如果连 `ALWAYS_OFF/R0+M0` 都违反 hard SLA，则是系统实现不满足部署约束，不得通过关闭更多资源伪装解决。

## 4. latency 测量对象

每个可执行 call 必须区分并记录：

- PM feature/decision latency；
- retrieval/embedding latency；
- resource render/packing latency；
- Generator request latency；
- request-to-first-token (`TTFT`)；
- request-to-completion (`T_complete`)；
- retry/queue/network metadata；
- 若未来纳入语音，另记 ASR endpointer 与 TTS first-audio；当前文本 Paper-1 不得把 text latency 写成 speech/audio latency。

`T_complete` 必须覆盖从系统收到冻结可见 state 到完整文本 response 可用的 wall-clock；不得用 ESC-RANK/evaluator离线评分时间冒充用户响应延迟。报告 median、p90、p95、max 与 timeout/fallback rate，primary constraint 使用 p95。

Primary percentile 必须从每次真实 call 的 raw wall-clock samples 计算；不得先把每个 state/repeat 压成 mean 后再对这些 means 求 p95，因为那会隐藏尾延迟与 SLA 违规。raw timing 只记录运行性能，不读取回复质量。

## 5. SLA 数字的冻结规则

研究者已明确 `60,000 ms` 响应不可接受，因此它是排他的 absolute ceiling，而不是正常目标。正式 `TTFT` 与 `T_complete` budgets 尚不能凭空填写：

- 先在冻结硬件/provider/streaming mode 上做 zero-outcome latency profiling；
- 只读取时钟、tokens、finish/retry，不读取 capability outcome；
- 按 task interaction mode 冻结预算；复杂任务可以有更宽预算，但全部必须严格低于 60,000 ms；
- budgets、percentile estimator、timeout/fallback 在 effect/confirmatory outcome 前由研究者一次性批准；
- 不根据哪个 budget 让 PM official score更高来选择。

在 exact budgets 冻结前，formal operating-point freeze 保持：

`IMPLEMENTATION BLOCKER — RESEARCHER DECISION REQUIRED`

这不是 empirical performance gate，而是尚未填写的部署需求参数；它不阻止 ontology、instrumentation、candidate materialization、人评准备或 zero-outcome profiling。

## 6. 单头与多头 runtime policy

- RQ1 只有 RS：benefit threshold通过后仍须满足该 call 的 latency feasibility。
- RQ2 的 MP/ME/MS 先产生独立 first-order benefit probabilities；全局 arbiter只在这些 eligible、threshold-positive heads中分配 latency budget。
- 如果联合请求超预算，arbiter按预冻结的 probability-margin-per-incremental-p95-latency排序选择可行 subset；canonical head order只处理完全并列。
- 这是透明的 first-order constrained allocation，不声称学到 interaction-aware/global-optimal policy；joint interaction仍只作诊断。
- Step2 不得擅自丢弃已分配资源；最终 subset identity必须在 treatment delivery 前确定并进入 trace。

## 7. “不持续共情/个性化/套策略”的评价

resource correctness 与 action appropriateness 分开。Pairwise effect rubric 必须评价：

- 新资源是否满足当前回复中真实未满足的需要；
- 是否只是重复当前可见信息；
- 是否为展示记忆而生硬提及过去；
- 是否机械重复共情、强行个性化、过度建议或套用一种策略；
- 简洁 `R0+M0` 是否已同等或更合适。

若 ON 只是增加这些无必要行为，判 `equivalent` 或 `OFF better`，不能因出现更多 empathy/memory surface wording而奖励。

ES-MemEval DG 官方场景主动诱导回忆，不能单独识别普通轮次的克制能力。因此新增 public-only `Natural-turn Appropriateness` secondary slice：

- RS 从 ESConv ordinary turns抽取；
- MP/ME/MS 从 EvoEmo ordinary historical session turns抽取；
- 使用 strict-past、user/session grouped holdout 与 outcome-blind strata；
- 人类/机器盲评只比较当前回复的条件适切性；
- 它支持 selectivity/mechanism claim，不替换 ESC-Eval/ES-MemEval official capability outcomes。

## 8. 两套 decision correctness

每个 head/task分别报告：

1. `Effect correctness`：PM 是否区分 oracle-beneficial 与 nonbeneficial states；
2. `Action correctness`：在 hard latency constraint 后，PM 是否作出 action-worthy ON/OFF。

除既有 ON-benefit recall、OFF specificity、unnecessary-open、missed-benefit、Brier、log loss 外，新增：

- beneficial-but-latency-infeasible rate；
- latency-feasible ON precision/recall；
- p95 SLA violation rate；
- R0+M0 sufficient / avoided-unnecessary-intervention rate；
- quality-admissible latency saving；
- timeout/fallback rate。

交互式 ESC/DG 的 local action correctness仍是 myopic fixed-prefix estimand；全程效果由 official end-to-end arms识别，不称 global policy regret。

## 9. 会失效与必须重跑的内容

必须修改/重跑：

- `PolicyDecision` 仅使用 probability threshold 的 active contract；
- `CostRecord.latency_ms` 单字段语义；
- threshold primary selection 的 minimum-token-first实现与测试；
- pre-outcome freeze 中把 Cost 完全排除于 action-worthiness的校验；
- v2 proposal 中所有可能被理解为 Cost 仅进入报告的措辞；
- threshold/authority/integration contract tests；
- zero-outcome latency instrumentation smoke 与 profiling。

不失效：

- 纯质量 effect labels/official raw outcomes；
- Cost 不进入 quality learner label/loss；
- 8/31 的 grouped-OOF/outer-training-inner-OOF outcome isolation与 0.5 reference；
- frozen Generator、official evaluator closeout、public sources、folds与已完成零 outcome工程证据。

## 10. 当前锁与调用状态

- calibration outcome locks：`CLOSED`
- confirmatory outcome locks：`CLOSED`
- 本修订新增 paid API calls：0
- 本修订新增 formal outcome calls：0
- 本修订新增 PM training runs：0

下一步仅实施 authority、contract、instrumentation、offline policy、natural-turn sampling plan和测试；然后运行 zero-outcome latency profiling并提交 exact SLA freeze packet。
