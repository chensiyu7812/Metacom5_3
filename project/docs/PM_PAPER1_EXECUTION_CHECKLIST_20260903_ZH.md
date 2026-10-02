# Paper-1 当前执行清单（2026-09-03）

状态：`ACTIVE WORKING CHECKLIST — NOT AN EMPIRICAL PASS GATE`

2026-09-17 执行链补齐：[静态资源量校准执行记录](PM_PAPER1_STATIC_AMOUNT_EXECUTION_20260917_ZH.md)。准备包已逐项复核（8 项产物哈希吻合、1,924 条请求逐条按 messages 重算哈希一致、共享 true-OFF 恰为每目标一条）。新增 79（可断点恢复的本地自然结束生成）、80（官方评分执行，默认免费 preflight）、81（回收／完整性审计／k 建议），以及按 upstream 固定 commit 复刻的 QA／Summary 官方 parser（`json-repair==0.52.4` 钉版本旁置，冻结 Generator 环境未改动）。20 项新测试通过，Paper-1 测试子集全绿。**生成 0 条、官方评分 0 次、付费 $0、k* 未选定、formal outcome 与 PM training 仍为 0。**A6000 仍被他项目 KVCacheNet 任务占用（实测空闲 16.7–17.4 GiB < 18 GiB 门槛），设备预检按预期拒绝载入，未干扰这些进程；已挂单实例看守进程，等该卡真正空出后自动续跑生成。拟议 $15 付费评分阶段仍未获批，`--execute` 实测被拒绝。

2026-09-17 继续推进：[裁判测量研究稿与论文图表](PM_PAPER1_JUDGE_MEASUREMENT_STUDY_20260917_ZH.md)已保留；[QA／Summary 校准包](PM_PAPER1_STATIC_AMOUNT_CALIBRATION_PACKAGE_20260917_ZH.md)已具体到 85 QA＋63 Summary、1,924 条完整生成请求、官方模板及选量代码。相关 20 项测试和四个官方提示对照通过。A6000 当前运行其他项目任务，未启动新生成或评分、未选择 k*。评分成本情景约 $7.85／$13.27／$24.21，拟议含重试 $15 阶段尚未授权；这些不是输出长度上限。

2026-09-17 本地比较已收口：480 次三候选比较、160 次 Selene 格式适配、156 次完整历史 Summary 对照及 26 次 Generator 自然结束均完成处理；计划内 821 次正常停止、1 次循环超时。Qwen 换序 70/80，Compass 55/80，Selene 适配后 48/77（另 3 对缺失）。本地开发优先 Qwen，但尚不单独承担全任务自动收益标注；[完整结果](PM_PAPER1_LOCAL_TEACHER_DEVELOPMENT_RESULTS_20260917_ZH.md)及[机器收口](../data/paper1_authority/paper1_local_teacher_development_closeout_20260917_v1.json)。新增 API $0，保守 GPU 生成墙钟约 3.02 小时；formal outcome / PM training 仍为 0。

2026-09-17 后续执行：研究者已授权务实开发、三款本地裁判和自然结束，不再重复申请该范围。Summary 26 条自然结束诊断完成，旧 12 条截断均消除，旧 14 条正常回复逐字保持；[结果](PM_PAPER1_SUMMARY_NATURAL_END_RESULTS_20260917_ZH.md)。已物化 QA/Summary 的 20,176 条 top-k 全量候选配置用于工作量盘点，[准备记录](PM_PAPER1_TOPK_PREPARATION_20260917_ZH.md)。新的正式校准样本、收费调用和 k* 尚未确定。开发样本可读可复用，不再强制“完全未触碰”或整批剔除 97 个关联目标；普通分组交叉拟合与运行时 gold/future 排除保留。

2026-09-17 更新：已按研究者 `$0.10` 批准完成 Gemini 96 题资格测试：100 次物理调用、92 个有效判决、4 个解析失败，保守记账 `$0.0654614`；累计 `$1.50724291`、剩余 `$48.49275709`。该配置不提升为 material-effect teacher，执行现有 V3 weak-teacher fallback；[完整结果与后续边界](PM_PAPER1_GEMINI_QUALIFICATION_RESULTS_20260917_ZH.md)。A/AI B/六题复核和原始请求保留，不重做人评；Summary equivalent 分支已修复；四把 outcome lock 仍关闭，formal outcome / PM training 均为 0。

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

