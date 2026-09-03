# Paper-1 当前执行清单（2026-09-03）

状态：`ACTIVE WORKING CHECKLIST — NOT AN EMPIRICAL PASS GATE`

本清单只管理依赖与产物，不以项目自设准确率、agreement、precision 或 head-count 门决定研究“通过/失败”。除机械完整性、泄漏、身份、预算与正式 outcome lock 外，测得的好坏均作为研究结果保留。

## 已完成：本轮方法与实现纠偏

- [x] 区分纯 `quality effect` 与部署 `action-worthiness`；Cost/latency 不进入质量 label/loss，但 p95 TTFT/完成时间约束最终 ON/OFF。
- [x] 将 threshold 主规则改为：60 秒灾难性 client completion 上限 → official quality one-SE → p95/median client completion → p95 client TTFT → tokens → ON rate。
- [x] 实现 RQ2 MP/ME/MS 多头 latency allocator；只考虑 mechanically eligible 且 threshold-positive 的 head，不声称 interaction-aware global optimum。
- [x] 将主时间边界冻结为同一客户端单调时钟的 `send→first-visible text` 与 `send→final-visible text`；后台 PM/检索/Generator/render 分段只作诊断。
- [x] 区分 `reference_client_received_text` 与 `browser_render_ready_text` 两个测量面，禁止混报或改名；离线 evaluator 耗时不算用户延迟。
- [x] 拆分 terminal timeout/incomplete 与 successful fallback：前者保留并按 60 秒 floor 分析，后者保留真实 client E2E latency；fallback rate/reason 单列。
- [x] primary p95 改为从 raw per-call wall-clock samples 计算，禁止 `p95(state means)`。
- [x] 冻结波动控制：每个 target/repeat 内 arms 随机顺序且紧邻形成 microblock，再随机 target microblock 顺序；warm 为主、cold 分开，controlled concurrency=1 与 offered-load stress 分开。
- [x] 输出长度造成的等待保留在 primary completion latency；ITL、固定 token milestone 与 token-normalized latency 只作诊断。
- [x] 冻结 official-quality/client-latency frontier；禁止 `quality - lambda × latency`、跨任务自设 composite 和二元 Paper PASS/FAIL。
- [x] 撤回 QA/Summary/DG 所有指标等权、任意 epsilon、全同向 Pareto 的旧 effect coding。
- [x] 实现 task-specific hierarchy：ESC Overall primary，Empathy/Information 只作至少一 ordinal point 的 material-degradation guard（不要求上升）；QA semantic judge primary；Summary Event F1 primary；DG local relevant-observation utilization + pairwise correctness/non-harm。
- [x] 修正 threshold surface：official-quality one-SE 使用 policy 实际选择 arm 的 task-specific official primary quality；oracle decision correctness 单独报告。
- [x] 建立 outcome-blind pre-call latency lookup contract：`task × head × context-token-bin × resource-token-bin` paired p95 estimate进入 runtime allocator，禁止用本次 post-action latency倒推动作。
- [x] 实现 effect correctness 与 latency-constrained action correctness 的分开报告。
- [x] 写明 ordinary-turn 判卷标准：更多共情、记忆、个性化、建议或策略语言本身不加分；无必要干预可判 equivalent/OFF-better。
- [x] authority/config/integration validator 对齐；401-session compiler 已在研究者授权预算内运行；formal outcome、PM training 与 formal GPU outcome 调用仍为 0。
- [x] 冻结 Paper‑1 scope：四个 L2 heads 预测 task-defined material positive effect 的概率；不声称逐请求 effect magnitude、expected utility、动态 top‑k、16-action/global sequential optimum，这些留作后续 magnitude/bandit/RL 研究。
- [x] 冻结 cost-neutral secondary：只复用已有 paired/OOF/sealed rows，按 task×head 报 Benefit Capture、harmful-open、net selected gain 与 local regret；禁止跨任务 ΔQ composite，也不为 secondary 新增 API 调用。
- [x] 建立所有付费 LLM API 累计 USD 50 hard cap（目标 `$25–35`、`$43` 停 optional、至少 `$5` retry reserve），并将 v9 `$0.03079930` 纳入账本。
- [x] 实现 provider-agnostic append-only 累计 API budget ledger：中断 reservation 按最坏费用占账、正常调用保留 `$5` retry reserve、同一成功 call hash 禁止二次付费、每个 logical call 最多一次 retry。

## 下一阶段：不读取 capability outcome 的准备工作

