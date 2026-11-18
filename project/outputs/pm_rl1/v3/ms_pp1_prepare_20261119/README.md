# MS-RAW / PP1 准备（2026-11-19，未授权运行）

- [中文差异报告](../../../../docs/PM_RL1_MS_PP1_PREPARATION_20261119_ZH.md)
- [PP1 运行前申请](PP1_APPLICATION_ZH.md)与[16 条精确清单](REQUEST_LIST_ZH.md)
- [owner 跨会话抽查](OWNER_CONSISTENCY_ZH.md)
- [独立的集成协调记录](coordinator/INTEGRATION_RECOMMENDATION_ZH.md)
- `B_REVIEW_STATUS.json`：原 B 回执 pending；这是 A 的追踪文件，不能当 B 批准。
- `cpu_v2/`：16 个原输入的重新分词/来源绑定、8 个 pending DP slot 和全部合法 RAW 审阅包。
- `OTHER_HEAD_QUALIFICATION.json`：MP/ME、RS、MS-SUM 单独维护，不阻塞 MS-RAW PP1。
- [复跑与边界](RUNBOOK_ZH.md)、[验证](VALIDATION_ZH.md)、`PRESERVATION.json`（459 文件不变）。

没有 Generator/GPU/Judge/研究训练/付费调用或 PR 合并。PP1 是程序试点，非资源效应检验。
