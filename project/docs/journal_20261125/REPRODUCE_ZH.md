# 本轮复跑入口

工作树 `/home/tokkio/Metacom5_3-journal`。私有运行根 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125`。所有构建使用**新输出目录**；已冻结候选/失败记录不覆盖。源版本见 `sources/SOURCE_RECEIPT.json`。代码不下载模型，不将 RAW 外传。

固定依赖组合（不要把本分支 HEAD 当作已包含 A/B/G 的全栈）：

```bash
python project/scripts/rl1v3/journal_materialize_stack.py \
  --repo /home/tokkio/Metacom5_3-journal --output /opt/tokkio-data0/tokkio_runs/NEW/stack
```

两个原探针（保留原始脚本、固定四文件）：

```bash
node project/scripts/rl1v3/journal_source_probe.cjs \
  project/data/external/evo_emo.json \
  project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json \
  project/data/paper1_authority/es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl \
  /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/sources/AnnoMI/AnnoMI-full.csv
node project/scripts/rl1v3/journal_annomi_behavior_probe.cjs \
  /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/sources/AnnoMI/AnnoMI-full.csv
```

Memory 已实跑脚本为 `journal_build_memory.py --out NEW --asof /opt/tokkio-data0/tokkio_projects/Metacom5_3-wsa-runprep/project/src/metacom_pm/rl1v3/compile/asof.py`，Python 为 `/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python`；资源、私有目标、实读、素材同时生成。`journal_validate_memory.py --help` 给出 snapshot port 实链复验入口。RS 与两次行为模型训练全命令位于私有 `rs/REPRODUCE.txt`，对应模块 `journal.rs_tasks`、`journal.rs_case_review`、`journal.behavior`。等权重训使用 `--equal-utterance --row-model`，不是重新聚合旧模型分数。

联合实际数据测试命令：

```bash
PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src \
CUDA_VISIBLE_DEVICES='' \
JOURNAL_RS_OUTPUT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/rs/candidates-v1 \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  project/tests/test_rl1v3_journal_renderer.py \
  project/tests/test_rl1v3_journal_memory.py \
  project/tests/test_rl1v3_journal_engineering.py \
  project/tests/test_rl1v3_journal_rs.py
```

当前首批冻结执行器 CPU 检查（无 GPU 访问）：

```bash
PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/smoke-v2/executor/project/src \
CUDA_VISIBLE_DEVICES='' \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/smoke-v2/executor/project/scripts/rl1v3/journal_smoke_run.py \
  check --plan /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/smoke-v2/SMOKE_PLAN.json
```

只有收到这个新计划的明确批准后，才可使用私有 `smoke-v2/RUN_AFTER_APPROVAL.sh <新批准JSON> <新data-volume run-root>`。脚本复用原 worker、进程组与硬停止守卫。原 A0 已批准脚本在 `engineering/A0_RUN_AFTER_APPROVAL.sh`，不因 M/RS 申请变化而改动。

当前可读资源样例：`memory/MEMORY_SAMPLES_PRIVATE.md`、`rs/cases-review-v2/cases-v2.private.jsonl`、`rs/candidates-v1/skills.private.jsonl`。答案/原文只在本地受控目录阅读，不加入公共提交。
