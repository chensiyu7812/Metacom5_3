# Policy Manager 第一篇论文最终冻结研究方案（2026-08-14）

状态：`ACTIVE / SINGLE SOURCE OF RESEARCH TRUTH / NO DRIFT`

机器可读合同：`data/pm_v1_5_contracts/pm_final_frozen_research_program_20260814_v1.json`

> **命名硬规则：研究方法暂称 Policy Manager（PM），不叫 MetaCom。** `Metacom5_3` 只是历史仓库名/会议相关工程名，不得写成论文方法名。
>
> **权威硬规则：从本文件提交起，本文件是第一篇论文研究设计的唯一主线。** 旧的 PM-v1、历史 v1.5/v2/V3/V5、synthetic 80-user、EvoEmo external、Function/Risk/Quality gate 等文档和代码只保留为历史、诊断或可复用实现证据；若与本文件冲突，以本文件为准。实现不一致时应修实现，不得反过来改研究问题来迁就旧代码。

---

## 1. 第一篇论文到底研究什么

### 1.1 核心问题

在情绪支持对话中，**Strategy-RAG 和长期记忆都是可选的外部资源**。外部资源并不是每一轮都必然有帮助，过度注入还会增加上下文长度、生成成本、噪声和误用机会。

第一篇论文只回答：

> **一个低容量、可审计的 Policy Manager，能否根据当前状态和资源候选的可见描述，选择性地打开 Strategy-RAG（RS）以及三类长期记忆（MP/MS/ME），在公认 benchmark 上保持或改善任务表现，同时减少不必要的资源注入和生成成本？**

这是一项 **selective external-resource allocation** 研究，不是端到端心理咨询模型研究。

### 1.2 第一篇明确不主张什么

第一篇不主张：

- PM 能诊断用户“真正的心理需求”；
- PM 能预测临床状态、人格或长期治疗效果；
- PM 直接预测 ESConv 的八类 support strategy；
- PM 已经学会 RS×MP×MS×ME 的高阶交互因果效应；
- PM 能对完全未见用户做广义真实世界泛化；
- 当前系统是临床心理治疗系统；
- 当前版本包含 Tokkio 多模态、记忆写回、POMDP 或端到端强化学习。

第一篇的目标是**存在性与可用性证明**：一个简单、小容量 PM 是否比“永远不用”“永远用”“同预算随机用”等合理策略更有选择价值。

---

## 2. 系统架构：一个 PM，四类可选资源

### 2.1 四类资源的固定语义

| 资源 | 固定定义 | 谁负责找具体内容 | PM 负责什么 |
|---|---|---|---|
| **RS** | 从 **ESConv train-only** 构建的 Strategy Bank 中检索出的支持策略卡/atomic move | Strategy Retriever | 当前是否值得把该 Strategy-RAG 候选注入 Generator |
| **MP** | 稳定或慢变的用户画像、偏好、约束 | Memory Retriever / typed catalog | 当前是否值得使用该 profile/preference 信息 |
| **MS** | 严格来自过去 session 的事件、经历、连续性主线 | Memory Retriever / typed catalog | 当前是否值得承接该跨 session 信息 |
| **ME** | 严格来自过去的行动—结果/经验—结果信息 | Memory Retriever / typed catalog | 当前是否值得使用该过去经验作有限类比 |

### 2.2 RS 的定义不得再次漂移

**RS 不是“当前应该选择 Question / Reflection / Suggestion 哪一类策略”的分类器。**

ESConv 的八类 strategy annotation 用于：

1. 构建和约束 Strategy Bank；
2. 形成 strategy family / atomic move；
3. 诊断 Strategy Retriever 的 family 对齐；

但它**不是** RS head 的 ON/OFF gold。

RS head 真正预测的是：

> **Retriever 已经给出一个 Strategy-RAG 候选后，这一轮把它交给 Generator 是否值得。**

因此四个资源仍然都是二元 gate：

`RS, MP, MS, ME ∈ {0,1}`

完整系统的合法资源组合仍为 16 种。**但不训练直接 16-class classifier。**

### 2.3 一个 PM 不等于四个 head 必须共享权重

PM 是一个统一策略模块，内部包含四个 component heads：

- RS head；
- MP head；
- MS head；
- ME head。

四个 head 可以分别有自己的 L2 逻辑回归参数，因为训练来源不同；它们仍属于一个 PM，因为共享：

- 同一个决策时点；
- 同一个输入/候选接口；
- 同一个 eligibility / budget / conflict projection；
- 同一个联合动作编译器；
- 同一个 Step 2；
- 同一个冻结 Generator；
- 同一个 trace 和 Cost ledger。

---

## 3. 固定运行链：Retrieval/Observation → Step 1 → Step 2 → Generator

当前第一篇采用以下边界：

```text
Current state
    │
    ├── Strategy candidate discovery ── RS candidate
    ├── Profile memory discovery ────── MP candidate
    ├── Session memory discovery ────── MS candidate
    └── Experience memory discovery ─── ME candidate
                         │
                         ▼
             outcome-blind observation
                         │
                         ▼
              Step 1: Policy Manager
              RS / MP / MS / ME ON/OFF
                         │
                         ▼
       eligibility + budget + conflict projection
                         │
                         ▼
                 one legal joint action
                         │
                         ▼
               Step 2: typed executor
                         │
                         ▼
                  frozen Generator
                         │
                         ▼
              official benchmark outcome
```

### 3.1 当前不是严格的 pre-retrieval router

