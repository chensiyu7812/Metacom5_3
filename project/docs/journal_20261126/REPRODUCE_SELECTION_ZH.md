# 本轮CPU复跑与私有边界

起点`35650aa2d63a52d59e73d549a19ac64996b9314a`。本目录为追加证据；旧输出、评分、准入与任务不改。公开JSON只含匿名逐题状态、计数、成本及身份，不包含query、RAW、gold、完整回复或私人评审理由。完整语义核查需要授权本机的私有材料，不能从聚合数据凭空恢复。

## 1. 环境与已有输入

```bash
cd /home/tokkio/Metacom5_3-journal
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
export CUDA_VISIBLE_DEVICES=''
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
PMJ_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
PMJ_TERM=/opt/tokkio-data0/tokkio_runs/pmrl1-j-terminal-20261125
PMJ_CLOSE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-closeout-20261125
PMJ_CURRENT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-selection-20261126
```

所有输出必须使用新目录/文件。下列`/tmp/pmrl1-selection-replay-*`仅为CPU复算示例，若已存在应另指定新路径，不能删除旧证据重跑覆盖。不会载入模型或访问GPU。当前公开文档/源码依赖原A/B/G stack；不重新拼装架构。

## 2. STOP/MS全量逐题复算

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_selective_diagnostic.py \
  --joint-root "$PMJ_TERM/joint" --out /tmp/pmrl1-selection-replay-stop-ms
```

独立从原fact/support观察重建联合区间，并核对96条实际事件输出及其hash。该复算校验旧观察的运算和绑定，**不自动证明语义观察正确**。预期共同确定成功为J06/J08/J14/J16/J18；五题切换18–20、输入21357、节省4129；STOP/MS上界18–21；C1为16–19、输入14498。`FULL_READBACK_PRIVATE.jsonl`和`INPUT_MANIFEST_PRIVATE.json`不可上传。

## 3. 归因复算

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_failure_attribution.py \
  --cases "$PMJ_CURRENT/attribution/CASES_V2_PRIVATE.jsonl" \
  --protected-hashes "$PMJ_CURRENT/attribution/PROTECTED_INPUT_HASHES_PRIVATE.json" \
  --out /tmp/pmrl1-selection-replay-attribution
```

`CASES_V2_PRIVATE.jsonl`是旧语义观察及有限来源核查的私有适配材料，已哈希冻结。其来源整理器、来源定位和长引文继续仅在本机；公开模块验证实际供证、引文、来源、旧label引用、私有case及359个原文件身份，重算156逻辑行（J96、T24、历史M36）并分组计数。适配材料不是独立金标准，也不被用来训练Judge。期望`changed_originals=0`、`internal_causal_mechanisms_identified=0`，输出计数与本目录`ATTRIBUTION_*`一致。原五项真人裁决仍pending。

## 4. 已完成154次调用计量复核

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_terminal_measurements.py \
  --root "$PMJ_TERM" --packages "$PMJ_CLOSE" \
  --out /tmp/pmrl1-selection-replay-TS.json
"$PMJ_PY" project/scripts/rl1v3/journal_joint_measurements.py \
  --root "$PMJ_TERM" --catalog "$PMJ_TERM/joint/RUN_CATALOG.json" \
  --out /tmp/pmrl1-selection-replay-J96.json
```

预期T/S为58次、87056输入/3674输出；J为96次、79880输入/5376输出。两对象分别与旧`terminal_results_v1/TS58_TECHNICAL_MEASUREMENTS.json`、`JOINT96_TECHNICAL_MEASUREMENTS.json`完全相等。本轮已实际执行，并写入`CPU_AND_HISTORY_RECEIPT.json`。

## 5. CPU测试及结构化独立诊断

```bash
export JOURNAL_RS_OUTPUT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/rs/candidates-v1
export JOURNAL_RS_FOLLOWUP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125/rs
export JOURNAL_RS_COMPLEX=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/rs_complex/package-v2
export JOURNAL_RS_BATCH_REVIEW=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/batch18_rs_review
export JOURNAL_KEYCAP_RS=/opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-20261125/rs_r1/final
export JOURNAL_CLOSEOUT_RS=/opt/tokkio-data0/tokkio_runs/pmrl1-j-closeout-20261125/rs_review/combined-v1
export JOURNAL_JOINT_PACKAGE="$PMJ_TERM/joint/packages-v5"
export JOURNAL_JOINT_BUNDLE="$PMJ_TERM/joint/source-bundle-v1"
"$PMJ_PY" -m pytest -q project/tests/test_rl1v3_journal*.py \
  --junitxml=/tmp/pmrl1-selection-replay-tests.xml
```

本轮267项全部通过，无跳过。新增24项分别为选择规则/区间7项、失败归因9项、结构化准入与评价8项。旧测试同样实际运行；没有新建大型Judge资格审查。

实际tokenizer/grammar CPU校验使用原G的py312环境、已有XGrammar的隔离副本：

```bash
PMJ_PACKAGE="$PMJ_CURRENT/structured/packages-v3"
PYTHONPATH="$PMJ_PACKAGE/executor/project/src:$PMJ_PACKAGE/executor/vendor_constrained" \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/journal_validate_structured_constrained.py \
  --package "$PMJ_PACKAGE" --out /tmp/pmrl1-selection-replay-grammar.json
```

环境保持`CUDA_VISIBLE_DEVICES=''`。预期36个原payload相同、140个候选值见证可达、8个错误格式拒绝、3种EOS可达、0模型加载、CUDA未初始化。CPU时间随机器负载变化，不要求复现时长字节。**不运行任何after-approval脚本**。SC1/SC2的生成准入、两个plan和请求SHA、执行器及预算见[独立申请](STRUCTURED_CONSTRAINED_RUN_REQUEST_ZH.md)，旧授权不可转用。

## 6. 公开结果导出

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_selection_public_report.py \
  --root "$PMJ_CURRENT" \
  --historical project/docs/journal_20261125/terminal_results_v1 \
  --out /tmp/pmrl1-selection-replay-public
```

该命令从本轮原始CPU产物生成固定公开白名单、24题Markdown表和清单；语义私有侧车不在白名单内。导出文件的hash见`selection_results_v1/EXPORT_MANIFEST.json`。格式诊断只准备一个方案，没有因为CPU准备过程的v1/v2版本而新增模型条件；当前唯一运行身份为packages-v3。
