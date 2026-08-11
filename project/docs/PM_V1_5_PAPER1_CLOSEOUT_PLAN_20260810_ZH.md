# PM V1.5 第一篇论文有限收口执行方案

状态：`ACTIVE HUMAN-READABLE PLAN / ZERO API / 2026-08-10`

唯一机器权威：`data/pm_v1_5_contracts/active_method_authority_v1.json`  
冻结方法合同：`data/pm_v1_5_contracts/paper1_bounded_suitability_safe_yield_closeout_v1.json`

本文只解释机器合同，不得覆盖机器合同。二者冲突时必须停机，以机器权威为准；不得选择更方便的版本继续。

## 1. 这次究竟改变了什么

研究目的没有改：仍然研究一个有限、低容量、可审计的 PM，决定何时开启 MP、MS、ME、RS，
并在同一检索、executor、generator 和 evaluator 下与 always-off、fixed-high、透明规则和同预算策略比较
质量、明确 grounding/interaction risk、功能和成本。

改变的是 PM 的主训练靶：

- V5.3/V5.4 试图直接预测非常细小的 `positive-support-contribution uplift`；它把一次随机回复和
  reviewer 的细微偏好放进训练真值。正式结果证明该方向不能稳定复现。
- 本方法先要求 actual Rank-1 候选在生成前 structurally valid 且 bounded suitable；然后让每个组件
  head 预测：在当前冻结 executor/generator 下，请求这个候选能否稳定产生 **safe functional yield**。
- safe functional yield 必须同时满足：候选确实在回复中产生实质贡献、组件 minimum 被实现、没有
  material risk。generator 不用、fallback 或误用都是部署 ITT 的 0；机械 assignment/binding/缺输出
  才是 invalid。
- Quality 不再生产 PM 标签，但仍是最终系统不可绕过的非劣门。资源即使被正确使用，只要最终回复
  质量显著变差，系统仍不及格。

因此它不是简单的“相关性分类”，也不再声称 PM 直接预言哪一句回复最受人喜欢。准确主张是：

> PM 学会在有限可见条件下预测哪些合格资源能被当前固定系统安全、实质地利用；端到端实验再验证
> 这种条件路由是否相对 baselines 保持即时支持质量、控制 material risk 并减少成本。

## 2. Suitability、safe yield 与最终 Quality 的关系

### 2.1 Suitability 是资格门，不是最终价值

它回答：候选是否属于当前用户和严格过去、是否提供当前尚未出现的具体增量、是否能实现该组件的
定义功能、当前边界是否允许。`UNKNOWN` 在部署时 OFF，在训练时不伪装成负例。

“适合”只表示值得交给固定系统尝试，不表示必然让回复更好。V5.4 的 MS 例子已经证明：reviewer
可以一致认为 MS 被正确使用，却仍可能认为 ON 回复不如 OFF。

### 2.2 Safe functional yield 是四个 PM head 的主标签

每个冻结 generator seed 单独标 0/1：

`candidate contribution present AND component minimum realized AND no material risk`

每个 state 的多个 seed 总权重为 1。模型学习的是在部署 ITT 下产生 safe yield 的概率；不删掉
generator non-use、fallback 或 misuse，也不把它们错误归为检索/PM 的语义失败。

### 2.3 Quality 是最终系统 guardrail

Quality、Risk、Function、Cost 始终分别报告。Quality 不稳定不再阻止 PM 完成训练；但最终 learned
policy 若相对 always-off 或 fixed-high 明显降低质量，就不能称系统及格。不同 reviewer family 对
Quality 方向不一致时，分别报告敏感性，不通过多数票或新 rubric 把失败救成 PASS。

## 3. 不要求四个头全部通过

结果按 head 明确分层。这里不能只数通过头数，还必须满足组件组合：

| 通过头数 | 允许主张 | 失败头处理 |
|---:|---|---|
| 4/4 | full four-component learned PM | 无 |
| RS + MP/MS/ME 至少一个 | primary partial multi-component learned PM | `learned_pm_qualified` 中失败头固定 OFF，逐头披露 |
| 仅 RS | RS component router；Paper 1 primary FAIL | 没有学会长期记忆路由 |
| 仅一个或多个 memory head、RS 失败 | memory component result；Paper 1 primary FAIL | 没有学会策略路由 |
| 0/4 | no learned PM | 报告负结果 |

第一篇论文的正式最低目标是 **RS 必须通过，并且 MP/MS/ME 至少一个通过**，随后完成所有适用公共轨道
的同栈系统比较。优先争取 RS、MP、MS；ME 按真实稀疏覆盖能学到多少报告多少。合法动作接口仍有
16 个；但 partial PM 实际可达动作子集和 OFF 比例必须报告。不得给失败头偷偷换透明规则后仍写成
full learned PM；这种 hybrid 只能作次要敏感性分析。

