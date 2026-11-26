# GSWS本轮复算与私有材料索引

本轮公共代码和聚合结果位于独立分支；不能假定单一公开提交包含完整本机A/B/G执行栈。沿用[原完整依赖说明](gsws_phase1/DEPENDENCIES_PUBLIC.json)，新增[实际v2及修复候选依赖](gsws_actual_v1/DEPENDENCIES_PUBLIC.json)。A/B/G、PR #28、历史结果没有修改。运行环境沿用Python3.12.14、torch2.7.1+cu128、transformers5.17.0、tokenizers0.23.2、safetensors0.8.0；HF backend，清单里的vLLM版本不是本轮使用vLLM的证据。

Gemma revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`、A6000 UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`不变。CPU测试环境与GPU推理环境分开：pytest使用paper1-py311，真实来源/正式日志全路径使用冻结paper1-judges-py312。未为安装pytest更改冻结GPU环境。

本机根目录：

- 原准备`/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-20261126`，简写R。
- 本轮`/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127`，简写A。
- 工作树`/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws`。

| 材料 | 本机位置 |
|---|---|
| 本次研究者授权原文与v2绑定 | A/authorization-v1（私有） |
| 原v2冻结四包 | R/packages-v2；未改写 |
| 实际失败原始日志、模型加载与退出 | A/run-01/job-392847b8c7f37835f6ada6034564541cc08ca0ab79091aa9a7b0787acf57ca90 |
| 逐槽结果、实际原始解释/回复集合 | A/results-v2-attempt1；两个RAW输出文件为空，明确0模型输出 |
| v3日志修复候选 | R/packages-v3-clockfix；未授权、未启动 |
| 正式日志写入器CPU接线 | A/clock-repair-cpu-v1；80次fixture，不是推理 |
| 原逐状态评价和12＋8独立审阅合同 | R/evaluation-v1；没有重新修改 |
| MAVEN原始训练文件 | R/public_sources/MAVEN-FACT/train.download.jsonl |
| 最终数据入口、目标、异常、50项选择 | A/event-data-final |
| 训练来源8个实际因果前缀与32项输入/参考 | A/event-dialogue-v2 |
| 实际CPU NLI输出及逐项对照 | A/event-skill-cpu-v1 |
| 从16个实际GSWS观察调用事件工具 | A/event-connect-v1 |

MAVEN首次处理在遇到真实越界坐标时终止，部分产物留在A/event-data-v1；v2加入保留异常而不崩溃；最终入口补全论元字符坐标对应的原始document字段，保留于event-data-final。数据源没有修复/覆盖，公开计数以final为准。ESConv的fold为null，训练资格依原split；初版过滤过严只取到4个Evo前缀，修复后在任何模型预测前固定8前缀event-dialogue-v2。原选择记录保留，没有按模型胜负换题。

## CPU复跑

从工作树执行，输出须使用新目录，避免覆盖证据：

```bash
python project/scripts/rl1v3/journal_gsws_collect.py \
  --run-root /opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127 \
  --catalog /opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-20261126/packages-v2/CATALOG.json \
  --output /opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127/recompute-results-new

python project/scripts/rl1v3/journal_event_data.py \
  --source /opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-20261126/public_sources/MAVEN-FACT/train.download.jsonl \
  --output /opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127/recompute-event-data-new

CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 PYTHONPATH=project/src \
  /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  project/scripts/rl1v3/journal_event_skill_cpu.py \
  --frozen /opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127/event-dialogue-v2 \
  --snapshot /home/tokkio/.cache/huggingface/hub/models--cross-encoder--nli-deberta-v3-base/snapshots/6c749ce3425cd33b46d187e45b92bbf96ee12ec7 \
  --output /opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127/recompute-event-skill-new
```

NLI只用于这一有限候选命题能力检查，不调用旧资格训练器。`event_understanding.py`依赖torch/transformers的部分是可选CPU模型适配；坐标/流程功能可纯Python运行。

正式日志CPU路径须将`PYTHONPATH`指向**冻结完整executor/project/src与vendor_dynamic_controller**，不要把稀疏工作树当完整运行依赖。命令为该executor内`journal_gsws_cpu_check.py --bundle R/source-bundle-v1 --old-plan R/packages-v3-clockfix/batch-01/PLAN.json --output 新目录`。该脚本模型后端始终fixture；没有GPU调用授权效果。

GPU执行仅通过冻结包`journal_gsws_run.py run --plan … --approval … --run-root …`，并要求新的真实批准证据。当前修复申请尚未批准；不提供可误用旧授权自动启动的脚本。每包设备/存储/身份/硬时限/0重试守卫不变；不改旧claim，也不使用其他GPU。当前工作树后续新增的数据/收集脚本未回写冻结包，重新freeze会产生不同身份，不能假装复现同SHA。

## 私有边界与评价

原文、gold、任务细节、32项参考、原始模型概率和研究者批准原文只留本机。公共文件仅代码、身份、聚合计数及别名状态。没有向作者发邮件或将原始对话送到网络。对外查询仅用于公开研究元信息。

12终局＋8解释仍按旧合同选取Q02-S0、Q02-S1、Q03-S1、Q08-S1，未改为更有利样本。因为实际输出尚不存在，没有制造待审“答案”；评审者/暴露状态为null，待产生材料及独立真人。旧5项真人待复核继续pending。

公开结果包含CPU辅助模型实际统计，但不构成正式reward、自然支持资格或GSWS质量结论。延迟区间的来源明确：加载父进程、CPU工具处理、此前检索等不混加；本轮客户端首文本和Tokkio有效语音均未测。
