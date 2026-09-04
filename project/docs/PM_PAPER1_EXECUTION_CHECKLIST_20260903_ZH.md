# Paper-1 当前执行清单（2026-09-03）

状态：`ACTIVE WORKING CHECKLIST — NOT AN EMPIRICAL PASS GATE`

本清单只管理依赖与产物，不以项目自设准确率、agreement、precision 或 head-count 门决定研究“通过/失败”。除机械完整性、泄漏、身份、预算与正式 outcome lock 外，测得的好坏均作为研究结果保留。

## 已完成：本轮方法与实现纠偏

- [x] 区分纯 `quality effect` 与部署 `action-worthiness`；Cost/latency 不进入质量 label/loss，但 p95 TTFT/完成时间约束最终 ON/OFF。
- [x] 将 threshold 主规则改为：60 秒灾难性 client completion 上限 → official quality one-SE → p95/median client completion → p95 client TTFT → tokens → ON rate。
- [x] 修订 RQ2 MP/ME/MS primary allocator：只考虑 mechanically eligible 且 threshold-positive 的 head；完整 bundle 可行则全开，发生预算碰撞则全部 optional memory fail closed并单列 collision。禁止以跨 head `(p-threshold)/latency` 作为 primary utility。
- [x] 将主时间边界冻结为同一客户端单调时钟的 `send→first-visible text` 与 `send→final-visible text`；后台 PM/检索/Generator/render 分段只作诊断。
- [x] 区分 `reference_client_received_text` 与 `browser_render_ready_text` 两个测量面，禁止混报或改名；离线 evaluator 耗时不算用户延迟。
- [x] 拆分 terminal timeout/incomplete 与 successful fallback：前者保留并按 60 秒 floor 分析，后者保留真实 client E2E latency；fallback rate/reason 单列。
- [x] primary p95 改为从 raw per-call wall-clock samples 计算，禁止 `p95(state means)`。
- [x] 冻结波动控制：每个 target/repeat 内 arms 随机顺序且紧邻形成 microblock，再随机 target microblock 顺序；warm 为主、cold 分开，controlled concurrency=1 与 offered-load stress 分开。
- [x] 输出长度造成的等待保留在 primary completion latency；ITL、固定 token milestone 与 token-normalized latency 只作诊断。
- [x] 冻结 official-quality/client-latency frontier；禁止 `quality - lambda × latency`、跨任务自设 composite 和二元 Paper PASS/FAIL。
- [x] 撤回 QA/Summary/DG 所有指标等权、任意 epsilon、全同向 Pareto 的旧 effect coding。
- [x] 实现 task-specific hierarchy V2：ESC Overall primary且七维完整报告，Empathy/Information 单独下降 1 分不再自动 veto；QA semantic judge primary；Summary Event F1 与 DG local utilization 的方向性连续差值必须由 pairwise 确认其 materiality。明确 pairwise equivalent 不得被微小方向性指标覆盖。
- [x] 修正 threshold surface：official-quality one-SE 使用 policy 实际选择 arm 的 task-specific official primary quality；oracle decision correctness 单独报告。
- [x] 建立 outcome-blind pre-call latency lookup contract：`task × head × context-token-bin × resource-token-bin` paired p95 estimate进入 runtime allocator，禁止用本次 post-action latency倒推动作。
- [x] 实现 effect correctness 与 latency-constrained action correctness 的分开报告。
- [x] 写明 ordinary-turn 判卷标准：更多共情、记忆、个性化、建议或策略语言本身不加分；无必要干预可判 equivalent/OFF-better。
- [x] authority/config/integration validator 对齐；401-session compiler 已在研究者授权预算内运行；formal outcome、PM training 与 formal GPU outcome 调用仍为 0。
- [x] 完成 2026-09-04 repository stabilization：AGENTS/current config 提升 Pre-Effect、Latency V2、Effect V2、Teacher V2 与 DG/Mistral schedule；旧 semantic v7-v9 和 V3 仅留 provenance，不再由 routine CI 重开。mixed historical/current tests 已拆分，当前 1427/ESC-overlap/RS-Top8 identity 继续 blocking。
- [x] 冻结 Paper‑1 scope：四个 L2 heads 预测 task-defined material positive effect 的概率；不声称逐请求 effect magnitude、expected utility、动态 top‑k、16-action/global sequential optimum，这些留作后续 magnitude/bandit/RL 研究。
- [x] 冻结 cost-neutral secondary：只复用已有 paired/OOF/sealed rows，按 task×head 报 Benefit Capture、harmful-open、net selected gain 与 local regret；禁止跨任务 ΔQ composite，也不为 secondary 新增 API 调用。
- [x] 建立所有付费 LLM API 累计 USD 50 hard cap（目标 `$25–35`、`$43` 停 optional、至少 `$5` retry reserve），并将 v9 `$0.03079930` 纳入账本。
- [x] 实现 provider-agnostic append-only 累计 API budget ledger：中断 reservation 按最坏费用占账、正常调用保留 `$5` retry reserve、同一成功 call hash 禁止二次付费、每个 logical call 最多一次 retry。
- [x] 处理 Generator 外部退役事件：NVIDIA 目录已无冻结的 `meta/llama-3.1-8b-instruct`，一次精确请求返回 HTTP 410 且未重试；在 formal outcome=0、PM training=0 时版本化迁移到本地 A6000 BF16 backend。四个 safetensors 分片逐字节匹配 Meta 官方仓库 LFS SHA-256，实际本地 chat template 单独 hash-freeze；不声称与旧 hosted NIM 未公开模板或 latency 等价。

