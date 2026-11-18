# 首轮真实生成与人评准入报告（WS-B，供研究者核准）

本轮只做 CPU 工作。执行次数：Generator 0、GPU 0、NeedCard writer 0、J1/J2 0、训练 0、付费 API 0。所有协议均为候选（PROPOSED_NOT_ADOPTED）；冻结的 P2 v1 和 #16、#17 的产物都没有改动。

## 0. 结论

**目前还不能开始任何真实生成或人评。** 离第一步最近的是 PP1，即 16 次 OFF / RET-MS 生成加双盲程序试点。16 个请求包已在 WS-A Draft PR #19 的 HEAD 上通过 B 的独立检查；PP1 还差以下 4 件事，没有一件需要扩充工程框架：

| # | 缺什么 | 由谁解除 |
|---|---|---|
| 1 | G0e 身份固定：PR #10 合入，或研究者书面固定 g_id、renderer、step2、decode；另需 A0 实测 | integration owner / 研究者；WS-A 执行 A0 |
| 2 | 研究者批准 PP1 协议，并单独授权绑定最终 SHA 的这 16 次调用 | 研究者 |
| 3 | 1 名筛查整理者和 2 名审阅者（整理者不兼任审阅者） | 研究者 |
| 4 | 评审工具：盲化、位置哈希、锁定时间戳、导出 | WS-B（可在授权前完成） |

**首轮正式 MS 比较**（FC-MS：OFF / DP-MS / RET-MS，按 S1/S2/S0/S7 分层）在 PP1 的基础上还需要：

- 正式协议获批，包括是否采用 margin；
- 90 条初筛（必要时按规则扩展）的标签；
- 正式样本的 DP-MS 导出、as-of 的 RET-MS；
- FC-MS 统一使用哪一个 renderer、是否保留 html.escape；
- EvoEmo 许可范围；
- 人力。

**FC-MS 不需要等待** MP/ME 语义审核、RS METHOD 卡或 J1。

## 1. 已满足的条件

| 条件 | 证据 |
|---|---|
| PR #18 的 8 个前缀通过 B 的独立机械核验：双 horizon、snapshot SHA、RAW 来源、owner/family 隔离、Generator 可见投影 | `pr18_receipt/WSB_RECEIPT_PR18_ZH.md`：<br>• 8/8 前缀；<br>• 16/16 快照；<br>• X5a 首次可测并通过；<br>• 63/63 预览；<br>• 63/63 重分词；<br>• 0 未来文本，0 跨 owner |
| PP1 的 16 个请求在 Draft PR #19 HEAD `4ac9ab3d` 上通过 B 检查 | `pp1_requests/`：<br>• 16/16 通过，16/16 重分词；<br>• OFF 与 RET-MS 共用同一 renderer；<br>• RET-MS 都是同一 owner 严格更早的完整会话 |
| PP1 的 QH 背景已在生成前构建：完整 as-of RAW，与资源臂无关 | `pp1/QH_BACKGROUNDS.json`：8 份，与 #18 `QH_SOURCE_HANDOFF` 的合法 RAW 集合一致 |
| Q0/QH/F v2：需要标签封存在审计侧；所有审阅者都看不到条件和任何模型或旧人工分数；F-A 移到审计侧 | `docs/PM_RL1_V321_PROTOCOL_REVISION_CANDIDATE_ZH.md` §3 |
| 门禁按用途拆分；FC-MS 不依赖 RS/MP/ME；PP1 不再成为所有生成的前置条件 | `gates/GATES_V321.json` |
| 17 组下的精度、可达非劣界和严重错误率上界已重新核算 | `stats/STATS_V321.json` |
| 90 条初筛：可重现，SHA 与抽样概率已登记；扩展规则只依赖标签 | `screen/INITIAL_SCREEN_90.json`（`31daca4e…`） |
| PP1 独立协议：流程、分歧处理、计时、停止条件（工程部分采用 #19 更严的运行规程）、与正式分析分离 | `pp1/PP1_PROTOCOL_ZH.md`（`b23b91eb…`） |
| 旧 54 保留，曝光只登记不排除；8 个 ELIGIBLE 输入 = 8 OFF + 8 RET-MS | 沿用 #17 |

## 2. 等待人力或权限的事项

1. **研究者决定**：
   - 是否采用 V1–V8 和新的 Gate 结构；
   - 主通道 QH、保护通道 Q0、约束 F，以及是否采用 margin；
   - html.escape 的处理（N1）和 FC-MS 统一使用的 renderer（N2）；
   - 许可范围；
   - PP1 是否作为正式人评的前置条件，还是允许书面豁免。
2. **研究者授权**：PP1 的 16 次 G0e 调用。在此之前还需要 A0 实测的授权。
3. **人员**：
   - 1 名筛查整理者：PP1 需要 1.5–2.8 小时；正式 90 条初筛需要 16–29 小时；
   - 2 名审阅者：PP1 每人 2.7–4.1 小时；
   - 1 名裁决者或审计人员。
