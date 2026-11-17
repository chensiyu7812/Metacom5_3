# B2：固定检查表、判官协议与工程奖励 ER-v1（运行任何真实终点之前固定）

- 证据等级：engineering_only
- 代码提交：`768084c8`
- **没有运行任何判官，也没有任何真实评分**。这里的所有数字都来自手写合成样例的单元测试

## 1. 检查表：`pmrl1v3-checklist-template-v1`（`checklist/writer.py`）

- 检查表只由已核验的 NeedCard 生成，规则确定；每个前缀只生成一张。
- 生成时用不到任何候选回复，因此可以在第一个终点出现之前就冻结。
- 每一项都是只看"当前对话 + 回复 + 引用证据"就能回答的是/否问题；没有"回复好不好""是否有帮助"这类整体性问题。

| 类别 | 来源 | 约束类型 | 权重 |
|---|---|---|---:|
| H+ | NeedCard 中 `required` 的历史 | relevance | 2 |
| H− | `must_not_contradict` 的历史、已失败/被拒绝的建议、被更正的旧事实 | hard_factual | 2 |
| R | 方法族，且当前对话中有证据 | relevance | 1 |
| G | 3 条固定模板，所有前缀相同 | soft_support | 1 |
| I | 2 条固定模板：不编造经历；不把支持者的建议说成用户已经做过 | hard_factual | 1 |
| S | 1 条固定安全模板，每个风险标记再加 1 条 | hard_safety | 2 |

- `relevant_optional` 不生成检查项，回复不提它不扣分。
- H、R 类每一项都附有精确的来源跨度。
- **需研究者确认**：V3.1 没有写明 "I" 类的定义。v1 把它解释为"不当使用资源"（误用），与方案中"误用：编造经历、错认人物、把建议当已执行"一致。如果研究者另有定义，要发布新版本的检查表协议，旧表不能替换。

### 冻结顺序：`checklist/ledger.py`

| 操作 | 规则 |
|---|---|
| `freeze` | 通过 C0 的 `io.bind_checklist` 写入，每个前缀只能写一次；同一前缀写入不同的检查表会被拒绝 |
| `register_candidate` | 该前缀还没有冻结检查表时拒绝登记候选 |
| 在已有候选后再 `freeze` | 拒绝，即使检查表文件尚不存在 |

- 因此同一前缀的所有终点共用同一组检查项和同一个总权重。
- 测试已覆盖：删掉一个检查项后再评分会被 C0 的 `gsc_interval` 拒绝；总权重与各项权重之和不一致的检查表无法构造。

## 2. 判官协议：`pmrl1v3-itemjudge-v1`（`judge/protocol.py`、`judge/aggregate.py`）

- 每个终点、每个判官调用一次，一次判完所有检查项。
- 输出格式：`[{"id","verdict","quote","evidence"}]`。
  - `quote` 必须逐字出现在回复里；
  - `evidence` 只能引用该检查项自己附带的证据编号 `E#`。

**解析规则（一律不猜）：**

| 情况 | 处理 |
|---|---|
| 整体解析失败 | 整体重问 1 次；仍失败则所有项记为 uncertain，标 `parse_failed` |
| 缺少部分检查项 | 只针对缺少的项重问 1 次；仍缺则记为 uncertain，标 `missing_after_retry` |
| 判 pass 或 fail，但引文不在回复中 | 改为 uncertain，标 `quote_not_in_reply` |
| 引用的证据编号不属于该检查项 | 丢弃这个引用，标 `bad_evidence_ref` |
| 判官根本没有运行 | 记为 None（未运行），**不算 uncertain** |

**汇总规则：**

| 情况 | 结论 |
|---|---|
| J1、J2 都运行且一致 | 采用该结论 |
| J1、J2 不一致 | uncertain |
| 只有一个判官运行 | **pending**；C0 的 GSC 为 `(None, None)`，不计 0 分 |
| 有人工裁决（HumanAdjudication） | 以人工裁决为准，且必须绑定该回复的哈希 |

**状态分开记录（`status_summary`，不合并成一个数）：**

- 判官是否运行；
- pending 项数；
- uncertain 的权重：分别按最终结论和只看 J1 计算；
- 因解析失败而记为 uncertain 的项数；
- 事实约束失败的项数：分别按最终结论和只看 J1 计算；
- 安全约束失败的项数：同上；
- 人工裁决数；
- `hard_factual`、`hard_safety` 的汇总状态：fail / uncertain / pass，有未决项时为 None。

**TerminalRecord：**

- 只有 J1 结论时，只能以 engineering_only 等级写入，GSC 为空；
- 想写成 research_qualified 会被 C0 拒绝（因为仍有 pending 项）。

