# Paper‑1 官方 Mistral‑24B 本地后端与方差实测

## 结论

ES‑MemEval 官方 DG 的 observation relevance（1–3）与 observation usage（boolean）后端已经在本机 A6000 上跑通。这里验证的是官方接口、资源和吞吐，不是系统质量 outcome，也不是自设的论文 PASS/FAIL 门。

固定身份：

- 模型：`mistralai/Mistral-Small-3.1-24B-Instruct-2503`
- revision：`68faf511d618ef198fef186659617cfd2eb8e33a`
- 权重：10 个 Hugging Face safetensors 分片，共 48,022,800,560 bytes；BF16、未量化
- 环境：Python 3.12、vLLM 0.10.1、Torch 2.7.1+cu128、Transformers 4.55.4、mistral-common 1.11.7
- 设备：RTX A6000；A4500 不参与

## 必要运行配置

官方模型卡说明 BF16/FP16 约需 55 GB GPU RAM，单张 48 GB A6000 不能把模型、KV cache 与运行时全部直接驻留。因此使用 5 GiB CPU offload；这不量化、不替换也不改写权重。

实际稳定配置为：

```text
CUDA_DEVICE_ORDER=PCI_BUS_ID
CUDA_VISIBLE_DEVICES=1
vllm serve <pinned snapshot> \
  --served-model-name mistralai/Mistral-Small-3.1-24B-Instruct-2503 \
  --tokenizer-mode mistral --config-format hf --load-format auto \
  --dtype bfloat16 --max-model-len 4096 --max-num-seqs 16 \
  --gpu-memory-utilization 0.98 --cpu-offload-gb 5 \
  --generation-config vllm \
  --limit-mm-per-prompt '{"image":0}' --mm-processor-cache-gb 0 \
  --guided-decoding-backend xgrammar \
  --guided-decoding-disable-any-whitespace
```

`disable-any-whitespace` 是接口兼容配置：默认 xgrammar 会让该模型在 JSON 的 `{` 后持续生成换行，耗尽官方 30-token 上限。启用后仍使用官方 `ScoreSchema` / `JudgementSchema` 和 30-token 上限，只禁止无意义的任意 JSON 空白，不改变允许的分值或布尔语义。

## 实测

样本来自公开历史对话，均匀覆盖 owner/topic/session/observation 表面；没有使用任何正式系统生成的回复，也没有读取正式 outcome。

| 项目 | 结果 |
|---|---:|
| 官方 temperature 省略首轮 | 100/100 schema-valid，100/100 stop |
| 同一 100 条重复 | 100/100 schema-valid，100/100 stop |
| 两轮判值一致 | 48/100 |
| 首轮吞吐 | 2.091 req/s |
| 102,720 calls 稳态外推 | 13.64 A6000 小时 |
| 单条 latency 中位数 / p95 / max | 3.52 / 5.32 / 5.94 s |
| prompt tokens 中位数 / max | 1,396.5 / 1,925 |
| completion tokens 中位数 / max | 11 / 19 |
| A6000 常驻峰值 | 48,505 / 49,140 MiB |

冷缓存 temperature=0 诊断首轮为 0.689 req/s，对应保守 41.43 小时外推；缓存稳定后固定 100 条重放达到 1.976 req/s。正式排程应保留启动预热与断点续跑余量，不能把 13.64 小时写成硬承诺。

## 方差的正确解释

官方代码创建 `ChatOpenAI` 时不传 temperature，因此正式 evaluator 是 sampling judge。48/100 的重复一致率说明单条判值有明显波动，但这不是 backend 失败，也不能靠改 parser 消除。

temperature=0 的附加诊断中，不同 continuous-batching context 下固定 100 条只有 62/100 与第一次相同；挑出其中 6 条顺序运行并连续重放则 6/6 相同。这表明并发数值路径也会影响临界样例。

Paper‑1 的处理规则是：

1. 正式主指标保持官方 temperature 省略契约，不以 temperature=0 偷换官方 evaluator。
2. 冻结并记录请求顺序、并发、server seed、模型与环境；承认这提高复现性但不保证单题确定。
3. 推断与置信区间以 owner/scenario 为独立单位，不把 102,720 个 observation 调用当成独立样本。
4. 小到无法越过 scenario-level uncertainty 的系统差异报告为证据不足，不写成确定增益。
5. 不做结果驱动的逐题重问、挑最好分或多数投票；若未来增加多次 judge，必须在看正式结果前另行冻结为统一协议。

## 正式请求排程

`paper1_official_mistral24b_formal_schedule_contract_20260904_v1.json` 已在 formal outcome=0 时冻结排程算法：以 owner/scenario/turn/observation/judgement-kind 为 matched unit，同一 unit 的六个系统请求保持相邻，并按固定 seed 对 canonical arm order 做循环平衡；禁止按 system arm 整块评分。pilot 启动命令没有显式传 `--seed`，因此不追认其 seed identity；正式 server 必须显式传 `--seed 0`。正式运行前还必须把每个 request hash、schedule position 和最终 manifest hash 落盘；断点续跑只能恢复原 manifest 的 pending suffix，不得重新 shuffle。

该安排只防止 arm 与调用顺序/batch context 系统性重合，不声称消除 sampling 或数值路径方差。正式推断仍使用 paired comparison 与 owner/scenario-clustered uncertainty，并保留 batch/restart block 作敏感性分析。

权威结果：`paper1_official_mistral24b_backend_pilot_20260904_v2.json`；greedy 与 batch-context 诊断分别保存在 V1 pilot 和 batch-context diagnostic。所有付费 API 调用、formal outcome 调用和 PM training 均为 0，四个 outcome lock 保持 CLOSED。
