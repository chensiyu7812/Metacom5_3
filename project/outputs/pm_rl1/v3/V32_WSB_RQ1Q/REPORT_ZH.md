# WS-B V3.2 资源增量价值的科研评价资格：本轮报告（CPU，2026-11-18）

- 分支：`pmrl1-v3/ws-b-v32-rq1-qual`。基于 PR #16 的 head `a9cf0cca`（叠在 #16 上）；#16、#11 的冻结交付都没有改动。
- 主文：[`docs/PM_RL1_V32_RESOURCE_EFFECT_QUALIFICATION_ADDENDUM_ZH.md`](../../../../docs/PM_RL1_V32_RESOURCE_EFFECT_QUALIFICATION_ADDENDUM_ZH.md)，状态为候选（PROPOSED_NOT_ADOPTED）。
- 表单：[`REVIEW_FORM_ZH.md`](REVIEW_FORM_ZH.md)。
- 候选协议 sha：`b28cf37b…`。冻结的 P2 v1（`2b6057c8…`）每次运行都重新核对，结果为未改变。
- 本轮**没有**做以下任何一项：Generator、GPU、NeedCard writer、J1/J2、训练、付费 API；修改 P2_PROTOCOL_FROZEN.json、旧 terminal 或 reward；修改 H0、EXECUTION_STATE 或 C0；合并任何 PR。
- 研究者 2026-11-18 的补充决定已经纳入：曝光只登记，不作为排除条件；控制手段是结果锁定；Q0/QH/F 作为版本化的候选，待跨线审阅和研究者确认。

## 0. 结论

**当前不具备运行第一轮有科学解释力的资源质量比较的条件。** Gate 1 = BLOCKED，Gate 2 = BLOCKED。最少的阻塞项有 5 项（第 9 节），都不是靠继续扩展工程框架能解决的：

1. G0 研究身份未成立：PR #10 未合入，A0 没有实测加载和解码。
2. 没有任何一个头有 Direct Provision 材料，也没有 RS METHOD 卡。
3. 生成前筛查标签和 QH 背景包为 0（需要人工）。
4. 研究者尚未批准评价协议候选（主指标、阈值、背景包规则、分层、样本量规则、Gate 定义）。
5. 两名审阅者尚未安排，程序试点未做。

建议第一轮比较的范围：**只做 MS**，即 OFF、DP-MS、RET-MS 在 S1/S2/S0/S7 分层上的比较。MS-RAW 是目前唯一有合法 as-of 内容的头，也是唯一能把"内容价值"和"检索损失"分开的头。MP/ME 要等 A 的 as-of typed view 解除 quarantine，RS 要等 METHOD 卡。

## 1. PR 与集成状态（本轮查询）

| PR | head | 状态 |
|---|---|---|
| integration | `320a33d1` | 未变 |
| #10 WS-A G0e | `73fdb12f` | **OPEN，未合入** |
| #11 WS-B S3 | `dd33e131` | Draft，不动 |
| #14 V3.2 候选 | `f26e7cf8` | Draft |
| #15 WS-A as-of CPU | `b63635f3` | OPEN；仍然只覆盖 3 个 owner（p1/p15/p18）；**没有新的 8-owner 证据** |
| #16 WS-B V3.2 P0–P2 | `a9cf0cca` | Draft，不动 |

## 2. 本轮交付与对应文件