1. [x] 建立唯一 active Multi-View contract：MP=target-time Current Profile View；ME=strict-past Atomic Event/Experience Timeline（action→outcome 仅为 subtype）；MS=完整 strict-past raw Session transcript。旧 semantic-memory v7/v8/v9 只保留历史 DEV provenance。
2a. [x] 完成 401 public sessions 的 active MP/ME extraction + factual verification 和无文本 source-lineage/cost/rejection census：18 owners、401 sessions、2236 accepted units（MP 713、ME 1523）、0 grounding rejection、802/802 logical calls 成功；2 次 timeout 均在唯一 retry 恢复；所有 compiler 版本累计 `$1.12641971 < $1.42149913`。schema/semantic rejection 作为结果保留，不作为推进门。
2b. [x] 用冻结的 401-session closeout 输出重建 target-time strict-past MP/ME/MS candidate pools：1,586 个官方目标的三个 head 均有候选；最终 pool 为 MP 388 / MS 401 / ME 1,523。MP exact owner-slot 388 个，713 条历史 MP 中 325 条被 target-time latest-rank view 正常取代，当前同 rank 冲突为 0。资源长度使用 hash-verified frozen Llama‑3.1 tokenizer：单候选中位 MP 26 / MS 592 / ME 29 tokens；MS 每用户完整池中位 13,177 tokens，因此这里只完成 eligible pool/census，绝不把完整池当作最终注入包，也不因统计结果回改 compiler。已将 401-session 结果提升为可从 GitHub 恢复的 public-data artifact；formal outcome / PM training / 新付费调用均为 0。
3. [ ] 固定 global packing、overflow、resource token caps 与 task-specific prompt wrappers；Step2 不得在分配后擅自 reroute/drop。
4. [ ] 生成 public-only Natural-turn Appropriateness sample：RS 来自 ESConv ordinary turns，memory 来自 EvoEmo ordinary historical turns；按 user/session grouped、strict-past、observable-only strata抽样。
5. [ ] 建立 reference client raw timing profiler与 token-bin lookup artifact；在冻结 provider/model/prompt/streaming/output-limit/region/connection-reuse stack 上记录同一客户端 monotonic clocks、tokens、retry/finish，不读取 response capability score。
6. [ ] 做 zero-outcome timing pilot，确认采集可靠性、重复次数与 time-block 设计；如存在具体产品目标，再向研究者提交严格低于 60,000 ms 的命名部署场景预算。没有更紧预算不阻塞论文主研究。

## Measurement work：人评与 pairwise teacher

7. [ ] 完成当前研究者正在进行的人评并按 blind item identity ingest；原始 disagreement 必须保留。
8. [ ] 生成新的 96-pair human reference（ESC 32、QA 16、Summary 16、DG 32；两名独立 rater；20% reverse duplicates），不复用旧 24 条 absolute-score 样本冒充 pairwise reference。
9. [ ] 在任何 pair outcome 前绑定 official-anchor 与 Gemini Flash‑Lite 的精确 model、provider route、prompt、parser、temperature、重试与费用上限；Claude 只可在同一既有 cap 内替代 Gemini，不得再做一套全量并行判卷。96 总数已包含 reverse duplicates。
10. [ ] 以人类 reference 的 task-wise agreement、order stability、equivalent recall、position bias、parse reliability 与 cost完整报告候选；不以“产生更多 ON”或“让 PM 分数更好”选 teacher。
11. [ ] 若 teacher 较弱，不循环修门：缩窄可识别 label 范围，tie/conflict 保留 uncertain，并收缩相应 claim。

## Calibration、训练与正式评价

12. [ ] 在相应 calibration lock 获得独立授权后，选择 RS/memory amount；held-out dose-response 只支持 secondary diminishing-return claim，不反向改变 k*。
13. [ ] 生成独立-state、focal-head-only ON/OFF pairs；相同 deterministic response 不伪装成独立 repeats。
14. [ ] 保存 raw official metrics、pairwise verdict、order stability、五类 effect 与每次 client raw latency/cost trace；timeout/retry/fallback 不得 complete-case 删除。
15. [ ] 训练四个 standardized L2 heads，产生 grouped OOF / outer-training-inner-OOF probabilities。
16. [ ] 用 v4 threshold protocol选择 head/task/fold operating points：先排除 p95 client completion ≥60 秒，再对所选 arm 的 official primary quality 做 one-SE 与 client latency tie-break；decision correctness另报；同时保留 fixed-0.5、always-on、always-off references。
17. [ ] 冻结 checkpoints、thresholds、multi-head allocator inputs、matched-random schedule 与 API call plan。
18. [ ] 运行 sealed local decision-correctness audit；结果不回流训练或 threshold。
19. [ ] 只有完整 stack 冻结后才打开 confirmatory locks，运行 RQ1 ESC-Eval 与 RQ2 ES-MemEval official end-to-end arms、component-minus 与预注册 secondary analyses。
20. [ ] 按 task/head 报告 official quality、effect correctness、action correctness、natural-turn restraint、client TTFT/completion、paired interleaved latency differences、quality-latency frontier、tokens/API cost、coverage、uncertainty与 failures；禁止跨任务自设 composite 或二元 Paper PASS/FAIL。
21. [ ] 仅从已有 grouped OOF/sealed paired rows 计算 task×head magnitude diagnostics：Benefit Capture 必须和 ON rate、tokens、net selected gain、harmful-open/false-open harm 同报；分母无正收益时记 NA；ESC/DG 仅称 one-step/local counterfactual regret。
22. [ ] 每阶段启动前生成 call manifest：settled + reserved + next-call worst-case ≤ `$50`；累计 `$43` 后停 optional；成功 prompt hash 禁止重复付费，transport/parser 最多重试一次，禁止结果驱动重跑。

## 当前仍需冻结的真实身份与可选参数

- Pairwise teacher 精确 identities：必须在读取 96-pair outcomes 前绑定。
- Reference-client/browser surface 的实际 runner 与环境 manifest：必须在正式计时前绑定。
- Gemini Flash‑Lite 的 exact model revision、provider endpoint、prompt/parser 与单次 worst-case reservation：必须在读取 pair outcomes 前绑定。
- 可选的 exact task-specific p95 TTFT/completion budgets：只有在主张某个具体部署场景时才需冻结；completion 必须 `< 60,000 ms`，不得用 capability outcome 选择。

其中 teacher 与测量 runner 是复现身份；更紧的 task budget 是部署情景参数，不是研究本体的推进门。ontology/candidate 重建、public census、UI、instrumentation、timing pilot 与 dry-run 均可继续推进。
