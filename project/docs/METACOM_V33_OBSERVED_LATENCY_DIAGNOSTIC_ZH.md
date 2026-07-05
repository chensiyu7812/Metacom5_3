# MetaCom V3.3 EvoEmo 生成日志延迟诊断

更新时间：2026-07-05  
状态：no API 诊断完成  
数据来源：`outputs/evoemo_selective/turns.jsonl`  
结果文件：

- `outputs/evoemo_response_v4/observed_latency_diagnostic.json`
- `outputs/evoemo_response_v4/observed_latency_diagnostic.md`
- `outputs/evoemo_response_v4/observed_latency_by_condition.csv`
- 复现脚本：`scripts/17m_analyze_evoemo_observed_latency.py`

## 1. 这是什么

这是从 EvoEmo selective generation 的既有生成日志里复算的在线延迟诊断。每一条 turn log 里已经记录了：

- `latency_ms`：从当前 turn 进入生成流程到 supporter response 生成完成的观测耗时；
- `generation_latency_ms`：生成器 API 调用耗时；
- `retrieval_latency_ms`：资源检索耗时；
- `pm_inference_ms`：PM 推理耗时；
- `pre_evidence_compute_ms`：证据执行前的本地计算耗时；
- `retrieval_calls`：检索调用数；
- `total_input_tokens` 与 `output_tokens`：生成器 token 规模。

因此这不是重新跑实验，也没有新增 API 成本。

## 2. 能不能写进论文

可以写，但应作为：

> observed online latency diagnostic

不应写成严格的 randomized latency benchmark。

原因是：

- 原始 generation 不是专门为延迟 benchmark 随机化设计的；
- API provider scheduling、网络状态、响应长度波动都会影响延迟；
- 不同 condition 的运行顺序可能带来系统性噪声；
- 这些日志不包含 judge、训练、统计分析耗时，只代表生成阶段。

因此论文中应把 `mean input tokens` 作为主资源成本指标，把 latency 作为部署相关的补充诊断。

## 3. 核心结果

下面只列与 V4 response quality 图一致的核心条件。每个 condition 都有 1020 个 turns。

| Condition | Mean latency ms | Median latency ms | P95 latency ms | Mean input tokens | Mean retrieval ms | Mean generation ms |
|---|---:|---:|---:|---:|---:|---:|
| Context Only | 665.0 | 546.4 | 1100.1 | 393.0 | 0.0 | 652.5 |
| Learned Selector | 1952.5 | 1969.4 | 2627.2 | 1291.8 | 1214.1 | 723.2 |
| Rule Selector | 3226.2 | 3274.7 | 4075.9 | 1624.0 | 2435.7 | 783.8 |
| Fixed All Structured | 2015.3 | 1975.5 | 2602.7 | 1651.3 | 1264.5 | 743.8 |
| Session Retrieval | 2170.5 | 2079.0 | 2978.9 | 3236.7 | 1271.0 | 892.3 |
| Full History | 2402.6 | 2360.2 | 3054.9 | 14076.2 | 1279.6 | 1115.6 |

额外诊断：

- Learned Selector 的 PM 推理耗时均值约 `8.1 ms`，相对 retrieval 与 generation 很小；
- Learned Selector 比 Context Only 慢，这是合理的，因为它会调用额外证据资源；
- Learned Selector 的观测均值延迟低于 Rule Selector、Session Retrieval 和 Full History；
- Rule Selector 的 token 数不算最高，但观测延迟最高，说明延迟不只由 token 数决定，也受在线检索路径影响；
- Full History 的 token 成本最高，但观测延迟未最高，说明 provider 调度与生成长度也会带来噪声。

## 4. 论文写法建议

安全写法：

> We use mean input tokens as the primary resource cost metric. In addition, we report observed online generation latency from EvoEmo generation logs as a deployment oriented diagnostic. The learned selector has lower observed mean latency than the rule selector, session retrieval, and full history baselines in this run, while PM inference itself adds only a small local overhead.

不应写：

> PM is universally faster than all baselines.

不应写：

> This is a controlled serving latency benchmark.

## 5. 解释边界

这组结果支持的是部署可行性层面的补充观察：

> PM 的额外推理开销很小，主要成本来自检索和生成。相对更保守或更重的资源策略，PM 在本轮 generation log 中同时降低 token 成本和观测生成延迟。

它不替代 V4 response quality，也不替代 sampled audit。论文主线仍应是：

1. response quality 与强 baseline 接近；
2. token cost 更低；
3. sampled audit 中资源风险有可解释差异；
4. latency 作为实际部署时的补充证据。
