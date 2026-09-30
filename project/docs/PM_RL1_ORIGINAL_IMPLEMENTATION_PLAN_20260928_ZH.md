# PM-RL1：单轮资源选择与执行学习——环境及训练实施方案

版本：2026-09-28；范围：第一版有限步资源决策。本文是研究与实现设计，不是已经运行的 RL 实验报告。

## 0. 最终建议与近期边界

近期研究只回答：给定当前对话前缀与合法历史，系统能否按需获取资源、正确使用，并改善当前回复质量、误用风险和资源成本之间的取舍。

一个 episode 从真实数据中的合法 pre-supporter 前缀开始，经历至多四次资源 GET，STOP 后生成一次回复、评分并结束。**没有模拟用户，没有下一轮用户话语，没有心理状态转移，没有跨会话写回，没有联合在线更新。** 使用多会话历史不等于研究多轮未来回报。

先训练执行器的监督适配，再冻结执行器训练小 PM。两模块都有真实训练与评价，但按阶段学习。旧四头及其结果继续保留；v3.1 作为长期路线图，当前不执行其中跨轮环境、seeker、重访和联合训练网格。

三项优先级：

1. 定义并验证真实的数据与程序转移；
2. 建立能分辨当前回复差异的评价证据；
3. 在这个环境上比较监督选择与有限步 RL。

如果可靠标签与有限计划监督选择已经解决问题，保留这个结果，不为 RL 名称增加无意义调用。若奖励只反映模型裁判偏好，结论必须限定为该代理目标。

## 1. 当前仓库与结果：本次审查依据

### 1.1 代码身份与审查范围

2026-09-28 重新查询仓库全部 11 个分支。活动分支仍为 `work/paper1-rq1-integration-20260816`，HEAD 为 `ba6917069cc6257ca8e64729509ce0f27e3cdc9b`，最后提交日期为 2026-09-17；`main` 为旧路线 `3c7e416a55aaca265fef63a39d9f101cde787f5b`。

重新枚举完整树 2,703 项、2,548 个文件；Python 文件分为：当前 paper1 源码 116、当前脚本 78、其他/历史源码 179、其他/历史脚本 535、测试 372、其他 4。目录名和数量不代表全部都是当前有效实现。

本次复用并重新核对上次 483 个相关文件的 Git blob SHA；发现本地审查副本的 `runtime_v7.py` 尾部不完整，已从同一 commit 重新取得全文，最终483个文件全部一致，未修改远端代码。沿当前入口重新检查关键数据、候选、检索、交付、评分、冻结、预算和服务路径，补查 6 个共享模块：`api.py`、`attempt_ledger.py`、`config.py`、`io.py`、`esc_rank_runtime.py`、`esc_eval_official_parser.py`。当前 paper1 的 194 个 Python 文件已做 AST/接口盘点；下述设计依据恢复后的完整版本。

这是一项覆盖当前研究链路、仓库结构和结果身份的系统审查，**不是逐行证明全仓库 1,284 个 Python 文件正确**。历史和已弃用合成训练数据没有重新读取或投入研究。未连接服务器、未执行完整 pytest/PyTorch/GPU 测试、未训练研究模型；不能将仓库里历史 checkpoint 当成当前四头或 RL 的已完成结果。

### 1.2 可确认的资产与限制

| 资产/结果 | 实际证据 | 本版处理 |
|---|---|---|
| 当前 Generator | Llama‑3.1‑8B‑Instruct，本地 BF16、固定权重/模板身份 | 复用基础模型，分别绑定固定指导和 LoRA 执行器 |
| BGE‑M3 | 固定检索、向量身份、相似度排序、ID tie-break | 保留候选排序，不先训练新 retriever |
| 来源 | 18 个虚拟 owner，401 sessions | 合成并人工审阅的公开来源；不是 18 名真实受试者 |
| 历史 MP / ME | 713 / 1,523；最终 profile slots 388 | 用历史版本重建切点视图，不能把最终状态倒灌过去 |
| MS | 完整历史会话原文 | 保留 raw 表示，不额外引入摘要模型 |
| ME 中行动—已观察结果 | 4 条；coping_attempt 374 条 | 主线研究一般事件、时序与合理使用，不声称学会个体行动疗效 |
| 编译 | 802 logical calls、804 attempts | 编译完成不等于资源实质有益；保留拒收/核验记录 |
| 四头 | 当前合同是 standardized L2 logistic；远端正式训练计数仍为 0 | 先核对服务器后续产物，不宣称已训练完成 |
| Gemini 资格 | 96 呈现，100 调用，92 有效，未获 material-effect teacher 资格 | 不继续把它默认用作 RL 奖励；不重做旧 96 题 |
| ESC-RANK | 24 题官方运行已完成；Overall 对人工 A/B 的 QWK 约 0.373/0.508 | 可作为独立测量来源之一，不能当无误真值或直接继承到新单轮任务 |
| 1,924 生成、1,631 unique scorer payload | 用户此前报告，未包含在本次可见的远端结果中 | 服务器逐请求验收，不能预设已具备可用 RL 标签 |
| 自然结束、Qwen 后续检查 | 用户此前报告本地有进展 | 不重复实现已修功能；先绑定真实版本与产物 |

较早的 QWK 0.7571 是人工之间的 Overall 一致性，不是 Gemini 资格或新奖励有效性。Qwen 换序一致也只能说明特定输入上的部分稳定性，不能直接证明本任务收益判断正确。

### 1.3 当前代码能复用什么，具体缺什么

以下路径相对 `project/src/metacom_pm/`：

