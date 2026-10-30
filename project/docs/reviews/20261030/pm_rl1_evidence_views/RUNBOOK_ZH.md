# 复算与回归

仓库：`/home/tokkio/Metacom5_3`。完整私有产物在 `project/outputs/pm_rl1/evidence_views_20261030_v3/`，不可覆盖。v1为首次成功准备版本，保留其较高布局开销与原计划重复OFF的记录；v2使用同一固定选择、精简表示及原OFF复用；v3冻结最终反馈候选交接代码，G输入与v2一致。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/132_prepare_evidence_views_and_development.py \
--output project/outputs/pm_rl1/evidence_views_20261030_v3 \
--tokenizer-dir /opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -rA \
project/tests/test_rl1_development_feedback.py \
project/tests/test_rl1_resource_evidence_views.py \
project/tests/test_rl1_resource_organization.py \
project/tests/test_rl1_temporal_evidence_ledger.py \
project/tests/test_rl1_environment.py \
project/tests/test_rl1_representation.py \
project/tests/test_rl1_feedback_score_audit.py \
project/tests/test_rl1_strict_audit_delivery.py \
project/tests/test_rl1_recovery_schedule.py \
--junitxml=/tmp/pmrl1-o2-final-tests.xml

git diff --check
```

重新复算必须给新的输出目录。脚本没有执行模型或真实评分的开关；缺输入/身份错误时写 `FAILURE.json` 并退出，不下载、不补推理。三轮准备均退出0；首轮定向测试12项通过，最终新增共享恢复及补核失败不回落测试，并扩展相关回归后115项通过（12.09秒），不能相加当作不同研究样本。

| 私有文件 | 用途 |
|---|---|
| `SELECTION_BEFORE_VIEWS.json` | 先按owner/prefix元数据固定6个开发前缀；不是独立验证资格 |
| `source_views_private/*.json` | 114份MP/ME来源映射、MP报告序列、ME事件目录、MS完整注册轮次、共享来源链接 |
| `MS_VIEW_RECEIPTS_PRIVATE.json` | 1,122个MS位置的逐项全文身份、轮数、费用及匹配项审计；无语义金标 |
| `COMPARISONS_PRIVATE.json` | A/B共同来源/域、两侧输入身份、不同候选与待判断项 |
| `GENERATION_INPUTS_PRIVATE.json` | 49个不同固定输入；6原OFF复用，43未生成；未附旧q/m |
| `INPUT_GAPS.json` | 缺库存等明确缺项，不用0补齐 |
| `J1_PRIMARY_REQUESTS_PRIVATE.json` | 22条完整真实开发请求，仅重建、未发送 |
| `J1_HANDOFF.json` | 当前公共接口与真实派发/资格剩余边界 |
| `INPUT_HASHES_PRIVATE.json`、`SOURCE_CODE_HASHES.json` | 实际读取和代码身份；没有mixed/test/sealed原文 |
| `PROTECTED_HASHES.json`、`OUTPUT_MANIFEST.json` | 不变的旧合同/账本/人评包，以及全部产物身份 |

合成测试只用虚构来源，不依赖上述私有目录，不调用网络/真实模型。`OfflineDevelopmentStage` 拒绝真实transport，不能用它替代财务审批和资格。真实开发材料没有被套用合成评分。
