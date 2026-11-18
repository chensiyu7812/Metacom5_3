# WS-B V3.2 P0–P2：as-of 绑定、资源价值协议与奖励资格（CPU，2026-11-18）

- 分支：`pmrl1-v3/ws-b-v32-p0p2`，基于 PR #11 head `dd33e131`（叠在 #11 上；**#11 冻结交付一字未改**）。
- 证据等级：全部为 engineering_only。
- 本轮**没有**：GPU、Generator、NeedCard writer、Judge、PPO/SFT、付费 API；没有运行 B6e 的 120 个终点或任何一次 J1 判定；没有改动 H0、EXECUTION_STATE、C0，也没有改动 B1/B2/B5/B6e 的冻结证据；没有合并任何 PR。
- 本文中的"计划""协议""候选"都没有执行；所有 quality/result 字段都是 null。

## 0. 结论

1. **G0e 正式绑定：BLOCKED。** PR #10 仍为 OPEN，自 00:06Z 起没有活动。因此 #11 保持 Draft，本轮也没有把任何临时合成的分支当作验收。#10 合入后的步骤见第 2 节。
2. **bank-v0 的时间一致性问题，问题出在入池规则，而不在编译器。** 旧编译器的输入是按时间顺序的：401/401 个会话的 prior-profile 哈希，只用严格过去的单元就能逐一重算出来。但 bank-v0 的 MP 池按"全轨迹最新值"入池，导致 **4,119 个前缀中有 3,460 个（84%）的 MP 合法池小于时间一致池**。反方向的差异为 0：旧池从不多出记录，只会缺记录。
3. 在 B6e 的 8 个前缀上，按同一 lexical-v0 规则重新取 MP Top-1：4 个与旧结果相同，3 个不同。ab3d17 的 MP 在旧库中"无合法候选"，**在时间一致池里有 2 个候选**，也就是说这个"不可达"本身就是全历史投影造成的。
4. **A 的 as-of sidecar（PR #15，`b63635f3`）通过 B 的独立机械检查**：p1/p15/p18 共 65 个真实切点全部通过。X5a 无法从导出文件检验，详见 `ASOF_JOINT_RECEIPT_ZH.md`。
5. **54 个输入的联合资格**：ELIGIBLE 16（8 个 OFF + 8 个 MS-RAW）、LEGACY_DIAGNOSTIC 24（RS、ME、ME+MS 各 8）、BLOCKED 14（MP、MP+MS 各 7），与 A 的判定逐项一致。B 的时间合法性轴本身给出 48 ELIGIBLE / 6 LEGACY。两轴共有 38 处不同，**全部是 A 的写入器/语义轴更严**；B 的判定从未比 A 更严。联合标签取两者中更保守的那个。54 个输入一个都没有更换。
6. **奖励**：NeedCard pilot v2 计划（`b1d3225b…`）的 CPU 复核通过，权重 SHA 已核对，writer 调用 0 次。J1 输出容量的新发现：如果回复是**一整句** 240 token 的长句，13 项检查表的最坏输出就有 6,981 token；多句回复（8 句 × 30 词）在 40 项时最坏为 5,223 token。新 decode 方案只是**候选**，需要研究者在两个上限之间做选择（第 7 节）。
7. **环境与基线**：完成 as-of 绑定的 episode、类型化的非法 GET、观察遮罩、NoText、奖励区间（pending 时不给数值）、按版本隔离的重放缓存，以及 11 个对照臂的公平性契约。B6e 8 个前缀的全部 471 个读取顺序共 942 次观察（含 NoText），**0 泄漏**。

## 1. 真实集成与 PR 状态（2026-11-18T12:23Z 查询）

