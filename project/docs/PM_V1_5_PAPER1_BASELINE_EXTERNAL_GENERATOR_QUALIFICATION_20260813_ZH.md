# PM V1.5 Paper 1：Baseline、三项外测与 Generator 资格补充

日期：2026-08-13  
状态：`ACTIVE_ZERO_API_QUALIFICATION_ADDENDUM / NO EXECUTION AUTHORITY`

机器合同：

`data/pm_v1_5_contracts/paper1_pm_baseline_external_generator_qualification_addendum_v1.json`

## 结论

Paper 1 的 PM 合格不是“相对 always-off 不伤质量、相对 fixed-high 少用 token”两项即可。完整资格是一个合取条件：

```text
RS_pass
AND count_pass(MP,MS,ME) >= 2
AND system value passes
AND learned modeling value passes
AND state-action selection value passes
AND joint 16-action safety/efficiency passes
AND all three external tracks pass their own task-specific gates
```

`default OFF` 是失败组件的正确安全行为，但不是组件 PASS。`OFF vs OFF` 没有退化，只能证明系统避免继续伤害；它不能证明 selector 非退化、组件做功或 conditional benefit。

## 一、每个 baseline 证明不同问题

### Always-off

证明可选资源是否保留非负系统价值。PM 必须满足：

- Quality NetWin 的 cluster 95% CI 下界大于 `-0.05`；
- Quality 点估计不小于 `0`；
- 每项 material interaction/grounding risk 的差值上界不超过 `+0.05`；
- 冻结 learned-ON 子集的 same-state randomized ITT uplift 点估计为正。

### Fixed-high eligible

证明选择性启用是否以较低资源达到相当结果：

- Quality/Risk 非劣；
- mean generator input tokens 至少下降 `10%`；
- retrieval、retry、output tokens、latency、USD 分开报告；
- 不能靠砍短、不完整回复制造成本优势。

### Transparent rule

证明 learned model 是否比简单规则更有价值：

- Quality、Risk、Cost Pareto 不坏；
- 至少一个预注册 primary selection outcome 严格改善；
- grouped/cross-fitted selector 确实优于 named simple baseline。

如果全线持平，只能说透明规则足够，不能声称 learned PM 有价值。

### Cost-matched fixed

证明动态选择优于同成本固定 bundle：成本误差先控制在 `5%` 内；同成本下 learned PM 必须在 Quality、verified Function 或 material Risk 至少一项严格更好，其余非劣。

### Cost-and-ON-rate-matched random

证明 PM 学到的是 state→action 匹配，而不是只学会少开：

- 每个组件 ON 数完全相同；
- 总注入成本误差不超过 `5%`；
- 至少 `25%` 状态动作不同；
- learned PM 的 Quality 或 beneficial/harmful-ON 选择严格更好，Risk 非劣。

### Component fixed / full-minus-component

每个计入 PASS 的头都必须独立做功，不能搭便车：selector、candidate support、verified Function、same-stack marginal outcome 四项全部成立。

### 16-action safe oracle frontier

- unsafe/structurally-invalid selection 为 `0`；
- deployment-ITT quality regret 在 `0.10` 等价带内；
- safe quality frontier 上 excess deterministic cost 不超过 `5%`；
- oracle-set inclusion、beneficial false-OFF、harmful false-ON 优于 rule 与 matched random。

## 二、三个外部实验分别如何通过

### ESConv：只证明 RS

主条件：always-off、fixed-high、transparent rule、learned RS、cost-matched fixed、cost/ON-rate-matched random。

通过要求：

- MP/MS/ME 必须结构性 OFF；
- learned RS 同时产生 ON/OFF；
- 相对 always-off，整体 Quality/Risk 非劣，learned-ON 子集 uplift 为正；
- 相对 fixed-high，Quality/Risk 非劣且减少无必要 RS 注入；只有 input tokens 真下降至少 `10%` 才能写总输入成本优势；
- 相对 rule 和 matched random，证明 learned state-action selection 的严格价值；
- requested→received 为 `1.00`，RS source-aware Function 必须非零、可归因、可复现；`0.80` 是工程参考目标，不是独立硬门；
- wrong-owner/future/scaffold exposure 为 `0`。

ESConv 不能证明长期记忆或 personalization。

### EvoEmo：证明 RS + 至少两个 memory heads 的联合系统

主条件除六个 policy baseline 外，还包括 RS-only、各单组件 fixed、full-minus-each-component、raw-session Top4、full history、16-action oracle。

通过要求：

- 相对 always-off：Quality/Risk 非劣，Quality 点估计非负，learned-ON ITT uplift 为正；
- 相对 fixed-high：Quality/Risk 非劣，generator input tokens 至少低 `10%`；
- 相对 rule、cost-matched fixed 和 matched random：证明严格的 adaptive selection value；
- RS 与至少两个 MP/MS/ME 分别满足完整 head-pass；
- full versus minus-component 或 component ON/OFF 显示各头的独立 Function/quality-cost contribution；
- requested→received=`1.00`，各头 Function 必须非零、可归因、可复现；single `0.80` 与 multi `0.70` 是工程参考目标，不是独立硬门；
- 16-action oracle 的安全、regret、frontier cost 全部过门。

EvoEmo 的 204 states 不能当 204 个独立样本；统计簇是 18 个 user。当前 OOF 路径是 cross-fitted in-domain evidence，不是 untouched-owner external validation。

