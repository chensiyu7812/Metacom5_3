# SC36实际输出的CPU复算

本轮以`4e78c03988167909a9291df4883214c51a018823`为起点。SC1/SC2已按新批准真实执行，36次均EOS，两个request set已claim。**下列命令只复算已有结果；不再次运行生成wrapper。** 所有新输出目录必须不存在，不能覆盖旧日志、评价或分析。

私有输入位于`/opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126`。公开文件不含原回复、source、gold、引用或私人评审内容；第三方只有公开聚合时能复核加总与配对，不能声称独立核验全部源语义。

```bash
cd /home/tokkio/Metacom5_3-journal
export CUDA_VISIBLE_DEVICES=''
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
PMJ_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
PMJ_SC=/opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126
PMJ_PKG=/opt/tokkio-data0/tokkio_runs/pmrl1-j-selection-20261126/structured/packages-v3
PMJ_OLD=/opt/tokkio-data0/tokkio_runs/pmrl1-j-terminal-20261125
```

## 原严格评分器收集

旧scorer SHA为`a83cc1b5960cb419bc893768f190da0664630cdc18c3ee4e9e63ae0a9374d87d`，原collector SHA为`aa912dcf739a8cd8ac87d41f78cd877da0643a1c6a128eea39bce88aaa23fdcc`，与批准时相同。

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_collect_structured_constrained.py \
  --plan "$PMJ_PKG/batch-01/PLAN_CONSTRAINED.json" \
  --job "$PMJ_SC/SC1_run1/job-2f4e8278ba783b5ba7ccf7905c0f35075bece1fce02b181add65297ad95f69df" \
  --original-outputs "$PMJ_OLD/structured/S1_results_v1/ACTUAL_OUTPUTS.private.json" \
  --out /tmp/pmrl1-sc36-replay-sc1
"$PMJ_PY" project/scripts/rl1v3/journal_collect_structured_constrained.py \
  --plan "$PMJ_PKG/batch-02/PLAN_CONSTRAINED.json" \
  --job "$PMJ_SC/SC2_run1/job-b2e93d5d567963e97a9f34389676becd56f9245cdc8bca3d2f60fe62815fa296" \
  --original-outputs "$PMJ_OLD/structured/S2_results_v1/ACTUAL_OUTPUTS.private.json" \
  --out /tmp/pmrl1-sc36-replay-sc2
```

预期各18条技术有效且格式pass，严格任务分别12、13。输出`READBACK_CONSTRAINED_PRIVATE.md`含完整新旧回复及参考，留本地。

## 实际计量、逐题对照与源契约定位

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_measure_sc36.py \
  --package "$PMJ_PKG" --run-root "$PMJ_SC" --original-root "$PMJ_OLD" \
  --out /tmp/pmrl1-sc36-replay-technical
"$PMJ_PY" project/scripts/rl1v3/journal_analyze_sc36.py \
  --root "$PMJ_SC" \
  --old-sidecar "$PMJ_OLD/structured/format_diagnostic_v1/FORMAT_DIAGNOSTIC_PRIVATE.jsonl" \
  --out /tmp/pmrl1-sc36-replay-analysis
"$PMJ_PY" project/scripts/rl1v3/journal_sc36_source_contract.py \
  --package "$PMJ_PKG" --root "$PMJ_SC" \
  --out /tmp/pmrl1-sc36-replay-source-contract
```

计量同时核对真实批准、计划、日志链、物理start/return/validate、原payload及36个新旧成本配对。预期新输入26873、输出1862、生成146.587755秒，两作业合计287.618698秒。mask计时属于生成内的processor墙钟，包含token同步；不能再加一次或视为净增量延迟。

答案值BASE11/18、RAW18/18；严格任务9/18、16/18，BASE→RAW严格修复7、保持成功9、保持失败2、退步0。源契约侧车只定位1处HTML实体、2处元数据引用、1处短引文缺required literal，以及元数据案例中1处说话人不匹配；类别有重叠，不能求和为独立错误。它不修复文本、不改变旧严格分。

主分析活跃版本为`analysis-v2`，只将布尔事件的计数字段从“pass/fail”改为“发生/未发生”，原`analysis-v1`保留；所有原始评分和计数值不变。源契约诊断为`source-contract-v1`，不是另一个成功评价器。

公开导出使用显式白名单：

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_publish_sc36.py \
  --root "$PMJ_SC" --out /tmp/pmrl1-sc36-replay-public
```

数据hash见[SC36_EXPORT_MANIFEST.json](sc36_results_v1/SC36_EXPORT_MANIFEST.json)。C1独立复算命令及6项新增测试见[C1报告](C1_DIMENSIONS_AND_SEQUENTIAL_ZH.md)。完整Journal CPU回归仍使用上一轮[环境变量](REPRODUCE_SELECTION_ZH.md#5-cpu测试及结构化独立诊断)，不把测试通过当成研究假设成立。

执行前兼容检查脚本为`journal_check_structured_constrained_compatibility.py`；其真实CPU凭据已公开。本轮没有为复跑报告重新载入模型、重新运行SC36或变更已冻结worker。

## 最终CPU回归与历史保护

本轮完整Journal回归实际为**307通过、0失败、0错误、0跳过，9.682秒**。使用上文CUDA空设备与固定栈，另按上一轮复跑文件设置所有既有私有fixture变量，并加入：

```bash
export SELECTIVE_MEMORY_VALIDATION_PRIVATE="$PMJ_SC/independent-memory"
"$PMJ_PY" -m pytest -q project/tests/test_rl1v3_journal*.py \
  --junitxml=/tmp/pmrl1-sc36-replay-tests.xml
```

新增覆盖包括C1配对未知、SC36真实计量契约、选择包旧授权拒绝/完整配对、真实时间合法读口，以及额外错误断言和参考争议不能伪成功。新评价记录程序的修复在生成前完成，原任务和30个payload不变，不代表语义判断获得资格。

上一轮334项输入清单、359项归因保护清单各自逐文件核对均0变化（两清单重叠，不相加），原scorer、collector、两份S36原输出也未变。公开[CPU与保护凭据](sc36_results_v1/CPU_REGRESSION_AND_PRESERVATION_PUBLIC.json)保留计数和hash；它是本次受影响证据的核验，不是重开J00资产审计。下一批只读CPU重建和最终唯一申请见[独立Memory文档](INDEPENDENT_MEMORY_VALIDATION_ZH.md)。
