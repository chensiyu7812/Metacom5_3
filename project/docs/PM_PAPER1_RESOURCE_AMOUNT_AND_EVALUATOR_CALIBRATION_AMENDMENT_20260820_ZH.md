# Paper-1 资源数量与 Evaluator 校准修正案（2026-08-20）

状态：**ACTIVE / RESEARCHER-AUTHORIZED / SCOPED AMENDMENT / PRE-CALIBRATION**
机器合同：`project/data/paper1_authority/paper1_resource_amount_and_evaluator_calibration_amendment_20260820_v1.json`

## 1. 修正边界

本修正案只覆盖两处旧执行决定：

1. RS M2 将 `Top-1 single injection` 写成最终 primary；
2. execution blueprint Phase-2 在 zero-outcome 后直接冻结 top-k / token cap。

它不重写核心研究。Policy Manager 名称、RS/MP/MS/ME 四个二元头、Route A first-order marginal utility、其他组件 OFF 的 canonical background、四个标准化 L2 logistic heads、0.5 primary threshold、public-only、exact-evidence cross-fitting、冻结 Generator、官方 benchmark 优先级、treatment-delivery validity 与 no-synthetic-rescue 全部不变。

## 2. RS：Top-1 从“最终答案”降回候选设计点

`Top-1` 继续保留在 amount grid 中，但不再预先宣布为最终 primary。正式处理改为：先在所有状态共享的 global amount rule 下校准资源数量与 token budget，再冻结 `k*`。这里的 global 是“不是逐状态看结果选 k”；在 outer cross-fitting 中，冻结的是同一 candidate grid、选择规则和预算规则，某个 held-out fold 的 `k*_f` 只能由该 fold 之外的 calibration outcome 得到。

不变的 RS 合同：

- atomic move 仍是不可再分的 catalog unit；
- BGE-M3、leave-current-dialogue-out 和 provenance 约束保留；
- Retriever/Step1 负责构造已经冻结的候选 bundle 并决定 inject-or-not；
- Step2 只负责忠实执行已分配 bundle，不能再做 usefulness filter、rerank 或隐式开关。

exact treatment alias 以 `rendered_card_text` 的精确 SHA-256 canonicalize，保留 atomic-unit/source-card/source-dialogue/family 的 provenance union。near duplicate 只报告，禁止凭语义阈值删除。当前无 outcome surface 可审计既有 Top-4 prefix；在任何 Generator calibration call 前，还必须物化 canonical catalog 上可 deterministic backfill 的正式排名。

## 3. 新执行顺序

唯一合法顺序改为：

1. zero-outcome amount surface；
2. evaluator qualification；
3. external calibration；
4. global budget freeze；
5. repeated-effect qualification；
6. formal effect dataset / PM training；
7. confirmatory evaluation。

因此，本轮不生成正式 ON/OFF outcome，不训练 PM，也不运行正式 GPU 实验。

## 4. 双 outcome lock

### CALIBRATION_OUTCOME_LOCK

当前为 `CLOSED`。只有在 amount surfaces、候选 evaluator、人类 reference、blindness、agreement 指标与阈值、calibration item identity、API/GPU hard cap 全部预冻结并经 researcher 批准后，才可为 evaluator qualification 与外部 amount calibration 单独开启。

### CONFIRMATORY_OUTCOME_LOCK

当前为 `CLOSED`。在 k/bundle、token budget、evaluator、features、folds、Generator/Step2、matched-random、seed/call plan 以及 fold-specific PM 全部冻结前不得开启。开启后也只允许读取 confirmatory ESC-Eval / ES-MemEval 官方 outcome。

仓库旧的 `outcome_lock` 暂作为 compatibility umbrella；它现在机械要求上述两个 scoped lock 同时 CLOSED。

## 5. RS zero-outcome amount surface

输入是已经物化的 15,061 个 atomic units、11,883 个决策状态与真实 BGE-M3 ranking。新 surface 连续报告 `k=1,2,3,4`，并报告：冻结 Llama tokenizer 的实际 injection tokens、exact aliases、same-source-card、family diversity、BGE margin 与 leave-dialogue-out 可用性。

当前 15,061 个 raw units 对应 13,172 个 exact canonical treatments；1,889 个是额外 exact alias（12.54%）。这证明 exact canonicalization 必须在 calibration 前完成，但不授权 near-duplicate 删除。初始 Generator calibration grid 冻结为 pure-k `k={0,1,2,3,4}`，所有 arm 共用一个不参与处理变化的 non-binding resource token cap `384`；actual injected tokens 逐轨迹另记。zero-outcome top-4 观测最大值低于该 cap，所以初始 grid 的截断率为 0。只有 calibration 最佳均值位于 `k=4` 且 `k=3` 落在相对 `k=4` 的 one-SE admissible set 之外时，才允许一次性扩展 `k={6,8}`；扩展调用前必须先物化 canonical top-8 并为全部 k 重审同一个 non-binding cap。不得读取 confirmatory outcome。

## 6. Memory amount surface

当前本地真实 semantic artifact 是 401/401 sessions、2,745 accepted units。typed adapter 后 unique candidate 为：

| Head | Unique candidates | Owners with any candidate | Targets with coverage |
|---|---:|---:|---:|
| MP | 378 | 18/18 | 1,586/1,586 |
| MS | 1,411 | 18/18 | 1,586/1,586 |
| ME | 80 | 18/18 | 1,586/1,586 |

