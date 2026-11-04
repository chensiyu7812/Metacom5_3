# 本轮复核与接续

工作目录 `/home/tokkio/Metacom5_3`。真实14次范围已执行完成；同一输出目录拒绝重新加载/运行，没有留置后台模型任务。以下复核不加载模型、不调用API。

```bash
env PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python project/scripts/rl1/157_audit_balanced_learning.py
env PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python project/docs/reviews/20261104/pm_rl1_client_latency_pilot/verify.py
```

35项相关测试（全部合成质量/时间，真实原优化器）：

```bash
env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -o addopts= -q project/tests/test_rl1_balanced_learning.py project/tests/test_rl1_balanced_objective.py project/tests/test_rl1_memoized_online.py project/tests/test_rl1_client_latency.py project/tests/test_rl1_organized_supervision.py
```

本机私有证据：

- `project/outputs/pm_rl1/memoized_online_validation_20261104_v1/`：487程序/591观察精确重放、请求内计算次数和来源清单。
- `project/outputs/pm_rl1/memoized_latency_pilot_20261104_v1/`：执行前协议、14条独立请求的客户端事件/实际原文、载入与GPU守卫记录、汇总及哈希清单。首次被拒执行日志为同级 `memoized_latency_pilot_20261104_v1_EXECUTION.log`；后续完整执行日志为 `memoized_latency_pilot_20261104_v1_ADMISSION_RECHECK.log`。
- `project/outputs/pm_rl1/balanced_learning_audit_20261104_v1/`：36条正式计时与原菜单/回复的绑定、覆盖数、待质量状态、453文件及账本核验。`SOURCES.json`绑定本轮新适配代码。用157无参数可只读重算；`--output`只允许新目录。

代码职责：`memoized_online.py`保持原资源/观察/请求内容；`online_materials.py`核验原包及完整真实来源；155全程序重放；156固定14次真实对比；157只读审计。`balanced_objective.py`负责编译共同回报，`balanced_learning.py`沿用原协调器和优化器，另绑定方法时间、当前行为参数及恢复证据。原历史模块字节未改变。

自然执行前仍须具备：准确且合格的ON/OFF质量反馈；显式共同λ及部署条件；BC/OneShot各自完整已测候选时间；当前行为参数的真实顺序执行时间（包括STOP）；原训练许可、完整16条批次、固定开发检查和比较反馈并集。每个缺失值保持pending。脚本重放pilot不满足当前行为绑定；不允许通过手工给旧时间补参数字段来绕过。

本轮没有选定λ，没有创建自然训练许可或检查点，没有覆盖旧结果、修改预算、推送远端或要求重复人评。
