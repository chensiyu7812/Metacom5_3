# 系统研究审查复跑与私有边界

起点 `c40b90c99cb991cf1c2793ffbe9927a0011885ab`。本轮所有检查是CPU；4次MIDSTATE模型申请尚未授权。不要执行旧DR脚本或用旧审批填写新批准文件。原PR #28与所有A/B/G冻结分支未合并。

## 1. 可仅用公开提交复算的部分

```bash
python project/scripts/rl1v3/journal_review_dynamic_latency.py \
  --source project/docs/journal_20261126/dynamic_results_v1 \
  --out /tmp/pmrl1-system-first-text-new
```

只用标准库，输入为原公开48端点、53调用、4作业和48条旧质量联结。输出首文字/完整回复计量、36个共同任务配对差及24个事后选择，不载入模型、不给正式reward。新目录必须不存在。本轮还从私有原始38个输出观察器时间戳独立复算，公开回执为 `system_review_v1/FIRST_TEXT_CLOCK_VALIDATION_PUBLIC.json`。

## 2. 依赖组合，不是单一Git提交

本机组合栈根为 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack`；其原 `DEPENDENCY_MANIFEST.json` 声明 base/A/B/G来源及每文件SHA。journal目录是本工作树的软链接，实际GPU运行则使用另行复制并冻结的executor。不得将当前工作树的新模块说成旧DR当时已加载。

公开[完整代码文件闭包](system_review_v1/COMPLETE_CODE_FILE_CLOSURE_PUBLIC.json)逐项列出531组合栈文件、613原DR执行文件和81 vendor文件；[依赖与环境清单](system_review_v1/DEPENDENCY_MANIFEST_PUBLIC.json)列出关键模块解析路径、具体提交、模型小文件/历史权重SHA依据以及两环境所有已安装distribution。安装列表不等于全部实际import。软件包文件、模型和受限来源需在本机单独具备，不能仅凭公开HEAD宣称完整复现。

来源与机制复算命令分别完整列于[代码审查](system_review_v1/CODE_AND_STACK_REVIEW_ZH.md#5-计量与复跑边界)、[数据审查](system_review_v1/DATA_FIT_AND_SOURCE_DIAGNOSTICS_ZH.md#6-复跑身份与公开边界)。两者只读开发缓存，输出必须新建；原封存测试正文不参与。无需下载新模型或读取权重。

## 3. 新4次申请的CPU准入

最终身份是 `midstate/package-v4`。v1–v3为准备过程的保留版本；没有任何版本实际生成过模型回复。四个payload和动作身份从初版至最终版保持；最终requests文件因源回执计量、封装检查及日志合同变化而有新SHA，审批只认v4。

```bash
export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1
PMJ_MID=/opt/tokkio-data0/tokkio_runs/pmrl1-j-system-review-20261126/midstate/package-v4
export PYTHONPATH="$PMJ_MID/executor/project/src"
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  "$PMJ_MID/executor/project/scripts/rl1v3/journal_run_pomdp_midstate.py" check \
  --plan "$PMJ_MID/PLAN.json"
```

协调者已使用冻结executor与实际Python 3.12独立执行此命令，结果为4 requests、2 states、0 model loads/calls、authorized=false。12项专名CPU测试覆盖恢复、动作顺序、无重试、旧授权拒绝和计时边界；实际源路径的4个transport fixture返回明确标为非模型，不参与质量或延迟结果。它们说明执行包可检查，不证明展开有效。

首次实际生成需要研究者绑定[固定申请](system_review_v1/MIDSTATE4_RUN_REQUEST_ZH.md)中的plan对象SHA、requests SHA和执行器身份另行批准。最多4 terminal、1 load、0 warmup/controller/retry、1200秒；没有已获授权的自动后续。

## 4. 私有材料与公开投影

本轮私有根：`/opt/tokkio-data0/tokkio_runs/pmrl1-j-system-review-20261126`。

|目录|实际材料|公开边界|
|---|---|---|
|`latency-v1`|公开输入的独立首字/质量—时间复算|计量与匿名逐题结果公开|
|`engineering/review-v3`|代码版本、环境、原事件聚合及synthetic机制反例|代码/SHA/版本/聚合公开，无源正文|
|`sources/cpu-final-v1`|原始前缀、query、完整候选、原文与评价侧引用的分离诊断|只公开计数、匿名情境和类型覆盖|
|`sources/fixed-expand-audit-v1`|先固定选择，再核4候选必要引用群，保留完整源定位|仅 `COUNTS_PUBLIC.jsonl` 复制为 `MIDSTATE_EXPAND_EVIDENCE_PUBLIC.jsonl`|
|`sources/SMV15_LIMITED_READBACK_PRIVATE.json`|单条既有完整供证失败的实际输入/输出/评价身份|仅公开原判断的有限说明和receipt SHA|
|`midstate/package-v4`|完整状态、4真实来源payload、候选和CPU fixture事件|plan身份、token/源计数、申请公开；RAW/任务全文/私有评价不公开|

旧DR真实48槽/53调用、四作业逐事件、原来源与原质量观察留在上一私有根，未覆盖。保护检查只核本次实际依赖清单，非J00重审。最终[验证回执](SYSTEM_REVIEW_VALIDATION_PUBLIC.json)及[新增交付清单](SYSTEM_REVIEW_DELIVERY_MANIFEST.json)记录本轮范围、身份与公开文件SHA。

## 5. 覆盖记录与限制

审查已覆盖用户列出的研究目标、计量、实际调用链、开发来源、两个中间状态及新机制方案；没有证明整个仓库无缺陷，也未做新语义裁判资格。以下数量只针对明确的核查对象，不是总准确率；类别可重叠，不能相加。0/N表示这些对象未观察到该类错误，不是全系统通过。

报告用途与完整性：

|Category|Observed defects|Assessment|
|---|---|---|
|指定交付主题|0/7|七项均有报告/代码/真实CPU依据；新模型结果不在本轮授权内|
|分析表达与边界|0/4|四主要维度分开，技术/语义/未知保留；没有把数据重放升级为长期效益|
|界面/交互|N/A|仓库Markdown及可复算数据，不是dashboard；无图形界面验收主张|

分析正确性与稳健性：

|Category|Observed defects|Assessment|
|---|---|---|
|关键计数与首字数值|0/9|53调用、48槽、6完整任务及6个指定P50逐项相符|
|端点首字时钟绑定|0/38|38真实端点从原时间戳复算；10缺失不补零|
|实际来源排序复算|0/36|36原查询Top2与冻结trace一致；敏感性改变不等于策略改善|
|复现的状态身份充分性|1/1|合法可达同hash异observation反例成立，旧实现保持，未来需新身份修订|
|因果/泛化资格|分母未知|不建立覆盖率或正确率；没有独立自然支持/长期转移验证，不能宣称完成科学资格|
|单提交完整复现|1/1|单journal HEAD不足；已补完整组合依赖清单，受限源/模型仍需本机资产|

需要修订的是未来机制与可支持的研究主张；原数据的计数与先前限定结论保持。所有未验证的质量影响明确保留未知，不以新增CPU测试数量替代研究进展。
