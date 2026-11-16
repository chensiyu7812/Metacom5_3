# 裁判测量研究与具体校准准备

- 论文分析稿：`repository_files/project/docs/PM_PAPER1_JUDGE_MEASUREMENT_STUDY_20260917_ZH.md`
- 校准说明：`repository_files/project/docs/PM_PAPER1_STATIC_AMOUNT_CALIBRATION_PACKAGE_20260917_ZH.md`
- 论文图表：`repository_files/project/docs/reviews/20260917/judge_measurement_figure.{png,svg,pdf}`
- 148 道选题、1,924 条完整生成请求、2,220 行分析映射及官方评分模板：`static_calibration_package/`

本轮只完成 CPU 准备和已有实验的分析整理，未启动或排队 GPU 生成，未调用付费 API，未选择 k*。A6000 当前运行其他项目任务。评分槽位还没有待生成的 prediction；不能直接作为 API 请求发送。拟议的 $15 评分阶段尚未授权；费用情景中的长度不是输出上限。

研究稿保留官方评分与源事实核查的区别，未改写官方指标。代码在完整 Metacom5_3 仓库及固定公共来源下运行；本包不包含模型权重或独立模型运行环境。
