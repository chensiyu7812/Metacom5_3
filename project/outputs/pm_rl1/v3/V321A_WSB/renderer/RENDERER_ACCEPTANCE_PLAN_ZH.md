# 统一 renderer 候选的独立验收计划（FC-MS Gate C7）

- **现状（更新）**：WS-A 在本轮期间提交了 Draft PR #21（`46349ccf`），其中包含候选 `renderer-fcms:e675b435…`（line-quote-1）。B 已按本计划完成机械验收：**PASS_WITH_NOTES**，RA1–RA7 全部通过，原生 token 32/32 一致。回执见 [WSB_RECEIPT_PR21_RENDERER_ZH.md](../pr21_renderer_receipt/WSB_RECEIPT_PR21_RENDERER_ZH.md)。DP 行出现、正式样本请求导出后需要复跑。
- **本轮准备**：
  - 写好验收检查器 [renderer_acceptance.py](../../../../../src/metacom_pm/rl1v3/asof/renderer_acceptance.py)；
  - 统计 RAW 中会被各种转义策略改变的轮次；
  - 在 #19 的 16 个请求上做一次空跑。
- **机器可读结果**：[RENDERER_ACCEPTANCE_PLAN.json](RENDERER_ACCEPTANCE_PLAN.json)。
- **验收方式**：B 不导入 A 的 renderer，只从 RAW 和请求本身重新推出 G 实际看到的内容。

## 1. 检查项

| 编号 | 检查 | 做法 | 通过条件 |
|---|---|---|---|
| RA1 | HTML 实体 | 逐块把载荷与 RAW 会话逐轮比对：原文 / html 转义 / 不符；统计 G 可见的实体数 | 一致执行研究者决定的转义策略 |
| RA2 | 来源边界 | 每个资源臂恰好一个证据块；载荷中不出现 `<resource`、`</Notes`、`<ExternalEvidence` 等分隔符 | 0 例；如果 RAW 中出现分隔符，须有登记过的中和规则 |
| RA3 | 单因素 | 资源臂去掉插入块后，与同一前缀的 OFF 字节相同；**DP 与 RET 的框架（前言、标签、属性）完全相同**，只允许选中的会话不同 | 全部相同 |
| RA4 | 原生 token | 用 G0e 的 tokenizer 文件（不加载权重）重新套 chat template 并分词，逐 token 比对 | 100% 一致；输入 + 320 ≤ 16,384 |
| RA5 | 请求身份 | 同一实验族只有一个 renderer_id；g_id、decode、step2 不变；渲染行为一变就产生新的 renderer_id 和请求 id，不迁移旧结果 | 满足 |
| RA6 | 泄露 | 8-gram 扫描：未来文本、其他 owner、元数据（哈希、记录 id、会话 id、字段名、条件名） | 0 |
| RA7 | OFF 复用 | OFF 请求与 G0e 的 OFF 字节相同 | 相同，则 PP1 的 OFF 不受影响 |

## 2. 证据

### 2.1 RAW 文本被各种转义改变的程度（9,368 轮）

| 策略 | 被改变的轮次 |
|---|---|
| 现行 `html.escape(quote=True)` | **5,242 轮（56%）**；绝大多数是撇号变成 `&#x27;` |
| 只转义 `& < >` | 10 轮（0.11%） |
| 原文不转义 | 0 轮 |

另外，RAW 中没有任何一轮包含分隔符字符串。

### 2.2 在 #19 的 16 个请求上空跑（G0e renderer `e04b6de4…`）

| 检查 | 结果 | 说明 |
|---|---|---|
| RA1 | **需要决定** | 8 个 RET-MS 块全部被 html 转义，G 可见的实体共 148 个 |
| RA2 | 通过 | |
| RA3 | 通过 | OFF 与 RET 只差一个块；框架只有 1 种 |
| RA4 | 已在上一轮单独通过 | 16/16，见 V3.2.1 回执 |
| RA5 | 通过 | 一个 renderer_id，同一 g_id、decode、step2 |
| RA6 | 通过 | |
| RA7 | 通过 | |

## 3. 对候选的建议（供 A 和研究者参考）

1. **原文不转义，另设边界检查**：载荷保持原文；检查器保证载荷里不含分隔符。现有数据中这种情况为 0 轮，即使出现，也只需对那一轮做登记过的中和。如果研究者更看重防注入，可以只转义 `& < >`，它只改变 10 轮。
2. **DP 与 RET 共用同一个块框架和标签**：例如都用 `<resource head="MS">`。E1 renderer 的 `type="MS-RAW-direct"` 如果只出现在 DP 臂，对 G 来说就是第二个因素（B 的 #18 回执 N2、N5）。
3. **改了 renderer，就要新的请求 id**：PP1 已固定在 `e04b6de4…` 上。如果 FC-MS 采用新的 renderer：
   - PP1 仍然有效，因为它只验证程序，不估计效应；
   - 但 PP1 的 RET 回复不能并入 FC-MS；
   - 如果新 renderer 在 PP1 运行之前就定下来，建议 PP1 直接使用它，这样 PP1 同时充当工程演练。
4. **转义改动的影响边界**：只要 OFF 不含资源块，它就不应受影响（RA7）。

## 4. 提交后的步骤

1. WS-A 提交候选，内容包括：renderer 规格与 id、正式样本或 8 个前缀的 DP/RET/OFF 请求包、原生 input_ids。
2. B 运行 RA1–RA3、RA5–RA7（CPU，约 1 分钟），以及 RA4（tokenizer 环境，约 5 分钟），然后出具回执。
3. 研究者决定转义策略，Gate C7 和 C6 才能关闭。
