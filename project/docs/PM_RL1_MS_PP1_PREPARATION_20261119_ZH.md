# WS-A：MS-RAW 第一轮材料与 PP1 执行准备差异报告

日期：2026-11-19（日本时间）。基于 #18 `0a91ff3329dc0d091fbb9e234035638efb45146c`；读取 B #17 当前 `3dafb2aa6e861846aa77a96d99a02c66e4fade7d`。两者均未合并，#17 仍是 PROPOSED_NOT_ADOPTED。没有变更 H0、EXECUTION_STATE、main、C0 或历史冻结证据。

**本轮已准备可审计的 16 条 OFF/RET-MS 原输入和 8 个 pending DP-MS 位置；B 独立回执尚未收到，PP1 执行条件尚未满足。** 本轮没有生成回复，因此不报告资源质量提升。四头全部完善不再是 MS-RAW 的前置条件。

完整目录：[`../outputs/pm_rl1/v3/ms_pp1_prepare_20261119/`](../outputs/pm_rl1/v3/ms_pp1_prepare_20261119/README.md)。

## 与 #18、#17 的差异

| 范围 | 本轮决定与新增交付 |
|---|---|
| 研究优先级 | 从四头资格准备收敛到 8 个既有真实语料前缀的 MS-RAW；MP/ME 43 项不在本轮审完，RS/SUM 独立维护，不阻塞 OFF/RET-MS PP1。 |
| 跨线验收 | 已向原 B 发送固定 #18 HEAD 的审查请求。GitHub 暂无 B 评论/review；`B_REVIEW_STATUS.json` 是 A 的状态记录，**不是 B 回执**。A 自检不替代。 |
| OFF / RET-MS | 从原 54 的 16 个联合 ELIGIBLE 输入定位到 #12 的 120 请求绑定，核对原 job/request/TerminalKey；原 lexical-v0 Top-1 完整 RAW 不变。 |
| renderer | PP1 使用原 G0e Notes renderer，16 份载荷逐字/逐 token 相等；#18 direct renderer 仍为独立预览提案。未来 DP-MS 使用与 OFF/RET 相同的基线和 renderer。 |
| DP-MS | 8 个独立 proposal 身份，提供全部 87 个合法历史 RAW 的无排名审阅包；不继承 #18 的“最近会话”为人工选择，不将 RET 改名。selected_record_id、最终 request_id、model_input、input_ids 都为 null。 |
| 语义范围 | 固定 first/RET/latest/current 抽查，共 20 份历史会话选择和 8 当前前缀。记录人物、第三人、阶段变化、语境张力和真实身份未确认；不改标签、不换题。 |
| GPU 申请 | 提交精确 16 次、0 warmup、HF/bf16 单 A6000 方案，显存/时间估计、停止规则和日志字段。尚无执行许可；没有加载模型。 |
| 评价 | Q0/QH/F、筛查/QH 背景和是否并入分析由 B/研究者冻结。本次 RAW 包不是固定 QH 背景；旧协议未改。 |

## 材料与身份绑定

固定 owner：p2、p3、p5、p8、p11、p13、p15、p16；执行顺序保留 B 的原 selection 顺序，每位 owner 的 OFF 后接 RET-MS，不根据内容重排。

`cpu_v2/MS_SOURCE_BINDINGS.json` 将原 bank-v0 MS record → source session/family/逐轮 span → #18 as-of record/frontier/snapshot → 原 ReadingView → 原 G0e model_input 绑定。16 个 snapshot SHA 和 8 对 horizon 在 A 的 CPU 检查中一致；已重新调用原 lexical-v0 搜索验证 8 个 Top-1 没有变化。所有当前前缀以 seeker 结束，没有包含当前后续会话。

`cpu_v2/REQUESTS_16.jsonl` 的原 request_id 不改变。`PP1-admission:` 是新增的许可/审计身份，绑定原请求、payload/native IDs、prefix、snapshot、frontier、source mapping、G/decode/renderer/Step-2；不是 C0 TerminalKey 升级，也不承接任何旧结果/reward。只允许 `model_input` 的 messages/input_ids/decode 进入模型，外侧来源、臂、评分、候选池和私有键不进入模型载荷。