第一篇统一称为：

> **pre-injection / pre-generation Policy Manager**

候选发现/轻量检索已经发生，因此第一篇**不声称节省所有 retrieval cost**。主要成本主张是：

- 更少的 resource-injected tokens；
- 更少的 generator input tokens；
- 更低的 Generator 侧推理/API 成本；
- 在实际实现中可能伴随更低端到端延迟。

retrieval/embedding 调用仍完整记录，但不把“已经发生的检索”错误包装成 PM 节省。

### 3.2 Step 1 只决定“要不要用”

Step 1 是唯一资源选择层，只输出 RS/MP/MS/ME 四个 bit，再经过确定性的可行性投影得到一个合法 joint action。

Step 1 不负责：

- 挑具体 Strategy Card；
- 挑具体 memory item；
- 写回复；
- 重新解释 gold；
- 根据 Generator 之后是否听话倒推当前决策。

### 3.3 Step 2 只决定“已经选了以后怎样正确用”

Step 2 不允许重新决定开关。它必须把 Step 1 已批准的 exact candidate 编译成可执行约束：

- candidate identity；
- allowed function；
- required contribution；
- epistemic / attribution mode；
- burden cap；
- forbidden inference；
- deterministic context-only fallback。

典型约束：

- **MP**：只能使用真实、当前有效的 profile/preference，不得机械贴标签；
- **MS**：必须明确这是过去 session 信息，不得把旧状态升级成当前事实；
- **ME**：只能有限类比“过去尝试过什么、结果怎样”，不得写成“这个方法对你一定有效”；
- **RS**：落实 Strategy Card 的 atomic move，不得向用户暴露内部卡名/内部 scaffold。

### 3.4 Generator 只负责生成自然语言

Generator 不兼任 PM。它只根据固定 base prompt + Step 2 提供的资源 block 生成最终回复。

如果 Step 1 开对，但 Step 2/Generator 没有真正执行，该失败不能反过来证明 Step 1 应该 OFF；它应由责任账本归到 Step 2 / Generator。

---

## 4. 学习方法：监督学习 + matched ON/OFF component-effect labels

### 4.1 模型固定为四个 L2 正则化逻辑回归二分类 head

第一篇 primary learner：

> **4 个 standardized L2-regularized logistic regression binary heads**

科学范式：监督学习；监督信号不是人工直接猜“应该开”，而是 matched ON/OFF component effect 派生标签。

不训练：

- 16 类动作分类器；
- 大型深度 policy network；
- RL policy；
- 端到端 Generator fine-tuning。

如果 primary learner 最终证明容量不足，复杂模型只能作为未来工作或预注册 challenger，不得在正式结果出来后追分式更换。

### 4.2 每个 head 的训练目标

对每个目标 component `c ∈ {RS, MP, MS, ME}`，在同一 state 上构造：

- OFF arm：不注入 c；
- ON arm：只打开 c；

并尽量固定：

- state / query；
- exact candidate；
- base prompt；
- Generator；
- decoding 参数；
- seed schedule；
- 其他 component 状态。

这估计的是：

> **在当前状态和冻结执行栈下，打开该 component 相对关闭它是否产生正的预期边际价值。**

### 4.3 训练标签三值化

训练标签不是强迫所有样本变 0/1：

- `positive_open`：ON 有实质质量收益，且没有不可接受的 material violation，成本在预算内；
- `nonpositive_off`：OFF 更好，或经过合格测量确认 material equivalence，而 ON 有额外成本；
- `unknown`：treatment 未有效执行、candidate lineage 不清、评测工具未资格化、结果不稳定/不可裁定。

`unknown` 在部署时默认 OFF，但**训练时排除**，不能伪装成负例。

### 4.4 训练用 outcome scorer 与论文最终 evaluator 必须分离

ON/OFF gate 在原始 dataset 中没有 gold。例如 ESConv 告诉我们人工 supporter 使用了 Affirmation，并不告诉我们“当前冻结 Generator 在没有 Strategy-RAG 时会不会一样好”。因此 gate 的 effect label 必须从实际 ON/OFF 生成结果中派生。

训练阶段允许使用一个**冻结、资格化、匿名 pairwise 的训练专用 outcome scorer**。它只负责产生弱监督，不负责宣布论文成功。

训练专用 quality 只保留四个正向维度：

1. Goal fulfillment；
2. Emotional support value；
3. Useful contribution；
4. Clarity & naturalness。

训练专用 atomic risk 只保留：

1. explicit boundary violation；
2. grounding/personal-evidence violation；
3. excessive directiveness / interaction burden。

硬工程完整性（wrong owner、future leakage、scaffold exposure 等）单独记，不混入 quality 总分。

**最终论文主结果不由这套内部 scorer 决定。** RQ1 最终由 ESC-Eval，RQ2 最终由 ES-MemEval 官方指标决定，从而避免“同一个 judge 既造标签又宣布模型成功”的闭环。

---

## 5. 数据集角色：三个公开资源，各负其责

### 5.1 ESConv：Strategy-RAG 的训练来源，不是长期记忆 benchmark

ESConv 用于：

- **train split** 构建 Strategy Bank；
- 训练/校准 Strategy Retriever；
- 在 train/dev 范围构造 RS OFF/ON effect data；
- held-out 部分做 strategy retriever 和 in-domain sanity diagnostics。

硬边界：

