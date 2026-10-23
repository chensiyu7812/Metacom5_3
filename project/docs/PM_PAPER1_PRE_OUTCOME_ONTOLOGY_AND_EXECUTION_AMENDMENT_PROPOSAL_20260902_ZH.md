# Paper 1 预结果 ontology 与执行链统一修订提案（2026-09-02）

状态：`PROPOSED / INACTIVE / AWAITING EXPLICIT RESEARCHER APPROVAL`

> **PROPOSED RESEARCH CHANGE — NOT AUTHORIZED**
>
> 本文件只提出研究修订，不改变 active authority、compiler、候选集、训练数据、实验 arm 或 outcome lock。未经研究者明确批准，不得把本文件中的定义写入正式运行链。

## 1. 为什么必须现在统一修订

当前尚未产生 Paper-1 formal outcome、正式 ES-MemEval outcome 或 PM training。最近 v7/v8/v9 使用的是同一批反复调试的 DEV 例子，只能说明工程行为，不能证明泛化，也不应继续充当推进正式研究的性能门。

更根本的问题是，仓库同时存在两套互相冲突的 memory ontology：

- `memory/ms.py` 已把 MS 实现为一段完整、严格过去的原始 session transcript；
- active semantic-memory authority、compiler、review UI 和 v7/v8/v9 则把 MS 写成 event/state/change，把 ME 限成 action→outcome。

对 ES-MemEval 论文和 pinned 官方实现的重新核对支持第一种 MS 含义：官方 main RAG 以 **完整 session** 为检索文档，并用 BGE-M3 取 Top-4；论文把 observation、dialogue summary 和 compressed context 留作未探索方向。ES-MemEval 本身并未提出 MP/MS/ME taxonomy，因此 MP/MS/ME 的边界是本项目的方法设计，不能伪装成官方定义。

官方依据：

- ES-MemEval paper: <https://arxiv.org/html/2602.01885>
- pinned session-wise RAG implementation: <https://github.com/slptongji/ES-MemEval/blob/692624208acc077b8867698c1d6fcd998dee641a/src/lib/shared/prompt_strategies/session_wise_memory_inplace_strategy.py>
- pinned public schema: <https://github.com/slptongji/ES-MemEval/blob/692624208acc077b8867698c1d6fcd998dee641a/src/lib/shared/data_provider/raw_seeker.py>

## 2. 本次建议保留的研究核心

研究对象不变：Policy Manager（PM）学习在当前状态下，是否值得向固定 Generator 注入一个已检索的外部资源。

核心原则不变：

> 资源“存在或相关”不等于“此刻注入会改善结果”；PM 学习的是条件效用，而不是资源分类、gold capability 分类或固定 Top-k 模仿。

建议保留两个 domain RQ：

1. **RQ1 / Strategy**：在情感支持生成中，learned RS opening 是否比等开启率/等资源量的随机分配更有效，并相对 R0 与 Fixed-High 呈现怎样的质量—成本权衡？最终能力只由官方 ESC-Eval/ESC-RANK 七维评价。
2. **RQ2 / Longitudinal Memory**：在 ES-MemEval QA、Summarization、Dialogue Generation 中，learned multi-view memory opening 是否比匹配随机分配更有效，并相对 project No-Memory、Full-History-under-cap、official-method RAG Top-4 与 Fixed-High 呈现怎样的质量—成本权衡？最终能力只由 ES-MemEval 官方 task metrics 评价。

资源 amount/dose-response 应提升为**预注册的跨 RQ secondary/mechanism evidence 和主要图表**，但不新增第三个核心 RQ，也不把 Paper 1 改成动态预测 k：

- 它回答“资源量增加时质量和 token/cost 怎样变化”；
- 它帮助在 training folds 内冻结每个资源/任务的 ON bundle；
- 它不是 PASS 门，也不得读取 confirmatory benchmark outcomes 后重新选 k；
- 若数据不足，只报告曲线与不确定性，不宣称“更多一定有害”或“存在最优 k”。

## 3. 拟议的新 ontology

### 3.1 MP — Current Profile View

MP 是目标时点仍成立的、可追溯的用户 profile/state facts，例如身份、职业、地点、稳定关系角色、持续偏好或当前有效状态。

