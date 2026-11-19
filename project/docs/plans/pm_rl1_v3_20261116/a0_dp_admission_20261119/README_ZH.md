# A0 最终准入与人工 DP v2

本轮只准备。原 WS-B 对 #23 的 E6 已正式签收；G0e 研究身份仍待研究者确认，A0 的4次调用尚未授权。本目录不是 H0、EXECUTION_STATE 或旧实验材料的修改。

## E6：已签收，保留原失败

[B签收回执](https://github.com/chensiyu7812/Metacom5_3/pull/23#issuecomment-7003746310)覆盖 #23 HEAD `67169816bddaf50206f9847300673d4887713c4d`：Python3.11 49/49、实际Python3.12进程路径20/20通过。[E6_ACCEPTANCE.json](E6_ACCEPTANCE.json)固定 B #24 HEAD、各原始文件 SHA、原#21四项失败及关闭对应关系。它只证明CPU故障注入范围，不证明模型真实加载、tokenizer一致或实际质量。

原#21 43/47、NOT_SIGNED保留；SIGTERM/SIGKILL残留、worker子进程残留和跨授权重跑已由B复核关闭。SIGTERM可能只留下未决START，必须保持pending、不可重试；建议性日志项不触发本轮重构。已签收执行器及其binding逐字不改。

## G0e：最终冻结目标，尚待研究者签署

[G0E_FREEZE_TARGET.json](G0E_FREEZE_TARGET.json)记录全部模型文件SHA、tokenizer、chat template、system SHA、源文件SHA和适用范围。其内容与#10的HF配置、原PP1 BASELINE逐项相同，不改变原 engineering_only spec 来制造新g_id。

| 身份 | 精确值或固定出处 |
|---|---|
| #10 HEAD | `73fdb12f29b6970a268eeda704d73e1bd35b1c3e` |
| G0e | `G0e:b624c7c3f99ffe6b35eca29e2f93ea9e624e66b31303415e4b9c4b1bc4c6c07e` |
| 权重 | Gemma-4-12B-it，revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`；model.safetensors SHA `5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d` |
| tokenizer | `native-tokenizer:79ff7ef649a97ffd84dc42f243db15a3ca7bc1eea618a9f9454e4f37942a8c92`；具体JSON/模板SHA见目标JSON |
| 原 Notes renderer | `renderer:e04b6de4d78624db4379c25537b9e6f8571b00b4c4edee681c7b5b3e31bb3d27` |
| Step-2 | `pmrl1v3-g0e-no-plan-1` |
| decode | 原greedy / seed0 / max_new_tokens320；完整参数见目标JSON |

研究级固定只适用于登记范围；不等于#10 merge，不修改全局冻结/采用状态，不授予任何运行许可。integration coordinator只读角色记录在此；WS-A工程代码与申请另行交付。

## A0 最终授权确认表

| 项目 | 申请值 / 状态 |
|---|---|
| G0e身份确认 | 待研究者正式确认上述目标及target SHA |
| A0计划 | `43f175c56d6a3e12078ed26744fd4c09f92ab67b7eb34b0a3e28d0ef40815cb2` |
| A0 binding | `c9eb9169897686c018b657c39b766689b78058441976774eb34107f8da0d65e1` |
| 执行checkout | #23 `67169816bddaf50206f9847300673d4887713c4d`；不是本DP工具的新HEAD |
| 执行代码 | `26343dc69ba1616fad293319a26a86b0b1b0816d`；5个文件SHA由原binding固定 |
| 输入 | 原 `A0_CALLS_4.jsonl`，SHA `f3a0e541b3c902c3c3f74b4c79382b103d894702ef200b7e4d198c2f369e692a` |
| 调用量 | 2条原OFF各重复2次，共4次；1次加载、0 warmup、0自动重试 |
| 加载 | 原HF / bf16 / SDPA / batch1 / 本地离线；原Python3.12环境；不切模型、backend或GPU |
| 容量 | 每次申请及启动前重查root≥1GiB、data≥4GiB/1000inode；固定A6000 UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`、空闲≥40960MiB、无其他计算进程 |
| 时间 | 总硬上限1200秒（含fresh hash），加载≤600秒、每调用≤300秒且不得超剩余总预算 |
| 立即停止 | 技术错误、SHA/tokenizer不符、空输出、A0首个length、重复token不一致、设备被占用、容量不足或截止；未完成/不明记pending，不补发 |
| 日志 | 数据盘新作业目录，START先持久化；保存加载诊断、原始text/token IDs、finish_reason、同步耗时、峰值显存、重复一致性、STOP/pending及链式SHA |
| 预估 | GPU约4–8分钟、显存26–36GiB；仍属估计，不是实测 |
| 授权 | **未授权**；[确认模板](A0_AUTHORIZATION_CONFIRMATION_TEMPLATE.json)已填B回执URL/HEAD/binding/文件SHA，签名与G0e确认仍为空，authorized=false |

TMPDIR、缓存和模型日志全部使用原RUNBOOK的数据盘布局；不清理旧文件或干预他人任务。获准后必须使用干净的#23 checkout，先核对最终计划/binding/模型/输入，再执行原4次。A0均为OFF，因此不声称已验证MS使用或情感支持质量。成功后交真实回执；**不得自动继续PP1**，PP1必须另外申请。

## 人工 DP v2

[工具与验证说明](DP_V2_ZH.md)记录新版离线界面、覆盖/缺失/时效/阶段字段、角色登记、真实筛查证据和计划绑定。原v1文件、8个pending身份、旧54/16输入、五项pending人工标注不变；A0/PP1不依赖DP工具。

本轮没有真实人工选择或正式样本导出。正式样本只接受真实冻结筛查证据及研究者确认；模拟数据仅用于机制测试。人工DP为主，Rule-DP不进入生成清单。FC-MS仍需B对实际DP/RET材料及未来生成/审阅入口调用这些检查进行复核。

## 剩余研究者事项

1. 正式确认G0e有限研究身份目标。
2. 单独批准上述最终身份的4次A0调用；本指令和E6回执都不是该批准。
3. 未来FC-MS在真实筛查后确认正式样本与人员登记；不影响当前A0最小路径。

E6范围engineering_ready=true；A0运行authorized=false；自然支持/资源增益research_qualified未证明。无GPU、Generator、Judge、实验训练、PPO、merge、许可邮件或历史改写。