| # | 交付 | 文件 |
|---|---|---|
| 1 | V3.2 补充提案（修订差异表 D1–D9 及依据） | 主文第 1 节 |
| 2 | Q0/QH/F 人评规范和中文盲评表单结构 | 主文第 5 节；`REVIEW_FORM_ZH.md`；`protocol/PROTOCOL_CANDIDATE.json` |
| 3 | 主要指标、统计方法与样本独立性方案 | 主文第 2、4、7 节；`stats/STATS_PLAN.json` |
| 4 | 旧 54 与补充集的身份边界 | `samples/SAMPLE_BOUNDARY.json`；本报告第 3 节 |
| 5 | S1–S7 覆盖矩阵和缺口 | `coverage/COVERAGE.json`、`coverage/SCREENING_DRAW.json`；本报告第 4 节 |
| 6 | E1 Direct Provision 比较协议和可执行性矩阵 | 主文第 8 节；`gates/E1_EXECUTABILITY.json`；本报告第 6 节 |
| 7 | A/B 联合资格与独立验收记录 | 本报告第 7 节 |
| 8 | Gate 1–2 清单 | `gates/GATES.json`；本报告第 9 节 |
| 9 | 下一轮最小有界 G0e 生成申请 | 本报告第 8 节：条件未满足，**只是草案，不提交** |

## 3. 旧 54 与补充集（重新读取 `p2/ELIGIBILITY_54.json`）

- 54 个输入的身份 `identity_sha256 = c0efa65c…`，未更换。
- 联合资格：ELIGIBLE 16、LEGACY_DIAGNOSTIC 24、BLOCKED 14，与第 9 轮一致。
- **真正通过资格的输入只有 OFF 8 个和 MS 8 个**（`eligible_is_8_off_8_ms = true`）。
- MS 的这 8 个输入是 bank-v0 lexical-v0 Top-1 的整段会话 RAW，因此属于"实际检索臂"（RET-MS），**不是 Direct Provision**。
- ab3d17 的 MP 和 MP+MS 两项仍为 BLOCKED，不纳入 54。
- 补充集使用另一个命名空间，身份由筛查抽样 `draw_sha256 = 857ed7d3…` 和纳入规则决定，排除了 B6e 的 8 个前缀。
- 人工构造的挑战集（如获批准）使用第三个命名空间。

## 4. S0–S7 覆盖矩阵与缺口

自然帧共 4,321 个合法切点：B0 的 4,119 个 rank≥1 切点，加上 202 个 rank-0 切点，涉及 18 个 owner。计算只用可见前缀、严格过去的 RAW 和 source rank 小于 cutoff 的编译单元，**不涉及任何回复或评分**。

下表是机械候选数，不是标签：

| 候选 | 前缀数 | 有候选的 owner | 每个 owner 最少 | 判定方式 |
|---|---:|---:|---:|---|
| S7 rank-0（无个人历史） | 202 | 18 | 4 | 机械可定 |
| 显式回指/时间线索（只用于富集 S1 候选） | 453 | 18 | 13 | 不是 S1 标签 |
| S3 切点前 slot 已改值 | 2,156 | 16 | 0（p11、p15） | 结构候选，需人工确认 |
| S3 ≥5 个会话前的 ongoing 事件 | 3,210 | 18 | 76 | 弱，几乎普遍 |
| S4 过去有支持者建议 | 4,046 | 18 | 111 | 不具区分度 |
| S5 建议后紧随拒绝/失败 | 1,805 | **10** | **0**（p1、p8、p10、p13、p14、p16、p17、p18） | 词面候选，需人工确认 |
| S6 过去提到第三人 | 4,007 | 18 | 131 | 不具区分度；RS 案例恒为候选 |

逐 owner 的数字见 `coverage/COVERAGE.json` 的 `matrix.*.per_owner`。

缺口（已写入 COVERAGE.json 的 `gaps`）：

- **S1 / S2 / S0**：没有生成前的人工筛查，就没有任何自然样本的计数。旧的已曝光证据（2026-11-05）是：96 个前缀中只有 10 个有具体信息缺口，说明严格意义上的 S1 很可能稀少。
- **S2**：没有机械代理，只能靠筛查区分"相关但可选"和"无关"。
- **S4 / S6**：线索几乎普遍，不能用于选样；需要人工筛查，或另立挑战集。
- **S5**：在 8 个 owner 上为 0，自然覆盖不均；bank-v0 的 ME stage 是 unknown，A 的账本里也还没有 rejected 阶段。
- **S7**：自然样本有 202 个，但旧 54 中为 0。