## 下一阶段：不读取 capability outcome 的准备工作

1. [x] 建立唯一 active Multi-View contract：MP=target-time Current Profile View；ME=strict-past Atomic Event/Experience Timeline（action→outcome 仅为 subtype）；MS=完整 strict-past raw Session transcript。旧 semantic-memory v7/v8/v9 只保留历史 DEV provenance。
2a. [x] 完成 401 public sessions 的 active MP/ME extraction + factual verification 和无文本 source-lineage/cost/rejection census：18 owners、401 sessions、2236 accepted units（MP 713、ME 1523）、0 grounding rejection、802/802 logical calls 成功；2 次 timeout 均在唯一 retry 恢复；所有 compiler 版本累计 `$1.12641971 < $1.42149913`。另已逐条审计 401+401 success caches、attempt prompts、accepted-unit compiler identity 与 promoted artifact：所有稳定 runtime identity 字段各自唯一，最终产物不混用 V1–V9，故无需重跑。schema/semantic rejection 作为结果保留，不作为推进门。
2b. [x] 用冻结的 401-session closeout 输出重建 target-time strict-past MP/ME/MS candidate pools：1,586 个官方目标的三个 head 均有候选；最终 pool 为 MP 388 / MS 401 / ME 1,523。MP exact owner-slot 388 个，713 条历史 MP 中 325 条被 target-time latest-rank view 正常取代，当前同 rank 冲突为 0。资源长度使用 hash-verified frozen Llama‑3.1 tokenizer：单候选中位 MP 26 / MS 592 / ME 29 tokens；MS 每用户完整池中位 13,177 tokens，因此这里只完成 eligible pool/census，绝不把完整池当作最终注入包，也不因统计结果回改 compiler。已将 401-session 结果提升为可从 GitHub 恢复的 public-data artifact；formal outcome / PM training / 新付费调用均为 0。
3a. [x] 完成 active Multi-View 的本地 BGE‑M3 Top‑8 与 zero-outcome amount surface：QA/Summary 共 4,656 个 target×head 排序；DG 保持每轮当前 seeker utterance 动态重检索，不制造静态 proxy。冻结 `k=0` true-OFF、exact-prefix packing、candidate-id 精确并列规则与 overflow fail-closed；Step2 升为 v2 并修正 MS=完整 raw transcript、ME=广义 atomic event/experience timeline。该 surface 只描述长度/覆盖，不选最终 k/cap，也不是经验门。
3b. [x] 逐文件对照固定的 ES‑MemEval `v1.0.0` commit，绑定 task-specific provider messages：QA/Summary 保留官方 system prompt并把 hash-bound Step2 blocks 放入官方 `Relevant Memory` 段；DG 保留官方 supporter prompt，把 typed blocks 放在官方 `now` 边界之前、当前对话放在之后，每轮请求必须停在当前 seeker turn。DG 只允许 supporter 官方可见的 display name，seeker simulator 的 topic/心理/身体/more_details 不得进入 supporter或 PM。旧 hosted NIM 内部 template 从未可见；退役迁移后，本地 tokenizer、chat template、权重和 serving source 都已 hash-bound，且明确不与旧 hosted latency 混合。
3c. [ ] 在 calibration 设计审阅后冻结 final resource cap，并补齐本地 backend 的 timeout/fallback、完整 PM+BGE+pack E2E、RS/DG timing 与正式重复计划。旧 384-token memory cap 不得继承：active MS 在 k=4 的静态精确资源块最大 3,639 tokens。
3d. [x] 重新逐行审计官方 DG seeker：固定 commit 的 15 个 DG executable 均使用 `gpt-4o` seeker；旧 Mixtral/Qwen fixed-seeker 是历史 controlled extension，不是官方依赖，故不存在 NVIDIA 目录退役 blocker。已冻结 exact prompt builder、隐藏 scenario/supporter 可见性边界、34 scenarios×10 turns×6 systems=2,040 个 seeker 逻辑调用，以及官方每个 non-stop turn 最多三次物理调用造成的费用表。零 outcome 兼容试跑后，按研究者 `$50` 硬预算冻结为一次物理 seeker 尝试：`stop` 直接采用，non-stop 立即执行官方 complete-sentence-prefix 处理并显式记账；本地 greedy supporter 同样只跑一次，因为同一请求三次输出逐字节相同。论文必须称“官方 prompt/roles/rounds/model family/scoring + 明示 one-attempt cost amendment”，不得声称 bit-exact upstream execution。
4a. [x] 生成 public-only Natural-turn Appropriateness 零结果抽样框与待审提案：RS frame=11,182 个 ESConv ordinary response opportunities；memory frame=4,061 个 EvoEmo ordinary historical-session opportunities，且每个状态 MP/ME/MS 都有严格过去候选。提案为每头 20 个基础 pair（共 80），每头 4 个 reverse duplicate（共 96 review slots）；memory 三头共享 20 个状态以允许 exact-prompt/seed OFF 复用。抽样仅用可见 turn type、长度、深度、候选可用性与 user/session grouping；无目标 supporter response、gold/effect outcome、判卷或 API 调用。
4b. [ ] 研究者审阅并冻结 Natural-turn 样本量/身份；当前 80+16 明确是 proposal，不得被代码或论文误称为 final。之后才可生成匿名 ON/OFF responses；默认 human-only，不给该 secondary slice 新增付费 LLM judge 预算。
5a. [x] 建立本地 reference client raw streaming profiler：同进程 monotonic send→first-visible / final-visible、tokens、finish、connection reuse、warm/cold 与 response hash 均已记录；回复文本不落盘、不评分。当前 artifact 是预构建 QA/Summary Generator-path pilot，不冒充完整 PM+BGE+pack E2E。
5b. [x] 已完成第二层 full-pipeline pilot：候选向量部署前预载，每个请求在同一客户端 monotonic clock 内重新做 BGE query embedding、MP/ME/MS 三池 ranking、固定 action、packing、请求构造和流式 Generator；21/21 完成，本地 `$0`。其 query+三头 ranking 中位 63.22 ms（51.78–169.05），pack+request 中位 1.78 ms（0.14–12.81）。仍缺训练后 PM、RS、动态 DG、多个 target/length bin 和预冻结正式 repeats，因此 N=2/cell 的 p95 不进入 allocator或论文 claim。
6. [x] 完成 zero-outcome timing pilot：1 cold + 20 warm、单并发、QA/Summary 各 5 个配置、两次随机相邻 microblock repeats，21/21 完成且同配置 greedy response hashes 一致；formal outcome=0、PM training=0、生成文本未保存/判分、有效本地 API cost=`$0`。该 pilot 同时确认 completion 受 prompt prefill 与停止长度共同影响，不能仅按输入 token 单调外推；当前请求的 realized output length 仍禁止作为 pre-action feature。如存在具体产品目标，再向研究者提交严格低于 60,000 ms 的命名部署场景预算；没有更紧预算不阻塞论文主研究。
6b. [x] 完成初始 termination audit：本地 tokenizer 的 EOS 正确绑定 `<|eot_id|>`（128009），server 将同一 ID 传给 generation；两批共 42 calls 中 stop=32、length=10，length 全部集中在 QA/Summary OFF。暂无 EOT 配置错误证据；更广 RS/memory/DG/target 工程样本完成前不冻结最终 256 cap，也不读取回复质量。

