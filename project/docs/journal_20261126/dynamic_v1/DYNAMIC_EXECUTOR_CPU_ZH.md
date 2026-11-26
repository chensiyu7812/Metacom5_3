# 动态执行器的 CPU 实证与边界

新增独立执行器已经实际连接 `controller → SEARCH/EXPAND → Generator 输入`。本轮只使用确定性的 CPU 协议占位返回，**模型加载、模型推断、GPU 与 API 调用均为 0**。没有修改既有有限环境、SMV、SC36、任务、来源或历史评分。

## 已执行的检查

8 个冻结任务按 4 个来源情境配对，六臂共 48 条终局路径全部实际重建合法来源、运行检索/展开、渲染和 native tokenizer。控制器占位调用 40 次、终局占位调用 48 次，只证明协议与预算可走通。32 条既有确定策略的 `messages/input_ids/decode` 与历史冻结输入全部相等；没有读取缓存输入来冒充检索。

19 项新增 CPU 回归通过，0 跳过，覆盖全 22 次作业预算、每角色及每任务预算、失败 start 计数、禁止重试、隐藏词查询、错误 JSON、控制器截断、第三次终局 length 停机、工具预算拒绝后的强制 STOP、返回文本/ID/时钟绑定、精确 system 绑定、禁止跨臂缓存、worker 独立 task/scope 限制、spawn 计时和失败 wire 保存。测试数据为 synthetic，不写入真实源句或答案。

实际来源 CPU 收据保留在 `engineering/live-cpu-v2/CPU_CHECK_PUBLIC.json`。之后仅新增 spawn/失败观测与 fixture 标记，没有改变策略、检索、输入或预算；其 19 项最终代码回归由 `engineering/FINAL_OBSERVABILITY_CPU_AMENDMENT.json` 单独绑定，不覆盖旧实读收据。公开计数与两个收据 SHA 见 [DYNAMIC_EXECUTOR_CPU_PUBLIC.json](DYNAMIC_EXECUTOR_CPU_PUBLIC.json)。

## 执行和失败边界

每个未来作业只允许两个任务、最多 22 次 start：12 次终局、2 次 OneShot、8 次 ToolAgent；分别最多 1 次 768-token OneShot 和 4 次 192-token ToolAgent，两个控制器每任务总输出上限同为 768。固定系统、实际观察、任务、来源、渲染、payload、输入 IDs 和返回均经独立身份绑定。OneShot 只看初始观察；ToolAgent 每轮使用已实际读到的新观察。

终局沿用原 decode。两个新控制器共同使用 grammar 和 `no_repeat_ngram_size=0`，独立于终局的原值 3；原因和实际 CPU 兼容性证据见 [CONTROLLER_PROTOCOL_AND_LATENCY_ZH.md](CONTROLLER_PROTOCOL_AND_LATENCY_ZH.md)。控制器协议或 length 失败立即停止整包，0 重试；终局 length 保留技术未完成，累计第三次停止整包。合法工具预算拒绝后强制 STOP，明确不是模型选择 STOP。任何缺结果、失败或未知的正式 reward 均为空。

失败 worker 的原始 JSON、原 `failure_stamp`、原始 wire 字节和真实父进程时间区间保存为私有不可覆盖文件，并由 journal 绑定 SHA。timeout 的未观测输出与有效动作时间保持空值，不补零、不推断部分答案。CPU fixture 每个端点明确 `backend=cpu_protocol_fixture_not_model`、`real_model_output=false` 和 `cpu_fixture_transport_only`，不能作为真实生成交付。

## 可测计时与不能推出的结论

采用同主机、同 boot 的 `CLOCK_MONOTONIC` 纳秒事件。冷来源/Tokenizer/Ledger 准备与加载单列；每条 Agent 在线路径在创建 episode 和合法性检查前开始。实际 retrieval、expand、legality、tokenization、renderer、实验设备守卫及日志均有事件或嵌套区间。renderer 含 tokenization、retrieval 含 legality、tool 包含内部步骤，不能相加为总时间。

`worker_spawn` 仅测 Popen 系统调用，不代表 worker 就绪。父进程 load 和 exchange 是含 IPC、设备轮询及反序列化的墙钟，不能将 exchange 解释为纯反序列化耗时。worker 单列 tokenizer 复验、生成准备、grammar 编译及 generation；内部 callback 记录首 token/首非空解码文本，prompt callback 不代表 prefill 完成。

控制器首个有效输出只在完整 JSON 与状态合法性通过后记时；首个非空字符不等于有效动作。终局首个非空文本未取得语义资格。没有向 UI 流式交付，所以 client TTFT 始终为空。实验守卫、日志和观察 callback 的成本仍计入实际墙钟。六臂顺序固定，首次 STOP 推断为冷首推，随后共享暖缓存；未来延迟比较需报告这些限制，不能直接声称因果收益。

Top4 宏操作保留原身份：1 次检索加 4 次完整 parent 读取，共 5 操作，区别于其余策略最多 4 次 SEARCH/EXPAND 的原语域。共同 token cap 不消除操作粒度差异。

## CPU 复跑

仅测试时设置 `CUDA_VISIBLE_DEVICES=''`。以下检查不会加载权重；`--out` 必须为新目录。私有根不公开原文、问题或评价答案。

```bash
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  project/tests/test_rl1v3_journal_pomdp_dynamic.py

CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src \
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/journal_check_pomdp_dynamic_cpu.py \
  --bundle /opt/tokkio-data0/tokkio_runs/pmrl1-j-pomdp-20261126/cases/bundle-v1 \
  --cpu /opt/tokkio-data0/tokkio_runs/pmrl1-j-pomdp-20261126/engineering/cpu-v2 \
  --proposal /opt/tokkio-data0/tokkio_runs/pmrl1-j-pomdp-20261126/engineering/proposal-v2-wording \
  --resources /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/memory/resources_private.jsonl \
  --metadata project/outputs/pm_rl1/v3/A1_preparation/final/registry/registry.json \
  --base-plan /opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126/independent-memory/packages-v3/batch-01/PLAN.json \
  --asset-manifest project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json \
  --out /opt/tokkio-data0/tokkio_runs/pmrl1-j-dynamic-20261126/engineering/live-cpu-replay-new
```

真实模型服务的权重加载、GPU 数值行为和动态模型返回尚未执行验证。CPU 接线可复跑不等于本轮有模型结果，也不构成未来运行授权。
