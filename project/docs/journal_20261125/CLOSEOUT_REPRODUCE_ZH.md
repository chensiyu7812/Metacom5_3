# 收口实验：CPU复跑与私有证据入口

以下命令只读取已完成作业，不重新启动GPU。工作树为独立journal分支；A/B/G运行依赖仍使用既有stack。需要本机原私有数据和冻结资产，公开仓库不提供RAW、gold、完整回复或私人评审。本轮全量207项测试通过，0失败、0跳过；详见公开`closeout_results_v1/VALIDATION.json`。

```bash
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
export CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
export JOURNAL_RS_OUTPUT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/rs/candidates-v1
export JOURNAL_RS_FOLLOWUP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125/rs
export JOURNAL_RS_COMPLEX=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/rs_complex/package-v2
export JOURNAL_RS_BATCH_REVIEW=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/batch18_rs_review
export JOURNAL_KEYCAP_RS=/opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-20261125/rs_r1/final
export JOURNAL_CLOSEOUT_RS=/opt/tokkio-data0/tokkio_runs/pmrl1-j-closeout-20261125/rs_review/combined-v1
C_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
C_RUN=/opt/tokkio-data0/tokkio_runs/pmrl1-j-closeout-20261125
C_CAP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125
C_KEY=/opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-20261125
C_EVID=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125
C_REPLAY=$(mktemp -d /opt/tokkio-data0/tokkio_runs/pmrl1-j-closeout-replay-XXXXXXXX)

"$C_PY" -m pytest -q project/tests/test_rl1v3_journal*.py

"$C_PY" project/scripts/rl1v3/journal_closeout_measurements.py \
 --root "$C_RUN" --packages "$C_CAP" --out "$C_REPLAY/MEASUREMENTS.json"

"$C_PY" project/scripts/rl1v3/journal_closeout_memory.py \
 --package "$C_CAP/memory_packages/final-v2" \
 --m2-job "$C_RUN/M2_run1/job-e426821295a7d6b1513f4c062727b8ff6b9fc4e315bac6f43d817a372099eedf" \
 --u1-job "$C_RUN/U1_run1/job-38b739b0789b23f7c69f9f521a43f76559b24c76231fcbb31fa0d842931e7e78" \
 --audit "$C_EVID/memory_audit/v2/ATOMS_PRIVATE.jsonl" \
 --m1-review "$C_KEY/memory_review/review-v1/M1_REVIEW_PRIVATE.jsonl" \
 --m2-review "$C_RUN/memory/review-v1/M2_REVIEW_PRIVATE.jsonl" \
 --u1-review "$C_RUN/memory/review-v1/U1_REVIEW_PRIVATE.jsonl" \
 --u1-inventory "$C_RUN/memory/source-freeze/U1_SOURCE_INVENTORY_PRIVATE.jsonl" \
 --out "$C_REPLAY/memory"

"$C_PY" -m metacom_pm.rl1v3.journal.closeout_rs merge \
 --finals "$C_KEY/rs_r1/final" "$C_RUN/rs_review/R2/final" \
 "$C_RUN/rs_review/R3/final" "$C_RUN/rs_review/R4/final" \
 --output "$C_REPLAY/rs"
```

Memory命令重新核对真实输出身份、来源、引文及固定观察，再生成逐题／配对表；不重新创造语义判断。RS merge核对四批终态manifest和全部72逻辑臂／68物理输出。逐批journal与固定观察可用`closeout_rs collect`、`finalize`重放，参数见模块`--help`；不调用模型。length输出保留为technical incomplete，不能当EOS或自动重试。

结构化18题可从同一私有seed重建到全新目录：

```bash
"$C_PY" project/scripts/rl1v3/journal_prepare_structured.py \
 --root /home/tokkio/Metacom5_3-integration --repo /home/tokkio/Metacom5_3-journal \
 --smoke /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/smoke-v2 \
 --measurements "$C_EVID/smoke_results/MEASUREMENTS.json" \
 --seed "$C_RUN/structured/SOURCE_SEED_PRIVATE.json" --out "$C_REPLAY/structured"
```

这里会实际进行18次合法Port读取和tokenize，不加载G权重。更换输出路径会改变新计划对象身份，不可把原授权转移到重建副本。有效申请只对应原`structured/packages-v2`。18题与36端点的参考验算及变异测试属于软件检查，不能计作G成功。两批评分器固定SHA为`a83cc1b5960cb419bc893768f190da0664630cdc18c3ee4e9e63ae0a9374d87d`。

检索22次的CPU重建命令、固定计划／请求SHA及预算在[TEMPORAL22_RUN_REQUEST_ZH.md](TEMPORAL22_RUN_REQUEST_ZH.md)；结构化36次申请见[STRUCTURED36_RUN_REQUEST_ZH.md](STRUCTURED36_RUN_REQUEST_ZH.md)。新包均使用独立准入，旧76次、A0或冒烟授权无法转移。

| 私有证据（相对`$C_RUN`） | 内容 |
|---|---|
| `USER_AUTHORIZATION.json`、`*_AUTHORIZED.json`、`*_run1/job-*` | 原76次授权、hash-chain调用、原输出与停止记录 |
| `memory/review-v1/M2_REVIEW_PRIVATE.md`、`U1_REVIEW_PRIVATE.md` | 本轮全部M2/U1回复、来源及逐项解释 |
| `memory/validated-v2/MEMORY36_REVIEW_PRIVATE.jsonl` | M1+M2完整36条观察 |
| `memory/source-freeze/`、`memory/REVIEW_MANIFEST_V2_PRIVATE.json` | 生成前源清单、审阅规则与最终身份 |
| `rs_review/combined-v1/READABLE_COMPARISON_PRIVATE.md` | 原复杂12题全部六臂及逐项标准／供给／观察 |
| `human_review5/READABLE_REVIEW_ZH_PRIVATE.md` | 原五项事后有限人审材料，等待真人裁决 |
| `structured/SOURCE_SEED_PRIVATE.json`、`SAMPLES_PRIVATE.md` | 18题实际源配置与可读样例 |
| `structured/endpoints-v1/ENDPOINTS_PENDING.private.jsonl` | 36个新任务专属端点，尚无实际G成功 |

原96项及64项校准不重跑、不改参考。人工材料完成不等于新增人评；自然支持外部验证仍保留。公开聚合采用显式allowlist导出，原文、gold、完整回复和私人语义观察留在数据卷。
