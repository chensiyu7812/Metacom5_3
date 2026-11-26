# SC36 执行前 CPU 组合兼容检查

结论：PASS。已批准的 `packages-v3` 可继续按原授权及原 GPU 守卫执行。本检查没有修改原包、plan、worker、decode 或评分器，也未实例化模型、加载权重或调用 GPU。

实际读取原 Gemma tokenizer、配置及冻结 decode，以当前 Transformers 的 `_get_logits_processor` 和 `_get_stopping_criteria` 构建组合。确认真实 `Gemma4UnifiedForConditionalGeneration` 没有覆写这些 helper；CPU 门面只承载配置，没有模型参数或 forward。

- 实际处理顺序：`SuppressTokensLogitsProcessor` → `StructuredConstrainedProcessor`。
- 原 suppress `[258883,258882]` 始终为负无穷，与 EOS `[1,106,50]` 无交集。
- 36 个原输入 tokenizer 身份一致；140 条原 prompt 可见候选路径、5,492 个真实 262,144 维 CPU mask 步骤全部通过，每步至少保留 2 个 finite logits，无 NaN 或正无穷。
- 三种 EOS 只在完整 JSON 边界可用；HF 原停止条件为 `MaxLengthCriteria` 和 `EosTokenCriteria`，319 新 tokens 未停、320 停止及三种 EOS 停止均通过。
- 组合检查循环实耗 26.829 秒；`model_loads=0`、`gpu_calls=0`、`cuda_initialized=false`。

这是有限可达前缀上、以 finite 合成 logits 输入进行的真实处理器组合测试。它没有证明任意语法前缀、实际模型 logits 的数值稳定性、GPU mask 传输或任务答案正确性；原 1200 秒硬限及异常停止规则继续生效。HF 对 suppress 的定义是将指定 token 分数置为负无穷；本次通过实际组合检查确认语法 mask 没有将其恢复。[官方 Transformers 5.17.0 generation 文档](https://huggingface.co/docs/transformers/v5.17.0/en/internal/generation_utils)

原 catalog SHA256：`0574640d2be436b410bc6f5aca236218d4a4f5f4a313f634b5f5b5c2bf08289c`。

私有回执：`/opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126/COMPOSED_LOGITS_CPU_CONSTRAINED.json`，完整 SHA 见同目录公开聚合 `CONSTRAINED_CPU_COMPATIBILITY_PUBLIC.json`。逐请求见证只保留在私有回执；公开文件不含问题、答案或原文。

复跑使用新输出文件，命令不启动模型：

```bash
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/journal_check_structured_constrained_compatibility.py \
  --package /opt/tokkio-data0/tokkio_runs/pmrl1-j-selection-20261126/structured/packages-v3 \
  --out NEW_CPU_RECEIPT.json
```
