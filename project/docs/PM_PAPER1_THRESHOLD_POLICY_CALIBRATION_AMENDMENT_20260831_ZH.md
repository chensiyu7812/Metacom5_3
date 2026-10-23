# Policy Manager Paper 1 阈值策略校准修订（2026-08-31）

状态：`ACTIVE / RESEARCHER-AUTHORIZED SCOPED PRE-OUTCOME AMENDMENT`

机器合同：`project/data/paper1_authority/paper1_threshold_policy_calibration_amendment_20260831_v1.json`

## 1. 修订范围与依据

本修订只替换 active Paper-1 中“固定 `0.5` 为唯一 primary operating point”的条款。研究者于 2026-08-31 明确批准在正式 outcome、PM training 和 confirmatory evaluation 均未开始时，将固定数值改为 outcome-isolated 的阈值选择协议。

`0.5` 是本项目在 2026-08-16 execution reconciliation 中自行预冻结的透明规则，不是 ESC-Eval 或 ES-MemEval 官方协议要求。它在概率充分校准、开错与关错代价对称且不计资源成本时有清晰解释，但这些条件不能由数值本身保证。

本修订不改变：

- RS/MP/MS/ME 四个二元头；
- Route A 与其他 optional heads OFF 的 canonical background；
- standardized L2 logistic regression learner；
- materially-positive paired effect 的 soft/binomial target；
- `ON better=1 / OFF better=0 / equivalent=0` 的训练计数；
- uncertain/invalid 不进入 likelihood；
- Cost 不进入 label 或 loss；
- public-only、exact-evidence cross-fitting、冻结 Generator、Step2 边界；
- RQ1/RQ2 benchmark arms 与官方 metric hierarchy；
- 四把 calibration/confirmatory outcome lock。

## 2. 被替换条款

旧 primary rule：

```text
eligible AND predicted_positive_effect_probability > 0.5 -> ON
```

新 primary rule：

```text
eligible AND policy_h,t,f(predicted_positive_effect_probability, tau*_h,t,f) -> ON
```

其中 `tau*` 只能由 grouped OOF 或 RQ2 outer-training/inner-OOF paired effects 按本修订的固定协议产生。任何 confirmatory outcome、held-out outer-target outcome、未来/参考/gold 字段均不得参与选择。

`0.5` 不删除，改为所有 head/task 必报的 mandatory transparent reference。`ELIGIBLE_ALWAYS_ON` 与 `ALWAYS_OFF` 同时进入表面，以直接诊断是否学会 ON 与 R0/M0；它们不是新增 learner。

## 3. 候选 operating-point 表面

冻结候选为：

```text
ELIGIBLE_ALWAYS_ON
tau in {0.05, 0.10, ..., 0.95}
ALWAYS_OFF
```

`tau=0.5` 必须单独标识和报告。候选表面不得在看过 calibration 或 confirmatory outcome 后扩展、缩窄或改变步长。

RQ1 冻结一个 RS operating point。RQ2 因 QA、Summary、DG 的官方 outcome surface 不同，为每个 `(MP/MS/ME, task)` 与 outer fold 冻结 operating point；这不构造跨任务 composite，也不把任务阈值误写成新增 PM head。

自然 effect evidence 不可识别的 head/task 不得 synthetic rescue、借用其他任务阈值或读取 held-out outcome；其 operating point 为 `ALWAYS_OFF / not identifiable`，并收缩该 cell 的 claim。

## 4. 质量优先、成本次优的机械规则

每个候选 policy 只复用已授权的 paired effect 与 grouped OOF prediction，不新增 Generator、judge 或 benchmark 调用。

对每个有效 repeat：

- `ON better`：选择 ON 得到质量 credit；
- `OFF better`：选择 OFF 得到质量 credit；
- `equivalent`：ON 与 OFF 都得到质量 credit，随后成本 tie-break 优先 OFF；
- `uncertain/invalid`：不进入选择质量分母，但保留原始审计记录。

质量按预冻结 cluster 先聚合，再计算 mean 与 standard error。令 `g_best` 为 mean quality 最高的候选，one-standard-error admissible set 为：

```text
mean_quality(g) >= mean_quality(g_best) - SE(g_best)
```

在 admissible set 中选择 mean Generator-input-token 最小者；仍并列时依次选择 realized ON rate 更低者、较高 threshold、canonical grid order。

这一规则不构造 `Quality - lambda * Cost`，不允许 Cost 抵消 material quality/integrity failure，也不改变 benefit-only learner。

## 5. 隔离与 cross-fitting

- RS：只能使用 ESConv effect-construction 数据的 grouped OOF predictions 与 paired labels选择 `tau*_RS`；ESC confirmatory role cards不得参与。
- RQ2：每个 held-out outer fold 的 operating point只能由该 fold的 outer-training 数据通过 inner grouped OOF产生；held-out target outcome不得参与。
- threshold grid、quality coding、cluster unit、one-SE rule和tie-break在任何 effect outcome前冻结。
- confirmatory outcome打开后，不得重新选择阈值；其他阈值只按预注册 sensitivity surface报告。

## 6. 概率与开关诊断

每个 head/task/fold 必须报告：

- Brier、log loss、reliability/calibration curve；
- fixed-0.5 与 selected operating point；
- realized ON rate；
- ON-benefit recall 与 OFF/non-benefit specificity；
- unnecessary-open、missed-benefit、harm/misuse diagnostics；
- Generator input/resource/output tokens、latency 与可恢复 API cost；
- always-on、always-off、matched-random 和 selected policy 的区别。

这些不是 empirical PASS gate。若选择退化为 always-on/off，必须如实报告，并相应收缩“state-dependent learned allocation”主张。

## 7. Top-k、阈值与部署成本的研究边界

Top-k/bundle amount 决定“ON 时注入多少资源”，阈值决定“何时 ON”，两者是不同层：

1. 先按既有 amount amendment 做全局/任务级 resource-amount calibration，冻结 `k*`、bundle 与 token cap；
2. 再用冻结 treatment 构造 repeated effects并训练四头；
3. 最后在 OOF/outer-training effects 上冻结 operating point；
4. 全栈冻结后才运行 confirmatory evaluation。

Top-k 和 operating point 是支撑 RQ1/RQ2 的方法学选择问题，不新增第三、第四个核心 RQ。论文可将下列问题作为预注册 secondary analysis：

- resource amount 对 official quality、冗余、输入 token 与延迟的影响；
- 同等或统计不可区分质量下，什么 operating point 最省 Generator-input tokens；
- 部署时 latency/token/API cost 的分解及不同预算 operating points 的 sensitivity frontier。

正式能力结论仍来自 ESC-Eval/ES-MemEval。部署层通常首先受 latency 约束，但 latency、token 和 API cost 必须分开报告；不得只因当前 provider 价格低就把 token 或 latency 隐去。

## 8. 对既有证据与执行顺序的影响

本修订发生在 formal effect、PM training 和 confirmatory outcome 之前，因此不使既有 RS catalog、BGE ranking、Memory compiler、split/fold、人评或 zero-outcome surface 失效，也不要求重新编译/编码/人评。

活动顺序更新为：

```text
resource qualification
-> treatment/execution qualification
-> evaluator qualification
-> resource-amount calibration and k/bundle freeze
-> repeated effect construction
-> four-head training with grouped OOF predictions
-> outcome-isolated operating-point calibration
-> full-stack freeze
-> confirmatory evaluation
```

本轮只允许 authority、contract、offline selector、validator 与测试变更；四把 outcome lock继续 `CLOSED`，paid API calls、formal outcome calls与PM training runs均为 `0`。
