# DYNAMIC88：CPU 复跑与私有证据位置

基于 `f2d59f1c42de672c0785e034dbbd76e424f5529e`；本交付是独立分支上的新增文件，未改旧输出/评价。公开代码、匿名统计、合同及 SHA；原文、完整问题/回复、gold、来源家族绑定及私人评审留在数据卷。下列 CPU 命令不加载模型权重；全部输出使用新目录，不覆盖既有结果。

## 1. 已有输出的计时复算

完整命令、原计量范围和逐题表见 [SMV_LATENCY_RESULTS_ZH.md](dynamic_v1/SMV_LATENCY_RESULTS_ZH.md)。实际两次复算位于 `pmrl1-j-dynamic-20261126/latency/analysis-v1` 和 `reproduce-v1`；SUMMARY/TASKWISE 字节一致。核对原 107 份输入/日志和 30 个完整输出对象，未重新评价。

## 2. 最终冻结执行器的真实来源 CPU 回放

在仓库根运行；最后一项 `--out` 改为尚不存在的目录。此命令用确定性协议 fixture 代替模型返回，真实执行来源、工具、打包和 tokenizer，不声称模型生成。

```bash
PMJ_RUNS=/opt/tokkio-data0/tokkio_runs
PMJ_PACKAGE="$PMJ_RUNS/pmrl1-j-dynamic-20261126/packages-v2"
export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$PMJ_PACKAGE/executor/project/src:$PMJ_PACKAGE/executor/vendor_dynamic_controller"
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/journal_check_pomdp_dynamic_cpu.py \
  --bundle "$PMJ_RUNS/pmrl1-j-pomdp-20261126/cases/bundle-v1" \
  --cpu "$PMJ_RUNS/pmrl1-j-pomdp-20261126/engineering/cpu-v2" \
  --proposal "$PMJ_RUNS/pmrl1-j-pomdp-20261126/engineering/proposal-v2-wording" \
  --resources "$PMJ_RUNS/pmrl1-j-20261125/memory/resources_private.jsonl" \
  --metadata project/outputs/pm_rl1/v3/A1_preparation/final/registry/registry.json \
  --base-plan "$PMJ_RUNS/pmrl1-j-sc36-20261126/independent-memory/packages-v3/batch-01/PLAN.json" \
  --asset-manifest project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json \
  --out "$PMJ_RUNS/pmrl1-j-dynamic-20261126/frozen-executor-replay-new"
```

本次已实际运行目录为 `frozen-executor-cpu-v1`，原收据、全部请求/事件、确定输入读回及逐包轨迹均保留在该目录，stdout 为同层 `FROZEN_CPU_STDOUT.log`。公开结果见 [FROZEN_EXECUTOR_CPU_CHECK.json](dynamic_v1/FROZEN_EXECUTOR_CPU_CHECK.json)；四个模块 SHA 与 packages-v2 的实际冻结代码相同。

## 3. 独立 CPU 准入

以下 `check` 只读身份和预算，不能启动 GPU，也不建立一次运行 claim。DR1–DR4 分别对应 `batch-01` 至 `batch-04`。

```bash
PMJ_PACKAGE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-dynamic-20261126/packages-v2
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PMJ_PACKAGE/executor/project/src:$PMJ_PACKAGE/executor/vendor_dynamic_controller" \
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  "$PMJ_PACKAGE/executor/project/scripts/rl1v3/journal_pomdp_dynamic_run.py" \
  check --plan "$PMJ_PACKAGE/batch-01/PLAN.json"
```

全部四包已在 CPU 测试中检验；最终冻结 CLI 的四包独立检查收据见本次私有 `FROZEN_ADMISSION_CPU.json`。未批准模板的 run 在设备检查前被拒绝，这个拒绝也作为 CPU 检查保存。审批必须绑定 catalog 文件、具体计划对象、严格预算、设备以及实际研究者决定文本 bytes；旧 SMV/SC36 授权无效。不要将 `APPROVAL_TEMPLATE.json` 的 false 改为 true 来假冒批准。

## 4. 全 Journal 回归

私有环境变量只提供冻结 CPU 输入，不含任何模型运行指令。去掉其中变量会跳过某些实际资源检查，因此不能把缺数据的结果当作这里的完整 429 项验证。

