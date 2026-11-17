# A0 CPU 环境与成本准备结果

2026-11-17，engineering_only。本次完成无需额外授权的 CPU 盘点、模型真实文件身份核验、100 个真实 OFF 请求准备和原生 tokenizer 容量检查。**A0 的 GPU 吞吐/训练显存验收仍未完成；不选择 S/M/L 档位。** G0 尚未冻结。最终环境报告为 `repair_1/ENV_REPORT.json`；根目录 `ENV_REPORT.json` 保留首次分词失败的原始记录，不能把它误读为最终成功报告。

实际环境：

| 环境 | Python | torch | transformers | vLLM | pytest |
|---|---|---|---|---|---|
| paper1-judges-py312 | 3.12.14 | 2.7.1+cu128 | 5.17.0 | 0.10.1 | 未安装 |
| paper1-py311 | 3.11.15 | 2.3.1+cu121 | 4.57.6 | 未安装 | 8.4.2 |
| paper1-qwen35-vllm-py312 | 3.12.14 | 2.10.0 | 5.5.1 | 0.19.1 | 未安装 |

这些环境未安装 accelerate/peft/trl/bitsandbytes；不能据模型大小宣称 QLoRA 已可运行。未安装或升级任何冻结环境。测试使用既有 cp311 jsonschema vendor。vLLM 版本存在不等于已验证支持 Gemma，本轮不作此声明。

模型文件全部实际读取并计算 SHA256，没有加载张量：Gemma-4-12B-it 实际 config 为 gemma4_unified / Gemma4UnifiedForConditionalGeneration，Qwen3.5-9B 为 qwen3_5 / Qwen3_5ForConditionalGeneration；两者 text config 的 max_position_embeddings 均为 262144。Gemma 配置、tokenizer、模板及权重与旧 PROTOCOL.json 逐项匹配；BGE-M3 权重匹配固定 revision `9a0624b896d81da7492a910ffa53731274b6cf3d` 和 SHA `993b2248881724788dcab8c644a91dfd63584b6e5604ff2037cb5541e1e38e7e`。BGE 底层 position config=8194，而 sentence_bert_config 的实际窗口=8192，最终报告分别保留，检索不得使用8194来截取编码输入。Qwen 文件身份是本次实际快照，不冒称已有独立冻结。

GPU 只读快照：指定 A6000 UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`，总 49140 MiB、空闲 48551 MiB、利用率 0%，当时 compute-apps 查询为空。快照不是将来空闲保证，也不是 V3 推理授权。历史 11/04 的36次限定实验已关闭，其许可不转移到新的100请求探针。没有加载 GPU、抢占进程或换卡。

吞吐准备使用原 P1 的114个 train/dev episode 中确定性抽出的100个不同前缀；逐条与隔离的 sanitized runtime 当前会话核对完整角色/文字、rank、日期及 cut，保证恰好到 seeker 且后接真实 supporter。**未读取或交付后续 supporter 目标、资源正文、gold、需求卡。** 请求正文为 OFF，candidate prompt 单独绑定身份；每请求记录 source_prefix_sha256/request_sha256/prompt_identity，没有改 B0 的普查/折分。

修复后的本地原生 tokenizer 实测：100/100 通过，输入长度 70–877 tokens；预留 max_new_tokens=320 后全部在原生上下文内；CPU 加载/分词耗时 1.938 秒（这是 CPU 探针时间，**不是生成吞吐或客户端等待**）。首次失败原因是 Transformers 返回 Mapping 类型 BatchEncoding 而非 dict；修复为 Mapping.input_ids 读取并验证单批维度，保留原 traceback、原探针代码与首次 manifest。真实复跑输出在 repair_1，未覆盖失败证据。增加回归覆盖这一返回类型。

定向测试：13 passed，0 failed。输入模型/来源文件、输出请求/分词结果及代码身份见 `repair_1/MANIFEST.json` 和 `DELIVERY_MANIFEST.json`。可在本机复核 manifest，或使用新输出目录重新盘点：

```bash
export PYTHONPATH=project/src
CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
project/scripts/rl1v3/a0_inventory.py --config project/configs/rl1v3/A0.json \
--out /tmp/pmrl1-a0-new-snapshot --dry-run
```

真实缺项：G0 HF/vLLM 吞吐、Qwen 判官吞吐、QLoRA 12B 峰值显存、prefill/decode/客户端等待、GPU小时和规模档位均为 null/未测。模型调用=0、训练step=0、付费=0。需要研究者对这批明确请求的 A6000 推理范围授权，并在执行前再次检查指定卡无其他任务、空闲≥30GiB；训练另按依赖及授权执行。无需为已完成的CPU盘点追加授权。

交付 B：可复用实际模型/运行环境身份和候选 OFF 请求包；不得将 A0 当成本模型已校准，latency_pred 应继续保持未知。A1/A1b 仍遵守 C0 审阅与集成门槛。
