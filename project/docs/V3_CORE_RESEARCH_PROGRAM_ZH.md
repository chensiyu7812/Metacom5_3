# MetaCom V3 核心研究方案：一个 PM、两类决策、两项核心实验

日期：2026-08-14

状态：`ACTIVE / OFFICIAL-BENCHMARK-FIRST / NO NEW API AUTHORITY`

机器合同：`data/v3_authority/v3_core_research_program_v1.json`

本文件是当前研究问题、主张、实验责任和执行顺序的唯一人类可读入口。旧 V1–V5.3 的 head gate、内部 Quality/Risk/Function、人评面板和三外测路线全部保留为开发历史，不再决定未来研究方向。

## 1. 一句话主张

MetaCom 在生成前显式管理两类可选资源：情绪支持策略与长期记忆。一个学习型 Policy Manager（PM）根据当前状态选择需要的策略和记忆，在公开情绪支持与长期记忆 benchmark 上保持或改善官方任务表现，并相对固定高资源方案降低实际成本。

这是一项“有无与可行性”研究：先证明显式、类型化、可学习的资源管理确实有价值，不主张临床疗效，也不要求监督学习的 PM 泛化到完全未见的真实用户。

## 2. 系统构造：一个 factorized PM，不是两个 PM

PM 是同一个 pre-generation policy manager，保留四个可解释输出 head 和一个联合动作编译器：

- `RS`：当前应该采用哪类情绪支持动作；动作空间和监督优先采用 ESConv 的官方策略体系。
- `MP`：是否需要相对稳定的用户画像、偏好和约束。
- `MS`：是否需要跨 session 的事件、经历和连续性。
- `ME`：是否需要过去行动及其结果，以避免重复无效建议或复用有效经验。

四个 head 可以使用各自最匹配的训练信号和参数；第一篇论文不要求它们共享同一组神经网络权重。称为“一个 PM”的依据是：它们共享同一候选观察合同、决策时点、联合预算/冲突投影、动作空间、执行器、generator、trace和Cost账本，并共同输出一个合法动作，而不是各自产生一套互不相干的系统回复。

### Step 1：选择资源

1. 统一 candidate layer 从 RS Bank 与严格过去的 MP/MS/ME memory stores 中发现候选；不同资源类型可以有相应索引，但同一实验的所有 policy arm 必须共享候选池、retriever配置和实际候选。
2. owner、严格过去、冲突、明确边界和资源存在性只作机械 hard mask。
3. 四个 factorized heads 根据运行时可见状态判断各资源是否值得开启。
4. task action mask、预算和冲突投影把四个输出编译为一个合法 joint action；完整系统仍对应 MP/MS/ME/RS 四 bit 的 16 动作空间。

Step 1 是唯一 PM 决策层。它发生在 candidate discovery 之后、资源注入和生成之前；不读取评测答案、未来session、generator回复或官方结果。

### Step 2：执行动作

Step 2 不是第二个 PM，也不重新判断开关。它接收 Step 1 已冻结的 joint action 和 exact candidates，构造成 typed resource program，通过当前benchmark的task adapter注入prompt，再由同一个冻结generator完成任务。RS/MP/MS/ME 的 source、owner、time和实际注入情况进入统一trace。

不同benchmark的任务prompt不可能逐字相同：ESC是支持回复，ES-MemEval还包含QA和summary。公平要求是同一任务内部各arm共享基础prompt和generator，只允许Step 1所选资源块不同；跨任务使用各自官方adapter，不能为了追求字面相同而破坏官方协议。

### Benchmark只是动作掩码不同

| Benchmark/task | 同一个PM的可用动作 | 结构性关闭原因 |
|---|---|---|
| ESConv、ESC-Eval strategy实验 | `M0+R0`或`M0+RS`；MP/MS/ME hard-OFF | 没有可归因的纵向私有记忆 |
| ES-MemEval QA、Summary | MP/MS/ME子集；RS hard-OFF | 不是支持回复任务，RS不可识别 |
| ES-MemEval Dialogue Generation（官方优先主分析） | MP/MS/ME子集；RS固定为同一基础条件 | 官方DG比较的是No-Mem、Full-History、RAG等memory settings，虽评价ES但没有RS策略干预 |