筛查抽样已在任何生成之前冻结：

- 每个 owner：线索层 4 个，其余有历史层 4 个，rank-0 层 1 个。
- 合计 162 个前缀（72 + 72 + 18），记录了包含概率。
- 标签数为 0。
- 纳入规则：每个 owner 纳入 S1 2 个、S2 1 个、S0 1 个、S7 1 个。

## 5. 曝光登记与数据独立性（`samples/EXPOSURE_REGISTRY_V2.json`）

- 规则：只登记，不自动排除。四类曝光是 inspection、design、outcome_other_contrast、outcome_same_contrast。
- 18 个 owner 全部属于 outcome_other_contrast（旧探针、人评、判官目录）。
- 设计阶段使用过的 owner：B6e 的 8 个 owner，以及 NeedCard 试点计划涉及的 owner（尚未调用 writer）。
- 54 个输入所在的 8 个前缀：outcome_same_contrast = 0。
- fa14cf 所在会话（p16_conv_4）在旧人评中出现过，已标记为敏感性分析对象。
- 自动排除：0。
- 统计聚类单位：17 个 owner 组（p13 与 p18 共享 esconv_1198，合为一组）。
- 证据等级：
  - 预注册比较 = 关于 EvoEmo 18 owner 分布的研究结论；
  - 看过对应结果后的分析 = exploratory；
  - 不主张对新用户的泛化。需要这类主张时，再另行安排独立验证，它不是当前的门槛。

## 6. E1 可执行性矩阵（`gates/E1_EXECUTABILITY.json`）

7 个实验族**目前全部不可执行**。每一族都受以下共同阻塞：G0 身份、审阅者、协议批准、QH 背景包。各族另有的阻塞：

| 族 | 唯一变化的因素 | 另外的阻塞 |
|---|---|---|
| E1-DP 记忆（OFF / DP-MP / DP-ME / DP-MS） | 一个头的内容 | 筛查标签；三个头都没有 DP 材料 |
| E1-DP RS（R0 / F-resident / METHOD / METHOD+CASE） | RS 材料 | 没有经审核的 METHOD 卡和许可 |
| M1 DP vs 检索 | 选择机制 | 筛查标签；DP 材料；as-of 检索视图（需 A 的正式绑定） |
| M2 Notes vs 有边界阅读 | renderer | A 尚未交付有边界阅读的 renderer 身份 |
| M3 单头 vs 组合 | 加入第二个头 | 同一前缀上只有 MS 一个头合格 |
| M4 需要 vs 不需要读取 | 情境层 | 筛查标签 |
| M5 正确使用 vs 诱发误用 | 风险标签 | 筛查标签；自然风险项未确认，挑战集需另批 |

## 7. A/B 联合资格与独立验收记录

**状态：PENDING。A 尚未提供新的 8-owner as-of 证据**（PR #15 仍为 `b63635f3`，只有 p1/p15/p18）。B6e 的 8 个 owner 是 p2、p3、p5、p8、p11、p13、p15、p16，与 PR #15 只在 p15 上重合。

已有记录（第 9 轮，未变）：p1/p15/p18 的 65 个切点通过 B 的独立机械检查，65/65。X5a 无法从单一 horizon 的导出文件检验。

A 交付后，B 按以下 5 个轴分别给出结论。A 的工程通过**不等于**研究资格。

