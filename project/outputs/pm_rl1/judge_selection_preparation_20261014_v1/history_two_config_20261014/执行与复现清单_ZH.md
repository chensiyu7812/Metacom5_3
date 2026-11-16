# 执行与复现清单

唯一当前草案是本目录根部`plan.json`，身份`7eb2b8c3c2545c4e66403b40b9a3e9db530e40207b0d6e12ab0c8f2e28be9daa`。`draft_build_00…03`仅为本轮离线生成过程的保留副本，不是其它候选或修订额度。最新验证在`verification_final_v2/`；所有mock记录明确mode=mock。旧Qwen的真实66次与这些mock互不混计。

## 已执行的离线检查

以下命令真实执行成功，使用既有CPU环境；未安装依赖。整体验证自动设置CUDA不可见、HF/Transformers离线。

```bash
cd /home/tokkio/Metacom5_3
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m unittest discover -s project/outputs/pm_rl1/judge_selection_preparation_20261014_v1 -p test_selection.py -v
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q project/tests/test_rl1_calibration_workflow.py
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/verify_offline.py --out /tmp/pmrl1_selection_verification_NEW
```

最后一条给出了新的可复现输出位置；目录已存在时需换一个新名字，脚本拒绝覆盖。实际本轮完整日志位于`verification_final_v2/`。该脚本依次运行22项新测试、23项原流程测试、各CLI帮助、两候选三阶段dry-run、80次mock、一次第二条故障的停派测试、mock分析，以及从原开发资料重建计划并逐字比较。守卫也检查旧共享账本和原9个本地未跟踪文件哈希不变。

测试覆盖：封存阶段在读文件前被拒绝；未获批准不会构造真实传输；工程结果缺失或mock不能打开真实下一阶段；配置、payload、返回和draw绑定；并发预留只放行额度内请求；在途/未知费用继续占用；跨共享20/旧50限制；失败原始片段和尝试保存；不重试；未知q/m/U为空；length不是低分；重复JSON字段不修复；Du不变成第二套观察；原140不能无回执改大。

没有覆盖的真实行为：API网络/流式兼容、服务端版本、实际usage和费用；Gemma权重加载、原生tokenizer计数、processor实际输出、显存峰值、速度和质量。旧流程pytest通过与新候选的真实资格无关。80次mock全为预设uncertain，是为了证明未知不会补0，不是准确性结果。

## 获准后才能执行的首阶段

以下命令只展示，来自本轮实际`--help`，未执行。`approval_for_engineering.json`目前不存在。用户确认后，由执行代理根据确认内容制作审批副本并记录消息依据，不把PENDING模板直接当许可。首阶段字段应限制phases=[engineering]、new_calls_limit=8、旧累计上限仍140；无需为首8次先改140。

```bash
cd /home/tokkio/Metacom5_3/project/outputs/pm_rl1/judge_selection_preparation_20261014_v1
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python runtime_receipts.py api --approval approval_for_engineering.json --out approved_api_readiness
```

这是另需批准的2个账户管理GET（models、balance），0次J、不发送项目对话。只从安全的本地环境读取API凭据，不在日志或聊天打印；不承诺账户已可用。后续核对价格、数据许可、共享账外责任及没有并发旧付费writer，再填独立回执引用和金额。`provider_account_reconciled`不能由一次余额GET自动推断为true。

Gemma需另获约24GB固定revision下载许可。当前没有下载脚本自动触发此动作，也不安装环境。下载后在预定目录准备好官方文件，再执行以下本地文件校验和tokenizer计数（不推理）：

```bash
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python runtime_receipts.py local --model-dir /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 --out gemma_local_readiness.json
```

目录是拟定位置，当前不存在；不能把另一个checkpoint放进去冒充。脚本核对官方Git blob/LFS SHA、原生模板下的全部40次输入长度、32k输出余量。文件哈希回执和精确长度检查通过后，只在指定A6000空闲时执行4条真实请求：

```bash
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python selection.py dry-run --candidate deepseek_flash_high --phase engineering
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python selection.py execute --candidate deepseek_flash_high --phase engineering --approval approval_for_engineering.json --execute-live
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python selection.py dry-run --candidate gemma4_12b_bf16 --phase engineering
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python selection.py execute --candidate gemma4_12b_bf16 --phase engineering --approval approval_for_engineering.json --execute-live
```

两项无需同时运行；任一未具备条件就报告该项阻塞，不改参数补位。首阶段最多8次，耗时30—180秒/请求情景下约4—24分钟，另加Gemma加载；DeepSeek首4条峰价2k—8k约$0.031—0.067，极限预留3.145728。遇到技术失败停止该配置，保留所有已开始记录，不自动恢复。GPU不空闲时等待/报告，不终止其它任务。工程筛选后就停止，提交版本/输入/显存/吞吐/计费/格式结果。

真实输出固定写入本目录`live_runs/<candidate>/`。调用计数跨两配置共享且保留旧66；同一请求不接受覆盖。审批必须绑定当前plan/config/代码身份；计划变了需重新审查，不能沿用旧许可。

## 后续阶段的接口（不代表批准）

每配置工程4条全部有效且来源/工程复核后，保存对应`engineering.review.json`；精确格式见`check_stage_gate`，含plan、config、phase、disposition和全部request IDs。批准范围增加到development才运行其余28条；同理开发记录和门复核后才能进入diagnostics。若完整两配置80次获批，需独立增补140→146并保留依据；4次恢复另议，当前runner不自动派发恢复。

```bash
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python selection.py execute --candidate deepseek_flash_high --phase development --approval approval_for_development.json --execute-live
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python selection.py execute --candidate deepseek_flash_high --phase diagnostics --approval approval_for_diagnostics.json --execute-live
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python analyze.py --candidate deepseek_flash_high --run-dir live_runs/deepseek_flash_high --out analysis_deepseek_NEW --review completed_semantic_review_private.csv
```

Gemma对应替换candidate和解释器。分析表可先不传`--review`，未审核维度全部pending，不生成胜者。审核CSV的source_ids用分号分隔，exact_quote为至少一个所引合法turn中逐字存在的片段；原始输出SHA必须匹配。逐字引用匹配仍不是语义蕴含证明，需要研究者解释。真实分析默认拒绝mock混入。

未来59次验收没有本目录可执行入口。只有一个配置开发复核可接受，再另行申请正式freeze及既有验收流程的适配/接入；这一步还需绑定新的运行身份，不能把当前草案或旧Qwenfreeze直接复用。封存标签继续冻结。更后面的128/384研究、训练和上传同样不在许可内。

## 主要文件

- `selection.py`：独立派发、双阶段门、身份/次数/预算守卫；默认dry-run/mock。
- `adapters.py`：官方DeepSeek SSE、本地Gemma原生模板/输出和mock传输；复用原解析器。
- `prepare.py`：只从开发资料重建配置、40×2请求、变体和预算。
- `runtime_receipts.py`：未来独立批准的账户读取、下载后本地身份/长度检查。
- `analyze.py`：逐回复、逐对、重复、风险对照及来源审核接收。
- `plan.json`、`configs.json`、`request_manifest.csv`：当前草案身份和精确清单。
- `human_and_historical_reference_private.json`、`variants_private.json`、`semantic_review_template_private.csv`：本机参考，不进入API字段。
- `budget_ledger_snapshot.json`、`cost_scenarios.csv`：真实旧账与预计新账分离。
- `approval_template_PENDING.json`：明确未获批准；不得用空字段猜余额/许可。

本轮到离线准备和验证结束；没有真实候选分数、没有最终冻结、没有新资格结论。
