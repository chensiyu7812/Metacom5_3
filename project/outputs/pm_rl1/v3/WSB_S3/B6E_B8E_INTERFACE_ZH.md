# B6e → B8e 真实训练接口（CPU 准备）

- 证据等级：engineering_only。
- 本轮**没有**真实 G0 终点、J1/J2 调用、GPU 或真实模型训练。
- 用到的 fixture（NeedCard、J1 回答以及由此得到的 ER 值）都明确标为 FIXTURE，不当作 G0 终点。

## 1. 结构

依赖方向：评价侧可以 import 检查表和判官代码；训练、环境和 G 侧不能（有静态 import 测试守护）。

| 层 | 模块 | 协议 |
|---|---|---|
| 评价侧终点登记 | `evaluate/terminal_registry.py` | `pmrl1v3-b6e-terminal-registry-v1` |
| 训练侧实例 | `train/real_instances.py` | `pmrl1v3-b8e-real-interface-v1` |

## 2. 登记规则（按先后顺序检查）

1. **真实 TerminalKey 与 ExecutionTrace**：
   - trace 必须能重现 key；
   - key 必须带有计划中的完整身份（bank、index、renderer、Step-2、G0、decode），任何一项不同都拒绝；
   - 只接受规范顺序的 Phase-1 key；
   - 把 key 中的 G0/decode 身份换成正式回放的身份后，必须与正式 B5 回放中同一子集的 key 完全相同。这证明子集和交付的记录组与 integration 验收时一致。
2. **检查表先冻结**：候选终点只能通过 `ChecklistLedger.register_candidate` 登记，前缀的检查表未冻结时直接拒绝；已有候选之后，检查表不能再冻结或修改。
3. **只收 ER-v3 工程记录**：
   - 要求 `is_gsc=False`、engineering_only，且不含任何 GSC 字段，并且使用的就是已冻结的那张检查表；
   - ER-v2 记录、带 GSC 字段的记录、C0 TerminalRecord 都会被拒绝；
   - 每个终点只能写一次。
4. **pending 语义**：
   - ER 拒绝计算的终点（hard_safety uncertain、不确定权重过高等）保持 pending，并记录原因；
   - 没有登记的终点记为 missing；
   - 这两种都**不填 0**。hard_safety 失败的终点按 ER-v3 记 −1，并单独计数。
5. **完整性**：
   - 终点表报告可达、已登记、已计算、拒绝、pending、缺失的数量；
   - 表 ID 带 `complete` 或 `partial` 标记。

## 3. B8e 读取规则

- `make_env` 走 `C0FiniteHeadEnv` 和读取端口的动态容量掩码。遇到未计算的终点，STOP 时抛 `PendingTerminal`。
- `oracle_dp`、`feasible_subsets`（OneShot 目标）和 `rewards` 只接受**完整**终点表；不完整表抛 `IncompleteTable`。不可达子集用 NaN 占位，并被掩码排除。
- `trainable(instances, arm)`：BC、OneShot、PPO、NoText 都只保留完整表的实例，排除的实例连同原因一起报告；Text 与 NoText 用同一组实例。

## 4. 验证（`tests/test_rl1v3_b8e_real_interface.py`，CI 可运行）

用真实 bank-v0 和 WS-A 的 PrefixPort（测试用字符计数 tokenizer），取 B6e-v3 选中的 R16 前缀 `01c44f464e0e` 和 MP8 前缀 `ab3d17407ca4`：

| 检查 | 结果 |
|---|---|
| 16 个和 8 个可达子集的真实 key 能被 trace 重现；换回回放身份后与回放 key 相同 | 通过 |
| 检查表未冻结就登记 / 身份不同 / trace 与 key 不符 / 重复登记 | 都被拒绝 |
| ER-v2 记录 / 带 GSC 字段的记录 / is_gsc=True / C0 记录 / 未登记的 key | 都被拒绝 |
| hard_safety uncertain 导致拒绝计算，加上一个终点缺失 | 表为 partial；环境抛 PendingTerminal；不能用作 Oracle；被 trainable 排除 |
| 完整表 | Seq-BC、Seq-BC-NoText、PPO、PPO-NoText 和 OneShot 各在真实环境里跑 1 个 epoch 或 1 轮；PPO 参数确有变化；安全失败的终点为 −1 |

另外，`scripts/rl1v3/B6e_select_v3.py real-keys` 用原生 Gemma tokenizer 和 WS-A 的正式端口，重建 8 个选中前缀全部 120 个终点的真实 key，逐个与正式 integration 回放核对（结果见 `B6e_plan/v3/REAL_KEYS_CHECK.json`）。

## 5. 不能据此得出的结论

- 今后用 8 个前缀做的真实训练，只能证明工程闭环可以运行。在同一批前缀上训练又测试，不能用来声称泛化能力，也不能说明 PPO 更优。
- ER 不是 GSC；没有研究级奖励资格，也不代表自然情感支持收益。
