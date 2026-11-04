# 执行器有限监督试验复核

主结果在 `project/outputs/pm_rl1/executor_revision_20261104_v2/`。v1 是保留的落盘失败现场，不是另一组可供挑选的模型。所有输入均来自既有24个隔离train前缀；无新API付费，无新的人评问卷。

完成后从仓库根目录只读复算证据，并更新本报告目录的 `CHECKS.json`：

```bash
python project/docs/reviews/20261104/pm_rl1_executor_revision/verify.py
```

定向测试（23项，含导致首轮中断的连续进度写入回归）：

```bash
env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -o addopts= -q project/tests/test_rl1_revision_journal.py project/tests/test_rl1_executor_revision.py project/tests/test_rl1_executor_encoding.py project/tests/test_rl1_executor_engineering.py project/tests/test_rl1_executor_use_probe.py project/tests/test_rl1_resource_comparison_runner.py
```

实际执行来源：163冻结原17条示范及32个对照输入；164完成5次原执行器生成，第二次优化更新后的进度落盘报错；166登记失败，原样沿用数据、参数、最终轮次和5条结果，绑定165的修复。165只改变进度文件落盘方式及预建目录，仍从原P2 epoch_3开始。v1有2次内存更新但无检查点，不能当作可用模型或继续训练状态；v2完成的15次更新单独统计。

v2训练与独立进程复载的实际命令如下。**已完成的试验不要重跑或换目录重置额度**；这些命令用于复现记录的解释，不是再次派发请求。

```bash
env CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929:project/src /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -u project/scripts/rl1/165_train_executor_revision_repair.py train --root project/outputs/pm_rl1/executor_revision_20261104_v2
env CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929:project/src /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -u project/scripts/rl1/165_train_executor_revision_repair.py compare --root project/outputs/pm_rl1/executor_revision_20261104_v2
```

证据入口：

- `PROTOCOL.json`、`WEAK_SOURCE_REVIEW_PRIVATE.json`：固定范围、技术修复来路、17行来源/当前需要审核。作者和审核者同为AI，不是独立帮助性标注。
- `TRAINING_PRIVATE.json`、`INPUTS_PRIVATE.json`、`PROJECTIONS_PRIVATE.json`：示范、全部完整输入、旧资源内容/时间到当前地址的精确投影。
- `training/ENCODING.json`、逐步/逐轮记录、三个适配器与优化器状态：仅回复+EOT损失、真实参数更新。固定epoch3，不按结果筛选检查点。
- `training/FINAL.json`、`RELOAD.json`：全量底座冻结哈希、LoRA变化、独立进程复载NLL。
- `CANDIDATE_PROTOCOL.json`、`candidate_G/`：候选独立身份、32次生成与关闭记录。原5次调用在v1 `baseline_G/`，另29条历史原回复复用。
- `RESULTS_PRIVATE.json`、`FIT_CONTRAST.json`、`REVIEW_ZH.html`：完整前后对照、目标条件敏感度诊断及浏览页；均不赋q/m或PPO奖励。
- `CONTENT_REVIEW_PRIVATE.json`、`CLOSEOUT.json`、`OUTPUT_MANIFEST.json`：内容检查、研究结论边界及私有文件哈希。

`analyze.py` 从固定raw重建前后对照与HTML。它不会加载模型，也不会调用评审；原私有结果已冻结，应核对而非覆盖。
