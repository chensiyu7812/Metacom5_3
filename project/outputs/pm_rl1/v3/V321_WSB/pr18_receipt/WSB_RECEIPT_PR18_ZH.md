# WS-B 对 PR #18 的独立回执

- **审查对象**：PR #18 HEAD `0a91ff3329dc0d091fbb9e234035638efb45146c`，base 为 #15 的 `b63635f3`。目录为 `project/outputs/pm_rl1/v3/qualification_e1_20261118/`。
- **审查者**：WS-B。只做 CPU 工作，没有加载权重，也没有调用 Generator、Judge 或付费 API。
- **结论**：分三个轴给出，互不推出。
  - 机械轴：**PASS_WITH_NOTES**（附 5 条备注）。
  - 人工语义、适用性与许可轴：**B 不签收**。
  - 研究资格轴：**尚未合格**。

## 1. 独立性

B 按 #18 的 `SNAPSHOT_HASH_SPEC_ZH.md` 自己实现了全部核验，没有导入或执行 A 的任何代码。A 的 589 项测试和参考 checker 都没有作为证据。具体做法：

- **canonical 编码**：自己写递归编码器，没有用 A 给出的 `json.dumps` 片段；另外与标准库逐对象比对，16/16 一致。
- **RAW 来源**：直接解析公开的 sanitized artifact（`51c16916…`），不经过 A1 registry。
- **前缀身份**：使用 B0 census（`377f4d0b…`）和 B6e-v3 选择（`f49b4e9b…`）。
- **Generator 身份**：使用 PR #10 `73fdb12f` 中的 `G0e.json`，包括 system prompt 和 decode 参数。
- **重分词**：使用 G0e 的 HF 解释器（transformers 5.17.0 / tokenizers 0.23.2），只读取 tokenizer 文件，不加载权重。tokenizer.json、tokenizer_config.json、chat_template.jinja 的 SHA 与 `G0e.json` 一致。
- **复用的 B 自有工具**：#16 的 sidecar adapter 与 X1–X7 检查器，覆盖全部 16 份快照。
- **代码与输出**：
  - `project/src/metacom_pm/rl1v3/asof/e1_receipt.py`
  - `project/scripts/rl1v3/V321_wsb_pr18_receipt.py`（步骤 `check` / `tokenize` / `pp1req` / `pp1tok`）
  - 测试 `project/tests/test_rl1v3_v321_e1_receipt.py`：合成 bundle，其中 5 类篡改都能被检出
  - 结果 `MECHANICAL_CHECK.json`、`PROJECTION_ROWS.json`、`TOKENIZE_CHECK.json`、`WSB_RECEIPT_PR18.json`

## 2. 机械轴逐项结果