- Strategy Bank 只能来自 ESConv train；
- validation/test 不得进入 Strategy Bank；
- ESConv gold strategy 可以诊断 retriever family match，但不是 RS gate gold；
- ESConv 没有可靠同用户长期历史，因此不用于证明 MP/MS/ME。

### 5.2 ESC-Eval：RQ0 Generator qualification + RQ1 最终外部 ESC 考卷

ESC-Eval 负责：

- Generator 的基础 ESC 能力画像；
- RQ1 中 R0 / Fixed-High / Matched-Random / Learned-RS-PM 的正式质量比较。

ESC-Eval 使用 role-playing 多轮交互，不依赖单一 ground-truth response 的 lexical overlap，因此比 BLEU/ROUGE 更适合作为第一篇的最终 ESC response benchmark。

**source overlap 边界：** 因 Strategy Bank 来自 ESConv，ESC-Eval 中源自 ESConv 的 role cards 不能包装成完全独立 transfer。正式 RQ1：

- primary：non-ESConv-source English role cards；
- secondary：当前冻结的完整 English card set 全量报告；
- ESConv-derived cards 单独作为 overlap / in-distribution sensitivity。

### 5.3 ES-MemEval：RQ2 memory PM 的正式 benchmark

RQ2 使用公开 ES-MemEval artifact，并明确记录 artifact identity。当前计划使用仓库已确认的：

> `ES-MemEval-Public-v1.0.0-1427`

论文原文描述 1,209 QA；若公开 v1.0.0 artifact 为 1,427，则论文必须诚实写“public artifact v1.0.0-1427”，不能声称精确复现 1,209。

ES-MemEval 三个任务：

- QA；
- Summarization；
- Dialogue Generation。

它同时提供长期记忆能力维度：Information Extraction、Temporal Reasoning、Conflict Detection、Abstention、User Modeling。

### 5.4 EvoEmo 的最终位置

EvoEmo 不再是第一篇主外部实验，不再控制研究方向。它可保留为：

- ES-MemEval 的底层纵向对话资源；
- candidate/debug/错误分析来源；
- 可选 supplemental longitudinal diagnostic。

不得再建立一套独立 EvoEmo Quality/Risk/Function 主门。

### 5.5 同用户 longitudinal adaptation 允许，但 evaluation leakage 禁止

第一篇**不要求完全 unseen-user 泛化**。允许同一用户的历史帮助适应该用户，但必须满足：

- 每个 evaluation query 本身不可进入训练；
- gold answer / gold evidence 不可进入 runtime PM 输入；
- 与 evaluation target 同 fact/event cluster 的标签不可泄漏到其训练 fold；
- 只能使用 target 时点以前的 session；
- future session 绝对禁止；
- 每个最终结果必须由没有见过该 evaluation target outcome 的 fold/checkpoint 产生。

统计推断仍按 18 个 user cluster 报告，不能把上千 QA item 当成上千独立用户。

---

## 6. Benchmark 与 baseline 的统一原则

必须区分三种 baseline 信息：

| 层次 | 作用 | 能否证明 PM 有用 |
|---|---|---|
| 论文已发表分数 | 外部坐标、合理分数范围 | **不能** |
| 官方协议 bounded reproduction | 检查 dataset/split/prompt/retrieval/scorer 没接错 | **不能直接** |
| **同栈 baseline 重跑** | 相同 Generator/题目/scorer，只改变资源分配方式 | **能，是主因果比较** |

因此，不得把论文中的 Mistral/Phi/GPT/BlenderBot 旧分数直接与 PM 做因果比较。

真正的正式 baseline 必须使用：

- 同一个冻结 Generator；
- 同一个基础 task prompt；
- 同一个 decoding / seed schedule；
- 同一个候选来源/检索器（在相应 arm 合法时）；
- 同一个 official scorer；
- 只改变 strategy/memory allocation policy。

---

## 7. Experiment 0：Generator qualification（前置，不是 PM 贡献）

### 7.1 目的

只回答：当前 Generator 是否足以承载 PM 实验，还是已经形成明显 generator ceiling。

当前正在执行的 ESC-Eval qualification 继续完成；不得中途为了追新模型打断。候选集合以当前 RQ0 freeze manifest 为准。

### 7.2 结果表

| Generator | Fluency ↑ | Expression ↑ | Empathy ↑ | Information ↑ | Skillful ↑ | Humanoid ↑ | Overall ↑ | Average ↑ | Completion ↑ | Input tokens ↓ | Median latency ↓ | Cost ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| incumbent |  |  |  |  |  |  |  |  |  |  |  |  |
| challenger |  |  |  |  |  |  |  |  |  |  |  |  |

ESC-Eval 的七维必须按官方 scorer 的原始输出尺度报告；若官方实现输出 0–4 或映射后的 0–100，保留该实现尺度并在论文中写清，禁止为了显得更高而自行换算。

ESC-RANK 由于公开 gold/split identity 不完整，**只作为同行认可的七维 scorer/profile，不单独定义绝对“及格线”**。

### 7.3 Generator 冻结规则

- 先看运行可靠性（completion / invalid turn / failure）；
- 再看 ESC-Eval Overall 与七维 profile；
- 再看 Cost；
- 若 incumbent 已达到可用水平且不存在明确 material capability gap，可保留以完成第一篇；
- 若 challenger 在 ESC/Step2 execution 上稳定、实质优于 incumbent，则必须在任何正式 PM effect generation 之前切换并冻结；
- Generator 一旦冻结，后面不得根据 PM 结果再换。若换 Generator，所有 effect labels 必须重新生成。

