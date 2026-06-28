# MetaCom V3.3 当前研究方案完整报告

快照时间：2026-06-24 14:19:01 JST  
项目路径：`/home/tokkio/esconv_experiment_bundle/policy_manager_35`  
报告性质：当前研究设计、工程实现和实验进度说明；不是最终论文结果报告。  

## 1. 一句话定位

本研究将长期情感支持对话中的证据使用建模为一个 **检索前资源分配问题**：

> 在固定回复生成器不变的情况下，Policy Manager 只基于部署时可见的当前对话状态和轻量 memory inventory metadata，决定是否调用 Persona/Preference Memory、Summary Memory、Event Memory 与 Strategy RAG，以在回复质量、记忆风险和资源成本之间取得更稳健的权衡。

本研究不训练新的情感支持生成器，而是在生成器外部训练一个资源调度层。核心方法名应表述为：

> supervised pre-evidence resource allocation policy

不要称为 RL、POMDP、RLHF、DPO、端到端 ESC generation model 或 clinical safety system。

## 2. 当前研究目的

当前版本的目标不是证明“更多记忆更好”，而是检验：

1. 学习型 PM 是否能在检索前预测哪些资源值得调用；
2. PM 是否能在回复质量非劣的前提下降低不必要检索和上下文成本；
3. PM 是否能减少过时、无关、突兀或未经支持的个人记忆使用；
4. PM 是否比固定动作、budget-matched fixed action 和强规则路由有更好的质量-风险-成本权衡；
5. 若 PM 跑不过 strong rule，也要诚实报告“强规则在当前可见状态下已足够强”，而不是强行写 PM 胜利。

当前最稳的论文主张不是“PM 显著提升所有回复质量”，而是：

> 在固定生成器和统一检索器下，学习式检索前资源分配可以被严格评测，并可能在保持回复质量非劣的同时改善资源效率与记忆使用可靠性。

## 3. 研究问题

### RQ1：检索前 PM 是否优于规则资源门控？

规则门控通常根据关键词、会话深度、资源可用性或固定阈值决定是否调用资源。PM 试图学习更细的条件模式，例如：同样有 Event Memory，当前是否真的适合提起；同样可用 Strategy RAG，当前是否会导致过度结构化。

### RQ2：选择性结构化证据是否优于全量或固定 RAG？

全量 raw-session RAG 成本高，并可能引入无关、过时、敏感或突兀历史。PM 的任务是只激活当前需要的资源组合。

### RQ3：Strategy RAG 是否应作为可选资源而非 always-on？

Strategy RAG 可能提升承接和指导，但也可能导致过早建议、模板化或过度结构化。因此它作为 `R0/RS` 动作轴，由 PM 决定是否调用。

### RQ4：PM 学到的是条件资源推理，还是模板记忆？

当前 synthetic 数据存在受控模板成分，因此必须通过 user-held-out、semantic-held-out、text-only、metadata-only、catalog-only、availability counterfactual 等诊断，检查 PM 是否真正利用资源可用性和当前上下文。

## 4. 系统因果流程

V3.3 沿用 V3.2 的关键因果边界：**先决策，后检索，再生成**。

```text
Step 1: Pre-evidence PM
  input:
    current user text
    recent/current session context
    current session summary
    session index/depth
    memory inventory metadata
    source-level catalog fingerprint/similarity
    candidate action id
  output:
    resource action = memory_action + strategy_action

Step 2: Evidence execution
  retrieve only selected memory source(s)
  retrieve strategy only if RS
  build prompt

Step 3: Fixed supporter generator
  generate final supporter response
```

PM 禁止读取：

- actual memory snippets；
- Strategy RAG snippets；
- selected memory ids；
- retrieval scores；
- post-retrieval evidence text；
- generated response；
- seeker reaction；
- judge labels；
- gold action / role card / scenario gold / relevant-session gold；
- future session 或 future event。

因此当前 PM 是 **pre-evidence resource allocator**，不是 evidence reranker。

## 5. 动作空间