### ES-MemEval：证明 memory retrieval/QA/abstention transport

主条件：no-memory、full history、official session-RAG Top4、typed-memory fixed-high、typed-memory learned PM。RS 为 N/A。

通过要求：

- 相对 no-memory，在 answerable memory-required questions 上 Token F1 uplift 的 user-cluster 95% CI 下界大于 `0`；
- 相对 typed fixed-high，Token F1 非劣、BERTScore 方向一致、conflict/abstention/false-answer 非劣，input tokens 至少低 `10%`；
- 相对 official RAG Top4，客观 QA 与 abstention 风险 Pareto 不坏，至少一个 primary outcome 严格改善；
- 相对 full history 形成预注册 accuracy-cost Pareto；
- extraction、temporal、conflict、user modeling、abstention 分别报告，不能用 macro 平均掩盖关键失败；
- wrong-user、future、answer/evidence leakage 为 `0`。

建议在结果打开前冻结 Token F1 非劣 margin `-0.03`、false-answer rate 差值上界 `+0.05`。若有完全分离的 development 波动估计，可在外测前仅替换一次。

三项外测必须分别通过，禁止互相替代或合并成一个 effect size。

## 三、Generator 对比保留，但延后到当前 treatment 成功之后

当前失败不能只归咎于 Llama 3.1 8B。现行 treatment 同时要求：

- RS ON 时是唯一 primary act；
- dominant Restatement 卡只允许一句复述；
- 不提问、不建议、不加第二 move；
- generator 还要输出结构化 trace 并通过 guard。

更强模型可能只是更忠实地执行一个不完整的回复设计。因此本轮先冻结 Llama 3.1 8B，把 treatment 改成 invariant `R0 + optional component deltas` 并通过开发晋级门。成功后，再在全新 development states 上运行以下 generator robustness factorial：

```text
                         Llama 3.1 8B     stronger generator
current treatment             A                  B
repaired treatment            C                  D
```

这个 2×2 回答：

- C、D 都改善：主要是 treatment/compiler 问题；
- 只有 D 改善：generator capacity / instruction-following interaction；
- 强模型绝对回复更好但 PM uplift 仍为零：generator 改善，不代表 PM 有价值；
- 两个 generator 的 PM uplift 都为正：才支持 generator robustness。

Generator 选择必须使用与正式/外测 outcome 分离的开发资格面板。至少检查：schema/transport 成功率 `≥0.95`、wrong-owner/future/scaffold=`0`、source-aware Function 非零/可归因/可复现、current-turn grounding 与 explicit-safety handling。single `0.80` 与 multi `0.70` 只作为工程参考目标。

正式比较中，每个 generator 内部都要跑完全相同的 policy baselines；跨 generator 只估计 generator main effect 和 PM×generator interaction，不能拿“强模型 PM”对“弱模型 baseline”。

如果只有强 generator 通过，论文可以主张“PM 在该冻结 generator 下合格，并揭示 Llama 3.1 8B 的容量/执行边界”，不能主张 generator-agnostic。若 generator 是看完外测结果后才选出的，新结果只能算 exploratory。

## 四、当前执行边界

MS-only 测量已经完成，但原 closeout 把“正向点估计”升级成了“MS 四项全部 PASS”，这个结论过头。核验后应读作：

- 19 对为 12 routed 胜、4 baseline 胜、3 平；pair-level 单侧符号检验约 `p=0.038`；
- 只有 11 个独立 user groups；按组归并为 7 正、2 负、2 平，单侧精确符号检验约 `p=0.090`；
- Risk 是 baseline 3 个非零、routed 0 个，但只有 3 个不一致对，单侧精确值约 `p=0.125`；
- 6/19 为生成器声称使用 MS，13/19 为 `clean_safe_personal_nonuse`；后者贡献 8 个 routed wins。因此这更像“MS treatment/prompt 在 ON slice 上有正向 ITT 信号”，还不能归因为具体记忆事实做功；
- 当前 Function 的独立证据来自此前 RS-confounded treatment 的 5/13 content-following。新 MS-only 19 例没有独立 source-aware Function 复核，generator self-report 不能补这个洞。

所以正式状态是 `MS_ON_SLICE_DIRECTIONAL_POSITIVE_DEVELOPMENT_EVIDENCE`，不是 `MS_pass`。RS default-off 也已经修正为 fail-closed 部署行为，不再把 `OFF vs OFF` 写成 same-stack PASS。

当前零 API generator inventory 显示，项目已具备 Llama 3.1 8B 历史参考以及 Qwen/DeepSeek/OpenAI 等候选接口。按 2026-08-13 官方资料，OpenAI 当前系列是 GPT-5.6（`sol` 能力上界、`terra` 质量/成本平衡），不是优先从 GPT-4o 起步；阿里云当前主推 Qwen3.7-Max/Plus；DeepSeek 当前 API 已进入 V4-Pro/V4-Flash。最稳妥的 primary challenger 是一个非 OpenAI 强生成器（Qwen3.7-Max 或 DeepSeek-V4-Pro），继续让 GPT-5.6 做盲评；GPT-5.6 作为 generator 只能配非 OpenAI/人类 judge anchor，避免同家族偏好。

本补充合同已在测量 closeout 后绑定进 active bundle，但只冻结比较与资格口径，不授权任何 generator、reviewer、fit 或外测调用。