| 当前文件/目录 | 已有能力 | 新版需要补充或修正 |
|---|---|---|
| `paper1/data/memory_source.py`、`materializer.py` | sanitized runtime，与 gold/原始标注隔离 | 新 `PrefixSpec`；原官方 Target.cutoff 是全部历史末端，不能用于中途前缀 |
| `paper1/multi_view_memory/candidate_adapter.py` | strict-past、owner/span 检查、先过滤再取 profile 最新版本 | 新切点适配；同 rank 冲突保留；不能简单把后一次提及当成事实更正 |
| `paper1/execution/packing.py` | 固定排序、精确 Top-k prefix、超预算不截断 | 组合计划、逐步 GET、合法动作 mask、总预算 |
| `paper1/execution/step2.py` | 单头 typed bundle、完整交付、非采用不删样本 | 复合 ResourcePlan；固定指导/LoRA 身份；执行训练 |
| `paper1/execution/visible_state.py` | outcome-blind projection | 单轮完整公开前缀、已取得证据及预算的 observation；不直接沿用仅当前句的旧 DG 输入 |
| `paper1/embeddings/*` | 固定模型、向量/cache identity | 已取得正文可见性、PM 特征缓存与在线编码成本 |
| `paper1/evaluation/official.py` | 规范已产生的官方指标 | 它不是实际评分 runner；必须绑定真正调用方 |
| `paper1/evaluation/effect_coding.py` | ON/OFF/equivalent/uncertain/invalid 语义 | 新连续代理 reward 独立命名；旧 uncertain 不能填 0 |
| `paper1/core/treatment.py` | 分配/交付检查 | 严格检查损坏、多余块；旧解析会跳过部分损坏块 |
| `paper1/core/threshold.py`、latency 模块 | 旧部署阈值、成本与延迟合同 | 新策略沿用记录方式，不能把旧二元阈值当 RL Q 值 |
| `api.py`、`attempt_ledger.py`、`paper1/api_budget.py` | 调用、身份、失败与成本记录 | 所有 runner 共用原子预算；不直接套旧 $50 常量 |
| `scripts/paper1/46_serve_local_llama31_reference.py` | 冻结模型推理服务 | 远端只支持 greedy 与有限 cap；核查本地自然结束、adapter、seed 与真实 finish reason |
| 当前 paper1 learner/env | 无本版完整实现 | 新 env、reward runner、训练器、冻结和评价入口 |

此前离线反例说明：损坏 resource block 可能逃过 OFF 验证；两个未协调旧账本实例可各预留 $30；actual 超出 reservation 时旧类会抛错而未记实付。这些是实现风险，**不证明历史实验污染或账单超支**。现有部分 runner 有外层锁，要检查所有新调用路径是否处于同一事务域。

## 2. 新研究与旧研究的关系

旧 Paper‑1：四个二元收益头、其他资源 OFF 的一阶对照、统一校准剂量、冻结执行器、任务分开的官方指标。旧结果继续按旧定义解释。

PM-RL1：当前轮内多次资源动作、按情境决定量、允许有限跨类型组合、以当前回复效用与资源成本训练；另训练 Step‑2 的监督适配。属于用户本轮已明确要求的后续研究范围，不再次询问是否允许研究动态量/Step‑2。

创建独立 `pm_rl1` namespace 和 scoped amendment，写清旧条款变化、影响产物及需重算范围；不要改旧 JSON 以假装旧测试全兼容。本次设计和免费工程工作已获用户方向授权；具体付费批次仍须核对既有适用授权与实际清单。

三项正式问题：

- RQ-S：相同来源/执行器/预算下，情境化与顺序资源策略是否优于固定取量和一次性计划？
- RQ-X：Step‑2 训练是否降低误用、提高资源增量，而不只是提高无资源回复能力？
- RQ-SX：执行器变化后资源价值是否改变；分别适配的 PM 是否比直接换配更合适？

本版不回答长期心理效果、模拟用户有效性、多模态状态估计、最佳心理治疗策略或联合 RL 优越性。

## 3. 先行研究：采用什么，暂不采用什么

| 研究 | 采用的具体内容 | 不直接采用及原因 |
|---|---|---|
| ES‑MemEval / EvoEmo | 公开历史、时间/更正/弃答任务、QA/Summary 评价入口；在原始 session 内构造合法前缀 | 不把完整作者背景、未来 observation 或全局摘要给 actor；原多轮 DG 不作为本版环境；论文 1,209 QA 与当前公开 1,427 版按 artifact 分清 |
| ESC‑Eval | 支持质量维度、盲评方法、已有 ESC-RANK 运行基础 | 不启动 ESC‑Role；完整对话评分不能自动变成当前最后一句的可靠奖励。改 prompt 后是新测量协议，不称官方原协议 |
| ESCA | 把策略/执行分别研究、监督训练后再优化的顺序、资源与执行协作的问题意识 | 其 RL 动作是连续 soft prompt，用户由 LLM 扮演、奖励偏策略执行；不直接移植为资源 GET 奖励或最佳 PPO 证据 |
| RLFF‑ESC | 训练奖励与独立评价分开，未来反馈需要单独构造与验证 | 不采用未来轨迹模拟、未来情绪奖励模型或 GRPO 回复训练；当前缺口并不在这些部分 |
| Value Reinforcement | supporter 明确判断参考是否适用；使用/不使用参考的对照和训练覆盖；SFT 思路 | 其 DPO 奖励使用后续 seeker 中目标价值的出现；本版不复制这个未来信号，不把资源采用率当收益 |
| D²RCU | 区分示例检索与生成利用，保留检索相关基线 | 不增加 COMET/认知图作为当前用户事实；动态检索的动机不证明余弦相关就是有用 |
| CASE | 认知/情感表示可以影响回复的相关工作 | 不拿其 latent 表示当真实心理状态或状态转移真值；本版不新训该模块 |
| Self‑RAG（补充） | 分开监督检索需求、相关性、证据支持和生成效用；反思行为可以用监督训练 | 不把模型自评当真值；不默认引入新 token、beam search 和全套训练栈 |
| Active Feature Acquisition（补充） | “继续买信息”或“停止并预测”的有限步决策、集合式观测、成本目标 | 分类标签比开放式支持回复更明确；不能据该文推定本项目 reward 已可靠 |

判断：本版最直接借鉴的是**可付成本的信息获取＋终局任务表现**，情绪支持论文提供任务、执行与评价背景；它们没有替我们解决本任务的标签有效性。

## 4. 数据构造：不生成用户未来

### 4.1 三个分开的数据用途

1. `legacy_dose`：服务器验收后的旧 QA/Summary 等剂量表。用于旧路线收口、缓存兼容分析和环境机制检查；不能自动当自然支持任务的正式训练数据。
2. `natural_prefix`：本版主研究。从 EvoEmo 原始当前 session 中选一个 seeker 发言之后、supporter 回复之前的切点。当前 session 公开前缀给模型，之前完整 sessions 才可成为记忆候选。原后续文本一律隔离。
3. `controlled_diagnostics`：有明确答案的来源/更正/未知结果/冗余/互补测试。优先从真实公开来源作可追踪干预；必要程序构造单列诊断，不冒充自然训练用户，不复活已弃用合成目录。

ESConv train 用于 RS bank 及必要执行示例；ESC‑Eval 角色卡维持旧正式评价用途，不转作本版训练池。RS 排除当前 dialogue 及已识别 seed 重叠；EvoEmo 的派生来源与 ESConv 有交集，必须记录重叠关系。

### 4.2 切分和数量是先验上限

复用已实际冻结且兼容的 owner split；否则沿 v3.1 的 `sha256("pmseq-v2-owner|"+owner_id)` 排序，12/3/3 train/dev/test。所有派生样本随 owner、原 session、源事实家族整体分组；不为当前版本重抽到有利 split。

