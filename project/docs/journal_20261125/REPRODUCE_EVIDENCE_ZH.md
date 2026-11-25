# 证据审查与实际结果复跑

本轮公共报告为 [ACTUAL_RESULTS_20261125_ZH.md](ACTUAL_RESULTS_20261125_ZH.md)。以下命令仅执行 CPU 校验/重放；不要重跑已经完成的 A0 或20次生成。所有输出使用新的目录，保留冻结输入及历史版本。

在独立 journal 工作树运行。依赖沿用上一轮 A/B/G 固定文件构成的私有 stack，未合并历史工作树。公开分支包含新增 journal 代码；私有 stack 的 journal 链接指向该工作树。

```bash
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
export CUDA_VISIBLE_DEVICES=''
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export JOURNAL_RS_OUTPUT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/rs/candidates-v1
export JOURNAL_RS_FOLLOWUP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125/rs
J_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
J_OLD=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125
J_NEW=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125
J_INPUT=/home/tokkio/Metacom5_3-integration
J_REPLAY=$(mktemp -d /opt/tokkio-data0/tokkio_runs/pmrl1-j-replay-XXXXXXXX)

"$J_PY" -m pytest -q project/tests/test_rl1v3_journal*.py

"$J_PY" project/scripts/rl1v3/journal_audit_memory_evidence.py \
  --root "$J_INPUT" --memory "$J_OLD/memory" \
  --review "$J_NEW/memory_audit/v2/MANUAL_REVIEW_PRIVATE.json" \
  --output "$J_REPLAY/audit"

"$J_PY" project/scripts/rl1v3/journal_build_representations.py \
  --root "$J_INPUT" --audit "$J_NEW/memory_audit/v2/ATOMS_PRIVATE.jsonl" \
  --runtime "$J_OLD/memory/tasks_runtime.jsonl" \
  --baseline "$J_OLD/requests-v2/G0E_BASELINE.json" --out "$J_REPLAY/representations"

"$J_PY" -m metacom_pm.rl1v3.journal.paired_results \
  --requests "$J_OLD/smoke-v2/SMOKE_REQUESTS.private.jsonl" \
  --job "$J_NEW/smoke_run1/job-4d88228888db1595ff6f800dbf588ddcfc784dd3a7f2789658f9e3c86119fc83" \
  --output "$J_REPLAY/paired"

"$J_PY" project/scripts/rl1v3/journal_export_public_results.py \
  --root "$J_NEW" --output "$J_REPLAY/public"
```

`paired_results` 从实际 worker 事件提取全部请求；拒绝重复/额外调用，保留未启动、已启动无返回和技术失败，不把缺失响应或语义评价写成零。输出 token 数由实际返回 token IDs 计算，输入数与 worker 记录交叉核对。

30题审查和生成后的语义审阅都包含人工式源文判断。CPU 重放验证既有判断的来源、跨度、hash、时点和供给关系；不能自动重现或资格化语义判断。正式结果维持 uncertain，不能将这些开发观察用作 reward。

Memory 盲审重放用 `journal_review_memory_outcomes.py freeze-blind` 输入已冻结的 `smoke_results/MEMORY_REVIEW_BLIND_PRIVATE.jsonl`、`memory_audit/v2/ATOMS_PRIVATE.jsonl`、`memory_outcomes-v1/MANUAL_REVIEW_PRIVATE.json` 和原 EvoEmo 文件，输出新目录，再用 `join-key` 读取 `smoke_results/REVIEW_KEY_PRIVATE.jsonl`。这只能复核原盲审，不能声称看到 arm 后再次评价仍为盲审。

RS 的 CPU 编码、7视频组外验证、供给审查和复杂12题重放命令保存在私有 `rs/REPRODUCE_V2.txt`。公开 `rs_followup complex` 要求私有 `--design` 文件，其固定 hash 为 `c8723215…`（完整值在 manifest 中）；任务条件和评价答案不硬编码在公共代码。新版 builder 实际重放四项冻结任务/评价输出字节一致。RS 盲审重放使用 `rs_smoke_review` 校验冻结 review 的引文偏移、响应身份和正式评价未知约束。

私有结果根目录为 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125`，主要入口：

| 内容 | 相对路径 |
|---|---|
| 全20条完整配对回复及逐条 tokens/时间 | `smoke_results/PAIRED_RESPONSES_PRIVATE.md` |
| 30题原子、官方口径、合法原文与 DP/RET 覆盖 | `memory_audit/v2/QA30_EVIDENCE_REVIEW_PRIVATE.md` |
| Memory 输出每个原子及新增个人事实的来源核对 | `memory_outcomes-v1/MEMORY_OUTCOME_REVIEW_PRIVATE.md` |
| RS 全12条配对观察与引文位置 | `rs/smoke_review-v1/PAIRED_REVIEW.private.jsonl` |
| 12题×3表示的实际读取内容 | `representations/build-v4/materials.private.jsonl` |
| MP/ME/SUM/SPAN 资源及原文跨度 | `representations/build-v4/resources.private.jsonl` |
| 原 As-of 的24次真实读取 | `representations/ASOF_VALIDATION_V1.json` |
| 独立复杂RS12题可读文本及评价 | `rs/complex12-v1/READABLE_TASKS.private.md` |
| 下一批18次实际调用的独立申请 | `next-batch-v1/BATCH_PLAN.json` |
| 8次 Writer 具体请求 | `representations/writer8-v1/WRITER8_REQUEST.json` |

下一批 CPU admission 检查无需访问 GPU：冻结执行器路径见 `next-batch-v1/BATCH_PLAN.json`，运行其 `journal_smoke_run.py check --plan .../BATCH_PLAN.json`。原授权无法转用于该新计划，`AUTHORIZATION_PENDING.json` 保持 false。Writer8 的旧吞吐说明已由 `next-batch-v1/WRITER8_TIMING_UPDATE.json` 更正；原申请不覆盖，尚缺独立8次 admission。