| PR | 分支 → base | head | 状态 |
|---|---|---|---|
| integration | `pmrl1-v3/integration` | `320a33d1d871199d171f998300ce926b341ca1a8` | 本轮未变 |
| #4 | V3.1 候选 → main | `75689002` | OPEN，未采纳 |
| #10 | WS-A G0e → integration | `73fdb12f29b6970a268eeda704d73e1bd35b1c3e` | **OPEN，未合入**（最后活动 00:06Z） |
| #11 | WS-B S3 → integration | `dd33e1311eea56a9312e99c7f237e928ee09fe12` | Draft，保持不动 |
| #12 | WS-A G0e binding → #10 分支 | `8ba20d21` | Draft |
| #13 | WS-A 四资源审查 → integration | `ea2f5bde04caba4590b26c80a572d66caa4a2d08` | OPEN |
| #14 | V3.2 方案 → integration | `f26e7cf8` | Draft |
| #15 | WS-A as-of CPU → integration | `b63635f3621f3a5d252099efcd58ae2d1958dce2` | Draft（本轮新出现，B 已复核，见第 3 节） |

## 2. G0e 正式绑定：BLOCKED

- 原因：PR #10 没有被 integration owner 合入。按指令，#11 不能用临时合成分支验收。
- 不依赖 G0e 的工作照常推进（第 3–9 节）。
- #10 合入后，按以下步骤执行，均已在 round 7 演练过：
  1. 把新 integration 普通合并进 `pmrl1-v3/ws-b-s3`；
  2. 运行 `B6e_g0e_binding_addendum.py`，输出到新目录 `v3_g0e_addendum/`，核对：
     - 8 个前缀、120 个可达终点、471 个读取顺序；
     - G0ePrefixPort 和 request_packet；
     - 新的 TerminalKey、trace 和请求 SHA；
     - PM/G 不泄漏 NeedCard、Judge、未来或私有字段；
     - 旧 B5 key 和 reward 完整保留，用旧 key 查新 key 必须查不到；所有 STOP 保持 pending；
  3. 跑 V3 严格测试、完整 CPU 和 PR CI，然后执行 `gh pr ready 11`，由 integration owner 合入。
- 本分支新增的 G 载荷白名单扫描（第 3.3 节），届时会直接用于这 120 个新请求。

## 3. PrefixAsOfBinding、可见性与 A 联合检查（P1）

### 3.1 绑定（`src/metacom_pm/rl1v3/asof/binding.py`，提案，不改 C0）

字段分为五组：

| 组 | 字段 |
|---|---|
| 前缀与切点 | prefix / cutoff |
| 来源与写入 | source_frontier、writer_identity、writer_kind |
| 快照与资源 | snapshot_sha、external_snapshot（只用 RS 自身版本） |
| 生成链身份 | bank / index / query、renderer、G、decode、Step-2 |
| 归属与可见性 | owner、family closure、visibility_policy |

另有 tier（legacy_engineering / research_candidate / research_qualified）。

`validate()` 采取 fail-closed：
- frontier 必须与 registry 的合法历史**完全一致**：不能多、不能少、不能来自未来、不能包含当前会话；
- research tier 必须使用时间顺序的 writer，且所有身份字段都不能是占位值（not_run、tokenizer-only、not-frozen 等）；
- bank-v0 只能是 `legacy_engineering`。

身份**不含 fold，也不含任何全局语料哈希**（与 A 的接口候选对齐），这样追加未来会话不会改变过去的绑定。

C0 迁移只是提案：在 TerminalKey 中加入 `asof_binding_sha256`。在此之前，B 侧使用复合键 `asof_terminal_key_sha256(C0 key, binding)`。

B6e 8 个前缀的 legacy 绑定已写出（`asof/B6E_LEGACY_BINDINGS.json`），validate 全部 0 问题。tier 都是 legacy_engineering，原因：MP 入池依赖 cutoff 之后的会话。

### 3.2 三张白名单（`asof/visibility.py`，SHA `ac4a256e…`）

