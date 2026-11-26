# GSWS第一阶段复跑与交付边界

以下命令均为CPU，不能启动模型。需要本机已批准来源缓存、Gemma tokenizer和原GE2冻结依赖；公开Git提交不包含这些私有材料或权重。[依赖清单](gsws_phase1/DEPENDENCIES_PUBLIC.json)包括实际闭包SHA。不要使用指向旧journal的组合栈符号链接执行新代码。

```bash
GSWS_ROOT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-20261126
GSWS_REPO=/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws
GSWS_EX=$GSWS_ROOT/packages-v1/executor
GSWS_PY=/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python
export PYTHONPATH=$GSWS_EX/project/src:$GSWS_EX/vendor_dynamic_controller
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1

# 校验冻结输入/代码/预算，无设备访问、无权重加载。
$GSWS_PY "$GSWS_EX/project/scripts/rl1v3/journal_gsws_run.py" check \
  --plan "$GSWS_ROOT/packages-v1/batch-01/PLAN.json"
# batch-02/03/04同理。

# 已存在的冻结输出不得覆盖。下面目录应是新的复跑目录。
$GSWS_PY "$GSWS_REPO/project/scripts/rl1v3/journal_gsws_prepare.py" \
  --old /opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-20261126 \
  --selection "$GSWS_ROOT/task_freeze/SELECTION_PRIVATE.json" \
  --output "$GSWS_ROOT/reproduce-source-01"
$GSWS_PY "$GSWS_REPO/project/scripts/rl1v3/journal_gsws_evidence.py" \
  --bundle "$GSWS_ROOT/reproduce-source-01" \
  --output "$GSWS_ROOT/reproduce-evidence-01"
$GSWS_PY "$GSWS_REPO/project/scripts/rl1v3/journal_gsws_cpu_check.py" \
  --bundle "$GSWS_ROOT/reproduce-source-01" \
  --old-plan /opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-20261126/packages-v2/batch-01/PLAN.json \
  --output "$GSWS_ROOT/reproduce-cpu-01"
$GSWS_PY "$GSWS_REPO/project/scripts/rl1v3/journal_gsws_grammar_check.py" \
  --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 \
  --output "$GSWS_ROOT/reproduce-grammar-01.json"

PYTHONPATH="$GSWS_EX/project/src" \
 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
 "$GSWS_REPO/project/tests/test_gsws.py"
```

每次实际CPU工具计量的单调时间和episode hash会不同；比较原文坐标/任务及策略输入内容，不要求墙钟证据字节重合。语义成功仍是null。CPU后端fixture有独立身份；真实worker禁止将fixture误用为模型状态。不能把模拟80槽写成80次模型生成。

准备脚本有write-once输出保护，原运行包也不可覆盖。冻结包脚本`journal_gsws_package.py`只能构建新目录；当前包已有固定SHA，任何修改都不继承今后的授权。任务/来源/评价不因CPU失败或未来模型胜负替换。

公开源复跑：按[来源表](GSWS_SOURCES_ZH.md)的七个固定commit下载官方仓库，在私有下载目录按原仓库名保存相关文件；`journal_gsws_public_probe.py --root <directory>`读取代码树、运行ESCA纯函数的合成反例、查询HF元数据并下载明确范围的文件。网络上HEAD可能变化，必须比较记录的commit/HF revision，不把新数据当成原身份。该脚本不加载模型，ESCA只做顶层结构/条数统计；来源正文继续隔离，不作新的开发或测试输入。

`journal_gsws_maven_probe.py --output-dir <new-private-directory>`从已经核实的官方Drive文件下载并统计MAVEN训练文件。复现须校验字节SHA；不接受HTML错误页作为数据。该下载不授予训练许可。LongMemEval文件只作外部评价可用性检查，不能导入训练或主任务。

## 本机材料定位

- `source-bundle-v1/TASKS.runtime.jsonl`：8个实际目标；`CPU_STATES_PRIVATE.jsonl`：16个实际观察与RAW输入。
- `source-bundle-v1/CPU_FIXTURES_NOT_MODEL_PRIVATE.jsonl`：32个真实来源输入/明确CPU输出示例，没有模型理解结果。
- `evaluation-v1/STATE_EVAL_CONTRACT_PRIVATE.jsonl`：16个冻结语义合同；`COORDINATES_PRIVATE.json`：逐项供证与当前引用的有界解释；原gold侧车只在此类评价路径。
- `task_freeze/`：生成前选择规则与源身份。
- `packages-v1/`：4包plan/request、独立executor和固定契约。
- `public_sources/`：官方代码/数据隔离下载及SHA；不上传RAW或完整监督数据。
- `cpu-runtime-v1/`与最终冻结栈检查目录：模拟输出的链路日志，不是模型输出。

正式运行只能使用`run --approval <真实研究者批准文件> --run-root <新目录>`；当前没有这样的批准文件，不提供可自动续跑或复用旧批准的循环。授权需绑定[运行申请](GSWS_RUN_REQUEST_ZH.md)的清单及plan对象SHA。