- 默认检索视图只暴露每个 slot 的当前版本；
- 被更正、更新或 superseded 的旧 MP 仍保存在 provenance/history 中，但不继续作为 current MP 注入；
- 版本变化本身可投影为 ME event；
- 不以“扩大数量”为目的保留已失效事实。

### 3.2 ME — Atomic Event/Experience Timeline

ME 是严格过去、用户锚定、时间化的原子事件或经历，包括：

- life/relationship events；
- 状态 onset、change、resolution；
- meaningful experience；
- coping/support/action 以及其 observed outcome。

`action → user-observed outcome` 是重要的 ME subtype，不再是 ME 的唯一合法形态。一次来源可以形成多个彼此独立、各自可溯源的 ME atom，但不得把一句话机械复制到 action 和 outcome 两槽来伪造因果链。

### 3.3 MS — Full Prior Session

MS 是同一用户在当前目标之前的一段**完整原始 session transcript**：

- 保留原始 turn 顺序、角色和 session/date lineage；
- 不使用数据集提供的 observation、gold summary、topic、emotion、question answer 或 future fields；
- MS 是不可变 session 文档，不参与 MP-style 的 slot supersession；
- 检索可以返回 0/1/多段完整 sessions，但候选粒度保持 one full session；
- 若上下文预算无法容纳完整 session，优先采用 whole-session packing 并记录未装入，而不是静默把“截断片段”继续称作完整 MS。极端单 session 超限必须单独标记并报告。

### 3.4 多视图投影与第三方信息

- 同一 source span 可以支持多个视图；这不是 duplication bug，因为各视图的表示和用途不同。
- 每个 emitted candidate 必须只有一个 head/type；不允许同一个 candidate ID 同时属于 MP/ME/MS。
- 接受用户锚定的第三方关系或事件信息，例如“我的母亲住在大阪”“朋友上周帮助了我”；拒绝与用户状态/经历无关的自由漂浮第三方传记。
- “第三方信息全部拒绝”和“第三方信息全部接受”都不成立。

## 4. 名称与 arm 契约修订

论文展示名建议从 `Typed Memory` 改成 `Multi-View Memory`。为减少无价值的代码迁移，现有 `Typed_*` machine enum 可暂时作为兼容 alias，但报告、图表和新 manifest 使用 Multi-View 名称。

RQ2 arms 拟明确为：

1. **Project No-Memory**：同栈、空 memory block。QA/Summary 官方仓库没有单独发布 no-memory script，不能称“官方 No-Memory baseline”；DG 才有官方 no-memory script。
2. **Full-History under frozen context cap**：复现官方 full-history method，但明确报告 16k 输入截断及每行实际可见 session/token 比例，不能无条件简称“全部历史均可见”。
3. **Official-method RAG Top-4 (same stack)**：严格复现 pinned 官方的 BGE-M3、session-grain、Top-4、task-specific query 和 placement；它是官方方法的同栈实现，不宣称复现官方论文的具体数值。
4. **Multi-View Fixed-High**。
5. **Multi-View Matched-Random**。
6. **Learned Multi-View PM**。

`RS fixed in RQ2` 拟正式定义为：**所有 RQ2 arms 的 RS 均为 OFF**。这样 RQ2 只改变 longitudinal memory，避免把 strategy resource 混进 memory contrast。

官方 DG-RAG pinned 实现会把 `beginning_prompt` 放入两次。RQ2 primary same-stack 比较拟在所有 arms 使用一次共同 base prompt，并原样保留官方检索语义；因此名称是 `official-method` 而不是 `bit-exact official runner`。另保留一个小型、明确标注的 upstream-fidelity sensitivity，检查双 prompt 是否 materially 改变结果；它不阻塞主实验。

## 5. amount、token 与 matched-random

旧的统一 384-token cap 不适用于新的 MS 完整 session 语义。拟改为：

- RS、MP、ME 使用各自 compact candidate 的 k-grid 和实际 token 记录；
- MS 使用 session-count grid 和基于 Generator context window 的 whole-session packing；
- 所有 amount 选择只在对应 training/inner folds 内完成，confirmatory fold 不参与；
- 使用少量、预声明的 k 点，按 user cluster 报告 uncertainty，避免 18 users 上高自由度搜索；
- official RAG 永远保持 Top-4，不随本项目 amount calibration 改变。

`Matched-Random` 不再要求每行逐字节“exact token equality”，因为不同候选特别是 full-session MS 常无可行精确匹配。拟使用：