| 白名单 | 内容 | 不得出现 |
|---|---|---|
| PM 观察 | C0 Observation（可见前缀、已读 ReadingView、可用性计数、动作 mask、input tokens） | — |
| PM 观察（NoText） | 同上，只去掉 reading_text | — |
| Generator 请求 | messages、input_ids、decode | — |
| 评价侧（NeedCard writer、检查表、Judge、人评） | 严格过去的合法证据 | NeedCard、检查表、Judge、未来文本、检索分数、最优子集、stratum、reward 等任何反向流入 PM/G 的信息 |
| 审计员 | 可以看到全部，包括未来 | 只做泄漏审计，不产出标签 |

扫描器拒绝以下内容：白名单外的字段路径、禁用键、私有 ID 或哈希、未来话语。与合法文本逐字相同的未来话语（例如固定问候语）单独计数，不算泄漏。

### 3.3 扫描结果（`visibility/VISIBILITY_SCAN.json`）

**PM 观察**
- 范围：B6e 8 个前缀的全部读取顺序，每个前缀检查数十到数百条未来话语（54–547 条）。
- 结果：471 个读取顺序、942 次观察（每个顺序都检查完整版和 NoText 版），**0 泄漏**。
- 对不可用的 MP 头（ab3d17）执行 GET，得到类型化的 `no_legal_candidates`，状态不变。

**G 载荷**
- 范围：PR #13 的 2 个 G0e fixture 请求，检查 183 条未来话语。
- 结果：0 泄漏（有 1 条与合法文本相同，单独计数）。
- 其余 118 个 G0e 请求要等 #10 合入后用附录检查。

### 3.4 bank-v0 的独立 as-of 审计（`asof/`）

| 检查 | 结果 |
|---|---|
| 编译器输入边界（只用严格过去单元，重算 prior-profile 哈希） | 401/401 重现；单元与会话、rank 的错配为 0 |
| MP 合法池 vs 时间一致池（4,119 个前缀） | 3,460 个前缀不同；时间一致池多出的单元共 12,663 次（按前缀累计）；旧池多出的为 0 |
| B6e 8 个前缀的 MP Top-1 反事实（同一 lexical-v0 规则） | same 4；differs 3（b60fe8、ac45ce、74a7a9）；ab3d17 旧库无候选、时间一致池有 2 个 |
| 交换格式对照（B6e 8 个 owner 的 192 个切点 × 2 个 horizon） | bank-v0 规则：175 处 X5a 违规（追加未来会话改变了早期池）；按时间一致方式重建：0 违规 |

ME 是整体迁移的，没有做投影；MS 是完整 RAW；RS 是外部预装快照。它们的时间合法性归结为 registry 规则，所有切点上 X1–X4 都是 0 违规。经过修复的记录（development_reviewed）仍然列入人工核查。

### 3.5 A 的 3 个 owner、65 个切点

逐项结果和请 A 补充的 4 件事见 `ASOF_JOINT_RECEIPT_ZH.md`。**机械层全部通过**；X5a 需要 A 导出双 horizon 文件才能检验。

## 4. 54 个输入的资格与未执行清单（P2）

文件：`p2/ELIGIBILITY_54.json`（逐项列出两轴标签、分歧、每个头的事实、预筛线索）。

| 子集 | 个数 | B 时间合法性 | A 写入器/语义 | 联合 |
|---|---:|---|---|---|
| OFF | 8 | ELIGIBLE | ELIGIBLE | **ELIGIBLE** |
| MS | 8 | ELIGIBLE | ELIGIBLE | **ELIGIBLE** |
| RS | 8 | ELIGIBLE（但只是 case-only v0 参照臂，不属于 RS 四方案） | LEGACY_DIAGNOSTIC | **LEGACY_DIAGNOSTIC** |
| ME | 8 | ELIGIBLE | LEGACY_DIAGNOSTIC（阶段、主体未审） | **LEGACY_DIAGNOSTIC** |
| ME+MS | 8 | ELIGIBLE | LEGACY_DIAGNOSTIC | **LEGACY_DIAGNOSTIC** |
| MP | 7 | 4 个 ELIGIBLE（交付单元相同）、3 个 LEGACY | BLOCKED | **BLOCKED** |
| MP+MS | 7 | 同 MP | BLOCKED | **BLOCKED** |
| 未列入（ab3d17 的 MP、MP+MS） | 2 | BLOCKED（旧库不可达，时间一致池可达） | — | BLOCKED；不补零；不纳入 54；如需加入，要另立身份 |

