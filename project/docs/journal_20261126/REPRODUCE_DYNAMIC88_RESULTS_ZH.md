# DR1–DR4 实际结果：复跑说明

本轮起点 `cc900c40e8b3394ee4f74fe11d92e8faf483c8e2`，沿原 `packages-v2` 清单 `b2d8e16eb33fcbf304b3b5b314cb8240bfcc085ea0847d5cb8fe88893e50ccac`。研究者明确批准后，四个作业各运行一次，共 53 次实际模型调用。DR3 按冻结协议停机，不以其余未用调用上限补齐。

以下全部是 **CPU 只读原日志后写新目录的复算**，不会触发模型加载/生成或使用研究授权。输出目录必须尚不存在。不要重新执行四个 `RUN_AFTER_NEW_APPROVAL.sh`；旧审批和持久 claim 不能作为重试权限。

## 1. 私有原始证据与公开对应

私有根：`/opt/tokkio-data0/tokkio_runs/pmrl1-j-dynamic-results-20261126`。

|材料|位置|含义|
|---|---|---|
|批准原文及逐包绑定|`RESEARCHER_APPROVAL_PRIVATE.json`、`DR1_AUTHORIZED.json` 至 `DR4_AUTHORIZED.json`|实际用户批准文本与各冻结 plan/catalog SHA|
|不可覆盖日志与 SUMMARY|`DR1_run1/job-*` 至 `DR4_run1/job-*`|所有模型输入/输出、动作、时钟、失败与事件 SHA 链|
|最后收集|`collection-final-v1`|48 终局槽、53 调用、全部事件及四包计量|
|原始完整回复及逐项依据|`quality/review-v1/READBACK_PRIVATE.md`、`REVIEWS_PRIVATE.jsonl`|38 个真实终局审阅；另外10槽保留未评|
|开发质量复跑|`quality/REPRODUCE_PRIVATE.md`|原手工开发观察的绑定与重建，不冒充独立语义再评|
|最终质量—延迟联结|`analysis-v3`|逐题、同任务配对、共同完整六臂集合及特权包络|
|最终决策诊断|`decisions/observations-quality-v3`|停止、供源、质量连接与未决|
|真实中间状态精确匹配|`decisions/exact-final-v1`|两个 CPU 重建 payload 的字节、SHA 与既有终局匹配|
|独立根代理复算|`ROOT_RAW_RECOMPUTE.json`|直接读原事件 start/return/时间戳/token IDs，非复用收集器汇总|

公开文件位于 [dynamic_results_v1](dynamic_results_v1/)。只包含匿名计量、任务状态、合同哈希和聚合；不含 RAW、任务全文、gold、完整回复或私人评审。`QUALITY_TASKWISE_PUBLIC.jsonl` 的 Qnn 与联结表 Tnn 对应；实现按真实 task_id 和 SHA 连接，不依赖显示名称。

## 2. 收集与身份验证

在仓库根设置 CPU 环境。收集器只接受真正 `hf_dynamic_real` 的链和返回，拒绝上一轮 CPU fixture；核对计划、审批、事件链、请求/观察/payload/输出、native tokenizer 及同 boot 时间包含关系。EOS 控制返回但状态拒绝，仍保留为模型返回，不虚构 terminal。

```bash
PMJ_RUNS=/opt/tokkio-data0/tokkio_runs
PMJ_RESULTS="$PMJ_RUNS/pmrl1-j-dynamic-results-20261126"
export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$PMJ_RUNS/pmrl1-j-20261125/stack/project/src"
PMJ_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
"$PMJ_PY" project/scripts/rl1v3/journal_collect_pomdp_dynamic.py \
  --catalog "$PMJ_RUNS/pmrl1-j-dynamic-20261126/packages-v2/CATALOG.json" \
  --runs-root "$PMJ_RESULTS" \
  --out "$PMJ_RESULTS/collection-reproduce-new"
```

实际最终结果：53 start/return，terminal 38、OneShot 7、ToolAgent 8；38 terminal EOS、1 `path_technical_failure`、9 `unexecuted`。收集器没有语义评分。`collector-validation-v1/DR3_CONTROLLER_REJECTION_READBACK.json` 保留原 frozen parser 的一次 CPU 失败重现；没有重发模型请求。

