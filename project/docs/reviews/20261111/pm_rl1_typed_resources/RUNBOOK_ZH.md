# 已完成阶段的复核入口

工作目录`/home/tokkio/Metacom5_3`。日期按客户端2026-11-11。

## 检查

```bash
env PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -q project/tests/test_rl1_typed_resource_views.py project/tests/test_rl1_qa_gain_gate.py project/tests/test_rl1_resource_organization.py project/tests/test_rl1_resource_value_probe.py
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/docs/reviews/20261105/pm_rl1_qa_resource_gain/verify.py
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/docs/reviews/20261111/pm_rl1_typed_resources/verify.py
```

本轮两个生成阶段均已关闭，不重跑`run`、`collect`或覆盖原包。核验不加载模型权重、不调用GPU/服务。原生token检查只加载本地tokenizer。

## 实际执行记录

QA：保持11月5日冻结包，原176脚本`run`接续（日志RUN_ATTEMPT_02.log），退出0，86请求完成；随后`collect`、人工式来源内容核查（助手，非独立人评）、177评估，得到ASSESSMENT_00。所有14题别名和5题要点在生成之前已固定。原加载前占用拒绝记录保留。

新表示：178 `prepare`→独立来源子序列核查→178 `run`（RUN.log）→178 `collect`。准备和收集也使用上述paper1-judges-py312环境，系统默认Python缺torch不能运行其导入依赖。42请求完成后才修复collector的重复keyword错误，保留源码和POST_EXECUTION_ANALYSIS_FIX.json；不修改已执行请求、协议或旧输出。`verify.py`精确核查该差异，不能泛化为允许任何hash变化。

准备时先修正了“旧raw turn ID被当成盲化数组下标”的新适配器错误；其命名空间差异原审计130已经记录。实际冻结包使用同源中唯一精确角色/跨度/原话定位，24/24前缀通过机械来源核验，然后按固定hash选择6个不同owner。没有根据生成结果调整样本。

## 继续工作边界

新增对照使用独立输出目录、版本和固定范围，不能把旧结果更名成新版本收益。下一阶段优先验证来源完整的记忆视图与强固定/简单停止/OneShot，不重开已关闭的自然支持正例搜索。语义生成、引用命中、短输入及未知结果均不自动成为正奖励。

每个新表示需能回答：哪些原事实/限制/事件阶段保留，哪些未确定，实体或指代是否仍可解释，何时展开原文；后台写入成本和在线决策/检索/有效语音等待分别记录。使用同一个资源域、相同基础指导、相同冻结G比较方法。检索器或PM能利用的字段必须来自当时可见内容，不能包含题目gold或本轮评分。
