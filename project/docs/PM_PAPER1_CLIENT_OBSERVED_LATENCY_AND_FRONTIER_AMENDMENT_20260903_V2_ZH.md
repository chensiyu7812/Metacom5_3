# Paper-1：客户端实测端到端延迟与 Quality–Latency Frontier 修订（2026-09-03 V2）

状态：`ACTIVE / RESEARCHER-AUTHORIZED SCOPED PRE-OUTCOME AMENDMENT`

机器合同：

- `project/data/paper1_authority/paper1_client_observed_latency_and_frontier_amendment_20260903_v2.json`
- `project/data/paper1_authority/paper1_client_latency_measurement_contract_v2.json`

研究者明确批准将 Paper-1 的 latency 进一步对齐真实文本部署体验：从用户发送一条消息开始，到客户端看到首个非空文字与完整回复为止；同时避免把项目自设的单一秒数变成决定论文成败的经验性硬门。

## 1. 对 V1 的 scoped precedence

本 V2 仅覆盖 2026-09-03 V1 latency amendment 的以下条款：

1. V1 从“冻结可见 state 进入 PM runtime”开始计时，只能表示 backend/system latency；V2 primary 从客户端 send event 开始。
2. V1 将未填写的 task-specific TTFT/completion SLA 写成 formal operating-point blocker；V2 撤销该 blocker。
3. V1 的 hard latency feasibility 改为：只对研究者明确声明的 `60,000 ms` 完成时间 catastrophic ceiling fail closed；更紧预算是预冻结 deployment scenario/sensitivity，不是 Paper PASS gate。
4. V1 的 latency-constrained threshold surface扩展为 official quality–client-latency frontier。

V2 不改变 pure quality-effect label、official scorer、public-only、Route A、strict-past、cross-fitting、Generator identity、五类 effect outcome、matched-random、formal outcome locks或任务主张边界。

## 2. Primary 用户延迟

同一个 reference client/browser monotonic clock记录：

```text
T0 = 用户/自动化客户端触发 send，且任何 PM、检索、prompt packing 尚未开始
T5 = 第一个非空、用户可见的文本 token/chunk 已进入客户端展示面
T6 = 完整规范化文本 response 已进入客户端展示面

Client E2E TTFT       = T5 - T0
Client E2E Completion = T6 - T0
```

论文 latency primary cost outcome：`p95 Client E2E Completion`。

体验 guardrail：`p95 Client E2E TTFT`。

如果当前 runner 没有浏览器 UI，只能声称 `reference-client-observed text E2E`：T5 是客户端收到首个非空 content，T6 是客户端获得完整规范化文本。以后由真实浏览器/Playwright从 send event 到 DOM render-ready测量时，才称 `browser send-to-render E2E`。两种 surface 不得混合汇总或改名冒充。

## 3. 组件诊断，不替代 primary

每次 call 以 trace ID连接下列本机 duration：

- client → backend ingress；
- backend ingress → PM start；
- PM feature/decision；
- retrieval/embedding；
- resource render/packing；
- provider request → first non-empty content；
- provider request → final content；
- backend final → client final/render-ready；
- inter-token latency、input/output tokens、retry、finish、timeout/fallback。

跨机器绝对 timestamps 不直接相减；client E2E 必须由同一 client monotonic clock闭合。服务器时间只用于诊断。

ESC-RANK、GPT-4o evaluator、Mistral observation scorer、人类判卷与任何 offline post-processing 均不属于用户响应路径，不进入 latency。

## 4. 波动是部署属性，不是要删除的脏数据

- 固定 model/route/version、client region、runner commit、streaming、prompt、decoding/output limit、connection reuse与并发/load mode。
- 同一 task/time block 内随机交错 arms；禁止先跑完一种 arm 再在另一时间段跑另一种。
- latency repeats 是共享服务与网络的真实随机观测；相同 deterministic content 仍不得冒充独立 quality outcomes。
- primary 使用 warm steady-state；cold start另报，不混合也不删除。
- timeout、retry、fallback保留并计 SLA/ceiling violation；禁止 complete-case-only latency。
- 每次 formal generation都记录 raw latency；primary p95从 raw per-call samples计算，不从 state means计算。
- 按 target与time block做 clustered/bootstrap uncertainty；按 task/arm分别报告 p50、p90、p95、max、timeout/fallback rate。
- concurrency=1 的 controlled comparison与预声明 offered-load stress必须分表；没有真实 load model时不声称多用户生产容量。

