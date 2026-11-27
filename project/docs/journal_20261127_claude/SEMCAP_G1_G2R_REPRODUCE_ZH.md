# G1／G2-R复跑说明与私有数据位置

记号：`W=/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws-claude`，`R=/opt/tokkio-data0/tokkio_runs/pmrl1-j-semcap-20261127`（私有，不入仓库），`REG=/home/tokkio/Metacom5_3-journal/project/outputs/pm_rl1/v3/A1_preparation/final/registry`，`A=/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127`，`C=/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-claude-20261127`，`NLI=$HOME/.cache/huggingface/hub/models--cross-encoder--nli-deberta-v3-base/snapshots/6c749ce3425cd33b46d187e45b92bbf96ee12ec7`，`PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python`（torch 2.3.1+cu121，transformers 4.57.6）。所有命令在`$W`下运行，`PYTHONUTF8=1`（否则本机locale下读取JSONL会ASCII解码失败）。

## G1

```bash
python3 project/scripts/rl1v3/semcap/g1_identity_prepare.py --registry $REG/sources.jsonl --metadata $REG/registry.json \
  --gsws-resources /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/memory/resources_private.jsonl \
  --exposed $A/event-dialogue-v2/PREFIXES.private.jsonl $C/speaker-dev-v1/PREFIXES.private.jsonl --output $R/g1-prefixes-v1
CUDA_VISIBLE_DEVICES= /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/rl1v3/semcap/g1_identity_run.py prepare \
  --prefixes $R/g1-prefixes-v1/PREFIXES.private.jsonl --baseline /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/smoke-v2/G0E_BASELINE.json \
  --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 --output $R/g1-requests-v1
# 运行（已执行一次；需新批准才能再运行）：run --requests ... --approval $R/authorization/G1_APPROVAL.json --run-root 新目录
python3 project/scripts/rl1v3/semcap/g1_identity_analyze.py --results $R/g1-run-01/RESULTS.private.jsonl \
  --review $R/g1-run-01/DEV_REVIEW.private.json --output project/docs/journal_20261127_claude/semcap_v2
```

固定值：prefixes SHA `b62d6520…`，requests SHA `26d16b09…`，模型safetensors `5a84cb31…`，批准原文SHA `53ce4118…`。

## G2-R数据

```bash
python3 project/scripts/rl1v3/semcap/dcs_seed_prepare.py --registry $REG/sources.jsonl --metadata $REG/registry.json \
  --gsws-resources /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/memory/resources_private.jsonl \
  --exposed $A/event-dialogue-v2/PREFIXES.private.jsonl $C/speaker-dev-v1/PREFIXES.private.jsonl $R/g1-prefixes-v1/PREFIXES.private.jsonl \
  --output $R/dcs-seeds-v1
# 助手编写的弱监督（私有）：$R/dcs-seeds-v1/DCS_AUTHORED.private.pyliteral、DCS_DEV_PARAPHRASES.private.pyliteral
python3 project/scripts/rl1v3/semcap/g2r_build_data.py --inli "$R/external-data/code/inli-repo/INLI Data" \
  --seeds $R/dcs-seeds-v1/SEEDS.private.jsonl --authored $R/dcs-seeds-v1/DCS_AUTHORED.private.pyliteral \
  --paraphrases $R/dcs-seeds-v1/DCS_DEV_PARAPHRASES.private.pyliteral --event32 $A/event-dialogue-v2 --speaker32 $C/speaker-dev-v1 --output 新目录
```

外部数据（私有下载，不再分发）：`$R/external-data/{dnli,decode,vitaminc}`，INLI与VitaminC仓库浅克隆在`$R/external-data/code/`。

## G2-R训练与评价（A4500，账本`$R/g2r/LEDGER.jsonl`累计上限10,800 s）

