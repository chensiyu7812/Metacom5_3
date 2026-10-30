# 复算与启动边界

工作目录 `/home/tokkio/Metacom5_3`。最终私有包 `project/outputs/pm_rl1/execution_bridges_20261030_v5/` 已准备且两入口check通过。不要覆盖这个目录；重新准备要用新目录，协议绑定固定执行位置。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/133_prepare_execution_bridges.py \
--output project/outputs/pm_rl1/execution_bridges_NEW_REPRODUCTION

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 \
PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929:project/src \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
project/scripts/rl1/134_run_resource_comparison.py \
--package project/outputs/pm_rl1/execution_bridges_20261030_v5

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/135_run_development_stage.py \
--package project/outputs/pm_rl1/execution_bridges_20261030_v5

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -ra \
project/tests/test_rl1_development_feedback.py \
project/tests/test_rl1_development_dispatch.py \
project/tests/test_rl1_development_preflight.py \
project/tests/test_rl1_resource_comparison_runner.py \
project/tests/test_rl1_local_backend.py \
project/tests/test_rl1_measurement_backend.py \
project/tests/test_rl1_recovery_schedule.py \
project/tests/test_rl1_feedback_workflow.py \
project/tests/test_rl1_feedback_source_evidence.py \
project/tests/test_rl1_score_audit_validation.py \
project/tests/test_rl1_strict_audit_delivery.py \
--junitxml=/tmp/pmrl1-execution-bridges-final.xml
```

真实启动只在对应固定范围获得明确批准后，保存真实研究者答复及其hash，生成与协议绑定的审批文件，给相应入口增加 `--execute --approval <实际批准文件>`。不得把 `*_APPROVAL_PENDING.json` 改个状态就冒充研究者批准。G还须原 `CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1`，入口会核验实际GPU；没有BGE加载。J由获准进程本地提供凭据，不在聊天/命令日志中传密钥。

本轮只执行了prepare/check及合成测试。G具体候选范围为原G加载1次、最多43生成、6原OFF复用、BGE/API/评分/训练/新增人评0、无自动重试；协议 `1f3b5d15cc37d2dfc3683b88e5be59617178a8a1af61d027f2e301059a6ba78f`。它返回完整原始回复与逐项来源/耗时/终止回执，不自动声称质量改善。

J协议 `1fe6b56a1b2f121bdf1b45828f600e4f29e4734d7b431614c48a0252cce2f5e0` 对应开发最多82评分attempt：22初评、22审查、最多22条件补核、最多16技术恢复；2个一次性服务/余额查询，公开价格表在每次显式启动时复核。$6是开发与后续选中路线验证共用的提案总资金，不是两阶段各$6，后续验证未获本包启动授权。准备包中现有额度和拟修订额度均明确保留；目前没有生效的额度变化。

| 文件 | 用途 |
|---|---|
| `G_PROTOCOL.json`、`G_REQUESTS_PRIVATE.json` | 固定原模型/代码/来源/输入与一次加载范围 |
| `REUSED_OFF_PRIVATE.json` | 原OFF请求与原始回复身份；不附旧评分 |
| `J_CONFIG_PRIVATE.json`、`live_J/PROTOCOL.json` | 完整原输入、S/A/R适配、财务与累计次数合同 |
| `COUNTER_BASELINE.json` | 304＋3＋1的历史尝试来源 |
| `HISTORICAL_CODE_DELTAS.json` | 原协议与后来公共测试迁移的差异，不改旧协议 |
| `*_APPROVAL_PENDING.json` | 待研究者集中决定的具体范围；不可执行 |
| `SOURCE_HASHES_PRIVATE.json`、`CODE_HASHES.json`、`PROTECTED_HASHES.json`、`PACKAGE_MANIFEST.json` | 可复核来源、实现、历史不变项与包身份 |

G成功关闭使用 `CLOSED_FIXED_COMPARISON`；J成功关闭使用 `CLOSED_DEVELOPMENT_NOT_QUALIFIED`。未知送达、账本/身份异常或不足以预留一条完整请求时停止，保留已有产物；不是重置后自动再跑。因已用完一次G加载范围而不能接续时，报告未完成项和额外加载需要，不删开始记录。
