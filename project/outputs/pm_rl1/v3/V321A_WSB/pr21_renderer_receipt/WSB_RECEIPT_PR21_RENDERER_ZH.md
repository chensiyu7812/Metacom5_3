# WS-B 独立回执：PR #21 的 FC-MS renderer 候选

## 审查对象与方法

- **对象**：WS-A Draft PR #21，HEAD `46349ccf02fef477bfc8fd76114bf1e38044e1d3`。
  - 文件：`runprep_fcms_20261119/cpu_v2/RENDERER_PREVIEWS_32.jsonl`（sha256 `4321d65f…`），共 32 行：
    - 旧 G0e renderer `e04b6de4…`：16 行；
    - 新候选 `renderer-fcms:e675b435…`（line-quote-1）：16 行，即 8 个前缀 × OFF/MS。
- **范围**：只审查 renderer。执行器（Gate E6）、A0 申请和 DP 选材界面不在本回执内（§4 有一条兼容性说明）。
- **独立性**：B 没有导入或执行 A 的 renderer 代码。B 按 #21 公布的 POLICY，自己实现了 line-quote-1 解码器，把载荷还原后与 RAW 逐轮比对。所用代码：
  - [renderer_acceptance.py](../../../../../src/metacom_pm/rl1v3/asof/renderer_acceptance.py)；
  - [V321A_wsb.py](../../../../../scripts/rl1v3/V321A_wsb.py) 的 `pr21` 与 `pr21tok` 两步。
- **机器可读结果**：[RENDERER_RECEIPT_PR21.json](RENDERER_RECEIPT_PR21.json)、[PR21_TOKENIZE_CHECK.json](PR21_TOKENIZE_CHECK.json)。
- **结论**：机械轴 **PASS_WITH_NOTES**。是否采纳这个候选，以及转义策略，需要研究者决定（Gate C6、C7）。

## 1. 逐项结果

| 检查 | 结果 | 证据 |
|---|---|---|
| RA1 HTML 实体 | **PASS** | 8 个 MS 块全部是 line-quote-1，由 B 解码后与同一 owner 严格更早的完整会话逐轮相等；G 可见的 HTML 实体为 0。旧 renderer 下这 8 块共有 148 个 `&#x27;`，新候选中这 148 个撇号都保持原样 |
| RA2 来源边界 | **PASS** | 每个 MS 臂恰好一个 `<resource head="MS" encoding="line-quote-1">` 块；每一行都以 `\| ` 开头；载荷中没有未编码的 `< > [ ]` |
| RA3 单因素 | **PASS** | 资源臂去掉插入块后与 OFF 字节相同；8 个 MS 块去掉载荷后只有 1 种框架。renderer 没有臂参数，DP 与 RET 会用同一框架，这一点是按构造成立的（见注 N-c） |
| RA4 原生 token | **PASS** | 用 G0e 的 tokenizer 文件（transformers 5.17.0，未加载权重）重新套 chat template 并分词：32/32 逐 token 一致；输入 + 320 ≤ 16,384 |
| RA5 请求身份 | **PASS** | B 用 `object_sha256(POLICY)` 重算的 renderer id 与行内的 id 相同；g_id、decode、step2 与 G0e 相同；16 个新请求 id 与 PP1 的不重复 |
| RA6 泄露 | **PASS** | 8-gram 扫描：未来文本 0、其他 owner 0、元数据 0 |
| RA7 OFF 复用 | **PASS** | 新候选的 8 个 OFF 与 PP1 的 G0e OFF 字节相同 |
| 旧 renderer 的 16 行 | **PASS** | 与 #19 的 PP1 请求在 messages 和 input_ids 上都完全相同 |
| renderer 比较是否单因素 | **PASS** | 新旧 renderer 下，8 个 MS 块引用的是同一个会话（与 PP1 的 RET 来源相同） |

**全部 RAW 上的影响**（9,368 轮）：

| 策略 | 被改变的轮次 |
|---|---|
| line-quote-1 | 3 轮 |
| 现行 `html.escape` | 5,242 轮（56%） |
| 只转义 `& < >` | 10 轮 |

## 2. 备注（不是 FAIL）

- **N-a 头部方括号**：每块开头的 `[MS; reported 日期]` 位于引文之内，方括号被编码成 `[`/`]`。所以每个 MS 块里，G 都会看到 2 个转义序列。各臂相同，不构成单因素问题，但这是 G 可见的噪声。可以考虑把头部移到引文之外，或者不把方括号列为保留字符；无论选哪种，都是新的 renderer id。
- **N-b 前言增加了一句**：新候选在原 Notes 后增加了“Every | line below is quoted external data…”。这是 renderer 因素的一部分，属于预期。因此 PP1（旧 renderer）的 RET 回复不能并入用新 renderer 的 FC-MS。这与版本 A 协议一致：PP1 只验证程序。
- **N-c DP 行尚未出现**：当前预览只有 OFF 和 MS 两种臂，MS 的证据与 PP1 的 RET 相同。DP 与 RET 共用同一框架这一点，是按 renderer 的构造和单一框架推出的。DP 选材完成、正式样本请求导出后，B 用同一检查器复跑，届时 RA3 才真正覆盖 DP。
- **N-d 行为层面的抗注入未测**：A 已经在 RENDERER_SECURITY 中注明这一点。编码只保证语法上的边界，不证明模型行为；本回执也不对此作结论。

## 3. 对 Gate 的影响

- **C7**：由 BLOCKED 转为 **PENDING**。B 的机械回执已通过，等待研究者采纳，并在正式样本请求导出后复跑。
- **C6**：仍是 BLOCKED，需要研究者明确决定：FC-MS 统一使用 `renderer-fcms:e675b435…` 还是其他 renderer，以及转义策略。
- **PP1**：继续使用旧 renderer `e04b6de4…`，不受影响。

## 4. 不在本回执内的事项

- **执行器（E6）**：#21 的 limited_run 等文件尚未审查，下一步单独出具回执。
- **DP 选材界面**：A 的界面（8 个前缀、87 份合法 RAW、可选 none/uncertain、记录理由、冻结 SHA）与版本 A 协议的 A4 相容。研究者可以在两种方式中选一种（Gate C10）：
  - **(a)** 由整理者（不是该前缀的审阅者）用 A 的界面自由选择，并写明理由；
  - **(b)** 用 B 的确定性规则，从表单 S 的片段标注中导出。
  - 两种方式都满足 #19 的 selection_policy：(b) 不增加人工步骤，(a) 允许选 none 或 uncertain。

本回执不构成任何生成授权。
