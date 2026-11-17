# A1 / A1b 正式分支接收与 CPU 验收（2026-11-17）

已在正式冻结的 C0 0.2.0 和 PR #7 合入后的 integration 上接收两个准备提交。当前只完成正式功能分支的代码接收与 CPU 验证，**不宣布 A1/A1b 已集成或 completed**；由 integration owner 统一验收、合入及维护全局状态。

## 提交与输入身份

- integration 基础：`8bcd326e5158482e3e4ad1760f82b117a58d1e2c`（PR #7 merge）；该最终 HEAD 实际 push CI [44106386903](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44106386903) success，355 V3 无 skip/xfail，完整 CPU 2120 passed / 63 历史 skip，integration-base 实际通过。
- C0 冻结记录：`d67f34ee35f3f69ee82e5973e4b31b6415a302d0`；其最终 HEAD push CI [44100003645](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44100003645) success。
- C0：`pmrl1v3-contracts-0.2.0` / `pmrl1v3-json-1`，共享文件集合 SHA256=`6262fdac86a611a13023736ec38711e2cf894b6af5fe4cde4be18e8f13490d82`。32 Schema、contracts/io 与冻结身份一致。
- PR #7 最终 HEAD：`baa6059fedcd9f40cc59d1cc1922bdc672de10d4`，PR CI [44104027013](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44104027013) success。其原始归档逐文件 SHA 作为本次输入，未改字节。
- 正式分支：`pmrl1-v3/ws-a-a1-bank-v0`，独立于旧 ws-a / 已集成 PR #5。
- A1：准备 `69a850c5f7746e62786c30e6d3a65262cac9ec44` → 独立正式提交 `7116b8bd430727cebe7fd05c328486bd9a4d1f99`。
- A1b：准备 `01a951143c740697736f396ff449b70e6c909a04` → 独立正式提交 `c9dd5aae7bff5262455fb6cc6942142a5abb35b9`；本轮测试精确绑定此提交。

cherry-pick 无冲突，44 个准备文件全部逐字节相同。没有重建来源/bank、重扫 64GB、覆盖旧准备报告或失败日志。旧报告中的未冻结、旧 CI marker 失败是历史实况；本目录是追加的正式接收证据，不修改历史时间点的描述。

## 当前基线实测

| 范围 | 结果 |
|---|---|
| 全部 `test_rl1v3_*.py` | 392 passed；0 skip/xfail/fail/error |
| `verify_v3_junit.py` | 通过；355 项已集成 V3 + 37 项 A1/A1b |
| 当前完整 CPU：Paper-1 + RL1 + V3 | 2225 passed；1 历史 skip；11 GPU deselected；0 fail/error/xfail |
| Schema 漂移 | 32 schemas checked |
| 文件所有权与冻结身份 | 共享 C0、B 代码/正式验收、全局状态、workflow 未改 |

本地 V3 耗时 46.34 秒，完整 CPU 500.25 秒。唯一历史 skip 是 `/home/chenzhi/paper1_runs/frozen_tokenizers/llama31_8b_instruct_tokenizer.json` 不存在，不算完整覆盖。GPU 测试由 `-m "not gpu"` 显式排除；没有修改测试、skip、xfail 或断言。命令、环境、XML、原日志、模块计数见 `validation/EXECUTION.json` 和 `TEST_RESULTS.json`。

本次最终证据 HEAD 的 PR CI 需推送后独立核对，归档在仓库外并在 PR / 集成交接中报告。不能用 C0 或 PR #7 的既有绿灯替代本 PR CI；本记录不预填 CI 成功。

## 实际接收的能力和已有实测

来源版本 `sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02`，共 401 个个人 MS-RAW 会话及 875 个 ESConv train 来源；84 个重叠 family 与 341 个非 train 来源已隔离。p13/p18 的 esc1198 共享 family 关联保留。全部 4119 个前缀身份沿用 B0；个人 ready_at=r+1 是逻辑会话结束边界，不是实测 writer 时间。

bank 版本 `bank:02d0a4b1e62fd033c02b4fdc8e76d8796b285aa058cb59201aacde2c13ce8dd9`，index 版本 `index:227cca582de991e1ef823e0122e842be7316bf4339acc73c88992870ff1846f3`。四头真实条目 MP 387、ME 1525、MS-RAW 401、RS 完整案例 875；合计 3188，3185 unverified、3 development_reviewed。没有 MS-SUM、方法卡、关系传播或已验证世界事实的宣称。

原准备阶段已测 16476 次 GET（4119 前缀 × 4 头）：15956 成功、520 次 no_legal_candidates，分别 MP 3610/4119、ME 4108/4119、MS 4119/4119、RS 4119/4119。此处接收并校验既有实测产物，没有伪称本轮重新运行全量读取。细粒度旧→新 ID、713→388 MP 差异、325 条排除原因、三条证据修复、repair/quarantine 状态及“存在/来源核验/进入 bank/实际读取”的分层统计保留在原 `A1b_preparation/ASSET_CONVERSION_SCORECARD.json` 与 migration.jsonl。

入口为 `sources.source_registry.build/load`、`bank.bank_v0.build/load`、`retrieve.search/read`、`Reader.availability/action_mask/terminal_key/replay`。原生 tokenizer 只读固定 tokenizer/config/template；没有加载模型权重或生成回复。最小调用例与 PendingTerminal 行为见原 `A1b_preparation/B_INTERFACE_ZH.md`。检索为确定性词面 v0，不能宣称 A5 的 BGE/BM25/RRF 或召回质量改善。

## PR #7 后续真实回放边界

已通过的 A 测试通过 C0FiniteHeadEnv 的 callback 接口读取真实 bank，但**不是 PR #7 新 BankPort 回放器的正式跨线验收**。新回放器仍须由 B 在正式合入后协调：

1. 把实际 acquired ReadingView 传给 A Reader，不能仅转发 token 总数。
2. 对齐完整 chat-template 动态容量与静态 unit_tokens 的 mask，并实际测试失败不推进状态。
3. `ready_at == cutoff_rank` 的已完成会话边界可读；reported_at/source 的严格过去仍要保持。
4. 使用真实 Reader.identity 绑定 renderer/G/decode/Step-2/bank/index，不能保留 unbound 配置。
5. 875 个 RS 完整案例不能冒充 B1 所需 MethodCatalog；B1/B2/生成尚未完成。

这些待办不以 fake ReadingView、占位方法目录、零奖励或伪造终点解决。本轮未修改 B0/B1/B2/B5 业务、C0 字段、全局状态、main、PR #4 或 H0。GPU、预训练模型推理、独立训练、付费调用均为零；完整 CPU 包含既有合成 optimizer 单元 fixture。
