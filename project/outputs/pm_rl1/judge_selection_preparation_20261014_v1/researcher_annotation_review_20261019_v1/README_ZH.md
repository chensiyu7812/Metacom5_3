# 2026-10-19 单人标注分析包

先打开 [研究判断与逐题分析](RESEARCHER_REVIEW_ZH.md)。

- [全部作答与英文回复附件](ANNOTATIONS_AND_SOURCES_ZH.md)：逐字段保留八条原答案、实际网页中文译文和原规则。
- `sources/`：四份完整合法英文上下文及原题卷；不含封存标签。
- `originals/`：用户原提交JSON、实际填写的researcher.html字节副本。
- `annotation_scores_unchanged.csv`：原分项和绑定；q范围未转换，无新正式U。
- `intake_receipt.json`、`validation.json`：身份、原文与保留记录核对。
- `provenance/`：两项后续说明、旧状态、文件哈希；分析不计独立人评。

唯一真实评审者为研究者本人。仅用于本地开发参照与讨论，没有新增模型调用，累计120及原STOP保持。不应把本包当作裁判合格、正式验收或训练授权。
