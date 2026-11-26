# GSWS 日志时序修复：独立执行申请（未批准）

GSWS packages-v2 第1作业已实际加载模型一次，75.819秒后于首次生成前停止，模型调用0，解释0，终局0。其余3作业未启动；不把未执行计为语义失败。

根因：gsws_runtime.call 在捕获 start 后，让 EXPERIMENT_GUARD 记录自动采集较晚时间，再将较早 start 传给 MODEL_CALL_START。正式 MonotonicJournal 正确拒绝倒序。旧CPU替身只list.append，漏检正式写入器。

独立候选 packages-v3-clockfix 仅增加 EXPERIMENT_GUARD 的 stamp=start；CPU检查改用正式日志写入器。相对packages-v2仅上述两文件变化，语义任务、输入、来源、模型、解码、四作业分配、评价及停止规则不变。真实来源/Tokenizer/正式日志CPU路径已完成80个替身调用，0模型加载，不代表模型理解成功。

本申请不是沿用原授权。原用户明确只准输入修改，且0 retry；此次修复超出该范围，失败作业也已经耗用一次加载。需批准一次明确的技术恢复例外：新4作业最多80实际调用、4加载、0 warmup、包内0 retry、每包1200秒合计4800秒。连同已失败启动累计最多5次加载、总实际时间上界4875.819秒。原失败作业及原scope永久保留，不解锁、不覆盖；原2–4不另行启动。无重复生成，因为旧包生成0次。

仍用原A6000 UUID、Gemma revision、解释512/G320。新identity的进入检查不能代替研究者批准。任何再次技术失败保留并停止其作业，不自动产生下一修复运行包。

清单SHA256：`6a588886fec487d9f844572151e8633ce5f4ede5d351e3447af34eb66ce8be7b`

执行器inventory SHA256：`0c6ea9db553c51e7ed81eabbc84d2844a5f1db8c746c2bd9fb336b0c4e569a6a`

| 作业 | plan对象SHA256 | request文件SHA256 |
|---|---|---|
| GSWS-1 | `e6d04730c5c03c30b4325b5ee71f3288da6787255620f3c7a3f91fb2133c69a5` | `9405301013e72ed5aeea3afdc1e0b52b18a00ace17ab75a4696e1bbf97cd23be` |
| GSWS-2 | `6fe3b377de710b0562134d8cd885b4aa7f17a5fc1ef282981f3e64d5aea164ae` | `3c5aff7ff5aa6cc6df9aaf77109e018c5fd7352cf9fdc18cf1853f36251a7560` |
| GSWS-3 | `27e36218bfd117db3d7a4925316a98c132aa525b164eda91053cd2b8c9c9b8af` | `04142d6bafca9619c25a297b62866f4a6b3c169774060ace9ac2e32fa6b05166` |
| GSWS-4 | `9403ce5a5157fd07ee04fa0abba31b9111c161691c584de0e4fc2bf686a75dae` | `5159c2ae56ba967f92936d6d4732c9762d34446972b185cfc8afb23639f6cbda` |
