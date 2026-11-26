# GE2 复跑、依赖与证据边界

本轮从 `48fdb54a683b51c9d5f77c98784a7b4f68b66d35` 追加文件。实际科研结果是来源检查、原输出只读重算和CPU执行验证，新增真实模型调用为0。运行申请只认 `packages-v2`，见[固定申请](GE2_RUN_REQUEST_ZH.md)。以下CPU命令不会取得GPU授权；所有输出目录必须是新的，不能覆盖这里列出的冻结产物。

## 可复现范围

Git中提交代码、聚合/逐题去文本统计、哈希与说明，不含RAW、gold、完整回复或私有审阅表。单独下载本Git提交可检查代码与公开计算，但不能复现依赖私有来源的运行。具有原合法数据访问权限的本机研究者可用以下冻结输入复跑；不需要重新获取或审计J00资产。

新冻结执行器是旧A/B/G组合栈的独立复制，加本轮GE2模块，并非一个journal Git提交天然包含全部依赖。[新闭包](ge2_v1/EXECUTOR_DEPENDENCY_PUBLIC.json)列出631个代码文件、81个vendor文件及SHA，链接[原A/B/G版本清单](system_review_v1/DEPENDENCY_MANIFEST_PUBLIC.json)与[原逐文件闭包](system_review_v1/COMPLETE_CODE_FILE_CLOSURE_PUBLIC.json)。模型、tokenizer、HF与原生语法库沿用原绑定；没有改旧执行器或重新进行G0e/E6资格实验。

|输入/产物|本机位置，相对于 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-20261126/`|身份/用途|
|---|---|---|
|生成前任务选择|`sources/SELECTION_PRIVATE.json`|SHA `f3a8d73453d5609c3fd41fc4cbe02644c556152ba5c77515c4e89128c3974a6c`|
|生成前共享检索冻结|`sources/RETRIEVAL_CONFIG_FREEZE.json`|SHA `23d7252d717693d5867d5bcd37751c2245c0f7c069adf185c6386d4b99b840bf`|
|最终来源包|`source-bundle-v2/MANIFEST_PRIVATE.json`|SHA `a9fe74c2d3caf4ea0cd889d7a393146b3d4a52d39aeb5c57f5c3c685d5f2b535`，绑定runtime、envelope、eval、Direct坐标及46题CPU输入|
|最终共同池检索计算|`cpu-final-v1/MANIFEST_PRIVATE.json`|SHA `27f875eedfbba50f6df9c9719731ea6b73b27e7579b2298afd37ba32bd54e2c4`；输入和执行脚本SHA可复核|
|实际来源/原生tokenizer传输检查|`runtime-frozen-v2/CPU_CHECK_PUBLIC.json`|37个非模型终局槽；不提供生成质量或模型延迟|
|冻结执行器准入|`FROZEN_ADMISSION_V2_PUBLIC.json`|四包check通过，旧批准拒绝；设备访问和真实调用为0|
|有限盲评准备|`evaluation/blind8-v2/`|G01/G04四普通臂共8输出，输出尚不存在，评审者未指派，未完成人评|
|原SC36只读重算|`evaluation/sc36-recheck-v2/`|36条旧模型输出、原严格evaluate函数，未修改评分器|
|T03两原hit联合供证|`t03-union-v1/`|原MIDSTATE4仅CPU恢复，无新增生成分支|
|唯一申请包|`packages-v2/CATALOG.json`|SHA `2fb7ae94eda42068e8f2fd0e4fff1c36cc18bcc9e780e3addbe2a17ae4ae5c2d`|

任务选择规则在新ranking前写入 `sources/SELECTION_RULES_PRIVATE.json`：官方30题按原capability分IE/TR/Abstention，各取 `SHA256('ge2-selection-v1|'+original_task_id)` 最小者；自然前缀取既有来源诊断P08/P05及P06/P07的最小case hash；联合任务取原SMV五个joint任务的最小两个task hash。自然条件使用完整实际pre-supporter前缀，不沿用旧人工单句要求。原始来源已开发暴露；不声称独立确认性样本。选择文件、原规则与私有选取脚本保留，规则不读取生成输赢。

源构建脚本 `journal_prepare_ge2_sources.py --help` 明确所需selection、design、resources、metadata、memory、audit、pomdp-bundle、joint-bundle、base-plan和asset-manifest；它复用既有私有来源。复算本轮结果应直接使用上述已经冻结的v2来源包，而非重选题或改写gold。初版来源表漏计当前请求已有事实的准备产物全部保留；最终G07当前1/2、G08当前2/2修正只用于新GE2来源诊断，不改变历史模型评价。

## CPU复跑

在仓库根目录运行，示例使用尚不存在的 `reproduce-*` 目录。若目录存在，另取一个名字；不能删除旧结果以复跑。

```bash
cd /home/tokkio/Metacom5_3-journal
export GE2_ROOT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-20261126
export GE2_PY=/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python
export GE2_EX="$GE2_ROOT/packages-v2/executor"
export GE2_OLD_PLAN=/opt/tokkio-data0/tokkio_runs/pmrl1-j-dynamic-20261126/packages-v2/batch-01/PLAN.json
export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$GE2_EX/project/src:$GE2_EX/vendor_dynamic_controller"
```

真实来源、共同合法池与同返回量检索诊断（没有模型权重）：

```bash
"$GE2_PY" project/scripts/rl1v3/journal_compare_ge2_sources.py \
  --bundle "$GE2_ROOT/source-bundle-v2" \
  --config-freeze "$GE2_ROOT/sources/RETRIEVAL_CONFIG_FREEZE.json" \
  --base-plan "$GE2_OLD_PLAN" \
  --asset-manifest project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json \
  --out "$GE2_ROOT/reproduce-retrieval-01"
