# Paper‑1 V2.1 一次性一致性修订（2026‑09‑03）

状态：`ACTIVE PRE-OUTCOME CONSISTENCY REPAIR`。本修订修复构念与实现错位，不新增经验性 PASS gate；formal outcome=0、PM training=0，四把 outcome lock 继续 CLOSED。

## 结论

网页版复核提出的六点中，ontology、threshold quality、timeout/fallback、latency microblock 和 pre-call latency prediction 均为真实问题或缺口。ESC guard 的担忧需要澄清而非改成另一套规则：当前实现已经允许 Empathy/Information 持平；其 guard 只阻止至少一个 ordinal point 的反向下降，不奖励“更多共情/建议”。Natural-turn blinded pairwise appropriateness 继续判定简短克制回复是否更合适。

## 官方证据与研究边界

固定上游为 `slptongji/ES-MemEval` tag `v1.0.0` / commit `692624208acc077b8867698c1d6fcd998dee641a`。官方公开结构分别含 `basic_info`、`event_experience` 与 `dialog_history`；官方 `SessionWiseMemoryInplaceStrategy.record_session` 将完整 session 的逐 turn 文本拼成一个 `Document`。ES‑MemEval 没有把 MP/ME/MS 定义为其官方 taxonomy，因此论文必须说这是本研究的 Multi‑View decomposition，而不是“官方三类 memory”。

唯一 active ontology：

- MP：target-time Current Profile View，仅稳定、slot-like 的当前事实；旧值留 provenance，但不与新值一起作为 current candidate。
- ME：strict-past Atomic Event/Experience Timeline，包含事件、阶段状态、变化、经历、coping/support experience；action→observed outcome 只是一个 subtype。
- MS：一份完整 strict-past raw Session transcript；不由 semantic extractor 生成 event atoms，不读取 dataset summary/observation。

旧 `semantic_memory` v7/v8/v9 明确为历史 DEV provenance，不再生成新 401/census/amount/effect artifact。

## Threshold V4

每个 OOF calibration row 同时保存 ON/OFF 的 task-specific official primary quality，并规范到 [0,1]：ESC Overall/4、QA LLM-as-Judge/2、Summary Event F1、DG Weighted Score。每个 candidate threshold 先模拟自己选择 ON 还是 OFF，再取被选 arm 的官方主质量，按最高层 cluster 计算均值与 SE。

one-SE 的输入只允许这条 official-quality surface。Oracle decision correctness、correct-ON recall、correct-OFF specificity、unnecessary-open 与 missed-benefit 另行报告，不得再把 oracle agreement 命名为 `mean_quality`。Confirmatory 或 held-out outer-target outcome 不得参与 threshold 选择。

## Client Latency V3

- Primary clocks 不变：client send→first-visible 与 send→final-visible。
- terminal timeout/incomplete 不删除，并以 60,000ms floor 分析。
- successful fallback 保留实际用户等待时间；fallback rate/reason 单列，禁止人工改写成 60,000ms。
- 每个 target/repeat 是一个 microblock，arms 在其中随机顺序紧邻执行；target microblocks 的顺序再随机。
- zero-outcome timing profiler 生成 `task × head × context-token-bin × resource-token-bin` 的 paired incremental p95 lookup。当前请求行动前查询；本次 realized post-action latency 永不反向决定本次动作。

## 不再反复修改的边界

除非发现 leakage、identity mismatch、机械实现 bug 或与 pinned official benchmark 的明确冲突，不再修改研究本体。Teacher agreement、label prevalence、PM accuracy、effect size、compiler coverage 与 natural-turn结果都是需要报告的 evidence，不是用来反复修到通过的门。

下一执行链固定为：active Multi‑View extractor/runtime → 401 candidate census → global packing/amount surfaces → teacher/reference → authorized amount calibration → paired effects → L2 heads → OOF threshold V4 → sealed decision audit → confirmatory official benchmarks。