## Measurement work：人评与 pairwise teacher

7. [ ] 完成当前研究者正在进行的人评并按 blind item identity ingest；原始 disagreement 必须保留。
8. [ ] 生成新的 teacher human reference：80 个基础语义 pair + 16 个反序 presentation = 96 个 blinded pair presentations（ESC 32、QA 16、Summary 16、DG 32）；两名独立 primary rater 各评全部 96 个，共 192 份 primary judgement。第三人/consensus adjudication 另计；不复用旧 24 条 absolute-score 样本冒充 pairwise reference。
9. [ ] 在任何 pair outcome 前绑定 official-anchor 与 Gemini Flash‑Lite 的精确 model、provider route、prompt、parser、temperature、重试与费用上限；Claude 只可在同一既有 cap 内替代 Gemini，不得再做一套全量并行判卷。96 总数已包含 reverse duplicates。
10. [ ] 以人类 reference 的 task-wise agreement、order stability、equivalent recall、position bias、parse reliability 与 cost完整报告候选；不以“产生更多 ON”或“让 PM 分数更好”选 teacher。
11. [ ] 若 teacher 较弱，不循环修门：缩窄可识别 label 范围，tie/conflict 保留 uncertain，并收缩相应 claim。

当前方法性最高优先级到此结束：除完成 96-pair teacher identity/reference 所必需的实现外，不再优先扩展 latency、simulator 或新门。

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
23. [x] 在 `$0.40` 家族上限内完成 DG retry compatibility：首次运行因 CUDA ordinal 歧义落到 A4500，10/10 轮完成、10/10 paid seeker 首试 stop、费用 `$0.08724`；A6000 零 API 重放 0/10 supporter bytes 相同，因此不伪称硬件等价。随后以 GPU 强绑定新 identity 在 A6000 完成正确轨迹，仍为 10/10 paid seeker 首试 stop，费用 `$0.0859925`。两次合计 `$0.1732325`，无 evaluator/outcome/PM training；错误轨迹只作消耗与工程诊断，不进入正式实验。
24. [x] 已验证本地官方 Mistral‑Small‑3.1‑24B backend：固定 revision `68faf511d618ef198fef186659617cfd2eb8e33a`、未量化 BF16、A6000 + 5 GiB CPU offload、vLLM 0.10.1/cu128。官方 temperature 省略形态的 100+100 条公共历史 observation judgement 均 100% schema-valid 且正常 stop；首轮 2.091 req/s，对 102,720 calls 的稳态外推约 13.64 A6000 小时，prompt 最大 1,925 < 4,096 tokens，峰值常驻显存 48,505/49,140 MiB。重复判值一致率为 48/100，属于官方采样 judge 的实测方差，不是推进门；正式报告必须使用 scenario-level uncertainty，小差异不得写成确定增益。temperature=0 诊断另发现 continuous-batching context 可改变单条判值，而 6 条顺序双重放 6/6 稳定。正式 schedule 算法现已冻结为 matched-unit 内六 arm 相邻、固定 seed 的循环平衡，concurrency=8；pilot 没有显式传 server seed，正式启动必须显式 `--seed 0`。实际 request manifest 与 hash 仍必须在 formal outcome unlock 前持久化，且断点续跑不得 reshuffle。