```

结果有108行（原46题加冻结8题的呈现×2检索器；其中3官方题重合）。`SUPPLY_DIAGNOSTICS_PRIVATE.jsonl` 保留每个来源群及实际取回内容，`COUNTS_PUBLIC.json`是汇总，不能把其中的完整供证字段当作任务成功。无ranking-cache才是重新运行CPU检索；CPU时间会变化。

原生控制语法及真实来源动态接线检查：

```bash
"$GE2_PY" "$GE2_EX/project/scripts/rl1v3/journal_check_ge2_controller.py" \
  --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 \
  --vendor "$GE2_EX/vendor_dynamic_controller" \
  --out "$GE2_ROOT/reproduce-controller-01.json"
"$GE2_PY" "$GE2_EX/project/scripts/rl1v3/journal_check_ge2_runtime.py" \
  --bundle "$GE2_ROOT/source-bundle-v2" --original-plan "$GE2_OLD_PLAN" \
  --out "$GE2_ROOT/reproduce-runtime-01"
```

前者以真实tokenizer/xgrammar检查有限合法路径、EOS与原抑制规则的finite交集，不加载G。后者经过真实Ledger/Port、同worker输入验证及全部37终局槽，返回明确标识的CPU fixture；另注入两条控制协议失败检查原终局fallback与后续独立请求。所有 `formal_reward` 为空；不能把fixture回复当模型结果。单位测试覆盖状态身份、语义改写、上下文/去重/句柄、截止时间、动作及评审记录约束：

```bash
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  project/tests/test_rl1v3_journal_ge2.py \
  project/tests/test_rl1v3_journal_ge2_runtime.py \
  project/tests/test_rl1v3_journal_ge2_evaluation.py
```

单位测试使用现有Python 3.11测试环境；Python 3.12运行环境未安装pytest，不为此修改冻结环境。真实tokenizer、语法、动态传输及准入检查使用上述实际Python 3.12运行环境。

冻结包只读check，不进行GPU探测或模型加载：

```bash
for GE2_BATCH in 01 02 03 04; do
  "$GE2_PY" "$GE2_EX/project/scripts/rl1v3/journal_ge2_run.py" check \
    --plan "$GE2_ROOT/packages-v2/batch-$GE2_BATCH/PLAN.json"
done
```

原T03两hit补充检查（保持旧重复证据、原动作与预算）：

```bash
"$GE2_PY" project/scripts/rl1v3/journal_ge2_midstate_union.py \
  --plan /opt/tokkio-data0/tokkio_runs/pmrl1-j-system-review-20261126/midstate/package-v4/PLAN.json \
  --out "$GE2_ROOT/reproduce-t03-01"
```

SC36复算入口为 `journal_ge2_evaluation.py structured-recheck`，传原 `structured_learning.py`、SC1/SC2的两份 `PLAN_CONSTRAINED.json` 和 `ENDPOINTS_CONSTRAINED_PRIVATE.jsonl`。所有精确路径及SHA已在[只读回执](ge2_v1/SC36_RECHECK_PUBLIC.json)中；入口读取同一evaluate函数，无输出清洗或评分放宽。`freeze --bundle source-bundle-v2 --out 新目录` 可复现本轮预先固定的8输出方法标签遮蔽审阅准备；它不能生成真人判断。

公开投影使用 `journal_export_ge2_cpu.py --root "$GE2_ROOT" --out 新目录`，读取固定 `cpu-final-v1` 和v2来源，只导出允许字段。私有逐题正文、gold、审阅材料及实际中间观察不应进入Git。

## 生成执行与停止

当前没有GE2或MIDSTATE4新批准。不得把上述CPU命令、批准模板或旧授权当作执行许可。研究者明确批准[本包身份](GE2_RUN_REQUEST_ZH.md)后，逐包使用 `packages-v2/batch-0N/RUN_AFTER_NEW_APPROVAL.sh`，传实际批准记录和全新输出目录；脚本只允许该包一次加载、0 warmup/0 retry、1200秒，设备守卫仍可阻止启动。不把CPU时的空CUDA变量带入运行脚本，不更换原指定设备。

实际生成后应按原任务四臂配对报告：有效证据与不足/争议、明确事实与自然支持、获取/STOP原因、技术降级、完整在线时间和终局内部首非空文字。单请求协议fallback不隐去失败；无剩余合法行动、时间/容量拒绝与主动STOP分列。客户端首文本、首段有效语音仍未测。旧STOP输出和CPUfixture均不能替代新分支延迟。

**停止边界不变：**强静态或OneShot解释全部收益就停止本版本序贯优越性主张；完整Direct供证仍有可复核执行错误，才提出原有那一次独立Step-2对照。尚无证据支持训练自然支持reward、BC/PPO或新Generator。
