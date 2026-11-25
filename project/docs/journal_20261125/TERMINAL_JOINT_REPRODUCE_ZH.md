# T/S真实终点与J06联合结果：CPU复跑

本页读取已经完成的154次真实调用，不启动GPU、不产生新语义标签。需要原本机私有数据、请求、源侧参考和审阅材料；公共仓库仅包含代码、无文本聚合和身份。语义观察的重放是核对其引用、来源、哈希和计算，不等于独立重复人评。

## 运行环境及主命令

在独立journal工作树根目录运行：

```bash
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
export CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
J_PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
J_RUN=/opt/tokkio-data0/tokkio_runs/pmrl1-j-terminal-20261125
J_CLOSE=/opt/tokkio-data0/tokkio_runs/pmrl1-j-closeout-20261125
J_KEY=/opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-20261125
J_EVID=/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125
J_REPLAY_PARENT=$(mktemp -d /opt/tokkio-data0/tokkio_runs/pmrl1-j-terminal-replay-XXXXXXXX)

"$J_PY" project/scripts/rl1v3/journal_replay_terminal.py \
 --root "$J_RUN" --closeout "$J_CLOSE" --keycap "$J_KEY" \
 --evidence "$J_EVID" --out "$J_REPLAY_PARENT/results"
```

此入口重新执行以下CPU计算并与本轮冻结结果比较：10份作业的hash-chain/计划/请求/授权/实际token计量；S1/S2的36个专属端点严格评分、18个配对和冻结可见规则；一次明确的JSON围栏诊断及正确分母；T1/T2原24逻辑臂与22物理回复的引用和逐题计数；旧12题整种表示Oracle复算；J06六批真实回复收集、96份事实源核对、事实/支持区间、四端点配对与固定策略、可读私有全文。它不调用`run`执行入口。不同输出目录只改变复跑材料的位置，不改变原实验身份或授予新的GPU许可。

S/T/J实际原始回复不清洗。严格JSON仍是原严格JSON；围栏结果仅独立事后诊断。未知区间不是统计置信区间，不把unknown当0，也不把区间上界当成功数。所有自然回复正式reward仍为null。

## 真实数据相关回归

```bash
export JOURNAL_RS_OUTPUT=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/rs/candidates-v1
export JOURNAL_RS_FOLLOWUP="$J_EVID/rs"
export JOURNAL_RS_COMPLEX=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/rs_complex/package-v2
export JOURNAL_RS_BATCH_REVIEW=/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/batch18_rs_review
export JOURNAL_KEYCAP_RS="$J_KEY/rs_r1/final"
export JOURNAL_CLOSEOUT_RS="$J_CLOSE/rs_review/combined-v1"
export JOURNAL_JOINT_PACKAGE="$J_RUN/joint/packages-v5"
export JOURNAL_JOINT_BUNDLE="$J_RUN/joint/source-bundle-v1"
"$J_PY" -m pytest -q project/tests/test_rl1v3_journal*.py \
 --junitxml="$J_REPLAY_PARENT/TESTS.xml"
```

这些检查包括真实As-of合法来源、task可见视图与旧PrefixSpec时间锚的分离、MP/ME掩码、容量测量不冒充GET、不可重复读取、STOP后禁止操作、供证/来源/回复身份、完整四格、技术失败与语义未知分离、物理复用成本、近似语境侧记和共享观测区间算术。未提供本机私有路径时部分测试会明确skip，不能冒称完整真实数据验证。

公开导出只允许预先列举的统计文件，不递归复制数据目录：

```bash
"$J_PY" project/scripts/rl1v3/journal_export_terminal.py \
 --root "$J_RUN" --out "$J_REPLAY_PARENT/public"
```

导出校验原96清单SHA、用户授权绑定及测试回执。实际研究结果和局限见[完整报告](REAL_TASK_JOINT_RESULTS_20261125_ZH.md)，运行身份见[原58申请](TEMPORAL22_RUN_REQUEST_ZH.md)、[结构化36申请](STRUCTURED36_RUN_REQUEST_ZH.md)及[联合96固定申请](JOINT96_RUN_REQUEST_ZH.md)。这些历史批准都已执行完毕，不表示可重新运行。

## 私有证据入口

以下路径相对`$J_RUN`，均不上传：

|材料|内容|
|---|---|
|`USER_AUTHORIZATION.json`、`JOINT96_USER_AUTHORIZATION.json`、`*_AUTHORIZED.json`|58与96两次独立授权及计划绑定|
|`S1_run1`、`S2_run1`、`T1_run1`、`T2_run1`、`J1_run1`至`J6_run1`|原始调用、加载、停止、token及hash-chain|
|`structured/STRUCTURED36_FULL_PRIVATE.md`|18题×2臂完整原始G输出、严格解析与分项诊断|
|`structured/S1_results_v1`、`structured/S2_results_v1`|36个真实专属端点，原pending清单保留在closeout卷|
|`structured/FORMAT_DIAGNOSTIC_RULE_POSTHOC.json`|唯一一次明确的CPU格式诊断规则，不是新评分资格|
|`memory/validated-v1/TEMPORAL_REVIEW_PRIVATE.md`|8题三臂全文、原子、合法证据、时点与拒答观察|
|`joint/source-bundle-v1`、`joint/FREEZE_RECEIPT.json`|生成前24任务、来源、RS程序、评价身份|
|`joint/packages-v5`、`joint/RUN_CATALOG.json`|已执行96请求及六个固定计划；旧构建尝试保留|
|`joint/POLICIES_PREOUTPUT.json`、`joint/support-review-v1/PROTOCOL_PREOUTPUT.json`|生成前策略与支持审阅口径|
|`joint/fact-review-v1/SOURCE_READ_RECEIPT_PRIVATE.json`|独立来源审阅先于J输出的身份记录|
|`joint/fact-review-v1/BATCH_*`、`joint/support-review-v1/BATCH*`|96份事实/支持分工观察与原始引用|
|`joint/fact-review-v1/CONTEXT_SCOPE_UNCERTAINTY_PRIVATE.json`|原7个近似表述观察保留，语境争议单独记录|
|`joint/readback-v2/J06_FULL_REVIEW_PRIVATE.md`|24题×4臂全部原始回复及逐项事实/支持证据|
|`joint/analysis-v2/JOINED_ENDPOINTS_PRIVATE.jsonl`|96个联合开发终点，正式reward均null|

`analysis-v1/readback-v1`保留。v2只修复STOP相对同一个STOP观测的区间减法：应为[0,0]，不能当作两个独立未知数计算成[-2,2]；其余标签、四臂及Oracle核心结果均不变。原五项有限人审仍在closeout卷等待真人裁决，不增设大型Judge资格审查。
