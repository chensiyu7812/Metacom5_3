# 2026-10-31执行记录与离线复算

工作目录：`/home/tokkio/Metacom5_3`。

以下是真实执行过的历史命令，退出0，42条全部自然结束。该协议的一次额外加载与42条生成范围已经关闭；不要为复算统计重新加载G，也不要运行旧43条包重生成结果。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 \
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 \
PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929:project/src \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -u \
project/scripts/rl1/134_run_resource_comparison.py \
--package project/outputs/pm_rl1/resource_comparison_remaining_20261030_v2 \
--execute \
--approval project/outputs/pm_rl1/resource_comparison_remaining_20261030_v2/G_APPROVED_20261031.json \
> project/outputs/pm_rl1/resource_comparison_remaining_20261030_v2/G_EXECUTION_20261031.log 2>&1
```

实际分析也退出0。可用不同的、新输出目录重新运行以下离线命令，不加载模型、不评分；无需`--allow-partial`，因为本批已经完整关闭。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/136_analyze_resource_comparison.py \
--package project/outputs/pm_rl1/resource_comparison_remaining_20261030_v2 \
--output project/outputs/pm_rl1/resource_comparison_results_NEW_REPRODUCTION
```

本次实际分析目录为`project/outputs/pm_rl1/resource_comparison_results_20261031_v1/`。原样本、比较方向、身份和模型不变；不重新采样、替换差结果或追加评分。

| 资产 | 作用 |
|---|---|
| remaining包：`USER_AUTHORIZATION_G_20261031.json`、`G_APPROVED_20261031.json` | 绑定本次研究者原话、准确范围和协议；原pending文件保留 |
| remaining包：`LAUNCH_20261031_RECEIPT.json`、`G_EXECUTION_20261031.log` | 本轮加载1/调用42/退出0的实际记录 |
| remaining包：`live_G/load.*`、42组started/raw/sealed、`CLOSED.json` | 真实原模型、每条输入输出与关闭身份 |
| remaining包：`PRIOR_G_RESULTS_PRIVATE.json` | 前次已完成1条的原协议与文件hash；未重新生成 |
| results包：`SUMMARY.json`、`RESPONSES_PRIVATE.json`、`PAIRS_PRIVATE.json` | 完整49行，9组同输入、14组变资源、6组同来源呈现 |
| results包：`OFF_PAIRS_PRIVATE.json`、`PENDING_REQUESTS_PRIVATE.json` | 43组对OFF与空的待执行清单；文本差异不是质量方向 |
| review包：`CASE_LEDGER_PRIVATE.json`、`INPUT_HASHES.json`、`VALIDATION.json` | 7个事后示例的准确引文/角色/来源；非独立人评、非训练标签 |
| 本公开目录：`SUMMARY.json`、`EXECUTION_RECEIPT.json`、`VALIDATION.json` | 不含原始回复的审阅摘要 |

`review包`指`project/outputs/pm_rl1/resource_comparison_review_20261031_v1/`。案例选择和解释属AI辅助开发观察；仅引文存在、角色字段、相同文本与token差属于机械核验。没有生成新人评问卷。

本轮未修改源码，未重复pytest；此前的31项工程检查记录留在20261030目录。曾有一条只读`rg`使用了不存在的简写文件名，退出2；经`rg --files`定位真实文件后读取成功，不影响模型运行、分析或原始输入。其余执行限制见结果报告。
