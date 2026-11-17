# C0 contracts 0.1.0：WS-B 接口审阅

- 审阅对象：`pmrl1-v3/ws-a` 的 `50c9ade0`（C0），在 `fa52e74d` 上复核；`project/src/metacom_pm/rl1v3/{contracts,io}.py` 与 25 个 Schema
- 审阅人：WS-B（Codex B）。只做审阅，**没有在 WS-B 分支写或复制契约**
- 可执行验收：`project/tests/test_rl1v3_c0_wsb_acceptance.py`。7 项是 B 依赖的现有保证，6 项是请求变更（`xfail(strict=True)`）。C0 采纳某项后，对应 xfail 会变成 XPASS 并报错，双方随后在同一个 schema-version 提交中去掉标记
- 结论：**有条件通过**。下面 R1–R6 改完后，B5 再基于冻结的 C0 实现；N1–N7 可以和 0.2.0 一起改，也可以在文档中说明理由后保留现状

## 已核验的现有保证（通过）

| 检查 | 结果 |
|---|---|
| A 的 C0 测试（含 A0）在 Python 3.11 CPU 环境下 | 117 通过 |
| B0 的 4,119 行普查都能无损构造 C0 `PrefixSpec`，`turns` 哈希与 B0 `prefix_sha256` 一致 | 4,119/4,119 |
| B0 的 canonical JSON 哈希与 `io.object_sha256` 逐字节相同（B0 改为 import io 后身份不变） | 是 |
| `PrefixSpec.visible()` 只保留 turns/timestamp；Observation/ReadingView/HeadAvailability 不含 record/owner/session/prefix/fold/stratum/score/rank/label/reward 字段 | 是 |
| Observation 解码时拒绝未知字段（例如注入 `record_id`） | 是 |
| TerminalKey 任一字段变化都会改变哈希；OFF 只能是 `(STOP,)`，且不能带 record | 是 |
| 构造开销：Observation 约 4 µs，TerminalKey.sha256 约 16 µs | PPO 表上训练可以直接使用契约对象 |

## 必须在 B5 冻结前修改（R1–R6）

**R1 Phase-1 终点必须按子集规范化。** 目前 `GET_MP→GET_RS→STOP` 和 `GET_RS→GET_MP→STOP` 是两个不同的 TerminalKey。V3.1 §6.9 规定 Phase-1 按固定顺序渲染，终点只依赖子集。如果不规范化，16 个子集会膨胀成 65 个有序键，带来重复生成、缓存不命中和 DP 不精确。建议在 TerminalKey 增加 `domain_id: Literal["finite_head_v1","adaptive_v1"]`。在 `finite_head_v1` 下，校验 `ordered_path` 必须是固定头顺序（RS, MP, ME, MS）的子序列加 STOP，并且每个头最多出现一次；`adaptive_v1` 保留真实获取顺序。环境内部轨迹仍保留真实顺序（Observation.acquired 的 ordinal），只有终点身份做规范化。

**R2 每个非 STOP 动作绑定自己的 record 组。** 现在 `acquired_record_ids` 是平铺的元组：一次 GET 可以打包多条 record，但无法回放出哪条 record 来自哪个动作；`(GET_MP, STOP)` 配空 record 也会被接受。建议改为 `acquired: tuple[tuple[Id, ...], ...]`，长度等于 `len(ordered_path) - 1`，并且每组非空。没有可交付单元的 GET 应在执行前被 mask，不能成为终点。

**R3 动作掩码要参数化 EXPAND_MS。** 现在 `action_mask` 只接受不带参数的 `EXPAND_MS`，无法表达哪一条已读 SUM 可以展开，也和 `ordered_path` 里的 `EXPAND_MS(j)` 不一致。建议共用一种动作名类型：`GET_RS|GET_MP|GET_ME|GET_MS|STOP|EXPAND_MS(j)`（j 是已读 ReadingView 的 ordinal），mask 中禁止裸 `EXPAND_MS`。同时在 ReadingView 增加可见的 `view`（sum/raw/method/case/assertion/event），或者至少增加 `expandable: bool`，让 PM 知道哪段阅读是可展开的摘要。不暴露 parent id。

