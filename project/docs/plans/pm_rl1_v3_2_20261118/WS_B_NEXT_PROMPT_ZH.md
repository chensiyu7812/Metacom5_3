# 下一轮给 WS-B 的指令：V3.2 as-of 绑定、奖励资格与机制实验协议（CPU 先行）

你继续负责 PM-RL1 WS-B。**新优先目标不是马上运行 B6e，而是在正式 G0e 集成后，把每个终点绑定到“该时点可被构建出来的资源快照”，并确保评分/实验可以区分真正需要、可选但不必提及、无益和潜在有害资源。**

请先读 PM_RL1_RESEARCH_PLAN_V3_2_CANDIDATE_20261118_ZH.md、现有 V3.1、RESOURCE_SPEC_ZH.md、PR #13 审查以及本分支 ROUND7/B2/J1V3_CAPACITY_RISK_ZH.md 和 NeedCard pilot v2 计划。新的 V3.2 是候选研究方案，不得自行改写全局 EXECUTION_STATE、H0 或老的 B1/B2/B5/B6e 冻结记录。

**本指令不构成 GPU 授权，也不批准 writer、G0、J1/J2、训练、生成、付费调用。** B1 20-call 试点、A0 GPU、B6e 120 终点和最多 360 J1 仍需各自的研究者明确批准。

## 1. 先保护现有 B 线与集成顺序

1. 核查 PR #10、#11、#12、#13、#4 和 integration 的最新状态；#11 在 #10 正式合入之前保持 Draft，不把本地临时合并当正式验收。
2. 当 #10 由 integration owner 合入后，从新 integration 对 #11 做普通同步并在真实 merge base 上运行 G0ePrefixPort、request_packet 和 B6e_g0e_binding_addendum：8/8 前缀、120/120 可达终点、471 读取顺序；重建新 TerminalKey/trace/请求 SHA、无 NeedCard/judge/未来和私有 ID 泄漏、旧奖励不可复用、全部 STOP pending。保留冻结的旧回放、plan 和 key，附录只追加新目录。
3. 重新运行 V3 严格测试与完整 CPU/PR CI，注明历史 63 skip 的环境原因；通过后才转为 ready，由 integration owner 合入，不自行 merge 或修改 global state。
4. 新 V3.2 CPU 研究工作从独立工作分支开展，不混进 #11 冻结交付；如果 #10 尚未合入，先做不依赖 G0e 的协议/测试准备。

## 2. 与 A 联合固定 PrefixAsOf 合法切点契约

1. 维持 B-owned PrefixSpec、owner/family/fold/cutoff；联合 A 定义 PrefixAsOfBinding：source_frontier、cutoff、writer_identity、snapshot_sha、bank/index/query/renderer/g/decode/step2 身份。需要 C0 新字段时只出迁移提案和版本评审，不擅改冻结 C0。
2. 建立三份白名单：PM 观察、Generator payload、评价侧私有 NeedCard/Judge。评价侧可读严格过去的合法证据，但不能通过查询分数、stratum、optimal subset、gold evidence 或终点奖赏免费喂给 PM。
3. A 的 as-of replay 先选 3–5 owners 切点，B 独立核对 source/原文/时间/ready/同会话边界，并做未来追加不影响旧状态和同源 family 排除测试；只有机械和语义条件通过的视图可晋级科研版。
4. 现有 8-prefix/120-endpoint B5 是 bank-v0 合法读取**工程回放**；不能假称已满足新的“历史时点可写入同一 bank”要求。新 as-of bank/renderer 必须生成新的终点身份，不重命名旧键，不搬运旧 reward。

## 3. 机制实验：冻结提案，不启动生成

1. 以 PR #13 的 39 个 OFF/单头和 15 个 MP+MS/ME+MS 输入（共54）为**已曝光开发材料**，逐条加 as-of eligibility、源/人物/阶段/可读性和不可达原因。对旧建库风险的条目标 LEGACY_DIAGNOSTIC 或 BLOCKED，不能为了凑满 54 个悄悄换前缀。
2. 设计至少四类互相独立的结果标签：存在合法相关候选、当前值得读取、Generator 正确使用或合理忽略、自然支持实际收益。RS 适用性与无候选单列；人工审阅时必须看原文，不凭 BGE 排名或开发者预判自动当 Recall 金标。
3. 预先冻结同 G 对照：OFF、MP/ME/MS/RS 单头、两头组合、ALL 可行项；对 RS 单独比较 R0、F-resident、Method、Method+case。相同方法卡和同一 prefix 下，Method+case 只能额外增加案例，不允许改变基础方法质量。
4. 针对“已拒建议”“过时事实”“第三人经历”“建议/尝试/完成混淆”“虽相关但无需主动提及”“无合法来源”提供盲评对照表、随机位置、tie/uncertain、错误类型和独立源/owner/family 集合。现有 54 个条件的计划不等于已经完成 54 次生成。
5. 对 G0e Notes vs A 的边界阅读块准备相同源内容的 paired protocol；包装变化、资源内容变化、ranker 变化、G 变化四个因素分开验证；不得用“引用历史比例更高”充当帮助性改善。

