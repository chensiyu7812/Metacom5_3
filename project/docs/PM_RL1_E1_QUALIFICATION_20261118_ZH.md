# WS-A：资源质量资格与 B6e as-of 对齐（Draft）

本轮结论是：**8 个实际评测前缀已具备可重算的时间一致 RAW、SourceFrontier 和读取绑定；尚没有一类外部资源完成“来源许可、语义、当前适用性、Generator 正确使用、支持增量”的全链资格。** 不据此宣布 E1 收益、research-qualified、A4–A7 或 bank-v1 完成。

角色分开记录：只读 integration coordinator 的报告及 GitHub CI 复核在本交付 `coordinator/`；其利益冲突已明示，不代替 WS-B 对 A 的独立确认。本文是 WS-A 资源/Generator 工程交付。分支基于 PR #15 `b63635f3`，作为新 Draft 子 PR，保留父分支和全部候选 PR。无合并权限；H0、EXECUTION_STATE、main 和冻结产物没有修改。

## 研究者本轮澄清的优先规则

Q0/QH/F 是研究讨论中的**未采用修订建议**，由 WS-B 提版本化方案，经跨线和研究者确认后冻结。A 不实现评价器、不改 #16 的冻结协议。

- Q0 只看合法当前前缀及匿名随机排列的回复，关注当前支持质量。
- QH 看相同前缀、回复及从合法 as-of RAW **独立构建**的固定背景；同一前缀跨所有条件完全相同，不能由资源臂实际召回内容决定。
- F 依据合法来源检查主体、阶段、时序、过期、虚构、重复拒绝/失败建议、不必要引用、建议适当性和安全。

`QH_SOURCE_HANDOFF.json` 交付每个前缀的**全部合法 RAW ID**，而不是本轮选中的 MS 或各臂资料并集。它是供 B 独立构建背景的来源清单，不是已冻结 QH 背景/评分器。B 的旧 Q/F 协议及其 76 对保持原样，待 B 修订；不能把旧协议当本轮 Q0/QH/F 已采用。

历史查看不自动取消正式评价资格。记录选样、此前调参和结果使用情况；原 54 提案保留，可在资格合格、协议事前固定后使用。额外独立确认数据由主张、精度与泛化需求决定，不作为所有实验的硬前置。禁止依据待报告正式测试结果改主要假设、指标、选样或反复调参。本轮没有读生成结果来选材料；8 前缀取 B 的固定 `SELECTION.json`，不因缺头换题。

## P1 交付

入口：`project/outputs/pm_rl1/v3/qualification_e1_20261118/cpu_v3/`。

- `BINDINGS.jsonl`：逐条 prefix / owner / session / cut_turn / cutoff / 时间 / snapshot / frontier / ReadingView；`BINDINGS_ZH.md` 是可读表。
- 8 对双 horizon、16 个快照，历史 RAW 共 87 会话。past writer 只消费 cutoff 前已完成会话；future writer 顺序消费该 owner 的后续会话，然后再次读取同一 cutoff。双方完整快照相等，全部 RAW membership 与原文、MP/ME 的不可读状态也相等。
- `ledgers/` 保留两个 writer horizon 的输入结果；`snapshots/`、`frontiers/`、`prefixes/` 和 `readings/` 可独立核对。个人 rank 只在 owner 内比较；相同 family 不允许跨 owner 读取。
- SHA 规范在 `SNAPSHOT_HASH_SPEC_ZH.md`；独立标准库检查器不导入 A/B 包。其通过是 A 的参考检查，不冒充 B 签收。
- 原 65 快照及其 manifests、旧 bank-v0、324 隔离 MP、83/54/120、100 OFF token IDs 和五项待审材料均保留；具体字节比对见 `PRESERVATION.json`。

来源与当时可构建分开：RAW 的 owner、完成/known/ready/cutoff、跨度与局部 source hash 可机械验证；known/ready 是逻辑会话完成边界，并非历史真实部署或异步 Writer 延迟实测。EvoEmo 的现有条款仍为既有研究授权复用、上游许可 unresolved，不能由公开可访问推定完整研究/部署许可。

## P2 语义材料及缺口

候选规则固定为：按 owner 内会话 rank、turn 顺序，对每个公开列出的 MP/ME 词面审阅层取首次出现；后续会话不能替代较早候选。规则只筛选**审阅线索**，不从 suggested/attempted 等词汇直接推出阶段、主体或客观事实。实际 ledger 的语义行仍 `subject=unknown`、`stage=unknown`、review pending，并全部 quarantine。

`SEMANTIC_REVIEW_DISPOSITIONS.jsonl` 对 64 条逐项给出原文、来源、known_at、未知有效时间、AI 预审假设及理由：**approved 0、pending 43、quarantined 21**。43 条可进一步人工核查，21 条不适合当前词面层或包含明显多主体/阶段歧义；64 条都没有人工批准、都不能从正式 Reader 读出。AI 预审不是人工真值。

具体风险包括：p15 的“他走出来了”是朋友经历，不能当用户画像；p13 的两只自己的狗与两只男友的狗必须拆主体；p16 独居与家人住外州是两个自报命题；p5 怕丢工作不等于已失业；p11 近期争吵不是稳定 slot。ME 中 `if it helps` 不是 outcome，`I will` 不是执行，`They sent` 不是用户完成，`won't let my team down` 不是拒绝建议。原五项 RAW 人工标注仍 `pending_human_review`，没有审批迁移。