## 当前仍需冻结的真实身份与可选参数

- Pairwise teacher 精确 identities：必须在读取 96-pair outcomes 前绑定。
- Teacher 的计数单位已冻结为 96 presentations × 2 primary raters = 192 primary judgements；实际 item/sheet identities 尚待生成并 hash-bind。
- Mistral arm-balanced schedule 算法已冻结；精确 formal request manifest/hash 在正式系统输出存在后、formal scoring 前冻结。
- Reference-client 本地 Generator-path runner、A6000、权重、chat template 与 pilot manifest 已绑定；正式 allocator-eligible 测量仍须补齐 RS/DG、full pipeline 与 repeats。Browser surface 如进入论文，需另绑实际 browser runner，不得从 localhost trace 推断。
- Gemini Flash‑Lite 的 exact model revision、provider endpoint、prompt/parser 与单次 worst-case reservation：必须在读取 pair outcomes 前绑定。
- 可选的 exact task-specific p95 TTFT/completion budgets：只有在主张某个具体部署场景时才需冻结；completion 必须 `< 60,000 ms`，不得用 capability outcome 选择。

其中 teacher 与测量 runner 是复现身份；更紧的 task budget 是部署情景参数，不是研究本体的推进门。ontology/candidate 重建、public census、UI、instrumentation、timing pilot 与 dry-run 均可继续推进。