7. [x] 已校验并封存 V2 原始 A、AI B 和六题复核。按实际流程记录联合人评 A，原始/人工复核/助手事实敏感性分开报告；AI B 只作探索比较。192 份独立 primary judgments 是原设计，不能冒充实际完成数量；不新增人评。
8. [x] 已生成并保留新版 teacher human reference 空白卷及离线表单：80 个基础语义 pair + 16 个反序 presentation = 96 个 blinded pair presentations（ESC 32、QA 16、Summary 16、DG 32）。原独立双人设计及试卷留作来源记录，实际提交与用途见第 7 项；不复用旧 24 条 absolute-score 样本冒充 pairwise reference。
   - [x] 已 outcome-blind 冻结 80 个 base identity 与 96 个 presentation/blind key；覆盖 ESC 27、QA 13、Summary 13、DG 27 个 base pair，16 个 reverse 不新增生成。ON 使用 `k∈{1,2,4}` 的 qualification probe，只覆盖候选 teacher 的低/中/高输入形态，不是 final amount 选择。53 个 ESC/QA/Summary ON/OFF 请求已精确构造；DG 采用 9 个 scenario cluster × MP/ME/MS，其中 `p7::dg::1` 复用已有 identity-matched first-turn seeker，每个 scenario 共用 seeker 与 OFF，避免无意义的付费重复和跨 head 生成噪声。执行前预算为 39,640 input tokens + 至多 480 output tokens，最坏估计约 `$0.1039`、授权 ceiling `$0.11`；此处仅记录冻结的 preflight，实际执行见下一项。
   - [x] 研究者已授权 `$0.11`；8/8 个冻结 GPT‑4o seeker 请求均首试 `stop`，实际 39,648 input + 221 output tokens，结算 `$0.1013300`，无重试/失败/evaluator。随后在 UUID 强绑定 A6000 上完成 142/142 个唯一 local Generator 请求，80 个 base pair 均有恰好一个 OFF 与一个 ON；双人各 96 题的同 A/B、独立题序 blind sheets 已生成并 hash-bound，现只待两名人类独立填写。
   - [x] 2026-09-08 研究者授权修订 DG 证据缺口：V2 提供九个情境的完整 strict-past raw history、日期索引和字面搜索；63 个 DG candidate instances 的来源均包含在新参考中。保留题目/回复/顺序/盲法、旧 V1 字节及已有生成结果。两份离线 HTML、规范 JSON 和各自独立分发 ZIP 已生成并 hash-bound；同版 96 个精确 Gemini 请求已离线构造，新增生成、付费调用、formal outcome 和 PM training 均为 0。
9. [x] 在收集主评/Gemini verdict 前绑定 Gemini Flash‑Lite 的精确 model、provider route、prompt、parser、temperature、thinking、重试与费用上限：Google Gemini API `gemini-2.5-flash-lite`，metadata version `001`，temperature=0、thinkingBudget=0、strict JSON 四类 parser、最多一次有界重试、qualification hard cap `$0.10`。2026-09-08 identity V2 绑定扩充后的 DG rubric/reference，落实重复 JSON 字段拒绝；不把本次经过回复内容审计的修订称为完全未见生成文本。Claude 只可在同一既有 cap 内替代 Gemini，不得再做一套全量并行判卷。该 freeze 本身不授权付费调用。
10. [x] 完整报告 Gemini task-wise agreement、order stability、equivalent recall、位置描述、解析与费用：有效 base 77/80；与原始 A 相同 7/77；翻转一致 8/13，3 组缺失。16 组反序原始字节全部核验；未以 ON 数量或 PM 表现选 teacher。
11. [x] 当前 Gemini V2 不提升为正式 teacher；按 V3 原有 fallback 仅使用官方 primary anchor 可识别的 effect，tie/conflict/连续量实质性未明案例保留 uncertain。新版本地裁判与提示可按研究者授权开发，保存修改理由与各版本结果；同卷结果按开发证据报告。Summary/DG 在可靠 pairwise 确认建立前，训练覆盖与对应主张保留限制；官方质量驱动的 amount calibration 可并行准备。

已授权本地裁判比较与自然结束诊断已完成，top-k 全量候选盘点已完成；下一步确定可承受的官方质量校准样本与实际调用清单，再选择 k*。Summary/DG 实质性判断仍作为测量限制单列，不增加无关推进门，不继续无边界扩展小模型名单。

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

- Pairwise teacher 的冻结 96 题已运行并收口；本候选不提升，AI B 不自动替代。模型/请求/原始参照和全部尝试记录保留。
- 现有人评按联合 A 与单列复核/敏感性记录，无需新卷；192 独立 primary judgments 留作原设计而非实际完成数。
- Mistral arm-balanced schedule 算法已冻结；精确 formal request manifest/hash 在正式系统输出存在后、formal scoring 前冻结。
- Reference-client 本地 Generator-path runner、A6000、权重、chat template 与 pilot manifest 已绑定；正式 allocator-eligible 测量仍须补齐 RS/DG、full pipeline 与 repeats。Browser surface 如进入论文，需另绑实际 browser runner，不得从 localhost trace 推断。
- Gemini V2 的旧离线估价已被 96 次官方 token 计数与本次实际尝试记录补充；预算采用保守记账，缓存折扣估计与最终账单分开。后续付费或 calibration 仍须新的具体 manifest 与对应授权。
- 可选的 exact task-specific p95 TTFT/completion budgets：只有在主张某个具体部署场景时才需冻结；completion 必须 `< 60,000 ms`，不得用 capability outcome 选择。

其中 teacher 与测量 runner 是复现身份；更紧的 task budget 是部署情景参数，不是研究本体的推进门。ontology/candidate 重建、public census、UI、instrumentation、timing pilot 与 dry-run 均可继续推进。
