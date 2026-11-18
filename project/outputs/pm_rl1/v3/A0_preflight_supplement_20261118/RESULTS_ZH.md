# A0 有界实测前置检查补充 v2（尚未授权 GPU）

本补充不覆盖 `A0_bounded_cpu_20261118`。CPU 申请计划 object SHA：`0476c0f19b45b3473129d5909ac12436ca44c5fc05df42fbe7994ec910d65194`。新 runner / 权重守卫 / 请求选择都绑定在新 plan；旧批准即使存在，也不适用于此 plan。当前批准模板 `authorized=false`，实际模型推理、生成、训练和付费调用均为0。

## 模型与加载路径

Gemma revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`；单文件23919549408 bytes，旧已固定权重 SHA `5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d`。本轮只读 safetensors 头部和文件大小，复核小文件 SHA；没有把24GB权重读入模型。完整字节 SHA 必须在单独授权后、正式加载前重新核对。

CPU meta-device 构建不分配权重存储、不执行 forward，CUDA 未初始化。Gemma `AutoModelForMultimodalLM → Gemma4UnifiedForConditionalGeneration` 的678个 state entries 与677个检查点张量完全匹配：仅 `lm_head.weight` 通过上游声明绑定到 `model.language_model.embed_tokens.weight`。6条上游视觉命名转换有逐项记录；没有缺失必需参数、形状错误或未知额外参数。

Qwen `Qwen3_5ForConditionalGeneration` 的760个必需张量均存在；检查点775个张量中，15个 MTP 张量属于当前上游 HF 非推测解码路径不使用的权重。精确15项名单、上游忽略规则、软件文件 SHA 均归档，不能宽泛放行任意 `mtp.*`。检查点包含 BF16 和 FP32（不是量化）。没有缺失必需参数和形状不一致。

`CHECKPOINT_PREFLIGHT.json` 固定完整软件、参数形状、header、非权重文件及既有权重 SHA。新 runner 先核对该报告、软件文件、所有实际权重 SHA；加载时显式 `trust_remote_code=False`、`ignore_mismatched_sizes=False`、`output_loading_info=True`。加载后、转入 GPU 前再次检查参数集合、非 meta、真实 tied parameter、missing/unexpected/mismatch/error；任何不一致停止。实际加载/推理兼容性仍未实测。

现安装 vLLM 0.19.1 的 registry SHA `3efaece3f48dc76d8bd6bd6825830f778365f8b2976ef4d1b42de0c9d59620c3` 未注册 **Gemma4UnifiedForConditionalGeneration**。相近的 Gemma4 类名不是合法别名。此为原生架构入口静态不准入证据，不是已做 GPU 启动测试；没有擅自尝试其他 backend 或其他模型。准备的命名回退为 transformers 5.17.0 / torch 2.7.1+cu128 / HF bf16 / sdpa。

Gemma tokenizer/template、EOS `[1,106,50]`、PAD0、greedy、seed0、no-thinking、320输出上限与 PR #10 不变。原100条OFF的请求正文与原生token IDs逐条重算一致。Qwen EOS248044、PAD来自固定tokenizer；NeedCard非thinking贪心max800。Qwen没有 generation_config.json，用已记录的model config和显式decode构建，未静默补模型。

## 请求长度与预算

| 条件 | 真实CPU输入份数 | 原生输入token范围 | 备注 |
|---|---:|---:|---|
| 旧OFF |100|70–877|原样复用，无重新采样 |
| ME |8|317–965|8个owner |
| MS |8|900–1766|完整真实RAW |
| RS |8|1509–3502|完整未验证案例 |
| ALL四头 |7|2484–4340|另保留320输出 |
| ALL可达三头 |1|2336|MP无合法候选，不冒充四头 |
| Qwen NeedCard输入 |3|3739 / 14162 / 27009|另保留800输出，32768运行时容量 |

Gemma：132个batch=1主请求 + 4个短请求batch4 + 16个短请求batch16 + 2 warmup = **最多154次**，每模型只允许1次加载。原方案104主请求/48短重复变为132/20，总量未扩大。批量测速与固定batch=1的G0e终点身份隔离；不得将批量输出写入G0e终点缓存。当前120份B6e全子集只用于CPU核对，计划只选32份资源条件作A0时长探针。

Qwen NeedCard：原3份主输入 + 3份批量重复 + 1 warmup = **最多7次**。J1真实输入尚缺，准备数为0，不以NeedCard吞吐替代J1，不产生真实NeedCard/J1标签。

## 安全执行与恢复

只有研究者明确批准上述新 plan SHA、workloads、期限和唯一设备之后才可执行。GPU UUID固定 `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`，启动空闲≥30720MiB且没有其他compute进程；flock路径为 `/opt/tokkio-data0/tokkio_projects/pmrl1-a6000-exclusive.lock`。不得杀死、抢占、迁移其他进程。加载期间监控并计入总时限；运行每秒检查他人进程及空闲≥2048MiB。单批300秒、Gemma阶段7200秒、Qwen阶段3600秒；外层timeout再保护。

授权后命令（此处仅展示，未执行）：

```bash
CUDA_VISIBLE_DEVICES=GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4 \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 \
timeout --signal=TERM --kill-after=30s 7500s \
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
project/scripts/rl1v3/a0_bounded_run_v2.py \
  --plan project/outputs/pm_rl1/v3/A0_preflight_supplement_20261118/GPU_PLAN.json \
  --approval /path/to/separately-signed-approval.json --workload gemma \
  --out /path/to/new-immutable-gemma-run
```

Qwen单独使用 `--workload needcard`，外层3900秒，必须等待Gemma释放锁。当前未授权模板实际测试在任何模型导入、设备访问、锁或输出目录创建之前拒绝。OOM、CUDA异常、加载不一致、他人任务出现、超时立即停止自身任务并保存FAILED，不自动重试、不自动换模型/量化/解码。STARTED/LOAD/WEIGHT_LOADING/batch.started/batch/FAILED/FINISHED和原始stdout/stderr应一起保存。恢复必须新建输出目录、核对已启动调用数量，取得绑定剩余额度的新明确授权，不覆盖部分结果。

将测量加载墙钟/峰值allocated/reserved/设备free、prefill/decode forward速度、TTFT、每请求输入输出tokens、batch/阶段耗时、正常EOS/截断/失败和各资源条件成本。CUDA同步hook会带测量开销，不能称为用户端到端延迟。HF batch=1是否满足B6e规模仍为待测。

## S/M/L-realized

`COST_STATUS.json` 分别登记 S=288、M=482、L-realized=748。有限域上界G0为4608/7712/11968次；J1上界13824/23136/35904次，NeedCard为288/482/748。实际无合法头会减少终点数，这些不是已经实现的GPU调用数。L=960明确不用。

全部时长、峰值显存、吞吐、正常结束率和可行性结论目前为待测；不填写推测实测值。取得测量后只用同execution_identity、同工作负载（NeedCard与J1分开）且非warmup的记录计算；B6e投影用batch=1、相近输入长度的Gemma记录，另加实际加载和排队时间。没有足够J1样本时总时间继续不确定。HF不满足门槛时停下提交证据和选项，模型替换须复核，不按生成质量选模型。

## 实际修复

最初CPU头部校验假定所有Qwen张量BF16，真实头部发现FP32，已修为按实际BF16/F32字宽逐项检查文件偏移；未转换权重。第二次报告序列化遇到HF内部set，改为排序列表。两次失败原始日志保存在 `preparation_failures/`，最终结构检查通过。这些都是CPU准备错误，不是GPU运行结果。
