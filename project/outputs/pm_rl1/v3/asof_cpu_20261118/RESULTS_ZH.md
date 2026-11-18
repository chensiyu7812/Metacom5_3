# WS-A V3.2 P0–P2 CPU 交付

独立分支 `pmrl1-v3/ws-a-asof-cpu-20261118`，integration base `320a33d1d871199d171f998300ce926b341ca1a8`。研究者授权 CPU 推进；H0/EXECUTION_STATE 的正式采纳仍由 integration owner 处理。完整说明见 [中文报告](../../../../docs/PM_RL1_ASOF_CPU_P0_P2_20261118_ZH.md)。

**已实现**：append-only 账本、三时间/事实有效期、合法 frontier、版本化快照及固定 SHA 加载、延迟更正/冲突隔离、MS 父文与显式 RAW fallback、METHOD/CASE 分离和四臂输入、新同证据 renderer 请求提案。C0、旧 bank、旧 Notes/TerminalKey、A0 计划、100 OFF 原生 token IDs、全局状态和 main 不变。未合并任何 PR。

**实际重放**：p1/p15/p18 的68会话、65真实切点、93账本记录；批量/流式/未来追加/持久重启/重复幂等通过。独立干净重跑的整个 manifest 与所有输出字节相同。旧324条隔离MP全部复现更晚替代的 latest 风险，未恢复入库。最终产物仅使用 [cpu_v3/MANIFEST.json](cpu_v3/MANIFEST.json)；v1失败日志、v2中间版本漂移记录保留，不计最终通过。

| 固定集合 | ELIGIBLE | BLOCKED | LEGACY_DIAGNOSTIC |
|---|---:|---:|---:|
| 83 开发样本 | 20 | 23 | 40 |
| 54 原提案 | 16 | 14 | 24 |

全部3,188旧资源、1,876独特候选、18,578候选出现及120旧请求可回查；54未换样。ELIGIBLE只表示机械输入资格；worth_reading/相关但无须提及仍为null，不能推导收益。

**B独立复核**：[最终收据](b_review/FINAL_RECEIPT.json)，100项测试通过；独立RAW oracle与65快照相同，另独立核验54/83/120/324保全。AI工程复核不冒充人工语义批准或原WS-B owner采纳。[接口候选](INTERFACE_FREEZE_CANDIDATE.json)仅私有sidecar，没有C0公共Schema修改。B报告保留初次缺陷与修复，32份Schema及integration/outcome-lock检查通过。

**CPU验证**：最终V3为580 passed/0 skip；本地完整CPU为2411 passed/1历史tokenizer缺失skip/11 GPU deselected，561.44秒。完整套件收集早于B最后新增两项，新增项包含在最终580项V3复跑中；[本地收据](LOCAL_CPU_RECEIPT.json)明确记录此边界。原始日志/JUnit位于 [validation](validation/) 与 [b_review](b_review/)。最初本地全量收集缺jsonschema，已用项目既有隔离vendor目录恢复；失败记录未覆盖。最终HEAD完整CPU CI的计数、skip理由及原始日志以本PR Actions与交付收据为准，不能拿专项通过替代完整CI。

**待审与阻塞**：研究者明确保持五项人工待审，[审查包](human_review/HUMAN_REVIEW_PACKET_ZH.md)含完整原话、前后文、完整会话RAW、speaker/owner/session/rank及来源SHA；②省略已补全。真实ledger人工批准数为0，14个语义候选均隔离，11个SUM示例均unusable。模型抽取/摘要、RS日常适用与许可例外/CASE关联、原生新请求分词与容量、A0/G0/Judge、人评与增量资源质量、正式owner接口采纳仍pending。

GPU/模型生成/Judge/研究训练/付费调用均为0。完整CPU suite中的确定性算法/优化器单测不是研究训练交付。未宣布A4、A5、A6、A7或资源收益完成。
