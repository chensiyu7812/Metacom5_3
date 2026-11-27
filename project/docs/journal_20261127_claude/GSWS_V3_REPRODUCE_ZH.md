# 复跑说明与私有材料位置

简写：R=`/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-20261126`（原准备，未改写），A=`/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127`（实际运行），C=`/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-claude-20261127`（本轮能力工具），W=`/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws-claude`（本分支工作树）。

## 一、GSWS v3恢复（GPU，已执行，不得再次用同一批准启动）

| 项 | 值 |
|---|---|
| 运行包 | R/packages-v3-clockfix，catalog SHA256 `6a588886…8be7b`，executor inventory `0c6ea9db…569a6a` |
| 推理环境 | `/opt/tokkio-data0/tokkio_envs/paper1-judges-py312`（Python 3.12.14、torch 2.7.1+cu128、transformers 5.17.0），HF backend |
| 模型/设备 | Gemma-4-12B-it revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`；A6000 `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4` |
| 批准 | A/authorization-v3-clockfix：`RESEARCHER_APPROVAL_PRIVATE.txt`（研究者原文）、`GSWS-{1..4}_APPROVAL.json`、生成脚本`make_approvals.py` |
| 启动 | `A/run_v3_all.sh`顺序调用`A/run_v3_one.py N`（N=1..4）；任一作业非FINISHED即停止，不自动续跑 |
| 原始日志 | A/run-v3-0N/job-*/（逐事件JSON、SUMMARY.json、worker.stderr.log）；A/run-v3-driver.log、A/run-v3-0N.console.log |
| scope claim | `/opt/tokkio-data0/tokkio_projects/pmrl1-validation/limited-g0e-claims/gsws-*.json`（v3 scope与v2不同，不冲突） |

executor在`check()`中重新校验inventory、catalog与plan绑定；同一plan已有claim，再次运行会被`claim_scope`拒绝（无隐式续跑）。

## 二、结果收集与统计（CPU，可重复）

```bash
cd W
python3 project/scripts/rl1v3/journal_gsws_collect.py --run-root A \
  --catalog R/packages-v3-clockfix/CATALOG.json --output A/新目录 --job-dir-prefix run-v3-
python3 project/scripts/rl1v3/journal_gsws_v3_stats.py --run-root A \
  --catalog R/packages-v3-clockfix/CATALOG.json --output A/新目录
python3 project/scripts/rl1v3/journal_gsws_review_dump.py --collected A/新目录 \
  --contract R/evaluation-v1/STATE_EVAL_CONTRACT_PRIVATE.jsonl --output A/新目录/REVIEW_SHEET.private.md
```

| 材料 | 本机位置 |
|---|---|
| 完整原始终局回复（48）与请求 | A/results-v3-clockfix/TERMINALS_RAW.private.jsonl |
| 完整原始解释（32） | A/results-v3-clockfix/INTERPRETERS_RAW.private.jsonl |
| 逐状态审阅表（含全部合法证据） | A/results-v3-clockfix/REVIEW_SHEET.private.md（短版`REVIEW_SHEET_SHORT.private.md`） |
| 逐槽统计 | A/results-v3-clockfix/SLOT_STATS_PUBLIC.jsonl，公开副本`gsws_v3_results/` |
| 12终局＋8解释盲包 | A/independent-review-packet-v1（`TERMINALS_BLIND`、`INTERPRETATIONS_BLIND`、臂对照键`ARM_KEY_DO_NOT_SHOW_REVIEWER`） |
| 开发审阅标签 | `gsws_v3_results/DEV_REVIEW_PUBLIC.jsonl`（只有标签与错误类别，无原文） |

`journal_gsws_collect.py`本轮仅增加`--job-dir-prefix`参数（默认`run-`，旧调用不变）。

## 三、语义能力工具（CPU，独立环境）

环境：`/opt/tokkio-data0/tokkio_envs/semcap-tools-py311`（由paper1-py311建立的venv；torch 2.5.1+cpu、transformers 4.46.3、maverick-coref 1.0.7）。模型缓存C/hf-cache（MiniCheck-FT5、Maverick）；NLI与DeBERTa-v3-base沿用`~/.cache/huggingface`。外部仓库只读浅克隆于C/external。

```bash
V=/opt/tokkio-data0/tokkio_envs/semcap-tools-py311/bin/python
NLI=$HOME/.cache/huggingface/hub/models--cross-encoder--nli-deberta-v3-base/snapshots/6c749ce3425cd33b46d187e45b92bbf96ee12ec7
MC=C/hf-cache/hub/models--lytang--MiniCheck-Flan-T5-Large/snapshots/96eafd01cee2d16cf81aaa2fb226b14f422a37b3
MAV=C/hf-cache/hub/models--sapienzanlp--maverick-mes-ontonotes/snapshots/087a90f0380ec1f20ed19732b657f53fd3542c81/weights.ckpt
SETS="event32=A/event-dialogue-v2 speaker32=C/speaker-dev-v1"
# 1) 新开发集选择（已执行；输出目录必须不存在）
python3 project/scripts/rl1v3/semcap/speaker_prefix_prepare.py \
  --registry /home/tokkio/Metacom5_3-journal/project/outputs/pm_rl1/v3/A1_preparation/final/registry/sources.jsonl \
  --metadata /home/tokkio/Metacom5_3-journal/project/outputs/pm_rl1/v3/A1_preparation/final/registry/registry.json \
  --gsws-resources /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/memory/resources_private.jsonl \
  --exposed A/event-dialogue-v2/PREFIXES.private.jsonl --output 新目录 --esconv 7