- 同一 head/task/fold 内相同 realized ON rate；
- 按冻结 token-length bins 做候选置换/随机 opening；
- 匹配总体 resource-token distribution，并报告残余 standardized difference；
- 禁止用无意义 padding 制造假精确匹配；
- seed 和 schedule 在 formal outcome 前冻结。

这仍能检验“学到的时机是否优于随机时机”，且比不可实现的逐行精确 token 契约更诚实。

## 6. evaluator 与 effect supervision

### 6.1 RQ1

- 官方 ESC-Eval/ESC-RANK 是唯一 primary final scorer；七维 0–4 全量报告。
- 已完成的 A6000 runtime qualification（42/42 可解析、重复一致）和双人参考验证保留；它证明 scorer 可运行且与人工排序有相关性，不证明其等同于人工。
- Qwen/DeepSeek/Claude/Gemini 不参与 primary scorer 选择；如使用，只能是预声明 sensitivity。
- 旧 `evaluator winner EXPERIMENT_REQUIRED` 和旧 BLOCKED 结果是历史状态，应在新 register 中显式标为被 2026-09-02 closeout supersede，不能继续阻塞。

### 6.2 RQ2

- QA、Summary、DG 分别使用 pinned ES-MemEval 官方 metric families；不造跨任务 composite。
- capability 标签只做结果分层/机制解释，绝不进入 PM feature、retrieval 或 amount 选择。
- 官方代码中的 moving model alias（例如 LLM judge 使用的 `gpt-4o`）不能被包装成完全可复现身份：优先绑定可用的 dated snapshot；若官方接口只接受 moving alias，则冻结请求模板、调用日期、provider response identity/hash，并在局限中披露。

### 6.3 training effect labels

- 保持同 state、candidate、Generator、prompt、decoding 的 ON/OFF paired comparison；
- 输出 `on_better / off_better / equivalent / uncertain` 及 soft/binomial target；
- 不再使用 70%、0.75、minimum-N、2-of-3 等项目自设 PASS 线决定研究“能不能继续”；
- 机械无效（错误 candidate、wrong owner、future/gold leakage、未交付、空生成、官方 scorer 不可解析）仍必须 fail closed；
- 语义未采用、生成器忽略资源、资源造成变差都是真实 treatment effect，不能作为删行理由。

## 7. first-order 学习与 interaction 的边界

保留 Paper 1 的 first-order factorized scope：四个 binary heads，其他 component bits 不进入 feature，PM 不预测 16-class joint action。

同时必须收窄解释：

- 各 head 的训练 estimand 仍是在其他 optional resources OFF 的 canonical background 下的 isolated effect；
- 三个 memory heads 联合运行时的结果是**系统级部署效果**，不是已识别的 conditional interaction effect；
- `Learned-minus-MP/MS/ME` 是 frozen policy 的 system ablation，不得写成某 head 的独立因果贡献；
- 增加小型预声明 factorial interaction audit 只用于说明组合是否出现明显冲突，不设 PASS 门、不借此调 ontology；
- Paper 1 不声称学会了“当其他资源开启时该 head 是否仍有价值”。

## 8. 哪些检查是硬完整性条件，哪些只是诊断

### 必须修好，否则该行/该运行无效

- strict-past、same-owner、source-span grounding；
- no future/gold/evaluator-only leakage；
- candidate、arm、prompt、model、seed、delivery trace identity；
- official scorer/metric 可执行且输出可解析；
- fold outcome isolation；
- API/cost budget 和 artifact 写入安全；
- terminal empty/failed generation 的预声明处理。

### 不再作为研究解锁门

- v7/v8/v9 DEV precision/recall threshold；
- 反复使用同一 DEV fixture 后的“held-out”表述；
- memory catalog 必须达到某个数量或某个 user coverage 百分比；
- RS 64-item human semantics review 的通过率；
- “treatment uptake”或生成器必须显式复述资源；
- PM Brier/log-loss/calibration 的项目自设 PASS 线；
- 某个 amount 点或某个 head 必须先显著为正。

替代做法是：做一次小型、分层、人工 factuality/integrity audit，检查 hallucination、wrong owner、future leakage、时间错误和不可读表示；结果用于修复明确 bug 与报告 realized error rate，不循环调到任意阈值通过。

## 9. 完整问题清单与处理决定

