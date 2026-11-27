# 第一轮工作指令（A = Codex；B = Claude Code）

本文件配套 [MASTER_PLAN_ZH.md](MASTER_PLAN_ZH.md)，是 2026-11-27 研究者已同意方向的**执行任务**。两线从本提交创建独立工作分支/独立 worktree，不在旧脏工作树或主分支写入，不修改旧 frozen 实验。先读取根 AGENTS.md 的新作用域与本主方案；旧 PR #28 及旧 G6 分支保持原身份。新任务不是创建 G7 或再写资格报告。CPU 开发与公开许可数据准备立即推进；GPU、训练、付费API、正式测试开封仍待一次明确预算确认。不得假称获得许可，旧批准不移植。

## 共用接口与交接

- A 拥有 project/src/metacom_pm/need_aware/data/ 与 evaluation/、相应脚本/测试；B 拥有 need_aware/memory/、agent/、runtime/ 与相应脚本/测试。建议命名可调整，职责边界不能混。共享的 runtime/eval schema 由 A 按主方案第4节实现；B 先按此契约做可接入组件，不等待 A 完成全量下载。若接口需改，A/B 在同一 PR 交接清单登记，而非各自产生不兼容 schema。
- 共同数据格式 runtime JSONL / evaluation JSONL 两套物理文件，task_id 唯一、版本固定；history resolver 只接 runtime，gold 在 scorer。选项为已打乱的所有选项，不含正确标记；检索 query 不包含答案选项。source ids/hash、native token count、实际输入 trace、失败、time 必须可 join。训练与正式 test 的目录/读取权限分离。
- 使用项目已有公开源码、私有数据路径由本机探测；不要向公开 GitHub 上传 RAW、源数据、金答案、私人日志、密钥、权重。只传代码、聚合统计、sha、路径角色与可复跑命令。
- 本轮各自完成真实 CPU 端到端；不是 mock、空 manifest 或文字清单。每线只交一个汇总报告及可运行代码，避免新增十几个治理文档。遇普通技术问题直接修复；只有访问许可/硬件/付费/研究构念必须研究者决定。

## A / Codex — 数据与能力、官方考卷、训练准备

目标：解决过去任务、标签、独立用户和学习数据不足的问题。先实际得到可训练、可评价的新数据与可复跑 scorer，不要继续旧 Judge 或四头训练。

1. 核查 PersonaMem-v2 text 数据卡与官方 repo/commit，下载实际 train/val CSV 和所需32k histories（按许可、磁盘和 pin；增量按需取 history，勿下载全部 multimodal/128k）。确认 18,500 / 2,600 / 5,000 声明是否与下载 revision 一致；输出按 persona、history family、pref_type、who、updated、sensitive/forget 类别 census、交叉重叠、缺失/重复、history 解析率。不要输出原文到公开 repo。
2. 读取真实 inference.py、prompts.py、inference_utils.py、官方训练 preprocessing；实现等价本地 MCQ 选项构造/打乱/解析 scorer，确认与上游正常/无效输出行为一致；测试使用已知选项的人工 fixture 和真实 val 的确定性 round-trip。**用真实数据实际跑 CPU 评测入口**：只可用已知答案的 scorer 自测或合成测试输出明确标作 plumbing，不称模型 accuracy。未得到模型结果就说没有模型结果。官方生成题面另建，不传 gold/options。
3. 按主方案冻结240 val 真实任务（180代表性+60困难，按实际 strata 与 persona，尽量>=60独立 persona；不因结果筛选），记录抽样种子、原始分母、source hashes。对 related_snippet 在合法实际 history 匹配，输出 direct_evidence coverage/歧义，不从 raw persona/gold 编造。另准备60预先分组开放任务与 train 3k–5k 候选；不训练，不读 test 标签或用 test 选择。保持 fold6 原锁。
4. 向 B 交付实际 runtime manifest、history resolver 和 EvalTask 接口；A 保管 eval sidecar，B 不读取它（C arm 仅由 A 产出已定位合法源坐标的独立 Direct 诊断 manifest，B 看证据而非答案，不能给其他 arms）。
5. 核实 PrefEval/OP-Bench 官方许可、数据格式与评测入口，先完成至少 PrefEval 的真实 CPU loader 小规模读取/样本计数和接口兼容；正式接入训练/测试顺序不扩大。ENPMR 只做数据许可/时间边界核实，未解决就标 blocked，不阻塞主干。ES-MemEval、ESC-Eval 现有实现复用，历史正式评价不重开。
6. 核实本机现有 G0e 及一个不同家族或能力参照模型实际路径、revision、license、native tokenizer 和 context limit（不加载GPU、不下载巨型模型未经预算）。跟 B 对齐 common cap；准备 official MCQ/开放 G 的消息和解码方案，输出 WP2 1,920 个终局逻辑请求与去重/预计物理调用上限。模型选择说明公平性；不要选弱模型自证效果。
7. 准备**一份**面向 WP2 后的训练实施路径：如果证据利用瓶颈成立，按官方 train 组织 grounded SFT/LoRA 与候选拒用/变化对照，说明训练目标及 checkpoint/训练预算；不先训练。避免把官方 MCQ distractor 当真实人类偏好、把 gold 偏好直接注入 runtime。按实际数据支持，缺监督就定义可执行的人工/弱监督验证，不制造真值。

验收：真实来源/版本/数量、240 runtime+隔离 eval tasks、可复跑 scorer、真实历史匹配 coverage、CPU 实测、与 B schema 一致。交付 git commit/PR、命令、计数、失败及单一 WP2 申请所需数据。报告中标出尚未执行项；不是以“全部准备好了”代替实际输出。

## B / Claude Code — 实际 Agent 代码、强基线、集成与批量运行器

