# V3.2.1-A 研究决定：最终签署候选

- **版本**：`pmrl1v3-v321a-researcher-decision-2`，回执 sha `a499c3a1…`。
- **机器可读版本**：[RESEARCHER_DECISION_V321A_FINAL_CANDIDATE.json](RESEARCHER_DECISION_V321A_FINAL_CANDIDATE.json)。
- **登记方式**：单独版本化登记。它取代第 13 轮的候选（`95dfae50…`，#24），**不修改**任何冻结协议：P2 v1 `2b6057c8`、#17 `b28cf37b`、V3.2.1 `d2fde5db`、V3.2.1-A `27df254f`。
- **生效条件**：研究者在 §5 签署之后生效。

## 1. 研究决定

1. PM Step-1 负责资源获取（GET_MS/MP/ME/RS 与 STOP）。
2. Step-2 继续 no-plan（`pmrl1v3-g0e-no-plan-1`）。
3. Generator 隐式判断是否使用、是否提及资源；没有提及历史不算错误。
4. QH 为主要长期支持指标；Q0 为即时质量保护；F 为事实与安全约束；三者不合成总分。
5. FC-MS-1 的唯一主比较：S1 中 DP-MS vs OFF（QH）。
6. 次要机制比较：RET-MS vs OFF、DP-MS vs RET-MS，主检验为 superior 后做 Holm。
7. 暂不采用 −0.10 非劣界；不显著只写 inconclusive。
8. 人工 DP-MS 为主要诊断条件；Rule-DP 只作辅助诊断，不生成。
9. FC-MS 采用 line-quote-1 renderer（`renderer-fcms:e675b435…`），正式 DP 请求产生后复验。
10. PP1 使用旧 renderer（`renderer:e04b6de4…`），结果不并入 FC-MS。
11. 预算暂定中等方案；90 条真实 S 标签产生后、任何 FC-MS 生成结果出现前最终冻结。

## 2. 绑定的身份

| 对象 | 身份 |
|---|---|
| 协议 | V3.2.1-A `27df254fcf28…`（不修改） |
| FC-MS renderer | `renderer-fcms:e675b43535843b6d…` |
| PP1 renderer | `renderer:e04b6de4d78624db…` |
| 执行器 | #23 HEAD `67169816`（代码 `26343dc6`）；A0 binding `c9eb9169…`，PP1 binding `2a14cac2…` |
| 运行计划 | A0 `43f175c5…`（4 次），PP1 `bc51f931…`（16 次） |
| G0e 研究身份 | #10 `73fdb12f…`：本回执签署时登记为研究级身份；不等于 merge |

## 3. 工程与数据

- **E6**：**已签收**，对象是 #23 HEAD `67169816` 及其两个 binding，范围为 CPU 故障注入：
  - Python 3.11 下 49/49；
  - Python 3.12 进程路径 20/20。
  - #21 `46349ccf` 的不签收结论（43/47，4 项缺陷）及其修复记录保留在 [E6 回执](../../V321A_WSB_R13/e6_receipt/WSB_E6_RECEIPT_PR21_ZH.md)，只针对那个旧的固定身份，不代表当前状态。
- **授权**：E6 签收和本回执都**不是** A0、PP1 或任何 GPU 的运行授权；A0 与 PP1 各自需要研究者单独授权。
- **数据**：研究者的决定和仍存在的不确定性，见 [数据治理记录](../governance/DATA_DECISION_R14_ZH.md)。这项决定不是作者给出的新许可。

## 4. Gate 状态（本轮）

明细见 [GATES_R14.json](../gates/GATES_R14.json)。7 个 Gate 仍然都是 BLOCKED；逐项共 PASS 7、PENDING 26、BLOCKED 31。

| Gate | 已通过 | 仍缺 |
|---|---|---|
| G-ENG | E3 请求核验；E4 输出策略；**E6 执行器** | E1 G0e 研究身份（签署本回执即可解决）；E2 A0 实测（需授权）；E5 研究者对作业的授权 |
| PP1 | P2 QH 背景；P6 工具 | P1 等 G-ENG；P3 整理者；P4 审阅者；P5 签署本回执 |
| FC-MS | **M4 数据使用范围（研究者决定）** | 主要是：签署（C1、C9）；人工标签（C2）；正式 DP 请求与 as-of 检索（M2、M3）；renderer 复验（C6、C7）；封存 ledger（C8）；DP 工具补齐（C10）；人员（C5）；PP1（C4） |
| G-RWD | R5 | 后续在线环境工作；R1–R5 不阻止 A0、PP1 或静态 FC-MS |

## 5. 签署（研究者填写）

- [ ] 同意 §1–§3 全部条目
- [ ] 同意，但有以下修改：____
- 签署人 ____ 日期 ____