```bash
G="CUDA_VISIBLE_DEVICES=GPU-bb27e322-0c2a-fe7f-35a8-3ec5944fd243 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUTF8=1"
D=$R/g2r-data-v1; DEV="$D/DEV_DCS.private.jsonl $D/DEV_INLI.private.jsonl"
env $G $PY project/scripts/rl1v3/semcap/g2r_train.py --arm T1 --base $NLI --train-inli $D/TRAIN_INLI.private.jsonl \
  --train-dcs $D/TRAIN_DCS.private.jsonl --maven $A/event-data-final --output 新目录 --ledger $R/g2r/LEDGER.jsonl --dev $DEV
# T2: --arm T2（同上，加MAVEN辅助头）；T1i: --arm T1i --implied-class --train-implied $D/TRAIN_INLI_IMPLIED.private.jsonl
env $G $PY project/scripts/rl1v3/semcap/g2r_eval.py --checkpoint <ckpt或$NLI> --output 新目录 --ledger $R/g2r/LEDGER.jsonl \
  --files $D/DEV_DCS.private.jsonl $D/DEV_INLI.private.jsonl $D/PROBE_INLI_IMPLIED.private.jsonl $D/REG_*.private.jsonl
CUDA_VISIBLE_DEVICES= $PY project/scripts/rl1v3/semcap/g2r_references_cpu.py hyponly --train-inli ... --train-dcs ... --files ... --output 新目录
CUDA_VISIBLE_DEVICES= /opt/tokkio-data0/tokkio_envs/semcap-tools-py311/bin/python project/scripts/rl1v3/semcap/g2r_references_cpu.py minicheck \
  --minicheck $C/hf-cache/hub/models--lytang--MiniCheck-Flan-T5-Large/snapshots/96eafd01cee2d16cf81aaa2fb226b14f422a37b3 --files ... --output 新目录
python3 project/scripts/rl1v3/semcap/g2r_analyze.py --data $D --arms T0=$R/g2r/eval-T0 T1=$R/g2r/eval-T1 T2=$R/g2r/eval-T2 \
  T1i=$R/g2r/eval-T1i H_hyponly=$R/g2r/ref-hyponly --minicheck $R/g2r/ref-minicheck --output <公开目录> --private-errors <私有md>
CUDA_VISIBLE_DEVICES= $PY project/scripts/rl1v3/semcap/g2r_agent_trace_cpu.py --checkpoint $R/g2r/T1i/checkpoint-epoch2 \
  --dev $D/DEV_DCS.private.jsonl --seeds $R/dcs-seeds-v1/SEEDS.private.jsonl --authored $R/dcs-seeds-v1/DCS_AUTHORED.private.pyliteral --output 新目录
```

## 私有位置一览

| 内容 | 位置 |
|---|---|
| 批准原文、G1绑定 | `$R/authorization/` |
| G1前缀、请求、原始24条回复、事件日志、开发审阅 | `$R/g1-prefixes-v1/`、`$R/g1-requests-v1/`、`$R/g1-run-01/` |
| DCS种子与编写材料 | `$R/dcs-seeds-v1/` |
| 训练/评价数据 | `$R/g2r-data-v1/` |
| 模型检查点（每个2.8 GB，含优化器状态） | `$R/g2r/{T1,T2,T1i}/checkpoint-epoch{1,2}/`；推荐`T1i/checkpoint-epoch2` |
| 原始预测（含概率） | `$R/g2r/eval-{T0,T1,T2,T1i}/`、`ref-hyponly/`、`ref-minicheck/` |
| 错误清单（含文本） | `$R/g2r/analysis-ERRORS.private.md` |
| 机制演示轨迹 | `$R/g2r/agent-trace-T1i-cpu/` |
| 失败记录（编码错误，保留） | `$R/g2r/eval-T0.FAILED_encoding_attempt1/` |

## G4（2026-11-27，本轮第三阶段）