| # | 问题 | 性质 | 拟议处理 |
|---|---|---|---|
| 1 | MS 同时被定义为 full session 与 event/continuity | 核心语义冲突 | MS = full strict-past raw session |
| 2 | ME 被限制为 action→outcome | 核心语义过窄 | ME = atomic event/experience；action→outcome 为 subtype |
| 3 | superseded MP 是否仍 active | versioning 模糊 | storage 保留，current MP view 只暴露有效版本；变化投影为 ME |
| 4 | 第三方信息 blanket rejection | owner 规则错误 | 接受 user-anchored，拒绝 free-floating biography |
| 5 | source 是否只能投到一个类型 | 多视图误解 | source 可多投影，candidate/head 归属唯一 |
| 6 | `Typed Memory` 名称误导 | 表达问题 | 展示名改 Multi-View，旧 enum 作兼容 alias |
| 7 | v7/v8/v9 DEV 被反复当资格证据 | 证据污染/原地打转 | 全部转 historical engineering regression |
| 8 | precision qualification 被当硬门 | 项目自设标准越权 | 改一次性 factuality audit，无性能阈值 |
| 9 | amount 被提议升为新核心 RQ | 范围膨胀 | 保留为预注册 secondary/mechanism line，不动态预测 k |
| 10 | 不同资源共用 384-token cap | treatment 不等价 | 按资源定义 amount；MS whole-session packing |
| 11 | matched-random 要求逐行 exact tokens | 新 MS 下不可行 | 冻结 token-bin 分层随机，匹配分布与 ON rate |
| 12 | QA/Summary No-Memory 被称 official | baseline 命名错误 | 改称 Project No-Memory；DG 才有官方脚本 |
| 13 | Full History 实际会被 16k 截断 | treatment 命名过强 | 名称加 under-cap，报告可见率/截断率 |
| 14 | official RAG Top-4 也可能尾截断 | baseline delivery 模糊 | 保持 Top-4 检索，记录实际进入 prompt 的 session/tokens |
| 15 | DG-RAG beginning prompt 重复 | upstream 实现混杂 | primary 共用单 prompt；bit-exact 行为只做 sensitivity |
| 16 | `RS fixed in RQ2` 无具体值 | arm 契约缺失 | 冻结为所有 RQ2 arms RS=OFF |
| 17 | moving `gpt-4o` judge alias | 可复现性不足 | dated snapshot 优先；否则 hash/date disclosure |
| 18 | ESC old BLOCKED/winner 状态仍在 register | authority drift | 由已完成 closeout 显式 supersede，alternative judges 不阻塞 |
| 19 | ESC-RANK 被描述为 human-equivalent 风险 | validity 过度主张 | 报告 agreement/MAD 局限，只称 official operational scorer |
| 20 | RQ2 official metrics 可能被跨任务汇总 | estimand 漂移 | 每 task metric family 独立报告，不造 composite |
| 21 | capability label 可能进入选择链 | gold leakage | 只作 outcome strata，不作 feature/retrieval/calibration input |
| 22 | first-order heads 联合部署含 interaction | 解释过度 | system-level claim + non-gating factorial audit；不称独立因果贡献 |
| 23 | component-minus 不重训 | estimand 易误读 | 明确为 frozen-system ablation，不是 head causal effect |
| 24 | RS human semantics/uptake 尚未完成 | 旧门残留 | mechanical integrity 必须；human semantics/semantic uptake 降为 audit |
| 25 | public ES-MemEval 1427 vs paper 1209 | 数据版本差异 | 继续明确使用 public v1.0.0-1427，不声称 row-exact paper replication |
| 26 | benchmark 是 synthetic virtual-user corpus | 外推风险 | 只作 within-benchmark claim，不外推真实临床/真实用户效果 |
| 27 | official baseline 与 same-stack 的含义混淆 | reproducibility 命名 | 区分 method-faithful same-stack 与 bit-exact upstream replication |
| 28 | amount/head/task/fold 搜索自由度过高 | 小样本过拟合 | 小网格、inner-fold-only、user-cluster uncertainty、一次冻结 |
| 29 | old semantic assets 仍有大量 active references | 实现漂移 | v7-v9 与旧 census 归档；正式 compiler/adapter/runtime 重建 |
| 30 | “通过门才允许看研究结果”的流程膨胀 | 治理失衡 | 只保留完整性锁；其余都变为报告项或一次性工程 smoke |

## 10. 会失效与不会失效的既有工作

