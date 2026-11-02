# 本轮复算

工作目录：`/home/tokkio/Metacom5_3`。

```bash
PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/139_audit_human_reference_reuse.py \
--output project/outputs/pm_rl1/human_reference_reuse_NEW_REPRODUCTION

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -ra \
project/tests/test_rl1_organized_learning_bridge.py \
project/tests/test_rl1_human_reference_reuse.py \
project/tests/test_rl1_organized_policy_interface.py \
--junitxml=/tmp/pmrl1-learning-human-reuse-final-20261102.xml

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python project/scripts/rl1/135_run_development_stage.py \
--package project/outputs/pm_rl1/execution_bridges_20261030_v6
```

最后一个命令仅check；没有`--execute`、审批文件、凭据或网络查询。研究者已答复暂不启动付费评分，不修改原pending/预算文件来绕过这一决定。

76项相关回归使用上述三个测试文件另加：`test_rl1_natural_batch.py`、`test_rl1_measurement_backend.py`、`test_rl1_qualified_learning.py`、`test_rl1_resource_organization.py`。JUnit见本目录；最后28项为缓存/资格检查小改后的验证。

生产调用边界：`LoadedBGEBlocks`接收已由原`bge_m3._load_model`核验的模型，逐块forward不重新分词；`execute_generation`投影到原`LocalNaturalGenerator.generate`。这些函数不承担加载/费用授权；实际worker须在具体阶段允许下调用，不能因模块可import就自行加载。当前没有新增真实运行入口或运行许可。

私有复用库含原人评、完整匹配依据和文件hash；公开目录仅保存汇总、方法、验证及代码hash，不发布原答案或原始回复。
