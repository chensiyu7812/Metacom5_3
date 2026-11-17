# WS-B S1：同步正式冻结 C0 与工程框架复审（2026-11-17）

本次普通 merge 已将正式冻结的 C0 合入现有 `pmrl1-v3/ws-b-s1`，未改 B 业务实现、共享契约、B0、研究方案或全局状态。PR #7 保持 Draft，由集成负责人审核后决定转 Ready 和合入。证据等级为 engineering_only。

- 同步前 B：`107d618e4dd90f8c1267b7a1d35704f5127384f9`。
- 冻结 integration：`d67f34ee35f3f69ee82e5973e4b31b6415a302d0`；其最终 HEAD [CI 44100003645](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44100003645) success。代码验收 SHA 为 `b7dd11f674d92384416e0745b9982101965433dc`。
- 实际同步/本地测试代码：`dc2e493e5184aa638f78887f4656fbae1f25e887`，双亲为原 B HEAD 和冻结 integration，普通 merge 无冲突。
- 共享版本：`pmrl1v3-contracts-0.2.0` / `pmrl1v3-json-1` / `pmrl1v3-b0-prefix-census-v1`；Phase-1 为 `finite_head_v1`。
- 冻结共享身份：`6262fdac86a611a13023736ec38711e2cf894b6af5fe4cde4be18e8f13490d82`，32 Schema 加 contracts/io 共 34 个文件 SHA 全部一致。

## 实际测试

| 范围 | 通过 | 失败 | skip | xfail |
|---|---:|---:|---:|---:|
| 全部 V3 + JUnit 强门禁 | 355 | 0 | 0 | 0 |
| Paper-1 + RL1 + V3 完整 CPU | 2188 | 0 | 1 | 0 |
| Schema 漂移检查 | 32 | 0 | 0 | 0 |

CPU pytest 另明确 deselect 11 个 GPU 测试；唯一 skip 为历史 Llama tokenizer 路径 `/home/chenzhi/paper1_runs/frozen_tokenizers/llama31_8b_instruct_tokenizer.json` 不存在。未将该跳过算作完整覆盖。V3 耗时 18.32 秒，完整 CPU 耗时 471.73 秒。原始日志、XML、逐模块计数、命令及环境位于本目录。正式 B C0 验收保持 14 项，文件 SHA256 为 `ba9c1e3411ead9604a71c7907b289204be102fd8de6733e1343b7f84e220f6d2`；A 的独立验收文件仍独立保留。

本提交的最终 PR HEAD CI 尚须推送后单独检查；结果会在 PR #7 与集成交接中绑定最终 SHA。此处不以 integration 的 CI 替代本 PR 的 CI。

## 来源与接口只读核对

A 准备提交 `01a951143c740697736f396ff449b70e6c909a04` 的 registry 共 1276 条来源，其中 401 个个人会话与 B CensusSources 的日期、rank、dataset、family、正文角色及 transcript hash 零差异。全部 4119 个 B0 前缀的 prefix_id 与 runtime_sha256 均与 A registry 一致。B0 原 manifest 的 4 个输出哈希仍一致。A 资产只读载入，没有合入、修改或运行模型。

真实 bank 回放尚未运行，下列接入差异保留为独立后续修复项：

1. B `BankPort.read(prefix, head, input_tokens_before=...)` 仅传总数；A `Reader.read(head, acquired=...)` 需要实际已读 ReadingView，必须由适配器维护可回放的阅读上下文，不能伪造或仅转发 token 数。
2. B 静态 `unit_tokens` mask 与 A 完整 chat-template 加资源正文的计账不同，须按实际读后上下文核对容量及失败状态，不能假定单位开销恒定。
3. B 回放器目前对 `ready_at >= cutoff_rank` 拒绝；A 的已结束会话逻辑时点为 r+1，等于下一会话 cutoff 时可读，拒绝条件为 `>`。24 个 B 覆盖样本的 top-1 个人资源实际有 21 次等号边界，详见 INTERFACE_CHECKS.json；须协调检查边界，保留来源时间的严格过去要求，不改共享 C0 字段。
4. B 配置中的 renderer/G/decode/Step-2 仍是 `unbound-*`，接入应绑定实际 Reader.identity，不能与真实 bank 读取混用旧缓存身份。
5. A bank-v0 提供 RS 完整案例，未提供 B1 需要的 MethodCatalog；不得将案例或历史策略草稿伪装成已交付方法目录。

因此本次只接受 PR #7 的 B1/B2 框架、ER-v1 与 B5 回放工具，不能宣布真实 bank 跨线验收、NeedCard 生成、B1、B2、B6e 或训练完成。后续在 A1/A1b 正式集成后解决接口差异并运行真实回放；GPU/生成/训练/付费仍须独立授权。

## 失败记录与证据保存

- 原 `d0bde000` / `107d618e` 的 CI marker 失败和原报告均保留；本次继承集成负责人一行修复后完整 CPU 通过，未弱化或跳过 V3 测试。
- 本目录身份审计辅助脚本首次把仓库根目录层级写错，产生 FileNotFoundError。仅修正该证据脚本的路径层级，保留 `interface_checks_initial_path_error.log`，重新执行后来源/身份全部通过。没有业务代码或 pytest 失败。
- 冻结最终 HEAD CI 的 9 个文件从集成负责人证据目录复制并逐字节比对，存于 `frozen_integration_final_head_ci/`；其 CI 为 V3 287 通过、完整 CPU 2052 通过及 63 个旧环境 skip，不能当作本地完整覆盖。
- 没有模型推理、GPU、付费调用或独立训练实验；仅运行既有 CPU 测试中的合成 fixture 和 optimizer 自检。