| 轴 | B 的独立动作 | 通过条件 |
|---|---|---|
| ① 快照身份 | 按 A 给出的 snapshot_sha 规范，用 B 自己的代码重算至少全部关键切点（8 个 B6e 前缀所在的切点） | 逐项相等 |
| ② 双 horizon 未来不变性（X5a） | 用 `V32_wsb_p0p2.py asof --a-exchange` 核对两个 horizon 的导出 | 追加未来会话后，早期快照、候选成员、排名输入和可读正文为 0 差异 |
| ③ owner/family、known/ready、读取边界 | X1–X4、X5b/c、X7，以及与 RAW oracle 的逐项核对 | 0 违规 |
| ④ 候选内容 = Generator 实际可见内容 | 对 G0e request_packet 做白名单扫描，并逐字比对候选正文 | 0 泄漏，0 不一致 |
| ⑤ 三个结论分开给出 | 语义审批（主体、阶段、是否过时，需人工）；证据合法性（as-of、span、家族闭包、许可）；研究资格（前两项加上冻结身份加上 G0） | 分别记录 PASS / BLOCKED / PENDING |

需要 A 提供：

1. 8 个 owner 的双 horizon 导出；
2. snapshot_sha 的计算规范；
3. 至少 1 条真实的更正链，或明确声明没有；
4. DP 材料及其来源、选择者和冻结 sha；
5. G0e 请求与候选内容的映射。

## 8. 下一轮最小有界 G0e 生成申请（草案，**条件未满足，不提交**）

### 8.1 程序试点 PP1

| 项目 | 内容 |
|---|---|
| 目的 | 只检验程序：表单是否可用、单件耗时、审阅者一致性、平局率和决定率。**不检验资源效应** |
| 输入 | 旧 54 中 16 个 ELIGIBLE 输入（8 OFF + 8 RET-MS），对应 8 个前缀、8 个 owner 组 |
| 请求数 | 16 次 G0e 调用 |
| 解码设置 | G0e 身份（PR #10）：greedy，`max_new_tokens = 320`，`timeout = 300 s`，不自动重试 |
| 设备 | 1 张 A6000，HF 回退路径（vLLM 未支持 Gemma4Unified 的证据保留）；不与 A 的 GPU 任务争用 |
| 预计耗时与费用 | 加载约 3–5 分钟，16 次请求共约 5 分钟；GPU 墙钟时间 < 20 分钟；费用 $0 |
| 人工 | 8 个前缀的筛查与背景包约 75 分钟；8 对 × 2 人 × (Q0 + QH) 约 72 分钟；16 份 F 约 64 分钟；合计约 3.5 小时 |
| 失败与停止条件 | 加载失败或 OOM → 停止，结果保持 pending。请求身份与登记表不一致 → 停止。G 载荷泄漏扫描不为 0 → 停止。`finish_reason = length` 记为 truncated、不重问，超过 2/16 即停止。不按内容重新生成。登记表之外的请求一律拒绝 |
| 结果的使用 | 单独报告。程序版本未改时，按预注册规则可以并入主分析；如果改了程序，就不并入 |
| ICC | 每个 owner 只有 1 个前缀，无法估计 ICC，样本量计算采用 ρ 的下限 0.1 和 0.3 做敏感性分析 |
| 前提条件 | PR #10 已合入；#11 的 G0e 附录已在真实 integration 上通过；A0 的 GPU 加载已获授权并完成实测；本补充已获批准；8 个前缀的筛查和背景包已冻结；研究者授权文件与计划 sha 绑定 |

### 8.2 第一轮正式比较 FC1（仅 MS，供规划，Gate 1 通过之后才可申请）

| 项目 | 内容 |
|---|---|
| 规模 | 最多 18 个 owner × (2 个 S1 + 1 个 S2 + 1 个 S0) = 72 个前缀；条件 OFF、DP-MS、RET-MS；另加 18 个 S7 的 OFF |
| G 调用 | ≤ 234 次（DP 与 RET 字节相同时共享请求） |
| 人工 | 筛查 162 个前缀约 22 小时（缩减版 90 个约 12 小时）；144 对 × 2 人 × 4.5 分钟约 22 小时；F 约 16 小时 |
| 精度 | 17 组、每组约 2 个 S1，d = 0.5、ρ = 0.1 时，95% 半宽 ≈ 0.25，MDE ≈ 0.36。只能检出较大的效应，这一点需要如实写明 |