MS：8 份完整 RAW 有单独读取身份和父文。8 份单句摘录仅作 SUM 审查候选，因覆盖不足均 **unusable**；没有 MS-SUM payload/token IDs。RAW direct 使用独立条件，未把回退算摘要成功。未来可比较原始上下文、逐命题 SUM 和父文回查，但本轮没有通过摘要审核，也不改有限头动作。

RS：仅两张 METHOD 候选，分别为可选邀请展开和暂定式复述，具有来源、许可范围、适用/不适用、动作及误用边界；CASE 独立存储，标明其他人对话。方法依据为 [SAMHSA TIP 35 第 3 章](https://library.samhsa.gov/sites/default/files/tip-35-pep19-02-01-003.pdf)，公开许可声明含第三方版权例外；正文直连访问挑战和索引核对范围如实登记。卡片许可例外、迁移到当前支持场景的适用性、CASE 方法关联均 pending。CASE 只从合法 ESConv train、排除 family 后按 source-local hash 取第一条，不称匹配成功或有效示范。没有新 RAG bank；策略标签不作方法有效性证据。

## 真实更正、否定与阶段变化

`RAW_CHAIN_COVERAGE.json` 从 401 份真实来源会话独立做覆盖审计。固定表达规则命中 851 条否定/拒绝线索、50 条尝试伴随不利后续线索、75 条阶段更新线索，显式 correction 规则命中 0。计数是话语线索出现次数，不是验证过的链；规则可能漏掉隐含/跨会话更正，不能据此断言语料不存在更正。

人工可复查的开发例包含 p1 从“治疗师建议爱好/开始画画”到后续“有帮助但短暂”，以及 p2 尝试写作后仍写不出来。它们只支持“真实 RAW 含相应报告”，所有阶段及关系仍待人工审阅。没有经批准的、更正目标明确且具有回溯有效时间的真实 invalidation 链，不能宣称真实数据已验证该机制。

`SYNTHETIC_MECHANISM.json` 使用完全独立手写来源：姐姐的居住更新在 r5 known、r7 ready，事实在 r2 改变；r4/r6 不提前改变，r7 才 supersede。另有意向未执行、尝试无帮助、完成/自报结果、拒绝、未知、跨 owner 同 family。该文件处处标明 synthetic，真实数据/人工批准计数为零，不进入 E1 或补足缺头。

## E1 Direct Provision 与五轴资格

每个前缀列 9 条：OFF、MP-direct、ME-direct、MS-RAW-direct、MS-SUM-direct、RS-R0、F-resident、METHOD、METHOD+CASE，共 72 条**提案位置**。其中 p3 MP 无候选，8 个 SUM 无合格摘要，共 9 条 unavailable；其余 63 条有 CPU 原生分词预览。缺项不改成 OFF、不补零、不换问题。

相同前缀使用相同 G0e HF 工程基线、固定系统提示、greedy/seed=0/max_new_tokens=320、no-plan Step-2、新统一 renderer。OFF 与 RS-R0 内容相同、实验族身份不同；F-resident 明确计入常驻文本；METHOD+CASE 保留完全相同 METHOD 文本再增加 CASE。当前 METHOD 固定第一张仅供审阅，不能替代 B 在生成前独立进行适用性选择。

Direct Provision 的 `query_id=direct_provision`，没有 lexical-v0/BM25/dense 召回排序。将来实际检索必须另立实验/索引/请求身份。新 native ID 绑定 proposal、实际 token IDs hash、冻结 tokenizer 身份和分词库版本；没有迁移旧请求 token IDs、结果、reward 或 TerminalKey。

五轴分别记录：来源时点与 owner/跨度；当时 Writer 可构建；语义审核；当前请求适用；G 正确使用。来源许可另列。前两项机械通过，不能给后三项填 true。MP/ME 只有审阅预览，绕不过 quarantine；MS-RAW 完整传递不等于适用；G 未生成，所以正确使用及增量支持质量均 unknown。所有 runtime_callable 与 research_qualified 均 false。

原生容量见 `TOKEN_CAPACITY_ZH.md`：全部 63 份预览在 HF 16,384 的上下文预算内，额外保留 320 输出 token。未加载权重、未初始化 GPU、未调用 Generator/Judge/训练/付费 API；不以分词时间代替生成吞吐或用户延迟。

## 下一步和停止边界

- B 独立复算：8 个前缀 join、双 horizon、snapshot hash、来源时间/owner、实际模型可见投影；B 收据前保持 pending，不以 A 运行检查器替代 B 批准。
- B 处理只读集成审查 R1–R5，特别是会话局部 source 身份、入口完整验证、STOP、缓存和 RELATION 交换；A 不代改 B 所有模块。
- 人工核查 43 待审候选及有明确新证据的隔离项；审核 SUM、METHOD/CASE 的许可和适用；原五项仍待研究者实际批准。
- B 提 Q0/QH/F 版本化协议，固定与资源臂独立的 QH 背景及评分；是否需要额外确认数据按主张/精度决定。
- 如需补充真实更正链：先登记许可、原始逐轮来源、人物/时间/明确修订目标和采样规则；在任何结果前另建身份。若现有 RAW 不足，缩小该头主张或另行采集授权数据；不能用 synthetic、解封旧 324 MP 或换题补齐。
- 模型运行、Judge、研究训练及任何 PR 合并仍未获本轮授权。

复跑命令、日志、完整 CPU/CI 计数、失败与跳过原因及 SHA 见同目录 `VALIDATION_ZH.md` 和 `VALIDATION_RECEIPT.json`。本文不改变旧研究方案或全局状态。