核心上限：96 train prefixes（12 owners 各最多8），24 dev（3 owners 各最多8），48 test（3 owners 各最多16），同一 session 最多一个主 prefix。先完成免费 census：每 owner 合法 session 数、候选类型、token、纠正/意向/结果覆盖；不足则下调共同规模，不能读取未来或复制近似样本补满。

当前 session 至少有一次用户发言；记忆实验至少有一个已完成的过去 session。切点按固定 hash 选，不能根据生成质量选“容易有收益”的前缀。控制场景与自然场景分开报告；训练/开发已看到的同事实改写不进入 test。

只有三个 test owners，结果必须呈现逐 owner 效应。样本、PM seed、生成重复不是新的独立用户。其结论是本来源分布的受限验证，不能声称广泛人群泛化。

### 4.3 来源与可用时间

`available_at` 是信息首次可被系统看到的时间，不是事件发生时间。先做时间过滤，再解 MP 版本；当前 session 的公开更正优先用于理解旧记忆，但不能据未来更正重建过去视图。

保留 713 条历史 MP 和 1,523 条 ME；不从最终 388 slots 倒推切点。MS 保留完整原始 session，禁止静默摘要或截断。相同时间的冲突版本保留歧义；过去的意向不会自动转为“已执行”，更不会转为“有效”。

来源文件/完整 gold 只在构造与评价权限域；actor、critic、G 使用明确投影。继承旧数据的研究暴露清单，原来被人工/模型反复查看的项不能重新命名为 sealed test。

## 5. 环境的精确定义

### 5.1 Episode 与不变对象

每个 episode 固定：公开前缀 x，切点 c，合法候选库存 I，排序/渲染/模型版本 v，预算 B，最大 GET 数 K，执行器 X，生成随机规则，以及评价合同 J。

I 是固定 BGE 排序的 RS/MP/MS/ME 列表；取资源不会重新检索、改变 query 或更新世界。当前用户文本在 episode 内不变。没有在线 memory writeback。

环境内部状态记为 `s_j=(x,c,I,n_j,E_j,B,K,j,v,phase)`：

- n_j：四个类型各已经取得多少条；
- E_j：已取得、将完整交付 G 的有序资源集合；
- j：已执行 GET 次数；
- phase：acquiring / pending_generation / pending_score / terminal / technical_failure。

完整候选正文在环境内部存在，不代表 policy 可以读取。gold、评分和未来文本不属于可读观测。

### 5.2 Actor/critic 的 observation

允许：当前公开对话前缀；已 GET 的正文与来源时间；四类计数；剩余 token/GET 预算；每类剩余数量；每类前4条候选的冻结 similarity/rank/token length/coarse age（缺项有mask）；合法动作 mask。初始时还提供共同的可行终值计划mask，最多70位，由环境按真实完整渲染计算，不含质量信息。OneShot与顺序策略都能看到同一份初始metadata和可行计划mask，避免只给OneShot额外的预算信息。

禁止：未 GET 正文或向量、evaluation-only source answers、原后续回复、未来 session、质量标签、reward model 分数、owner ID/target ID/分组 ID、隐含“值得取用”的离线老师标签。

未 GET 候选的 metadata 及可行性确实可能编码一些内容信息：它们是预声明的合法观测，不把这种情形宣称“检索前完全无信息”。生成 metadata 和枚举可行计划的实际开销也计入；这项程序/tokenizer计算不需要为70个计划生成回复。

actor 与 critic 共用同一权限投影，不使用 privileged critic。数据类不得把完整 EpisodeSpec 传给网络，让调用方自行挑字段；返回白名单 observation DTO。

### 5.3 这是哪一种状态问题

完整环境的 GET 转移由程序确定；对 actor 而言，未取得资源正文仍不可见，所以可表述为**有限时域、部分观测的信息获取任务**。部分观测对象是资源内容，不是一个臆造的心理状态。

初始分布ρ是冻结split内的owner平衡前缀抽样，不依据策略得分改变。GET的转移核为 `T(s'|s,GET_h)=1[s'=F_h(s)]`；观测核为程序投影 `Ω(o|s)=1[o=Project(s)]`。STOP的结果由固定生成器的实际输出分布与固定评审协议决定；greedy配置也需保存runtime差异，不能假定跨硬件逐字确定。没有需要从心理标签拟合的T或Ω。

在排名和库存固定、每次 GET 承诺交付、当前文本不变的规则下，所有已经取得的内容＋初始 metadata＋计数/预算记录了动作历史中的有效信息。采用规范集合表示即可；首版不需要跨轮 GRU 或心理 belief network。文本编码仍是有损近似，不能据此声称数学上已获得完全 Markov 的低维充分统计量。

## 6. 动作与确定性转移

### 6.1 首版动作

`STOP=0, GET_RS=1, GET_MP=2, GET_MS=3, GET_ME=4`。

各类最多取4条，**总 GET 最多4次**，因此至多5个决策点（包含最后 STOP）。QA/Summary 的旧兼容测试固定 RS OFF；自然前缀允许四类。第一版不增加任意 item-ID 选择、重排、删资源、改 query、草稿重写或自问自答动作。

GET_h 取该类尚未取得的下一条，取得后承诺完整交付给 G。Step‑2 可以语义上不采用，但不能把该条从 prompt 删除、退还 token 或改称“没有取过”。上一轮讨论的“排除资源”在本版落实为合理不采用；显式丢弃/重排是后续单独动作协议。

这版主要学习类型、数量、组合和停止，不保证找出所有候选中的最佳任意子集；相似度首条不合适且挡住后续资源，是明确限制。

### 6.2 合法性与预算

资源预算初始候选 B=2,048 个 Generator tokens，包括整块说明、来源、分隔符、正文；同时检查完整 chat template/context 容量。此数是工程起点，不是实验结果。先用无 outcome 的容量 census 检查1,024/2,048/4,096档；若需变更，在任何新效果标签前统一冻结。主实验所有方法同 B。

GET_h 只有下一条存在、j<K、完整新增计划不超 B/上下文时才合法。rank1 超预算时不能偷偷跳到 rank2；该头当前 mask 为 false。非法动作必须报协议错误，不自动映射 STOP 或返回有意义的负样本。

STOP 始终合法，E=空即无资源。K 达到4或没有合法 GET 时只剩 STOP；这是研究任务的正常终止，不是 timeout。不得再另加一次“第5条探测”。

完整四类、总量≤4时最多70个终值计数计划；三类 memory 最多35个。它们只是理论上界，预算/候选缺失后更少；不同取得顺序不应制造额外终值 treatment。

### 6.3 转移函数 T

GET_h：