所以旧远端 `MP=3/MS=401/ME=3` 不是当前本地事实。不过 ME 每 owner 平均只有 4.44 个，MP 分布也不均；两者不得被假定可做普通宽 Top-k sweep，更不得 synthetic rescue。每个 k 必须报告 realized full-k coverage。

QA 与 Summary 已按各自 visible query 物化 typed BGE bundle/token surfaces。DG 在生成前没有静态 query；本轮只报告 unranked capacity/token envelope。其 10-round dynamic query window、调用时点和 re-retrieval schedule 必须先按 pinned official harness 做机械审计并冻结，否则 `CALIBRATION_OUTCOME_LOCK` 不得打开。

## 7. ESC evaluator qualification

审计 pinned ESC-Eval commit 后，公开仓库包含 scorer/evaluator code、331 张 English role cards、3 条 example trajectories 与 3-row example score files，但没有可用于重算 agreement 的 item-level human validation labels 或 train/validation/test assignment。example score 不能充当 qualification gold。

缺少这些 human labels **不阻塞 official ESC-RANK evaluation**；它只意味着不能声称某个 alternative judge 已经对人类评分完成 agreement qualification。official ESC-RANK 先作为 reference/primary candidate。当前本机实测 `score.py` 在 4.76 秒内因 formal env 未安装 `peft` 而在模型加载前退出，未发生 GPU allocation；同时官方 InternLM2-chat-7B 的 fp16 权重分片约 15.49 GB，本机 RTX 2070 只有 8 GiB，系统 RAM 也只有 7.7 GiB，所以 official stack 不适合在本机 qualification。下一步是在租用的至少 24 GiB GPU 上固定 base/adapters/runtime 与官方代码的 `ESC-RANK1` 路径勘误，测 load peak VRAM、warm/cold latency、parse rate 和重复输入的 exact score-vector reproducibility。只有这一步证明 ESC-RANK 本身不实用，才启动 alternative judge；Qwen 只能是与 ESC-RANK 比 agreement/cost 的 proxy。

reference rater 与所有候选 evaluator 只看到官方所需 role-card context、dialogue、rubric 和随机 item id；PM identity、arm、ON/OFF、k、token budget、Ours/baseline、retrieval score 全部隐藏。比较 quadratic weighted kappa、Spearman、MAD、pairwise ranking consistency、valid parse rate 与 cost。选择按 validity/agreement first、cost second，严禁依据哪个 judge 让 Ours 分高。

## 8. ESC split feasibility

173 张 non-ESConv English cards 只用 `source + category(res) + overlap metadata + card hash` 构建了三个 seed=0 feasibility scenario：24/149、36/137、52/121。三个 scenario 都报告 source/category 分布；本修正案不选择比例。158 张 ESConv-source cards 继续只是 overlap sensitivity，不进入这三个 primary-transfer split。

## 9. RQ2 outer folds

K=5, seed=0 的 1,586 targets / 477 exact-evidence components 结构报告已物化，五折 target 数为 317/317/317/317/318，所有 targets exactly once、所有 components atomic。K=4 与 K=6、同为 seed=0，仅作 no-outcome structural comparison；禁止 seed shopping。shared-session semantic components 仍只用于 sensitivity。

任何 held-out outer target 的 amount selection 都不得读取该 target 的 outcome。冻结对象是共同 grid、selection rule 和 budget rule；fold-specific `k*_f` 只可由 outer-training calibration partition 产生。ES-MemEval 继续使用官方 GPT-4o evaluation protocol。

## 10. 正式 amount selection rule

先在预注册 official primary anchor 上找均值最高的 `g_best`。one-standard-error admissible set 定义为：

`mean(g) >= mean(g_best) - SE(g_best)`

SE 必须使用预冻结的 cluster unit。然后在 admissible set 中选 mean Generator-input-token 最小者；仍并列时选较小 k，再按 canonical grid order。Cost 不进入训练 label/loss。

- RS：ESC-Eval `Overall`；
- QA：official LLM-as-Judge semantic correctness primary，F1/BERTScore 辅助或 tie evidence；
- Summary：Event F1 primary，official LLM Score 作 semantic/faithfulness guard，ROUGE 解释；
- DG：Weighted Score primary，LT-Memory/Personalization/Emotional Support 作 guards/解释。

禁止构造跨 QA/Summary/DG composite。

## 11. BGE engineering gate

旧实现错误地假定 live pooling config 必有字符串 `pooling_mode`；当前冻结环境实际返回 `pooling_mode_cls_token=true` 等布尔 schema。修复后同时支持并交叉核对两种 schema；缺失、多开或两种表示冲突都 fail closed。RTX 2070 的完整 GPU suite 为 11/11 PASS。

既有 census/cache 绑定 runtime identity `44922…`；当前恢复环境 identity 为 `62ee94…`。二者不相同，cache key 已包含 runtime identity，所以不能互相冒充。此次 surfaces 绑定既有 census/hash，不混算、不重编码，也没有正式 GPU 实验。

## 12. 本轮锁定状态

- paid API calls: `0`
- formal outcome calls: `0`
- PM training runs: `0`
- formal GPU experiments: `0`
- `CALIBRATION_OUTCOME_LOCK=CLOSED`
- `CONFIRMATORY_OUTCOME_LOCK=CLOSED`
