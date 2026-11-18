# WS-A：V3.2 P0–P2 时间一致 CPU 原型

日期：2026-11-18（日本时间）。范围：研究者本轮明确授权的 CPU 开发、测试、跨线工程审阅及独立 PR。方案为 PR #14 `f26e7cf8e2c4a728a0d36078700ea676b47223ef`；最新核对 integration base 为 `320a33d1d871199d171f998300ce926b341ca1a8`。分支：`pmrl1-v3/ws-a-asof-cpu-20261118`。本报告不登记 H0 采纳，不更新 EXECUTION_STATE，不合并旧 PR。

## 已实现及证据入口

新模块 `rl1v3/compile/asof.py` 提供独立版本的私有 `PrefixAsOf / SourceFrontier / LedgerRecord / Ledger / materialize / load_snapshot`，并保留 C0 ReadingView 形状的受控 GET。账本一条记录一个不可变文件，原子发布、同内容重试 NOOP；更正、否定、矛盾均追加新记录。数据盘支持重启再加载；这是单 writer CPU 原型，不宣称已经实现并发写服务或真实异步延迟。

主证据目录为 [asof_cpu_20261118](../outputs/pm_rl1/v3/asof_cpu_20261118/RESULTS_ZH.md)，最终可复核产物为 `cpu_v3/`，包含：

- 3 位固定开发 owner：p1、p15、p18；逐次提交全部 68 会话，在下一会话的真实 seeker→supporter 切点物化 65 份快照（31/21/13）。每位最后会话只提交，不伪造其后的真实 prefix。
- 93 条账本记录：68 RAW、14 个 MP/ME 语义候选、11 个 unusable 的单命题 SUM 结构示例。14 项语义均为 AI 开发预筛，**人工核准数为零**；没有模型抽取或模型摘要。候选未进入可调用 MP/ME 正向池。
- `snapshots/`、`LEDGER.jsonl`、`SNAPSHOT_DIFFS.jsonl`、`request_frontiers/`、完整 source frontier 与 snapshot SHA；`MANIFEST.json` 固定输入 Git commit、原文件 SHA 和实际代码文件 SHA。
- `LEGACY_LATEST_RISK.json` 逐项列出 324 条旧 MP 隔离记录、精确原文、后继 rank，以及 65 个切点的全历史 latest 与前缀 latest 的诊断差异。两种 legacy latest 都不当作新事实抽取器。
- `BANK_INVENTORY.jsonl` 保留全部 3,188 条旧身份；`SAMPLE_83_ELIGIBILITY.jsonl`、`ALL_SAMPLE_CANDIDATE_ELIGIBILITY.jsonl` 覆盖原 83 个开发样本的全部 18,578 个候选上下文，以及固定 1,876 个不同候选 catalog 身份。
- `INPUT_54_ELIGIBILITY.jsonl` 与原 54 项逐项对应；`FIXED_54_PROPOSAL_COPY.json` 保留原 proposal。没有更换样本或补造两项不可达的 MP 条件。
- `OLD_120_REQUEST_PRESERVATION.jsonl` 核对全部旧请求、旧 key、原生 token ID 数量与 hash；新 `TYPED_REQUEST_PROPOSALS.jsonl` 保留同一原话证据和系统基线，另建 renderer 与请求提案身份。

## 三时间与快照含义

源会话 r 内的原话保留 `reported_at=(源日期,r)`；完成后可提交的最早逻辑 `known_at=r+1`，`ready_at>=known_at`。late-known/late-ready 可分别延迟。当前会话只提供合法可见 prefix，不写入本轮长期 memory。`event_time`、`valid_from/valid_to` 是事实叙述的时间，可能早于获知，未知保持 null；事实日期可仅有 date，不能硬转成 rank。

更正在 r5 得知、r7 才 ready，可以记录事实在 r2 已结束，但 r4 和 r6 的读取不因此改变。旧 row 不回写 `valid_to`，新 relation 同时保存 `invalidated_knowledge_time`、`readable_at` 和 `fact_valid_to`。没有经过核准的关系不改变投影；无明确更正的同 subject/slot 记录并存为 conflict，GET 拒绝静默挑最新一条。

snapshot 身份绑定合法可见 prefix、writer、合法逐会话 frontier 和已到时点的 ledger；不绑定全 registry version、全 corpus 文件 hash、未来候选池或当前会话尚不可见的后续文字。全文件 SHA 在审计 manifest 单独保留。每会话 source binding 包含 owner、dataset、family/ancestors、rank、已知日期、许可及 transcript hash。追加未来材料或改变全 corpus 文件 hash不改变过去快照；改变真实过去原文则必须改变身份。

所有 rank 均是 owner 内坐标。p13 与 p18 的 `esc1198` 虽共享 family 和相同原文，仍不能互读个人记忆。RS 使用独立外部版本和实验准备日期，不与个人会话 rank 比较；四臂是固定外部知识条件的待执行对照，并不声称该材料当年已在真实部署中安装。

## 资格结果及其限制

| 原集合 | ELIGIBLE | BLOCKED | LEGACY_DIAGNOSTIC |
|---|---:|---:|---:|
| 83 开发样本 | 20 | 23 | 40 |
| 54 原输入提案 | 16 | 14 | 24 |

`ELIGIBLE` 只表示本轮机械输入资格，主要为完整 RAW/真 OFF；不是语义正确、当前值得读取、自然支持收益或正式实验许可。`BLOCKED` 包含无合法候选及受全历史 latest 入池选择影响的 MP；不等于已发现未来文字曾送给 G。`LEGACY_DIAGNOSTIC` 可以复核旧读取，但 ME 阶段/主体、RS 适用性等未达到 V3.2 语义资格。每项独立保留 `as_of_source_eligible`，避免将 source 合法与 writer 合格混为一谈。

