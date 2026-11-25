# 原结构化 36 次：一次约束解码诊断申请

状态：CPU_PREPARED / GPU_NOT_AUTHORIZED。起点 `35650aa2d63a52d59e73d549a19ac64996b9314a`。申请固定原 18 题 BASE/RAW 完整配对，共 36 次新调用；没有执行新 GPU、API 或训练。原 154 次结果和原严格评分保留。

原 S1/S2 的 36 条真实回复已逐条读回：27 条纯 JSON 围栏、2 条围栏外另有 thought、7 条非 JSON；原严格裸 JSON 契约成功仍为 0/36。本次只检验增加输出结构约束后，原答案值与证据契约是否能被实际满足，不把格式通过称为任务成功。

## 唯一干预及本地可行性

模型仍是原 Gemma `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`，本地 Transformers 5.17.0、torch 2.7.1+cu128、GemmaTokenizer/tokenizers 0.23.2。原 tasks、source、messages、input_ids、原答案要求、renderer 和严格 scorer 均保持原字节。所有原 decode 配置保持，包括 greedy、seed 0、`max_new_tokens=320`、EOS `[1,106,50]`、原 suppress_tokens、无 thinking；唯一新增干预是逐 token 的语法 logits mask，另有独立 constraint/request/plan 身份。

使用现有 XGrammar 0.1.21（Apache-2.0）CPU 编译器及 matcher，复制到新私有 executor 的 `vendor_constrained` 并逐文件哈希；已有环境不安装或修改依赖。CPU 生成 bitmask，以原 torch `masked_fill` 应用，避免新 Triton kernel。原运行 supervisor、硬限、device/storage/fresh-model-SHA 守卫、单次 claim 和禁止重试逻辑复用；仅选择新 worker。原 supervisor 的 run AST 在替换 worker 类名后完全一致。