动作空间为 8 类 memory action × 2 类 strategy action，共 16 个动作。

Memory action：

- `M0`：不调用长期记忆；
- `MP`：Preference / Persona Memory；
- `MS`：Summary Memory；
- `ME`：Episodic / Event Memory；
- `MPMS`：MP + MS；
- `MPE`：MP + ME；
- `MSE`：MS + ME；
- `MPMSME`：MP + MS + ME。

Strategy action：

- `R0`：不调用 Strategy RAG；
- `RS`：调用 Strategy RAG。

完整动作示例：

```text
M0+R0
M0+RS
ME+R0
ME+RS
MPMSME+RS
```

PM 可控资源只有长期记忆源和 Strategy RAG。当前用户话语、近期上下文、安全约束和基础 supporter prompt 是固定输入，不由 PM 决定。

## 6. 数据资源与边界

### 6.1 Synthetic development 数据

当前 development 主数据：

- `data/synthetic/runtime_states.jsonl`
- `data/synthetic/memory_backend.jsonl`
- `data/synthetic/pair_graph.jsonl`
- `data/strategy/strategy_cards.jsonl`

数据规模：

```text
source states: 192
runtime cards: 1728 = 192 states × 9 counterfactual inventory variants
users: 16
semantic families: 12
unique current texts: 36
strategy cards: 156
```

数据准备审计：

```text
data/synthetic/audit_report.json: PASS
future_memory violations: 0
memory marker violations: 0
min variants per state: 9
max variants per state: 9
```

action availability 分布：

```text
2 available actions: 192 cards
4 available actions: 768 cards
8 available actions: 576 cards
16 available actions: 192 cards
```

注意：这些 synthetic/support-gradient 数据只用于 development、judge calibration、PM training、validation selection 和内部诊断，不能作为最终外部效果证明。

### 6.2 Memory backend

`memory_backend.jsonl` 与 runtime state 物理分离。PM 的 pre-evidence features 只能读取 runtime state 中的 inventory metadata 与 catalog fingerprint；真正 memory item 只在 action execution / judging 时可见。

Memory source 语义：

- MP：稳定偏好、沟通习惯、支持风格、慢变 persona；
- MS：跨 session 摘要、长期模式、状态演变；
- ME：具体事件、时间顺序、旧事实与更新事实。

### 6.3 Strategy Bank

当前 `data/strategy/strategy_cards.jsonl` 是 pilot/development 用 Strategy Bank，共 156 条。它不是最终 confirmatory Strategy Bank。

正式 ESConv/EvoEmo 外部实验前，仍需：

1. 接入官方 ESConv；
2. 只用 ESConv train split 重建 Strategy Bank；
3. 删除与 ESConv test / EvoEmo session 的重叠；
4. 重跑 overlap audit；
5. 冻结 study protocol。

### 6.4 External data

当前已恢复：

- `data/external/evo_emo.json`：18 users；
- EvoEmo / ES-MemEval-derived 18-user longitudinal evaluation 是长期记忆外部主验证方向；
- ESConv 后续用于 Strategy routing、response-quality、memory abstention / false-memory-control，不用于证明长期记忆能力。

## 7. Pair Graph 设计

Pair graph 文件：

```text
data/synthetic/pair_graph.jsonl
```

规模：

```text
total pairs: 24720
training eligible pairs: 19776
non-training audit pairs: 4944
reversal pairs: 2966
same-order repeat pairs: 1978
```

pair type：

```text
strategy: 6970
memory: 6205
combination: 7216
chord: 4329
```

Pair graph audit：

```text
data/synthetic/pair_graph_audit.json: ok=true
connected components per card: 1
isolated actions: none
orientation balanced for RS and richer-memory positions
```

Pair graph 用于 response pairwise judge，不做全动作全排列，而是稀疏连接图。训练时非 tie pair 按 card 归一，避免动作多的 card 对训练贡献过大。

## 8. 生成器与模型配置

当前配置文件：

```text
configs/experiment.yaml
```

主要 endpoint：

