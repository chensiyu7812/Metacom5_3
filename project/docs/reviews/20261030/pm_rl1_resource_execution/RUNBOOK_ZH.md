# 本轮复算与待批准接续

工作目录 `/home/tokkio/Metacom5_3`。原43条阶段实际启动记录保存在 `project/outputs/pm_rl1/execution_bridges_20261030_v6/G_EXECUTION_20261030_02.log`，退出码1；已完成1条，停止于下一次GPU排他检查。旧一次加载额度已消耗，不要重新运行旧入口尝试重载。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/136_analyze_resource_comparison.py \
--package project/outputs/pm_rl1/execution_bridges_20261030_v6 \
--output project/outputs/pm_rl1/resource_comparison_partial_NEW_REPRODUCTION \
--allow-partial

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/137_prepare_resource_comparison_continuation.py \
--package project/outputs/pm_rl1/execution_bridges_20261030_v6 \
--output project/outputs/pm_rl1/resource_comparison_remaining_NEW_REPRODUCTION

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 \
PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929:project/src \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
project/scripts/rl1/134_run_resource_comparison.py \
--package project/outputs/pm_rl1/resource_comparison_remaining_20261030_v2

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -ra \
project/tests/test_rl1_resource_comparison_analysis.py \
project/tests/test_rl1_resource_comparison_runner.py \
project/tests/test_rl1_local_backend.py \
--junitxml=/tmp/pmrl1-resource-execution-final-tests.xml
```

接续范围：**额外G加载1次、仅剩余42条新输入、复用已完成1条和6原OFF、0 BGE/评分/训练/新人评/API费用、不重发未知请求**。审批文件仍为PENDING，没有真实接续启动。协议 `864b242537018cbcab5dec30b64b1f94d9c262d7ed87618ebd73f0e367d16c24`。

获准后在原环境、原 `CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1` 下，对上述134入口增加 `--execute --approval <记录真实研究者答复的批准文件>`。旧已完成1条仍保留前一协议身份，不重新生成或重封装成新调用。未来完整分析运行136时读取接续包，它会同时核验并合并被明确绑定的前一结果。

| 记录 | 用途 |
|---|---|
| 原v5的三个GPU检查与 `CLOSED_UNUSED_G_SCOPE.json` | 模型加载前的采样问题；没有消耗G调用 |
| v6的 `LAUNCH_01_RECEIPT.json` | 真实其他进程占用导致的加载前拒绝 |
| v6的 `LAUNCH_02_RECEIPT.json`、`live_G/*` | 1次成功加载、1条自然回复及运行中外部占用后的停止 |
| partial的 `RESPONSES_PRIVATE.json`、`PAIRS_PRIVATE.json`、`PENDING_REQUESTS_PRIVATE.json` | 49输入的完整分母；1新完成、6复用、42未开始 |
| remaining v2的 `PRIOR_G_RESULTS_PRIVATE.json` | 前一已完成请求、来源协议、原始文件及封印hash |
| remaining v2的 `G_REQUESTS_PRIVATE.json` | 精确剩余42条，不含已完成请求 |

旧S/A付费范围没有因G接续获准。31测试通过不代表独立人评、J资格或真实学习完成。
