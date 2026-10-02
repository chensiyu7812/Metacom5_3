# Paper-1 本地 full-pipeline latency pilot（2026-09-04）

状态：`COMPLETE — NOT ALLOCATOR ELIGIBLE`

本轮把上一版只测 Generator 的 reference client 扩成同一进程、同一 monotonic clock 的真实请求路径：部署前预载 2,312 个候选向量；收到请求后在 A4500 重新编码当前 query，分别重排 MP/ME/MS 三个候选池，执行固定 pilot action，渲染/pack 资源，构造 provider messages，再向本地 A6000 Llama‑3.1‑8B 发起流式请求。首个可见文本和最终文本都从最初收到请求的时点计时，而不是从 provider POST 才开始。这里冻结的是双本地 GPU、concurrency=1 的 reference deployment shape，不能与单 GPU 或 hosted latency 混报。

共 21 次：1 cold + 20 warm；QA/Summary 各一个 outcome-blind 中位资源长度目标，各含 OFF、MP-k4、ME-k4、MS-k1、ALL-k4，两次随机相邻 microblock repeat。21/21 完成，生成文本不落盘、不评分，只保留 hash、usage、finish reason 和时间；formal outcome=0、PM training=0、API cost=`$0`。

组件诊断：

- fresh query embedding + 三个 head ranking：中位 63.22 ms，范围 51.78–169.05 ms；
- 固定 action 分支：中位约 0.0013 ms；
- pack + request construction：中位 1.78 ms，范围 0.14–12.81 ms。

这证明“用户发出消息→检索/选择/pack→流式生成→最终文本”的同钟采集链已经工作，也说明上一版只测 provider 少记了中位约 68 ms 的请求前工作。但它仍不能进入最终 allocator：当前 action 是固定配置，不是假装存在的训练后 PM；每 cell 只有两次；只有一个 target/task；尚无 RS 和真正每轮变化的 DG。正式 lookup 会在 final k/cap 与 feature schema 冻结后分层取多个 target，并将真实 PM 系数推理加入同一时钟；这些是依赖清单，不是用准确率阻塞研究的自设经验门。

机器 authority：`project/data/paper1_authority/paper1_full_pipeline_latency_pilot_20260904_v1.json`。
