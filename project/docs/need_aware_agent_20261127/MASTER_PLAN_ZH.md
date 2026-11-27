# 长期陪伴 Agent：需求感知与自适应记忆利用 — 现行研究主方案 v1.0

日期：2026-11-27（JST）。研究者在本次讨论中同意从 PM-RL1-J 转向本方向，并要求更新 GitHub、领导 Codex 与 Claude Code 实施。本文件是本分支唯一新增的研究方向与执行顺序权威；不是新的历史结果、GPU 运行授权、付费许可或正式测试解封。研究代号暂用 NAA（Need-Aware Agent），不宣称论文最终方法名或首创。固定起点 f45c281a06ee12b3ca7d59ebe8017116c6fcdffe；主分支和历史 PR 保留。执行说明见 [WORK_ORDERS_ZH.md](WORK_ORDERS_ZH.md)。任何人员或 Agent 不得以旧方案覆盖本分支的新研究目标；旧方案的安全、隐私、来源和已授权作业限制继续适用于各自原实验。

## 1. 研究问题与论文边界

博士总体目标：长期陪伴数字人，理解用户、维护长期状态、适应当前需要并提供适当帮助；情感支持是重要场景而非全部。当前期刊：文本型、跨会话历史条件下的目标与偏好感知记忆利用。不是纯 QA、纯检索时延、临床治疗或真实跨月情绪改善。暂不扩大到主动提醒、视频、跨轮心理转移、所有外部工具。允许研究并适配 Generator；固定 G 是一次对照的控制变量，不是永久假定。

RQ1（能力）：合法历史中的事实、时序、有效偏好与当前目标如何被正确理解和利用？定位供给、检索、表示、生成执行差异。
RQ2（主要方法目标）：在同一信息和生成器下，**依据当前目标与有效历史决定记忆适用性，落实为实际回复行为**，能否同时提高应当个性化时的任务完成/偏好遵循，减少无关、过时、第三方、重复、迎合式或违反遗忘要求的使用？不能仅以记忆提及率、检索命中或 MCQ 成绩宣称开放对话改善。
RQ3（系统目标，条件扩展）：在 RQ1/RQ2 能力成立的条件下，按需获取/继续/停止/澄清能否改进质量—真实时延取舍？学习 PM、序贯与 RL 不是必需的发表前提。

主方法假设（待检验，不是已实现贡献）：将长期证据中的偏好与状态表达成可追溯、可更新的候选；将“是否有相关记忆”和“是否适用于本轮目标”分开；按适用性选择使用、背景使用、不使用或澄清；比较原文直供、离线状态组织、相同证据下的适用性控制、同 G 的固定增强。优先做最小的可学习应用决策，不把所有能力都做成独立同步 LLM。若简单固定 RAG+适配 G 已覆盖能力，则接受其为强基线/实际系统，停止无增量模块；不把旧 PM 换个名字作为贡献。

竞争性：PersonaMem-v2 已有 GRPO 与 Agentic Memory（MemAgent 改造），Adaptive-RAG、ENPMR、OP-Bench 已分别研究动态检索、隐含情感需求检索、过度个性化。不能把检索开关、记忆结构、训练 G 或 Agent 标签本身作为新颖性。可辩护候选贡献是“面向目标、当前约束、变化与不适用记忆的实际行为控制，在同证据/同 G/匹配预算下可辨别的增量与独立开放回复证据”。若与先行工作重叠或无可重复增量，应缩小主张或转为诚实的边界研究，不保证发表。代码： https://github.com/bowen-upenn/PersonaMem-v2 ; https://arxiv.org/abs/2512.06688 ; https://aclanthology.org/2024.naacl-long.389/ ; https://aclanthology.org/2026.findings-acl.2080/ ; https://aclanthology.org/2026.emnlp-main.1168/ 。

## 2. 历史证据、保留与禁止重复