对每个输入回答五个问题：

| 问题 | 回答方式 |
|---|---|
| 是否合法 | 机械判定 |
| 是否有合法候选 | 机械判定 |
| 是否相关、当前是否值得读取 | `pending_human` |
| Generator 能否正确使用或合理忽略 | `not_answerable_before_generation` |
| 需要哪些人工语义核查 | 逐项列出：主体、阶段、是否过时、是否需要主动提及、RS 是否适用、外部案例不是用户经历、两头是否读到同一会话（重复信息）、修复后的转述与原话是否一致 |

七种诊断情形：词面预筛只是给人工核查用的提示，不能当作标签。

| 情形 | 内容 | 覆盖情况 |
|---|---|---|
| S1 | 历史补充了必要信息 | 由人工标签决定；46 个资源输入都是候选 |
| S2 | 有合法资源，但当前请求不需要 | 同 S1 |
| S3 | 关键信息已过时 | 预筛命中 21 个 |
| S4 | 资源可能导致不恰当的建议 | 预筛命中 22 个 |
| S5 | 用户已拒绝或已尝试失败的建议 | 预筛命中 9 个 |
| S6 | 第三人信息可能被当成用户经历 | 预筛命中 36 个 |
| S7 | 完全没有合法的个人历史来源 | **54 个输入中没有覆盖** |

S7 的补充方案（提案，不替换 54 中的任何输入）：
- 选样规则：每个 B6e owner 取 rank-0 会话中 sample_key 最小的前缀；
- 另立身份，需研究者批准；
- 选样在任何生成之前完成。

## 5. 资源比较协议（P2，冻结 SHA `2b6057c8dde4b443c08fd3ff281cb6c22c3ebd1f4d1a02eab8ac948a7bd4c81f`）

所有比较固定以下条件：同一个 G0e、系统提示、decode、可见前缀、合法来源，以及 lexical-v0 检索。**每个实验族只改变一个因素**。

| 实验族 | 比较内容 | 输入 |
|---|---|---|
| EXP-D | OFF vs RS / MP / ME / MS 单头 | 已冻结的 39 个 D 输入 |
| EXP-E | MP+MS、ME+MS vs 各自的组成部分 vs OFF | 已冻结的 15 个 E 输入；只报告序数模式，不做加法交互分 |
| EXP-E tier-2 | RS+MP、RS+ME、RS+MS、MP+ME、ALL | 预注册；必须在看到 tier-1 结果之前一并授权或一并不授权 |
| EXP-RS | R0 / F-resident / METHOD / METHOD+CASE | 8 个前缀全用；新增 24 个输入，R0 与 OFF 共用；材料等 A 提供 |
| EXP-C | G0e Notes vs 有边界的阅读块 | 证据文本相同，只改包装；使用新的 renderer 身份 |

EXP-RS 的约束：
- F-resident 带有常驻文本，永远不能称为 OFF；
- METHOD 卡由只看过可见前缀和方法目录的审阅者在生成前选定（直接提供，属于 E1）；
- METHOD+CASE = 字节完全相同的 METHOD 卡 + 关联的外部案例；
- 缺少材料的臂记为 unavailable，不能临时现写。

盲评设计：