```bash
PMJ_RUNS=/opt/tokkio-data0/tokkio_runs
export CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$PMJ_RUNS/pmrl1-j-20261125/stack/project/src"
export JOURNAL_RS_OUTPUT="$PMJ_RUNS/pmrl1-j-20261125/rs/candidates-v1"
export JOURNAL_RS_FOLLOWUP="$PMJ_RUNS/pmrl1-j-evidence-20261125/rs"
export JOURNAL_RS_COMPLEX="$PMJ_RUNS/pmrl1-j-capability-20261125/rs_complex/package-v2"
export JOURNAL_RS_BATCH_REVIEW="$PMJ_RUNS/pmrl1-j-capability-20261125/batch18_rs_review"
export JOURNAL_KEYCAP_RS="$PMJ_RUNS/pmrl1-j-keycap-20261125/rs_r1/final"
export JOURNAL_CLOSEOUT_RS="$PMJ_RUNS/pmrl1-j-closeout-20261125/rs_review/combined-v1"
export JOURNAL_JOINT_PACKAGE="$PMJ_RUNS/pmrl1-j-terminal-20261125/joint/packages-v5"
export JOURNAL_JOINT_BUNDLE="$PMJ_RUNS/pmrl1-j-terminal-20261125/joint/source-bundle-v1"
export SELECTIVE_MEMORY_VALIDATION_PRIVATE="$PMJ_RUNS/pmrl1-j-sc36-20261126/independent-memory"
export POMDP_SOURCE_CASES_PRIVATE="$PMJ_RUNS/pmrl1-j-pomdp-20261126/cases"
export POMDP_DYNAMIC_PACKAGES_PRIVATE="$PMJ_RUNS/pmrl1-j-dynamic-20261126/packages-v2"
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  project/tests/test_rl1v3_journal*.py \
  --junitxml=/tmp/pmrl1-dynamic-journal-tests-new.xml
```

本次实跑为 429 通过、0 失败/错误/跳过，12.958 秒；原 XML 在 `pmrl1-j-dynamic-20261126/CPU_TESTS_FINAL.xml`。这不含真实 GPU 数值、吞吐、模型动作合法率或用户任务成功率。

## 5. native grammar 与包重建

native tokenizer、36 条路径/488 个前缀及 9 项边界检查命令见 [CONTROLLER_PROTOCOL_AND_LATENCY_ZH.md](dynamic_v1/CONTROLLER_PROTOCOL_AND_LATENCY_ZH.md)，最终私有目录 `protocol/native-v3`。不调用 `generate()`，不加载权重。原三元组限制与新共同协议的结果分别保留。

如需复建包，在新目录运行以下命令。包包含绝对路径，换输出路径会产生**新的**计划/catalog SHA；复建只检验流程，不自动取得已冻结包身份或未来运行授权。

```bash
PMJ_RUNS=/opt/tokkio-data0/tokkio_runs
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PMJ_RUNS/pmrl1-j-20261125/stack/project/src" \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  project/scripts/rl1v3/journal_prepare_pomdp_dynamic.py \
  --repo "$PWD" \
  --prior "$PMJ_RUNS/pmrl1-j-pomdp-20261126/engineering/proposal-v2-wording" \
  --bundle "$PMJ_RUNS/pmrl1-j-pomdp-20261126/cases/bundle-v1" \
  --cpu "$PMJ_RUNS/pmrl1-j-pomdp-20261126/engineering/cpu-v2" \
  --original-plan "$PMJ_RUNS/pmrl1-j-sc36-20261126/independent-memory/packages-v3/batch-01/PLAN.json" \
  --constrained-plan "$PMJ_RUNS/pmrl1-j-selection-20261126/structured/packages-v3/batch-01/PLAN_CONSTRAINED.json" \
  --asset-manifest project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json \
  --out "$PMJ_RUNS/pmrl1-j-dynamic-20261126/packages-rebuild-new"
```

活动 `packages-v2` 不再原位重建；早期失败的 v1 保留。没有模型重跑。

## 6. 获批后的入口与权限边界

只有收到研究者针对 [运行申请](DYNAMIC88_RUN_REQUEST_ZH.md)的新批准，才保存决定原文并写独立批准文件。每包已有单独 `RUN_AFTER_NEW_APPROVAL.sh`，接受批准文件与一个新数据卷输出目录；它不串联其他包，不自动续跑。监督器在模型/设备访问前验证批准，随后保留原设备、空间和独占守卫。不要用这里的 CPU 环境（尤其空 CUDA 可见设备）直接充当真实作业环境。

真实结果留私有；公开只交付逐题匿名结果、计量、错误归因、合同和复跑说明。最终交付清单 [DYNAMIC88_DELIVERY_MANIFEST.json](DYNAMIC88_DELIVERY_MANIFEST.json)覆盖本轮新增公开文件。此清单证明身份和可复算性，不证明科学假设。
