# 运行与复核入口

工作目录`/home/tokkio/Metacom5_3`。CPU环境为`/tmp/pmrl1-publication-20261022-venv/bin/python`，`PYTHONPATH=project/src`。GPU使用原`/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python`，原SFT vendor另加`/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103`，保持CUDA_DEVICE_ORDER=PCI_BUS_ID、CUDA_VISIBLE_DEVICES=1及离线模型加载。

## 实际目录

均位于`project/outputs/pm_rl1/`：

| 内容 | 目录 |
|---|---|
| 固定24前缀/487程序/431输入、OFF复用证明 | `organized_initial_training_20261103_v2` |
| 真实BGE及FullText/NoText | `organized_initial_encoding_20261103_v2` |
| 全量无模型重放验证 | `organized_initial_validation_20261103_v1` |
| G加载前旧采样拦截、0加载/0生成关闭记录 | `organized_initial_generation_20261103_v1` |
| 新入口、1次G加载/407新回复全部完成 | `organized_initial_generation_20261103_v2` |
| 431回复seal核验、375个去重待测内容 | `actual_training_feedback_20261103_v1` |
| 有界评分原包、原始日志和续跑日志 | `execution_bridges_20261103_v1` |
| 原评分进程 | `J_EXECUTION_20261103.log`，退出1 |
| 续跑进程 | `J_CONTINUATION_20261103.log` |
| 保留未知责任的余额刷新及接续 | `account_refresh_20261103_v1`、`J_ACCOUNT_REFRESH_EXECUTION_20261103.log` |
| 单一未知请求固定隔离证明 | `ISOLATION_20261103.json` |
| 开发审计快照 | `paid_development_snapshot_20261103_v1/v2/v3/v4` |
| 有限只读收口观察器 | `real_preparation_closeout_20261103_v1` |
| 余额刷新后进程的只读收口观察器 | `real_preparation_closeout_20261103_v2` |

G进程自然完成后有`RESULTS.json`及`RESPONSES_PRIVATE.json`。评分完成后有`live_J/CLOSED.json`；其状态是开发关闭、不是奖励资格。停止或未知请求不重派，不删除旧journal，不清空账本。

观察器已实际完成G后处理和第一次J停止后的144只读审计，输出`paid_development_snapshot_20261103_final`；J在余额检查停止，尚无`CLOSED.json`，不能误称整个开发阶段完成。观察器本身不派发模型/API，不授予资格或启动训练，现已正常退出。随后148入口凭新的只读账户快照，在保留所有未知责任和原次数/金额边界下接续。

v2观察器只等待148进程退出或开发关闭后再执行一次144审计，目标`paid_development_snapshot_20261103_refresh_final`；不发起任何API或模型调用，最长观察24小时。研究者已答复“暂不充值”，不得据新快照重复询问或增加预算；余额不足时停在派发前。

## 无模型复核

```bash
env PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python project/scripts/rl1/144_audit_development_progress.py --package project/outputs/pm_rl1/execution_bridges_20261103_v1 --bank project/outputs/pm_rl1/human_reference_reuse_20261102_v2 --output /tmp/pmrl1_development_new_snapshot

env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python project/scripts/rl1/145_validate_organized_initial.py --package project/outputs/pm_rl1/organized_initial_training_20261103_v2 --encoding project/outputs/pm_rl1/organized_initial_encoding_20261103_v2 --output /tmp/pmrl1_initial_new_validation
```

输出目录必须未存在。144只读原账与评分，按第一份有效交付保留unknown，逐条重解析原raw，对旧q区间做区间归属判断。145复制真实BGE cache到验证目录，原cache字节保持，无模型forward。

G全部完成后，146号入口核验431条回复与原始seal、24条OFF，并生成按完整evidence/reply去重的待评分输入：

```bash
env PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python project/scripts/rl1/146_prepare_actual_training_feedback.py --package project/outputs/pm_rl1/organized_initial_training_20261103_v2 --generation project/outputs/pm_rl1/organized_initial_generation_20261103_v2 --output /tmp/pmrl1_actual_feedback_inputs
```

该入口不派发评分、不发放训练资格。147的续跑仍使用原审批和原阶段身份，仅放行固定未知请求之外的槽；原未知请求未结责任始终占用预算。已运行进程期间不再启动同阶段，新的未知请求会继续停下。

148仅适用于原账户快照已拦截、原单一未知请求仍完整保留的本次阶段。它的`prepare`模式执行一次余额查询并封存来源，`check`无网络，`execute`沿用原价格/服务检查和调度。不可将余额差推算为未知调用的结算，不可凭充值提升原研究金额或次数上限。当前账户余量只能支持少量后续调用；补充余额是账户资金条件，不是新增研究预算授权。

## 测试范围

56项：`test_rl1_organized_supervision.py`、`test_rl1_organized_learning_bridge.py`、`test_rl1_cached_generation_worker.py`、`test_rl1_development_feedback.py`、`test_rl1_development_dispatch.py`、`test_rl1_development_preflight.py`。

29项：`test_rl1_organized_local_backend.py`、`test_rl1_development_progress_audit.py`、`test_rl1_local_backend.py`、`test_rl1_resource_comparison_runner.py`。

新增8项：`test_rl1_retained_liability_continuation.py`。原stage相关24项及审计2项另作回归重跑，不增加不同测试总数。

新增10项：`test_rl1_account_balance_refresh.py`；与前述8项、原派发12项、原预检4项组合34项退出0。不同测试合计103项。