1. 验证旧 state hash、action mask、episode/version；
2. 从冻结 I_h 取索引 n_h 的真实条目；
3. 更新 n_h、E、j，按固定 RS→MP→MS→ME 与类内 rank 渲染；
4. 重新计算真实 tokens 和新 mask，返回新的公开 observation；
5. 记录 transition receipt。**不调用 LLM 来想象新状态，不产生用户反应。**

STOP：

1. 冻结 plan 与完整 prompt；
2. 用冻结 X 实际生成一次回复，或读取身份完全一致的已生成训练缓存；
3. 完整性检查后交独立评分接口；
4. 保存原始回复、评分/证据及成本，返回 reward，episode 结束。

任何评分缺失进入 pending/technical_failure，不能用 reward=0 冒充成功。训练中的缓存是“已观测终局反馈的复用”，不是一次新独立生成，也不是部署延迟测量。

## 7. Step‑2：研究对象与环境部件的边界

X_b 为对应新版输入的旧 typed 指导适配基线；X_g 为固定指导、原模型；X_l 为与 X_g **逐字同推理提示**、增加监督 LoRA 的执行器。

MP/MS/ME 已有来源和时态指导，不能称新创。RS 旧提示要求表达所分配 moves；若允许合理不采用，必须替换冲突句，不能同时要求“必须表达”和“可以不用”。

训练样本：同一合法 prefix 下，OFF、预先判定相关的合法资源、合法但低相关/冗余资源。低相关不等于无效真值，最终仍测实际输出。不得把 wrong-owner 或未来信息当正常输入以凑负例。

初版上限96 train＋24 dev prefixes，每个3条件、2候选。teacher 使用条件内真实可见输入；来源/质量核验只接受有证据的回复。每条件至多一次修复。正确使用和合理不使用都可为好答案。明确标为弱监督，不把模型核验叫人工真值。

执行训练默认 LoRA r8/alpha16/q_proj+v_proj、BF16、dropout0、lr1e-4、microbatch1/accumulation16、最多3 epochs、seed17；只对当前回复与 EOS 计算损失。按 dev response NLL 选 checkpoint，生成诊断另报；NLL 不证明资源利用提升。若接受数/来源覆盖不足，最多扩96个新 train prefixes，规则在 test 前按数据覆盖决定，不因结果没有正收益就不断补样。

先训练再冻结 X_l，之后 PM 的采样批次中 X 不改变。X_g/X_l 各自绑定终局缓存与标签；来源/候选可共享，回复和 reward 不可跨执行器继承。X_l 无提升是有效负结果；未训练成功不是同一结论。

本版不训练 LLM token-level PPO/GRPO，不引入 online joint learning。Step‑2 合理不使用资源并不自动使 Step‑1 的选择正确：取得后没用仍然可能是浪费。

## 8. 奖励测量：最大的实际缺口

### 8.1 四层必须分开

1. 来源/时间合法：程序与 source span 核验。
2. 内容相关/适用：与当前需要的关系，需要语义判断。
3. 输出是否误用：事实、时间、人物、意向、已观察结果、边界等。
4. 最终增益：同一执行器下，相对无资源或另一计划，回复是否更好。

原 Gemini 资格不足、现有 ordinal 分数有压缩和裁判误差，不能把 old effect labels 直接连上 PPO 就宣称 reward 可信。

### 8.2 主线 reward record

自然支持任务使用一个新绑定的本地 current-turn evaluator：一次调用联合返回 q、misuse、证据与不确定性；不新增一套 LLM reward model 的梯度训练。

`q ∈ {0,1,2,3,4}`：0 严重失配/不能使用；1 明显问题；2 基本回应但存在重要不足；3 贴合、连贯、适当；4 充分回应当前需要并尊重已知约束。只评价新生成的当前回复，相同历史作为语境；不能用此前优质原文把末句错误平均掉。分数是训练效用编码，不假设人类效用天然等距。

`m ∈ {0,0.25,1}`：0 未发现资源相关误用；0.25 局部不影响核心建议的失准；1 实质性误用，如把未执行说成已有效、把过时限制当现在、将示例人物当用户、违背当前明确边界。所有错误带 response span、source span 与理由；unsupported/contradicted/uncertain 分开。没有声称事实时 precision=NA，不自动“资源使用满分”。

同一评价材料构造规则用于所有 arms：x＋严格合法历史形成的评审证据＋被评价回复。评审可读完整合法证据来发现未取资源造成的遗漏，但看不到策略名、k、相似度、成本、训练 seed、Ours/baseline。actor/G 不读这些评价侧材料。

m衡量输出中的资源相关错误风险；另记来源本身语义错误、检索不适配、生成扭曲、合理不采用、遗漏及无法确定的归因。若G忠实复述了一条编译错误的资源，不能仅因最终回答错了就断言是执行器误解。相同合法资源条件的配对实验用于减少这类混淆。

若评审证据超出可用 context，先解决统一证据组织或标测量缺失，不能只向裁判提供某个方法取到的资源。无足够依据的错误或质量判断保留 uncertain，不填0。

### 8.3 必须先做的小型测量检查

从 train/dev 取12个真实前缀；每个构造4个回复：真实无资源/真实有资源、对其中一个做单点来源或状态损伤、内容保持的风格改写，共最多48个 score payload。自然差异是主体，故意损坏控制不是全部证据。

检查：格式完整；来源证据能被复核；明确损伤是否被识别；风格变化是否无故主导；普通资源差异是否全平局；长回复是否得到无依据高分。预选12个 payload 重复一次只测稳定性；独立人工/不同评审盲看12个配对用于定位具体偏差。人和模型的审核身份分别记录；没有人工时不得声称 human validation。

只允许一次针对明确问题的 train/dev rubric 修订，旧新版本不混标。不得按 PM 得分最高选 evaluator。没有足够分辨率时先做来源/执行错误研究；环境工程继续可完成，但不扩大“有帮助性优化”的 RL。

这不是重做旧96题。是新任务的小型测量诊断；不存在自动保证可信的样本数或一致性阈值。需要扩大人工证据时先交付具体待审材料与其要支撑的主张，不要求用户先批准抽象大项目。

### 8.4 训练奖励与正式测量分开

J_train 固定本地模型、revision、prompt、decode、parser；X teacher 和 J_train 若同家族明确披露。正式保持独立来源核验和一份冻结的盲审子集；ESC-RANK 可作能力范围经检查后的补充维度，不能把新单轮 prompt 叫官方 ESC-Eval 复现。

正式盲审的起始上限为24个配对：12对比较同资源下X_g/X_l，12对比较X_l下RL/OneShot；按3个test owners平衡、按hash选取、PM seed在结果前轮换，均隐藏方法身份。优先由独立人工做来源及适当性判断；若只有独立模型则准确标明。24对只是有界证据补充，不能保证统计充分或据此声称人类普遍偏好；评审不回流训练。

