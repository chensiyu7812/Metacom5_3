# 下一轮给 WS-A 的指令：V3.2 时间一致资源环境（CPU 先行）

你继续负责 PM-RL1 WS-A，但本轮**首先解决研究环境的时间一致性和四资源的可验证能力**，不要把 PR #13 的只读审查直接写成 A3/A4/A5 已完成，也不要把 bank-v0 的合法读取误当资源质量提升。

研究者已同意**编写**新的 V3.2 研究方案候选。先阅读项目中的 PM_RL1_RESEARCH_PLAN_V3_2_CANDIDATE_20261118_ZH.md，并与 V3.1、RESOURCE_SPEC_ZH.md、PR #13 审查以及最新正式 integration 对照。V3.2 文档还需要正式治理/采纳；本轮只执行范围清楚的 CPU 准备与独立审查，不自行修改全局 EXECUTION_STATE、H0 或任何旧冻结证据。

**本指令不是 GPU 授权。不得加载 Gemma/Qwen 权重、运行生成、判官、SFT、PPO 或付费 API；也不得启动 B 的 120 个 B6e 终点。**

## 1. 开工检查与历史保全

1. 查询 PR #10（G0e）、#11（B）、#12（A 后续）、#13（本次审查）、#4（未采纳 V3.1）及 integration 的最新真实状态和 HEAD，不把历史消息当当前状态。
2. PR #13 的 ea2f5bde 是**审查和待验证提案**；3,188 条 bank、83 条候选、54 条输入提案及 120 请求属于旧身份，必须保持可复核，不能覆盖、改名或挪用奖励。
3. 如果 #10 尚未合入，独立开展不依赖 G0e 提交的来源/时间 CPU 原型；从当前 integration 新建**单独工作分支**，不要向 #10/#12/#13 已冻结 PR 混入新代码。#10 由 integration owner 合入。
4. 保留现有 C0 0.2.0 和 A1/A1b/B5 的正式 manifest、source/bank/index SHA、旧 TerminalKey、G0e 最终身份与 100 条 OFF 原生 token IDs。任何 C0 对外字段变更先与 B 出书面兼容清单，由 integration owner 评审。

## 2. P1：chronological as-of 环境最小可执行原型

优先级最高。目标不是一次性重编译全部 401 会话，而是用既有 A1 可信 RAW 创建**可执行、可重复、时间不作弊**的记忆构建器。

1. 在 A-owned 来源/编译模块里，提出并实现独立版本的 as_of(prefix, writer_identity) 或等价 CPU 入口：每次仅消耗 cutoff 前已完成且当时已获知、已 ready 的会话；当前可见话语不作为已经写回的长期资源。
2. 三时间字段必须明确：event_time（事实何时成立，可能 unknown）、known_at/reported_at（何时被告诉系统）、ready_at（Writer 完成可读）；valid_from/valid_to 与更新的获知时间不可混为一个值。
3. 以 append-only ledger 保存候选 MP 原子事实、ME 事件及阶段、更正/否定/冲突链；一条记录必须绑定原话 span、speaker、owner、family、版本及语义核查状态。来源不足就保留 unknown 或原话，不得创造看似确定的当前画像。
4. 必须实测 PR #13 指出的旧 MP 全轨迹 latest 选择偏差：选取有前后更正的真实 owner/会话，从空状态按 rank 顺序重放；比较每个 cutoff 的“可写入/可读成员”与旧 bank-v0，记录差异来源。不得将 324 个隔离 MP 直接放回正式 bank。
5. 用至少 3–5 名 owner 和足以包含时间变化的若干会话及前缀，提供每个时点的 SOURCE_FRONTIER、LEDGER、SNAPSHOT manifest；样本数和筛选依据固定，称作**开发/机制测试**，不叫独立金标。
6. 必须通过 CPU 不变量：未来追加不改过去 snapshot 和候选、stream/batch 同 cutoff 等价、重复写幂等、owner/family 隔离、计划/尝试/完成区分、人物自他边界、r5 新知不进入 r4、未知时间不杜撰。任何机械越权 fail-closed；附最小真实反例与单元测试。