```text
supporter generator:
  model: meta/llama-3.1-8b-instruct
  provider: NVIDIA API
  family: llama

seeker simulator:
  model: mistralai/mixtral-8x7b-instruct-v0.1
  provider: NVIDIA API
  family: mistral

seeker_alt:
  model: qwen/qwen2_5-7b-instruct
  provider: NVIDIA API
  family: qwen

training judge:
  model: gemini-2.5-flash-lite
  provider: Google Gemini OpenAI-compatible API
  family: google_gemini

final judge:
  model: gpt-4o
  provider: OpenAI API
  family: openai_gpt4o
```

当前选择 Llama-8B 作为 supporter generator 的理由：

- 中等强度模型更可能对 memory/strategy 资源变化敏感；
- 成本和部署现实性更好；
- 避免过强模型把所有动作都生成成接近 tie 的 ceiling。

当前 training judge 使用 Gemini Flash-Lite 的理由：

- Claude Sonnet pilot 可过，但 full judging 成本过高；
- GPT-4o-mini、DeepSeek/NVIDIA、GLM/NVIDIA、Qwen/NVIDIA 在先前尝试中分别存在测量稳定性、限流或速度问题；
- Gemini Flash-Lite 在 Protocol V3 + strategy validator fix 后通过 pilot gate；
- full judging 成本可控，估计约 8-15 USD 量级。

Family independence：

- training judge：Google；
- final judge：OpenAI；
- generator：Llama；
- seeker：Mistral / Qwen。

正式 confirmatory judging 不能使用与 training judge 同 family 的 Gemini final judge。

## 9. Action Sweep

已完成 full synthetic action sweep：

```text
script: scripts/06_run_action_sweep.py
output: outputs/synthetic_sweep/action_outcomes.jsonl
rows: 11136 action outcomes
```

动作覆盖：

```text
M0+R0: 1728
M0+RS: 1728
ME+R0: 960
ME+RS: 960
MP+R0: 768
MP+RS: 768
MS+R0: 768
MS+RS: 768
MPE+R0: 384
MPE+RS: 384
MPMS+R0: 384
MPMS+RS: 384
MSE+R0: 384
MSE+RS: 384
MPMSME+R0: 192
MPMSME+RS: 192
```

每个 outcome 记录：

- `card_id`；
- `state_id`；
- `user_id`；
- `action_id`；
- response；
- selected memory ids；
- selected strategy ids；
- memory/strategy view；
- cost；
- prompt/request provenance。

cost 字段包括：

- base prompt tokens；
- memory tokens；
- strategy tokens；
- total input tokens；
- output tokens；
- retrieval calls；
- latency；
- PM input token estimate。

这些 cost 是后续 deployment policy cost / offline sweep cost 区分的基础。

## 10. Judge 与 Measurement Protocol V3

当前 measurement protocol：

```text
docs/MEASUREMENT_PROTOCOL_V3.md
```

V3 核心变化：

1. controls 分为 hard calibration controls 与 boundary diagnostics；
2. hard controls 要求 100% 通过；
3. boundary controls 透明报告，但不做一票否决；
4. training-eligible response pairs 使用 dual-order debiasing；
5. forward/reverse 不一致时最终 response preference 设为 tie；
6. raw dual-order agreement、raw reversal、position bias 作为 diagnostics；
7. hard response signal gate 改用 debiased 后的 effective non-tie rate。

Pilot hard gates：

```text
judging complete
pair graph audit ok
hard control accuracy >= 1.0
same-order repeat consistency >= 0.80
effective non-tie response signal >= 0.25
strategy pair tie rate < 0.50
all judgment outputs complete
```

Pilot diagnostics：

- aggregate control accuracy；
- boundary control pass/fail；
- raw dual-order agreement；
- raw reversal consistency；
- raw position bias；
- tie rate by pair type；
- dual-order disagreement resolved-to-tie count。

当前通过的 pilot：

