# G0e 初始工程身份与请求层（CPU 准备）

本任务基于正式 integration `320a33d1d871199d171f998300ce926b341ca1a8`，新分支 `pmrl1-v3/ws-a-g0e-cpu`。PR #8 已合入（merge `b591863e4439014872dd076c72b20b99983a52e4`）；不向旧 PR 堆叠。C0 0.2.0、32 份 Schema、B 业务代码及旧 bank/renderer 保持原样。未更新全局状态、H0 或 main。

这是 `pmrl1v3-g0e-1` 工程候选，尚非 A7 正式研究 G0。模型按方案先选现有 Gemma，未依据资源增益挑选。尚未加载权重、生成回复或运行判官。

- Gemma-4-12B-it 完整 revision：`707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`。
- 权重 23,919,549,408 bytes；SHA256 `5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d`。复用既有 A0 字节审计并核对文件大小；本轮没有重新扫描权重。实际 GPU 加载前脚本要求重新校验所有权重 SHA。
- tokenizer、配置、chat template 文件 SHA 与 A0 attestation 一起保存在 `project/configs/rl1v3/G0e.json`；本轮重新核验小文件。原生 tokenizer 身份 `native-tokenizer:79ff7ef649a97ffd84dc42f243db15a3ca7bc1eea618a9f9454e4f37942a8c92`。
- 系统提示复用 A0 100 条 OFF 的 `pmrl1v3-support-B0-1`。资源 Notes 放在 system 后，固定 RS→MP→ME→MS，全文转义并明确为外部数据。
- 固定 no-plan Step-2：`pmrl1v3-g0e-no-plan-1`。没有私有计划生成。A7 的 SupportPlan 对照尚未开展。
- greedy、seed=0、非 thinking、max_new_tokens=320、EOS=[1,106,50]、pad=0、suppress=[258883,258882]。HF bf16/sdpa，固定 batch=1，启用确定性算法、禁 TF32；运行环境版本纳入身份。不声称跨 backend/硬件逐位相同。
- 原生 context=262144；初始运行上限=16384，含完整输入和 320 输出保留。绝不截断输入补齐。

HF G0e：`G0e:b624c7c3f99ffe6b35eca29e2f93ea9e624e66b31303415e4b9c4b1bc4c6c07e`。
Renderer：`renderer:e04b6de4d78624db4379c25537b9e6f8571b00b4c4edee681c7b5b3e31bb3d27`。
Decode：`decode:de376c64c6da1bc02d0752811d8a0dffeec41f2bd9cf869a1e8c1af16f448069`。
请求协议：`pmrl1v3-g0e-request-packet-1`，新增输入 Schema 在独立目录 `project/schemas/rl1v3_g0e/`。

## B6e 调用

```python
from metacom_pm.rl1v3.generator.g0e_port import make_port_factory
factory = make_port_factory(root=repo, backend="hf")  # 只加载 bank 和 tokenizer
prefix = factory.prefix(b0_or_coverage_row)
port = factory.for_prefix(prefix)
off = port.request_packet()
read = port.read("ME", acquired=(), input_tokens_before=port.base_tokens)
# 先检查 isinstance(read, contracts.ReadSuccess)，失败没有 reading。
packet = port.request_packet((read.reading,))
model_input = packet.payload()     # 唯一可交给模型的投影
private = packet.private_envelope()  # 终点身份/轨迹/计费，只供执行器与审计
```

`payload()` 仅有 messages、原生 input_ids 和固定 decode。PrefixSpec 只投影 role/text；成功 ReadingView 只投影 head/reading_text。NeedCard、Checklist、判官、oracle、候选分数、record/source/owner ID 和未读取正文没有进入投影。私有 envelope 明确分开，禁止整体发送模型。

B 环境使用 `TerminalIdentity(**port.identity)`、`read_takes_acquired=True`、`dynamic_mask=port.action_mask`，容量取 `port.effective_context_tokens - port.output_reserve_tokens`。`packet.key` 必须等于 B 环境的 `env.terminal_key(state)`；实际调用用 payload，缓存以完整 key + request SHA + runtime binding SHA 隔离。

旧 `bank.v0_port` 继续服务既有 B5 回放。source/bank/index 不变；新提示与生成 runtime 会产生新的 renderer/g_id 和 TerminalKey，这是显式新版本，不能套用旧终点缓存。相同资源 ReadingView 的正文、来源与 ordinal 语义不变。

## 真实 CPU 案例

固定开发前缀 `0ebfd29108ab51e0db08f404cfb56a518a28c31fd46c83c4d84b73f0428e3893`，按可得性选择，未参考任何终点评分。

| 条件 | 原生输入 token | 输出保留 | 总 context 上界 |
|---|---:|---:|---:|
| OFF | 418 | 320 | 738 |
| ME-only | 668 | 320 | 988 |
| RS-only | 1658 | 320 | 1978 |
| ALL | 2771 | 320 | 3091 |

`REQUEST_EXAMPLES.jsonl` 保存四个完整输入、私有 key/trace 和全账；`ORDER_REPLAY.jsonl` 验证 16 个子集/65 条合法读取顺序。请求身份不包含实际轨迹顺序，轨迹另存；同子集不同顺序的原生输入和请求 SHA 相同。OFF 无 Notes、无额外资源。

`g0e_b6e_cpu_check.py` 直接使用 B 的未修改 C0FiniteHeadEnv，对固定 coverage 中 fold 1–5 的 20 个开发前缀逐顺序检查 key、轨迹、计费和 pending；统计见 `B_ENV_SUMMARY.json`。这不是重新抽取 B6e 120 个终点，也没有运行 Generator。

## 失败与缓存

未授权/未运行不写 generation outcome。空回复、超时、OOM、异常和 320-token 技术截断不当成功回复、零奖励或认证结果。自然 EOS 的非空回复才可作为完成缓存读取；评价仍 pending。失败尝试保留但不命中成功缓存，不自动重试。缓存文件 write-once，并校验完整内容、终点与运行身份。CPU 测试中的示例输出明确是 fixture，未保存为真实模型产物。

本轮修复了私有 ReadPlan 与公开 ReadingView 的计费适配；公开入口继续拒绝 plan、失败对象和伪造 view。首轮测试用了 C0 不允许的 stratum 字面值，修正测试 fixture 为合法 `both`，保留断言。初始 batch 配置候选由可变上限改为 G0e 固定 batch=1；旧候选与失败日志另存，未改写历史结果。最终验证及提交/CI 见本轮 `VALIDATION_ZH.md`。

GPU 运行、正式 A7、A4 方法卡、A5 混合召回、A6 bank-v1、G1 训练均未完成。
