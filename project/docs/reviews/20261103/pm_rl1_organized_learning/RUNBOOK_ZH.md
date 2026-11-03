# 本轮复算与接续入口

在仓库根目录执行；已验证环境是 `/tmp/pmrl1-publication-20261022-venv/bin/python`。这些命令只跑CPU合成网络和测试，不加载G/BGE、不调用评分服务。诊断输出目录必须是新目录，不能覆盖v1/v2/v3。

```bash
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /tmp/pmrl1-publication-20261022-venv/bin/python project/scripts/rl1/140_check_organized_learnability.py --output project/outputs/pm_rl1/organized_learnability_replication --episodes 128
```

完整相关测试集合：

```bash
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -ra project/tests/test_rl1_organized_learning.py project/tests/test_rl1_organized_supervision.py project/tests/test_rl1_local_backend.py project/tests/test_rl1_cached_generation_worker.py project/tests/test_rl1_supervised_learning.py project/tests/test_rl1_qualified_learning.py project/tests/test_rl1_organized_learning_bridge.py project/tests/test_rl1_organized_policy_interface.py project/tests/test_rl1_study_schedule.py project/tests/test_rl1_measurement_backend.py
```

本轮按先87项回归、后29项受影响路径及反馈后端、最后8项缓存检查运行；存在重叠，不能相加。一次定向命令曾误写不存在的 `test_rl1_research_backend.py`，pytest退出4且没有运行测试；已改用实际的 `test_rl1_measurement_backend.py`，对应执行退出0。这是命令定位错误，不计作测试通过。

接续代码入口：

| 操作 | 入口 |
|---|---|
| 明确训练候选和实际输入 | `organized_supervision.endpoint`、`training_menu` |
| 通过共享队列准备初始监督 | `ResearchBackend.prepare_organized_supervision` |
| 编译动作／价值／程序回报目标 | `organized_supervision.prepare_targets`、`prepare_supervised` |
| BC或OneShot优化和重载 | `supervised_learning.fit_supervised`、`load_initialization` |
| 具体固定规模运行 | `qualified_learning.make_run_manifest` → `OrganizedRun` |
| 收集／恢复／轮询／更新 | `collect`、`resume_collection`、继承的`poll/update_once/recover_update` |
| 固定开发检查和终点 | `evaluate_development`、继承的`finish` |
| 完整训练反馈并集 | `organized_supervision.comparison_union` |
| 初始观察选择OneShot程序 | `ProgramReturnModel.choose/search` |

`comparison_union`测试中的六个完成回执是明确合成夹具；`OrganizedRun`另有真实执行128条合成轨迹和8次更新的测试。二者分别验证并集来源规则和训练终点执行，不能写成已经完成六个真实研究运行。

本轮诊断的OneShot部分直接测其模型回报回归能力，明确标记 `formal_final_union_training=false`；正式OneShot数据必须从完成运行的公共并集产生。搜索预算是计算上限，不是环境4 GET限制；在未来原生上下文不可继续执行时的程序语义，需与所有程序基线统一明确，不能偷用未来检索当选择时的可行性标签。