| # | 检查 | 结果 |
|---|---|---|
| M1 | 哈希规范：4 个测试向量；自写编码器与标准库对 16 份快照逐一比对 | PASS（4/4，16/16） |
| M2 | 8 个前缀与 B6e 选择、B0 census 的 owner/session/cut_turn/cutoff_rank/timestamp 一致；前缀轮次与 RAW 逐字一致；最后一轮是 seeker；`prefix_context_sha256` 可重算 | PASS 8/8 |
| M3 | SourceFrontier 恰好等于合法过去会话（rank < cutoff 且日期 ≤ 前缀时间），不多不少；`transcript_sha256` 由 RAW 重算；`source_sha256` 按规范的 10 个字段重算；family 一致 | PASS 8/8 |
| M4 | 16 份快照的 `snapshot_sha` 可重算，并与文件、BINDINGS 一致；`source_frontier_sha256` 一致；frontier 文件一致 | PASS 16/16 |
| M5 | 双 horizon：两个 ledger 中每行的 record_id 都可重算；past ledger 是 future ledger 的前缀，且内容相同；future 新增的行全部 reported ≥ cutoff；B 用自己的规则（reported < cutoff 且 ready ≤ cutoff）从两个 ledger 分别物化，结果都等于快照（X5a）；past 与 future 快照文件逐字相同 | PASS 8/8（X5a 首次可测并通过） |
| M6 | 每条记录：owner 等于前缀 owner；每个 span 都在合法过去会话内，`exact_quote` 等于 RAW 的码点切片，`raw_turn_sha256` 可重算；时间满足 reported < known ≤ ready ≤ cutoff | PASS 8/8 |
| M7 | MS_RAW：每个合法会话恰好 1 条，span 覆盖全部非空轮次；与 BINDINGS 的 raw ids 一致 | PASS 8/8（87 条） |
| M8 | MS ReadingView：是最近一个合法会话，view=raw，正文与 RAW 逐字一致；MP/ME 均 unavailable；`reading_sha256` = MS ReadingView 的对象哈希；MP/ME 在快照中都不可读（quarantine） | PASS 8/8 |
| M9 | B 的 #16 sidecar adapter 与 X1–X4、R1–R5 RAW oracle | PASS 16/16 |
| M10 | Generator 可见投影，共 72 个位置、63 份预览：<br>• system prompt 等于 G0e；<br>• 对话部分与前缀逐字一致；<br>• OFF/R0 没有插入块，其余臂恰好在第 1 位插入 1 个 user 块；<br>• 去掉插入块后与 OFF 完全相同（单因素）；<br>• MS-RAW 的载荷反转义后等于 ReadingView；<br>• 8-gram 扫描：未来文本 0、其他 owner 0；<br>• 元数据模式（哈希、record id、session id、字段名、条件名）0；<br>• `messages_sha256`、`input_ids_sha256` 可重算；<br>• 输入 + 320 ≤ 16,384；<br>• decode 与 step2 等于 G0e；<br>• 全部 runtime_callable=false，reward 与结果均为 null | PASS 63/63（137–1,598 token） |
| M11 | 重分词：用 G0e 原生 chat template 对 63 份预览重新分词 | PASS 63/63，逐 token 一致 |
| M12 | 双 horizon ReadingView：8 对相同，并与 bundle 中的 readings 相同 | PASS 8/8 |
| M13 | owner/family 隔离：<br>• 所有记录和 span 都属于本 owner；<br>• CASE（esconv_0274）不属于 18 个 owner 中任何一个的 family；<br>• 18 个 owner 之间唯一共享的 ESConv family 是 esconv_1198（p13+p18） | PASS |
| M14 | 语义候选计数的机械一致性：<br>• 共 64 条（ME 49、MP 15）；<br>• pending 43、quarantined 21；<br>• human pending 64，runtime quarantined 64，approved 0；<br>• 与 8 份快照中的非 RAW 记录 id 完全一致 | PASS（仅验证计数，不验证语义） |

### 备注（不是 FAIL，但影响后续 Gate）

- **N1 展示属性**：MS-RAW、MP、ME 和 CASE 的证据块都经过 `html.escape`，例如 `'` 变成 `&#x27;`、`"` 变成 `&quot;`；对话本身不转义。
  - PR #10 的 G0e renderer（`request_packet.py`、`v0.py`）同样转义，所以 PP1 的 RET-MS 也受影响。
  - 这不是泄露，也不是机械错误。但它是 Generator 实际看到的文本形式，进入正式比较前需要研究者或 A 明确决定保留还是修改；修改即为新的 renderer 身份。
- **N2 单因素**：#18 的 E1 renderer（`renderer-e1-direct:323c2054…`，前言为 "Optional historical evidence…"）与 G0e renderer（`renderer:e04b6de4…`，前言为 "Notes — quoted external data…"）不同。
  - 如果 DP-MS 用 E1 renderer、RET-MS 用旧输入，比较就会同时改变选材和呈现两个因素。
  - FC-MS 必须让同一实验族的所有臂共用一个 renderer。
- **N3 RS 措辞**：RS 证据块沿用 "Optional historical evidence" 前言，但 RS 并不是个人历史。这个问题交 RS 适用性审核。
- **N4 family closure 的定义**：A 的 closure 是 as-of 的，即 owner family 加上当前及更早会话的 family。p13 截至 rank 12 时不含 esconv_1198。B 的统计聚类仍按全轨迹把 p13 与 p18 合并，更严格，不受影响。
- **N5 臂名对 G 可见**：`<ExternalEvidence type="MS-RAW-direct">` 等臂名 Generator 看得到，审阅者看不到。这属于处理本身的一部分，必须在同一实验族内保持固定。