机器修正条款：`data/pm_v1_5_contracts/paper1_primary_head_success_amendment_v1.json`。该条款只修正
primary passing-head 组合，不改变 per-head 标签、门槛、fold、16 动作、baseline 或最终 Q/R/F/Cost 门。

## 4. 数据只使用公共主干，不再生成 80 个长期用户

### 4.1 ESConv

- train 934、validation 186；test 180 中隔离与 EvoEmo 重叠后最终 169 dialogue；
- outer-train 用于 RS state/candidate/suitability/safe-yield；
- 没有同用户 memory 时 MP/MS/ME 因无合法 candidate 关闭；
- 主要外测 RS 路由、结束/listen-only/重复负例、atomic move execution 和即时 QRC。

### 4.2 EvoEmo

- 18 users、401 sessions、既有 204 response selection identities；
- 只读取 runtime 可见的 raw current prefix 与同用户严格过去 raw sessions；
- 禁止把 `current_session_summary`、observation、event timeline、topic grouping 或 QA gold 放入 PM；
- 六个 outer folds 按 canonical source user 分组；同一 raw session 即使被不同 wrapper user 引用，也
  必须在同一 fold；
- 训练/评估 MP_PROFILE、MS_SESSION、ME_REUSABLE_OUTCOME，RS 为辅助；
- EvoEmo 没有 response preference items，因此 MP_PREFERENCE 不纳入公共主张，作为明确限制。

### 4.3 ES-MemEval

- 1,427 questions，覆盖 IE/TR/CD/user modeling/abstention；
- 只做独立 QA retrieval、multi-evidence、answer 和 abstention 压力测试；
- QA answer/evidence 必须与 generator-visible question 物理分离；
- QA gold 不训练 response PM，也不把 QA 能力误写成四组件支持回复质量。

## 5. 两道训练前门

### 门 A：公共数据的 fresh suitability 资格

旧 V3 构造包虽有高 agreement，但 construction realization 有错误；V5.3 public atomic packet 又实际
失败。因此两包都只能作为 codebook 证据，不能直接成为新 gold。

新包按组件分别检查四个原子轴。每轴 raw agreement 至少 `.80`、chance-adjusted agreement 至少
`.60`、derived decision raw agreement 至少 `.80`、resolved coverage 至少 `.80`；每 head 至少
8 个 suitable 和 8 个 not-suitable 独立 group。每个组件只允许一次资格；失败即固定 OFF，不再
新增小包或修改题目追分。

### 门 B：safe functional yield 测量资格

- candidate contribution agreement ≥ `.85`；
- component minimum agreement ≥ `.80`；
- material-risk agreement ≥ `.90`；
- resolved coverage ≥ `.90`；
- candidate-own boundary 归 Risk，不再混进 Function。

Quality 没有训练资格门，因为它不再是训练标签。

## 6. 训练和合理及格线

每个通过门 A/B 的组件训练一个标准化 L2 logistic primary；只允许一个冻结的 full-dialogue ×
actual-candidate BGE relation challenger。禁止轮换 embedding、模型、阈值或 family 追分。

当前只冻结不可降低的最低 floor：grouped OOF balanced accuracy `.60`、recall/spec 各 `.55`、
Brier 必须胜 prevalence、预测 ON/OFF 各至少 15%，并通过 fresh confirmation。正式数值门在
development 中看到 label prevalence、测量 reliability 和 prior baseline 后一次性冻结；只能比 floor
更严格，不能在 confirmation/external 后降低。无论 PASS/FAIL 都报告连续指标和 cluster uncertainty。

这个设计避免两种错误：一是把 `.65` 当脱离真实分布的神圣数字；二是看到结果后把门降到刚好通过。

## 7. Baselines 和最终系统门

主 baselines：always-off、fixed-high eligible、transparent suitability rule、learned qualified、
cost-matched fixed、cost-and-on-rate-matched random。它们共享 exact current state、candidate、
retriever、executor、generator、seed、guard、evaluator 和成本口径。

最终必须分别报告：

1. routing：逐 head proper score、BA、recall/spec、coverage、16-action Hamming/exact/oracle-compatible；
2. execution：requested→received→used→minimum→safe yield→fallback；
3. Quality：learned 对 off/high/rule 的同状态比较与 reviewer sensitivity；
4. Risk：两臂绝对 material/critical event，不用质量或成本抵消；
5. Cost：deterministic injected tokens 与 provider input/output/latency/USD 分开；
6. responsibility：source/candidate、retrieval、observation、PM、projection、executor/generator、
   measurement、system outcome 的最早失败层。

透明规则不是稻草人。learned PM 匹配规则可支持“低容量模型复现 bounded routing”；只有 fresh
结果严格更好，才声称 learned superiority。

## 8. 单向阶段与当前准确位置

