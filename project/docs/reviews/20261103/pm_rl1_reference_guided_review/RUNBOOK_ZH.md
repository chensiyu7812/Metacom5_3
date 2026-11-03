# 复算与接续

仓库根目录运行以下命令。它只读现有资料，在新目录写结果，不连接模型或账户。

```bash
PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python \
  project/scripts/rl1/150_prepare_reference_guided_review.py \
  --output project/outputs/pm_rl1/reference_guided_review_20261103_recheck
```

默认输入是`execution_bridges_20261103_v1`、`paid_development_snapshot_20261103_refresh_final`和`human_answer_reanalysis_20261103_v2`。输出目录必须不存在；如付费阶段后来推进，旧快照与账本不一致时会拒绝构建，应先用144号入口生成新快照并通过`--snapshot`指定。不要改旧快照以通过检查。

```bash
PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -q \
  project/tests/test_rl1_feedback_reference_review.py \
  project/tests/test_rl1_development_progress_audit.py \
  project/tests/test_rl1_feedback_score_audit.py
```

当前共26项。私有结果不提交Git；公开结果只含计数和已披露诊断。`AUDIT_REQUESTS_PRIVATE.json`是供核对的准备件，不是绕过原预算、未知责任、前置依赖或派发顺序的运行入口。付费接续仍由原运行器及其守卫负责，本次未启动。