```text
output dir: outputs/judge_pilot_gemini_flash_lite_v3_strategyfix
status: PILOT_GO_FULL_JUDGING
hard controls: 9/9 pass
boundary diagnostics: 0/2 pass, reported but non-blocking
effective non-tie rate: 0.482
same-order repeat consistency: 0.966
strategy pair signal: pass
```

边界 diagnostics 未通过：

- `resp_authorized_unseen_neutral`；
- `m0_correct_optional`。

解释：这两个 control 本身混入了 naturalness / optional memory use 的主观边界，不再作为 hard gate。

## 11. Judge 输出任务

Full judging 包含 6 类输出。

### 11.1 M1 Memory Opportunity Audit

输入：

- visible context；
- available memory inventory。

输出每个 memory item：

- current relevance；
- potential helpfulness；
- stale；
- conflicts with newer information；
- intrusive if mentioned。

M1 用于审计 inventory 的机会与风险，不给 PM 作为部署输入。

### 11.2 M0 Memory Omission Audit

用于 `M0+R0` 和 `M0+RS`：

- omission appropriateness；
- missed memory opportunity severity；
- missed useful sources；
- unsupported personal claim。

关键修复：正确不使用记忆可以得分；M0+RS 不得获得 memory-use credit。

### 11.3 M2 Memory Use Audit

用于非 M0 动作：

- source-set appropriateness；
- selected source relevance；
- source utilization；
- unused retrieval；
- stale/conflicting；
- unnecessary exposure；
- unsupported personal claim；
- missed useful sources。

### 11.4 Strategy Use Audit

用于 RS 动作：

- strategy relevance；
- strategy utilization；
- over-structuring；
- premature advice。

当前观察：strategy use audit 倾向偏乐观，几乎多数 RS 都被判 relevance/utilization 高。因此最终论文不能只靠 strategy audit 证明 Strategy RAG 有益，仍应优先看 response pair 中的 `R0 vs RS`。

### 11.5 Strategy Omission Audit

用于 R0 动作：

- strategy omission appropriateness；
- missed strategy opportunity severity；
- premature/overstructured without strategy。

### 11.6 Response Pairwise Judge

输入：

- visible dialogue context；
- response A；
- response B。

不可见：

- action id；
- memory evidence；
- strategy evidence；
- selected memory ids；
- old utility。

输出：

- preference: A / B / tie；
- empathy；
- contextual fit；
- guidance fit；
- non-intrusiveness；
- coherence；
- reason。

训练用最终 preference 经过 dual-order debiasing。若 forward/reverse 对同一 underlying response 不一致，则最终记为 tie。

## 12. PM 输入特征

实现文件：

```text
src/metacom_pm/features.py
```

Feature modes：

- `full`；
- `text_only`；
- `metadata_only`；
- `catalog_only`。

允许特征：

- 当前用户文本；
- 当前 session history；
- 当前 session summary；
- session index；
- action one-hot / selected source indicators；
- memory inventory availability；
- source count；
- min/max age；
- estimated tokens；
- selected source × metadata interactions；
- lightweight source-level catalog fingerprint；
- query-to-catalog similarity；
- action-gated text TF-IDF features。

禁止特征：

- actual memory snippets；
- actual strategy snippets；
- selected memory ids；
- retrieval scores；
- generated response；
- judge labels；
- gold fields；
- future information。

FeatureBuilder 还包含 OOD report。严重 scalar OOD 或严重 catalog OOD 会 fail closed，不允许静默使用模型。

## 13. PM 训练算法

实现文件：

```text
src/metacom_pm/training.py
script: scripts/10_train_pm.py
```

模型结构：

```text
FeatureBuilder
  -> response_ranker: LogisticRegression
  -> misuse_regressor: Ridge
  -> omission_regressor: Ridge
  -> memory_decision_regressor: Ridge
  -> strategy_risk_regressor: Ridge
  -> strategy_decision_regressor: Ridge
```

Response head：

- pairwise ranking；
- 对每个 non-tie response pair 构造 `x(action_a) - x(action_b)`；
- label 为 A/B preference；
- mirror sample `-(diff)`，减少 A/B orientation dependence；
- pair loss 按 card 归一，避免动作多的 card 权重过大；
- LogisticRegression 输出经 sigmoid 映射为 bounded `response_score`。

