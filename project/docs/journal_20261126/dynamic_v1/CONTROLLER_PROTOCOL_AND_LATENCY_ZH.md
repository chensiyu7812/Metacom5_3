# 动态控制器共同协议与单调时钟：CPU 实现记录

本轮基于 `f2d59f1c42de672c0785e034dbbd76e424f5529e` 新增实现，未修改 SC36、旧 POMDP 冻结模块或终局 G 配置。模型加载、模型生成、GPU、模型 API、训练均为 **0**。本文件只报告控制协议和计时基础的 CPU 检查，不能代替 88 次提案的独立准入、真实执行或任务效果。

**共同控制器协议**

[pomdp_controller_protocol.py](../../../src/metacom_pm/rl1v3/journal/pomdp_controller_protocol.py) 提供静态 `protocol_contract()`、`controller_decode()`、XGrammar 编译与 logits processor，以及独立的严格解析和状态合法性检查。`protocol_contract()` 和 [pomdp_latency.py](../../../src/metacom_pm/rl1v3/journal/pomdp_latency.py) 的 `latency_contract()` 可在纯 Python 3.11 中调用，不导入 torch、transformers 或 xgrammar。两份机器合同见 [CONTROLLER_PROTOCOL.json](CONTROLLER_PROTOCOL.json) 和 [LATENCY_PROTOCOL.json](LATENCY_PROTOCOL.json)。

| 层 | LLMOneShot | LLMToolAgent |
|---|---|---|
| 语法 | 1–5 个动作对象组成的数组 | 单个动作对象 |
| SEARCH | `action` 与非空 `query` 字符串 | 相同 |
| EXPAND | 整数 `from_search`（0–3）、整数 `hit_rank`（0 或 1） | `hit:` 加 24 位十六进制字符的 `handle` |
| STOP | 单字段对象；语法始终保留 | 相同 |
| 状态检查 | 至多 4 次获取；STOP 后不得有动作；引用此前计划中的 SEARCH；query 仅含初始可见词 | 当前 action mask、实际已观察句柄；query 仅含当前问题或实际已送达文本的词 |
| 输出上限 | 1 次 × 768 token | 至多 4 次 × 192 token |

词的定义直接复用既有 `temporal_retrieval.words`，包括大小写归一化；这是一项明确的词面来源规则，不是语义蕴含判断。grammar 只接收角色、tokenizer、词表大小和 EOS，不接任务、候选池、正确下一动作、来源引用或评价答案。它允许语法上正确但当前不可执行的动作；后者由状态检查明确拒绝。不得通过 grammar 为模型选中“正确行动”。

严格解析拒绝重复 JSON key、NaN/Infinity、bool 冒充整数、额外字段、围栏/思考文本、尾随第二个对象、非法句柄、越界引用和未观察 query 词。解析或状态失败不清洗、修复、替换为 STOP 或重试。合法工具返回的预算拒绝与控制器格式/状态错误属于不同运行事件，由动态执行器保留各自处理。

**原解码规则的实际 CPU 检查**

复用 SC36 隔离的 XGrammar **0.1.21**，只载入已固定 Gemma tokenizer/config，未读取权重。将原控制 system 文本与通用测试情境组成 native prompt，再逐 token 回放合法 JSON，检查 grammar 与 HF `NoRepeatNGramLogitsProcessor(3)` 的交集。固定测试包括两个角色、紧凑/带空格 JSON、STOP/SEARCH/EXPAND/四次获取程序，并分别检查 EOS **1、106、50**。

共检查 **36 条路径、488 个前缀**。原 `no_repeat_ngram_size=3` 在 **18 条指定合法路径中阻断 15 条**的预定下一 token；另外 3 条路径完成。system 中的 JSON 示例和已出现的 query 词也参与 n-gram 历史，因此格式与可见词复用受到影响。本次没有观察到全有限 logits 交集为空，不能把“指定路径受阻”写成“所有格式都死锁”。

在已确认的新共同控制协议中，两控制器均明确设为 **`no_repeat_ngram_size=0`**；其余基础 decode 原样复制，仅按角色改变既定输出上限。该设置下 **18/18** 指定路径经 EOS 完成。终局 G 仍使用原配置，包括原 `no_repeat_ngram_size=3`。这是新控制器身份的显式选择，不是运行中遇错后的 fallback，也不是对旧 SC36 的修改。

processor 对 grammar 与其他解码约束的交集执行有限值检查：任何 NaN、正无穷或零个有限合法 token 均立即抛出技术错误；不解除 mask，也不向全 `-inf` 向量执行任意 argmax。XGrammar 0.1.21 不提供 `is_completed()`；最终检查使用其实际 `is_terminated()`，或在未终止时检查 EOS bit 是否允许。JSON 已闭合但没有 EOS 仍不是已正常终止；控制器的长度截断仍由执行器按技术未完成处理。