| 任务 | 是否盲 | 内容 |
|---|---|---|
| Q | 盲 | 审阅者看到：可见前缀；该前缀所有条件读到的合法资料并集（对每一对候选都相同）；A/B 两个回复。审阅者看不到：条件名、各回复读了什么、NeedCard、检查表、J1。<br>回答：偏好（A_better / B_better / tie / uncertain）、强度、逐回复错误、正向类别、安全标记。uncertain 不能记为 tie、0 或输。 |
| F | 非盲 | 由另一名审阅者进行，或在 Q 锁定之后进行；给出该回复实际读到的资料，判断错误归因：资料 / Generator / 不明。 |

- 错误类别（预注册）：E1 主体混淆、E2 阶段混淆、E3 过时当现状、E4 重复已拒或已失败的建议、E5 编造历史、E6 强行或不自然地提及历史、E7 资料诱发的不当建议、E8 忽略当前需求、E9 提及笔记或系统、E10 安全、E11 其他。正向类别：P1 正确使用必要信息、P2 相关但合理地不提、P3 个性化且无误。
- 76 个预注册的盲评对（`p2/BLIND_REVIEW_PAIRS.json`）：每个非 OFF 输入对 OFF；每个 E 输入另外对其组成部分。A/B 位置和页面顺序由冻结协议的 SHA 决定。
- 每对需要两名独立审阅者，计算一致性；分歧由第三人裁决，原始标签保留。J1 不担任审阅者。
- 分析：以 8 个 owner 为聚类单位，只做描述性的开发证据，不做显著性检验。禁止：删除难例、反复生成直到满意、用引用率代替帮助性。

## 6. NeedCard 与检查表：角色语义

- pilot v2：`check --verify-weights` 通过（`logs/needcard_pilot_v2_check.log`）：plan_sha256 `b1d3225b…`，0 问题，权重已核对，运行目录不存在，**writer 调用 0 次**，没有授权。
- 门槛全部不变：首次调用 20 次、0 次重问、S1–S5 停止条件、六项逐卡审查、证据错误率 ≤ 10%、B6e 8 个前缀各有一张 valid 卡。

三种角色的语义（`judge/reward_qualification_v1.py`，用冻结的 checklist v3 测试验证）：

| 角色 | 含义 | 检查表中的处理 | 审核对应项 |
|---|---|---|---|
| required | 缺少这条历史，回答当前明确的需求就会出错或答非所问 | 生成 H+ 项，只要求"考虑到"，不要求明确提及 | 审阅者必须写出"缺少它会怎样失败"；写不出来 → stratum_error |
| relevant_optional | 相关但可以不提 | **不生成任何检查项**：不提不扣分；提错由固定的 I 项捕捉 | — |
| must_not_contradict | 不能违背的已知事实 | 生成 H- 项 | — |

测试证实：同一张卡如果把可选项误标为 required，会多出 1 个 H+ 项、总权重 +2。这正是第 8 轮发现的"强迫提及"风险；它由六项审查中的 `optional_not_mislabeled` 和 H1 人评来拦截。

## 7. J1 容量与新 decode 方案（候选，未采用）

文件：`reward/J1_CAPACITY_V2.json`。只用 Qwen3.5-9B 原生 tokenizer 做静态计数，没有运行判官。

最坏输出（缩进 JSON，每项都引用最长句，H-/I 全部失败且各引两处）：

| 检查表项数 | 一般回复（114 tok） | 多句长回复（8×30 词，248 tok） | 一整句长回复（241 tok） |
|---:|---:|---:|---:|
| 9 | 964 | 1,169 | 4,738 |
| 13 | 1,431 | 1,731 | 6,981 |
| 17 | 1,897 | 2,295 | 9,223 |
| 22 | 2,533 | 3,061 | 12,301 |
| 40 | 4,333 | 5,223 | 20,761 |

- 所有形状的最坏输出都超过 800：保留原有风险证据，冻结的 itemjudge-v3（max_new_tokens = 800）不变。
- 输入侧：8 个前缀在 ALL 资料、13 项检查表、320 token 回复下为 3,993–5,965 token；估算 40 项时为 6,747–8,719 token，远低于 32k 的运行上下文。

