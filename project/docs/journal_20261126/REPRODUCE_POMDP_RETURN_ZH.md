# SMV30 与新 POMDP CPU 身份的复跑说明

本轮只执行研究者批准的 SMV1/SMV2：30 个实际调用、两次加载，原 `packages-v3` 清单 SHA256 为 `51470d87ec9af85e03a47a31baf45cf6a585a351480a0e6353c9e26649a702f8`。本页所有命令均为 CPU 读取/复算，不会启动或重跑这些模型请求。新的序贯提案仍未授权、尚未完成动态运行准入。

仓库为 `/home/tokkio/Metacom5_3-journal`。公共代码包含脚本、聚合报告和匿名逐题数据；完整历史、问题、gold、模型回复及助手审阅记录只在已有私有运行根目录。公开 GitHub 不含这些输入，远程复跑需要研究者自行提供同身份私有资产，不能仅凭公共聚合重建语义标签。

## 1. 固定运行与结果身份

|对象|位置或公开清单|
|---|---|
|SMV 固定任务/请求/评分合同|`/opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126/independent-memory`，`packages-v3` / `source-bundle-v3` / `evaluation-preparation-v2`|
|新 SMV 批准与真实执行|`/opt/tokkio-data0/tokkio_runs/pmrl1-j-pomdp-20261126/static`，`SMV1_AUTHORIZED.json` / `SMV2_AUTHORIZED.json` / `SMV*_run1/job-*`|
|SMV 完整输出与开发观察|同根 `static/collected-v1` / `static/review-final-v1` / `static/analysis-v1`；草稿也保留|
|SMV 公开计量与逐题结果|[smv30_results_v1/MANIFEST.json](smv30_results_v1/MANIFEST.json)|
|新来源任务与评价隔离|新根 `cases/bundle-v1`；[SOURCE_MANIFEST.json](pomdp_v1/SOURCE_MANIFEST.json)|
|原 80 条 CPU 轨迹与终局输入|新根 `engineering/cpu-v2`；首次失败 `cpu-v1` 保留；[ENGINEERING_MANIFEST.json](pomdp_v1/ENGINEERING_MANIFEST.json)|
|原 80 路及追加 Top4 来源审计|新根 `cases/trace-audit-v1` / `cases/top4-audit-v1`；实际可读 trace 和来源只存私有|
|未来预算|[BOUNDED_PROPOSAL_V2_PUBLIC.json](pomdp_v1/BOUNDED_PROPOSAL_V2_PUBLIC.json)，不是已准入计划|

旧两份保护清单分别包含 334 和 359 个文件，本轮逐一核对均为零变化；两清单有重叠，不相加。原 tracked 文件相对起点均未改。没有重开 J00/G0e/E6/A0，没有消费原剩余 220 次请求。公开检查回执见 [POMDP_RETURN_VALIDATION_PUBLIC.json](POMDP_RETURN_VALIDATION_PUBLIC.json)。

## 2. 重读真实 SMV 日志并复算

```bash
cd /home/tokkio/Metacom5_3-journal
export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
PMJ_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
PMJ_SMV=/opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126/independent-memory
PMJ_STATIC=/opt/tokkio-data0/tokkio_runs/pmrl1-j-pomdp-20261126/static

# 输出目录必须不存在。collector核对批准、hash链、调用顺序、payload、tokens和停止原因。
"$PMJ_PY" project/scripts/rl1v3/journal_smv_results.py \
  --package "$PMJ_SMV/packages-v3" --run-root "$PMJ_STATIC" \
  --preparation "$PMJ_SMV/evaluation-preparation-v2" \
  --out /tmp/pmrl1-smv-fresh-collection

# 仅聚合逐条显式审阅，不从关键词猜语义，不把供证当成功。
"$PMJ_PY" project/scripts/rl1v3/journal_analyze_smv.py \
  --source "$PMJ_SMV" --actual /tmp/pmrl1-smv-fresh-collection \
  --review "$PMJ_STATIC/review-final-v1" \
  --preparation "$PMJ_SMV/evaluation-preparation-v2" \
  --out /tmp/pmrl1-smv-fresh-analysis
```