# 2) B/C/D × tagged/attributed
CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 $V project/scripts/rl1v3/semcap/claim_support_cpu.py --sets $SETS --nli $NLI --minicheck $MC --output 新目录
# 3) scoped臂、4) scoped+coref臂（追加到同一输出目录）
CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 $V project/scripts/rl1v3/semcap/claim_support_scoped_cpu.py --sets $SETS --nli $NLI --minicheck $MC --base 新目录
CUDA_VISIBLE_DEVICES= HF_HOME=C/hf-cache $V project/scripts/rl1v3/semcap/coref_claim_cpu.py --sets $SETS --nli $NLI --minicheck $MC --maverick $MAV --base 新目录
# 5) MAVEN-FACT条件化事实性：冒烟（已执行）；完整训练待GPU批准
CUDA_VISIBLE_DEVICES= $V project/scripts/rl1v3/semcap/factuality_train.py --data A/event-data-final \
  --model $HOME/.cache/huggingface/hub/models--microsoft--deberta-v3-base/snapshots/8ccc9b6f36199bec6961081d44eb72fb3f7353f3 \
  --output 新目录 --smoke 500 --dev-limit 500 --epochs 1
```

Maverick首次加载会从HF取DeBERTa-v3-large分词器配置（之后可离线）；其`weights.ckpt`经`torch.load`（pickle）加载，来源为官方HF仓库。

| 材料 | 本机位置 |
|---|---|
| speaker32前缀、命题、参考（预测前冻结） | C/speaker-dev-v1（`CLAIM_INPUTS` `6e3c83bc…`，`CLAIM_REFERENCES` `2fd561ca…`，`PREFIXES` `945a4d48…`） |
| 预测（参考连接前写出）与逐项结果 | C/claim-support-cpu-v1/`PREDICTIONS_*BEFORE_REFERENCE_JOIN.private.jsonl`、`RESULTS_ALL_PRIVATE.jsonl` |
| 冒烟训练 | C/factuality-smoke-cpu-v2；首次因截断参数失败的日志保留为`factuality-smoke-cpu-v1.FAILED_truncation.log` |

CPU测试：`PYTHONPATH=project/src $V -m pytest -q project/tests/test_semcap_identity.py project/tests/test_semcap_claim_support.py`（9项通过）。注意本分支是稀疏工作树，`tests/test_gsws.py`依赖`generator/g0e.py`，须将`PYTHONPATH`指向冻结executor（见Codex的`GSWS_ACTUAL_REPRODUCE_ZH.md`）。

## 四、私有边界

原文、参考、32+32条开发命题、批准原文、盲包与审阅表只在本机。公开目录只含代码、聚合指标、别名、标签类别与文件SHA。外部访问仅为公开仓库/模型下载；未向任何服务发送对话或个人信息；GPU使用仅限本次获批GSWS恢复；付费调用0。
