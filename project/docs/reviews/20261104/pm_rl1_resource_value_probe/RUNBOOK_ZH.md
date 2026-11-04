# 资源价值诊断复核入口

从仓库根目录执行。完整结果见[RESULTS_ZH.md](RESULTS_ZH.md)。以下命令只读私有实验产物，写本目录检查摘要，不加载模型、不调用API。

```bash
python project/docs/reviews/20261104/pm_rl1_resource_value_probe/verify.py
```

收到的原答复已保存在新目录内，接入脚本可幂等核对；原题和原引用库不覆盖：

```bash
python project/docs/reviews/20261104/pm_rl1_resource_value_probe/ingest_reference.py
```

已运行的9项定向测试：

```bash
env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -o addopts= -q project/tests/test_rl1_resource_value_probe.py project/tests/test_rl1_resource_comparison_runner.py
```

本批产物根：`project/outputs/pm_rl1/resource_value_probe_20261104_v1/`。原始数据留在忽略的私有目录，本目录不提交其对话正文。

- `STUDY.json`、`SOURCES.json`、`G_PROTOCOL.json`：生成前选择、输入/代码/来源、21次单加载执行边界。study identity `24be439f53d046e1f67228bfd933f8436fda228c69ce59caf333ae079e4eb334`；G protocol identity `37814a45db241f98ee00962a42151e18bff8f546bc9a61e651e0d3d08d0a7b6c`。
- `INVENTORY_PRIVATE.json`、`VARIANTS_PRIVATE.json`、`DISTRACTORS_PRIVATE.json`：24前缀初步需求假设、完整源会话、初始排名/6MS路径、呈现保持和长度不匹配记录。
- `CARDS_PRIVATE.json`、`INPUTS_PRIVATE.json`、`REUSED_PRIVATE.json`：41条件、36输入、17精确旧输入。`G_REQUESTS_PRIVATE.json`和`live_G/`对应21次真实调用。
- `RESULTS_PRIVATE.json`、`CONTENT_REVIEW_PRIVATE.json`、`MECHANISM_REVIEW_ZH.html`：原回复与探索性内容核查；没有q/m奖励。HTML是证据浏览页，不是要求补填的问卷。
- `ONE_COMPARISON_PRIVATE.json`/`ONE_COMPARISON_ZH.html`：原N21问题及匿名呈现。`RECEIVED_ANSWER_PRIVATE.json`、`INTAKE_PRIVATE.json`：后来收到的完整原话、AI辅助来源及精确绑定。原题不改写为“原来已答”。
- `ANSWER_REGISTRY_PRIVATE.json`、`REFERENCE_INDEX.json`：当前36条参照库；35条旧记录逐项保留。未自动重配置旧评分/训练输入。
- `CLOSEOUT.json`：答复后的最终状态。`OUTPUT_MANIFEST.json`：本批私有产物文件清单与哈希。早期`SUMMARY.json`/内容核查保留答复前状态。
- 本目录`CHECKS.json`：独立复算结果，`verify.py`不导入本批实现。

`161_probe_resource_value.py`的`run`阶段已关闭，**不要为核查重新运行生成或换目录重置调用范围**。需要新呈现/执行器对照时另立有限请求和版本，保留这批原始结果。已用原执行环境运行21次，退出0；分析退出0；原有9项测试退出0；本轮独立核验退出0。
