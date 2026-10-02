# Paper-1 Qualification Results Packet（2026-08-20）

## 结论

本轮是 **outcome-blind qualification 执行**，不是 Top-k 质量 calibration、PM effect、PM training 或正式 ESC-Eval / ES-MemEval。两项研究者批准的结构决策已经冻结；三条 qualification 线均按预注册前门执行，并在真实未满足条件处停止。当前状态为：

- ESC `large_52` 与 RQ2 `K=5, seed=0`：`FROZEN`；
- RS resource semantics：材料已就绪，真实 human review `0/64`，因此 uptake 未启动；
- Semantic Memory v7：真实 old-DEV regression 失败，401-session 全量未启动；
- ESC evaluator：盲评包与 bias probes 已就绪，但 ≥24 GiB runtime、精确 judge identities 和两名真人评分均未完成；
- 四把 calibration/confirmatory outcome lock 均为 `CLOSED`，formal outcome calls=`0`，PM training runs=`0`。

## 1. 已冻结的结构身份

| 决策 | 冻结值 | 机械证据 |
|---|---:|---|
| ESC split | `large_52`, seed 0 | 173 个 non-ESConv primary-transfer cards：52 calibration、121 confirmatory |
| RQ2 outer folds | `K=5`, seed 0 | 1586 targets、477 exact-evidence components；fold targets=`317/317/317/317/318` |

split、K 或 seed 均不得更换；禁止 seed shopping。冻结 manifest 为 `paper1_structural_split_fold_freeze_20260820_v1.json`，SHA256=`a9f62d305b82ff04cc986b02bdb840e59838405caf00913998988b8f8c5e92f8`。

## 2. A 线：RS resource qualification

Aggregate reporting / interpretation rule 已在人类结果出现前冻结：报告 overall、rank 与 family 分层的原始分子分母、比例与 Wilson 95% 区间；不设事后 PASS 线。64-item review sheet 已盲化 rank、family、similarity、provenance、PM identity 和未来 arm。

Human 或 LLM 的 state-appropriateness、冗余或 near-duplicate 判断不得成为 candidate-level/runtime utility filter。只有另行机械确认的 identity、leave-dialogue-out、atomicity、explicit boundary、executability 或 leakage 结构失败才可 hard-exclude。

真实状态：human=`0/64`、LLM=`0/64`。因此 treatment-uptake assignment=`0`、Llama Generator calls=`0`、cost=`$0`。这不是执行失败，而是按预注册顺序停在真人节点。

## 3. B 线：Semantic Memory v7

v7 runtime 在离线门通过后，对旧 32-item DEV packet 做了 verifier-only live replay。29 个 source sessions 的 29 次 Qwen 调用全部完成，费用 `$0.08161918 / $5.00`；没有 outcome 调用。

| DEV 指标 | 结果 |
|---|---:|
| old FAIL/REVIEW 被拒 | `7/12` |
| old PASS 被保留 | `6/20` |
| local strict schema/gate rejection | `11` |
| provider call failure | `0/29` |

该结果触发 `DEV_REGRESSION_FAILED_401_NOT_RUN`：

- 11 条是 Qwen 输出的 `accepted/reason` 与其自身 typed evidence flags 冲突；本地 fail-closed 正确；
- 5 条旧 MP FAIL 被接收，均通过 ID/class/span binding，问题是 Qwen 对 future plan、recent health、education-vs-occupation、third-party subject、episodic event 的语义证据分类错误；
- 14 条 old PASS 被拒由 8 条 Qwen gate 矛盾、2 条 MP 语义误拒与 4 条本地 ME shared-span ordering bug 构成；
- shared-span bug 已作最小本地修复并单测，但它不能解决其余语义/contract 问题，且没有据此重跑 API。

因此 401-session full compile 没有启动；不存在新 v7 catalog、held-out IDs 或 human packet。post-run runtime identity 已改变，剩余 `$4.91838082` 不能在没有新授权的情况下继续使用。

## 4. C 线：ESC evaluator qualification

已构建 24-item blind package：6 条 pinned public natural-baseline dialogues，加 18 条 controlled bias items。9 个 controlled pairs 覆盖 verbosity、redundant suggestions、list/format style；每对 control/variant 绑定同一 context 与声明的 semantic atoms。两名独立真人现已各完成 `24/24`，原始提交按字节保存。

数据质量审计发现历史 v1 instrument 将官方 `Humanoid` 与 `Skillful` rubric 按位置对调。该问题属于标签绑定错误，不是评分缺失：原始提交保持不变，normalized artifacts 只机械执行 `v1 Skillful → official Humanoid`、`v1 Humanoid → official Skillful`。无需因此重评 24 项。

双人 Overall agreement 为 QWK=`0.7571`、Spearman=`0.8007`、MAD=`0.625`；24 项中仅 1 项 Overall 绝对分差 ≥2。分歧作为人类测量不确定性保留，不将任一 reviewer 静默指定为 primary。controlled verbosity variants 同时改变了支持性 framing，因此其结果不能被解释为纯长度偏好。

唯一 major-Overall 项 `escq_0e49439a9e28fb56` 已在不显示原始 rater scores、继续隐藏 identity 的条件下裁决为 `Overall=4`。human reference 现冻结为“两名等权独立 reference + 唯一 major-Overall targeted adjudication”；当前 24-item reference 不再需要额外人评。

当前不能给 evaluator winner：

- 本机 RTX 2070 只有 8192 MiB，没有已连接的 ≥24 GiB GPU，也没有 pinned model snapshots；
- 两名真人盲评及唯一 major-Overall targeted adjudication 已完成；不构造伪造的完整单一 human gold；
- Qwen、DeepSeek judge 的 exact model/version 未由研究者冻结；
- 第四独立家族及 exact model/version 未指定。

因此 ESC-RANK dimension calls=`0`、general judge calls=`0`、recommendation=`null`。选择顺序继续固定为 validity/agreement → bias/sensitivity → cost/latency，禁止按哪个 evaluator 让 PM/Ours 得分更高来选。

## 5. 锁与执行账

| 项目 | 数值 |
|---|---:|
| Qwen semantic compiler calls | 29 |
| Qwen cost | `$0.08161918` |
| Llama Generator calls | 0 |
| general judge calls | 0 |
| ESC-RANK calls | 0 |
| formal outcome calls | 0 |
| PM training runs | 0 |

`RQ1_RS_CALIBRATION_OUTCOME_LOCK`、`RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK`、`RQ1_CONFIRMATORY_OUTCOME_LOCK`、`RQ2_CONFIRMATORY_OUTCOME_LOCK` 均保持 `CLOSED`。

## 6. 下一研究者决策点

1. 安排并完成 RS 64-item blind human review；锁定结果后才可建立 uptake assignment 与专用 Llama authorization/ledger。
2. 对 Semantic Memory 决定是否批准新的 contract/prompt 修订；当前 v7 已被真实 DEV 否决，禁止直接继续 401。
3. 提供或租用 ≥24 GiB pinned GPU 环境跑 ESC-RANK runtime qualification。
4. 冻结 exact Qwen judge、DeepSeek judge，并指定第四独立模型家族及 exact model/version。

这些决定完成前，不打开任何 calibration lock。
