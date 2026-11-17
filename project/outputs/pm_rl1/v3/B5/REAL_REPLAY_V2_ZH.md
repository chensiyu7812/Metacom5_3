# B5 真实 bank-v0 回放 v2：24 个固定覆盖前缀（集成前运行）

- 证据等级：engineering_only。只用 CPU；读取 Gemma tokenizer 文件，没有加载权重；Generator、判官、GPU、付费调用都是 0 次
- **正式结果**：`real_replay_v2_aport_02d0a4b1_173bed23/`。
  - 用 WS-A 自己的读取端口 `bank.v0_port.PrefixPort`（`pmrl1v3-a1b-read-port-v1`，PR #8 head `a26998f0`），代码 `173bed23`；
  - 含 `replay_reports.jsonl`、`summary.json` 和 `manifest.json`（输入、输出、代码文件的 SHA256）。
- **交叉核对**：`real_replay_v2_02d0a4b1_d06715bf/`。
  - 用 B 的薄适配层 `env/a1b_port.py`，基于 A 的上一个 head `a0771e1e`，代码 `d06715bf`；
  - 两次运行逐前缀比较 key、可达子集、各子集输入 token、availability 和身份，结果见第 2 节。
- **状态 `pre_integration_rehearsal`**：WS-A 的 A1 `7116b8bd` 和 A1b `c9dd5aae` 还在 PR #8 中，尚未合入 integration（脚本运行时用 `git merge-base` 实际检查过）
  - 本次用的是 A 的真实 source registry 和 bank-v0；
  - 但按规定这还不是"正式交付后"的回放；
  - PR #8 合入后，在 integration 上用同一脚本重跑，核对报告逐字节相同后，再作为正式结果
- v1 回放器（`bank_replay.py`）、v1 配置和 `REAL_REPLAY_STATUS_ZH.md` 都保持不变

## 1. v2 修复的五项跨线差异（集成负责人在 `WSB_S1_C0_FROZEN_SYNC_20261117` 中列出）

| 差异 | v2 做法 |
|---|---|
| 1. 只转发 token 总数 | 读取时把状态中实际已读的 ReadingView（序号 1..n，按读取顺序）传给 A 的无状态 `Reader.read(head, acquired=...)`；`input_tokens_before` 必须与状态一致 |
| 2. 静态 unit_tokens 掩码 | GET 是否合法 = 静态规则 **且** A 的 `action_mask(acquired)`（按完整 chat template 实测容量）；静态掩码只作诊断并报告分歧。对每个被屏蔽的头单独探测，结果不进入环境状态 |
| 3. ready_at 边界 | 个人资源 `ready_at.session_rank ≤ cutoff` 可读，大于 cutoff 拒绝；`reported_at` 和来源 rank 仍必须严格早于切点，日期不得晚于前缀日期 |
| 4. 身份写成 unbound | TerminalKey 用真实的 `Reader.identity`；身份中出现 `unbound*` 时直接拒绝运行 |
| 5. RS 案例冒充方法目录 | RS 只按外部 train 案例核对：无 owner、来自 ESConv train、family 与前缀谱系不相交、每个跨度对 ESConv 原文核验通过。不当作方法目录 |

## 2. 结果（24 个前缀）

两次运行得出同一组结论：
- 正式运行用 A 的 PrefixPort，基于 `a26998f0`，耗时 98.7 秒；
- 交叉核对用 B 的适配层，基于 `a0771e1e`，耗时 218.8 秒。

两者的 24 份逐前缀报告**每个字段都完全相同**，所以 A 两次提交之间对 Reader 的重构没有改变可观测的读取结果，两种端口实现也一致。

