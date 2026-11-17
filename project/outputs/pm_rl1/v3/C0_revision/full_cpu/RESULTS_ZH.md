# C0 0.2.0 全量 CPU 回归

被测共享代码：`8aab9f250cd652917f5ef50af48bcc86ab1f1358`（执行开始时同一源码尚未提交，当前文件 SHA 由 MANIFEST 固定）。

命令：`PYTHONPATH=project/src:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q -m 'not gpu' project/tests/test_paper1_*.py project/tests/test_rl1_*.py project/tests/test_rl1v3_*.py -ra -o addopts= --junitxml=project/outputs/pm_rl1/v3/C0_revision/full_cpu/pytest.xml`

实际结果：**2018 passed / 0 failed / 1 skipped / 11 deselected，461.01 秒**。
唯一 skip 是历史 Llama tokenizer 不存在于 `/home/chenzhi/paper1_runs/frozen_tokenizers/llama31_8b_instruct_tokenizer.json`；本轮未增加 skip。11 项 GPU 测试在无授权条件下按既有标记排除。C0/B 验收全部实跑。

compileall、Schema 32 项一致性、integration base/outcome lock、契约回放 31 接受/33 拒绝通过。PR #5 对应 CI run `44046041069` 在本记录写入时尚未结束；最终以 GitHub 实际状态为准。

B 复审已通过 PR 评论请求；尚未收到正式通过意见，不宣布冻结。本记录补充上层 RESULTS 中的“全量运行中”，不覆盖任何先前日志。