| 历史问题 | 已有证据及限制 | 本次处理 |
|---|---|---|
| V1.0 / V1.5 泛化与资源收益 | Context Only 3.745 vs PM 3.657；独立同预算诊断 ME+R0 有利；不证明外部资源普遍有害 | 保留历史结果；不重新训练四头证明原假设 |
| Paper-1 Judge | 训练裁判与人评等价/胜负不一致，不能作为稳定整体奖励 | 采用官方确定性 MCQ 与任务指标，开放回复独立盲评；不再进行无期限 Judge 竞赛 |
| 11/11 QA、J06 | 0/14 vs 定向13/14；J06 12个缺事实任务 MS 16/16 原子 vs STOP 0/16；24题仅6家族、池1–2会话 | 记忆能力有条件价值；大规模独立 persona 与长历史；不把小池 Oracle 当普遍上界 |
| GE2 | 8开发任务 FixedTop4 6–8，ToolAgent 5–6；G02 供证未利用、G07 可能提前 STOP | 复用检索和真实调用，定位证据利用与充分性；不直接训练 PPO |
| GSWS | 16状态 RAW/Notes 11通过、GSWS 13；解释回退7/32；同步 +23.89s | 停止同步状态解释路线；状态维护移到写入阶段，独立测量 |
| G2-R / G4 / G6 | T1i 开发 Macro-F1 .816→.893；G4 固定核验无增益且 +约9.5s；G6 32筛查实质可修复失败0，留出未运行 | 不恢复 G7/在线 INSPECT_CLAIM/NLI 微调。T1i 仅离线候选，须有独立缺口才用 |
| 28候选/45次 pilot | 20许可可用状态、5家族，15人工反事实、自然跨会话0；未获新结果 | 不作为前门；默认不执行；若研究者单独批准仅功能诊断，不扩题追分 |

证据入口：[11-25 J06](../journal_20261125/REAL_TASK_JOINT_RESULTS_20261125_ZH.md)、[GSWS](../journal_20261127_claude/GSWS_V3_RESULTS_AND_DECISIONS_ZH.md)、[G4](../journal_20261127_claude/G4_SYSTEM_CONTRAST_RESULTS_ZH.md)、[G6](../journal_20261127_claude/G6_CLOSEOUT_AND_DIRECTION_ZH.md)。以上采用已有报告，不是重新计算或独立人评；GSWS/G1/G4 独立评审 pending，仍按原身份保留。fold6 及旧正式 outcome locks 不开。无须重复 J00、A0、E6、PP1、C0、旧 DP 或历史资格门；不修改历史协议、失败、盲包和结果。

## 3. 数据主干：先实际下载、检查、跑官方评测

首轮只把 **PersonaMem-v2 text** 作为新训练/开发主干，不接入所有 benchmark。官方数据卡 https://huggingface.co/datasets/bowen-upenn/PersonaMem-v2 （CC BY 4.0；LLM 合成，不是真实用户）。卡片列 1,000 personas、26,100 条偏好/片段/问答；text train 18,500、val 2,600、benchmark 5,000，宣称 persona_id 无交集。实际使用必须记录固定 HF revision、文件 SHA-256、确切数量/独立 persona/交集；不以卡片代替实测。32k 文本 history 优先；128k 作为后续难度/长度条件。注意多个任务复用同一 persona history；按 persona/history family 而非行分组。禁止使用旧自造 11/80 用户数据。

官方仓库 https://github.com/bowen-upenn/PersonaMem-v2 的 inference.py 实际提供 mcq/generative/both，load_chat_history 后追加 user_query，MCQ 打乱 correct_answer+incorrect_answers，输出解析后核对选项映射。先复现官方 MCQ 契约；不执行默认付费脚本、不原样安装包含联网服务的 Docker、不直接调用 data_generation；固定上游 commit 并核验代码许可、依赖与本地适配。MCQ 的所有选项文本是官方合法题面；正确选项位置/答案 key 只能在 scorer，检索 query 只取用户请求与可见上下文，不用选项找 gold。相同任务所有方法共享选项排列和随机种子。开放生成完全不提供候选答案，不把 MCQ accuracy 称为生成质量。官方 generative scorer 如需 API，准备本地/独立人工替代并标为非官方；禁止未经批准调用。

