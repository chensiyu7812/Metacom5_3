# 本地裁判比较结果（2026-09-17）

先读 [结果报告](结果报告.md)，再用浏览器打开 [逐题审阅](逐题审阅.html)。页面可按任务筛选、搜索题面，展开原回答、四种配置、换序理由及完整历史对照。

- `base80_reference_and_judges.csv`：80 对基础题的参照与裁判结果。
- `summary_evidence_diagnostic/summary13_evidence_and_completion_comparison.csv`：三配置 × 13 对 Summary。
- 各模型目录：原始请求、身份、逐条输出、停止原因和版本快照。
- `execution_summary.json`：822 条计划内记录、被纠正配置及中断消耗的汇总。
- `topk_preparation/`：候选盘点，尚未选择 k*。
- `repository_files/`：本轮代码、研究记录与公开统计；运行脚本仍依赖完整仓库的既有公共数据及来源文件，不是脱离项目的模型运行环境。

结果为复用材料的开发证据。联合人评 A、人工复核、辅助事实检查和 AI B 分列；严格解析与明确格式修复分列。原始输出不覆盖。文件夹包含逐题材料，仅作本地研究结果包；不含模型权重或 API 凭证。

新增 API 费用 $0；formal outcome 与 PM training 均为 0。本轮未执行 Git commit/push。
