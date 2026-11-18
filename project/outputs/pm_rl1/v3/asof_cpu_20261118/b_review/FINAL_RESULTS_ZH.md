# B 最终独立工程复核

最终复核绑定 `cpu_v3` 和 [FINAL_RECEIPT.json](FINAL_RECEIPT.json) 中四份实现文件、测试文件与产物的 SHA。此前 `cpu_v2` 之后增加了固定 SHA 的 snapshot loader，故 v2 代码绑定漂移检查失败的日志保留为中间过程，不能作为最终通过证据。

最终 **100 项 CPU 测试全部通过，0 failed / errors / skipped**。新增回归涵盖：同 ready 时 RAW→SUM 依赖顺序的批量重建和持久重启；私有 subject ID 拒绝；snapshot 固定 SHA 加载；即使重算内部哈希，改写 snapshot 仍无法通过外部固定 SHA。

另外使用不导入 A 编译器的 [独立产物检查脚本](verify_final_artifacts.py) 核对：

- PR #13 原54提案的完整副本、顺序、plan_job_id / prefix / subset / old_request 逐项不变，没有换样；结果为14 BLOCKED、16 ELIGIBLE、24 LEGACY_DIAGNOSTIC。
- 原83开发样本的 selected record 及所有18,578次候选出现记录保留；结果为23 BLOCKED、20 ELIGIBLE、40 LEGACY_DIAGNOSTIC。1,876为去重候选 catalog 数量，与出现次数不同。
- 120旧请求的 key / messages / 原生 token IDs 哈希保留；54新表示逐字使用相同证据和当前可见前缀，不继承旧结果。
- 65个真实时点快照与 B 独立 RAW oracle 相同；68个完整RAW会话、93条ledger；324条旧隔离MP身份和精确源跨度保留、替代rank均更晚，未恢复入bank。
- 五项人工审查保持 pending，并附完整原始RAW；全部真实ledger无 human_approved。RS四臂相同prefix与方法集合，METHOD+CASE仅附加案例，均不可执行。
- C0 contracts / io、32份Schema、全局EXECUTION_STATE与integration基线逐字相同。

这是独立 B AI 工程复核，不是人工语义审查、原WS-B owner正式采纳或研究级资源收益证明。时间仍是逻辑重放边界，模型抽取/生成、人工语义批准、新请求原生分词和资源增量质量保持 pending。