本轮已实际复跑到 `static/root-reproduce-v1`，五份收集文件及三份分析文件 **8/8 逐字节一致**，没有模型调用。`output_sha256` 绑定完整 worker output 对象，不是仅文本字符串的 hash。未知端点在同一实际回复复用时从配对差中抵消，不同回复的未知不强行关联；事实 NA 与成功分开。

## 3. 来源、检索及新原型复跑

以下私有脚本不包含新的模型执行；其公开实现是 `journal_pomdp_source_cases.py`、`journal_pomdp_source_trace_audit.py`、`journal_pomdp_source_static_audit.py`、`journal_prepare_pomdp_memory.py`、`journal_report_pomdp_memory.py`、`journal_pomdp_fixed_top4_pressure.py`、`journal_prepare_pomdp_proposal_v2.py`。脚本保存了固定资产参数；输入 hash 在相应 manifest 中。

```bash
PMJ_NEW=/opt/tokkio-data0/tokkio_runs/pmrl1-j-pomdp-20261126

# 重建16任务的来源/目标分离，再审计已存在的80+16实际CPU读取；不重新检索或生成。
bash "$PMJ_NEW/cases/REPRODUCE_SOURCE_CPU.sh" /tmp/pmrl1-pomdp-source-fresh

# 重跑原80条CPU路径，使用原tokenizer与renderer，仅加载tokenizer，不加载G权重。
bash "$PMJ_NEW/engineering/REPRODUCE_CPU.sh" /tmp/pmrl1-pomdp-path-fresh

# 同初始query的整会话Top4压力读取及v2预算对象；无模型推理。
bash "$PMJ_NEW/engineering/REPRODUCE_TOP4_PRESSURE_AND_PROPOSAL.sh" /tmp/pmrl1-pomdp-top4-fresh
```

来源脚本本轮实际复跑的 **16 份任务、参考及来源计数文件逐字节一致**。重新检索的计时字段会随 CPU 调度变化，不要求含计时的轨迹 hash 相同；任务、合法池、返回原文与确定输入身份应稳定。首次分词错误及 Top4 汇总键序列化错误均留有原记录，只修程序问题，不根据覆盖结果改来源、规则或样本。

原80条路径上限四次获取；Top4 macro 为一次检索加四次父读取，共五次操作。它们共享 token/context 上限，但不是完全相同动作域。`SOURCE_TOP4_COMPARISON.json` 的来源数不能当作模型答案或支持成功。

## 4. 本轮完整 CPU 回归

```bash
cd /home/tokkio/Metacom5_3-journal
export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
export JOURNAL_RS_OUTPUT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/rs/candidates-v1
export JOURNAL_RS_FOLLOWUP=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125/rs
export JOURNAL_RS_COMPLEX=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/rs_complex/package-v2
export JOURNAL_RS_BATCH_REVIEW=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/batch18_rs_review
export JOURNAL_KEYCAP_RS=/opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-20261125/rs_r1/final
export JOURNAL_CLOSEOUT_RS=/opt/tokkio-data0/tokkio_runs/pmrl1-j-closeout-20261125/rs_review/combined-v1
export JOURNAL_JOINT_PACKAGE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-terminal-20261125/joint/packages-v5
export JOURNAL_JOINT_BUNDLE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-terminal-20261125/joint/source-bundle-v1
export SELECTIVE_MEMORY_VALIDATION_PRIVATE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126/independent-memory
export POMDP_SOURCE_CASES_PRIVATE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-pomdp-20261126/cases
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  project/tests/test_rl1v3_journal*.py --junitxml=/tmp/pmrl1-pomdp-tests-new.xml
```

实际结果 **347 passed、0 failed、0 errors、0 skipped，10.749 秒**。XML SHA256：`c364c7d70769c651fa5bdae5f1f516164a9950b266c16f09006405b5c9ac20aa`。它验证权限、日期、引用、完整来源、预算、重复读取、参数 provenance、无文本边界、严格 parser 和真实产物绑定，不证明 POMDP 或自然支持研究假设成立。

公开导出经限定长文本匹配及人工检查；这不是覆盖所有潜在泄露的保证，也没有重新开展资产审计。原五项真人审阅继续等待研究者，助手开发记录不充当它们的裁决。