可选小型官方 QA 外部验证：最多48个 outcome-isolated test targets×OFF/Fixed/OneShot/RL，共192个答案，用原官方 scorer；不需要 seeker。训练所有自然支持 reward 不用官方 API。QA 改善不能替代自然支持质量证据，旧完整 Paper‑1 官方对照另行收口，不与本版范围混同。

无独立有效评价时，最终只能说模型学会优化已声明的代理，不说已经提高真实支持效果。

## 9. 奖励函数与信用分配

令 `U_X(x,E)=q_X(x,E)/4 − α m_X(x,E)`；初始 α=1，表示重大误用的惩罚与完整质量区间同量级。这是研究者定义的偏好，不是数据推导的心理常数。

令 c(E) 为规范渲染后完整资源块的 G-token 数，空集为0；B 为共同 cap。初始 λ=0.05，γ=1。

```
GET:  r_j = -λ * [c(E_next) - c(E_now)] / B
STOP: r_j = U_X(x,E_final) - U_X(x,empty)
```

于是完整回报严格为：

`R = U_X(x,E_final) - U_X(x,empty) - λ*c(E_final)/B`。

无资源基线每个 prefix×executor 只实际生成并测量一次，按完整身份缓存；在部署时不额外生成无资源答案。它在同一 episode 的所有动作计划之间是常数，因此不会改变最优计划，但有利于解释资源增量。若基线缺分数，先进入待处理，不把基线当0。

STOP 不再扣第二次资源成本。tokenizer 的组合长度并非数学保证逐条单调，因此保存精确差值；无删除/重复 GET，状态无环，不存在来回领 token 奖励的路径。若改为非负逐次付费成本，必须重新定义总目标，不能一面裁差值一面声称上述等式仍成立。

不把“相邻 k 的质量差”作为免费的 GET 奖励：它需要额外生成，而且第1条暂时没收益不意味着第2条无法形成互补。GET 后不调用 G/J，只有 STOP 时实际生成评分。γ=1 保证多一次 GET 不会额外折扣最终质量。

λ 从小规模 dev 的质量/成本量级检查，不按 test 调整；初版不跑大网格。α、λ、评分锚点、技术失败规则需在真实训练前冻结。正式分别报告 q、m、质量增量、实际 tokens、延迟，不能只报混合 R。

真实延迟首版不直接放进 reward：排队、加载、输出长度、并发噪声会混入硬件负载。先测端到端与各段成本，之后有稳定预测器再做独立 latency-aware 扩展。该版直接优化的是资源输入成本，不承诺实际延迟必降。

其他计费/计算（PM 编码、固定检索、G 输出、训练 scorer、加载交换）全部记录。不能只报告 c(E) 就声称总算力减少。QA/Summary 若做环境桥接，仍用各自任务测量；不同任务数值不混成共同论文总分。

## 10. 可控、可审计与可信分别怎样验证

### 10.1 必须有的记录

PrefixSpec、SourceSnapshot、Inventory、Observation、ResourcePlan、TransitionReceipt、PromptReceipt、GenerationRecord、ScoreRecord、EpisodeRecord、FreezeManifest。

每个包括 schema/version、输入 hash、来源、模型/提示/解码身份、seed、状态及父产物 hash。ID 用于审计，不输入模型。TransitionReceipt 保存旧/新状态 hash、实际 action、mask、取到的 item、完整 tokens 与 reward 分项。

审计trace与给learner的 `info` 分开存放，防止vector-env wrapper把完整inventory/gold附加到网络输入。`reset()`只返回公开observation与无敏感审计ID；`step()`在GET后不给任何预计算终值分数；技术故障的状态通过明确异常/状态通道返回。

### 10.2 机械检查

- source-span、owner、切点、available_at；MP先过滤后解析版本；当前可见修正不会被旧记忆覆盖。
- 替换未来/gold/作者注释不改变公开 observation、候选和 prompt。
- 固定 metadata 后替换未 GET 正文，不改变当前 actor 输入；GET 后该内容才出现。改变正文并重新检索引起 metadata 改变是另一种合法测试，不能混淆。
- 同集合不同 GET 顺序得到同 G prompt；动作 mask/实际内容一致；不跳 rank、不丢包、不重取；OFF无额外块。
- 精确总 token cap、上下文容量、forced STOP、非法动作拒绝。
- 任意合法路径的累计 reward 等于第9节终值目标；终局不得 bootstrap。
- 保存/恢复后相同身份不重复调用、不重复训练更新；同一 batch 不换 X/J。
- actor/critic feature canary：gold、score、owner/arm等字段无法通过数据类进入网络。

### 10.3 行为与测量检查

- 确定有害的来源误用能够被定位；修复该错误后评分方向合理。
- 正确但没帮助、相关但有害、合理不使用分别存在，不能只学“资源多就好”。
- 明确遗漏必要信息会影响质量；沉默/空泛回复不能靠低事实错误获胜。
- 保存置信与不确定样本，不把 uncertain 全部筛成伪负例。
- 训练 reward 提高后，独立评价和来源错误是否同步变化。

工程可重放不等于评价有效；评分模型间一致也不等于用户收益。两份检查报告分别出具。

### 10.4 技术失败与语义失败

生成器正确收到资源但忽略/误用/回复差：有效实验结果，照常保留和处罚。错 owner/future 注入、prompt 错配、空生成、未完成截断、不可解析评分：技术失败，不能当0分终局。

每请求最多一次同身份恢复/重试；失败和 UNKNOWN 不无限补样。PPO 的 reward 未齐全 episode 不进入 actor/critic 的整条损失；保留尝试计数与有选择缺失的局限。正式报告完成率、missing 和失败敏感性，不能只看 complete-case 胜率。

若采用 Gymnasium，正常 STOP/预算规定的结束为 `terminated`；非任务定义的中断为技术截断/异常，另有结构化状态。**不要对“缺失 reward 的失败”套普通 time-limit bootstrap。** 超时之后是否收费/是否后台仍生成由运行器恢复，不能在 env 中猜测。

## 11. 先建立可验证的非 RL 基线

### 11.1 单头完整剂量表是第一座桥

对一个固定 head、prefix、executor，k=0..4 的反馈若齐全，整条停止路径只有5个可能终值。可精确算出哪个终值最优、每一步继续与停止的目标；这是检查 reward、停止规则和训练器的理想小环境。

精确最优只供 train 教师或 sealed 后的 oracle 诊断；测试部署不能读取各 k 的真实分数。单头相邻量的实测差异可以诊断，不意味着线上策略可以免费读取。