第一篇不要求 Generator fine-tuning。只有所有合理现成 instruct model 都无法通过 executor/ESC qualification 时，才考虑下一阶段 domain SFT；这不是当前默认路径。

---

## 8. RQ1：Selective Strategy-RAG allocation

### 8.1 研究问题

> **Strategy-RAG 是否需要 always-on？一个 learned RS gate 能否在 ESC-Eval 上保持/改善情绪支持质量，同时减少不必要的 Strategy-RAG 注入和生成成本？**

### 8.2 训练流程

1. 用 ESConv train-only 构建/冻结 Strategy Bank；
2. 冻结 Strategy Retriever；
3. 对 ESConv train/dev 中的训练 state，固定同一 Top-1 Strategy Card；
4. 生成 matched `R0` vs `RS` pair；
5. 用训练专用、资格化 pairwise scorer 生成 `positive_open / nonpositive_off / unknown`；
6. 训练 RS 的 L2 logistic head；
7. ESConv held-out 只做 in-domain sanity/retriever diagnostic；
8. 最终 RQ1 进入 ESC-Eval，同栈比较四个 arm。

### 8.3 正式四个 arm

| Arm | RS 行为 | 它回答的问题 |
|---|---|---|
| **R0 / No Strategy-RAG** | 永远不注入 Strategy Card | 完全不用外部策略资源怎么样 |
| **RS Fixed-High** | 有合法 Top-1 就每轮注入同一候选 | always-on Strategy-RAG 怎么样 |
| **RS Matched-Random** | ON rate / token budget 与 Learned PM 匹配，但随机决定在哪些 state 开 | “少开”本身是不是就够了 |
| **Learned RS-PM** | PM 决定是否注入同一 Top-1 candidate | 是否真正学到“什么时候值得开” |

所有 arm 的 Strategy Retriever 和 Top-1 candidate identity 必须相同；唯一实验变量是是否注入。

### 8.4 ESConv Oracle 的位置

ESConv gold strategy / Oracle **不是 PM baseline**，因为 PM 不预测 strategy category。

它只允许做 retriever diagnostic，例如：

- `strategy_family_match_at_1`；
- `strategy_family_match_at_3`（若 Top-k 诊断存在）。

它只能回答“Retriever 找到的卡是否与人工 strategy family 大体一致”，不能回答“这一轮是否应该打开 RS”。

### 8.5 RQ1 正式指标字段

**Primary official outcome：**

- `esc_overall`

**Secondary official profile：**

- `esc_fluency`
- `esc_expression`
- `esc_empathy`
- `esc_information`
- `esc_skillful`
- `esc_humanoid`

**运行与资源字段：**

- `dialogue_completion_rate`
- `valid_supporter_turn_rate`
- `failure_rate`
- `retry_count`
- `rs_candidate_present_rate`
- `rs_on_rate`
- `strategy_card_tokens_injected`

**Cost 字段见第 11 节。**

ESConv 的 PPL/BLEU/ROUGE/Distinct、strategy ACC 只允许作为 secondary/in-domain diagnostic，不进入 RQ1 primary claim。

### 8.6 RQ1 的“做出来”定义

必须同时看三类比较：

1. **Learned vs R0**：证明选择性 Strategy-RAG 至少没有使整体系统变成“还不如不用”；
2. **Learned vs Fixed-High**：证明在 ESC-Eval Overall 非劣时，能减少资源/Generator 成本；
3. **Learned vs Matched-Random**：证明不是“少开就行”，而是 opening location 有信息。

正式 trade-off 判据见第 12 节。

---

## 9. RQ2：Selective typed-memory allocation

### 9.1 typed memory 是什么

Typed memory 不是新模型，而是把 raw longitudinal history 按用途拆成可审计资源。

例如 raw history：

> “3 月 12 日用户说下周要组会，很紧张，后来提到自己准备了三个问题；第二天说练习后感觉好一些。”

可以形成：

```text
MP / PROFILE_OR_PREFERENCE
fact: User prefers short, concrete suggestions.
```

```text
MS / SESSION_MEMORY
event: The previous session centered on anxiety before a lab presentation.
time: past session
```

```text
ME / EXPERIENCE_OUTCOME
action: Practiced three likely questions beforehand.
outcome: Later reported feeling more prepared.
```

所有 memory 必须来自 target 时点以前的真实允许历史，不能从 QA gold/future timeline 反向构造 runtime memory。

### 9.2 一个 memory PM，而不是三套 benchmark-specific PM

MP/MS/ME 三个 head 是同一个 PM 的三个固定 component heads。QA/Summary/DG 可以把 `task_type` 作为运行时已知特征，但**不得为三个任务分别训练三套不同 PM 并再称为一个统一 PM**。

相同的 MP/MS/ME head 参数在三个 ES-MemEval task format 上运行；不同 task 只改变 task prompt 和合法 task mask。

### 9.3 正式六个 baseline/arm

| Arm | Memory 条件 | 作用 |
|---|---|---|
| **No Memory** | 不提供长期历史 | 记忆下界 |
| **Full History** | 提供允许范围内全部过去历史 | 高资源长上下文基线 |
| **Official RAG Top-4** | 同一冻结 Generator + 官方式 bge-m3 / session-level Top-4 条件 | 公认固定 RAG baseline |
| **Typed Fixed-High** | 使用与 PM 完全相同的 MP/MS/ME typed candidate machinery，但所有 eligible 类型都开 | 隔离 typed representation 本身与 learned gating 的贡献 |
| **Typed Matched-Random** | 每个 component 的使用率/注入预算与 Learned PM 匹配，但随机决定在哪些 eligible state 开 | 控制“少用资源”本身 |
| **Learned Typed-Memory PM** | MP/MS/ME 三个 learned gate | 本研究方法 |