**R4 检查表要绑定前缀，并固定分母。** `ChecklistItem` 没有 prefix 归属，所以无法校验同一前缀的 16 个终点共用同一组检查项和总权重 `W_x`（§6.8.2 的硬要求）。建议新增 `Checklist(prefix_id, needcard_sha256, items, total_weight, writer_identity)`，并校验 `total_weight == sum(items.weight)`、item_id 唯一。`TerminalRecord` 增加 `checklist_sha256` 和 `feedback_id`（J1/J2 模型、提示、解析器和聚合版本）。判官身份**不进入** TerminalKey：同一回复可以被新判官重新评分，但评分身份必须独立记录，不能被沉默复用。

**R5 逐项判定要保留依据，并区分"J2 未运行"。** 附录 A 要求每项输出 verdict、回复中的 quote 和证据 source_span。现在 `ItemVerdict` 只有三个枚举值。建议增加 `J1_quote, J1_source_span, J2_quote, J2_source_span`（可为 null），并把 `J2` 改为 `Verdict | None`（None 表示未运行）。另外校验：J1、J2 都存在且不一致时，`final` 只能是 uncertain，除非有记录在案的人工裁决字段。

**R6 硬约束允许"待测"。** `hard_factual` 和 `hard_safety` 目前必须填 pass/fail/uncertain。B6e 阶段多数终点还没有安全或事实核查，只能被迫填成 uncertain，这把"未测"和"判官不确定"混为一谈。建议改为 `Verdict | None`（None 表示 pending），并在 B 侧奖励中规定 pending 不能算 0，也不能算 pass。

## 建议一起改或说明（N1–N7）

- **N1** §6.9 的初始观察包含"该 owner 历史会话数"。现在只能间接从 MS 的 count 推断，语义不同（MS 的 count 是候选数）。建议在 Observation 中增加 `history_sessions: Nonnegative`。
- **N2** Observation 的 docstring 写"No IDs, ranks"，但 `ReadingView.reported_at.session_rank` 是 owner 内的绝对 rank。建议在 ReadingView 中改用相对值 `sessions_ago`（= cutoff_rank − source_rank），或者修改 docstring，明确 rank 是允许的合法报告时间。
- **N3** NeedCard：`outdated_facts` 按附录 A 应是 `(old_span, new_span)` 成对结构；增加 `writer_identity` 与 `input_sha256` 以便复现；增加跨度校验状态。
- **N4** PrefixSpec：V3 的 `prefix_id` 统一由 B0 生成，规则是 `object_sha256({protocol, dataset, owner_id, session_id, cut_turn, prefix_sha256})`，绑定内容，与折分无关。`from_legacy` 使用的旧 identity 含 split，只能用于历史产物，不能用于 V3 新数据。`ancestor_family_ids` 建议定义为"当前会话和全部严格过去会话的 family"，由 B0 填写，供 RS family 闭包过滤（例如 84 个 ESConv 种子）。
- **N5** `HeadAvailability.count` 的语义需要写进 docstring：它是合法性过滤（owner、cutoff、ready_at、family）后、与查询无关的候选池大小，所有臂一致。Phase-1 每次 GET 只交付一个确定的阅读单元，与 count 无关。
- **N6** `retrieve.read` 的失败（空、超出原生容量）应返回带类型的拒绝，不产生 ordinal，也不产生 G 输入。为了在执行前 mask 超容量的 GET，`RetrievalResult` 需要私下带上"将交付单元的 tokens"（只给执行器，不进 Observation）。
- **N7** Phase-1 的"每头 top-3 分数与大小"可见元数据，按 RESOURCE_SPEC §5.1 先退回 availability/count-only；若之后做成消融，必须升级 schema 版本并让所有臂同时获得。

## 对 B 侧的影响

- B0 已与 C0 兼容。C0 冻结后，B0 改为 import `rl1v3.io` 并升级 protocol 版本号；身份值不变，因为两边哈希逐字节相同。
- B5 等 R1–R3 冻结后实现。DP、mask 和状态转移将直接使用 C0 的 Observation 和 TerminalKey，不另造类型。
- B2 和 B6e 依赖 R4–R6；在这之前只做内部实现草稿，不落盘正式终点表。