因此 ESConv 与 ES-MemEval 不是训练两个 PM，而是在两个结构上不同但互补的 observation/action slices 上训练和评估同一个 factorized PM。官方ES-MemEval Dialogue Generation可以检验memory选择是否改善长期记忆、个性化和支持回复，但**不能直接证明RS与三个memory heads的完整16动作联合策略**。第一篇论文当前也不主张独立识别strategy×memory interaction。

只有在ESConv、ESC-Eval和ES-MemEval官方主结果完成后，若“同一个factorized PM”仍缺少必要的端到端联合运行证据，才允许把ES-MemEval DG扩展为一个预注册的最小`RS fixed/off × memory policy`补充实验。它必须明确称为MetaCom adaptation，不得称为ES-MemEval官方条件；在此之前不激活完整16动作DG实验。

RS/MP/MS/ME 不再各自绑定一套项目自建“总及格门”。研究结果由公开 benchmark 的官方任务指标裁决，head 的价值通过同一官方指标下的 component-minus 消融解释。

## 3. 研究问题与实验一一对应

### RQ0：generator 是否具备完成研究的基础情绪支持能力？

- 考卷：ESC-Eval。
- 协议：公开英文高质量 role cards、官方五轮交互、官方 wrapper 和官方七维。
- 结果：完整报告七维、完成率、延迟、tokens 与费用；ESC-Eval 没有统一官方 pass line，因此不制造绝对及格分。
- 决策：在官方画像、可靠性与 Cost 的 Pareto 关系中选定一个 generator，并对所有 PM 与 baseline 冻结同一 generator。
- 不证明：PM 或 memory 有用。

### RQ1：学习型策略分配是否比不分配或非自适应分配更有效？

- 学习来源：ESConv 官方 train/dev 结构和策略标签。
- 基础检验：ESConv 官方 held-out 数据，把论文定义的条件（Vanilla、Random、Learned/Joint；Oracle 只作有标签上界）移植到同一个冻结 generator 和基础 prompt 下重新运行；不把论文旧模型的现成分数当成我们的因果 baseline。
- 外部结果考卷：ESC-Eval；保持同一 generator、同一 role card、同一交互协议，只改变策略资源的分配方式。
- 主要比较：无显式策略、频率/开启率匹配随机策略、学习型策略 PM；固定策略只作必要参照。
- 主要结果：ESConv 官方结果与 ESC-Eval 官方七维；Cost 单列。
- 可支持主张：学习型 strategy decision 对公开 ESC 任务有选择价值。
- 系统身份：调用统一 PM，但由 task mask 将 MP/MS/ME 机械关闭；不是另训一个“strategy PM产品”。

如果策略 PM 使用 ESConv 训练，ESC-Eval 中由 ESConv 派生的 role cards 不能承担独立迁移证据。完整 331 卡仍全量报告，但跨来源迁移的主要分析使用预先确定的非 ESConv 来源卡；若以后加入 ExTES 训练，则同时排除 ExTES 来源卡。

### RQ2：学习型记忆分配能否在长期记忆任务上取得更好的表现—成本权衡？

- 考卷：`ES-MemEval-Public-v1.0.0-1427` 的全部 1427 QA、125 summary 和 34 dialogue-generation scenario。
- 指标：仅使用对应任务的官方指标；QA、summary、dialogue generation 分开报告，不制造跨任务总分。
- 主要条件：把官方定义的 Full History、固定 RAG/top-k 和 No Memory 条件移植到同一个冻结 generator、官方任务 prompt 与 scorer 下重新运行，再与学习型 memory PM 比较。
- 主要结果：官方任务表现与 Cost 的 Pareto 关系。
- 统计单位：18 个 user；题目和场景是 user 内重复测量，不能当作 1427 个独立用户。
- 可支持主张：显式、类型化、状态依赖的 memory allocation 在公开长期记忆 benchmark 上具有系统价值。
- DG责任：QA/Summary测更客观的memory能力；Dialogue Generation在RS固定条件下比较No-Mem、Full-History、官方RAG和typed-memory PM，并使用官方observation指标与LT-Mem、Personalization、ES评分。它不承担四头16动作联合证明。

