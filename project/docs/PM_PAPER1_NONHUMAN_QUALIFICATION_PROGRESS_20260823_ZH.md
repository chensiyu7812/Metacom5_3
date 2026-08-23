# Paper-1 非人评资格工作进展

状态：`LOCAL_NONHUMAN_WORK_COMPLETE_PENDING_EXTERNAL_OR_RESEARCHER_INPUT`。

本轮没有填写任何 human verdict，没有调用付费 API、Generator 或 evaluator，没有启动 401-session compile，没有读取或调用 outcome，也没有训练 PM。四把 outcome lock 全部保持 `CLOSED`。

## 已完成

1. V8 checkpoint 已作为独立 commit `5bc6509ba0426a0dfb6d20fed1264e58e0bb6607` 推送。
2. 对冻结的 old MP20 + ME12 DEV matrix 做了可复现 data-quality audit。v8 拒绝 11/12 个旧 FAIL/REVIEW，但只保留 9/20 个旧 PASS；主要失败来自 MP support relation 被压成布尔值，以及 ME semantic order 与 shared-span topology 混在一个 enum。该结果只用于 DEV 诊断，不能估计 full catalog 质量。
3. 完成 outcome-blind v9 离线 schema/gates/binding：Qwen 仍只输出 typed observations；formal verdict 完全由 deterministic code 得出。修复是 class-general 的，没有 item blacklist，也没有扩 ontology。
4. 按 pinned official ES-MemEval harness 机械冻结 DG dynamic query：每轮 seeker utterance 写入后、supporter generation 前，以当前 seeker exact text 作为 query；10 轮每轮重新检索。bundle amount 仍未冻结。
5. 完成 ESC-RANK 云端资产 attestor 与运行手册。本机 8192 MiB 仍不满足 >=24576 MiB gate，所以没有伪装成 runtime qualification 完成。

## 现在仍需外部输入的事项

- RS 64-item semantics qualification：需要真人 blind review，当前 0/64；在完成前不得运行 uptake。
- Memory v9 live DEV：需要研究者另行批准新的 API hard cap；v8 的 USD 0.25 授权不自动延续。通过后仍须停下审阅，不能自动跑 401。
- Memory held-out：依赖合格的 v9 DEV、另行授权的 401 compile、新 catalog 后冻结的新 IDs，以及真人 blind review。
- ESC-RANK：需要 >=24 GiB GPU 和 pinned snapshots。
- alternative evaluator：exact Qwen/DeepSeek/独立家族 identity 仍须研究者指定，并需要两名真人 reference ratings；不得由代码静默选择。

因此，当前本地可安全完成且不依赖人评/API/GPU 的主要资格工作已经关闭。剩余任务不是“再补一点本地代码”即可完成，而分别需要人评、明确的新 API 授权或 >=24 GiB GPU。