## 5. 输出长度不是应从 primary 中消掉的混杂

用户确实需要等待完整输出，所以 Client E2E Completion保留实际 response length影响。output tokens、ITL和固定-token milestone latency只作诊断，解释差异来自 PM/retrieval、prefill、排队、网络还是更长生成；不能用 token-normalization替换主端到端结果。质量 scorer负责防止通过截短回复获得虚假低延迟。

## 6. 研究主分析：不用一个任意秒数决定成败

每个 task/head/arm同时报告：

1. official quality outcome及 clustered uncertainty；
2. Client E2E Completion/TTFT distributions；
3. paired/interleaved latency differences；
4. resource ON rate、tokens/API cost与 timeout；
5. quality–latency frontier：同等/one-SE quality下谁的 p95 completion更低，以及相同预声明 latency budget下谁的 official quality更高。

禁止构造 `Quality - lambda * latency`、跨 task composite或二元 Paper PASS/FAIL。

PM 的主要效率论证是：相对 Fixed-High/Always-On/Matched-Random，在保留或改善 official quality的同时，减少不必要资源打开并降低真实客户端等待；相对 R0+M0若增加了必要延迟，则必须由可分辨的质量收益与更好的选择位置支撑，不能只写“更快”。

## 7. Ceiling、deployment budget 与 sensitivity

- `60,000 ms` Client E2E Completion 是研究者声明的 catastrophic unacceptable ceiling；达到或超过即 violation。
- 它不是同行公认的通用文本聊天标准，也不是 Paper 能否成立的 gate。
- 更紧的 task-specific TTFT/completion budgets若用于实际 runtime，必须在 capability outcomes前，由 zero-outcome same-stack timing profile与明确部署需求冻结。
- 不冻结更紧预算不阻止 ontology、candidate、effect、PM training或 formal benchmark推进；此时 primary policy只使用 catastrophic ceiling + quality-first one-SE + minimum observed/predicted client latency。
- 预注册 sensitivity可使用完整 latency frontier和 outcome-blind timing anchors；不得事后挑选一个最有利于 Learned PM 的预算。

## 8. Threshold 与 multi-head policy

Primary operating-point顺序改为：

1. 排除 p95 Client E2E Completion `>= 60,000 ms` 的 catastrophic-infeasible candidate；
2. 在其余 candidate中形成 official quality one-SE admissible set；
3. 依次最小化 p95 completion、median completion、p95 TTFT、tokens、ON rate；
4. higher threshold与canonical order处理完全并列。

若另有研究者冻结的更紧 deployment budget，它只产生一个明确命名的 deployment-scenario operating point及 sensitivity结果，不覆盖上述 Paper primary。

RQ2 multi-head allocator默认使用 catastrophic remaining budget；若报告更紧 budget，必须带 budget/profile identity。它继续是 first-order allocation，不声称 interaction-aware/global optimum。

## 9. 当前状态与下一步

- formal outcome calls：0
- PM training runs：0
- 本修订 paid API calls：0
- 四条 calibration/confirmatory locks：`CLOSED`

立即实施：更新 authority/config/contracts/tests；建立 reference-client timer与随机交错 schedule schema；随后与已纠正的 MP/MS/ME candidate重建并行推进。实际 latency evidence在后续真实 generation calls上采集，不为“过门”反复修改 evaluator或 ontology。

## 10. 外部定义边界

NVIDIA NIM/AIPerf将 TTFT定义为 query submission到首 token，将 E2E request latency定义为请求到末 token，并明确网络、queueing与batching会进入服务观测。本研究在此基础上把边界外扩到 client send/render-ready：

- https://docs.nvidia.com/nim/benchmarking/llm/latest/metrics.html
- https://docs.nvidia.com/aiperf/dev/reference/ai-perf-metrics-reference

关于可接受秒数，既有研究显示场景和任务依赖，不能为 Paper‑1 提供一个可直接移植的通用文本 SLA：

- https://doi.org/10.1145/3719160.3736636
- https://doi.org/10.1145/3772318.3790716
