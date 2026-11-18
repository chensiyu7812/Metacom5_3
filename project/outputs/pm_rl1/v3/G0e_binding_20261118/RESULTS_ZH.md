# G0e / B6e 身份绑定补充（CPU 联合验收）

本补充保留 PR #10 `73fdb12f29b6970a268eeda704d73e1bd35b1c3e` 全部代码、输入、冻结记录和 CI 证据；未合并 PR #10，未修改 EXECUTION_STATE。integration 基础为 `320a33d1d871199d171f998300ce926b341ca1a8`。PR #10 应由 integration owner 合入；本补充是独立分支，不向旧 PR 堆叠修改。

A 代码 `f7bc866f` 与 B PR #11 `0af8d35e2d5f91c15705f5056de31da279f77f11` 在独立、未推送的联合工作树合成 `3cf1661d558238238515a811de3f879e8616ba87`，调用 B 的真实 `terminal_registry.ReplayBinding`、`TerminalRegistry`、`real_instances.make_env`。该提交仅用于联合验收，不是正式 integration。

## 正式端口及身份

入口 `metacom_pm.rl1v3.generator.g0e_port.make_port_factory(root=repo)`，返回的 `G0ePrefixPort.protocol` 为 `pmrl1v3-g0e-read-port-1`。`prefix(row)` 只接受 B0 的合法 owner/session/cut_turn/prefix_id；`for_prefix(prefix)` 固定本次可见前缀。

| 字段 | 固定值 |
|---|---|
| C0 / JSON | `pmrl1v3-contracts-0.2.0` / `pmrl1v3-json-1` |
| source | `sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02` |
| bank | `bank:02d0a4b1e62fd033c02b4fdc8e76d8796b285aa058cb59201aacde2c13ce8dd9` |
| index | `index:227cca582de991e1ef823e0122e842be7316bf4339acc73c88992870ff1846f3` |
| g_id | `G0e:b624c7c3f99ffe6b35eca29e2f93ea9e624e66b31303415e4b9c4b1bc4c6c07e` |
| renderer_id | `renderer:e04b6de4d78624db4379c25537b9e6f8571b00b4c4edee681c7b5b3e31bb3d27` |
| decode_id | `decode:de376c64c6da1bc02d0752811d8a0dffeec41f2bd9cf869a1e8c1af16f448069` |
| step2_id | `pmrl1v3-g0e-no-plan-1` |
| request protocol | `pmrl1v3-g0e-request-packet-1` |
| supplement protocol | `pmrl1v3-g0e-replay-binding-1` |

`port.identity` 包含 bank/index/renderer/step2/g/decode 六字段；完整 TerminalKey 另含 schema、domain=`finite_head_v1`、owner、prefix、runtime prefix hash、规范 GET 路径和逐动作 record 组。实际 GET 顺序单独保存在 ExecutionTrace。`binding` 固定模型、HF batch=1、系统提示、tokenizer、decode、输出缓存规则。G0e 是工程身份，不是 A7。

`availability()` 返回各头合法候选数量；`action_mask(acquired)` 再核对完整容量。`read(head, acquired=(), input_tokens_before=None, bank_version=None, index_version=None)` 返回 C0 ReadSuccess / ReadFailure。失败不发布 ReadingView、不消耗 ordinal。`base_tokens`、`output_reserve_tokens=320`、`native_context_tokens=262144`、`effective_context_tokens=16384` 是容量字段。

`request_packet(acquired)` 重新验证合法来源和实际 GET，返回 `payload()`、完整 key/trace 和 token 账。只有 `payload()` 的 messages / input_ids / decode 可送模型；私有 envelope 不能进入模型。完整原生输入长度与保守计费 `billed_input_tokens` 分开记录，B 环境的 input_tokens 使用后者。`replay(key)` 对所有版本和当前前缀严格匹配。

## 旧回放如何对应

旧 bank-v0 renderer 为 `renderer:e7678cc104e460d60e547d8e41debdd284ba519d903e35bd22c615f23e133010`，属于 tokenizer-only 回放。新 renderer 使用同一批成功 ReadingView，以规范 RS/MP/ME/MS 顺序投影到 Notes 和固定 B0 系统提示。source/bank/index、阅读正文、来源跨度和原生正文 token 数均不变；请求 framing、renderer、g、decode、Step-2 变了，所以旧终点缓存不可复用。

```python
from metacom_pm.rl1v3.bank.v0_port import make_port_factory as old_factory
from metacom_pm.rl1v3.generator.g0e_port import make_port_factory
from metacom_pm.rl1v3.generator.replay_binding import rebuild_from_replay
old = old_factory(root=repo)
new = make_port_factory(root=repo)
prefix = new.prefix(b0_row)
packet, evidence = rebuild_from_replay(
    old.for_prefix(prefix), new.for_prefix(prefix), verified_old_terminal_key)
# packet.payload() 才是生成输入；当前未执行生成。
```

函数先用旧端口真实重放旧 key，再按对应子集通过新端口真实 GET；逐项核对 record 组、ReadingView、合法来源后才构造新 key。B 的 `ReplayBinding.replay_key_sha` 仅用于对照旧资源身份，既不替换新 key，也不写旧缓存。B 冻结的 `PLAN_V3_FROZEN.json` 原值保留；启动真实 B6e 前应引用本补充 manifest 的完整六字段，而不只补 g_id/decode_id。

## 实际联合结果

- 8 个固定前缀、8 个 owner；7×16 + 1×8 = **120** 可达子集，**471** 条合法顺序，全部通过。
- 所有新旧资源组/ReadingView 一致；120 个新 key 和请求身份独立，所有同子集合法顺序得到同一请求，trace 保留各自顺序。
- B 最新 RealInstance 环境中的 key、trace、计费与 G0e 请求一致；STOP **全部 pending**，没有填零。
- B registry 对每个新 key 完成 trace / plan identity / 旧资源组核对后，真实拒绝未冻结 Checklist 的登记。没有生成 Checklist、NeedCard、回复或 ER；测试用未写入的 response SHA sentinel 不是模型输出。
- 部分表被 B Oracle/OneShot 入口拒绝。没有训练实验。
- `KEY_BINDINGS.jsonl` 保存新旧完整 key、真实 trace 与 token 账；`ORDER_CHECKS.jsonl` 保存471条顺序；`CPU_REQUESTS_ONLY.jsonl` 是120份 CPU 输入材料，**不是120次生成授权**。
- 当前合法前缀白名单、成功 GET、私有 source_key/record/prefix ID 排除、OFF 无 Notes 和容量均实测；无 NeedCard、检查表、judge、oracle 或未来评测数据输入。

接口实现无需修改 B-owned 模块、C0 或32份 Schema。B 可以据此准备新的 B6e 调用 manifest；真实执行仍缺正式集成、本补充绑定审阅、真实 NeedCard/Checklist、J1 身份/负载和独立 GPU 实验授权。
