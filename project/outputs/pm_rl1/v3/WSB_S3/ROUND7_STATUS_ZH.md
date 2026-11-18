# WS-B S3 第 7 轮状态：对接 G0e，推进 NeedCard 试点到可执行门槛（2026-11-18）

- 证据等级：engineering_only。
- 本轮**没有**：GPU、模型生成、判官调用、真实训练、付费调用。
- 研究者的建议（20 次、不重问）**没有**被当作授权。

## 1. 集成

| 项 | 状态 |
|---|---|
| PR #10（WS-A G0e，head `73fdb12f`） | 集成负责人尚未合入（见第 7 节） |
| PR #11（本分支） | Draft；等 PR #10 合入后同步 integration、重跑回归和 CI，再转为可审阅 |
| 集成前演练 | 在本地把 PR #10 head 临时合入本分支（这个分支没有推送，已删除）：没有冲突；V3 共 564 项通过（含 A 的 24 项）；我的"PM/G 不得 import needs/checklist/judge"静态护栏与 A 的新模块兼容 |
| 没有修改的范围 | C0；A 的 bank、source、generator 业务代码；H0；main；PR #4；全局 EXECUTION_STATE；B2-v3 修复；v1/v2 历史；B1 计划 v1；B6e-v3 选样 |

## 2. G0e 终点身份重新绑定（`B6e_g0e_binding_addendum.py`）

- 新增的附录只写一次，**不覆盖** `PLAN_V3_FROZEN.json`、`REAL_KEYS_CHECK.json` 或正式 B5 的结果。
- 做法：
  - 用 A 的正式 `G0ePrefixPort` 和 `render.request_packet`，对 8 个已选前缀完整重跑 B5 v2 的全部回放检查；
  - 逐个终点重建 TerminalKey、ExecutionTrace 和请求包，核对 key、trace、计费和运行时上下文；
  - 检查发给模型的内容里，没有未来文本、私有 ID，也没有 NeedCard、检查表或判官内容；
  - 与旧回放身份对比：版本字段可以不同，记录组、正文和读数 token 必须完全相同；
  - 用旧 key 建的奖励表去查新 key，必须查不到；
  - 所有 STOP 保持 pending；
  - 可达数与预注册不一致就停止，不改写抽样方案。
- 演练结果（集成前、未提交）：
  - 8/8 通过；可达数 7×16 + 1×8 = 120，与预注册一致；
  - 变化的身份字段只有 renderer、Step-2、g_id、decode_id；
  - 资源对应关系 120/120 相同；
  - 新的输入 token 范围 137–4,340，上下文上界最多 4,660（运行时上限 16,384）。
- 演练中出现过两处 future_text 误报：两句支持者的固定问候语，既出现在可见前缀里，也逐字出现在之后的会话里。现在这类文本单独计数（每个前缀 0–1 段），不算泄漏；每个前缀其余 54–543 段未来文本都逐个检查过，均未出现在 payload 中。
- **正式结果**：等 PR #10 合入后在 integration 上运行，见第 7 节。

## 3. B2-v3 风险诊断（`B2/J1V3_CAPACITY_RISK_ZH.md`）

- 原子错误账本 v3 和全部反例测试保持不变、全部通过。
- 原定 J1 `max_new_tokens = 800` **明显不够**：
  - 13 项的检查表，每项都引一句时就超过 800；
  - 40 项时，即使只给判定也超过 800。
- 被截断后，贪心重问仍会被截断，于是所有项都记 uncertain，ER 拒绝计算，终点保持 pending。不会产生错误分数，但会**系统性**地让终点停在 pending。
- 已记录为尚未实测的容量风险，并提出了按前缀定额的 J1 解码方案（上限 4,096，超出则调用前阻塞，记录结束原因，不原样重问）。**未采用**；冻结的判官身份没有改动。

## 4. B1 试点（`B1/NEEDCARD_PILOT_V2_AUTH_REQUEST_ZH.md`）

- 新计划 v2 `b1d3225b…`：max_first_calls=20，max_retry_calls=0。在 GPU 环境中用 CPU 复核无问题，权重 SHA 也已核对。
- 原计划 v1 `9a43a79b…`（40 次）保留，仍能通过校验。
- **未运行，等研究者对其中一个计划给出独立授权。**
- 运行后用核查协议 v2：6 项检查与预注册完全相同；结论分为 valid、evidence_error、stratum_error、uncertain、writer_failed、pre_call_blocked。两道门：证据错误率 ≤ 10%，且 B6e 选中的 8 个前缀各有一张 valid 卡；任一不满足，B6e 暂停。

## 5. 逐卡核查结果

**还没有任何卡片**（writer 调用 0 次），因此没有有效卡、writer_failed、证据错误或层级错误的数据。

## 6. B6e / B8e

- 已为将来真实运行预先写好报告函数（`evaluate/b6e_report.py`），覆盖：
  - 终点的正常生成率和截断率；
  - J1 完整解析率和原子错误冲突率；
  - ER-v3 计算、拒绝、pending、安全失败的比例；
  - 按资源子集和需求层分组的拒绝率；
  - OFF 与 ME_only 对照的实际覆盖；
  - 12 格敏感性分析；
  - token、GET 次数、耗时、显存；
  - 完整终点表（只有它才能用于 DP_Oracle，或在不填零的前提下用于 PPO）。
- **B6e 现在不能申请授权**。未满足的条件：
  - PR #10、#11 尚未正式集成；
  - G0e 的正式重新绑定尚未完成；
  - A0 尚未实测；
  - 20 张 NeedCard 尚未生成、尚未核查；
  - 8 张 valid 卡和对应的 v3 检查表都还没有；
  - J1 的输出容量风险尚未解决（800 不够，需要研究者批准新的解码方案）；
  - 研究者尚未批准 G0 和 J1 的调用额度。
- 已有的 FIXTURE 训练结果只是单元自检。

## 7. 正式集成结果（PR #10 合入后补充）

截至本次提交，PR #10 仍是 OPEN，最后更新于 2026-11-18T00:06Z；integration 仍为 `320a33d1`。因此以下步骤**尚未执行**，PR #11 保持 Draft：
1. 普通合入新的 integration；
2. 在 integration 上正式运行 G0e 附录（输出到 `outputs/pm_rl1/v3/B6e_plan/v3_g0e_addendum/`）；
3. 重跑 V3、完整 CPU 和 PR CI；
4. 转为可审阅。

本分支当前 head `10fccdf6` 的 PR CI（run 44212034419）已成功：
- V3：542 passed，0 skip、0 xfail；
- 完整 CPU：2,307 passed，63 个旧环境 skip，0 失败。
