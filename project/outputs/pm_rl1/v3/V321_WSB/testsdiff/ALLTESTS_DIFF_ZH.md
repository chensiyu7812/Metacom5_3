# 额外全量测试的 99 个失败：base 与 HEAD 逐测试对照

## 方法

- **两次运行条件相同**：在同一个临时 worktree 中依次检出两个提交，每次检出后都 `git clean -fdx`。使用同一个 venv（Python 3.11.15，`pip freeze` 的 sha 记录在 `runs/env.txt`），执行同一条命令：

  ```
  TMPDIR=<数据盘> PYTHONNOUSERSITE=1 PYTHONPATH=src CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    python -m pytest -q -m "not gpu" tests -ra -o addopts= --junitxml=<id>.xml
  ```

  脚本见 `runs/run_pair.sh`。与上一轮相比只多了 `TMPDIR`：根盘可用空间约 0.7 GB，默认 `/tmp` 会让临时目录报 Errno 28（#19 的完整运行就出现过这种情况）。两次运行用的是同一个 TMPDIR。
- **对照的提交**：
  - base：PR #17 的 base `a9cf0cca`，即 #16 HEAD；
  - HEAD：PR #17 的最终 HEAD `3dafb2aa`；
  - 参考：上一轮在主工作区、默认 TMPDIR 下于 `6c8d2ebd` 的运行（`V32_WSB_RQ1Q/logs/alltests_dir.xml`）；
  - 补充：#20 的代码 HEAD `c2f13862`，在同一个 worktree 中用同一条命令运行。
- **比较方式**：解析 junit XML，逐个测试 ID 比较。结果见 `ALLTESTS_DIFF.json`，原始 log 与 XML 见 `runs/`。

## 结果

| 运行 | passed | failed | skipped | 耗时 |
|---|---:|---:|---:|---|
| base `a9cf0cca` | 3,931 | 99 | 66 | 37:21 |
| HEAD `3dafb2aa` | 3,961 | 99 | 66 | 34:19 |
| 参考 `6c8d2ebd`（主工作区） | 3,961 | 99 | 66 | 14:10 |
| #20 代码 HEAD `c2f13862` | 3,995 | 99 | 66 | 34:03 |

- **两边都失败**：99 个测试 ID 完全相同。
- **只在一边失败**：base 0，HEAD 0。
- **状态变化**：在两边都存在的测试中，0 个改变状态。
- **只在 HEAD 存在的测试**：30 个，全部来自 `tests/test_rl1v3_v32_rq1_qual.py`（#17 新增），全部通过。
- **与参考运行的失败集合**：完全相同，说明 worktree 位置和 TMPDIR 都不影响结果。
- **#20 代码 HEAD**：失败集合与 #17 HEAD 完全相同；多出的 34 个通过来自 #20 新增的 V3.2.1 测试。

**结论**：这 99 个失败在 #17 之前就已存在，#17 和 #20 都没有引入、修复或改变任何一个。

## 99 个失败的构成（HEAD）

**按文件**：

| 文件 | 失败数 |
|---|---:|
| `test_v1_5_*`（42 个文件） | 89 |
| `test_posthoc_v1_bank_probe` | 7 |
| `test_mock_pipeline` | 1 |
| `test_pm_v2_eval_hardening` | 1 |
| `test_scientific_safeguards` | 1 |

**按原因**：

| 原因 | 失败数 |
|---|---:|
| FileNotFoundError：缺少未入库的旧数据或旧产物 | 81 |
| `ValueError: qualified V1.5 prompt compiler accepts at most one card`：旧测试与现行编译器不符 | 11 |
| 旧产物的计数或状态与断言不符（如 `BLOCKED` ≠ `API_PILOT_READY`，503 ≠ 509） | 5 |
| AttributeError：旧 API 已变 | 1 |
| KeyError：旧记录字段 | 1 |

这些文件都不在 CI 范围内。CI 只运行 `test_paper1_*`、`test_rl1_*`、`test_rl1v3_*`，以及 V3 严格套件。#16、#17、#20 都没有修改其中任何一个文件。是否修复或归档这些旧测试，应作为单独任务，由 integration owner 决定。

## CI（核对的是最终 HEAD，不是较早的绿色结果）

| PR | 提交 | run | V3 严格套件 | 公共 CPU 套件 |
|---|---|---|---|---|
| #17 最终 HEAD | `3dafb2aa` | 44323588907 | 633 passed | 2,398 passed / 63 skipped |
| #20 代码 HEAD | `c2f13862` | 44350790945 | 667 passed（+34 项 V3.2.1 测试） | 2,432 passed / 63 skipped |

#20 最终 HEAD 的 CI 在最后一次推送后核对，写在 PR 描述中。