63 份 #18 预览与旧 54 提案均未替换。16 份 PP1 原生重新分词结果与原 IDs 一致：输入 **137–1766**，加 320 输出最多 2086，HF 上下文 16384 内全部容纳。token 容量通过不代表资源适用或 Generator 能正确使用。

DP 的审阅材料在 `DP_REVIEW_POOLS.json`：只含当前合法前缀、全部合法 RAW、来源时间/主体说话者，不含 RET 选择、相似度、召回排名或生成结果。独立选择者须依据经确认的流程先固定条件独立 QH 背景，再选适用完整 RAW；可记录无适用材料。没有选材/人工确认就不创建可执行 DP 请求；未来选材改变必须新建内容身份，不复用待定 slot 当请求。

## owner 与语义抽查的边界

详见 `OWNER_CONSISTENCY_ZH.md` 与带原文位置的 JSON。8 个 owner 的来源/时间机械对应通过；同 owner 只是语料编组，不证明自然人身份。p13、p3 的跨 family 连接仍待人工理解；p8 存在语境张力，未自动修补；p5 的 Margaret 工作情况有阶段更新，p15 朋友经历和 p16 supporter 自述必须保持主体边界。p13/p18 共享 `esconv_1198` 的组依赖保留，扩大实验时不能拆成独立用户。

本轮没有新的人工批准。原五项 RAW 人工标注仍 `pending_human_review`；64 条 MP/ME 候选及 324 条旧隔离 MP 不变。MS-SUM 8 条仍 unusable，RS 两张 METHOD 与一条唯一 CASE（8 个绑定）的许可/适用仍 pending。它们的独立资格清单见 `OTHER_HEAD_QUALIFICATION.json`，`blocks_MS_RAW_PP1=false`。

## 分开的角色与交接

WS-A 负责以上材料。只读 integration coordinator 的工作单独在 `coordinator/`：九个 PR 当前 HEAD CI/实际步骤、祖先关系、合并推荐和 R1–R5。无文本冲突不代表联合验收，A 作者自检不作 B 批准。

优先 G0e 链 #10 → 原 B 在真实 integration 重验 → #11 → #12；MS 证据链由 B 对 #18 固定对象独立签收后处理 #15 → #18 → 本 PR。#16 在线环境仍因 source binding、入口、STOP、缓存、RELATION 的 R1–R5 HOLD；#17 合入依赖其父链。静态 PP1 不消费该在线环境，但没有撤销其缺陷或绕过受保护流程。#13/#14 可以单独文档审阅，不作为本次材料前置。

最小外部工作为：原 B 独立回执；8 个前缀的人工筛查和同前缀统一 QH 背景/两名审阅人；真实 integration 的 G0e/执行器与获准 A0 实测；研究者确认 PP1 版本和结果使用规则，并在这些材料齐备后授权最终 SHA 的 16 次调用。完整四资源资格、额外独立数据一律不被自动设置为 MS-RAW PP1 前置。额外确认数据仍按具体主张/精度/泛化需要判断。

`PP1_APPLICATION_ZH.md`、`REQUEST_LIST_ZH.md`、`PP1_LOG_SCHEMA.json` 和 `APPROVAL_TEMPLATE_NOT_AUTHORIZED.json` 是可审阅申请材料。预算为一个模型加载、16 次生成、零 warmup/Judge/训练/API；估计显存 26–36 GiB、总时间 8–20 分钟，均未实测。第三个 length、OOM、timeout、空输出、身份/泄漏或设备/时限异常停止；不按回复质量重生成。

验证和失败/跳过原因见 `VALIDATION_ZH.md`、`VALIDATION_RECEIPT.json`。所有观察/设计发生在本轮模型结果之前；没有结果驱动调参、重选或修改评价标准，没有声称支持质量增益成立。
