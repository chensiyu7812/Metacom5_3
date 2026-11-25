# 本轮CPU复跑与证据入口

工作树为独立journal分支，依赖原stack与既有私有来源。本文件不提供再次执行已完成42次GPU作业的命令。测量、审阅绑定、RAW读取与请求构建均为CPU；下面独立NLI段会加载同一固定NLI到CPU，不能与G调用混淆。所有复跑写新目录，保留原结果。

```bash
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
export CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
export JOURNAL_RS_OUTPUT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/rs/candidates-v1
export JOURNAL_RS_FOLLOWUP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125/rs
export JOURNAL_RS_COMPLEX=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/rs_complex/package-v2
export JOURNAL_RS_BATCH_REVIEW=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/batch18_rs_review
export JOURNAL_KEYCAP_RS=/opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-20261125/rs_r1/final
K_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
K_RUN=/opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-20261125
K_CAP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125
K_OLD=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125
K_EVID=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125
K_REPLAY=$(mktemp -d /opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-replay-XXXXXXXX)

"$K_PY" -m pytest -q project/tests/test_rl1v3_journal*.py

"$K_PY" project/scripts/rl1v3/journal_keycap_measurements.py \
  --root "$K_RUN" --packages "$K_CAP" --out "$K_REPLAY/MEASUREMENTS.json"

"$K_PY" project/scripts/rl1v3/journal_keycap_memory_review.py \
  --package "$K_CAP/memory_packages/final-v2" \
  --m1-job "$K_RUN/M1_run1/job-65681a5504377ef5bead0bd0a72a1138f42141ef65c57b253108f7cda3067ce3" \
  --w1-job "$K_RUN/W1_run1/job-db1c4d4b033d3c10a948632558ce6d4b66a9ff141693fd745d35b7b805b3c23b" \
  --audit "$K_EVID/memory_audit/v2/ATOMS_PRIVATE.jsonl" \
  --inventory "$K_RUN/memory_review/source_freeze/WRITER_PROPOSITIONS_PRIVATE.json" \
  --review "$K_RUN/memory_review/review-v1" \
  --registry /home/tokkio/Metacom5_3-journal/project/outputs/pm_rl1/v3/A1_preparation/final/registry \
  --ledger "$K_OLD/memory/ledger" \
  --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 \
  --assets /home/tokkio/Metacom5_3-integration/project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json \
  --out "$K_REPLAY/memory"

"$K_PY" -m metacom_pm.rl1v3.journal.keycap_rs_review collect \
  --package "$K_CAP/rs_complex/package-v2" \
  --job "$K_RUN/R1_run2/job-d5c6b1e8e3038e5a2ff7d8d8d1e1870462abd9117119e5635a2a5ab639819d59" \
  --preoutcome "$K_RUN/rs_r1/PREOUTCOME_REVIEW_PLAN.private.json" \
  --output "$K_REPLAY/rs-collection"
"$K_PY" -m metacom_pm.rl1v3.journal.keycap_rs_review finalize \
  --package "$K_CAP/rs_complex/package-v2" --collection "$K_REPLAY/rs-collection" \
  --review-path "$K_RUN/rs_r1/OBSERVATIONS_FROZEN_PRIVATE.jsonl" \
  --receipt-path "$K_RUN/rs_r1/OBSERVATION_FREEZE_RECEIPT.json" --output "$K_REPLAY/rs-review"

"$K_PY" -m metacom_pm.rl1v3.journal.semantic_validation predict \
  --frozen "$K_RUN/semantic_validation/frozen-v1" --out "$K_REPLAY/nli"

"$K_PY" project/scripts/rl1v3/journal_temporal_generation.py prepare \
  --memory "$K_OLD/memory" --rankings "$K_CAP/memory_retrieval/run-v1" \
  --template "$K_EVID/next-batch-v1/BATCH_PLAN.json" \
  --measurements "$K_EVID/smoke_results/MEASUREMENTS.json" \
  --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 \
  --assets /home/tokkio/Metacom5_3-integration/project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json \
  --output "$K_REPLAY/temporal"
"$K_PY" project/scripts/rl1v3/journal_temporal_generation.py evaluate \
  --output "$K_REPLAY/temporal" --audit "$K_EVID/memory_audit/v2/ATOMS_PRIVATE.jsonl"

"$K_PY" project/scripts/rl1v3/journal_export_keycap.py --root "$K_RUN" \
  --catalog project/docs/journal_20261125/capability_results_v1/RUN_REQUEST_IDENTITIES.json \
  --out "$K_REPLAY/public"
```

本轮实测164测试全通过。Memory复跑验证18+8份观察的身份、引文与命题覆盖，执行8次真实RAW ReadingView和16结构变异；它不重新生成私人语义观察或资格化审阅者。RS复跑先重放原Journal，再读取冻结观察；不启动G、不重新判断回复。结构日期只核对报告日期，阶段保持unknown。

NLI参考构建入口为`semantic_validation freeze --help`。完整输入来源hash、窗口及模型规格存于`semantic_validation/frozen-v1/PROTOCOL_FROZEN.json`，私有`REFERENCE_DESIGN_PRIVATE.json`是冻结输入，不由预测结果重新编写。复跑使用原`FrozenSupportNeedNLIScorer`、原模型snapshot与固定阈值；浮点概率及计时容许平台差异，任何阈值越界应报告，不调参追求匹配。

原42次执行授权、launcher、原Journal和R1入口失败记录在`$K_RUN`。R1修复使用冻结`executor/project/src`作为PYTHONPATH，调用该快照中的`metacom_pm.rl1v3.journal.rs_complex_run.run(plan, approval, run_root)`；没有把当前工作树代码替换进快照，也没有新建模型／请求身份。后续五包必须有各自新授权，再使用原守卫执行。

| 私有证据 | 相对`$K_RUN`路径 |
|---|---|
| M1逐题三臂全文／原子与供应引用 | `memory_review/review-v1/M1_REVIEW_PRIVATE.md`、`.jsonl` |
| W1八份全文／134命题覆盖 | `memory_review/review-v1/W1_REVIEW_PRIVATE.md`、`.jsonl` |
| 旧定位问题及正确来源sidecar | `memory_review/review-v1/SOURCE_REFERENCE_ERRATA_PRIVATE.json` |
| 八次实际RAW读取和16结构对照 | `memory_review/validation-v1/RAW_FALLBACK8_PRIVATE.jsonl`、`STRUCTURED_REFERENCE16_PRIVATE.jsonl` |
| R1完整18逻辑臂、方法引用及归因 | `rs_r1/final/READABLE_COMPARISON_PRIVATE.md`、`rs_r1/LAYER_DIAGNOSIS_PRIVATE.json` |
| 64项输入／独立来源参考／预测 | `semantic_validation/frozen-v1/`、`semantic_validation/results-v1/` |
| 五项有限人工复核 | `semantic_validation/FINITE_HUMAN_REVIEW_PRIVATE.json` |
| 8日期题、24逻辑／22唯一payload及供应评价 | `temporal_generation/candidate-v1/` |

公开文件只含代码、聚合、身份与复跑说明。完整RAW、gold、私人参考和生成全文不上传GitHub。