Published Mistral/Phi/GPT 分数只作坐标，不作为因果 comparator。

### 9.4 ES-MemEval QA 结果表与字段

| Method | F1 ↑ | BERTScore ↑ | LLM Judge (0–2) ↑ | Recall@k ↑ | nDCG@k ↑ | Input tokens ↓ | Latency ↓ | Cost ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| No Memory |  |  |  | N/A | N/A |  |  |  |
| Full History |  |  |  | N/A | N/A |  |  |  |
| Official RAG Top-4 |  |  |  |  |  |  |  |  |
| Typed Fixed-High |  |  |  |  |  |  |  |  |
| Typed Matched-Random |  |  |  |  |  |  |  |  |
| Learned Typed-Memory PM |  |  |  |  |  |  |  |  |

F1/BERTScore/LLM-as-Judge 分别按 IE/TR/CD/Abs/UM 和 All 报告。Recall@k/nDCG@k 是 retrieval 诊断，不应误归为 PM Step1 的唯一能力。

### 9.5 ES-MemEval Summarization 结果表与字段

| Method | ROUGE-1 ↑ | ROUGE-2 ↑ | ROUGE-L ↑ | Event Precision ↑ | Event Recall ↑ | Event F1 ↑ | LLM Score (0–5) ↑ | Input tokens ↓ | Cost ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| No Memory |  |  |  |  |  |  |  |  |  |
| Full History |  |  |  |  |  |  |  |  |  |
| Official RAG Top-4 |  |  |  |  |  |  |  |  |  |
| Typed Fixed-High |  |  |  |  |  |  |  |  |  |
| Typed Matched-Random |  |  |  |  |  |  |  |  |  |
| Learned Typed-Memory PM |  |  |  |  |  |  |  |  |  |

### 9.6 ES-MemEval Dialogue Generation 结果表与字段

| Method | Observation Recall ↑ | Weighted Score ↑ | LT-Memory (1–5) ↑ | Personalization (1–5) ↑ | Emotional Support (1–5) ↑ | Input tokens ↓ | Median latency ↓ | Cost ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| No Memory |  |  |  |  |  |  |  |  |
| Full History |  |  |  |  |  |  |  |  |
| Official RAG Top-4 |  |  |  |  |  |  |  |  |
| Typed Fixed-High |  |  |  |  |  |  |  |  |
| Typed Matched-Random |  |  |  |  |  |  |  |  |
| Learned Typed-Memory PM |  |  |  |  |  |  |  |  |

**RS 在 ES-MemEval 官方主分析中必须固定。** QA/Summary 不开放 RS；Dialogue Generation 也不能偷偷变成 RS+MP+MS+ME 的 16-action 官方实验。否则会同时改变 strategy 与 memory，破坏 memory attribution。

ES-MemEval DG 可以证明“memory allocation 是否改善最终个性化 ESC 回复”，但不能证明“RS×memory 联合交互已经被因果识别”。

---

## 10. Memory component-minus 消融

Baseline 与 ablation 必须分开。

主 Learned PM 运行以后，做：

- `Learned - MP`：只强制 MP=OFF，其余 head 保持原 PM 决策；
- `Learned - MS`：只强制 MS=OFF；
- `Learned - ME`：只强制 ME=OFF。

不得为了消融重新训练另外三套 PM。

### 10.1 消融表

| Variant | QA primary ↑ | Summary Event F1 ↑ | DG Weighted Score ↑ | LT-Mem ↑ | Personalization ↑ | Emotional Support ↑ | Input tokens ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full Learned PM |  |  |  |  |  |  |  |
| − MP |  |  |  |  |  |  |  |
| − MS |  |  |  |  |  |  |  |
| − ME |  |  |  |  |  |  |  |

### 10.2 “一个 memory head 有用”的冻结定义

一个 head 计为 `useful`，必须：

1. eligible slice 在看到正式 outcome 前冻结；
2. full-minus-head 相对 full Learned PM 在至少一个预注册 official primary metric 上出现正向 paired effect；
3. 该 eligible slice 的 aggregate effect > 0；
4. 正方向至少出现在两个独立 user 或 fact/event cluster；
5. 报告 user-cluster uncertainty 和全部负例；
6. 不要求第一篇每个 head 都单独达到传统 p<0.05。

第一篇的 typed-memory 机制主张要求：

> **MP/MS/ME 三个 head 至少两个满足 useful 定义。**

若只有一个 useful，仍可报告 memory system 结果，但必须把“typed-memory allocation”主张降级为“single/limited memory gating evidence”。

---

## 11. Cost：第一篇的正式第二条轴

Cost 不由 LLM judge 判断，全部来自运行日志。

### 11.1 Primary Cost

- `generator_input_tokens`
- `resource_injected_tokens`

### 11.2 必报 Cost

- `output_tokens`
- `total_tokens`
- `retrieval_calls`
- `embedding_calls`
- `retrieval_latency_ms`
- `generator_latency_ms`
- `end_to_end_latency_ms`
- `retry_count`
- `api_cost_usd`（若可准确恢复）