第一篇论文不要求“在完全未见用户上泛化”。允许同一长期用户在适应阶段与之后的评测阶段出现，这与个性化系统的目标一致；但评测 query、gold outcome 和未来 session 不得进入拟合。若官方 release 没有可直接使用的 train/test 划分，则采用用户内严格时间前缀→后缀，或按事实/事件组隔离的 outcome-blind cross-fitting。结论边界明确写成“在该公开 benchmark 的用户与任务分布上”。

## 4. 三个 memory heads 至少两个有用

这是第一篇论文的机制性要求，与系统整体主张不冲突：

```text
overall memory PM has a positive official-metric/cost result
AND count(useful(MP), useful(MS), useful(ME)) >= 2
```

`useful(head)` 不再由自建 Function judge 或主观 Quality 门决定，而由 ES-MemEval 官方结果上的预先映射消融决定：

1. 在看不到模型输出和 gold outcome 的情况下，把可评测实例按记忆语义映射到 MP/MS/ME eligible slice；同一实例可涉及多个 head，但必须在结果前登记。
2. 全系统与 `full-minus-head` 使用相同 generator、retriever 候选边界、prompt、decoding 和评测实例。
3. 被计为有用的 head 必须在官方指标上产生非零、方向正确的配对改善，且该改善在至少两个独立 user 或事实/事件簇中复现；其 eligible slice 的净效应不能由少数恶化案例抵消。
4. 同时报告 user-cluster uncertainty 和全部反例，不把题目数冒充独立样本数。
5. per-head 显著性可作为更强证据报告，但不是第一篇论文必须让三个 head 各自通过的四套旧门。

若官方数据无法形成某个 head 的足够 eligible slice，该 head 标为 `NOT_IDENTIFIABLE_ON_THIS_BENCHMARK`，不能用内部人评补成“通过”；论文仍须由另外两个 head 满足类型化贡献要求。

## 5. Baseline 的责任

Baseline 是实验条件，不是新评价体系。

### 三层证据不能混用

1. **论文已发表分数**：只作历史参考分布。原论文使用的 generator、prompt、上下文窗口和运行环境与我们不同，不能直接计算“我们的 PM 比论文 baseline 提升多少”。
2. **官方协议/代码 sanity reproduction**：用少量或一个代表配置确认 dataset split、prompt 拼接、retrieval、scorer 和指标方向与官方一致。如果模型revision、API或paper row身份无法精确恢复，就明确称为协议验证，不追求复刻每个旧数值。
3. **同栈 baseline rerun（论文主比较）**：冻结同一个 generator、基础prompt、decoding、候选历史、评测实例和官方 scorer，只改变资源分配策略。这一层才识别 PM 的边际价值，并完整记录 Cost。

因此，下一步不是复跑官方论文里全部 Mistral、Phi、GPT 配置。我们先验证官方管线，然后在最终选定的 MetaCom generator 上重新运行官方定义的 baseline 条件。

### 策略实验

- Vanilla / no explicit strategy；
- 与 learned PM 的策略频率/开启率匹配的 Random；
- Learned strategy PM；
- Oracle：仅在 ESConv 有 gold 策略标签的 held-out 数据上作上界。

### 记忆实验

- Full History / fixed-high；
- 官方固定 RAG/top-k；
- 与 learned PM 的memory类型、开启率和预算匹配的 Random，用来排除“只是少放context”的解释；
- Learned typed-memory PM；
- `full-minus-MP`、`full-minus-MS`、`full-minus-ME`，只用于 component accountability；
- No Memory：仅作允许且有解释意义的下界。