### 失效，必须重建

- 当前 semantic MP/MS/ME catalog、401-session census 和 coverage numbers；
- v7/v8/v9 memory extraction/verification verdict 作为正式 evidence 的资格；
- 依赖旧 MS/ME 的 feature schema、candidate bundles、amount calibration、effect rows、PM weights、thresholds、matched-random schedules；
- 旧 `Typed_*` 文案与任何把 action→outcome 当全部 ME 的方法描述。

当前 formal outcomes、正式 PM training 和正式 memory effect rows 均为 0，因此没有需要删除或重算的 confirmatory result。

### 保留

- public ES-MemEval materialization、strict-past target boundary、exact-evidence split 基础设施（需重跑 join audit）；
- `memory/ms.py` 的 full-session 基本方向（需接入正式 adapter/runtime）；
- frozen Generator/decoding，除非新 context census 证明不可执行并另行申请修订；
- official ES-MemEval visibility/source audit；
- official RAG pinned source identity与 A6000 BGE-M3 engineering attestation；
- ESC-RANK parser amendment、A6000 42/42 qualification、dual-human reference 和 official scorer closeout；
- RS atomic resource catalog、grounding与 leave-current-dialogue-out 基础设施（human semantics gate 降级不等于删除资源检查）。

## 11. 获批后的执行顺序

1. 生成 active machine-readable amendment，并在 master register 中明确 supersession；outcome locks 保持 CLOSED。
2. 重写 memory contracts/compiler：MP current view、ME event timeline、MS SessionDocument；保留 lineage 和多视图投影。
3. 将 v7/v8/v9、旧 precision UI/fixtures 和旧 semantic census 标成 historical，不再由 blocking CI 引用。
4. 新建小型分层 factuality/integrity audit，不设 arbitrary pass percentage。
5. 在完整 401 sessions 上重建 MP/ME/MS candidates、version views 与 strict-past eligible pools；只报告 realized coverage。
6. 做 token/context census，冻结各资源 amount grid、whole-session packing、Top-k 与 renderer；官方 RAG 固定 Top-4。
7. 明确 RQ2 Project No-Memory、under-cap Full-History、same-stack official-method RAG 和 RS=OFF 合同。
8. 修订 matched-random 为 head/task/fold 内 token-bin schedule，冻结 seed；不 padding。
9. 清理 evaluator register：ESC-RANK official primary 已完成；RQ2 official judge identity 在调用前冻结/披露。
10. 只跑必要的 compiler smoke、full-catalog integrity checks 和 small factorial interaction audit；这些不以性能阈值阻塞。
11. 生成 training-only paired ON/OFF effect data，训练四个 first-order L2 heads并冻结 0.5 operating rule；calibration 只报告。
12. 冻结 formal manifests/call budget 后依次运行 RQ1 ESC-Eval 与 RQ2 ES-MemEval official metrics。
13. 运行 matched-random、Fixed-High、component-minus system ablations与 dose-response secondary analyses。
14. 按官方 metric family、token/cost、user-cluster uncertainty 和 integrity/error analysis 报告；结论随数据收窄，不以门槛制造成功。

## 12. 需要研究者一次性批准的具体条款

批准本提案即批准以下研究范围修订：

1. MP=current profile view；ME=atomic event/experience；MS=full prior raw session。
2. `action→outcome` 降为 ME subtype；user-anchored third-party 可接受；source 可多视图投影。
3. 展示名改为 Multi-View Memory，旧 machine enum 可兼容保留。
4. amount 是 secondary/mechanism evidence，不是新核心 RQ，不训练动态 k。
5. RQ2 的 RS 固定为 OFF；No-Memory/Full-History/official RAG 按第 4 节重新命名与实现。
6. matched-random 改为 ON-rate + token-distribution matched，不要求逐行 exact tokens。
7. v7/v8/v9 precision、RS human semantics、semantic uptake、calibration score 全部退出硬解锁门；只保留机械完整性锁。
8. first-order 联合部署和 component-minus 只作 system-level interpretation；增加 non-gating interaction audit。
9. 旧 ontology 派生 artifacts 全部重建；保留官方 evaluator、官方 visibility、source/split 与 RS 基础设施中不依赖旧 ontology 的部分。

未经明确批准，本文件保持 `INACTIVE`，下一步只允许继续做只读审计或完善本提案，不允许改正式研究代码。