目标：让数据能进入真正系统，解决记忆组织、身份接线、Generator 利用、序贯控制和重复在线推理的根因；不重启在线核验。

**先解决实际 import/runner 缺口**：主方案第4节记录了已核实的缺文件与历史可取回的固定 blob。公开 checkout 缺 limited_run.py / runprep_checkpoint.py / g0e.py，旧 WorkerCallBudget 只允许两任务，不能直接用于1,920调用。先实际核查本机 G6 完整工作树，从固定历史源找齐兼容依赖并实现新版本薄适配/批处理 scope，做真实 import/CLI、native tokenizer 和拒绝未授权运行测试；不擅自修改旧限制、复制旧许可或只写恢复建议。若本地资产不全，使用已有历史源码恢复；不兼容时写安全独立 adapter，并用实际 CPU 路径验证。

1. 核查 f45c281a 的实际源码与本地工作树资产：ge2_memory.py (_canonical_rows/render_intervals/observe/step), ge2_retrieval.py (SharedRetrieval), ge2_sources.py, ge2_runtime.py / ge2_worker.py, pomdp_memory.py, semcap/identity.py, g4_context.py, g6_context.py, evidence_state.py。列每个复用/薄适配/不复用的原因，特别核查 G6 中 memory_record 只接测试运行器的问题。**实现新 route 的实际读写接口**，不是再做 G7；保留原 source coordinates、owner、报告时间/消息顺序、主体与用户当前性、冲突/遗忘约束；写入阶段只允许从历史到 cutoff，无 query gold。旧实验模块不可回改。
2. 先接 A 的 RuntimeTask/EvidenceRecord 契约，编写 source resolver、索引、BM25 baseline；复用本机可用 BGE/dense encoder（无 GPU/付费授权时 CPU 能做就做，不能做则准备同预算运行）。用至少240真实 val tasks 做 CPU 检索/输入 materialization，记录实际读入原文、owner/time/重复/容量。强固定检索可选 BM25/dense/hybrid 在 train/val 的共同信息预算下比较；先用 A 提供的任务内合法证据定位诊断评估 coverage，不能将 Direct target 传给 B baseline。B不负责看 gold。
3. 实现四个统一 arms A Context Only/B Strong Fixed RAG/C Direct Evidence/D same evidence + grounded state projection，确保 C/D 所见原文一致。D 先 deterministic identity/time projection + 简洁适用性指令；任何生成式状态 writer 单独离线缓存及版本、额外模型调用预算，不运行同步 GSWS/INSPECT_CLAIM。实现 MCQ 与 generation 的同一合法上下文接口，MCQ 选项不用于检索。完成相同请求 hash 精确复用、防重、source_id traces。对缺 direct 定位的任务只标 diagnostic not_evaluable，保留 A/B。
4. 复用现有 GE2 worker/guard/deadline/实际日志机制；如果旧代码身份限制，写独立薄 adapter/new manifest，绝不伪造旧授权。支持真实 native tokenizer 计数、模型切换、批量、断点恢复、seed/顺序、失败/超时、TTFT/完成计时。对本地旧缓存路径/磁盘/设备占用只读核查；不杀别的作业、不占 GPU、不自发付费。明确离线写入/索引、retrieval、online control、G 的成本分开。
5. 运行 CPU 回归及真实数据端到端“读取→检索→合法消息→请求序列→dry-run/实际CPU路径→scorer交接”；测试 wrong owner/future/gold/role/forget/缺证据、相同输入复用、无授权拒绝、容量预检。测试与 mock 不是终局。不能因 1 条 schema 错停止整个研究，修复后在同范围继续。
6. 与 A 联合给出一次 WP2 实验包：240任务×两G×四臂上限1,920；明确模型加载、native context cap、物理调用数、总GPU秒、retry policy、日志与成本上限。目标预算为12 GPU小时候选，实际计量与本机限制决定可行缩放；不为加规模申请无关 GPU。授权后 batch 前16是同一正式开发包技术 smoke，成功继续全部剩余，无需逐组问；到硬限停止，报告实际完成/缺口。若第二 G 不可用，完成可行单 G 对照并显式留跨模型问题，不捏造比较。
7. 提出 WP3/WP4 的实现候选（不提前训练）：若 B→C 改善做检索修复，若 C→D 改善接离线状态，若 G差异优先交 A 适配，若同信息下需要应用控制，则将当前目标/active preference/unknown 映射 use/background/ignore/clarify，同 G 比较。先规则/监督，有等预算序贯余量才启 RL。禁止无依据开发一个新的万能 Agent、扩大为所有多模态/提醒。

验收：实际可运行的 adapter/renderer/runner + 真实240任务检索及 materialization 统计（若 A 数据尚未就绪，以已合法缓存实物先接线，最终须以 A 同一批次验证；不能用 mock 代替）；每臂实际消息身份/证据边界、端到端 CPU 结果、调用预算与可执行 GPU 命令。交付 git commit/PR、实际测试、失败与待批项。无真实 GPU 推理就不要宣称取得方法结果。

## 联合验收（提交给研究者，不要求额外规划回合）

一份短联合摘要：A/B commit、真实数据计数/owner 划分/许可、240个冻结请求及 direct coverage、强基线与模型选择、CPU回归/实际输入统计、WP2 的确切一次性预算、当前真实 blockers。若接口失败 A/B 直接修复并重试；只有真正不能在现有权限下运行才停。研究者批准 GPU 后立即按 manifest 全量执行，提交逐项配对终局/失败、真实成本与 WP3 单一针对性修复建议。无需再给研究者一份“大方案”。本次默认不批准新 GPU/训练/API，不开启旧 outcome locks，不把未发生的任务记为已完成。