Action-level heads：

- Ridge regressors；
- 目标来自 M0/M2/strategy audits；
- 输出包括 misuse risk、omission risk、memory decision quality、strategy decision quality、strategy risk。

训练 split：

- 来自 `data/synthetic/folds.jsonl`；
- 支持 user-held-out 和 semantic-held-out folds；
- strict split 会检查 state_id sibling 不跨 train/validation；
- text overlap / user overlap / semantic family overlap 做 diagnostics。

当前尚未完成 PM 训练，因为 full judging 仍在运行。

## 14. Validation Selection

实现文件：

```text
src/metacom_pm/selection.py
script: scripts/11_tune_validation.py
```

Validation-only 冻结内容：

- validation-selected best fixed action；
- budget-matched fixed action；
- PM `epsilon`；
- PM `tau_misuse`；
- PM `tau_omission`；
- PM `tau_strategy`；
- strong rule grid 参数；
- selection margins。

PM 决策规则：

1. 对所有合法 action 预测 response score；
2. 找到接近最好 response 的候选集；
3. 过滤 misuse / omission / strategy risk；
4. 在满足质量与风险约束的候选中优先选择低成本动作；
5. confirmatory 阶段不允许 constraint fallback。

Validation selection 采用：

```text
near-best response
then near-lowest safety risk
then minimum cost
```

默认 selection margins：

```text
response_margin = 0.02
safety_margin = 0.02
```

Strong rule baseline：

- 使用与 PM 同样的 pre-evidence inventory/catalog visibility；
- grid search threshold values `[0.0, 0.04, 0.08, 0.12, 0.18]`；
- `max_sources` in `[1, 2, 3]`；
- 在 validation 上选择，不看 test/external。

## 15. 评价指标

### 15.1 Measurement health

- hard control accuracy；
- boundary diagnostics；
- same-order repeat consistency；
- effective non-tie response rate；
- strategy pair signal；
- schema/completeness；
- raw reversal / position bias diagnostics；
- error/retry rate；
- response tie rate by pair type。

### 15.2 Response quality

Response quality 不作为默认 superiority claim，而作为非劣约束：

```text
lower 95% CI of NetWin(PM vs strongest preregistered baseline) > -0.05
```

内部训练使用 pairwise response ranking，外部评估仍需 LLM final judge 或人工盲评子集。

### 15.3 Memory quality

- M0 omission appropriateness；
- missed memory opportunity；
- source-set appropriateness；
- selected source relevance；
- utilization；
- unused retrieval；
- stale/conflict；
- unnecessary exposure；
- unsupported personal claim。

### 15.4 Strategy quality

- strategy relevance；
- strategy utilization；
- over-structuring；
- premature advice；
- missed strategy opportunity。

### 15.5 Cost / efficiency

- retrieval calls；
- memory tokens；
- strategy tokens；
- total input tokens；
- output tokens；
- latency；
- estimated API/GPU cost。

必须区分：

- offline action sweep cost；
- deployment policy cost。

## 16. Baselines

内部 development 至少包含：

1. `M0+R0`；
2. `M0+RS`；
3. validation-selected best fixed action；
4. budget-matched fixed action；
5. strong rule policy；
6. text-only learned router；
7. metadata-only learned router；
8. catalog-only learned router；
9. raw/full RAG diagnostic baseline。

正式结论不能只依赖弱规则 baseline。若 PM 不能赢 strong rule，应如实报告。

## 17. 当前实验阶段

已完成：

```text
00/01 synthetic preparation and audit
04 pair graph build/audit
05 generator variance diagnostic
06 full synthetic action sweep
07 judge pilot with Gemini Flash-Lite + Protocol V3 + strategy validator fix
08 pilot gate analysis: PILOT_GO_FULL_JUDGING
```

正在运行：