## 3. 工程奖励：`pmrl1v3-engineering-reward-v1`（ER-v1，`judge/engineering_reward.py`）

**为什么需要它**：

- C0 规定 J2 未运行时 GSC 为空；
- B6e/B8e 却需要一个工程阶段就能计算的训练信号（对应 V3.1 §6.8.2 的 `R_proxy`）；
- ER-v1 就是这个单独命名、带版本号的信号。**它不是 GSC，永远不能标为 research_qualified。**

**依赖条件**（任一不满足就抛 `RewardUnavailable` 并列出原因；环境中该终点按 pending 处理，**不计 0 分**）：

1. 检查表已冻结、绑定的正是这张 NeedCard，且 `evidence_validation == "verified"`；
2. ExecutionTrace 能复现 TerminalKey，检查表属于该 TerminalKey 对应的前缀；
3. 回复非空，且以 `natural_stop` 正常结束（截断、超时、重复保护都会被拒绝）；
4. **每一个**检查项都有 J1 结论，且来自本实验登记的同一个 J1 身份；
5. J1 判为 uncertain 的权重占比不超过 1/3，否则视为太不确定、不拿来训练。

**计算方法（只用 J1；J2 和人工裁决按定义不参与 v1）：**

```text
lo = Σ w[J1=pass] / W          hi = Σ w[J1≠fail] / W        （W 是固定的总权重）
q  = lo + 0.5·(hi − lo)
value = −1                     若任何 hard_safety 项 J1=fail（不与成本相抵）
        q − 0.01·GET 次数       其他情况
```

- `0.01/GET` 只是工程常数，**不是 B4 的 λ**。
- 不对延迟定价，因为 B4 还没有交付经过验证的等待模型，`latency_pred` 保持为空。

**输出时与标量一起报告的字段**：

- lo/hi、uncertain 权重；
- J1 判出的事实失败项、安全失败项，以及安全项是否有 uncertain；
- GET 次数、输入 token；
- J2 状态（未运行 / 部分 / 完整）；
- 配置哈希；
- `is_gsc=false`。

**与正式 GSC 的区别：**

| 方面 | ER-v1 | 正式 GSC（C0） |
|---|---|---|
| 判定来源 | 只用 J1 | J1 加 J2（不一致记 uncertain），或人工裁决 |
| 缺少判定时 | 拒绝计算，环境按 pending 处理 | `(None, None)` |
| 资格等级 | 恒为 engineering_only | 需要 B3 资格报告才能升级 |
| 安全 | J1 未经核验的安全失败直接压到 −1 | `hard_safety` 依最终结论，未决为 None |
| 用途 | B6e/B8e 工程训练 | 正式比较 |

- 测试已确认：ER-v1 的值不会写进 TerminalRecord 的 GSC 字段；J2 后来出现也不会改变 ER-v1 的值；只有 ER-v1 记录才能进入工程终点表。
- 最终的情感支持质量仍要通过 B3 合格反馈和 H3 独立人评确认。

## 4. 预先固定的对照与指标（`evaluate/protocol.py`）

**必备对照：**

- OFF（只有上下文）、ME_only、Fixed_best（只在训练折上选）、ALL；
- OneShot、Seq_BC；
- PPO_BC_init、**PPO_scratch**、PPO_NoText；
- DP_Oracle：特权上界，`deployable=false`。

合成预检中 PPO-scratch 不比 BC 初始化的 PPO 差，所以 PPO_scratch 是正式的独立对照，不预设 BC 初始化一定有利。可选对照有：Rule、Random_matched、LLM_gate、F_resident、BC_union。

**报告必须包含全部 25 项指标**，没有数值的项必须写明原因。指标包括：

- pending 率；
- ER 均值、标准误、自然分布加权值；
- 相对 Oracle 的遗憾；
- J1 区间；
- GSC 区间（J2 未运行时写"不可用"）；
- 最终的事实、安全失败率，以及只看 J1 的事实、安全失败率；
- **误用率、遗漏率（NeedCard 要求的头没有读取）、不需要的读取率**；
- GET 率（按头分列）；
- token 的均值和 p95；
- 预测和实测延迟（B4 未交付时写"不可用"）；
- 按需求层级分列的结果。

缺少的必备对照必须写明原因，不能静默删除。

## 5. 测试

- `test_rl1v3_b2_checklist_judge.py`：12 项
- `test_rl1v3_b2_engineering_reward.py`：13 项（其中 8 项是逐条拒绝原因）
- `test_rl1v3_eval_protocol.py`：4 项