source span 数、hash 和冻结 bank 内定位均可回查；subject/current validity 为 unknown，worth_reading 和 relevant_but_need_not_mention 为 null。它们是尚未人工判断的问题，不是 false/零。旧 324 MP 没有恢复到 bank-v0；本次新 writer 不以该旧候选池作输入。

## 四资源与 Generator 表示

MP 具有 subject、slot、有效时间和有证据的更正对象；未知主体保持隔离。ME 内部区分 suggested/intended/attempted/completed/outcome_reported/rejected/unknown。C0 0.2.0 未定义 rejected，因此兼容方案是内部保留 rejected，已有 ReadingView.stage 使用 unknown，正文明确历史拒绝；不修改共享 enum。

MS 保留逐轮完整 RAW、父文身份和单命题跨度；SUM 未审/失效时返回明确的 `SUM_TO_RAW_FALLBACK` 私有计划和独立身份。没有把 fallback 当作纯 SUM 成果，也没有加入 EXPAND 动作。

RS 准备两张低风险交流动作 METHOD 候选（邀请展开、暂定式复述），与一条 ESConv train CASE 分表。来源为 SAMHSA TIP 35 第3章，保留来源域、适用/禁用、动作、误用、许可说明和未审状态。官方索引文本可核对，PDF 正文访问本轮返回 403；逐项版权例外和日常支持迁移审查保持 pending。来源公开不等于方法对本任务有效，也没有临床/危机用途批准。四臂 R0/F-resident/METHOD/METHOD+CASE 使用同 prefix、同 G 条件；F 有额外文本，METHOD+CASE 的 METHOD 部分字节完全相同。CASE 与方法的语义关联未验证，非 R0 条件均不开放正式调用。原方法依据见 [SAMHSA TIP 35](https://library.samhsa.gov/sites/default/files/tip-35-pep19-02-01-003.pdf)，许可线索见 [NCBI 收录](https://www.ncbi.nlm.nih.gov/books/NBK571068/table/ch3.t4/)。

新 renderer 只从合法 C0 prefix 和经 frozen bank 重新核验的 ReadingView 建立人物/阶段/证据/可忽略边界块。旧 Notes、旧 G0e、旧 TerminalKey 均不变。新请求身份绑定 prefix、frontier、snapshot、writer、renderer、证据、messages、G/decode/Step-2；旧 key 仅为私有映射。54 份新对象都是**不可执行的请求提案**，新原生分词/容量、真实 G 阅读与质量均 pending，`input_ids=null`，`terminal_result=null`，绝不迁移旧 reward。

## B 联合记录与治理

[接口冻结候选](../outputs/pm_rl1/v3/asof_cpu_20261118/INTERFACE_FREEZE_CANDIDATE.json) 明确 executor-private、PM、G 可见字段和身份迁移规则。B 独立直接解析 sources.jsonl 构造 65 个真实切点 oracle，未调用 A 的筛选器来制造期望值；另测试共享 family 跨 owner、未来追加、晚 ready、事实日期、建议/执行、未知主体、更正、冲突、同证据 renderer 和 OFF。

B 是独立 Codex 工程审阅，不冒充人评或现有 WS-B owner / integration owner 的正式采纳。初审缺陷及修复重验全部保留。C0 公共 Schema、32 份 schema 文件、全局状态未变；本轮不需要以修改公共 Schema 为前提推进。正式消费绑定仍由 B owner/integration owner 按治理审阅，不能把候选接口的 AI 工程通过写成 H0。

## 人工审查、A0 与剩余阻塞

研究者明确要求五项保持待审；[审查包](../outputs/pm_rl1/v3/asof_cpu_20261118/human_review/HUMAN_REVIEW_PACKET_ZH.md) 给出每项完整原话、speaker、owner/session/rank、原 turn index、前后文、完整会话 JSON、精确字符跨度和来源 SHA。第②条省略内容已完整恢复。待审标签没有被写成已验证事实。

保留 PR #12 的 A0 有界计划（Gemma 最多154/Qwen7）、100 OFF 请求和原生 token IDs；本轮不扩预算、不执行。后续同一栈应分别测客户端请求结束→首个有效可见文本、完整完成，以及过滤/检索/序列化/分词/prefill/decode、cold/warm、cache hit/miss、GPU/CPU 队列、失败/回退。新表示及 RS 四臂的原生容量需另行 CPU 分词核查；CPU snapshot 构建时间不能替代用户等待或模型吞吐。

剩余：真实五项及其余语义人工审查、自动抽取与摘要模型接口资格、RS 来源/版权例外/适用与方法—案例关联审查、正式 B/integration 采纳、原生请求容量、A0/G0、Judge/人评和同 G/OFF 资源增量质量。没有进行 GPU、生成、Judge、研究训练或付费调用。完整 CPU suite 含既有确定性算法/优化器单元测试，不生成研究训练检查点。

工程测试通过只支持上述机制，不宣布 A4/A5/A6/A7、完整 bank-v1 或研究级资源收益完成。

## 复跑

```bash
git fetch origin pull/12/head:refs/remotes/origin/pr12 pull/13/head:refs/remotes/origin/pr13
CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONPATH=project/src python project/scripts/rl1v3/asof_cpu_replay.py \
  --out /absolute/path/to/new-empty-output
PYTHONPATH=project/src python -m pytest -q \
  project/tests/test_rl1v3_asof_writer.py project/tests/test_rl1v3_asof_b_acceptance.py
```

脚本不联网、不加载分词器/权重、拒绝覆盖已有输出。依赖标准项目 Python 环境。最终 CI、实际计数、原始日志及跳过项见任务 RESULTS 和 validation，不将历史 skip 算作覆盖。