1. `P0_ZERO_API_CLAIM_LABEL_VERSION_FREEZE`：完成；合同、amendment 与 authority 已通过 validator；
2. `P1_PUBLIC_SOURCE_AND_CANONICAL_GROUP_MATERIALIZATION`：结构部分完成并关闭；已物化 unlabeled state、literal candidate、canonical group 和物理分离 QA；
3. `P1B_ACTUAL_RANK1_MATERIALIZATION`：完成并关闭；37,097 个 state-component 行已物化，独立全量复算通过；
4. `P2A_SUITABILITY_QUALIFICATION_PACKET_MATERIALIZATION`：完成并关闭；132 条双 reviewer 空白盲包已物化并独立复算；
5. `P2B_FRESH_SUITABILITY_MEASUREMENT_QUALIFICATION`：尚未授权；每组件一次资格；
6. `P2C_SAFE_YIELD_MEASUREMENT_QUALIFICATION`：suitability 通过的组件才进入；
7. `P3_SINGLE_PUBLIC_TRAINING_AND_HEAD_QUALIFICATION`：一次 grouped OOF/full fit；
8. `P4_SAME_STACK_BASELINE_CONFIRMATION`：一次 baseline confirmation；
9. `P5_ESCONV_EVOEMO_ESMEMEVAL_REPORTING_AND_TERMINAL_CLOSEOUT`：三轨报告，终局。

当前仍不允许 API、标签、训练、baseline 或 external。P1 结构物化共得到 18,341 个
ESConv states、4,689 个 EvoEmo states、108 MP + 4,564 MS + 24 ME literal candidates，以及
1,427 份 generator-visible QA 和 1,427 份 evaluator-only gold。逐状态重算 strict-past candidate count、
owner、current-prefix、共享 session fold 和 forbidden-field canary 均通过。该一次性入口已关闭，不能
覆盖产物。P1B 随后冻结 37,097 个 actual Rank-1 行：RS 22,913/23,030、MS 4,442/4,689、
MP 846/4,689、ME 417/4,689 有执行候选；其余是明确的结构/检索 OFF，不是 PM 负标签。第二次从源面
全量重算的 Rank-1 身份与分数一致。P1/P1B 入口均已关闭，不能覆盖产物。下一步只能创建新的
content-addressed P2 phase manifest；phase manifest 只能授权阶段，不能修改本方法的 estimand、split、
标签、指标或 baselines。

P2A 已进一步冻结 132 条 actual-Rank-1 qualification surface：MP 34 条/17 groups、MS 34/17、
ME 28/14、RS 36/36。两位 reviewer 使用不同 item ID 和不同顺序；state/group/Rank-1 ID、抽样 stratum、
score/margin 与预期方向只存在于物理分离 private key。公开盲包没有任何标签或 outcome。P2A 入口已关闭。

## 9. 版本控制：以后什么才算“当前版本”

任何 artifact 必须同时满足以下条件才是 active：

1. `active_method_authority_v1.json` 指向当前 method；
2. method contract SHA256 完全匹配；
3. 当前 phase manifest 逐路径、逐 SHA256 点名该 artifact；
4. method registry 的 `canonical_next` 一致；
5. implementation tree、source/split/feature/label schema、model/evaluator/baseline identity 齐全；
6. paid release 在该 phase 明确授权并绑定 method/authority hash。

文件名更新、脚本编号更大、目录 mtime 更新、旧报告写 PASS、另一个聊天窗口说“当前”均没有授权力。
旧脚本可以作为历史复现资产，但不能自行成为当前 runner。

## 10. 当前唯一下一步

P0 authority validator、P1 structural final audit 与 P1B actual-Rank-1 独立全量复算均已通过。
P1 candidate manifest 为：
`data/pm_v1_5_contracts/paper1_p1_public_source_group_manifest_candidate_v1.json`，冻结 SHA256 为
`8498c9660bbd8cebc312a0638f76c27a7f379ca887fbffbaf6f6fe8d91ecbc6a`。

结构物化终审为：
`outputs/pm_v1_5_paper1_p1_structural_surface_final_audit_20260810/report.json`。

P1B 终审为：
`outputs/pm_v1_5_paper1_p1b_actual_rank1_final_audit_20260810/report.json`；冻结 artifact SHA256 为
`e70187b9dadc9e0c4b5e3e627ebe3d3cfb7bb1c78e86c716c59f1158bce47ae5`。

P2A 终审为：
`outputs/pm_v1_5_paper1_p2a_suitability_packet_final_audit_20260810/report.json`。

下一步只设计 P2B 双 reviewer 的固定 endpoint/schema、独立乱序 call plan、逐调用 ledger、transport-only
恢复上限、费用上限和 pre-adjudication agreement analyzer。新的 phase manifest 通过前不得发 reviewer
调用；在 suitability 资格通过前不得创建 safe-yield 标签、生成回复、训练 PM 或读取 external outcome。
