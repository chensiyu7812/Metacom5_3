# 执行器使用诊断复核

从仓库根目录执行，只读核验及写本目录摘要，不加载模型、不调用API：

```bash
python project/docs/reviews/20261104/pm_rl1_executor_use_probe/verify.py
```

5个修订候选已创建，可幂等核对；脚本不改原数据、不训练：

```bash
python project/docs/reviews/20261104/pm_rl1_executor_use_probe/prepare_candidates.py
```

已运行并通过的9项定向测试：

```bash
env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -o addopts= -q project/tests/test_rl1_executor_use_probe.py project/tests/test_rl1_resource_comparison_runner.py
```

实验根为`project/outputs/pm_rl1/executor_use_probe_20261104_v1/`：

- `P2_AUDIT.json`、`TARGET_CARDS_PRIVATE.json`、`P2_CONTENT_REVIEW_PRIVATE.json`：493实际目标的结构审计、8情境26目标和内容疑点的精确引文。
- `STUDY.json`、`G_PROTOCOL.json`、`SOURCES.json`：单一指导、18次调用/1次加载及旧输入/模型/代码身份。
- `ORIGINALS_PRIVATE.json`：16个旧输入及真实旧回复。`INPUTS_PRIVATE.json`、`CARDS_PRIVATE.json`、`G_REQUESTS_PRIVATE.json`：本批完整输入和对照。
- `live_G/`：18组启动/raw/seal及关闭记录；`RESULTS_PRIVATE.json`为真实输出；`CONTENT_REVIEW_PRIVATE.json`为AI内容审查，没有奖励。
- `REVISION_CANDIDATES_PRIVATE.json`：5个绑定原输入的AI草稿，接纳/训练均为否；不要未经配套就当正式训练包或收益标签。
- `REVIEW_ZH.html`：全部对照及5个草稿的浏览页，非问卷。
- `CLOSEOUT.json`、`OUTPUT_MANIFEST.json`：结果收口和私有产物哈希；本目录`CHECKS.json`为独立复算。

生成已关闭，不为复核重跑`162_probe_executor_use.py run`或换目录重置18次额度。新适配器使用原G执行器消息格式，显式支持真正OFF，未修改原冻结执行器文件。prepare、run、analyze均退出0；新材料不是新增主版本、正式收益或泛化结果。