4. **人工语义审核**：64 条 MP/ME 候选（只有做 FC-MP / FC-ME 时才需要）；METHOD/CASE 的许可与适用性（只有做 FC-RS 时才需要）。

## 3. 等待工程的事项

| 事项 | 负责 | 阻塞 |
|---|---|---|
| PR #10 合入，或书面固定 G0e 身份 | integration owner / 研究者 | G-ENG |
| A0 实测：加载前重算权重 hash，确定性重复调用 | WS-A（需授权） | G-ENG |
| 评审工具 | WS-B | PP1 P6 |
| 按正式样本导出 DP-MS（同一规则、同一 renderer），冻结 as-of RET-MS | WS-A；WS-B 核验 | FC-MS M2/M3/C6 |
| 修复 #16 的 R1–R5，并由 A/B 签收 | WS-B；WS-A 签收 | 只阻塞 G-RWD |

## 4. 一次 PP1 的最大成本

| 项 | 预计 | 上界 |
|---|---|---|
| Generator 调用 | 16 | 16（不重试） |
| GPU 时间 | 约 11 分钟（#19 规划 8–20 分钟，均未实测） | 20 分钟（#19 的全阶段硬上限 1,200 s） |
| Judge / writer / 付费 API | 0 | 0 |
| 人工合计 | 约 7.4 小时（背景用检索式略读） | 11.5 小时（按 250 词/分通读 36,340 词的背景）；再乘 1.5 倍裕量，约 17.2 小时 |

明细见 `pp1/PP1_PROTOCOL_ZH.md` §7 和 `admission/ADMISSION_NUMBERS.json`。

## 5. 首轮正式 MS 比较的规模与成本（规划数）

- **设计**：17 组，每组 m 个前缀；3 个臂，每个前缀做全部 3 对比较；两名审阅者做 Q0 + QH，一人做 F。
- **阅读量**：每人每个前缀通读一次背景，取筛查集中有历史前缀的中位数 4,102 词（上界）。

| m（前缀数） | 生成调用 | 每名审阅者 | F 负责人 | 人工合计 | QH 对 OFF 的 MDE（ICC 0.1） |
|---|---:|---:|---:|---:|---:|
| 2（34） | 102 | 18.1 小时 | 17.3 小时 | 53.5 小时 | 0.38 |
| 3（51） | 153 | 27.2 小时 | 25.9 小时 | 80.2 小时 | 0.32 |
| 4（68） | 204 | 36.2 小时 | 34.5 小时 | 107 小时 | 0.29 |

- **筛查**：90 条初筛通读约 29 小时（检索式约 16 小时）；扩展到 162 条约 50 小时。
- **读法**：在 m = 2 时，只有约 0.38 以上的净偏好差异能以 80% 的把握检出。−0.10 的非劣界在 ICC ≥ 0.04 时不可达。不显著只能报告为 inconclusive，不能写成“无效”或“非劣”。
- **成本大头**：主要是通读历史。研究者可以在正式协议冻结前决定是否允许检索式阅读，但需要先在 PP1 中测量它对 QH 一致性的影响。

## 6. 本轮交付对照

| 指令 | 交付 |
|---|---|
| 1 独立复核 PR #18 并出具回执 | `pr18_receipt/`：机械 PASS_WITH_NOTES，N1–N5；语义轴不签收；研究资格轴尚未合格；R1–R5 处置；另有 #19 的 16 个 PP1 请求回执（`pp1_requests/`） |
| 2 重构门禁 | `gates/GATES_V321.json`；文档 §2 |
| 3 修改 Q0/QH/F | 文档 §3；`protocol/PROTOCOL_V321_CANDIDATE.json` 中的 `review` 与 `audit_ledger` |
| 4 统计方案 | `stats/STATS_V321.json`；文档 §4 |
| 5 样本筛查 | `screen/INITIAL_SCREEN_90.json`；文档 §5 |
| 6 PP1 独立协议 | `pp1/` |
| 7 测试问题核查 | `testsdiff/`，见本报告 §7 |
| 8 准入报告 | 本文件 |

## 7. 测试核查

见 `testsdiff/ALLTESTS_DIFF_ZH.md`。在相同环境、相同命令下，base `a9cf0cca` 与 #17 HEAD `3dafb2aa` 的 99 个失败逐测试 ID 完全相同：只在一边失败的为 0，状态变化 0；HEAD 多出的 30 个测试全部通过。这 99 个都是旧 `test_v1_5_*`、posthoc 等文件，不在 CI 范围内，81 个是缺少未入库的旧数据。#17 最终 HEAD 的 CI（run 44323588907）：V3 633 passed，公共 2,398 passed。#20 最终 HEAD 的 CI 写在 PR 描述中。
