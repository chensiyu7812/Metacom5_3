# PP1 生成之后：R1/R2 盲评页构建清单（只给 CUR1）

**前提**：A0 已通过；研究者已单独授权 PP1；16 次生成已经完成，并通过 WS-A 的核验。在此之前，不制作任何真实回复的评审页。

## 输入（WS-A 提供，放在 CUR1 的保管目录）

| 文件 | 内容 |
|---|---|
| `REPLIES.jsonl` | 每行一条：`reply_key`、`case_key`（8 个 PP1 前缀之一）、`condition`、`text`（Generator 原始回复） |
| `PAIRS.json` | `[pair_key, case_key, reply_key_x, reply_key_y]`，共 8 组 |
| `salt.txt` | CUR1 自己生成一次，并一直保管（至少 16 个字符）；不放进仓库，不交给 R1/R2 |

## 步骤

| # | 谁 | 做什么 | 命令或检查 |
|---|---|---|---|
| 1 | CUR1 | 生成回复翻译批次 `Y01.txt`，放到 `CUR2_操作/`。批次里只有“回复 01…16”，顺序已打乱，不含前缀、配对、位置或条件 | `replybatch --replies … --pairs … --salt-file …` |
| 2 | CUR2 | 用 ChatGPT 翻译 Y01，规则与其他批次相同，返回 `Y01.zh.txt` | 逐行检查：缺行、数字、译注、照抄英文 |
| 3 | CUR1 | 构建 R1/R2 第一部分（只有 Q0，没有历史），放进 `R1/` 和 `R2/` | `reviewers …`：两人的文本和译文完全相同、位置镜像、盲态扫描、页面检查 |
| 4 | R1、R2 | 各自完成 Q0，锁定并导出阶段文件，交给 CUR1 | 页面强制先锁定 |
| 5 | CUR1 | 登记 Q0 锚点，生成该审阅者的第二部分（QH、探针、F，含完整历史及其中文） | `part2real --who R1 --export …`：锚点不符的第二部分，页面拒绝载入；同一人不能登记两个不同的锚点 |
| 6 | R1、R2 | 完成 QH、探针、F，锁定并导出最终文件，交给 CUR1 | — |
| 7 | CUR1 | 收件，核对两份最终文件 | `receive`；`pp1_tool.verify_export` |
| 8 | CUR1 | 列出 F 严重分歧，生成裁决包交给 CUR2 | `pp1_tool.f_disputes`、`adjudication_package`；PP1 没有 DP 条件，所以 CUR2 可以裁决全部分歧 |
| 9 | CUR1 | 两人和裁决全部锁定之后，做 F-A 审计（非盲） | `auditor_package` |
| 10 | CUR1 | 程序指标：用时、盲态探针、一致性、历史阅读 | `procedure_metrics`；只把汇总交给研究者 |

## 不能做

- 不在 R1/R2 锁定之前，把任何回复、条件或生成清单给他们。
- 不让 R1 或 R2 操作 Y01 的翻译。
- 不因为页面或翻译不方便就取消锁定或盲态。检查不通过的页面不发出。