全部动作反馈已知时先用监督学习获得情境化剂量选择。称它为离线计划/监督选择，不能因把表格包进 env 就声称 RL 比监督更省标注。

### 11.2 一次性计划对照

OneShot-Dose 使用与顺序策略相同的初始公开前缀和 metadata，一次预测终值计划。最大动作集合与 RL 可到达集合相同，排除预算不可行项；不能让它只选5个计划而 RL选70个，再把差异全部归因顺序观察。

用 train 中实际测过的 `(prefix, plan, q, m, cost)` 拟合效用预测器；未测计划不是0，也不是负例。特征可包括各类型剂量、相似度/长度及乘积项，但不偷看未 GET 正文。小样本中未测组合属于外推，需如实报告。

最终 OneShot 与其他静态基线可以使用相同 executor 下**本轮所有训练方法已获得反馈的共同 union**，并报告数据来源；这样不让 RL 独占更大标注集。dev/test反馈不加入该包。另记录在线探索总调用与各方法的训练成本，不把自适应收集数据当无选择的总体样本。

## 12. RL 训练方法：一套小策略，不先做算法网格

### 12.1 主建议

真实有限步训练首选 **masked feed-forward PPO**，取消上一版跨轮 recurrent PPO 的 GRU 和长轨迹状态。原因是：动作只有5个、每条最多5个决策点、实际 reward 来自冻结 X/J；on-policy 更新边界清楚，避免第一版把离线缺标签、Q值外推和循环 replay 一起引入。

这不是 PPO 最优的理论判断。Double DQN 适合离散动作且能复用 transition，值得后续在真实调用成为瓶颈时研究；它需要特别检查未测动作的 bootstrap 和过估计。GRPO/token-level RL 不适合作为这一步小资源策略的默认实现。只因为 ESCA 用 PPO 或 RLFF 用 GRPO，不能决定本项目算法。

缓存让已测终值可以反复用于采样，但缓存不让旧策略的动作 log-prob 变成当前策略。每个 PPO batch 的动作轨迹必须由该 batch 的冻结 behavior policy 重新采样；旧轨迹仅用于监督初始化/诊断，不放入未经校正的 PPO surrogate。

### 12.2 网络与信息

冻结 BGE‑M3；公开前缀编码＋已取得条目编码（按类型/rank最多4 slots并保留mask）＋原始 metadata/预算进入128维投影和两层128宽 MLP；5维 policy logits＋1维 value。相同 acquired set 用规范顺序编码；不输入 retrieval-order 决策路径作为额外暗示。

全部标准化只fit train；owner/target/schema hash等不是网络特征。编码器不更新；已取得文本的编码可按identity缓存，但线上也必须在合法取得之后才释放给actor。缓存命中不代表真实首次部署编码成本为0。短前缀/条目长度上限、截断/分块规则在首次训练前统一冻结，不偷偷裁掉关键证据。

### 12.3 共同初始化与训练额度

首批24个 train prefixes，按owner平衡。每个最多15个计划：OFF 1、四类k1和k2共8、六种两类各Top1组合共6。X_g/X_l分别真实生成和评分，最多720个终值反馈对。低覆盖/超预算计划标不可行，不补0。

利用这些**已测**终值建有限支持图，做 masked BC 初始化：只在能到已测终值的路径产生监督，合理并列保留。不得把未测 STOP 标负、也不得把未测组合填0。这个支持图是初始化来源，主 RL 仍可在合法动作域探索其他计划。

P_g 在 X_g 上训练；P_l 在 X_l 上训练。网络、train/dev来源、初始seed、batch和 episode 额度相同；BC标签分别来自对应X。该比较包含监督与RL整体适配，不能独立声称在线RL再适配贡献。

默认各128 episodes×3 seeds（17/29/43），合计768训练episodes；初始32同身份 smoke可计入128。均匀owner→该owner合法prefix抽样，所有重复标明不是独立样本。128是预算而非收敛保证；零信号/极低动作熵先诊断，不自动扩量。

PPO起点：Adam lr3e-4、clip0.2、γ1、GAEλ1、value系数0.5、entropy0.01、grad clip0.5；16完整episodes/batch、4epochs、每minibatch4episodes。每个batch全部 reward 齐备后更新。forced STOP不计policy/entropy损失，可计value；初始化中未拟合的critic不得伪装已知oracle。

开发评价只在64与128，各用同24dev前缀；主比较固定128终点，不各挑峰值checkpoint。训练前若计算预算不足，所有组统一降64×3并写清；不看test后延长落后组。第二RL算法不是近期必做。

### 12.4 开真模型前必须验证的学习行为

程序构造 E0：包含无需资源、取一条即可、首条暂时无收益但两条互补、错误/冗余资源、预算阻止行动等案例。真实训练小策略，而不只断言 reward 算式；与随机/Always STOP/精确DP比较，记录3seeds曲线。

检查合法动作概率、log-prob重算、参数真实变化、critic target、γ=1 credit、终局无bootstrap、保存恢复与相同batch版本。若PPO无法在可解小任务学习，先修实现；本次文档检查没有替代这项服务器训练验收。

## 13. 正式实验的最小结构

### 13.1 执行实验

48 test prefixes×OFF/相关合法/低相关合法三条件×X_b/X_g/X_l三个执行器，最多432个回复。相关性在生成前冻结；缺条件如实记录。X_g/X_l同提示，事实/适用性与q分开评价。

比较无资源能力、资源增量 `q(E)-q(empty)`、重大误用及不采用。X_l在OFF也提升但资源增量不变，不能说学会了更强资源利用。单个SFT seed限制结论稳定性；若执行训练成为强主张，优先复现实验seed，而不是先增加第二RL算法。

### 13.2 策略与执行交叉

| 方法 | X_g | X_l |
|---|---|---|
| No Resource | 1 | 1 |
| Fixed-Dose（dev选） | 1 | 1 |
| Matched Random（dev定分布） | 1 | 1 |
| OneShot-Dose（对应X训练） | 1 | 1 |
| P_g | 3 PM seeds | 3 PM seeds |
| P_l | 3 PM seeds | 3 PM seeds |

共20个checkpoint/策略实例×48 test prefixes=最多960个回复。Fixed包含在共同动作/预算域中；匹配随机按dev的类型/剂量分布构造，test实际成本仍需报告，不宣称精确等成本。旧四头若已有可比checkpoint，可增加补充行，不能用新proxy冒称旧模型。

与执行实验只有完全相同输入/模型/解码的请求才去重。去重共享结果保留统计相关性；不同seed/重复目的不能随意合并。

### 13.3 可得结论

