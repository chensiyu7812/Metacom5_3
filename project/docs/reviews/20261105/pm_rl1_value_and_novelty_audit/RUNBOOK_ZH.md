# 可行性审查的复核入口

本轮只读既有train/dev隔离资产和论文，新增本轮文档与审查产物；无模型调用、GPU加载、训练、付费评分或新人评。未改正式G、奖励、数据划分或旧自然支持退出决定。

在仓库根运行只读校验：

```bash
python project/docs/reviews/20261105/pm_rl1_value_and_novelty_audit/verify.py
```

核验旧42份来源文件及本轮产物哈希、1,261题的唯一键/owner split/CSV绑定、关键结构计数、固定15题来源及逐题审查绑定、旧人评摘要不变和官方PDF哈希。结果保存为[CHECKS.json](CHECKS.json)。这不是模型效果测试或答案资格认证。

`audit.py`是本次统计生成入口，使用标准库和CPU。它对输出使用独占创建，避免覆盖既有结果；已有产物时不要在同一目录重复执行。重算核对使用上面的只读脚本。

私有产物位于`project/outputs/pm_rl1/value_and_novelty_audit_20261105_v1/`，包括`SOURCE_MANIFEST.json`、`QA_SUMMARY.json`、`CITATION_SAMPLE_PRIVATE.json`、`CITATION_REVIEW_PRIVATE.json`、论文PDF/文本/下载记录及`OUTPUT_MANIFEST.json`。不把题目、gold或私有引用复制到公共文档或策略输入。

后续候选验收步骤见[报告第5节](RESULTS_ZH.md#5-怎样用小规模验收降低后续无意义投入)。这些是有待具体数据资格审查和生成前固定的方案，不是已完成效果或已改写主实验。