官方支持 `generate(..., logits_processor=[...])` 接口；XGrammar 提供 Hugging Face tokenizer 与 grammar 接口。此处 GPU 适配尚未实跑，不能把 CPU 通过写成 GPU 已验证。[Transformers generation API](https://huggingface.co/docs/transformers/v5.17.0/en/internal/generation_utils)、[XGrammar 官方示例](https://github.com/mlc-ai/xgrammar/blob/main/docs/start/quick_start.md)、[TokenizerInfo 接口](https://xgrammar.mlc.ai/docs/latest/api/python/tokenizer_info.html)。文档当前版本仅说明接口；实际使用的是本地已检查并冻结的 0.1.21。已有 LM Format Enforcer 0.10.12 的 Transformers integration 实际出现旧导入路径错误，未修改旧环境修复。

静态 schema 只有 `value/certainty/quote/speaker` 四个字符串、`reported_date` 字符串或 null，五字段必需、无额外字段。**没有答案、候选值、speaker、certainty、日期的 enum/const/pattern**，没有 source/gold 条件分支。候选答案仍只来自原 prompt。编译器按 schema 属性顺序生成；字符串值不受语义限制。它能接受错误答案、错误 speaker、无效日期，因此既不保证原未知协议，也不保证事实或引文正确。EOS 集合不变，只有语法完整时允许结束；到原长度上限仍按 length 未完成处理，不强行闭合、不重试。

## CPU 实测与计量

- 36/36 原 messages 的原 tokenizer 读回 input_ids 完全相同；18 完整任务配对。
- 原提示中的全部 140 个候选值见证均能到达语法终态；最大见证 50 tokens，未读取参考答案来编译 grammar。
- 3 个原 EOS 均通过；围栏、块外文字、错误字段类型、额外/重复字段、残缺 JSON 等 8 个负例均拒绝。
- 真实 262,144 词表通过 Transformers `LogitsProcessorList` 的 CPU mask 测试。最终测试 grammar 编译 1.197 秒（含 tokenizer 总 2.894 秒）；50 步 mask 中位 0.927 ms、最大 3.192 ms。此前保留的首次测试出现 47.956 ms 最大值，预算使用这个较保守观测，不舍弃慢样本。
- 8 个合成 CPU 单元测试通过，包括旧批准不可转用、重复 claim 禁止、合法 JSON 仍可因错误行动阶段失败、解析失败字段保持未评、length 未完成，以及合理 unknown 不被计成来源归属错误。两个真实旧 S 作业交给新 collector 均因作业身份不符被拒绝。
- 全部测试 `model_loads=0 / gpu_calls=0 / cuda_initialized=false`。CPU mask 计时不含设备传输；未来 worker 单列 grammar 编译和累计 CPU mask 时间，完整 generation 时间包含设备 mask，不重复相加。

## 精确申请

私有根：`/opt/tokkio-data0/tokkio_runs/pmrl1-j-selection-20261126/structured`。仅 `packages-v3` 为本次申请，v1/v2 保留为 CPU 准备历史。

| 包 | 原任务及完整配对 | 新 physical calls | 输入 tokens | plan object SHA256 |
|---|---|---:|---:|---|
| SC1 | S01–S09 × BASE/RAW | 18 | 13,225 | `07d7e0f6870627ea07f8f6dbb9f2b5b4652a7c14bf7072b5a34049d0d762bd29` |
| SC2 | S10–S18 × BASE/RAW | 18 | 13,648 | `b96ea315311d7375cd7db3252d96c40225ca22351d787965ac789bb2436c32b2` |

Catalog 文件 SHA256：`0574640d2be436b410bc6f5aca236218d4a4f5f4a313f634b5f5b5c2bf08289c`。Constraint object SHA256：`df0c6ddfdb0e38b03d90285852e8f92bb96d164ac5c3e97ca438a32f0b4f3e0d`。

| 包 | 完整 requests 文件 SHA256 |
|---|---|
| SC1 | `ab282445c9a606a5412e5100852f8b86f3018e22de8e37bdaf69ef315740088e` |
| SC2 | `468f65d3becb657b0da5a740f3f6651b2ac7560cea80d03a9210332f54441d54` |

两包相同的 executor inventory object SHA256（`object_sha256(plan.executor_files_sha256)`，550 文件）为 `14548d2dc00f822fca0c257ad529a0a93edc93d6adfd35d30de59b885327feb1`；隔离 grammar vendor inventory object SHA256 为 `5fd996c36287fda4c7967d94595e0b6879b6d5c4f7046ed8b848e74f74d80d23`。

每包原 GPU `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`；1 load、0 warmup、0 retry、全局硬限 1200 秒，两个包共最多 2400 秒。原 load/request 上限仍为 600/300 秒，并受全局硬限约束；OOM、非法语法状态、device/disk/hash 变化或超时停止自身作业，第三次 length 依原逻辑停止。没有跨 GPU fallback、自动续跑或扩样。

预算同时使用原 20 次实测（1380 output tokens / 108.596 秒）与原 S36（两包 152.260/147.309 秒；最慢单次约 12.279 tokens/s）。保守计划为每包最多 5760 output tokens，按 10 tokens/s、setup/hash/load 100 秒、grammar 编译 3 秒及每 token 47.956 ms CPU mask，约 **955.23 秒/包**。这不是完成保证，GPU mask 传输尚无新实测；若全局上限先到则保留未完成，不追加调用。

两份 `APPROVAL_CONSTRAINED_TEMPLATE.json` 均 `authorized:false`。只接受协议 `pmrl1-j-structured-constrained-run-v1`、job kind `JOURNAL_STRUCTURED_CONSTRAINED` 且匹配各自完整 plan SHA 的新批准。原 S/J/M/RS/Writer 批准均不可转用。

## 执行及评价入口

CPU 检查使用新 executor；以下 `P` 为私有根下 `packages-v3`，`PY` 为 `/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python`：

```bash
PYTHONPATH="$P/executor/project/src" "$PY" \
  "$P/executor/project/scripts/rl1v3/journal_structured_constrained.py" check \
  --plan "$P/batch-01/PLAN_CONSTRAINED.json"
```

获得独立批准后，各包已有可执行脚本（两参数分别为新批准文件和全新数据盘 run root）：

```bash
bash /opt/tokkio-data0/tokkio_runs/pmrl1-j-selection-20261126/structured/RUN_SC1_CONSTRAINED_V3_AFTER_APPROVAL.sh NEW_SC1_APPROVAL.json NEW_SC1_RUN_ROOT
bash /opt/tokkio-data0/tokkio_runs/pmrl1-j-selection-20261126/structured/RUN_SC2_CONSTRAINED_V3_AFTER_APPROVAL.sh NEW_SC2_APPROVAL.json NEW_SC2_RUN_ROOT
```

脚本在新 run root 隔离 cache/tmp，旧执行器和旧 run 目录不变。不能使用仍为 false 的模板运行。

结果入口为 `project/scripts/rl1v3/journal_collect_structured_constrained.py --plan ... --job ... --original-outputs ... --out NEW_RESULT_DIR`，以当前固定 stack 的 PYTHONPATH 运行 CPU 收集。它核对新请求及 hash chain，原输出文件 SHA、task/payload/renderer/source-reference/constraint/scorer 都进入对应端点身份，不把旧 jreq 输出挂到新 jconstrained。

严格 scorer 仍为 `structured_learning.evaluate`，SHA `a83cc1b5960cb419bc893768f190da0664630cdc18c3ee4e9e63ae0a9374d87d`。另外只提供可读字段诊断：格式、答案值、引用是否真实供应/原文精确子串、required literal、speaker、报告日期、原任务/阶段类别、未知协议、合规弃答、技术未完成。**解析失败时这些语义字段为 null，不能逐项记错；原严格分仍原样保留。** 不去围栏、不忽略 thought、不放宽短引文标准，不按新结果改规则。私有读回包含全量原始新旧回复和逐题来源；公开只出聚合、状态与成本。

来源字段只对实际 supported、非 unknown 的已知值声称评价；合法 unknown 形态的空 quote、speaker unknown 和日期 null 保持来源诊断未评。值正确性仍用原 scorer，缺少供应证据时的合规弃答另列，不把弃答误计成来源错误。

评价代码另冻结在 `EVALUATION_FREEZE_CONSTRAINED_V2.json`，文件 SHA256 为 `edabd66b13216768f205ab8ae8157e307db8347b0f1cf816e14ee79d1293f372`；原评价 freeze 保留。本次修正只涉及新 collector 的来源字段分母，不改变任何生成身份。CPU 证据为 `CPU_VALIDATION_CONSTRAINED_V3.json`，预算为 `FEASIBILITY_CONSTRAINED_V2.json`。新语法通过或旧 scorer 成功都不会自动批准正式 reward、训练表或 RL 运行。