- RL超过Fixed但未超过OneShot：说明自适应资源计划有价值，尚未证实逐步观察/继续决策的额外收益。
- RL超过同数据、同动作域OneShot：支持本设置下序贯信息利用价值；还需排查模型容量、优化与可见信息差异，不能只由算法名称归因。
- P_l/X_l超过P_g/X_l：支持针对执行器重新适配的整体价值。
- X_l资源增量与来源指标改善：支持所测分布上的利用改善。
- 训练reward涨而独立评分不涨：代理优化成功，真实任务收益未证实。

主结果包括质量、误用/伤害、正收益捕获、无效取用、ON/GET分布、tokens、全链延迟和失败。正收益捕获与local regret只在有足够成对反馈的诊断子集定义；未测全计划不称全局oracle。无正收益分母记NA。

## 14. 统计、复用与测试暴露

前缀内配对；同owner、session、事实家族有关联。先按owner汇总，再报告PM seeds和逐owner差异。3个test owners的cluster区间很不稳定，不能靠960回复冒充960独立用户。

Ordinal q 报原分布、配对胜/平/负与均值敏感性；不能只用“无显著差异”宣布质量等效。等效/非劣主张需预先解释的margin和足够证据。事实误用率需明确分母（全部回复/有事实回复/断言数），避免不说事实获得虚假优势。

只改统计→复算；只改parser→从raw重解析；改J→原回复重评分；改X/prompt/资源表示→重生成受影响回复；改cutoff→重新构造相关后代。正式test一经打开记录exposure；基于其结果改设计后不能继续称同一池未见确认集。

缓存键至少包含source/prefix/cutoff、inventory、canonical plan、完整prompt、G权重/adapter/tokenizer/runtime/device/decode/seed。scorer键另含完整证据、rubric/model/parser与measurement draw ID。编译、检索、G、评分分别缓存，禁止一个模型名包办身份。

## 15. 计算与API：先核对清单，不先消费

核心推理都可计划走本地；是否有合适的训练裁判以实际安装与测量检查为准。新增API仍按既有时期目标约$10、硬上限$20核账，不重置已花/UNKNOWN/在途金额；旧$50不是新增可叠加额度。具体余额和费率需服务器核验，本表不是价格保证或付费批准。

| 阶段 | 上限口径 | 基础本地模型调用 |
|---|---|---:|
| X数据 | (96train+24dev)×3条件×[2候选+2核验+1修复+1复核] | 2,160 |
| X一次追加（非默认） | 96train×3×6 | 1,728 |
| 共同初始化 | 24prefix×15plans×2executors×(G+J) | 1,440 |
| 核心RL训练 | 2executors×3seeds×128episodes×(G+J) | 1,536 |
| 开发评价 | 2×3×2checks×24prefix×(G+J) | 576 |
| 正式执行矩阵 | 48×3conditions×3executors×(G+J) | 864 |
| 正式策略交叉 | 48×20instances×(G+J) | 1,920 |
| **上列默认核心合计** | **不含一次追加，缓存命中前** | **8,496** |

初始化和训练需无资源基线：若每个96train/24dev/48test prefix×2executors均需额外一个G+J，保守预留最多672调用；与上表已有OFF去重，不能再次计实付。另列测量检查48+12 score calls、SFT dev生成诊断、独立评价/人评、时延实测、技术重试、来源核验及旧F任务；都不默认为0。

如果正式1392个回复全部再跑ESC-RANK七维，还会增加最多9,744次维度调用；且必须先说明它在新单轮协议上的适用性。因此不把“独立评分”写成免费的一行。选择哪份独立证据在test前声明，并保护其预算。

每个环境episode最多一次G和一次联合q/m评分；GET本身不调用生成大模型。自然回复、原评分缓存可复用，不反复购买OFF，不做所有70计划×全部prefix的默认穷举。

A4500优先G，A6000按阶段承担BGE批编码、X LoRA及J；无需常驻seeker，也没有session barrier换模型。GPU不能合并显存。BGE当前旧实现固定cuda，适配CPU或独立device时要版本化并测成本，不能声称直接可在任意卡并发。

在训练前用真实短/中/长前缀测加载、峰值、吞吐、自然EOS、adapter切换、client断开恢复和队列。逐阶段公式 `N_G*t_G + N_J*t_J + loads + encoding + training` 再给工期；现阶段不能诚实预报多少小时。评估时不把缓存响应延迟冒充模型生成延迟。

端到端时延在同硬件/并发下交错测量；可预选12前缀×4主要系统×3次真实运行=144次G作小型时延补充，评分可按身份复用。重复用于性能方差，不作新用户样本。

预算网关使用SQLite事务或等价单一broker，reserve/send/raw-response/settle可恢复；actual超reservation如实记账再暂停新调用。UNKNOWN按最大责任额占用，不因网络报错释放。所有provider的尝试共用总账，local-only不得调用付费provider。

## 16. Codex 的实现模块与接线顺序

新建 `project/src/metacom_pm/rl1/`，不重写旧paper1合同：

```
contracts.py       PrefixSpec / Inventory / Observation / Plan / Score / Episode
dataset.py         合法前缀、owner分组、exposure和容量census
asof.py            复用旧候选适配并显式传切点
visibility.py      actor/critic/G/judge权限投影
plan.py            规范集合、完整tokens、mask、可达计划
env.py             reset / step / resume，不包含心理状态模型
adapters.py        generator、tokenizer、encoder、scorer绑定
reward.py          原始q/m、OFF基线、成本、分项回报
cache.py           多级identity、请求恢复、measurement repeats
executor.py        SFT数据、LoRA训练与冻结
baselines.py       Fixed/Random/OneShot/有限支持DP
policy.py          masked MLP actor/critic
ppo.py             真实on-policy采样与更新
evaluate.py        静态矩阵、交叉、独立测量与成本
audit.py           来源、泄漏、转移、奖励与恢复检查
```

建议 `scripts/rl1/run.py stage <ID> --part prepare|execute|analyze --local-only`；这是**待实现接口，不是仓库现成可运行命令**。模型绑定缺失只阻塞相应live阶段，不能让seeker字段等全局required清单阻塞免费工作。

| 阶段 | 依赖 | 产物与验收 |
|---|---|---|
| R00 | 无 | 本地HEAD/dirty、已有1924/后续脚本、模型、账本核对；保留现有进度 |
| R01 | R00 | scoped amendment、schema、可复用边界、统一账本和缓存 |
| R02 | R01 | PrefixSpec、split/exposure、as-of inventory、容量与预算冻结 |
| R03 | R02 | 无模型env：真实GET、mask、token、STOP、重放、全部机械canary |
| R04 | R03 | X_b/X_g、自然结束服务、真实单次G→评分记录；完成奖励小样检查 |
| R05 | R04 | Step‑2 SFT数据/参数更新/重载/dev冻结；失败与无收益分开 |
| R06 | R04,R05 | 两执行器共同计划反馈、OFF缓存、监督/一次性基线 |
| R07 | R06 | E0真实PPO学习检查，通过后P_g/P_l有限真实训练与dev |
| R08 | R05,R06 | 可独立冻结并完成执行/监督选择结果；不等RL成功 |
| R09 | R07,R08 | RL终点、交叉与独立评价；或明确RL未运行/失败范围 |
| R10 | R08 | 汇总真实完成的层级、源证据、成本和限制；R09状态单列 |