matched Random 是“学习型选择有价值”主张所必需的因果对照，但仍使用同一官方 benchmark 指标，不构成第三套自定义考卷。Transparent rule、六动作oracle等旧矩阵不自动恢复；只有它们回答额外必要问题时才增加。

### 公平运行时约束

- 所有正式比较使用同一冻结 generator/model mode、相同基础prompt模板、decoding、retry和输出处理；
- ESConv/ESC-Eval各arm只改变strategy policy给出的动作；
- ES-MemEval各arm只改变可见历史或检索/typed-memory policy，官方问题文本和评分prompt不变；
- 所有条件使用同一PM runtime与Step 2合同；benchmark只施加预先声明的task action mask，不替换成另一套policy manager；
- baseline可以拥有其定义所需的不同context量，这正是处理差异，但不能拥有更强generator或专属prompt优化；
- published score、不同generator的官方复现和同栈PM结果分表报告，禁止混成一张可直接排名的表。

## 6. 论文成功形态

第一篇论文成立需要同时看到：

1. RQ0 完成：选出可用且可复现的同栈 generator；
2. RQ1 正向：learned strategy PM 相对 Vanilla/Random 在 ESConv 与/或 ESC-Eval 官方结果上显示选择价值；
3. RQ2 正向：learned memory PM 相对 Full History/固定 RAG 显示更好的官方表现—Cost 权衡；
4. 三个 memory heads 中至少两个具有 ES-MemEval 官方指标上的非零、可复现边际贡献；
5. 所有结论使用正确的数据版本、训练/评测隔离和 cluster 单位。

不要求：临床安全或心理治疗有效性、真实用户长期改善、四个旧 head 在所有数据集分别通过、三个 memory heads 全部显著、完全未见真实用户泛化、策略×记忆交互的独立因果识别。

如果只有系统级 memory PM 正向、但不足两个 head 能被官方数据识别，系统主张可以报告，类型化 memory 主张必须削弱；不能用旧人评补强。

## 7. 不再执行的漂移路线

在两项官方核心实验完成前，默认不执行：

- 新的自定义 Quality/Risk/Function 总门；
- 为救某个 head 反复制造小面板、改 prompt、换 judge；
- 把 EvoEmo 当作第三个独立外部人群或必过主轨；
- 要求 MP/MS/ME/RS 在每个数据集各自 pass；
- 为追求完全未见用户泛化而增加无关训练工程；
- 在看到正式结果后修改 eligible slice、baseline、metric 或统计单位。

EvoEmo、旧同状态实验、原子 Risk 和 Function 审计继续保留。只有官方结果明确显示某项必要主张无法识别时，才允许提出一个最小、预注册的补充分析；它不能取代官方结果。

## 8. 从现在开始的落地顺序

1. 完成正在运行的 ESC-Eval English-331 官方协议生成与官方评分；在 Llama 3.1 8B 和 Qwen 3.7 Plus non-thinking 中选定研究 generator。
2. 先做 ESConv 与 ES-MemEval 官方数据/协议/scorer sanity reproduction；随后用选定 generator 同栈重跑官方定义的 baseline 条件及 matched Random，先确认数据、prompt、统计单位和成本账本完整。
3. 物化一个factorized PM接口：四个Step 1 head→task mask与joint projection→一个legal action→统一Step 2；复用旧MP/MS/ME候选编译、严格过去边界和cost accounting，废弃旧head pass gate。
4. 先完成 RQ1：ESConv 训练/held-out 检验，再在 ESC-Eval 非 ESConv 来源卡上评价策略选择。
5. 再完成 RQ2：ES-MemEval 全任务的 Full History、固定 RAG、learned PM 和 component-minus；MP/MS/ME eligible mapping 必须在结果前生成。
6. 汇总官方指标、user/dialogue cluster uncertainty 和 Cost，判断完整主张或诚实缩小后的主张。
7. 只有届时出现明确不可识别缺口，才讨论最小补充实验；ME 是否需要额外救援也在这一步决定。

任何 generator/judge/API 运行仍需独立 identity、费用上限和用户明确批准。本方案本身不授权新调用。