Latency 至少报告 median 与 p95；API latency 抖动较大，不只报 mean。

### 11.3 Cost 主张边界

因为当前 PM 位于 candidate discovery 之后，主要 cost claim 是：

> **在官方 benchmark performance 不出现 material degradation 的前提下，减少不必要的 injected context / generator input / generation cost。**

不得用更低 Cost 抵消明确的质量失败或严重 integrity failure。

---

## 12. “怎样才算做出来”：最终判决规则

不存在 ESC-Eval 或 ES-MemEval 官方规定的“60 分及格”。第一篇采用**预注册的相对成功标准**。

### 12.1 质量非劣 margin 的产生方式

不允许正式结果出来后拍脑袋选 margin。

每个 official primary metric 的 non-inferiority margin `δ` 必须在 main arm outcome 解封前，由对应 evaluator 的 qualification/repeatability slice 产生并写入 freeze manifest：

1. 在相同条件下重复运行/重复评分 qualification slice；
2. 估计 evaluator + stochastic generation 的重复测量噪声；
3. 预先冻结一个“超过正常测量噪声才算 material”的 `δ`；
4. main table 以后不得修改。

若 evaluator 基本确定性，则使用预先冻结的小效应阈值，不允许根据 Learned PM 结果反推。

### 12.2 Cost effect-size threshold

第一篇保留历史上已经反复使用的工程效应阈值：

> **相对对应 high-resource same-stack baseline，Generator input tokens 至少下降 10% 才计为“实质性成本改善”。**

这是本研究预注册工程阈值，不是 benchmark 官方及格线。

### 12.3 RQ1 成功条件

RQ1 成功需要：

- Learned RS-PM 对 Fixed-High 的 `ESC-Eval Overall` 满足预注册非劣；
- Learned RS-PM 相对 Fixed-High 的 `generator_input_tokens` 至少下降 10%；
- Learned RS-PM 相对 Matched-Random 的 Overall 出现正向 paired effect；
- R0 比较不显示 learned system 出现 material overall degradation；
- 其余六个 ESC-Eval 维度全部透明报告，不允许只挑有利维度。

如果只做到“和 Fixed-High 一样但便宜”，可以支持 **efficient selective allocation**；如果同时显著/稳定高于 Fixed-High，则是更强结果，但不是第一篇最低要求。

### 12.4 RQ2 成功条件

RQ2 不造跨任务混合总分。对 QA / Summary / DG 各自报告官方 primary metric。

Selective memory system 至少需要：

- Learned PM 相对 Typed Fixed-High 在主要 task outcomes 上总体非劣，并且 input tokens 至少下降 10%；
- Learned PM 相对 Typed Matched-Random 在预注册 primary metrics 上总体正向，证明 opening location 有信息；
- 与 Official RAG Top-4 / Full History 的差异完整报告；
- 不允许为了一个任务的好结果掩盖另一个任务的严重退化；
- MP/MS/ME 至少两个通过第 10.2 节的 useful component 标准。

### 12.5 第一篇最低完整结论

最理想、也最符合第一篇定位的结论是：

> **Policy Manager 在 Strategy-RAG 与 typed long-term memory 两类外部资源上都表现出选择价值：在公认 benchmark 指标不出现 material degradation 的情况下，减少了不必要的上下文/Generator 成本；且至少两类 typed memory 资源通过独立消融表现出可复现贡献。**

若 RQ1 或 RQ2 只有一侧成立，论文可以降级主张，但不得修改 benchmark/阈值把失败改成成功。

---

## 13. 统计单位与不确定性

### 13.1 RQ1

- 以 ESC-Eval role card / dialogue 为主要 paired cluster；
- 如果同一 role card 有多个 frozen seeds，先在 card 内聚合或使用 cluster-aware paired bootstrap；
- 不把每个 turn 当独立样本；
- arm 之间使用相同 role-card × seed schedule。

### 13.2 RQ2

- ES-MemEval 只有 18 个长期用户，统计推断必须把 user 当最高层 cluster；
- QA/Summary/DG item 可提供效果观测，但不等于新增独立用户；
- 报 user-cluster bootstrap / cluster-aware CI；
- 正式论文明确说明不声称广泛人口级 unseen-user generalization。

### 13.3 Matched-Random 的冻结方式

Matched-Random 只能在 Learned PM 的 opening schedule / rate 已被冻结、但 outcome 尚未解封时生成随机 opening schedule。

- RQ1：匹配总体 RS ON rate 和尽量匹配 injected-token budget；
- RQ2：按 MP/MS/ME 分别匹配 component ON rate 与资源 token budget；
- candidate identity 与 retriever 不变；
- 随机 seed 在 outcome 前冻结。

---

## 14. 最小 integrity audit：保留，但不再成为第三张考卷

第一篇主要能力由 ESC-Eval / ES-MemEval 官方指标判断。过去自建的 Quality/Function/Risk 大门不再控制研究方向。

只保留少量硬诊断：

- wrong owner / cross-user retrieval；
- future leakage；
- fabricated personal history / unsupported personal fact；
- stale/conflict misuse；
- explicit boundary violation（适用时）；
- excessive directiveness（适用时）；
- internal scaffold/resource-label exposure。

这些事件：

- 单独报告；
- 不合成一个“Risk 总分”；
- 不与 Quality 做加权平均；
- pipeline-invalid（如 wrong owner、future leakage）必须修复后重跑对应实验，因为这属于实验无效，而不是普通模型得分低；
- user-facing misuse 可以作为正式 failure outcome 保留并报告，不能因为 Cost 低而抵消。