## 9. Gate 1–2 清单（`gates/GATES.json`）

**Gate 1（运行第一轮有解释力的资源质量比较）：BLOCKED**

| 项 | 状态 | 依据 |
|---|---|---|
| G1.1 54 个输入身份不变；16/24/14；ELIGIBLE = 8 OFF + 8 MS | PASS | 重新读取 ELIGIBILITY_54 |
| G1.2 G0 研究身份 | **BLOCKED** | PR #10 OPEN；A0 未实测 |
| G1.3 B 接受 8 个 B6e owner 的 as-of 证据 | PENDING | PR #15 仍只有 3 个 owner（不在"只做 MS"首轮的关键路径上，但 MP/ME 之前必须通过） |
| G1.4 至少 1 个记忆头有 DP 材料，RS 有 METHOD 卡 | **BLOCKED** | MP/ME 全部 quarantine；没有 METHOD 卡；DP-MS 尚未选定 |
| G1.5 筛查标签和 QH 背景包 | PENDING | 抽样已冻结，标签为 0 |
| G1.6 研究者批准评价协议 | PENDING | 本补充为候选 |
| G1.7 两名审阅者到位并完成程序试点 | PENDING | 0 人 |
| G1.8 结果锁定登记 | PENDING | 只有模板 |

**Gate 2（奖励资格与 BC/PPO）：BLOCKED**

| 项 | 状态 | 依据 |
|---|---|---|
| G2.1 Gate 1 已通过，并有预注册人评结果 | **BLOCKED** | Gate 1 |
| G2.2 NeedCard 试点 v2 已运行并审核 | PENDING | 计划 `b1d3225b`；writer 调用 0 次；未授权 |
| G2.3 J1 decode 上限（8,192 / 16,384）及 JudgeIdentity | PENDING | 仍是候选 |
| G2.4 用人评检验 J1/ER（阈值先固定） | PENDING | 没有人评，也没有运行过 J1 |
| G2.5 奖励构成分离，pending 不填 0 | PASS | ER-v3 加 reward_qualification_v1（第 9 轮测试） |
| G2.6 延迟实测 | PENDING | 需授权 |
| G2.7 研究者授权 BC/PPO | PENDING | 未申请 |

**最少阻塞项**（解除后即可进入 PP1，再进入 FC1）：

| # | 阻塞项 | 负责方 |
|---|---|---|
| 1 | 合入 PR #10，并授权和完成 A0 实测 | integration owner 与研究者 |
| 2 | 用已冻结的规则选定 DP-MS 材料（可以使用现有的合法 RAW，代价最低） | WS-A 审阅者；MP/ME/RS 材料留到后续实验族 |
| 3 | 完成筛查和 QH 背景包 | 评价侧整理者 |
| 4 | 研究者批准本补充，并确定第 11 节的 6 项选择 | 研究者 |
| 5 | 安排 2 名审阅者，并完成 PP1 | 研究者 |

## 10. 测试、CI 与日志

- 新测试 `tests/test_rl1v3_v32_rq1_qual.py`：30 项。覆盖冻结的 v1 未改变、54 个输入的资格、Q0/QH/F 的隔离、QH 背景包不使用并集、配对与聚类规则、uncertain 只进上下界、精确符号翻转、Holm、精度、抽样的确定性以及与回复无关、曝光不排除、可执行性、Gate。
- 测试数量和 CI 结果以 PR 页面为准。本地结果见 `logs/v3_strict.*` 和 `logs/full_cpu.*`。
- 第一次运行（代码 `54727b35`）因为 manifest 根路径错误而失败，产物已删除，日志原样保留为 `logs/failed_54727b35_*.log`。修复后（`6c8d2ebd`）5 个步骤全部通过，日志为 `logs/<step>.log` 和 `logs/<step>.start`。
- 每个步骤都有 `manifest.json`，记录输入、输出和代码的 SHA。
