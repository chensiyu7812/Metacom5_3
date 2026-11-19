# A0 独立最小运行申请（未授权）

此作业只检验 G0e 真实加载、输出结束、运行计时和同机重复确定性，不用于情感支持质量评价。与 PP1 分开签署、分开调用账本、分开目录；无 warmup、无自动重试、无 Judge。原有 100 OFF 及更大 A0 方案不会自动执行。

- 最终模型 Gemma-4-12B-it，revision 707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7；本地路径 /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3。
- 权重 model.safetensors：23,919,549,408 bytes；SHA256 5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d。完整非权重 hashes、系统提示、decode、tokenizer/template 在未改动的 ../ms_pp1_prepare_20261119/cpu_v2/BASELINE.json。新增当前逐字节核查收据与未来加载前重算分别记录，读取权重字节不构建模型或 tensor。
- tokenizer native-tokenizer:79ff7ef649a97ffd84dc42f243db15a3ca7bc1eea618a9f9454e4f37942a8c92；G0e G0e:b624c7c3f99ffe6b35eca29e2f93ea9e624e66b31303415e4b9c4b1bc4c6c07e。
- 原 renderer renderer:e04b6de4d78624db4379c25537b9e6f8571b00b4c4edee681c7b5b3e31bb3d27，Step-2 pmrl1v3-g0e-no-plan-1；这 4 次均 OFF，无 Notes。
- decode decode:de376c64c6da1bc02d0752811d8a0dffeec41f2bd9cf869a1e8c1af16f448069：greedy、seed 0、max_new_tokens 320、enable_thinking false、num_beams 1，EOS [1,106,50]，pad 0，repetition penalty 1，suppress [258883,258882]。
- 执行器代码 HEAD 575011b43947f4aaf73d6bb31f376bf4c36405fc。申请还必须绑定最终交付 checkout HEAD；计划内逐文件 SHA 与代码 HEAD 对照，授权文件必须与实际干净 checkout 完全相同。代码报告提交与交付提交分开，避免自引用 hash。

## 精确调用

从 #12 固定的 100 个 OFF_reused，排除与 PP1 完全相同 messages，再按原生输入长度与 request ID 排序，取最短/最长各重复两次。100 个全部满足排除条件。没有使用生成结果；不是更换 PP1 测试问题。

| 顺序 | 原请求来源 | 输入 token | 重复 |
|---|---|---:|---:|
| 1 | 50478e6d85dd6d834eedb020d175a69120b0dfd90f8a51aa930c1b0fd3778296 | 70 | 1 |
| 2 | 同上 | 70 | 2 |
| 3 | 0f0085a3167fa68a1607e8e5b74b31cd56efe92065a02ccfacd672e6e4735007 | 877 | 1 |
| 4 | 同上 | 877 | 2 |

精确新 A0 request IDs、messages、token IDs、source commit/path、payload SHA 见 cpu_v2/A0_CALLS_4.jsonl 和 A0_SELECTION.json。这仅覆盖 OFF 的 70–877 token 范围，不声称实测覆盖 PP1 最长 1,766 token 或所有资源使用行为。

## 加载与停止

单 A6000 UUID GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4，HF batch=1，bf16，SDPA，TF32 false，deterministic algorithms true。Python 3.12.14 / torch 2.7.1+cu128 / transformers 5.17.0 / tokenizers 0.23.2 / safetensors 0.8.0；不用 vLLM，不换模型或后端。

只能由已准入 supervisor 启动内部子进程，AutoModelForMultimodalLM.from_pretrained(local_files_only=True, trust_remote_code=False, ignore_mismatched_sizes=False, output_loading_info=True) 一次；校验 #12 header/shape/tied weights 与 loading diagnostics，再移到指定 CUDA 设备。677 checkpoint tensors + 1 tied alias 的既有 CPU 结构证据不是加载成功证明。新 checkpoint guard 逐字复制 #12 模块到独立名字，未改旧 PR。

GPU 预计约 4–8 分钟（加载约 3–5 分钟加 4 次小输入生成；未实测）；显存预计 26–36 GiB，权重约 22.28 GiB 加 KV/激活/加载余量。启动前需至少 40 GiB 空闲，无其他 compute PID；不预占设备。测量后再修订后续预算，不能扩大本作业。

每作业总硬预算 1,200 秒，包含 fresh hash，加载最多 600 秒，每调用最多 300 秒，取剩余总预算的较小值。独立 watchdog 杀掉本作业子进程组；日志收尾可能稍晚，不能继续生成。hash 本身只在 CPU 分块读取。首次技术失败、空回复、OOM、版本/权重/原生 token 不符、占用冲突、容量不足、任意 length 截断或重复对 token IDs 不同立即停。任何失败不得重试或补足，未完成项 pending；从未测量的吞吐/显存不填实测值。

每个物理调用前持久写 REQUEST_START，返回原始 token IDs/文本/finish reason 后再验证。events 链式 SHA、UTC、顺序号、payload SHA、耗时、显存以及最终 SUMMARY 构成账本。授权 claim 用 O_EXCL 防复用；未决 START 不能重新发起。另作新的授权决定才可改变计划，不允许编辑既有账本。

阻塞：G0e 路径未签署、最终执行器 B/负责人签收未取得、根盘储备不达标、研究者未单独授权。A0_MIN_AUTHORIZATION_TEMPLATE.json 明确 false，填写模板或 CPU PASS 都不是授权。
