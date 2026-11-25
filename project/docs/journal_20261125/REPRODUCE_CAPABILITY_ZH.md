# CPU复跑、测量复核与私有交付索引

在独立journal工作树使用原依赖stack。以下均不启动GPU；生成作业已经完成，禁止作为复跑步骤再调用run。新的实验只执行其新授权绑定。

```bash
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
export CUDA_VISIBLE_DEVICES=''
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
export JOURNAL_RS_OUTPUT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/rs/candidates-v1
export JOURNAL_RS_FOLLOWUP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125/rs
export JOURNAL_RS_COMPLEX=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/rs_complex/package-v2
export JOURNAL_RS_BATCH_REVIEW=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/batch18_rs_review
J_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
J_OLD=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125
J_EVIDENCE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125
J_CAP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125
J_INPUT=/home/tokkio/Metacom5_3-integration
J_REPLAY=$(mktemp -d /opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-replay-XXXXXXXX)

"$J_PY" -m pytest -q project/tests/test_rl1v3_journal*.py

"$J_PY" -m metacom_pm.rl1v3.journal.paired_results \
  --requests "$J_EVIDENCE/next-batch-v1/REQUESTS.private.jsonl" \
  --logical-requests "$J_EVIDENCE/next-batch-v1/LOGICAL_REQUESTS.private.jsonl" \
  --job "$J_CAP/batch18_run1/job-89fd2b51b8cf5b9a2132782385b8954e9cbb9a5673737d27e72f96a997bf2c88" \
  --output "$J_REPLAY/paired"

"$J_PY" project/scripts/rl1v3/journal_compare_temporal_retrieval.py retrieve \
  --memory "$J_OLD/memory" \
  --model /home/tokkio/.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5/snapshots/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a \
  --native-model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 \
  --assets "$J_INPUT/project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json" \
  --output "$J_REPLAY/retrieval"
"$J_PY" project/scripts/rl1v3/journal_compare_temporal_retrieval.py evaluate \
  --output "$J_REPLAY/retrieval" --audit "$J_EVIDENCE/memory_audit/v2/ATOMS_PRIVATE.jsonl"

"$J_PY" -m metacom_pm.rl1v3.journal.eval_calibration build \
  --old "$J_OLD" --evidence "$J_EVIDENCE" --assets "$J_INPUT" \
  --design "$J_CAP/calibration/DESIGN_FROZEN.json" \
  --manual "$J_CAP/calibration/MANUAL_REFERENCE_DESIGN.private.json" --out "$J_REPLAY/calibration-items"
"$J_PY" -m metacom_pm.rl1v3.journal.eval_calibration score \
  --frozen "$J_REPLAY/calibration-items" \
  --classifier "$J_OLD/rs/behavior-unique-v1/model.private.joblib" --out "$J_REPLAY/calibration-results"

"$J_PY" project/scripts/rl1v3/journal_calibration_source_lineage.py \
  --items "$J_REPLAY/calibration-items" --out "$J_REPLAY/calibration-lineage"

"$J_PY" project/scripts/rl1v3/journal_prepare_memory_packages.py \
  --root "$J_INPUT" --representations "$J_EVIDENCE/representations/build-v4" \
  --writer8 "$J_EVIDENCE/representations/writer8-v1" --smoke "$J_OLD/smoke-v2" \
  --measurements "$J_EVIDENCE/smoke_results/MEASUREMENTS.json" \
  --repo "$PWD" --out "$J_REPLAY/memory-packages"

"$J_PY" project/scripts/rl1v3/journal_rs_complex.py build \
  --tasks-dir "$J_EVIDENCE/rs/complex12-v1" --candidates "$J_OLD/rs/candidates-v1" \
  --sources "$J_OLD/sources" \
  --review-path "$J_CAP/rs_complex/APPLICABILITY_REVIEW-v2.private.json" \
  --review-sha256 4c2e2dba188a112ef4ecb88ea055ea480512d953dfbc2d42226d66b78d2345b9 \
  --template-plan "$J_EVIDENCE/next-batch-v1/BATCH_PLAN.json" \
  --repo "$PWD" --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 \
  --assets "$J_INPUT/project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json" \
  --output "$J_REPLAY/rs-complex"

"$J_PY" project/scripts/rl1v3/journal_export_capability_results.py \
  --root "$J_CAP" --out "$J_REPLAY/public"
```

检索阶段只读runtime问题与RAW；evaluate阶段才读取人工证据。结果中的排名应重现，耗时随CPU负载变化。既有As-of交叉检查与共同严格分母的副表不改写原任务身份；原RET30/30来源集合也必须重现。

校准的当前活跃版为`items-v2/results-v2`：输入与预测和v1字节相同，两条`missing`参考的枚举映射修复及分母变化见`V2_CORRECTION_RECEIPT.json`。程序重放不能代替独立语义审阅。历史人评、同模型助手开发观察、历史缓存judge预测分开；既有TF-IDF只推断，不重新拟合。来源连接脚本`journal_calibration_source_lineage.py --help`给出原件参数；其sidecar记录可证明的跨类别连接，不能把16组件当成独立试验样本。

Memory/RS构建使用完整固定payload，CPU检查不会加载G。新输出目录会改变executor路径及包裹计划hash，不能据新hash继承旧授权。原冻结运行快照仍是审批对象。Native分词、素材和任务JSONL应重现；耗时、输出绝对路径及包含代码/路径的manifest可变化。

私有根目录`$J_CAP`中的完整材料：

| 内容 | 路径 |
|---|---|
| 20逻辑臂完整原始输出、复用标记、逐条计量 | `batch18_results/PAIRED_RESPONSES_PRIVATE.jsonl`及`.md` |
| Memory 6物理/8逻辑逐句来源核查 | `batch18_memory_review/LOGICAL8_READABLE_PRIVATE.md` |
| RS 12条原项判断、引文与辅助观察 | `batch18_rs_review/PAIRED_REVIEW.private.jsonl` |
| 30题所有检索结果及证据覆盖 | `memory_retrieval/run-v1/QA30_COMPARISON_PRIVATE.md` |
| 排名、冷/热计时、证据冻结 | `memory_retrieval/run-v1/RANKINGS_PRIVATE.jsonl`、`RANKING_FREEZE.json` |
| 96项完整inputs/references/predictions | `calibration/items-v2/`、`calibration/results-v2/` |
| 可证明来源组件关联 | `calibration/source-lineage-v1/SOURCE_LINEAGE_PRIVATE.json` |
| 36表示、Writer8、MP/ME6完整请求 | `memory_packages/final-v2/` |
| 复杂RS12题×6臂完整来源/评价/输入 | `rs_complex/package-v2/READABLE_PACKAGE.private.md` |

所有原RAW、gold、私人评审材料和生成全文留在私有目录。公共输出采用字段允许清单；公开分支只包含代码、计数、计划身份与复跑说明。各分析的原语义判断不会被自动重判为正式奖励。
