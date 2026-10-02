# Paper-1 人评参考材料 V2（2026-09-08）

状态：`ACTIVE / RESEARCHER-AUTHORIZED SCOPED AMENDMENT / HUMAN RATINGS PENDING`

研究者在审阅 2026-09-07 的 DG 证据缺口及工作量说明后授权：“行吧，那做吧，应该怎样做，最能支持主张的，怎样最能校准的，就怎么来。生成新的人评卷子吧。” 本授权执行的是提高测量有效性、生成新版盲评卷，不以产生正向结果为目的；不授权 Gemini、正式 effect、PM training 或正式 benchmark 调用。

本修订仅对 human reference、对应 pairwise teacher 的证据规则、离线交付与接收格式具有 scoped precedence。当前 config 指向本次新版 machine contracts；旧版保留为来源追溯。

## 原因、修改与保留

2026-09-07 内容审计发现，DG 参考只含 topic 的 related_sessions，检索资源却可以来自完整过去历史。27 个 DG 基础 pair 的 15 个资源包至少包含一个卷内未展示的来源会话；该计数不是无效题数。内容核查确认存在回复中实际提及、在原始历史有依据、但在卷内未展示的历史事实。本修订发生在生成文字经过内容审计之后、主评和 Gemini 判定尚未收集之前；不把它描述成完全未见回复的修改。

保留既定 80 基础 pair + 16 反序 = 每人 96 题，两名主评共 192 个判断，任务配额及九个 DG 情境不变。保留全部 142 条生成回复、题目、A/B 映射和两人各自题序。数量依据是既定覆盖设计，不声称 96 为统计功效证明的最低样本量。样本和裁判均不根据正向标签率、PM 表现或期待的结论选择。

DG 每题的统一参考载荷包括原相关历史摘录，以及同一用户、目标截止边界之前的完整原始会话。按 runtime source 的 session chronological rank 严格检查 `rank < target.cutoff_rank`；当前 B17 边界为该用户全部历史会话数。保留原角色、日期和原文，不生成摘要、不按回复内容检索补充证据，不包含隐藏的新话题 narrative、seeker 心理/身体设定或未来对话。两个回复使用同一参考；人类与 Gemini 接收逐字相同的参考载荷。

DG rubric 澄清：摘录不穷尽历史；不能只因摘录没有某事实就判为编造。核查时区分 seeker 的陈述与 supporter 的猜测，区分过去事件与当前状态，考虑时间和可见更新。完整证据仍不能支持可靠判断时允许 uncertain。QA、Summary、ESC 的原题、reference 和质量判定定义保持现行口径。

网页为无外部依赖的离线表单，提供中文操作说明、原英文文本、并列 A/B、完整历史的会话索引和字面搜索、本机保存、进度导出和恢复。搜索只做文本匹配，不替评审选证据或评分。JSON 是完整、可移交的规范答卷；网页仅改变展示方式。英文 rubric 为规范文本，中文为一致的阅读辅助。每题只要求 verdict 与 rationale，中文或英文理由均可。

## 双评与预先确定的分歧处理

两名主评独立完成自己的全部 96 题，不交流判断、不查看对方答卷，不由模型代评。允许休息、分次填写及在本人材料内查证；不寻找重复题、不为使重复题一致而改答案。回复即使截断、拒答或质量差，也按实际内容评，不补全或重生成。

收到两份完成答卷后先验证身份、完整性和原题不可变字段，封存原始评分。主评一致性与反序稳定性均使用封存原始数据，不能被后续共识结果覆盖。

在本轮选择既有方案允许的 **predeclared consensus adjudication**：使用每个基础 pair 的原始非反序呈现作为规范 A/B 方向。两位主评在该呈现上同为确定方向或 equivalent，且存在的反序核验无不一致时，可直接形成 reference；任一 uncertain、主评分歧或反序不稳定进入单独的共识记录。两人仍只看匿名回复与同版证据，在原始评分封存后讨论；没有有依据的共识则保留 uncertain，不强制多数、不改原评分。共识在查看 Gemini verdict 前封存；不属于 192 个独立主评判断。

teacher 报告包含原始双评一致性、每任务/每类别支持数、对每位主评及共识 reference 的结果、反序稳定性、equivalent recall、位置偏好、uncertain 和解析失败。DG 按九个共享情境聚类，memory 推断以 owner 为最高聚类层；反序不作为新增独立任务。没有任意一致率 PASS 门槛，也不据同一人评卷反复调 rubric 到“通过”。

## 版本与复核

- 旧 v1 卷及其哈希保留，新提交入口为 v2。旧评分若出现需独立归档，不能无版本区分地混入新版。
- 生成和 seeker 产物仍有效，无需重跑；已有费用记录不变。
- 新建 reference amendment、instrument v2、human-reference design v2、qualification plan v3、Gemini identity v2 和 sheet manifest v2。
- Gemini 模型、provider、解码、retry 和预算上限不变；更新 DG rubric/payload 身份。解析器落实原契约对重复/冲突 JSON 字段 fail-closed 的要求；这不是新的判分标准。
- 导出精确 Gemini 请求 manifest，核对人机输入参考完全一致。只能做离线 token 估计，实际付费前仍需 provider token count 与累计/阶段预算 reservation；本轮不发送请求，不增加 $0.10 qualification cap。
- 必须复核：原卷不变、80/16/96 分母、全部回复与题序不变、严格过去完整来源覆盖、匿名化、反序、人机证据一致性、导出/恢复/篡改拒绝、离线浏览器行为和当前集成检查。

研究主张、四头定义、learner、正式标签规则、amount/top-k 顺序和四把 CLOSED 锁均不变。此轮只是测量参照，不是 PM 训练标签或自然轮次适当性评测。之前审计指出的 teacher 目标与后续验证隔离仍须在正式 calibration/effect manifests 中解决；本修订不静默改 fold 或解封正式结果。