---

## 15. 责任划分与追责逻辑

每条运行必须保存完整 trace：

`state → candidates → observation → eligibility → Step1 scores → requested action → feasible action → Step2 binding → injected resource → generator response → official outcome → cost`

| 层 | 责任 | 典型失败 |
|---|---|---|
| **Retrieval/Candidate** | 找到当前用户正确、严格过去、相关的 candidate | Top-1 错话题、错用户、漏掉明显 relevant item |
| **Observation/Eligibility** | 把候选的 owner/time/relevance/redundancy/boundary 等可见属性变成 outcome-blind feature/mask | 把陈旧候选当可用、把明确拒绝建议判成 eligible |
| **PM Step 1** | 在输入正确时预测该 component 是否值得打开 | 候选和 observation 都对，但 PM 开错/关错 |
| **Joint Projection** | 将四 bit 投影为预算/冲突合法动作 | 互斥资源同时开、预算投影错 |
| **Step 2** | 将已选 exact resource 正确绑定、限制用途、注入 | 开对了但注入错 item、时间语态错、required contribution 缺失 |
| **Generator** | 按 Step2 自然实现，不编造、不泄露 scaffold | 明明收到正确资源但没使用/误用/生成质量差 |
| **Resource hypothesis / system ceiling** | 前述链路均正确但 benchmark 没有收益 | 说明该资源在此类状态本来没有足够边际价值，或 Generator capacity 已成上限 |

**官方 benchmark 负责判“最终有没有价值”，责任账本负责解释“为什么成功/失败”。** 两者不得互相替代。

---

## 16. 防作弊/防泄漏只保留必要锁，不再堆锁

第一篇只保留能保护因果归因和 benchmark 公平性的锁：

1. ESConv Strategy Bank 只能来自 train；
2. ES-MemEval evaluation target/gold/future session 不进 runtime PM；
3. candidate 只来自严格过去、同一 owner；
4. arm 之间 Generator/base prompt/decoding/scorer 不变；
5. same-stack baseline 只改变资源分配方式；
6. thresholds/margins/random seeds 在 main outcomes 前冻结；
7. main outcome 解封后不得改 prompt、Generator、retriever、PM 特征或 sample subset；
8. 所有关键 artifact 记录 hash/manifest。

除上述必要边界外，不再为了“看起来更严格”增加无法解释、无法追责的额外锁。

---

## 17. 官方 benchmark 的边界：能证明什么、不能证明什么

### 17.1 ESC-Eval

能证明：

- 多轮 ESC chatbot 在同行七维 rubric 下的能力画像；
- R0 / Fixed / Random / Learned 之间的 response-level 系统差异。

不能证明：

- 某个 RS gate label 是心理学绝对真值；
- 某一张 Strategy Card 是唯一正确策略；
- 临床疗效。

### 17.2 ES-MemEval

能证明：

- 长期记忆的 extraction、temporal、conflict、abstention、user modeling 能力；
- QA/Summary/DG 下的 memory utilization 与 personalization；
- fixed RAG / full history / typed selective memory 的对照。

不能证明：

- MP/MS/ME 是 ES-MemEval 官方 taxonomy；这三类是本研究提出的 typed memory decomposition；
- 18 用户等同于广泛真实人群；
- RS×memory 联合四头交互已经被官方 benchmark 因果识别。

因此论文表述统一为：

> **We evaluate our typed memory decomposition using the official ES-MemEval tasks and metrics.**

而不是“ES-MemEval 官方定义了 MP/MS/ME”。

---

## 18. 官方协议复现与同栈 baseline 的实际执行顺序

### 18.1 bounded official-protocol sanity reproduction

每个 benchmark 只做足够确认 pipeline 正确的有限复现：

- 数据身份；
- split / role-card identity；
- prompt assembly；
- retrieval protocol；
- scorer；
- metric direction / plausible range。

不需要把历史所有 Mistral/Phi/GPT/BlenderBot 模型重新烧一遍。

### 18.2 same-stack baseline rerun

之后把“官方/公认 baseline 条件”迁移到冻结 Generator：

- Strategy：R0 / Fixed-high / Matched-random / Learned；
- Memory：No Memory / Full History / Official RAG Top-4 / Typed Fixed-High / Typed Matched-Random / Learned。

真正论文因果结论只来自这一层。

---

## 19. 实施顺序：从现在开始不得自行改变

1. **完成当前 ESC-Eval Generator qualification。** 不打断当前运行，不临时加入新模型追分。
2. **按 RQ0 结果冻结一个 Generator。** 冻结 model ID、mode、base prompt、decoding、seed schedule。
3. **做最小官方协议 sanity reproduction。** ESC-Eval/ESConv/ES-MemEval pipeline 各确认一次。
4. **冻结 Strategy Bank 和 memory catalog construction。** ESConv train-only；memory strict-past/same-owner。
5. **冻结 training-only outcome measurement contract。** pairwise quality + atomic risk；先通过最小 human-anchor qualification。
6. **生成 RS、MP、MS、ME matched ON/OFF effect labels。** unknown 不训练。
7. **训练四个 L2 logistic heads。** 不训练 16-class，不换模型追分。
8. **冻结 PM 与同栈 baseline configs。** 包括 matched-random seed/schedule。
9. **RQ1：运行 ESC-Eval 四臂正式实验。** primary 用 non-ESConv-source cards，全 English set 做 secondary。
10. **RQ2：运行 ES-MemEval 六臂 QA/Summary/DG。** RS 在 RQ2 official main 固定。
11. **运行 −MP / −MS / −ME component-minus 消融。** 不重训 PM。
12. **汇总 official outcome + Cost + cluster uncertainty + minimal integrity audit。**
13. **只在全部主结果冻结以后写论文结论。** 不得根据结果倒改研究问题或及格线。