候选方案 `j1-decode-v1-candidate-2`（状态 PROPOSED_NOT_ADOPTED）：
- 按终点定额：在检查表冻结、回复生成之后，J1 调用之前计算 B = ceil(1.25 × W / 256) × 256，W 是用该回复实际句长算出的最坏输出；
- 超过上限，或输入 + B 超过 32k，则在调用前阻塞，终点保持 pending；
- finish_reason = length 记为 truncated，不原样重问；格式错误只重问一次，缺失项只补问一次；
- 记录 finish_reason、输出 token、预算、输入 token 和耗时。

需要研究者选定上限：

| 上限 | 能覆盖的形状 | 会被阻塞的形状 |
|---|---|---|
| **8,192（推荐）** | 全部多句回复，直到 40 项 | 一整句长回复且 ≥ 13 项 |
| 16,384 | 一整句长回复，直到 22 项 | 更大的形状；离线耗时更长（不计入用户延迟） |

无论选哪一个，都应在生成之后、第一次 J1 调用之前，先报告被阻塞的终点比例，再由研究者确认。批准之前，新的 JudgeIdentity 不得使用。

调用与终点的状态分开登记：
- 调用状态：ok / truncated / parse_failed / pre_call_blocked / call_error；
- 检查项状态：pass / fail / uncertain / bad_evidence_ref / missing；
- 终点状态：complete / pending / refused_pending。

所有未完成的终点都给出 [下界, 上界]，从不填 0。

训练 reward 与最终评价的隔离规则 R1–R8（`check_isolation` 可执行）：
- R1 最终评价使用与训练不同的模型家族和提示；
- R2 / R4 最终标签不参与训练和选择，seed 与 checkpoint 只在开发集上选；
- R3 最终评价的 owner/family 留出；
- R5 未通过资格的 reward 只能用于 engineering_only 结论；
- R6 报告代理指标与独立评价的背离（代理升而独立评价不升，视为 reward hacking 信号）；
- R7 pending 不记 0；
- R8 所有对照臂使用同一 reward 身份、同一反馈预算、同一批前缀。

H1 人评校准包是设计稿：分 8 层，最多 48 项，双盲、左右随机，保留全部分歧。需要真实终点和 NeedCard 才能抽取，目前 0 项。

## 8. 有限头环境与强基线（CPU）

`env/research_v32.py` 保留原有的 STOP/GET 语义（每个头最多读一次，只在 STOP 时给奖励），新增：
- `BoundEpisode`：环境身份必须与 binding 一致；
- `try_step`：非法 GET 返回类型化原因（already_read、no_legal_candidates、over_capacity、max_gets、after_stop、unknown_action、read_failure），状态不变；
- 白名单内的观察，以及 NoText 版本；
- `stop_value`：只返回 complete / partial / pending 区间，pending 没有数值；
- `ReplayCache`：只写一次，身份不同就不命中，禁止迁移。

`evaluate/baselines_v32.py`：
- 11 个对照臂：OFF、ALL、Fixed-best、F-resident、Rule、Random、OneShot、Seq-BC、BC-union、PPO、PPO-NoText；Oracle 只作诊断。
- 7 个预注册对比，Holm 校正，按 owner 聚类 bootstrap。
- `check_fair` 拒绝以下情况：共享身份不同；F-resident 以外的臂换了 renderer；F-resident 没有自己的 renderer；BC-union 的反馈量与 PPO 不同；pending 当作 0。
- 合成任务上的 fixture 结果（`env/BASELINES_FIXTURE.json`）只证明这些臂能跑通，**不是**支持质量或 PPO 的证据。
- S288 / M482 / L-realized748 仍只是计划档位，不可行的 L960 不会复活。

## 9. 用户延迟测量协议（`evaluate/latency_v1.py`）

