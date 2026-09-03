# Paper-1 当前执行清单（2026-09-03）

状态：`ACTIVE WORKING CHECKLIST — NOT AN EMPIRICAL PASS GATE`

本清单只管理依赖与产物，不以项目自设准确率、agreement、precision 或 head-count 门决定研究“通过/失败”。除机械完整性、泄漏、身份、预算与正式 outcome lock 外，测得的好坏均作为研究结果保留。

## 已完成：本轮方法与实现纠偏

- [x] 区分纯 `quality effect` 与部署 `action-worthiness`；Cost/latency 不进入质量 label/loss，但 p95 TTFT/完成时间约束最终 ON/OFF。
- [x] 将 threshold 主规则改为：60 秒灾难性 client completion 上限 → official quality one-SE → p95/median client completion → p95 client TTFT → tokens → ON rate。
- [x] 实现 RQ2 MP/ME/MS 多头 latency allocator；只考虑 mechanically eligible 且 threshold-positive 的 head，不声称 interaction-aware global optimum。
- [x] 将主时间边界冻结为同一客户端单调时钟的 `send→first-visible text` 与 `send→final-visible text`；后台 PM/检索/Generator/render 分段只作诊断。
- [x] 区分 `reference_client_received_text` 与 `browser_render_ready_text` 两个测量面，禁止混报或改名；离线 evaluator 耗时不算用户延迟。
- [x] 允许记录超过 60 秒与 timeout/fallback 的坏样本；60 秒仅为研究者声明的灾难性完成上限，不是普适行业 SLA 或论文二元过门线。
- [x] primary p95 改为从 raw per-call wall-clock samples 计算，禁止 `p95(state means)`。
- [x] 冻结波动控制：task/time-block 内随机交错各 arm，warm 为主、cold 分开，controlled concurrency=1 与 offered-load stress 分开，按 target/time block 聚类 bootstrap。
- [x] 输出长度造成的等待保留在 primary completion latency；ITL、固定 token milestone 与 token-normalized latency 只作诊断。
- [x] 冻结 official-quality/client-latency frontier；禁止 `quality - lambda × latency`、跨任务自设 composite 和二元 Paper PASS/FAIL。
- [x] 撤回 QA/Summary/DG 所有指标等权、任意 epsilon、全同向 Pareto 的旧 effect coding。
- [x] 实现 task-specific hierarchy：ESC Overall + Empathy/Information guards；QA semantic judge primary；Summary Event F1 primary；DG local relevant-observation utilization + pairwise correctness/non-harm。
- [x] 实现 effect correctness 与 latency-constrained action correctness 的分开报告。
- [x] 写明 ordinary-turn 判卷标准：更多共情、记忆、个性化、建议或策略语言本身不加分；无必要干预可判 equivalent/OFF-better。
- [x] authority/config/integration validator 对齐；formal outcome、PM training、paid API、formal GPU 调用均未由本轮打开。

## 下一阶段：不读取 capability outcome 的准备工作

1. [ ] 按已纠正的 MP/Profile、MS/cross-session continuity、ME/action→observed-outcome 定义重建 formal candidate/compiler contracts；v7/v8/v9 只保留 DEV provenance，不再作为“必须过 precision gate”的 formal 入口。
2. [ ] 对 401 public sessions 重建 strict-past candidate pools、coverage、collision、token 与 source-lineage census。
3. [ ] 固定 global packing、overflow、resource token caps 与 task-specific prompt wrappers；Step2 不得在分配后擅自 reroute/drop。
4. [ ] 生成 public-only Natural-turn Appropriateness sample：RS 来自 ESConv ordinary turns，memory 来自 EvoEmo ordinary historical turns；按 user/session grouped、strict-past、observable-only strata抽样。
5. [ ] 建立 reference client raw timing profiler；在冻结 provider/model/prompt/streaming/output-limit/region/connection-reuse stack 上记录同一客户端 monotonic clocks、tokens、retry/finish，不读取 response capability score。
6. [ ] 做 zero-outcome timing pilot，确认采集可靠性、重复次数与 time-block 设计；如存在具体产品目标，再向研究者提交严格低于 60,000 ms 的命名部署场景预算。没有更紧预算不阻塞论文主研究。

## Measurement work：人评与 pairwise teacher

7. [ ] 完成当前研究者正在进行的人评并按 blind item identity ingest；原始 disagreement 必须保留。
8. [ ] 生成新的 96-pair human reference（ESC 32、QA 16、Summary 16、DG 32；两名独立 rater；20% reverse duplicates），不复用旧 24 条 absolute-score 样本冒充 pairwise reference。
9. [ ] 在任何 pair outcome 前绑定 Claude/Gemini/official-anchor candidate teacher 的精确 model、provider route、prompt、parser、temperature、重试与费用上限。
10. [ ] 以人类 reference 的 task-wise agreement、order stability、equivalent recall、position bias、parse reliability 与 cost完整报告候选；不以“产生更多 ON”或“让 PM 分数更好”选 teacher。
11. [ ] 若 teacher 较弱，不循环修门：缩窄可识别 label 范围，tie/conflict 保留 uncertain，并收缩相应 claim。

## Calibration、训练与正式评价

12. [ ] 在相应 calibration lock 获得独立授权后，选择 RS/memory amount；held-out dose-response 只支持 secondary diminishing-return claim，不反向改变 k*。
13. [ ] 生成独立-state、focal-head-only ON/OFF pairs；相同 deterministic response 不伪装成独立 repeats。
14. [ ] 保存 raw official metrics、pairwise verdict、order stability、五类 effect 与每次 client raw latency/cost trace；timeout/retry/fallback 不得 complete-case 删除。
15. [ ] 训练四个 standardized L2 heads，产生 grouped OOF / outer-training-inner-OOF probabilities。
16. [ ] 用新 v3 threshold protocol选择 head/task/fold operating points：先排除 p95 client completion ≥60 秒，再做 official-quality one-SE 与 client latency tie-break；同时保留 fixed-0.5、always-on、always-off references。命名部署场景只作附加报告。
17. [ ] 冻结 checkpoints、thresholds、multi-head allocator inputs、matched-random schedule 与 API call plan。
18. [ ] 运行 sealed local decision-correctness audit；结果不回流训练或 threshold。
19. [ ] 只有完整 stack 冻结后才打开 confirmatory locks，运行 RQ1 ESC-Eval 与 RQ2 ES-MemEval official end-to-end arms、component-minus 与预注册 secondary analyses。
20. [ ] 按 task/head 报告 official quality、effect correctness、action correctness、natural-turn restraint、client TTFT/completion、paired interleaved latency differences、quality-latency frontier、tokens/API cost、coverage、uncertainty与 failures；禁止跨任务自设 composite 或二元 Paper PASS/FAIL。

## 当前仍需冻结的真实身份与可选参数

- Pairwise teacher 精确 identities：必须在读取 96-pair outcomes 前绑定。
- Reference-client/browser surface 的实际 runner 与环境 manifest：必须在正式计时前绑定。
- 可选的 exact task-specific p95 TTFT/completion budgets：只有在主张某个具体部署场景时才需冻结；completion 必须 `< 60,000 ms`，不得用 capability outcome 选择。

其中 teacher 与测量 runner 是复现身份；更紧的 task budget 是部署情景参数，不是研究本体的推进门。ontology/candidate 重建、public census、UI、instrumentation、timing pilot 与 dry-run 均可继续推进。