## 3. 人工语义、适用性与许可轴：B 不签收

B 只核对了上面 M14 的计数，**没有**判断以下内容：

- 64 条 MP/ME 候选的主体、阶段与有效性；
- 8 条 SUM 不可用的理由；
- EvoEmo 上游许可；
- 2 张 METHOD 卡与 CASE 的许可、适用性和二者之间的关联。

这些都由研究者指派的审核者负责。机械 PASS 不推出这一轴通过。

## 4. 研究资格轴：尚未合格

- **现在可以用于**：
  - PP1 的 QH 背景来源（全部合法 RAW；B 已据此为 8 个前缀构建 QH 背景，见 `pp1/QH_BACKGROUNDS.json`）；
  - FC-MS 的 DP-MS 候选（8 个前缀；正式样本前缀需要按同一规则导出）。
- **不能用于**：
  - 任何效果结论；
  - MP/ME/RS 的正式比较；
  - 奖励。

## 5. PP1 的 16 个请求（Draft PR #19 HEAD）

对象是 A 的 Draft PR #19，HEAD 为 `4ac9ab3d`。文件 `cpu_v2/REQUESTS_16.jsonl` 的 SHA 为 `9af4a173…`。B 用同一套方法做了检查：

- 16/16 通过，16/16 重分词一致；
- OFF 与 RET-MS 共用同一个 renderer（`renderer:e04b6de4…`），PP1 内部没有 N2 问题；
- 8 个 RET-MS 载荷都能逐字对应到同一 owner 严格更早的一个完整会话；
- 每个请求都与 B 的 ELIGIBILITY_54 一致（plan_job_id、terminal key、旧 request id、条件），input_tokens 与 PR #13 的 job 一致；
- 8 个 RET-MS 都有 N1 所述的转义。

这是针对 #19 固定 HEAD 的正式机械回执（结果见 `../pp1_requests/`）。#19 有新提交时须用同一检查器复跑。它不构成生成授权，也不代表 PP1 协议已获批。

## 6. #16 的 R1–R5 处置

5 项全部确认属实，都是 B 的代码问题。

| 项 | 问题 | 处置 |
|---|---|---|
| R1 | binding 身份经 registry 的 source_id 间接依赖整个文件的 raw_sha256 | 接受。在 binding v2 中改用 A 规范里的会话局部 source_sha256，旧 binding 只保留为审计映射；需要 A/B 签收 |
| R2 | `BoundEpisode` 构造时没有调用完整的验证 | 接受。构造时必须完整验证，并绑定实际的 snapshot 和 port |
| R3 | STOP 后 done 仍为 False，之后的 GET 依然成功 | 接受。STOP 置 done，之后的 GET 返回 after_stop；补真实的 STOP→GET 测试 |
| R4 | 缓存在同内容重试时报错，且存在可变别名 | 接受。同内容重试应幂等，put 和 get 都使用深拷贝的不可变值 |
| R5 | adapter 遇到 RELATION 记录时报 KeyError | 接受。交换格式保留 relation、target、known/ready 与有效区间；未批准的关系不改变事实投影 |

- **对 PP1 和首轮 MS 比较的依赖**：PP1 和 FC-MS 都是静态的“固定请求 → 生成 → 人评”，不经过 `BoundEpisode`、`ReplayCache` 或 RELATION 交换。所以 R1–R5 不阻塞 G-ENG、PP1 或 FC-MS。
- **对后续在线环境的风险**：PM 在线环境、BC/PPO 以及更正链回执都依赖这些接口，因此 R1–R5 被列为 G-RWD 的前置项 R4（负责人：WS-B 修复，WS-A 签收）。本轮没有修复。

## 7. 对 Gate 的影响

Gate 的详细定义见 `../gates/GATES_V321.json`。

- **G-ENG E3**：PR #18 的 63 份预览通过；PP1 的 16 个请求在 #19 HEAD 上通过，状态为 PASS。
- **FC-MS M2**：8 个前缀可用；正式样本前缀尚未导出，状态为 BLOCKED。
- **C6 单一 renderer**：状态为 BLOCKED（N1/N2）。
- **FC-MP / FC-ME / FC-RS**：语义与许可问题仍为 BLOCKED。