数据实物：train/val 可本地下载实际处理；benchmark 文件可以下载校验身份但结果/标签隔离，冻结前不用于模型选择；仅通过独立评分入口做最终评测。用真实 history JSON 构建索引，不能把 expanded_persona/raw_persona_file/preference/prev_pref/related_conversation_snippet/correct_answer/incorrect_answers/target category 等研究标签当可部署输入。related_conversation_snippet 仅用于离线诊断参考：必须匹配已合法可见 history 中原话及说话人/坐标；无法匹配时记 missing/ambiguous，不补造证据、不删除普通任务。官方完整 history 后的 query 为官方任务时间边界；如无真实日期，以消息顺序/报告顺序表示，不编造时间。跨数据集不混成总分，不以 QA/自然对话来源预测是否检索。

| 外部数据 | 职责 / 使用顺序 |
|---|---|
| PrefEval https://prefeval.github.io/ / https://github.com/amazon-science/PrefEval | 第二优先；3,000 preference-query、显式/隐式、官方 generation/MCQ；作为开放行为外部考卷，显式/隐式同族；核实许可与官方 split |
| OP-Bench https://github.com/yulinlp/OP-Bench | 1,700验证实例、20用户、irrelevance/repetition/sycophancy；正式过度个性化保护项；复现其真实分母和多轮重复条件，不把所有题当单轮 |
| ES-MemEval https://github.com/slptongji/ES-MemEval | 原始 QA/DG 的记忆与情感支持外部验证；沿用官方语义/指标，旧 fold6 不动；开发暴露如实披露 |
| ENPMR-Bench https://aclanthology.org/2026.findings-acl.2080/ | 情感需求主动检索，优先核查实际代码/数据许可/目标之前的时间证据；未解决不得纳入。缺失时用已合法 EvoEmo/ESC-Eval 的受控外部验证，不把它们称为等价 ENPMR |
| LongMemEval https://github.com/xiaowu0162/LongMemEval | 仅当序贯收益需要长池复杂事实测试时接入 cleaned S/oracle；不必马上增加500题和M版本 |
| ESConv/AnnoMI/ESC-Eval | 保留短期支持行为/多轮质量；策略标签是观察行为非最佳行为；不以它们给全量新PM造奖励 |
| PersonaMem-v3 | 主动提醒等未来工作；本轮不纳入 |

A 交付实际源文件与哈希清单、数据 census、合法前缀构造、gold 隔离、官方 MCQ scorer、真实数据 CPU 运行回执及模型请求清单。至少真实 240 个 val 任务冻结（若可用 persona 不足60则如实说明并按全体分组抽样，不造用户）；180 代表性抽样＋60 按预先定义的更新/隐式/第三方/敏感或遗忘等困难类别分层，避免重叠；类别以实际字段为准，不要求造不存在的正例。训练候选 3,000–5,000 行，按 persona 分组、仅 train；需要训练才物化目标。测试统计按官方分布和逐类别分别报告，开发困难层不能估计自然发生率。

## 4. 代码实现：重用、少改、可跑，而非又造一套框架

新实现建议放 project/src/metacom_pm/need_aware/，命令入口 project/scripts/need_aware/，测试 project/tests/test_need_aware_*.py。建议目录是新开发边界，不意味着文件已经存在。冻结 rl1、rl1v3/journal、semcap、旧 scorer、配置不改；用新 adapter/import 复用（如受原实验身份限制则写薄适配，不能绕过运行 guard）。不迁移模型/原始数据到 GitHub。