## 3. P2：四头存储与表示的可靠最小包

此阶段只准备受审样本和有身份的候选接口，**不重做整个 bank，也不实施 A5**。

- MP：先实现 subject/slot/validity/provenance 的结构；对于错主体、身份不明或缺明确更正的条目输出 unknown/quarantine，不允许“全历史最后出现的一条一定正确”。
- ME：至少对 suggested、intended、attempted、completed 或 outcome_reported、rejected、unknown 做源证据测试；同事件链只接受证据支持的关系，不引入未证实图推理。
- MS：保留 RAW 不变；设计 SUM + 每句父文跨度 + unusable + RAW fallback 身份。CPU 结构和校验先做，真实模型生成摘要须研究者另批；比较 RAW/SUM 不能同时换排序/G。
- RS：先建立一小套**低风险、有合法来源且可人工核对**的 METHOD 候选，字段包括适用、禁用、动作、来源、许可、误用；CASE 独立附加。制作四臂 R0、F-resident、METHOD、METHOD+CASE 的公平输入规范，明确 F 有额外 token 而非 OFF，CASE 不得伪装用户经历。尚未通过审查的 RS 不进入正向可调用池。
- 四头是统一 GET 接口下四种类型化读取视图，可以用 SQLite/JSONL；不要只因方案讨论图/混合检索就提前启动知识图谱、BGE/BM25/RRF，仍保留词面-v0 对照。

## 4. 现有审查材料的真正后续

1. 使用 PR #13 已提供的 83 条候选与 1,876 记录 catalog，对每条增加/检查 as-of eligibility、源文跨度、主体、事件阶段、是否当前有效、适用性、读取必要性和“相关但无需提及”字段；让人工判断保持 unreviewed，不代人评。
2. 对 54 个已提出的 D/E 输入形成逐项 eligibility matrix：哪些旧 v0 条目来源合法、哪些受全轨迹建库选择影响、哪些需要新的 as-of materialization；不能偷偷重新挑一组更有利的输入。记录 BLOCKED/ELIGIBLE/LEGACY_DIAGNOSTIC 及理由。
3. 在**相同合法源材料**下准备当前 G0e Notes 与新“带人物/阶段/可选忽略边界”的渲染对照。输入内容和包装同时变更的情况要拆成独立因素；原版 renderer/G0e 不变，新候选必须另立身份并与 B 审阅 TerminalKey 规则。
4. 提供 A0 延迟测量需求：prefill/decode、首可见有效文本、完整完成、GPU/CPU/缓存和资源组合耗时；Gemma/Qwen 真实 A6000 测量仍 pending。保留已交付最多 Gemma154/Qwen7 的 A0 有界方案，不增预算、不自行执行。

## 5. 联合交付和止损

在提交前与 B 交换 source frontier/材料化快照身份和字段白名单，由 B 对至少若干同 owner 的切点独立重建对照；**不向 B 提供任何未来标签作为 PM observation**。

本轮交付：

1. 实际 integration base SHA、独立新 PR 与 commit SHA；
2. as-of Writer 的最小模块/sidecar、输入和输出 manifest、从旧 bank 的差异报告；
3. prefix-extension/流式等价/人物阶段/越界的 CPU pytest 与原始日志；
4. MP/ME/MS/RS 最小受审资源样例和来源、许可、阅读白名单；
5. 83 候选、54 输入的 eligibility/blocked/legacy 对照与新 renderer 候选身份；
6. B 联合检查收据、CI、版本冻结和剩余 GPU/人工审查阻塞。

**禁止宣称**：V3.2 已采纳、A3/A4/A5/A6/A7 已完成、BGE 检索改善、支持质量改善、自动记忆 Writer 已验证全体数据、独立人评或真实延迟已经发生。

如果改动旧 C0 Schema、旧 bank、EXECUTION_STATE 或任何冻结文件不可避免，先停下来报告冲突及最小迁移设计，不自行重写。提交内容尽量是 additive 的版本新文件、保留旧 SHA。所有模型调用等研究者独立授权。