## 4. NeedCard/J1 奖励资格：把新方案变成可检查流程

1. 保全 pilot v2 的固定 plan_sha256=b1d3225b4e9b9442c2d2e7c1730ea7645e2168bd5987a2d9138fa77adca1598f、20 次首次调用、零重问、调用前阻塞和 S1–S5 停止条件。继续仅 CPU preflight；请求研究者明确批准以后才能运行。既有 v1 40-call 计划保留，不做自动替换。
2. 六项逐卡人工审核和证据错误率≤10%、B6e 八前缀各有一张 valid 卡的硬门槛不变。无真实 writer 卡就记录零卡，不能提交虚构“valid”。NeedCard required 必须真正依赖当时严格过去，relevant_optional 不引用不惩罚，must_not_contradict 不允许过时建议/错误人物。
3. J1 v3 800-token 缺口保留为未解决容量风险；独立提交“按前缀输出预算+解码版本”的方案与静态 token 测量，注明最大4,096是**提议**、是否覆盖最坏长输出、context 总预算以及人工批准门。未获批准不得改协议 v3 JudgeIdentity 或隐式采用新 max_new_tokens。
4. 不确定输出处理：truncated 与 JSON parse/error/ref mismatch 分开；原子错误归属 L1–L8 与 H-/I 冲突审查；所有不完整终点 pending，未知构成下上界，不填0、不因不同资源子集各删不同检查项改变分母。
5. 设计小规模 H1 人评校准包：来源正确、时序、主体、负例建议、真正无需历史、同等回复、支持质量、安全等分层；保留人工与 J1/J2 不一致；双盲和候选左右随机；不得要求模型 Judge 替代研究者盲核。

## 5. Phase-1 环境和在线等待：准备但不扩大运行

1. 保留已有 16 子集 FiniteHead 环境和 STOP/GET 动作语义；外层用户历史进程是 exogenous replay，内层是单轮 GET/STOP，不得在论文中称已训练出跨月影响用户行为的 policy。
2. 补充用于科研的 SnapshotBinding、观测遮罩、invalid GET、source readiness、缺失终点、reward interval、NoText 消融与可重放缓存测试；不把测试生成的 FIXTURE reward 当成已取得的真实模型效果。
3. 先在 CPU 预注册主要比较：OFF、ALL、Fixed-best、F-resident、Rule、OneShot、Seq-BC、BC-union、PPO、NoText，明确 owner/family 分组、多重比较、失败/缺失记录。S288/M482/L-realized748 只是计划规模和采样口径，不能将不可行 L960 改称正式实现。
4. 与 A0 区分真实请求用户等待与离线标注成本：首个有效可见文本、完整文本、最终 Tokkio 首有效语音，均报 p50/p95、失败/兜底与队列影响。B1 writer 的 Qwen 时间不是 J1 Judge 时间，更不是在线 G/PM 的延迟；准备独立测量 manifest 与工具接口。

## 6. 验收与提交

本轮输出：

- integration / #10 / #11 最新真实状态、实际 SHA 与 CI；
- G0e 正式绑定（如集成条件满足）及旧/新 key 隔离报告，否则明确 BLOCKED；
- B↔A PrefixAsOfBinding 与可见/私有白名单审查、3–5 owners 独立 cutoff 检查；
- 54 个旧提案的 eligibility 与盲评/RS 四方案/Notes 对照的**未执行**生成计划；
- B1 pilot v2 待授权清单、J1 容量修订需研究者批准的候选版本、人评资格/不足清单；
- Phase-1/DP/BC/PPO 的 CPU fixture 回归与强基线公平性方案；
- 源与任务身份 manifest、全部原始日志、CI、remaining blockers；
- 对 A 的正式交接提案及是否需要 C0 新 schema 的书面理由。

不运行任何 GPU、模型推理、判官、生成、训练、付费 API；不启动 B6e；不擅自合并任何 PR、不改 global EXECUTION_STATE/H0；不要宣称 B1/B2/B3/B6e 或自然支持收益已完成。若研究者正式授权某项独立实验，以对应已冻结 plan SHA 和确切范围另开新执行回合，不把本指令当授权。
