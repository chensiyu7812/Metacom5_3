# C0 0.1.0 接口提交 B 审阅

状态：WS-A 初稿，**尚未跨线冻结**；须 B 审阅、集成负责人合入后开始 A1/A1b。H0 未完成，总状态表未改。实现依据 V3.1 §5 与 RESOURCE_SPEC §2–3，交接依据 integration 的 STARTUP_HANDOFF_20261117_ZH.md。

入口为 `metacom_pm.rl1v3.contracts` 和 `metacom_pm.rl1v3.io`。全部对象是 Pydantic v2 校验的 frozen dataclass，嵌套序列为 tuple，无可变 dict。Python 构造使用 keyword-only；JSON 用 `canonical_json(obj)` / `decode_contract(Type, text)`，拒绝未知字段、重复 key、错版本、NaN。每种对象的 `.sha256` 包含所有 dataclass 字段和 schema_version。对应的 25 个 Draft 2020-12 Schema 位于 `project/schemas/rl1v3/`；Schema 负责结构/枚举/数值范围，decode 额外执行跨字段约束，SourceSpan.verify(source) 执行外部源文校验。不能仅凭 JSON Schema 通过就宣布来源/语义已验证。

时间：`TimePoint(date=None, session_rank=n)` 是合法的仅 rank 时间；全部未知用 null。rank 仅在同 owner 内有序。ResourceRecord 的 `reported_at.session_rank == source_rank`；ready_at 不得早于报告；event_time 可为合法报告的未来计划，不能改变 stage。`invalid_at.session_rank == invalidated_knowledge_rank` 且要有更正原话；**valid_to 独立、未知保持 null**，不会复制更正获知时间。SHA 不做 Unicode 规范化，否则会破坏源文字符偏移。

私有/可见边界：PrefixSpec 是执行器私有路由信封，含 owner、family、split/fold、可选评价层 stratum；调用 `.visible()` 得到只有 turns/timestamp 的 VisiblePrefix。Observation 仅含可见前缀、已读 ReadingView、availability/count、合法动作名和 input_tokens，actor/critic 共用；没有候选分数。RetrievalResult/Trace、SourceSpan、ResourceRecord、NeedCard、Checklist、TerminalRecord 都不能直接给 actor/G。ReadingView 仅 head/ordinal/reading_text/reported_at/tokens/stage，没有 record/owner/来源 hash/审阅标签。正文中的自然姓名可来自原话，内部身份不是用户可见姓名。

`SourceTurn(turn_index, role, text)` 使用 seeker/supporter 原角色，cut_turn 是包含当前 seeker 的零基索引。`PrefixSpec.from_legacy(prefix, dataset=..., family_id=...)` 适配旧 `cut_after_turn_index`，不改旧类。source_key 格式 `dataset:owner_id:session_id:turn_index`；旧 namespace 必须经 A1 映射，不能直接猜。

ResourceRecord.body 是**私有原始/类型特定 JSON 的字符串**；保留旧信息而不把任意字典键扩散成共享字段。reading_text 是独立阅读正文，不能直接渲染 body。old evidence_status 最多 exact_span_verified；没有独立语义核验不填 semantically_supported。Stage 增补 completed，并保留 unknown；supporter_suggestion 不能映成 completed/attempted。RS negative_only 不能 positive_eligible；高风险 deployment 须 professional_approved。实际来源、许可、适用性和亲代闭包由 A1/A6 外部校验，C0 不冒充完成。

TerminalKey 含规范指定全部字段。ordered_path 保存 `GET_ME` 等动作及 `EXPAND_MS(j)` 可见序号，以唯一 STOP 结尾；OFF 是 `(STOP,)`，acquired_record_ids 为空。一次 GET 可打包多条 record，故不强行将动作数等同 record 数。decode_id 要绑定 seed/backend/sampling/cap，renderer_id 要绑定 RAW/SUM/fallback 等呈现条件；改变任一字段即新哈希。TerminalRecord 的 hard_factual/hard_safety 为 pass/fail/uncertain；无反馈时 GSC 双 null，已有未知项保留区间；latency 两字段以秒计，无实测/模型时 null。ItemVerdict 独立保存 J1/J2/final，不能填数值 0 代替 uncertain。

B 审阅重点：

1. B0 的 PrefixSpec/旧 cut_after_turn_index 适配是否覆盖输入；fold/stratum 只能留执行/评价侧。
2. B5 的 action_mask 为合法动作名 tuple；EXPAND_MS 的 ordinal 在执行器动作参数及 TerminalKey 字符串中保留，不暴露 parent ID。是否需在冻结前补明确的动作参数类型。
3. NeedCard 的三类 history role、固定 applies_to=all_terminals、TerminalRecord 的三态硬约束/软偏好对象是否满足 B2/B6。
4. 对 schema/Observation/TerminalKey 的改动须独立版本并协调；WS-B 不复制另一套契约。

立即可调用：契约构造/编解码、精确跨度验证、legacy prefix 适配、可见前缀投影、身份哈希、不可覆盖的 JSON/JSONL 写入及 manifest 校验。**source_registry/bank_v0/retrieve/render 尚未交付**，不可由这个接口提交推断已经存在。
