# A0 有界 GPU 实测申请：CPU 准备，无运行授权

本轮只复用既有资产、构造输入并静态检查环境。GPU 调用、模型权重加载、真实生成、训练、付费调用均为 0。`GPU_PLAN.json`、`OFF_REUSE_CHECK.json`、输入 JSONL 和代码构成可审阅申请；`APPROVAL_TEMPLATE_NOT_AUTHORIZED.json` 的 authorized=false 不是授权。

100 条原有 OFF 请求未重采样，逐条验证请求 SHA、原生 token 数和 token IDs SHA 与 A0/repair_1 一致，输入 70–877 token。额外四个已合法读取的 G0e 资源条件用于较长输入测速。没有使用旧模型输出或 Judge 分数作为新测试证据。

静态兼容性：现有 vLLM 0.19.1 注册表不含权重声明的 `Gemma4UnifiedForConditionalGeneration`；不通过别名冒充支持。HF transformers 5.17.0 有该实现，作为方案指定的命名回退，实际运行兼容性仍未测。Qwen3.5 的 vLLM 架构存在，但这不是显存或吞吐验证。当前准备的可执行测速使用命名 HF 路径；vLLM Gemma 实测须先解决架构兼容并建立新 runtime 身份。不得自动换模型。

Qwen 本地缺少 generation_config.json：修复准备脚本，EOS 来自固定 config.text_config，PAD 来自固定 tokenizer 词表，明确 greedy/nonthinking/800。不会下载或推测默认配置。仅复用 B 的真实 NeedCard 输入构造器及 RS-v0 类别目录，选短/中/长三张输入，pack SHA 和 token 数与 B 已固定 20 张 CPU 预检一致。J1 的真实 Checklist/回复输入尚缺，不能把这组测速称为 J1 吞吐。

## 建议批准的有界工作量

| 阶段 | 输入与 batch | 最多实际请求（含 warmup） | 加载次数 | 阶段硬停止 |
|---|---|---:|---:|---:|
| Gemma HF | 100 OFF + 4 资源条件；另 16 短请求分别按 4/8/16 batch，完整 padded context≤32768 | 154（含 2 warmup） | 1 | 7200 s |
| Qwen HF | 3 张真实 NeedCard 短/中/长输入，batch=1 及受容量限制的 batch≤2 | 7（含 1 warmup） | 1 | 3600 s |

这是运行预算与停止上界，不是预计耗时。输入及实际分批清单已固定在 plan；长请求不可截断，单请求+输出保留必须 fit。Qwen 长上下文若 OOM，停止并保留错误，不自行缩短原文或转模型。A0 各 batch 的独立 `A0-probe:` 身份用于测速，不写 G0e/B6e 正式终点缓存。

仅允许 A6000 UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`。同一共享 flock；启动前无其他 compute PID 且空闲至少 30 GiB，运行中每秒检查其他 PID、剩余显存（2 GiB 停止线）及阶段期限。检测到 B/其他任务则停止自身，不抢占、不杀别人、不切 GPU。启动前 fresh 验证权重 SHA、精确 runtime 版本、请求和 runner SHA。每批超时 300 s；保留 STARTED/FAILED/逐批日志，不自动重试。外部 timeout 是阻塞内核的第二道上限；显存监测不是原子设备预留，因此仍须与 B 安排独占窗口。

获独立批准并签入具体 approval_reference、plan SHA、workloads、到期时间后，才执行下面命令（本轮没有执行）：

```bash
export CUDA_VISIBLE_DEVICES=GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4
export PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTHONPATH=project/src
# APPROVAL.json 必须是研究者另行批准后填写的文件，不是本目录 false 模板。
timeout --signal=TERM --kill-after=60s 7500s /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/rl1v3/a0_bounded_run.py --plan project/outputs/pm_rl1/v3/A0_bounded_cpu_20261118/GPU_PLAN.json --approval APPROVAL.json --workload gemma --out NEW_GEMMA_RUN
# 前一阶段退出、释放 GPU 并再次核查独占后，独立执行 Qwen：
timeout --signal=TERM --kill-after=60s 3900s /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/rl1v3/a0_bounded_run.py --plan project/outputs/pm_rl1/v3/A0_bounded_cpu_20261118/GPU_PLAN.json --approval APPROVAL.json --workload needcard --out NEW_QWEN_RUN
```

测量模型加载、同步 first forward/prefill、后续 forward/decode、首 token、生成 wall time、输出 token/s、请求/s、Torch 峰值 allocated/reserved 和观察到的空闲显存。按实际输入长度、batch、EOS/技术截断分别保存。局部模型延迟不等于 Tokkio 端到端等待。GPU 路径目前只作静态/CPU 防护测试，尚未验证其运行成功。

## 成本与缺失信息

`a0_project_cost.py` 只接受与 plan execution identity 一致的真实批次记录，排除 warmup；没有测量则保留 null。B1 20 张、B6e 120 个 G0 / 最多 360 次 J1 的预计秒数当前均为 null。B 原配置尚为 128/384，需 B 按研究者最新要求固定新调用 manifest，A 未改 B sampler。

S=288 / M=482 / L-realized=748 的有限域上界分别为 4608/7712/11968 个 G0、13824/23136/35904 次 J1；不可得头将减少实际数量。`COST_STATUS.json` 对各规模保留未知耗时，正式投影使用测得按长度/batch 的秒/请求范围，另计加载、排队和重试。没有 J1 实际输入与测速时不会给出总耗时估值。

首轮缺失 Qwen generation_config、次轮读取了旧审计不存在的 identity 字段，均保留失败日志并修复；模型身份现由固定文件集与 runtime/分批清单计算。A0 全任务仍缺独立 GPU 授权和真实实测，不标 completed。
