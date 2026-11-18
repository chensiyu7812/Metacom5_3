# WS-B 对 WS-A as-of sidecar（PR #15）的独立复核收据

- 复核对象：PR #15 `pmrl1-v3/ws-a-asof-cpu-20261118` @ `b63635f3621f3a5d252099efcd58ae2d1958dce2`，65 个快照文件（集合 SHA `7dccff27…`，见 `asof/WSA_SIDECAR_INDEPENDENT_CHECK.json`）。
- 复核方：WS-B owner。只读 A 的输出文件，**不导入、不执行 A 的代码**；判定逻辑全部是 B 自己的实现（`asof/check.py`、`asof/wsa_adapter.py`）。
- 证据等级：engineering_only。下面的"通过"只是机械层（来源、时间、主体所属 owner、追加不改写），**不是**语义批准、人工审核或 H0 采纳。PR #15 内的"B 角色 AI 工程复核"不能替代本收据，本收据也不能替代人工语义审核。

## 1. 结果

| 检查 | 范围 | 结果 |
|---|---|---|
| X1 frontier 与 registry 合法历史完全一致（不多不少） | p1 / p15 / p18 共 65 个切点（31 / 21 / 13） | 65/65 |
| X2 每条记录的 span 逐字回查原文；只来自严格过去、已完成的同 owner 会话；不含当前会话 | 65 个快照中的全部 1,073 次记录出现 | 0 违规 |
| X3 known ≥ 报告 rank；ready ≥ known；ready ≤ cutoff | 同上 | 0 违规 |
| X4 event_time 无证据不得出现；stage 取值合法 | 同上（A 的 ME/MP 阶段：attempted 36、outcome_reported 35、intended 32、unknown 30、suggested 19、rejected 3） | 0 违规 |
| B 自建 RAW oracle：可读 MS_RAW 恰好等于全部严格过去会话，每条非空话语逐字出现；非 RAW 记录全部未开放读取 | 65 个快照 | 65/65；MP/ME/SUM 全部 quarantine |
| X5b 后来切点不改写已 ready 的过去记录 / X5c 过去记录不会无后继地消失 | 每个 owner 的全部切点对 | 0 违规 |
| X5a 同一前缀在不同 writer horizon（只见过去 vs 已见全历史）下快照相同 | — | **无法从导出文件检验**：每个前缀只导出一个 horizon |

检查器本身用 bank-v0 做了阴性/阳性对照（B6e 8 个 owner 的 192 个切点 × 2 个 horizon）：bank-v0 的 MP 全历史 latest 规则触发 175 处 X5a 违规；同一批编译单元按"截至 cutoff 的最新值"重建后，0 违规。所以 X5a 检查是有效的，只是 A 目前的导出文件无法用它来检验。

## 2. 接口字段对齐（B 提案 `pmrl1v3-prefix-asof-binding-v0.1-proposal` ↔ A 候选 `57047c5f…`）

| B PrefixAsOfBinding | A 接口候选 | 处理 |
|---|---|---|
| prefix_id / session_id / cut_turn | 无（A 用 prefix_context_sha256 定位） | B 保留：B0 prefix_id 是 B 侧 join 键；由 prefix_context_sha256 唯一反查（65/65 成功） |
| owner_id、cutoff_rank、timestamp、prefix_context_sha256、family_closure | PrefixAsOf 私有字段 | 一致 |
| source_frontier（source_id、rank、transcript_sha256、ready_rank） | SourceFrontier.sources（source_sha256、transcript_sha256、known/ready…） | 等价：经 registry (owner, session) 映射，65/65 一致 |
| external_snapshot | external_RS external_version | **B 已改为只用 RS 自身版本**（原先用了全局 registry 版本，会让追加未来会话改变历史身份；A 的设计是对的） |
| fold | identity_exclusions 含 fold | **B 已从身份中剔除 fold** |
| writer_identity / writer_kind | writer_identity / protocol | 一致；bank-v0 记为 `legacy_full_history_projection`，不能晋级 research |
| snapshot_sha256 | snapshot_sha | 一致；B 目前无法重算 A 的 snapshot_sha，需要 A 给出规范（见第 3 节） |
| bank_version / index_version / query_id | 无（sidecar 尚无检索索引） | 联合规则：直接提供（P2 E1）时 query_id = `direct_provision`；一旦引入检索，必须给出真实的 index 身份 |
| renderer_id / g_id / decode_id / step2_id | new_request_rules 中已绑定 | 一致 |
| visibility_policy | pm_visible / g_visible（文字描述） | 用 B 白名单的 SHA `ac4a256e…` |
| tier | qualification | 一致：本轮全部 engineering_only |

C0 0.2.0 不需要修改。正式把 as-of 身份写入 TerminalKey 的迁移只是提案（`asof_binding_sha256`），需要跨线评审并由 integration owner 决定；在此之前，B 侧所有新的缓存和终点都用复合键 `asof_terminal_key_sha256(C0 key, binding)`，旧 key 和旧 reward 永远查不到新身份。

## 3. 请 WS-A 补充（不阻塞本收据的机械结论）

1. 给 3 个 owner 各导出至少一组**双 horizon** 快照（writer 只见过 cutoff 之前 vs 已见全历史，然后都取 cutoff 视图），让 B 能直接从文件检验 X5a。
2. 给出 snapshot_sha 的规范（字段顺序和编码），让 B 能独立重算，而不只是信任 manifest。
3. 本批真实文件中没有 invalidation，也没有 valid_from / valid_to：迟到更正（"r5 才知道的事不能出现在 r4"）目前只在 A 的单元测试里验证过，真实数据中没有出现。请至少提供 1 个真实的更正链，或明确声明没有。
4. A 的 sidecar 中 MP 只有 4 条唯一记录：MP 头的 as-of 视图目前基本是空的。54 个输入中涉及 MP 的条目全部判为 BLOCKED，与此一致。

## 4. 不能据此声称的内容

as-of 环境已达到研究资格；MP/ME 语义正确；任何资源有增量价值；旧 bank-v0 的 120 个工程终点可以改名成新的 as-of 终点。