R04测量不足时，R03工程仍可完成，来源与执行错误分析继续；不启动大量含糊reward训练。R07失败不把R08堵住。R05工程失败可收口固定指导结果，但不能称已完成双模块学习。

第一个工作日的合理交付不是训练好的RL，而是：本地资产复用表、合法前缀/动作域统计、一个可重放的真实GET/STOP轨迹、模型服务最小调用、待审reward样例及准确调用清单。不能先批量生成再发现输入/评分合同不兼容。

## 17. 本次设计的验证与未完成项

本次已完成：远端分支与全树核对；既有483文件重新核对、6共享模块blob验证；关键链路与7篇上传先行论文的方法边界复核；范围收敛；环境、观测、动作、转移、reward与训练协议设计；计划数量、依赖和奖励算式的离线检查。

模型无关检查枚举了4种GET、长度0–4的341条动作序列，核对70个终值计划、预算mask、强制STOP、终值成本只计一次与奖励望远镜求和；同时构造首条边际负但两条联合有益的反例。这里使用的是小型参考状态与模拟成本，**不替代真实tokenizer、生产env或PPO训练验收**。

未完成：服务器1924数据验收、当前模型/服务实测、完整仓库测试、真实reward人工核验、LoRA/PPO训练、正式评价和实际API报价。本方案不会把这些写成已有证据。

## 18. 给服务器Codex的接手指令

> 按本文PM-RL1范围推进：一条合法前缀、最多4次GET、一次最终回复、一次评价后结束。不要启动seeker、用户心理状态网络、跨会话写回、GRPO回复训练或联合RL。
>
> 先完成R00–R03，读取当前AGENTS及最新本地合同，保护dirty worktree。用户已确定后续研究方向；以独立namespace登记与旧四头合同的差异，保留旧结果。重点核对1924请求及本地后续服务，逐identity复用，不覆盖本地进度。
>
> 环境的下一状态必须由真实候选、取得动作、tokens与mask确定，不能由LLM编造。未GET正文不给actor/critic；gold和未来只留在对应评价/隔离域。GET不调用G/J，STOP才实际生成并评分；不重排、不丢资源、不退已发生费用。
>
> 先绑定可审计q/m及OFF基线，制作真实差异与来源损伤的测量检查包。语义误用保留为有效结果，技术失败/uncertain不填0。工程可用不等于reward有效，不以PM赢作为资格条件。
>
> 监督训练并冻结X_l，再训练小PM；保留同输入X_g/X_l、OneShot与固定/随机基线。默认一套masked feed-forward PPO，不做算法大网格。先E0真实学习检查，后受限真模型训练。所有成本按真实attempt/unique反馈分别记录。
>
> 在实际模型绑定、数据census和吞吐完成之前不承诺工期；API沿既有时期累计上限，不重置账本。完成具体请求与费用责任额后只执行已有授权的付费批次，其余本地工程继续。各阶段以真实产物和明确局限交付，不把计划写成结果。

## 19. 关键来源

仓库链接固定于本次核对的commit，服务器最新未提交产物需另验：

- [当前配置](https://github.com/chensiyu7812/Metacom5_3/blob/ba6917069cc6257ca8e64729509ce0f27e3cdc9b/project/configs/paper1_public_only.yaml)
- [执行清单](https://github.com/chensiyu7812/Metacom5_3/blob/ba6917069cc6257ca8e64729509ce0f27e3cdc9b/project/docs/PM_PAPER1_EXECUTION_CHECKLIST_20260903_ZH.md)
- [旧二元收益范围](https://github.com/chensiyu7812/Metacom5_3/blob/ba6917069cc6257ca8e64729509ce0f27e3cdc9b/project/docs/PM_PAPER1_BINARY_BENEFIT_SCOPE_AND_API_BUDGET_AMENDMENT_20260903_ZH.md)
- [候选适配](https://github.com/chensiyu7812/Metacom5_3/blob/ba6917069cc6257ca8e64729509ce0f27e3cdc9b/project/src/metacom_pm/paper1/multi_view_memory/candidate_adapter.py)
- [排序与打包](https://github.com/chensiyu7812/Metacom5_3/blob/ba6917069cc6257ca8e64729509ce0f27e3cdc9b/project/src/metacom_pm/paper1/execution/packing.py)
- [Step‑2交付](https://github.com/chensiyu7812/Metacom5_3/blob/ba6917069cc6257ca8e64729509ce0f27e3cdc9b/project/src/metacom_pm/paper1/execution/step2.py)
- [401编译收口](https://github.com/chensiyu7812/Metacom5_3/blob/ba6917069cc6257ca8e64729509ce0f27e3cdc9b/project/data/paper1_authority/paper1_multi_view_401_closeout_20260903_v1.json)
- [ESC-RANK实测收口](https://github.com/chensiyu7812/Metacom5_3/blob/ba6917069cc6257ca8e64729509ce0f27e3cdc9b/project/data/paper1_authority/paper1_official_esc_rank_qualification_closeout_20260902_v1.json)

上传原始研究计划及7篇论文已用于判断任务与方法边界。公开论文入口：

- [ES-MemEval](https://arxiv.org/abs/2602.01885)、[ESC-Eval](https://aclanthology.org/2024.emnlp-main.883/)
- [ESCA](https://ojs.aaai.org/index.php/AAAI/article/view/38807/42769)、[RLFF-ESC](https://arxiv.org/abs/2508.12935)
- [Value Reinforcement](https://arxiv.org/abs/2501.17182)、[D²RCU](https://arxiv.org/abs/2404.02505)、[CASE](https://aclanthology.org/2023.acl-long.457/)
- [Self-RAG作者项目页](https://selfrag.github.io/)
- [Active Feature Acquisition，NeurIPS 2018](https://papers.nips.cc/paper_files/paper/2018/hash/e5841df2166dd424a57127423d276bbe-Abstract.html)
- [PPO](https://arxiv.org/abs/1707.06347)、[Double DQN](https://arxiv.org/abs/1509.06461)、[Gymnasium环境接口](https://gymnasium.farama.org/api/env/)

本方案的样本数量、网络大小、α/λ及episode上限都是待绑定的工程与研究选择，不是这些论文保证过的最优值。
