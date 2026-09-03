# Paper-1 官方 DG seeker 与成本审计（2026-09-04）

状态：`ZERO-OUTCOME SOURCE AUDIT COMPLETE — PAID EXECUTION POLICY PENDING`

## 核心纠正

固定的 `slptongji/ES-MemEval@692624208acc077b8867698c1d6fcd998dee641a` 并没有使用 NVIDIA Mixtral 或 Qwen 作为 DG seeker。所有 DG executable 都把 seeker 设为 `common_configurations.gpt4o`，后者对应 `gpt-4o`。Mixtral/Qwen 是本项目旧版为了让各 policy 共用输入而建立的 fixed-seeker 扩展；它们不是官方 benchmark 的模型依赖。因此，NVIDIA 目录没有这两个模型不会阻塞 Paper-1 的官方 DG 路线。

官方 10 轮协议如下：每轮 GPT-4o seeker 先读取隐藏 persona、全部历史摘要/事件、related-session 原文、topic、心理/身体状态和 more details，再读取本轨迹此前 supporter 回复，生成最多 60 tokens；新 seeker utterance 加入 supporter 可见历史后，本地 Generator 才回复。隐藏 scenario 字段不得进入 PM、检索 query 或 supporter prompt。

## 精确调用面

公开数据有 18 位 owner、34 个 subsequent-topic scenario。六个主要系统完整运行时：

- GPT-4o seeker：`34 × 10 × 6 = 2,040` 个逻辑调用；
- 本地 supporter：2,040 个调用；
- GPT-4o overall judge：204 个调用；
- 本地 Mistral-24B observation relevance：51,360 个调用；
- 本地 Mistral-24B observation usage：51,360 个调用。

最后两项合计 102,720，而不是旧预算文件误写的“五次 observation aggregation/trajectory”。官方代码实际对每个 scenario 的每条 related observation，在每个 turn 分别做 relevance 和 usage 判断。它没有 API 美元成本，但有很大的本地 GPU 时间成本，正式执行必须做可恢复、内容寻址、逐成功落盘的 runner。

## GPT-4o seeker 成本

用 `tiktoken 0.12.0/o200k_base` 对公开已知 prompt 精确计数，并对未来每条 seeker/supporter message 使用官方 60-token cap，再为每条 message 加 32-token serialization reserve。六系统一次物理尝试的 reserve 为 11,314,620 input tokens + 122,400 output tokens。

按 2026-09-04 OpenAI 官方 GPT-4o 价格（input `$2.50/M`、cached input `$1.25/M`、output `$10/M`）：

- 每个逻辑 turn 只做一次物理调用、全部按 uncached reserve：`$29.51055`；
- 全部 input 命中 cache 的敏感性下界（不是 hard reserve）：`$15.367275`；
- 完全照 upstream 的“non-stop 最多三次”且每次都走满：`$88.53165`。

因此，原先给“六个 RQ2 系统完整官方评价”预留 `$22`，与 upstream 三次尝试的最坏行为不相容；这不是模型效果问题，而是旧 call arithmetic 错了。实际 prompt caching 可能显著降低账单，但 hard-cap 不能把 cache hit 当作必然发生。

## 仍需在付费前冻结的单一选择

可复现模型候选固定为 `gpt-4o-2024-11-20`：它是公开仓库提交日之前最新的 GPT-4o snapshot，当前账户目录可用。相对官方移动 alias `gpt-4o`，这属于可复现性修订，不是换 evaluator family。

物理尝试规则仍有两个诚实选择：

1. 完全保留 upstream 最多三次生成；那么必须减少系统/场景或提高预算，不能声称 `$50` 内完整执行。
2. 每个 seeker turn 只调用一次，并将 `stop`/`length` 的接纳及完整句前缀规则作为 pre-outcome cost amendment 冻结。它保留官方 GPT-4o、prompt、10 轮顺序和 60-token cap，但不再称 bit-exact upstream runner。

推荐第 2 条，因为论文研究对象是 Policy Manager，不是比较 seeker 的随机重采样策略；一次共同冻结的规则适用于全部 arms，不根据结果改变。正式付费前仍要先做极小的 compatibility/cost pilot，并从原始 finish reason 报告长度截断率。当前没有发出任何 seeker/evaluator 调用，四把 outcome lock 均保持 CLOSED。

机器产物：`project/data/paper1_authority/paper1_official_dg_simulator_call_cost_surface_20260904_v1.json`。
