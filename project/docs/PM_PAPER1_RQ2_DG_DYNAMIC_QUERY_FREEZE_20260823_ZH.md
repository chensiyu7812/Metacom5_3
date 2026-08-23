# Paper-1 RQ2 DG Dynamic Query 机械冻结

状态：`FROZEN`。本文件只冻结 ES-MemEval Dialogue Generation 的 query 文本、调用时点和重复检索计划，不冻结 MP/MS/ME bundle 数量，不打开任何 outcome lock。

## 机械依据

基于已固定的 `slptongji/ES-MemEval@692624208acc077b8867698c1d6fcd998dee641a` official harness：DG 共 10 个 interaction rounds。每轮先生成 seeker utterance 并加入 supporter room，然后 official RAG 在生成 supporter response 前调用 `session_history[-1].text()`；此时最后一条消息正是本轮刚生成的真实 seeker utterance。检索每轮重新执行，而不是在整段对话开始前只执行一次。

## 冻结内容

- 调用轮次：1 至 10，每轮一次，共 10 次；
- 调用时点：本轮 seeker utterance 已写入可见历史、supporter response 尚未生成；
- query：本轮当前 seeker utterance 的 exact text，仅这一条；
- schedule：每次 supporter generation 前重新检索；
- 禁止静态 pre-generation query、未来轮次、gold/reference/outcome、seeker simulator 隐藏字段进入 query；
- PM/retriever 只可再使用既有 authority 允许的 outcome-blind eligible-candidate raw observables；
- Step2 不增加 utility filter。

## 未在本文件冻结

typed bundle 的 task-specific 数量与 token budget 仍必须经过 outcome-isolated calibration；Generator、Step2、features、folds 与完整 full-stack identity 仍按 active authority 逐项冻结。本文件不改变 official RAG Top-4 baseline 的 session-granularity per-round dynamic retrieval。

本次读取 outcome=`0`，调用 outcome=`0`，PM training=`0`，formal ES-MemEval=`0`；四把 outcome lock 均保持 `CLOSED`。
