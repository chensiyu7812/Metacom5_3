# CPU 验证与失败记录（PR 创建时快照）

此文件保留创建 Draft 时的真实状态；**最终同一 HEAD 的运行结果追加到 PR Conversation 和 PR 描述**，不重写已有证据。最终提交 SHA/CI run/job/artifact 和计数以该收据为准。当前不会将尚未完成的重跑写为通过。

- 新增 8 项专项检查：8 passed / 0 failed，0.85 秒；检查真实 16 载荷/来源、篡改拒绝、DP pending、防注入白名单和一次调用/停止行为。
- 第一次完整 CPU 套件：2427 passed、1 failed、2 setup errors、1 skipped、11 GPU deselected，568.23 秒。失败在旧 RS/source registry 测试的临时文件写入，明确 `Errno 28: No space left on device`；根盘当时 0 可用，数据盘约 308 GiB 可用。完整失败日志和 JUnit 保留，不能将失败算覆盖通过。
- 已将 TMPDIR 和 pytest --basetemp 指到本轮数据盘目录，进行完整重跑；未改任何测试断言。仅清理了本轮已结束失败 run 的 `/tmp/pytest-of-tokkio/pytest-188`（762 MiB）；其他任务文件未动。
- 唯一已知历史 skip：缺冻结 Llama tokenizer `/home/chenzhi/paper1_runs/frozen_tokenizers/llama31_8b_instruct_tokenizer.json`；跳过不算覆盖。远端 CI 的环境 skip 以实际日志单列。
- CPU 原生重新分词的 16 份输入与原 IDs 完全一致；干净重跑 13 个文件逐字一致；459 个保护文件未变；integration-base/outcome-lock PASS。
- 开发 CPU v1 是校验器补充 source/frontier/known/date/family 检查前的预览，已单独移到验证目录 `superseded_cpu_v1`；没有模型结果，正式交付仅 cpu_v2。最终代码 hash 在 VALIDATION_RECEIPT 中，重跑结果须对这些 hash。
- CPU 标准套件包含既有确定性 optimizer fixture 单元测试；没有研究训练、研究 checkpoint、Generator/Judge、GPU 或付费 API。A 参考 checker 和测试通过均不是 B 回执。

复跑完整套件（从 project 目录，先创建自己的新临时目录；不要复用已有 --basetemp）：

```bash
TMPDIR=/path/to/new/data-volume/tmp CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103 \
  /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q -m 'not gpu' \
  tests/test_paper1_*.py tests/test_rl1_*.py tests/test_rl1v3_*.py -ra -o addopts= \
  --basetemp=/path/to/new/data-volume/pytest --junitxml=/path/to/new/full.xml
```

远端 CI 另执行 V3 严格套件（零 skip/xfail/error 门禁）和相同公共 CPU 范围。不得复用 #18 或 #17 的测试数字声称本 PR 最终 HEAD 通过。