---

## 20. Stop rules：失败也必须能得到科学结论

- Generator qualification 失败：在 PM effect generation 前换到已预注册 challenger，然后重新冻结；不训练旧 Generator 的 PM。
- RS effect data 几乎全 ON 或全 OFF：优先解释为 Strategy-RAG 的条件效应不足/训练 slice 不可识别，不自动生成 synthetic 用户“救标签”。
- 某 memory head 无足够 eligible evidence：标记 `not identifiable on this benchmark`，不造 synthetic gold 补齐。
- 只有一个 memory head useful：typed-memory 主张降级，不修改 useful 定义。
- Learned ≈ Random：说明 selector 没学到 opening location；不能只拿“成本低”宣称 learned routing 成功。
- Learned < Fixed-high 且成本收益不足：RQ 失败，如实报告。
- benchmark scorer 出现明显不稳定：停止正式 outcome，先修 measurement qualification；不能看着结果挑 scorer。

第一篇的价值不是“所有东西都必须赢”，而是：**成功和失败都有冻结、可解释、可追责的判定标准。**

---

## 21. 论文最终 Results 的固定表结构

主文建议只保留：

1. **Table 1 — Generator Qualification on ESC-Eval**
2. **Table 2 — Selective Strategy-RAG on ESC-Eval**
3. **Table 3A — ES-MemEval QA**
4. **Table 3B — ES-MemEval Summarization**
5. **Table 3C — ES-MemEval Dialogue Generation**
6. **Table 4 — MP/MS/ME Component-Minus Ablation**
7. **Figure — Performance–Cost Pareto**：横轴 generator input tokens/Cost，纵轴对应 official primary metric。

旧 Quality/Function/Risk 大表、旧 synthetic action sweep、旧 16-way pseudo-gold 不进入第一篇主结果。

---

## 22. 一句话论文主线

> **Policy Manager 将 Strategy-RAG 与三类长期记忆视为可选外部资源：Retriever 负责找候选，四个低容量 component heads 在 Step 1 决定当前是否值得打开，Step 2 负责正确执行，冻结 Generator 负责生成自然语言；Strategy 侧用 ESConv train-only 建库/训练、用 ESC-Eval 做最终多轮 ESC 考试，Memory 侧用 ES-MemEval 官方 QA/Summary/DG 指标评价。论文最终回答的不是“PM 是否猜中了一个自建标签”，而是“相同 Generator 与相同考卷下，learned selective allocation 能否以更少的上下文/成本获得不劣甚至更好的官方 benchmark 表现”。**

---

## 23. 对 Codex/后续 agent 的禁止漂移条款

除非用户明确要求改变研究问题，否则后续 agent **不得**：

- 把方法名写成 MetaCom；
- 把 RS 改成 ESConv strategy category classifier；
- 把 PM 改成直接 16-class classifier；
- 把 RQ1 主指标改回 strategy ACC/BLEU/ROUGE；
- 把 ESConv Oracle 当 RS gate 的 gold/oracle baseline；
- 把 EvoEmo 恢复为第一篇主外部 outcome gate；
- 把 ES-MemEval DG 改成 RS+MP+MS+ME 四头联合官方实验；
- 把 published historical model scores 当同栈因果 baseline；
- 重新引入大规模自建 Quality/Function/Risk 总分控制论文主结论；
- 在正式 main outcomes 后修改 Generator、prompt、retriever、margin、sample subset 或成功定义；
- 因某 head 没学会而生成 synthetic 用户/标签去“补成功”；
- 因旧实现不符合本方案而改变本方案；应修实现并记录 migration。

任何建议若确实需要改变上述边界，必须先明确写成：

> `PROPOSED RESEARCH CHANGE — NOT AUTHORIZED`

说明理由、影响和需要重跑的实验，等待用户明确批准后才能修改 authority 文件。

---

## 24. 当前完成标准

从本文件起，“不知道做到什么程度才算做出来”的问题被定义为：

- **Generator**：已通过并冻结；
- **RQ1**：Learned RS-PM 在 ESC-Eval Overall 上对 Fixed-High 非劣、input token 至少节省 10%，并优于同使用率 Matched-Random；
- **RQ2**：Learned typed-memory PM 在 ES-MemEval 官方任务指标上相对高资源同栈基线保持总体非劣并至少节省 10% input token，且优于 Matched-Random；
- **Mechanism**：MP/MS/ME 至少两个通过冻结的 component-minus useful 标准；
- **Evidence**：所有主表使用官方 benchmark 指标；Cost 来自真实日志；统计按 role-card/user cluster；硬 integrity failure 单独报告；
- **Claim boundary**：不把 18 用户写成广泛人群泛化，不把 benchmark score 写成临床疗效。

满足以上条件，即可说：

> **第一篇的 Policy Manager 已经“做出来”并具有可发表的存在性/可用性证据。**

若未满足，也必须按本文件的 stop rule 得到清楚的负结果，而不是继续改变定义直至“通过”。
