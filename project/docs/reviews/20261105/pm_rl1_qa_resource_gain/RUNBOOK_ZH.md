# QA收益验证：冻结包、检查与接续

仓库：`/home/tokkio/Metacom5_3`。私有目录：`project/outputs/pm_rl1/qa_resource_gain_20261105_v1/`。

已完成：`176 screen → encode → controls → prepare`。来源与D内容审查原件另存。`encode`使用原BGE本地权重，在`paper1-py311`环境CPU运行，4线程、离线、完整输入，无GPU调用。`prepare`使用`paper1-judges-py312`中的原Gemma tokenizer。两种模型的软件/设备身份独立保存，不声称CPU向量就是旧GPU缓存。

已尝试一次`run`，退出1，在加载前被其他GPU任务挡住；86个请求均未开始。保留`RUN.log`、`EXECUTION_ATTEMPT_01.json`和原检查。不要覆盖日志、重新`prepare`或复制输出目录重试已开始的请求。

只读复核：

```bash
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/docs/reviews/20261105/pm_rl1_qa_resource_gain/verify.py
env PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -q project/tests/test_rl1_qa_gain_gate.py
```

在已有明确GPU空闲条件后接续同一包；不是自动轮询、抢占或改变既有排他条件。代码仍在加载前重新检查实际最新快照：

```bash
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/rl1/176_probe_qa_resource_gain.py run --output project/outputs/pm_rl1/qa_resource_gain_20261105_v1 > project/outputs/pm_rl1/qa_resource_gain_20261105_v1/RUN_ATTEMPT_02.log 2>&1
```

仅在这次加载阶段结束后收集一次结果（技术不完整也保留，不能补成0）：

```bash
python project/scripts/rl1/176_probe_qa_resource_gain.py collect --output project/outputs/pm_rl1/qa_resource_gain_20261105_v1
```

`BLIND_SOURCE_REVIEW_PRIVATE.json`不含条件标签。按冻结的别名/语义要点审查输出；需要复核的项写到`BLIND_SOURCE_VERDICTS_PRIVATE.json`，以`review_id`为键，每项包含`reply_identity`、`verdict`（correct/partial/incorrect/abstained/uncertain）和理由。不得照着想通过的条件改答案；不得把这种助手事实核查称为新增独立人评或奖励资格。任何后续更正保留原件和版本。

```bash
python project/scripts/rl1/177_assess_qa_resource_gain.py --output project/outputs/pm_rl1/qa_resource_gain_20261105_v1
```

判定文件按版本新增，不覆盖；未完成或不确定时输出待定/上下界。通过只进入强简单基线及读后信息价值检查，仍不开始RL、不推广G、不赋训练奖励。

`PREPARATION_MANIFEST.json`只封存本轮准备及第一次加载前拒绝的现有文件；以后新增执行/结果文件允许追加，旧文件不得改写。需要改变已冻结代码/条件时另记修订，不静默修改协议哈希。