| 项 | 结果 |
|---|---|
| 通过全部检查 | **24/24** |
| 可达子集数 | **16 个：21 个前缀；8 个：3 个前缀** |
| 不可达原因 | 3 个前缀的 MP 为 `unavailable:no_legal_candidates`（第 2–4 折的 early 段前缀：过去会话里没有合法的 MP 记录） |
| 各头有合法候选的前缀数 | RS 24、MP 21、ME 24、MS 24 |
| 合法候选数中位 | RS 875、MP 4、ME 28、MS 8.5 |
| 单头阅读 token 中位（Gemma 原生） | RS 1,318、MS 713.5、ME 113.5、MP 95 |
| 前缀基础 prompt | 122–1,002 token |
| 四头全读后的输入 | 2,249–4,520 token（原生 context 262,144，输出预留 320） |
| ready_at 恰好等于 cutoff 的已交付记录 | 21 条（与集成负责人统计的 21 次等号边界一致，现在均判为合法） |
| 正常容量下静态掩码与动态掩码的分歧 | 0 |
| 终点 | 全部 pending：没有 Generator 输出，没有填写任何奖励 |

**每个前缀实际检查的内容**：

1. **从初始状态对四个头逐一真实 GET**：availability>0 时，读取只允许因容量被拒，availability=0 必须对应读取失败；失败的读取不改变 token 数。
2. **来源核对**，对每条交付的记录：
   - bank 版本、头和视图；
   - owner：个人资源必须属于本 owner，RS 必须没有 owner；
   - 时间：来源 rank 和 reported_at 严格早于切点，ready_at 不晚于切点，日期不晚于前缀日期；
   - family 闭包：个人资源在闭包内，RS 与之不相交；
   - 每个来源跨度都通过 `verify_legal_span`（RS 则对 ESConv 原文核验）；
   - 阅读正文必须包含引用的原文；
   - token 数等于 Gemma 原生计数，且不超过原生容量。
3. **完整终点身份**：
   - 每个可达子集只有 1 个 TerminalKey，而 ExecutionTrace 的条数等于 k!（共 65 种顺序时就有 65 条）；
   - 不同顺序下，阅读内容和子集的总输入 token 都相同（单个头的计费增量会随顺序变化，这是预期的）；
   - 每个规范顺序的 key 都由 A 的 `reader.replay(key)` 重放，记录组、正文和 token 都一致。
4. **pending 语义**：
   - 终点表为空时，所有 STOP 都抛 PendingTerminal；
   - 终点表只有 OFF 时，只有 OFF 有奖励。
5. **重复回放**：第二轮从磁盘**独立重新加载** registry 和 bank，并新建 tokenizer 实例；record id、正文哈希、token、key 和 trace 与第一轮完全相同。

## 3. 容量压力检查（诊断用，有独立的 renderer 身份）

- 设置：每个前缀把容量设为"基础 prompt + 四个头单读计费的中位数"。
- 结果：
  - 24 个前缀全部通过，可达子集为 3 或 4 个；被屏蔽的原因都是 `capacity`；
  - 在**真实记录**上验证了"被拒绝的读取不推进状态"：先用只看静态规则的环境去读一个会因容量被拒的头，读取被拒绝，状态对象不变；下一次成功的读取仍然拿到序号 n+1（24/24）；
  - 在这个容量下，静态掩码与动态掩码没有出现分歧。两者确实会出现分歧的情形由程序化 fixture 覆盖（一次性外层包装开销）。

## 4. 测试

`tests/test_rl1v3_b5_bank_replay_v2.py` 共 21 项：

- fixture 18 项，覆盖 12 类故障：
  - 外部 owner；
  - ready_at 晚于切点；
  - RS family 与前缀谱系重叠；
  - RS 不是 train 案例；
  - 阅读正文没有包含引用原文；
  - token 数与原生计数不符；
  - availability 为 0 但读取成功；
  - 有合法候选却被拒绝读取；
  - 回显的输入 token 与状态不符；
  - 掩码隐藏了可读的头；
  - A 侧重放结果不同；
  - 新建 port 后回放漂移。
- 真实 bank-v0 3 项：读入 A 已提交的 registry 和 bank，tokenizer 只是测试用的按字符计数；包括篡改 ready_at 和 owner 后能被检出。