```text
09 full synthetic judging
endpoint: training_judge / gemini-2.5-flash-lite
output dir: outputs/full_judging_gemini_flash_lite_v3
pilot gate: outputs/judge_pilot_gemini_flash_lite_v3_strategyfix/pilot_gate.json
```

运行命令：

```bash
nohup env PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/09_run_full_judging.py \
  --out-dir outputs/full_judging_gemini_flash_lite_v3 \
  --pilot-gate outputs/judge_pilot_gemini_flash_lite_v3_strategyfix/pilot_gate.json \
  > logs/09_full_judging_gemini_flash_lite_v3.log 2>&1 &
```

当前进度快照：

```text
snapshot: 2026-06-24 14:19:01 JST
process PID: 633367
elapsed: 22:07:43

memory_opportunity_judgments.jsonl: 1727
memory_omission_judgments.jsonl: 2878
memory_use_judgments.jsonl: 6320
strategy_use_judgments.jsonl: 4599
strategy_omission_judgments.jsonl: 4586
raw_judge_calls.jsonl: 21772
response_pair_judgments.jsonl: not started at snapshot
```

Expected final counts:

```text
M1 memory opportunity: 1728
M0 memory omission: 3456
M2 memory use: 7680
strategy use: 5568
strategy omission: 5568
response pair: 24720 validated rows
```

当前进度解释：

- M1 基本完成；
- M0/M2/strategy audits 约 80%+；
- response pair 仍未开始；
- Gemini 错误率一度较高，但近期稳定性明显改善；
- 进入 response pair 后需要立即检查 tie rate、A/B distribution、by-pair-type signal。

## 18. 已观察到的中途标签倾向

M1 memory opportunity 分布正常，有梯度：

```text
relevance 0/1/2 roughly: majority 0, substantial 1, smaller 2
helpfulness 0/1/2 similarly distributed
stale/conflict/intrusive all present
```

M2 memory use 有区分度：

```text
overall_source_set_appropriateness 0/1/2 均有较多样本
```

Strategy use audit 偏乐观：

```text
多数 RS 被 judge 评为 strategy_relevance=2 / strategy_utilization=2
over_structuring 和 premature_advice 很少出现
```

解释：

- Strategy audit 不能单独承担“Strategy RAG 有益”的主证据；
- Strategy 主效果应优先通过 response pair 中同 memory 条件下 `R0 vs RS` 估计；
- 若 full response pair 仍有信号，可以用于 Q_response；
- 若 response pair 偏弱，则论文主张应更收敛到 memory/resource reliability 和 cost trade-off。

## 19. 后续计划

### Step 1：完成 full judging

等待 `outputs/full_judging_gemini_flash_lite_v3` 全部 judgment 文件完成，并生成 full judging attestation。

注意：当前训练脚本默认读取 `outputs/full_judging/`，而本次 full judging 输出在：

```text
outputs/full_judging_gemini_flash_lite_v3/
```

后续训练前需要二选一：

1. 将该目录稳定复制/链接为 `outputs/full_judging/`；
2. 或修改 `scripts/10_train_pm.py` / `scripts/11_tune_validation.py` 支持自定义 full judging dir。

### Step 2：response pair 中途检查

一旦出现：

```text
outputs/full_judging_gemini_flash_lite_v3/response_pair_judgments.jsonl
```

立即检查：

- overall tie rate；
- effective non-tie rate；
- A/B distribution；
- by pair type: strategy / memory / combination / chord；
- dual-order disagreement resolved-to-tie；
- whether strategy pairs still have response signal。

### Step 3：训练 PM

使用 `scripts/10_train_pm.py`：

- primary fold: user fold 0；
- feature mode: full；
- ablations: text_only, metadata_only, catalog_only；
- seeds: at least several seeds if time allows；
- strict split recommended。

### Step 4：Validation selection

使用 `scripts/11_tune_validation.py`：

- select best fixed；
- select budget-matched fixed；
- tune PM epsilon/tau thresholds；
- tune strong rule grid；
- freeze selection before test/external evaluation。

### Step 5：Development evaluation

在 synthetic development 上报告：

