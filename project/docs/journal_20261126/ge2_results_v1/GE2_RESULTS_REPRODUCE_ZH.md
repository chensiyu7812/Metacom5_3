# GE2 实际结果的只读复算与交付边界

本说明对应从 `5440d422110c57cba6567fca216383cd86e838de` 追加的真实GE2结果。四包已完成，**以下仅复算原日志、坐标和既有审阅，不再次生成、不取得新GPU授权**。不能重新运行原run脚本、删除原claim或使用未花完调用数。原代码、任务和评价结果均保留。

公开仓库包含新分析代码、无正文的37终局表、配对差、聚合、哈希和说明。RAW、gold、原始完整回复、语义审阅跨度和方法盲键只在原有权限的本机保存。单个journal Git提交不足以重建A/B/G组合栈及私有来源；没有宣称公开一条命令可复现完整模型实验。

## 1. 原执行身份与产物

|身份|SHA256/说明|
|---|---|
|packages-v2清单文件|`2fb7ae94eda42068e8f2fd0e4fff1c36cc18bcc9e780e3addbe2a17ae4ae5c2d`|
|冻结执行器inventory对象|`c8bdfa61b536635687b11442e459cfdc0630ae064adcf13324a7deb5707e21e4`|
|原控制合同对象|`02b6b443adeacb08dba131a000d0f0c47083db5a721645892fd329e845525684`|
|本轮明确批准记录文件|`e23f629e6d4a70702070cc7df823dcb9792337204d65b0f3fb4d8723dda4c11d`|
|原来源包manifest|`a9fe74c2d3caf4ea0cd889d7a393146b3d4a52d39aeb5c57f5c3c685d5f2b535`|
|原模型|Gemma-4-12B-it revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`，HF，原decode|
|指定GPU|`GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`，无换卡/干预其他项目|

四份plan对象与request文件SHA沿用[原申请](../GE2_RUN_REQUEST_ZH.md)。[冻结执行闭包](../ge2_v1/EXECUTOR_DEPENDENCY_PUBLIC.json)记录631代码文件及81 vendor文件，链接原A/B/G来源；本次新增分析模块不导入到执行器，也未改执行器内任何文件。CPU分析使用本机旧组合栈的journal链接，实际GPU使用冻结的独立副本，两者不能混称单一HEAD。

原包根为 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-20261126`（下称O）。本轮结果根为 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-results-20261126`（下称R）。

|R中的目录/文件|内容与验证作用|
|---|---|
|`authorization-v1/`|真实批准证据、四份包级批准、执行前独立准入回执|
|`GE2-1_run-v1` 至 `GE2-4_run-v1`|每包恰好一个job目录；原编号JSON日志、SUMMARY、不可覆写返回和claim|
|`coordinate-audit-v1/`|生成前来源坐标、旧/新覆盖并列、私有原文定位|
|`CURRENT_SOURCE_SEMANTIC_REVIEW_PRIVATE.jsonl`|生成前12个可见话轮的当前自述/引文/提问身份审阅|
|`collection-final-v1/`|59实际调用、37完整轨迹，逐条验证原日志链、返回、EOS和测量；技术层尚未作语义审阅|
|`actual-supply-v1/`|37终局真实payload的坐标重建；22次实际控制观察绑定；完整私有逐原子供应|
|`blind8-actual-v1/`|原G01/G04八输出盲审材料，与原选择和实际输出绑定；未复制方法key|
|`blind8-review-v1/`|助手遮蔽审阅、原文跨度与封存manifest；后解盲，不是独立人评|
|`root-common-review-v1/`|其他29条具名助手开发审阅，原合同验证及暴露身份|
|`analysis-final-v1/`|原37条审阅与实际测量合并；完整私人回复报告、公开逐题表/配对/聚合|
|`posthoc-payloads-v1/`|原query固定窗口payload比较、G07全部8个观察后展开候选的CPU可达性|
|`mechanism-final-v1/`|原实际动作/窗口角色/停止原因/控制状态的可复算诊断，无新增标签|

完整私有回复报告路径为：

`/opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-results-20261126/analysis-final-v1/COMPLETE_TASKWISE_REPLIES_PRIVATE.md`

其中逐题列出全部原始G文本、可见输入、真实动作、供证坐标和原审阅。私有源和审阅不随Git推送；公开数据中的SHA只作身份绑定。日志中所有时间戳使用同一boot的CLOCK_MONOTONIC，客户端/有效语音字段为null。

## 2. CPU复算

输出路径必须是新目录；如果已有同名目录，选择新名字，不能删除旧结果或覆盖。使用既有Python环境，不安装或升级冻结推理依赖。以下命令不加载模型权重。

```bash
cd /home/tokkio/Metacom5_3-journal
export GE2_ORIGINAL=/opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-20261126
export GE2_RESULT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-results-20261126
export GE2_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
export GE2_RUNTIME_PY=/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python
export GE2_ANALYSIS_STACK=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
export PYTHONPATH="$GE2_ANALYSIS_STACK"
export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
```

首先从原实际执行日志重新收集，而非读取job FINISHED就假设成功：

```bash
"$GE2_PY" project/scripts/rl1v3/journal_collect_ge2_results.py \
  --package "$GE2_ORIGINAL/packages-v2" --root "$GE2_RESULT" \
  --bundle "$GE2_ORIGINAL/source-bundle-v2" \
  --out "$GE2_RESULT/reproduce-collection-01"
