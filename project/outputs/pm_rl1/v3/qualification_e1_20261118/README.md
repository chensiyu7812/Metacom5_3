# WS-A E0/E1 资源资格交付（CPU，Draft）

主报告：[PM_RL1_E1_QUALIFICATION](../../../../../docs/PM_RL1_E1_QUALIFICATION_20261118_ZH.md)。本目录只新增证据，不批准研究资源或模型运行。

- [8 前缀绑定表](BINDINGS_ZH.md)；完整 `cpu_v3/BINDINGS.jsonl`、snapshots/frontiers/ledgers/readings。
- [SHA 交换规范](SNAPSHOT_HASH_SPEC_ZH.md)及 HASH_TEST_VECTORS；[复跑与 B 审阅入口](RUNBOOK_ZH.md)。
- SEMANTIC_REVIEW_DISPOSITIONS：64 条逐项 AI 预审，approved 0 / pending 43 / quarantined 21；实际 Reader 均不放行 MP/ME。
- [容量与可执行性](TOKEN_CAPACITY_ZH.md)；FINAL_EXECUTABILITY_MATRIX；72 提案位置，63 native previews，9 unavailable。
- QH_SOURCE_HANDOFF 位于 cpu_v3：条件无关的全部合法 RAW；Q0/QH/F 待 B 提案，不是评分器。
- RAW_CHAIN_COVERAGE 位于 cpu_v3；SYNTHETIC_MECHANISM 单独标示，不能冒充真实更正验证。
- [测试报告](VALIDATION_ZH.md)、VALIDATION_RECEIPT、PRESERVATION、REPRODUCIBILITY 和 BLOCKERS。
- coordinator/ 单独保留只读集成角色的审查、CI 核对、五项接口风险和推荐队列。没有合并授权。

旧曝光不自动排除正式评价；不允许根据正式测试结果改样本、指标或主要假设。额外确认数据按具体主张、统计精度与泛化需求决定。