- 在线指标：请求结束到首个有效可见文本（隐藏计划或无效 JSON 不算）、到完整文本；Tokkio 说话结束到首个有效语音。
- 分组与组成：按 cold/warm 分组；记录缓存、排队、PM、检索、渲染、prefill、decode、隐藏 Step-2、回退和 TTS。
- 报告：p50/p95，以及失败、超时、重试、回退的比例。失败行计入比例，但不计入分位数；分位数按端到端测量，不能把每个 GET 的分位数相加。
- 离线账本与在线账本**分开**：NeedCard writer、检查表、J1/J2、人评、建索引、训练、批量预计算都记在离线账本。在线行里出现离线字段会被直接拒绝。
- 真实 A6000 / Tokkio 测量需要另行授权（每个条件 ≥ 30 次 warm + 10 次 cold，按 seed 交错顺序）。

## 10. 测试、CI 与日志

- 新测试 `tests/test_rl1v3_v32_wsb.py`：37 项，使用真实保留快照和 fixture，不调用模型。
- 本地 V3 严格套件（最终代码 HEAD `cdca8c31`）：**603 passed**，0 skip / xfail / fail；`verify_v3_junit` 门禁通过（`logs/v3_strict.*`、`logs/v3_gate.json`）。其中 566 项为原有测试，37 项为本轮新增。
- 本地完整 CPU 套件（在 `db48181e` 上启动；此后的提交只改了脚本和 1 条 ME 核查规则，后者已由 V3 严格套件覆盖）：**2,435 passed，2 skipped，11 个 GPU 用例 deselected**，耗时 560 s。2 个 skip 都是环境原因：本机没有冻结的 Llama tokenizer 文件，PATH 上没有 rg。原始文件为 `logs/full_cpu.log` / `.xml`。PR CI 以 Actions 结果为准。
- 各步骤输出的 code_sha：asof、env、latency 为 `db48181e`；visibility、reward 为 `32eb4b9c`；p2 为 `cdca8c31`。中途作废或预跑的日志以 `superseded_*`、`prerun_*`、`failed_*` 为前缀原样保留。
- 每一步都有 `manifest.json`，记录输入、输出、代码的 SHA 和 code_sha。
- 原始日志：`logs/*.log`，其中包括预跑和已作废的运行，原样保留。

## 11. 风险与下一阶段需要的授权

**风险**
- bank-v0 的 MP 池在 84% 的前缀上不满足时间一致性。旧的 120 个工程终点（以及 MP 相关的结论）不能升级为 as-of 研究终点。
- A 的 sidecar 中 MP/ME/SUM 全部 quarantine：时间一致的 MP/ME 视图几乎为空，P2 能真正使用的资源输入目前只有 MS-RAW。
- J1 遇到一整句长回复时容量会爆炸；同一个 Qwen3.5-9B 同时担任 writer 和 J1，存在共同盲点。
- 18 个 owner 都是已曝光的开发材料。

**需要研究者明确决定或授权**

| # | 事项 | 内容 |
|---|---|---|
| 1 | integration owner 合入 PR #10 | 解除 G0e BLOCKED |
| 2 | NeedCard pilot v2 | 计划 `b1d3225b…`：≤ 20 次首次调用、0 次重问 |
| 3 | J1 decode 上限 | 8,192 或 16,384，并冻结新的 JudgeIdentity |
| 4 | P2 生成范围 | 只授权 tier-1，还是 tier-1 + tier-2，需在看到结果前决定 |
| 5 | S7 补充集选样规则 | 第 4 节的 rank-0 规则 |
| 6 | EXP-RS 材料 | 低风险 METHOD 卡及其许可，由 A 提供 |
| 7 | 人工审阅人力 | 76 对 × 2 人，加上任务 F |
| 8 | A6000 延迟测量 | 第 9 节的测量计划 |
| 9 | C0 迁移提案（TerminalKey 增加 asof_binding_sha256） | 跨线评审 |
