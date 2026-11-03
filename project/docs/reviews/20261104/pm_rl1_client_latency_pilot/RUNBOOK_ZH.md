# 首轮客户端计时：运行和复核

工作目录`/home/tokkio/Metacom5_3`。已执行固定26次范围并关闭，无后台模型任务；原输出目录不可重跑。重复计时请求各有独立slot/draw身份，不是生成缓存重放；中断没有自动重试。

## 代码

- `project/src/metacom_pm/rl1/client_latency.py`：单客户端时钟、流式接收、失败/删失保留、明确秒数权重的候选回报。
- `project/src/metacom_pm/rl1/latency_serving.py`：真实在线固定/顺序读取、请求内编码缓存、另有身份的原参数流式生成适配器。
- `project/scripts/rl1/154_measure_reference_client_latency.py`：固定输入及执行范围、一次G/BGE加载、交错重复、逐请求留存及汇总。
- `project/tests/test_rl1_client_latency.py`：首段与完整等待、失败、缺失、来源/条件校验、OFF路径及逐次完整编码等测试。

## 无模型复核

```bash
python project/docs/reviews/20261104/pm_rl1_client_latency_pilot/verify.py

env PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -q \
  project/tests/test_rl1_client_latency.py \
  project/tests/test_rl1_organized_policy_interface.py \
  project/tests/test_rl1_organized_local_backend.py
```

前者独立复算客户端事件、原请求/回复及来源哈希，不派发模型。后者30项通过，全部为工程测试，不能当真实质量或训练效果。

## 本轮实际执行命令

```bash
env PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python \
  project/scripts/rl1/154_measure_reference_client_latency.py prepare \
  --output project/outputs/pm_rl1/client_latency_pilot_20261104_v1

env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 \
  TOKENIZERS_PARALLELISM=false \
  PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103:project/src \
  /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -u \
  project/scripts/rl1/154_measure_reference_client_latency.py run \
  --output project/outputs/pm_rl1/client_latency_pilot_20261104_v1
```

运行日志单独保存为`client_latency_pilot_20261104_v1_EXECUTION.log`。所有真实调用已完成，不再次运行上述`run`。后续新实验需新目录及清楚的具体比较范围；当前用户的继续推进授权不因换目录失效，不要求重复确认常规本地工作。

守卫仍检查原A6000、加载前45,000MiB/0%及其他可见进程；不换设备、不终止他人任务。原模型、适配器、BGE、软件版本及453历史来源保持。新流式源码属于本轮执行身份，后续修改应保留本轮源码/产物身份，不把新版本结果混入本轮。

`summarize`只读已有请求并更新汇总，但封存后默认使用独立`verify.py`检查，不覆盖原manifest。秒数函数没有λ默认值；原正式训练协调器没有自动切换到它。未来训练适配须同时处理共同监督目标、OneShot和PPO，不允许只在最终表格中把token成本重命名为延迟。