- PM vs best fixed；
- PM vs budget fixed；
- PM vs strong rule；
- PM action distribution；
- cost reduction；
- misuse/omission/strategy risk；
- response quality non-inferiority；
- feature ablations；
- availability counterfactual。

### Step 6：Confirmatory hygiene

正式外部实验前：

1. 接入 ESConv；
2. 只用 ESConv train 重建 Strategy Bank；
3. 做 overlap audit；
4. 构建 ESConv test runtime；
5. 锁定 study freeze；
6. 不再修改 protocol / gates / thresholds。

### Step 7：External evaluation

ESConv：

- Strategy routing；
- response quality；
- no-memory abstention；
- false-memory control。

EvoEmo / ES-MemEval-style：

- full 18 users；
- longitudinal memory resource allocation；
- time truncation；
- no future sessions；
- official-aligned / selective-memory tracks separated。

Human evaluation：

- 抽取 10%-20% response pairs 或关键 PM-vs-baseline pairs；
- 3 名盲评者；
- 不显示 action/evidence；
- 报告 majority vote 和 inter-annotator agreement。

## 20. 成功与失败解释

### 成功模式 A：质量与记忆优势

相对 strongest preregistered baseline：

- response preference 显著更好；
- memory decision quality 更好；
- misuse 不更差；
- cost 不超过预注册上限。

### 成功模式 B：质量非劣、资源更优

相对 strongest preregistered baseline：

- response quality 满足非劣；
- memory quality 满足非劣或更好；
- retrieval calls / input tokens 明显下降；
- misuse 不更差。

这是当前最现实、最稳的成功模式。

### 若 PM 不优于 strong rule

应报告：

> 在当前 deployment-observable features 和 controlled synthetic setting 下，强规则已经足以完成大部分资源调度；学习型 PM 的边际收益有限。

这不是工程失败，而是一个有效科学结论。它说明本研究没有只打弱 baseline，也为后续更真实 longitudinal setting、更多状态信息或 RL/future-oriented reward 提供边界。

### 若 response pair 信号不足

不能声称 PM 改善回复质量。可以收敛为：

> PM 改善资源选择、记忆适切性或成本效率，同时保持回复质量非劣或未观察到明显下降。

## 21. 当前主要风险

1. Full judging 耗时长，Gemini 偶发 503，需要断点续跑；
2. Strategy audit 偏乐观，不能作为 Strategy RAG 主证据；
3. Response pair 尚未开始，Q_response 是否有足够信号仍待验证；
4. Synthetic 数据用于 development，不可作为最终外部 claim；
5. 如果直接用 `outputs/full_judging_gemini_flash_lite_v3`，训练脚本路径需要处理；
6. Final judge 与 training judge 必须保持 family independent；
7. 外部 ESConv/EvoEmo 前必须重新构建正式 Strategy Bank 并冻结 protocol。

## 22. 当前可报告结论

截至本报告快照，可以安全说：

1. 工程骨架已跑通 pre-evidence action sweep；
2. 当前 action space、pair graph、data audit 和 measurement protocol 已形成闭环；
3. Gemini Flash-Lite 在 Protocol V3 下通过 judge pilot gate；
4. Full synthetic judging 正在运行，audit 标签目前未出现整体崩坏；
5. PM 尚未训练完成；
6. 任何关于 PM 是否优于 rule / fixed / raw RAG 的结论尚未产生；
7. 当前研究仍处于 development judging 阶段，不是 final test 或 external evaluation。

## 23. 最短下一步清单

1. 等 full judging 完成；
2. response pair 一开始就做 tie-rate 和 by-pair-type signal 检查；
3. full judging 完成后验证 attestation；
4. 处理 `outputs/full_judging_gemini_flash_lite_v3` 与训练脚本默认路径；
5. 跑 `scripts/10_train_pm.py`；
6. 跑 `scripts/11_tune_validation.py`；
7. 输出 PM vs fixed/rule development report；
8. 再决定是否进入 ESConv/EvoEmo 外部阶段。