另有 **9 项 native CPU 边界检查**：全负无穷、NaN、正无穷、多序列、JSON 前 EOS 禁止、完整 JSON 无 EOS、未完成前缀、EOS 后 token、被更换的前缀。普通 CPU 单元测试 **44/44** 通过，包括解析/来源边界、跨进程时钟和首文本观察。详细记录见 [PROTOCOL_NATIVE_CPU_CHECK.json](PROTOCOL_NATIVE_CPU_CHECK.json)。有限路径回放不证明整个 token 空间可达、真实模型会选择有效动作或任务能够完成。

**真实时间合同与观察边界**

`MonotonicClock.stamp()` 返回 `CLOCK_MONOTONIC`、Linux `boot_id`、整数 `monotonic_ns` 和 PID。只有同一 boot、同一时钟域的事件可相减；跨 boot、UTC、反向时间或 bool 伪装的数值均被拒绝。实际 CPU 子进程检查确认父子进程可在同一 Linux 单调时钟域比较。UTC 可以用于日志展示，不能计算时延。

监督器绑定 job/load 起止；动态运行时绑定 agent/PM、每次 controller、资源访问及 terminal 起止；worker 为每次真实生成附上首输出观察。这些时钟信息留在计量侧，不作为额外控制器观察，也不改变既有 NoText 策略的定义。NoText 仍不是新增 LLM 消融。

| 事件或量 | 实际含义 | 不能声称的含义 |
|---|---|---|
| `prompt_callback` | HF 将原 prompt 交给 streamer 的时点，通常在真正 prefill 之前 | prefill 完成或 prefill 耗时 |
| `first_generated_token` | callback 收到第一个生成 token，可为 EOS、特殊 token 或空白 | 已有可读/有效回答 |
| `first_non_special_token` | 首个不属于 tokenizer 特殊 ID 的 token | 已形成文字或语义 |
| `first_nonempty_decoded_text` | 累积解码出现非空白、非控制字符、非 U+FFFD 的字符；标点也可满足 | 已满足任务、内容正确或有帮助 |
| `semantic_text_validity` | 固定 `not_machine_qualified` | 自动认定首个“有效”语义片段 |
| `client_ttft_ns` | 固定 null；当前 worker stdout 只在最终回包发送 | 用户已经收到首段文本 |

`FirstOutputObserver` 作为被动 HF streamer，不重写 logits/token，不把观察文本再输入模型。但它会增加逐 token CPU 传输、同步和解码开销，**不能宣称零开销**。HF 的传输可能发生在 `put()` 之前，所以 `callback_work_ns` 仅记录 `put()` 内部；完整 generation 单调墙钟计入全部新增开销。所有比较臂采用相同 instrumentation；与历史未装 observer 的延迟不是同一个运行身份。当前仅做 CPU 接口检查，没有真实生成同一性或实测 GPU TTFT 结果。

同一 job 只计一次实际冷加载，后续调用共享已加载模型，不增加 warmup；共享加载与重叠区间不能重复相加或伪装成每题冷启动。当前比较关闭 terminal 结果缓存，不能用旧回复替代新生成或把缓存返回当推断时延。吞吐量推算、总时长除 token 数、CPU 回放耗时，都不能补出不存在的首 token、首文本或 client 时间戳。

**复跑**

纯 Python 边界测试：

```bash
PYTHONPATH=project/src /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  project/tests/test_rl1v3_journal_pomdp_controller_protocol.py \
  project/tests/test_rl1v3_journal_pomdp_latency.py
```

native CPU 检查使用 [journal_check_pomdp_protocol.py](../../../scripts/rl1v3/journal_check_pomdp_protocol.py)；必须给一个尚不存在的输出目录，避免覆盖旧记录：

```bash
CUDA_VISIBLE_DEVICES='' /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/journal_check_pomdp_protocol.py \
  --tokenizer-path /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 \
  --vendor-path /opt/tokkio-data0/tokkio_runs/pmrl1-j-selection-20261126/structured/packages-v3/executor/vendor_constrained \
  --out /tmp/pmrl1-dynamic-protocol-new-cpu-check
```

脚本本地编译 grammar、回放固定 token、检查 `torch.cuda.is_initialized()==False`，不调用 `generate()` 或加载模型。独立 admission 必须另外绑定最终模块、两份合同、依赖和请求身份；这些 CPU 结果不构成执行授权。