**已核实的源码缺口（不是假设）**：在基线 f45c281a 的公开 Git 树，`rl1v3/generator/` 仅有 `__init__.py`、`preflight.py`、`tokenizer_probe.py`；但 `journal/ge2_worker.py` 导入 `generator.limited_run`、`generator.runprep_checkpoint`，`journal/ge2_runtime.py`、`renderer.py` 还依赖 `generator.g0e`。公开 checkout 不能被视为完整运行栈。已实际定位历史源码：`limited_run.py` (blob f87edf670ee1463343924cc459a91e337f179d80)、`runprep_checkpoint.py` (13c26eede7fbdf18d831b8e6edd987502c96a8ca)、其依赖 `compile/ms_pp1.py` (b84f31e71bd8cb4c599247bdd9ff341b48c891d1) 均见 commit [67169816bddaf50206f9847300673d4887713c4d](https://github.com/chensiyu7812/Metacom5_3/commit/67169816bddaf50206f9847300673d4887713c4d)；`g0e.py` (22f7088e9e6f98b424e720390c3ca79508dde798) 见 [73fdb12f29b6970a268eeda704d73e1bd35b1c3e](https://github.com/chensiyu7812/Metacom5_3/commit/73fdb12f29b6970a268eeda704d73e1bd35b1c3e)。此外 `ge2_worker.py` 的 `WorkerCallBudget`硬编码两任务和8–10终局/角色限额，不能原样支持240任务批量。B 先从本地已运行 G6/GE2 的完整工作树和这些固定提交恢复或版本化适配必要源码（含其传递依赖、配置、模型绑定及许可），不盲目 cherry-pick 旧授权、不假设历史 blob 可直接拼接。优先新 NAA backend 复用真正已运行的 load/generate/guard/计时逻辑，新的批量 manifest/调用上限从批准的 NAA scope 派生，不改旧 WorkerCallBudget。完成独立环境 import/CLI CPU 检查、真实 native tokenizer 渲染、guard 无授权拒绝与 resumable 账本测试；在真实授权模型烟测前只能称 CPU 可运行准备，不能宣称 GPU backend 已复现。缺源码先找上述固定版本，无法兼容则新薄适配保留安全边界，避免数周重复盘点。

| 已核对的原代码 | 使用方式与缺口 |
|---|---|
| rl1v3/journal/ge2_retrieval.py SharedRetrieval / RetrievalConfig / validate_record | 复用合法候选、BM25、turn/session 坐标；实际记录构念不匹配时转换，不假装已有 dense 支持。复用已有 BGE 缓存或 encoder、在 val 上选择强固定检索（BM25、dense、hybrid）并公平计费 |
| journal/ge2_memory.py GE2Episode._canonical_rows/render_intervals/observe/step | 已有合法性、去重、坐标、SEARCH/EXPAND/STOP；其 renderer 仍拼 speaker: exact_quote。新 route 独立接 identity/time projection 到实际 Memory Writer 与实际 reader，不只在测试运行器。旧 identity/hash 不动 |
| journal/pomdp_memory.py SearchExpandEpisode | 保留动态 baseline，可适配；非必须新 RL 环境 |
| semcap/identity.py classify_source/render_current_dialogue/attribute_history | 可复用身份边界（导入人类、同一AI、外部案例），新数据实际角色未知时保留未知，不假定真实人格。尤其避免把旧支持者经历写为 AI 自己经历 |
| semcap/g4_context.py memory_record/render_records/generator_messages；g6_context.py | 复用身份、报告时间与记录引用；G6 明示未接生产写入。统一到新实际读写入口；禁止恢复在线 CHECK |
| semcap/evidence_state.py revise/InspectClaim | 可复用状态词与 conflict 处理；模型判断非 gold，subject/time_scope 曾未实际参与。若无独立收益不调用 T1i |
| journal/ge2_controller.py / ge2_runtime.py / ge2_worker.py | 保留真实工具 baseline、deadline/CallBudget/worker 与调用计数；原 controller evidence_state 是自报，不当标签。检查实际本机后端/模型路径、兼容 native tokenizer，不能直接伪造旧 runner manifest 或旧审批 |

建议最小接口：不为每个逻辑能力增加 LLM。A 写数据及 scorer；B 写 retrieval/runtime/Writer/reader；共用交换契约，不互改。
- RuntimeTask：task_id, dataset_revision, split, persona_group(仅分组/检索隔离，不作预测特征), source_family, history_ref, cutoff/order, current_messages, user_query, task_mode(mcq/generation), options(仅 MCQ，打乱后的 id/text 无答案标志)。history_ref 解析仅给当前 persona、cutoff 前原文。不得含 eval 字段。
- EvalTask（物理独立、运行进程不可读）：task_id, gold_choice_id/reference_answer, gold_preference/related_snippet, category/updated/who, verified_spans(如存在), scoring_protocol。仅训练/评价进程读取各自分区。
- EvidenceRecord：source_id, owner_id, session/order, speaker/situation, reported_at(可空), original_text/hash, coordinates, validity/unknown；claim/state view 可附 source_ids、scope、status、reported_vs_event_time、superseded/forget flag；不把 inferred 当 confirmed，不自动覆盖矛盾。不使用第三方或已要求忘记的信息作为用户偏好；保留安全的删除/排除记录，不在输出透露。
- Prediction：run_id, task_id, arm, model/prompt/tokenizer/data/retrieval version, actual delivered ids, input/output tokens, per-component time, TTFT measured/unknown, completion, stop_reason, errors, exact request hash, output_ref；评分单独 join task_id。原始输出留本地；每个失败均在账本（不只统计成功）。
- CLI 至少实际有 prepare / retrieve / materialize / infer / score / aggregate（名称可调整但功能必须存在）；CPU fixture 测试只是回归，不算实际推理。必须用真实下载数据产出至少240合法请求和真实 CPU 检索日志；用故意污染 gold/future/wrong persona/identity/forget 的测试证实阻断。运行过程中不能访问完整 gold sidecar。

线上逻辑：直接回答（本轮充分）/取得证据/再获取/澄清；取得后决定 use/background/ignore/unknown；明确当前要求优先、适用范围、时间变化与不确定性。不强行复述历史。首轮最小方法是同 evidence 下的适用性控制：普通强 RAG prompt vs 相同证据＋可追溯 applicability/active constraints（从实际可见信息生成、可由同一次 G 隐式完成）；状态整理由离线可复用 writer 实现，原文保底。先规则/轻量监督，证明额外模块对终局有增量才保留。

## 5. 第一轮实测设计：单一完整工作包（不是下一份小 pilot）

WP1（CPU，立即）：A 与 B 按 handoff 并行实际开发/下载/复现。冻结 240 val 请求、两种 G、共同 context budget、强固定检索、官方 scorer、run manifest、成本与失败规则。第二模型先核实已有 checkpoint（例如不同家族 Qwen 或实际可用更强模型，不指定未验证模型），不得为配平故意选弱对照。报告实际显存/容量/许可；没有第二模型则先同 G 完成完整对照，明确跨模型归因待做，不换成同权重重复。禁止偷跑 GPU 或远程 API。

WP2（开发实测，单次预算批准后）：240 同源 val tasks × 2 G × 4 arms = 1,920 **终局请求上限**（先从固定清单顺序运行至预算；相同请求允许精确复用但不能作独立观测）。
 A Context Only: 用户 query＋固定近期对话（定义无历史 vs recent window；PersonaMem target 是追加请求时，不能把整个 history 偷给 A）。
 B Strong Fixed RAG: 只用合法 history；k/budget/候选排序预先在 train/val 内确定，未看 test。记录 recall 诊断和索引/embedding代价。
 C Direct Evidence: 从已合法可见原文定位必要证据（离线已知任务信息，仅诊断）；不能把金偏好、答案、作者说明替换成证据，missing 记不可定位；不称可部署或严格质量上界。
 D Evidence-grounded State: **同 C 的确切证据**加上仅从可见证据推导的结构/应用约束；第一轮可用确定性身份/报告时间/阶段投影和一致 prompt，以避免新在线解释模型；生成式 writer 若启用必须单独版本、缓存每 persona+cutoff、盲于当前题/答案、计入非实时调用与延迟。D 不比 C 偷加原始信息。C/D 无合法定位时记录 not_evaluable，A/B仍必须报告，不把该缺口当失败正例或删除总体数据。
 对每个 G 的同任务同输入预处理、解码和输出格式比较。MCQ 240 主；先准备 60 个独立预定 val 开放任务（如能使用官方生成版），同一 G 的 A/B/方法候选最多180另计的生成请求，由下一次同预算包明确，**不从1,920中偷算**。无人工标签的开放输出只作开发诊断，不产生正式 reward。最终独立盲评拟150–200配对（两人、按 persona 分层、含保持/变差/误用，不挑有利题）。
 32k full history 不能自动塞入 G0e 16k packet。共同有效上下文预算按真实 native tokenizer 与留出输出选定（例如8k/12k，需实际确认），不把截断版叫官方 full-history；有容量的模型另列完整历史对照，并明确不同容量。正式论文至少有同预算比较、较强 full/long context baseline（能运行才报告），和 PersonaMem 官方 MemAgent/同类方法可运行版本或明确复现缺口。
 使用实际 GPU/模型装载身份、max context、生成上限、磁盘/独占锁、日志、interrupt/resume。所有新请求与模型容量按物理调用数和总GPU占用秒计；索引构建、Writer、训练、评审不隐去。建议 WP2 一次审批上限1,920终局、两种模型顺序加载、12 GPU小时（43,200s，含加载/重试/实际工作，预算不是预测）；本机如核算不合理提交可行等比例调整一次，不逐小批申请。前16个请求是实际 batch 的技术烟测，计入上限，不另起“研究阶段”；技术成功即在同授权内继续。技术失败修复后续跑待完成项，按预算记录重试且不覆盖原结果；达硬限停止并报告缺口。零付费、无外传、训练另批准。

## 6. 依据结果直接修复而不是再次诊断（WP3、WP4）

WP2 结果必须分解为 A→B（实际记忆系统）、B→C（供应缺口的诊断）、C→D（同信息组织增量）、模型差异×C/D（利用能力），报告配对修复/退步/不确定、证据覆盖、无支持断言与遗漏。不是仅对比平均分；C 是条件性诊断参照，不等于真正 Oracle。先估计按 persona 聚类的成对 CI、样本差异、开发有/无头部余量；小 CI 不排除成本空间，不得从小样本差异不显著推出等价。

| 结果 | 必须实施的动作 / 一次修复界限 |
|---|---|
| B漏掉证据、C修复 | B 改一次检索：候选粒度+BM25/dense/hybrid、时间/重排，从 train 合法 evidence 构造检索监督；同一冻结 dev 重跑受影响臂＋完整必要对照；另保留未暴露 val 确认 |
| C已供证仍错且参照G修复 | A 做一次 G 能力适配；选 3,000–5,000 官方 train（若足够）依据真实错误类型构建 SFT/LoRA，或具有合格成对标签的偏好训练；严禁用 val/test 答案训练。先复现 upstream Qwen/官方配方的适用部分，不强制 GRPO。相同数据、同训练/推理预算比较；未经批准不训练 |
| 同证据 D 更好 | B 实现实际离线 Writer/reader 的最小版本，不运行同步 GSWS；可复用 T1i 但非必选；以同等信息、普通 Notes/raw+相同 token 作为对照并含写入成本 |
| 证据已充分、模型还不懂当前需求 | 使用 train 的合法 history/query 与正确/错误行为对（显式/隐式、更新、第三方、遗忘），学习应用/拒用决策；比较简单 prompt/规则与适配 G，不加新的在线事实核验 |
| A/B/C/D 均差 | 先检验题面与官方 scorer、证据是否实际可定位、模型/容量。若任务有效且两 G 均不能处理，修复可学习能力或承认范围；不以重新抽更容易题作为解决方案 |
| B/C/D 同等强、置信度仍不足 | 完成剩余冻结 val、报告范围，避免把开发差异不显著当饱和；若可靠地无增量，保留强 B，研究选择性应用/时延或转独立长期适应；不继续追加小探针 |

WP3 只选择**一个影响最大的主瓶颈修复**（另一条确定性安全/接口修复可并行），一次实现+验证；若没有正增量，终止该具体方案或回到强 baseline。不得不断增加小模块或改测试以求正。可保留不影响最终主张的真实负结果。WP4 以适用性为核心：同 G、同合法 evidence、同 token/近似时延预算，比较 RAW fixed、普通规则、candidate 适用性模块、适配 G+fixed、完整方法；包含本轮已可满足/历史必要/偏好改变/历史不适用/缺证据应澄清；来自真实官方目标或独立预先定义的匹配反事实，后者单独报告。对于同样历史、不同当前目标或同目标更新偏好，检验行为是否相应变化，不要求主动提及记忆。只有显著有用的功能才进入完整 Agent。

## 7. 正式评价与 PM 条件扩展（WP5/WP6）

正式选择以 val 冻结后、官方 persona-disjoint benchmark 为主，不重跑 test 调参。至少：
- PersonaMem-v2 official MCQ accuracy、各类/更新/隐式/第三方/遗忘子群，分组 CI；开放回答单列，不以 MCQ 作为实际支持效果。
- PrefEval generation/MCQ、OP-Bench 官方指标（如有收费独立判分明确非官方替代）、ES-MemEval 官方 QA/DG 与情感支持专项评价（可用 ENPMR 后）；各 benchmark 分母独立，不报告跨任务混合一个分数。
- 与主要强固定基线比较的 goal/preference gain、误用/遗忘风险保护、配对差异；同模型同预算的完整系统与消融；Generator适配的收益不能归到 PM。
- 延迟：真实本地 Agent TTFT/完整 P50/P95（未测标 unknown），检索、写入离线、在线模型调用、tokens、失败/超时、缓存/预热规则；Tokkio 语音端到端另测，不把本地时间改名。共同运行次序随机/交错，模型切换/加载时间分列。
- 验证成功标准：预注册实际有意义的改善门槛与非劣界限（依据独立人评/开发配对方差/资源预算提出，不临时追分），按 persona cluster bootstrap 或适当配对模型估 CI、处理少数 owner 及多重比较。目标是在主要任务中有可辨别增量、误用保护不过度恶化、独立生成证据方向一致；不把不显著当非劣，不以新增模块数量、NLL、GPU次数或测试通过替代效果。完成全体测试后只报告，失败不换主指标。

若已实现相同任务上的动作反事实（可观测输入、至少两种有效行动、质量与真实成本、可靠标签），再训练低成本 PM（cost-sensitive supervised/ranking/BC），比较 best fixed、规则、matched random、one-shot、同底层 tool agent 与 hindsight diagnostic。若先读后才能决定下一次读取且**同预算下**存在可重复的序贯优势（非工具调用次数），才允许提出 RL，先强监督/有限搜索对照。没有可靠奖励/额外收益就不启动 PPO。真实跨轮心理改善不是当前主张。

## 8. 治理：两次主要研究决策而非几十次阶段审批

1. 本次研究方向与 CPU 开发已同意；GPU/训练/付费/正式测试尚无具体授权，旧 locks 不变。A/B 对应 [WORK_ORDERS_ZH.md](WORK_ORDERS_ZH.md) 启动；不要要求重复总体方向确认。
2. 首次交付为可跑代码＋真实数据 CPU 回执＋一次 WP2 有界申请；模型运行后交付真实结果及根据第6节自动确定的单一修复候选/预算。正式训练/测试另用明确授权；不反复审批同一已批准批次，不把每个子脚本变成研究 gate。
3. 执行者有责任在既定范围内修复普通错误（依赖、格式、解析、缓存），使用真实数据走通，保留版本；不得以阻塞清单代替工作。若硬件/许可/安全/实验构念实质改变，则提出最小可行替代；无权限不突破。不得重复小样本并追加 G7/G8。旧结果与失败全保留。
4. 每个工作包一个 evidence ledger：commit、实际命令、数据/模型版本、请求/完成/失败/跳过、逐类结果、真实成本、局限、下一步。公开 GitHub 仅代码/统计/非敏感说明；原始对话、样本、用户/评审身份、个人数据、密钥、私人回复和模型权重留实验服务器。不得宣称实际已运行尚未运行的操作。
5. 研究指导者（本次对话的 ChatGPT）基于两线真实产物统一作科研决策；没有自主访问本地机器、持续后台管理或发放资源权。A/B 不能自行重写 RQ；变更须说明证据、影响及是否需要重新评价，待研究者同意后更新本文件。历史文件中的“current”“frozen”仅按原实验作用域读取。