```bash
PYJ=/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python; E="PYTHONUTF8=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1"
python3 project/scripts/rl1v3/semcap/g4_candidates.py --registry $REG/sources.jsonl --metadata $REG/registry.json \
  --gsws-resources /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/memory/resources_private.jsonl \
  --exposed $A/event-dialogue-v2/PREFIXES.private.jsonl $C/speaker-dev-v1/PREFIXES.private.jsonl \
            $R/g1-prefixes-v1/PREFIXES.private.jsonl $R/dcs-seeds-v1/SEEDS.private.jsonl --output $R/g4-candidates-v1
# 助手在预测前写的冻结设计：$R/g4-candidates-v1/G4_STATES_FROZEN.private.json
env $E CUDA_VISIBLE_DEVICES= $PYJ project/scripts/rl1v3/semcap/g4_run.py prepare --frozen $R/g4-candidates-v1/G4_STATES_FROZEN.private.json \
  --candidates $R/g4-candidates-v1/CANDIDATES.private.jsonl --baseline /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/smoke-v2/G0E_BASELINE.json \
  --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 --t1i $R/g2r/T1i/checkpoint-epoch2 --output 新目录
env $E CUDA_VISIBLE_DEVICES= $PYJ project/scripts/rl1v3/semcap/g4_run.py run --dry-run 3 --states ... --baseline ... --model ... --t1i ... --run-root 新目录   # CPU演练
# 正式运行（已执行一次；需新批准）：run --states --prepare-report --approval $R/authorization/G4_APPROVAL.json ... CUDA_VISIBLE_DEVICES=A6000 UUID CUBLAS_WORKSPACE_CONFIG=:4096:8
python3 project/scripts/rl1v3/semcap/g4_analyze.py stats --run $R/g4-run-01 --checks $R/g4-prepare-v1/CHECKS.private.json --review $R/g4-run-01/DEV_REVIEW.private.json --output <公开json>
env $E CUDA_VISIBLE_DEVICES= $PYJ project/scripts/rl1v3/semcap/g4_analyze.py t0 --run $R/g4-run-01 --states $R/g4-prepare-v1/STATES.private.jsonl --t0 $NLI --t1i $R/g2r/T1i/checkpoint-epoch2 --output <私有jsonl>
python3 project/scripts/rl1v3/semcap/g4_analyze.py blind --run $R/g4-run-01 --states ... --checks ... --output 新目录
```

固定值：states SHA `30fa04d3…`；代码SHA见`g4_v1/G4_RUN_PUBLIC.json`。私有：`$R/g4-candidates-v1/`（候选与冻结设计）、`$R/g4-prepare-v1/`（STATES、CHECKS）、`$R/g4-run-01/`（CALLS含全部提示与原始输出、RESULTS含命题/核验/WM/回复、EVENTS、DEV_REVIEW、CLAIM_REFERENCE_POSTHOC、T0_T1I_CLAIMS）、`$R/g4-blind-v1/`（盲评包与钥匙）、`$R/g4-dryrun-cpu-v{1,2}/`（CPU演练）、`$R/g4-cpu-checks/`。

## G6（在线INSPECT_CLAIM收口）

```bash
python3 project/scripts/rl1v3/semcap/g6_select.py --candidates $R/g4-candidates-v1/CANDIDATES.private.jsonl \
  --g4-states $R/g4-prepare-v1/STATES.private.jsonl --output $R/g6-select-v1
# 助手预测前写的冻结设计：$R/g6-select-v1/G6_STATES_FROZEN.private.json
env $E CUDA_VISIBLE_DEVICES= $PYJ project/scripts/rl1v3/semcap/g6_run.py prepare --frozen $R/g6-select-v1/G6_STATES_FROZEN.private.json \
  --candidates $R/g4-candidates-v1/CANDIDATES.private.jsonl --baseline /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/smoke-v2/G0E_BASELINE.json \
  --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 --t1i $R/g2r/T1i/checkpoint-epoch2 --output 新目录
env $E CUDA_VISIBLE_DEVICES= $PYJ project/scripts/rl1v3/semcap/g6_run.py run --dry-run 3 --dry-gate continue|stop ...   # CPU演练
# 正式运行（已执行一次；需新批准）：run --approval $R/authorization/G6_APPROVAL.json ...；筛查后进程等待 g6-run-01/GATE_DECISION.json
python3 project/scripts/rl1v3/semcap/g6_gate_view.py $R/g6-run-01 $R/g6-prepare-v1/CHECKS.private.json   # 阶段审阅视图
```

固定值：states SHA `50ccb189…`；审阅文件SHA `20b4d3f5…`（决定文件绑定）。私有：`$R/g6-select-v1/`、`$R/g6-prepare-v1/`、`$R/g6-run-01/`（CALLS、RESULTS、EVENTS、GATE_REVIEW、GATE_DECISION）、`$R/g6-dryrun-cpu-v{1,2,3}/`、`$R/g1-blind-v1/`。