```

校验包括前条文件SHA链、单调时间、plan/请求/输出绑定、EOS和实际token、原始终局输入、37个原槽的执行状态；后续单独使用原源坐标构建实际G消息：

```bash
"$GE2_PY" project/scripts/rl1v3/journal_audit_ge2_actual_supply.py \
  --collection "$GE2_RESULT/reproduce-collection-01" \
  --bundle "$GE2_ORIGINAL/source-bundle-v2" \
  --current-review "$GE2_RESULT/CURRENT_SOURCE_SEMANTIC_REVIEW_PRIVATE.jsonl" \
  --out "$GE2_RESULT/reproduce-supply-01"
```

生成前旧substring与严格坐标并列的复算入口如下；它读取原CPU条件和预先具名审阅，不读取G输出：

```bash
"$GE2_PY" project/scripts/rl1v3/journal_audit_ge2_source_coordinates.py \
  --bundle "$GE2_ORIGINAL/source-bundle-v2" \
  --cpu "$GE2_ORIGINAL/cpu-final-v1" \
  --current-review "$GE2_RESULT/CURRENT_SOURCE_SEMANTIC_REVIEW_PRIVATE.jsonl" \
  --out "$GE2_RESULT/reproduce-coordinates-01"
```

实际机制诊断及CPU候选比较（后者仅使用原生tokenizer，不推理）：

```bash
"$GE2_PY" project/scripts/rl1v3/journal_ge2_mechanism_diagnostics.py \
  --collection "$GE2_RESULT/reproduce-collection-01" \
  --bundle "$GE2_ORIGINAL/source-bundle-v2" \
  --out "$GE2_RESULT/reproduce-mechanism-01"
"$GE2_RUNTIME_PY" project/scripts/rl1v3/journal_ge2_posthoc_payloads.py \
  --collection "$GE2_RESULT/reproduce-collection-01" \
  --bundle "$GE2_ORIGINAL/source-bundle-v2" \
  --current-review "$GE2_RESULT/CURRENT_SOURCE_SEMANTIC_REVIEW_PRIVATE.jsonl" \
  --plan "$GE2_ORIGINAL/packages-v2/batch-01/PLAN.json" \
  --out "$GE2_RESULT/reproduce-payloads-01"
```

汇总原37条既有语义审阅，重新运行原validator及配对/nearest-rank计算：

```bash
"$GE2_PY" project/scripts/rl1v3/journal_summarize_ge2_results.py \
  --root "$GE2_RESULT" --original "$GE2_ORIGINAL" \
  --out "$GE2_RESULT/reproduce-analysis-01"
```

该汇总入口使用R中固定的 `collection-final-v1 / actual-supply-v1 / blind8-review-v1 / root-common-review-v1`。先与前述复算的无正文结果核对相等，再汇总；不能把新写语义意见静默替换封存审阅。输入缺失则失败，不用覆盖率或自动unknown填满。重复运行只复现已有观察的计算，不是一次新的独立资格测试。

固定八输出材料的绑定入口为 `journal_bind_ge2_blind_outputs.py --frozen "$GE2_ORIGINAL/evaluation/blind8-v2" --collection "$GE2_RESULT/collection-final-v1" --out 新私有目录`。它只复制原共同源包并绑定真实返回，不产生评审结果。真人身份和暴露必须如实记录；本轮没有真人裁决。

## 3. 有限CPU验证和公开复核

本轮13项来源坐标反例测试通过：错speaker、错turn、错record、Unicode字符/字节、问答组缺上下文、未知保留及当前文字身份等。复跑：

```bash
PYTHONPATH=project/src "$GE2_PY" -m pytest -q \
  project/tests/test_rl1v3_journal_ge2_source_coordinates.py
```

另外核对原冻结四包身份、37真实payload、22实际观察及37审阅记录。只检查本轮新产物和既有包身份，没有重开J00/G0e/E6/A0或全量Judge盘点。[验证回执](VALIDATION_PUBLIC.json)区分程序验证和语义资格；测试通过不能证明研究假设成立。

不具备私有数据访问权限时，可直接从[逐格表](ENDPOINTS_REVIEWED_PUBLIC.jsonl)重算完成区间与时间：按method分组，分别求 `quality.complete_interval` 两端之和；将实际纳秒除1e9后排序，P50/P95取 `ceil(q*n)-1` 索引。缺测不能填0，U不变成失败。各题/各普通臂都有原37格记录；Direct只含5题。正式语义结论还需检查私有原文和参考，公开聚合不能独立证明它们。

新增代码文件、公开数据、报告以及私有输入manifest SHA见[交付清单](DELIVERY_MANIFEST_PUBLIC.json)。已对待提交文件检查RAW/gold/回复长文本泄漏；哈希、别名和计数不替代完整复现材料。本轮结果只追加到独立journal分支，PR #28与原A/B/G冻结执行器保持不变。
