# Paper‑1 Generator 退役与本地 backend 修订（2026‑09‑03）

## 结论

原先冻结的 NVIDIA hosted NIM `meta/llama-3.1-8b-instruct` 已无法继续使用：2026‑09‑03 获取到的 `/v1/models` 目录包含 81 个模型，但没有该模型；随后对完全相同 model ID 发出的唯一一次正式 QA/No‑Memory 流式探测返回 HTTP 410。410 是确定性的资源退役响应，因此没有重试。

这发生在 formal outcome=0、PM training=0、四个 outcome lock 全部 CLOSED 的阶段。为保留原先选定的模型而不重新做结果导向的模型搜索，Paper‑1 将 Generator backend 版本化修订为：

- 模型仍为 Llama‑3.1‑8B‑Instruct；
- 本地 A6000、BF16、greedy decoding（`do_sample=false`）、单并发；
- `torch 2.3.1+cu121`、`transformers 4.57.6`、`aiohttp` 流式 reference server；
- 模型文件、tokenizer、实际 chat template、服务协议和 request messages 分别绑定哈希；
- 不把旧 hosted NIM latency 与本地 latency 合并，也不声称二者的未公开内部 chat template 相同。

## 为什么这是最小变化

本地下载使用此前 tokenizer 已经采用的 `NousResearch/Meta-Llama-3.1-8B-Instruct` 固定 revision `d10aef…`。四个 safetensors 权重分片的 SHA‑256 与 Meta 官方 `meta-llama/Llama-3.1-8B-Instruct` 仓库逐分片完全一致，模型权重没有改变。变化的是 serving backend 和现在可以明确冻结的本地 chat template；这一变化必须在方法与复现材料中如实报告。

相比改用 Nemotron、视觉 Llama 或重新选择其他模型，本地同权重迁移最少改变原先 RQ0 的 Generator 选择。由于尚无正式结果，它不会形成“看结果换模型”的污染。

## 首次 reference-client pilot

已运行一个不读取 capability outcome 的小型 pilot：

- QA、Summary 各取一个 `ALL_k4` 资源长度中位数目标；
- 每个目标比较 OFF、MP‑k4、ME‑k4、MS‑k1、ALL‑k4；
- 1 次 cold 请求，20 次 warm 请求；warm 为两个随机化相邻 microblock repeats；
- concurrency=1，使用同一客户端 monotonic clock记录发送到首个可见文本与完整文本；
- 21/21 完成；每个 task×configuration 的两次 warm response hash 一致；
- 只保存 response SHA‑256，不保存或评价回复文本；
- 本地 pilot 付费 API 成本为 `$0`。

这批数据只能证明采集链和本地 deployment stack 可工作。每个 warm cell 只有两次请求，且没有 RS、动态 DG、真实在线 BGE 检索和 PM/packing，因此其 p95 不进入 runtime allocator，也不能支持论文中的稳定 latency claim。

pilot 暴露了一个必须在正式 lookup 中保留的事实：输入更短不保证 completion 更短。此次 OFF 请求多次生成到 256-token 上限，而部分 ON 请求较早停止。因此：

- TTFT 主要反映 prefill、调度和首个可见 chunk；
- completion 同时受输入长度和生成停止长度影响；
- task 的固定最大输出上限是 pre-call identity；
- 当前请求实际生成了多少 token 是 post-action 变量，禁止拿来决定当前 ON/OFF；
- 正式 latency lookup 要从独立 zero-outcome timing data 学到这些分布，而不是假设 latency 只随输入 token 单调增加。

## 预算

hosted 退役探测因 NVIDIA 没有可审计的公开 token tariff，按 reservation 最大值保守计入 `$0.01`。研究者本轮批准的 timing-pilot 上限是 `$1.00`，剩余 `$0.99`；Paper‑1 累计保守记账从 `$1.15721901` 变为 `$1.16721901`。本地权重下载、A6000 推理和该 pilot 不计付费 LLM API 成本。

## 下一步

在 latency lookup 能进入 allocator 前，还需：

1. 补齐 RS 与动态 DG；
2. 对每个冻结的 context/resource token bin 抽多个目标；
3. 在看正式 timing distribution 前冻结重复次数；
4. warm 为主、cold 单报；
5. 把 PM、query embedding、retrieval、packing 和流式 Generator 放进同一个 client clock；
6. 保留 timeout、fallback、finish reason、output cap 和真实停止长度；
7. 继续把 60 秒作为研究者声明的灾难性完成时间上限，而不是把小 pilot 的任何数值升级成新的自设“通过门”。

2026-09-04 复核纠正：这里曾把旧项目的 NVIDIA Mixtral/Qwen fixed-seeker 扩展误写成 Paper-1 官方 DG seeker。固定的 ES-MemEval 源码实际上在所有 DG executable 中把 seeker 绑定为 `gpt-4o`；Mixtral/Qwen 是否仍在 NVIDIA 目录与官方 DG 主路线无关。正式 DG 仍需冻结 GPT-4o 的确切 snapshot、一次逻辑调用的物理尝试规则和费用，但不再寻找所谓“官方 Mixtral 替代品”。详见 `PM_PAPER1_OFFICIAL_DG_SIMULATOR_AND_COST_AUDIT_20260904_ZH.md`。

机器可读 authority：`project/data/paper1_authority/paper1_generator_backend_retirement_local_amendment_20260903_v1.json`。