## 3. 质量—延迟联结与表格

先沿 `quality/REPRODUCE_PRIVATE.md` 验证冻结开发观察；38 条观察和6个无效观察变异检查已通过，6个最终产物在实际复跑中逐字一致。此步骤检验引用/绑定与评价契约一致性，不给助手判断新增真人资格。

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_analyze_pomdp_dynamic.py \
  --collection "$PMJ_RESULTS/collection-final-v1" \
  --reviews "$PMJ_RESULTS/quality/review-v1/REVIEWS_PRIVATE.jsonl" \
  --out "$PMJ_RESULTS/analysis-reproduce-new"
"$PMJ_PY" project/scripts/rl1v3/journal_render_pomdp_dynamic_results.py \
  --analysis "$PMJ_RESULTS/analysis-reproduce-new" \
  --out "$PMJ_RESULTS/TASKWISE_REPRODUCE_NEW.md"
```

完整配对集合为 T01/T02/T03/T04/T07/T08；T05/T06 保留在48槽中，但不混入共同六臂分母。技术/未执行没有语义0，unknown保留区间；同任务、同 payload、同文本的共同语义不确定性在配对差中抵消，真实计时仍来自各自实际执行。P50/P95 使用 nearest-rank，不用 tokens 推时延。

早期 `ANALYSIS_STDOUT.log` 保留显示别名 Q/T 不同导致的联结拒绝；随后改用真实任务 ID 与不可变身份、分别校验显示别名的一一关系。`analysis-v2` 是中间统计，最终 `analysis-v3` 补充最佳固定区间、质量分层配对时间并把无终局供证值保留为空。没有修改输入、回复或开发判断。

## 4. 停止诊断与中间状态重建

```bash
"$PMJ_PY" project/scripts/rl1v3/journal_diagnose_pomdp_decisions.py \
  --collection "$PMJ_RESULTS/collection-final-v1" \
  --plan "$PMJ_RESULTS/decisions/DECISION_DIAGNOSTIC_PLAN.private.json" \
  --quality-review "$PMJ_RESULTS/quality/review-v1/REVIEWS_PRIVATE.jsonl" \
  --out "$PMJ_RESULTS/decisions/reproduce-new"
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/journal_check_pomdp_midstates.py \
  --collection "$PMJ_RESULTS/collection-final-v1" \
  --plan "$PMJ_RESULTS/decisions/DECISION_DIAGNOSTIC_PLAN.private.json" \
  --out "$PMJ_RESULTS/decisions/midstate-reproduce-new"
```

最后命令只载入 CPU tokenizer/config 与冻结 renderer，不载入权重。最多四状态的固定选择实际得到两个，均只有同 payload STOP 端点；没有继续分支就不产生最优动作标签。不用 Top4 从初始状态出发的终局冒充中间状态继续获取的反事实。

## 5. CPU 检查与保护

全 Journal 回归沿 [上一交付的CPU环境](REPRODUCE_DYNAMIC88_ZH.md#4-全-journal-回归)，并加：

```bash
export POMDP_DYNAMIC_RESULTS_PRIVATE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-dynamic-results-20261126
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  project/tests/test_rl1v3_journal*.py \
  --junitxml=/tmp/pmrl1-dynamic-results-tests-new.xml
```

实际本轮完整 XML 为 `CPU_TESTS_FINAL.xml`；包括原冻结资源环境测试、新收集器、决策诊断、缺失/共享未知处理及实际48槽联结。测试不重启任何GPU作业，也不验证科学假设成立。

最终 [DYNAMIC88_RESULTS_VALIDATION_PUBLIC.json](DYNAMIC88_RESULTS_VALIDATION_PUBLIC.json)记录实际计数、字节保护、复算与公开内容检查；[DYNAMIC88_RESULTS_DELIVERY_MANIFEST.json](DYNAMIC88_RESULTS_DELIVERY_MANIFEST.json)只覆盖本轮新公开文件。旧 cc900c40 清单、原运行计划/执行器、历史输出/评价均保持不变。
