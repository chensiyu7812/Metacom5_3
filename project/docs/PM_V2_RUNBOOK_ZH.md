# MetaCom PM-v2.1 可执行运行手册

更新时间：2026-07-14

> 适用分支：`codex/pm-v2-hardening`。本流程新建 PM-v2.1 产物，不覆盖 PM-v1 的冻结结果。

## 0. 当前状态与诚实边界

截至本文更新时间，generation compatibility 历史中已有六次失败 physical attempts 和一次 v4 structural-success attempt；它们都保留在不可覆盖账本中。当前 v6 目录的付费 API 调用数是 **0**。PM 是否真正学会因情境选择不同资源、何时不用资源，以及是否优于同预算固定动作，仍必须由后续数据生成、双 family 标签、人工审计、internal holdout 和外部评测证明。

能预先保证的是 fail-closed：缺失矩阵、坏标签、近常量 policy、M0/R0 未学会、风险/不确定性失准、OOD 回退过多、成本不匹配或评审协议失败时停止。不能预先保证的是 PM-v2.1 一定获得正面经验结果。

## 1. 环境、分支和统一规则

```bash
cd /home/tokkio/metacom_workspace/metacom_v2
git switch codex/pm-v2-hardening
cd project

PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  -m pytest -q

PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  -m compileall -q src scripts
```

所有付费脚本都遵守同一协议：

1. 必须显式运行 `--dry-run`；
2. 价格必须进入冻结配置和成本 SHA；synthetic generator 的 GPT-4o-mini 价格已在 `pm_v2.yaml` 冻结为 input 0.15 / output 0.60 USD per million tokens，相关 CLI 价格参数仅作 exact-match assertion；
3. 设置调用数、总成本和单次输入 token 上限；
4. 检查 dry-run 的精确 call plan、预算 gate 和成本估计；
5. `--run` 必须使用相同目录、相同参数，并接受 dry-run 产生的精确 `cost_estimate_sha256`；
6. 配置、prompt、输入、模型 endpoint、价格或预算任一变化，旧 SHA 自动失效，必须重新 dry-run；
7. 不在 external 结果上反向调整阈值、composite、baseline 或选择规则。

任何 PM-v2 paid stage 一旦出现非空 physical-attempt ledger，就禁止 `--overwrite`（包括 `--dry-run --overwrite`）。`STARTED` 即视为已花费；失败、中断或未知状态只能原地按剩余 call key 恢复，不能删除 ledger 后重发。

下文其余价格环境变量只表示经人工核验后的数值，不是本文给出的价格：

```bash
export PMV2_GENERATOR_INPUT_USD_PER_MTOK=...
export PMV2_GENERATOR_OUTPUT_USD_PER_MTOK=...
export PMV2_DATA_MAX_USD=...
export PMV2_PILOT_SWEEP_MAX_USD=...
export PMV2_PILOT_JUDGE_MAX_USD=...
export PMV2_FULL_SWEEP_MAX_USD=...
export PMV2_FULL_JUDGE_MAX_USD=...
export PMV2_EXTERNAL_GENERATION_MAX_USD=...
export PMV2_FORCED_SWAP_MAX_USD=...
export PMV2_FULL_EXTERNAL_JUDGE_MAX_USD=...
```

API keys 只在真正执行相应 `--run` 前注入环境；dry-run 和下述 no-API 检查不需要 key。

## 2. PM-v2.1 的不可变口径

- 16 个候选是 8 个 memory subsets × `R0/RS` 的 resource actions，不是 16 个独立回复 policy。
- judge schema 不存在 `overall`。六个 response dimensions 独立输出；训练 utility 使用冻结的 `pmv2-quality-v2` composite。
- `pmv2-quality-v2` 权重为 emotional support 0.30、personalization 0.20、memory appropriateness 0.15、factual grounding 0.15、temporal consistency 0.10、non-intrusiveness 0.10。
- 所有 state-action 中位数都保留在完整矩阵中；不以“整行可靠/不可靠”删除样本。每个维度的 MAD 同时用于连续降权和分 split、分 action-dimension 覆盖 gate。
- 模型直接预测六个质量 head 和七个风险 head；成本直接来自资源成本/observed tokens，不由 LLM 打分。
- calibration 以 user block（max over states×actions）拟合 head-wise split-conformal residual radii，并使用 YAML 中唯一预注册的 uncertainty `z`；internal test 只评一次，拟合集自身的 Wilson 下界不作成功门。
- paired delta 和置信区间按 `user_id` cluster bootstrap，不能把同一用户的状态当作独立样本。
- reportability、OOD、cost-match、label/human 阈值和 human sample seed 都只来自 `configs/pm_v2.yaml`；命令行不能临时放宽。
- 正式系统是 pre-retrieval PM + post-retrieval Evidence Filter；完整契约见 [`PM_V2_EVIDENCE_FILTER_PROTOCOL_ZH.md`](PM_V2_EVIDENCE_FILTER_PROTOCOL_ZH.md)。requested/effective action 必须分开报告。

## 3. No-API：从真实 ESConv train split 提取 seed

正式 seed 必须使用仓库中的真实 ESConv 文件和严格、按 index 对齐的 split/overlap manifest：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/18_prepare_pm_v2_seed_dialogues.py \
  --inputs data/external/ESConv.json \
  --split-manifest data/strategy/esconv_split_manifest.jsonl \
  --out data/pm_v2/train_seed_dialogues.jsonl \
  --minimum-seeds 100
```

该 manifest 是 authoritative：只接收 train，自动排除标为 EvoEmo overlap 的对话，并拒绝 source/manifest 行数、index、ID 或 schema 不一致。输出包括：

- `data/pm_v2/train_seed_dialogues.jsonl`
- `data/pm_v2/train_seed_dialogues.jsonl.audit.json`

先人工检查 audit 中的源 SHA、manifest SHA、eligible/selected 数量、validation/test rejection 与 overlap exclusion，再进入任何 API 阶段。

## 4. Development data：先做单调用兼容 pilot，再生成完整 52-user 数据

冻结规模来自 YAML，不能用 CLI 改成一个较容易通过的版本：

| Split | Users | States/user | States |
|---|---:|---:|---:|
| train | 24 | 9 | 216 |
| calibration | 12 | 9 | 108 |
| internal_test | 16 | 9 | 144 |
| total | 52 | 9 | 468 |

每个 user bundle 是一次调用，必须恰好覆盖九个 regime；因此预期与硬上界均为 52 次 bundle calls。v6 orthogonal source-grounded schema 已移除结构性重试理由，YAML 只允许每个 bundle 1 次冻结请求；失败必须先审查协议，不能自动换 seed 继续付费。calibration/internal 扩为 12/16 users，是为了避免把相关 state-action 行当独立 conformal 样本。正式 `--run` 禁止 `--max-users`。

### 4.1 v4 结论：transport PASS，但科学语义 FAIL

2026-07-15 的 v4 单调用确实成功返回 strict JSON，账本也只有一个 `STARTED`/`SUCCEEDED` pair；该产物必须永久保留在 `outputs/pm_v2_generation_compatibility_pilot_role_slot_v4/`。但是，人工逐例检查发现它不能授权 full generation：

- 9/9 case 的 `recent_dialogue` 先出现与 `current_user_text` 相同的 user turn，之后还有 assistant 和更晚的 user turn，形成未来信息泄漏；
- 33/33 memories 的 age 都等于 1，PM 无法从该数据学习 temporal cost/risk；
- MP/MS/ME 语义边界模糊，MP 中出现建议性话语，多个 distractor 实际仍与当前问题相关；
- `multi_source_needed` 没有可靠证明三源互补，strategy helpful/harmful 与候选 semantic family 也存在错配；
- 成功账本只保存 compiled bundle，无法从产物重建完整 provider draft 与原始 response。

因此 v4 只能记为“schema transport 兼容”，其 structural attestation 不是 semantic PASS，更不是 52-call 许可。

### 4.2 v6 实测失败与 v7 deterministic-evidence replay（0 新 API）

v6 已实际执行并失败。OpenAI 接受 strict schema 并返回完整对象，usage 为 input 4,084、output 3,434、total 7,518 tokens；账本恰好一组 `STARTED -> FAILED`。失败来自 37 个本地 lexical family/distractor 检查，不是 HTTP、schema、网络或截断。证据保存在 `outputs/pm_v2_generation_compatibility_pilot_orthogonal_v6/`；旧成本 SHA `f2cc9fbf...` 已消费，禁止再次运行该命令。

v6 说明 provider 不应同时负责自然语言 surface 和实验 oracle。v7 改为：provider 只生成对话 surface；resource regime、needed source、coverage rationale、item utility、risk flags、memory age、source form 和 evidence text 由冻结 deterministic blueprint 编译。为保持已经实测通过的 strict provider schema，provider 返回的 rationale/memory slots 仍可存在，但 compiler 明确丢弃，不用于标签或 evidence。越界 surface 逐 case 使用有 provenance 的 deterministic fallback，不再让一个 semantic drift 浪费整次请求。

v7 同时增加反 V1 捷径约束：每个 case 的 MP/MS/ME 恰好各两条，无论 source 是否 needed；needed source 内有 helpful 与同源 distractor；family position 在用户间轮换并覆盖全部九类 regime，topic 不能映射到固定 policy。case ID 隐去 regime，session position 在每个 split 的用户间循环平衡，memory ages 只依赖中性 position/source/slot 而不依赖 utility。oracle/evaluator context 不进入 PM deployable state。

当前 provider schema 与 v6 已付费调用实际接受的 schema 完全相同，因此不再发 compatibility API。用下列命令对 v6 immutable ledger/raw response 做正式零 API replay：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/20d_replay_pm_v2_paid_generation_pilot.py
```

2026-07-15 replay 已完成：输出为 `outputs/pm_v2_generation_compatibility_pilot_deterministic_evidence_v7/`，最终 attestation `PASS`，SHA256 `683effc2193bc1c99a72a5f2ec8f4c2f74579f4a3fa53ef6d8485a4e8e540948`，`new_physical_api_attempts=0`。九例中 7 个保留 provider surface；`multi_source_needed` 因混合 academic/workplace topic、`strategy_harmful` 因 user turn 未明确表达无建议边界而使用透明 deterministic fallback。全部 structural checks 和 214 项 no-API tests 通过。

**不要再次运行 `scripts/20a... --run`。** 当前下一步是双人语义审查。v1--v6 的所有 physical attempts、目录和账本均须永久保留；v7 structural PASS 也不等于 PM 已学会或外部效果已经成立。

### 4.3 Pilot 双人 semantic review（0 API，full generation 的硬前置）

pilot 成功后先生成审查包：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/20b_prepare_pm_v2_generation_pilot_semantic_review.py
```

阅读 `generation_pilot_semantic_review_readable_ZH.md`，由两名独立审查者分别填写已经生成的精简 `reviewer_a.csv` 与 `reviewer_b.csv`。每份只有九行；填写 semantic family、regime、needed memory sources、item utility、MP/MS/ME source type、当前轮时间顺序、memory age design 和 strategy need 八列，所有值只能是 0/1，notes 可选。两人完成前不得讨论答案。然后分析：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/20c_analyze_pm_v2_generation_pilot_semantic_review.py \
  --completed \
    outputs/pm_v2_generation_pilot_semantic_review_v7/reviewer_a.csv \
    outputs/pm_v2_generation_pilot_semantic_review_v7/reviewer_b.csv
```

该门为 all-affirmative：任一审查者、任一 case、任一维度出现 0，或 annotator 不独立、保护列被改动、lineage/hash 不一致，report 都是 `FAIL`。full generator 与 study freeze 都要求同一个 review attestation 为 `PASS`。

### 4.4 Full generation dry-run（0 API）

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/20_generate_pm_v2_development_data.py \
  --dry-run \
  --seed-dialogues data/pm_v2/train_seed_dialogues.jsonl \
  --strategy-bank data/strategy/strategy_cards.jsonl \
  --out-dir data/pm_v2 \
  --max-api-calls 52 \
  --max-estimated-usd 1 \
  --max-input-tokens-per-call 12000
```

检查 `generation_cost_estimate.json` 和 `generation_call_plan.jsonl`：`planned_users=52`、`expected_api_calls=52`、`maximum_api_calls=52`，且预算 gate 为 `PASS`。

2026-07-15 当前 v7 full no-API dry-run 已连续两次文件 SHA256 一致：最大 52 calls、最大单次 input 上界 9,128、总成本保守上界 0.31259895 USD、budget gate `PASS`，成本 SHA 为 `69ede6499a1ccf3978b705c4706b198cf4e12f984e91980702a9b5e223434e31`。`generation_cost_estimate.json` 与 `generation_call_plan.jsonl` 的两次文件 SHA256 分别稳定为 `0e64e9aa...` 与 `838331dd...`。它只是成本与请求计划，不授权现在执行 52 次调用。

### 4.5 Pilot structural PASS + 双人 semantic PASS 后才允许 full run

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/20_generate_pm_v2_development_data.py \
  --run \
  --seed-dialogues data/pm_v2/train_seed_dialogues.jsonl \
  --strategy-bank data/strategy/strategy_cards.jsonl \
  --out-dir data/pm_v2 \
  --generation-pilot-attestation outputs/pm_v2_generation_compatibility_pilot_deterministic_evidence_v7/artifact_attestation.json \
  --generation-pilot-semantic-attestation outputs/pm_v2_generation_pilot_semantic_review_v7/artifact_attestation.json \
  --max-api-calls 52 \
  --max-estimated-usd 1 \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 69ede6499a1ccf3978b705c4706b198cf4e12f984e91980702a9b5e223434e31
```

输出必须包含 52 bundles、468 states，并为每个 state 暴露完整 16 actions。`pm_v2_data_report.json` 中的跨 split word/char fixed-hash near-duplicate gate 必须为 `PASS`。`regime`、needed sources、覆盖 rationale 和逐 item `helpful/irrelevant/harmful` 标签等 oracle/evaluator 信息保存在独立 `evaluator_contexts.jsonl`，不会进入 PM feature state。每个 needed source 必须同时包含 helpful item 和同源 distractor，防止过滤器只学习 source ID。

full `--run` 会在读取 API key 和登记首个 paid attempt **之前**重算 compatibility contract，并同时验证 structural pilot 与双人 semantic-review attestations；缺失、FAIL、篡改或旧 lineage 都会 fail closed。full dry-run 本身不需要 attestation，便于在零 API 阶段先核对 52/52 call 计划。

### 4.6 全量数据人工 semantic-sanity gate（0 API，付费 sweep 前必做）

JSON schema、九类 regime 数量和 `needed_memory_sources` 的结构约束只能证明“格式合法”，不能证明生成内容在语义上真的符合其标签。任何 compatibility/full action sweep 之前，先生成冻结的盲化人工审计包：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/18a_prepare_pm_v2_semantic_sanity_audit.py \
  --pm-v2-config configs/pm_v2.yaml \
  --states data/pm_v2/pm_v2_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --evaluator-contexts data/pm_v2/evaluator_contexts.jsonl \
  --out-dir outputs/pm_v2_semantic_sanity
```

YAML 同时冻结 `states_per_regime_per_split=1` 与 `minimum_states_per_family_per_split=1`。采样不是固定27条，而是按 split 做 deterministic greedy set-cover：每个 split×regime 至少一条，并覆盖该 split 的全部 semantic families。对冻结的 14/5/5 family 设计，train 至少14条、calibration/internal 各至少9条，正式最小 packet 为32 items；若实际 family/regime 分布需要更多状态，算法会确定性扩展，不能从 CLI 挑容易案例。输出：

- `semantic_sanity_packet.csv`：隐藏 state/user/split/generator/rationale，仅显示判断标签所需的情境、authorized context、按 MP/MS/ME 标记的实际 synthetic memory 内容、stale/conflict/item-utility flags、source 摘要、候选 semantic family/regime/needed sources；
- `semantic_sanity_manual.md`：冻结 0/1 判定规则和九类 regime 定义；
- `semantic_sanity_plan.json`：保存真实 state/split/regime/family 对照、逐 split family universe、set-cover 计数、输入 hashes、逐行 hash 与 plan self-hash。

至少两名 annotator 独立复制并填写 packet；只能填写 `semantic_family_match`、`regime_match`、`needed_memory_sources_match`、`memory_item_utility_match`、`annotator_id` 和 `notes`，前四列严格使用 `0/1`。随后分析：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/18b_analyze_pm_v2_semantic_sanity_audit.py \
  --completed <ANNOTATOR_A.csv> <ANNOTATOR_B.csv> \
  --pm-v2-config configs/pm_v2.yaml \
  --states data/pm_v2/pm_v2_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --evaluator-contexts data/pm_v2/evaluator_contexts.jsonl
```

分析要求每个 item 至少两份独立评分，并按 YAML 检查逐字段 affirmative rate、逐字段 pairwise agreement、逐 regime、逐 split 与逐 semantic-family affirmative rate。分析会从当前 state/context 重新执行同一 set-cover 并要求 plan identity 完全一致。只有 `semantic_sanity_report.json` 和 `artifact_attestation.json` 均为同一 config/states/memory-backend/evaluator-context lineage 的 `PASS`，Evidence Filter 才允许训练，script 31 才会生成 pilot plan；script 06 在 PM-v2 compatibility/full dry-run 和 run 前也会再次验证，并要求每条 runtime row 与 audited PM-v2 state 的确定性转换完全一致。缺失、FAIL、漏 family、重复 annotator、改动 packet 的保护列、换 runtime/data 或换阈值都会在创建任何 API call plan 前失败。

### 4.5 训练并冻结 Memory Evidence Filter（0 API）

人工 semantic-sanity PASS 后，训练 item-level memory filter：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/36_train_pm_v2_evidence_filter.py \
  --pm-v2-config configs/pm_v2.yaml \
  --states data/pm_v2/pm_v2_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --evaluator-contexts data/pm_v2/evaluator_contexts.jsonl \
  --semantic-sanity-report outputs/pm_v2_semantic_sanity/semantic_sanity_report.json \
  --semantic-sanity-attestation outputs/pm_v2_semantic_sanity/artifact_attestation.json
```

训练只使用 train users，threshold 只使用 calibration users，最终 recall/precision/specificity gate 只检查 internal-test users。`training_report.json`、`evidence_filter.joblib` 和 attestation 任一缺失、hash 漂移或 gate FAIL，script 06、study freeze 和 external generation 都会在 API 前停止。strategy card 目前使用透明的 lexical contextual fail-safe，不宣称 learned card-level causal usefulness。

## 5. Development compatibility pilot：再验证两个 judge families

第 4.1 节已经独立验证 synthetic generator。这里的 action/judge pilot 继续验证两个 development judge families；它同样只作 API/schema/protocol 兼容性诊断，不参与调参，不代替完整 action matrix。

### 5.1 No-API 生成平衡 pilot plan

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/31_plan_pm_v2_development_pilot.py \
  --pm-v2-config configs/pm_v2.yaml \
  --states data/pm_v2/pm_v2_states.jsonl \
  --runtime data/pm_v2/runtime_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --evaluator-contexts data/pm_v2/evaluator_contexts.jsonl \
  --strategy-bank data/strategy/strategy_cards.jsonl \
  --semantic-sanity-report outputs/pm_v2_semantic_sanity/semantic_sanity_report.json \
  --semantic-sanity-attestation outputs/pm_v2_semantic_sanity/artifact_attestation.json \
  --out outputs/pm_v2_development_pilot/pilot_plan.json
```

YAML 冻结为每个 evaluator-only regime 2 个 **train states**、10 个覆盖 M0/R0/RS/低中高资源的 actions：共 18 states、180 state-action outcomes。整个 compatibility/feasibility pilot 都限定 train split，不能用 calibration 或 internal-test label 决定是否继续 full run。regime 仅用于平衡抽样，不进入 generator 或 PM feature。pilot plan 同时绑定前一步 semantic-sanity report/attestation；不能用另一个 state 文件的 PASS 结果。

script 31 还会在创建任何付费 action plan 前，用**最终部署时同一个**
`PMV2FeatureBuilder` 和固定 `M0+R0` action 做 train-only、按 user 分组的
交叉验证。门禁分别检查 regime、needed-source、memory need，以及
strategy-helpful vs strategy-harmful、memory-helpful vs memory-harmful 的可观测性。
该诊断只回答 evaluator 定义的路由信号是否存在于合法的 pre-retrieval feature
space；它不是 learned-router 成绩。script 34、script 06 和 full development gate
都会从 exact states/evaluator contexts/YAML 重新计算并要求逐字段等于 pilot plan，
所以重算 plan self-hash 也不能伪造一个 PASS。

### 5.2 Development judge structured-schema smoke：4 calls

在花 180 次 generator calls 之前，先用 pilot plan 中确定性选出的一个 train state 和 YAML 固定的匿名 candidate 验证两个 development judge endpoints。exact matrix 是 `2 families × {response, risk} = 4` 个 physical calls；该步骤只验证 structured-output/schema、provider usage 与 token bound，不把四次分数当作质量证据。

先 dry-run（不读 API key）：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/34_run_pm_v2_development_judge_schema_smoke.py \
  --dry-run \
  --pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --max-api-calls 4 \
  --max-estimated-usd 2 \
  --max-input-tokens-per-call 12000
```

人工接受同一个 cost SHA 后运行：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/34_run_pm_v2_development_judge_schema_smoke.py \
  --run \
  --pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --max-api-calls 4 \
  --max-estimated-usd 2 \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_SCHEMA_SMOKE_DRY_RUN>
```

脚本会在第一个 ledger `STARTED` 前先解析两个 endpoint 的 API keys 并创建两个 clients；任一 key/client 缺失时四次调用均不会开始。每个 logical call 只有一次 physical attempt，successful result 连同 validated schema object 和正数 provider usage 持久化，可在成功后进程崩溃时恢复而不重发。若任一 spent call 失败，exact PASS matrix 已不可达，重跑会立即输出 fail-closed 结果，不会越过失败项继续补发后面的 calls。只有同目录 `summary.json` 与 `artifact_attestation.json` 的 exact four-call `PASS` 才允许 5.3 节生成 action pilot。

### 5.3 Pilot action sweep：180 calls

action-sweep generator 的非零预算核算代理价格已冻结在 `development_sweep.pricing_usd_per_mtok`（input 0.15 / output 0.60）；NVIDIA research endpoint 的 prototype access 即使不出具按-token账单，也不能通过 CLI 零价格让 cost gate 失真。CLI price flags 仅可作为 exact assertion，以下命令直接从 YAML 派生。

先 dry-run：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/06_run_action_sweep.py \
  --dry-run \
  --pm-v2-config configs/pm_v2.yaml \
  --runtime data/pm_v2/runtime_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --strategy-bank data/strategy/strategy_cards.jsonl \
  --pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --out-dir outputs/pm_v2_development_pilot \
  --max-api-calls 180 \
  --max-estimated-usd "$PMV2_PILOT_SWEEP_MAX_USD" \
  --max-input-tokens-per-call 12000
```

接受相同 plan 的 SHA 后才 run：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/06_run_action_sweep.py \
  --run \
  --pm-v2-config configs/pm_v2.yaml \
  --runtime data/pm_v2/runtime_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --strategy-bank data/strategy/strategy_cards.jsonl \
  --pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --out-dir outputs/pm_v2_development_pilot \
  --max-api-calls 180 \
  --max-estimated-usd "$PMV2_PILOT_SWEEP_MAX_USD" \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_PILOT_SWEEP_DRY_RUN>
```

### 5.4 Pilot multi-family judging：720 calls

development endpoints 与逐-family价格只从 `configs/pm_v2.yaml` 读取，必须是两个声明为不同 family 的 endpoint；它们与 external judges 按 family 隔离。每个 outcome 对每个 family 分别做 response 与 risk 调用，所以 180 × 2 × 2 = 720 calls。成本估算包含实际发送的 structured-output JSON schema。

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/21_judge_pm_v2_action_sweep.py \
  --dry-run \
  --compatibility-pilot \
  --pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --outcomes outputs/pm_v2_development_pilot/action_outcomes.jsonl \
  --sweep-manifest outputs/pm_v2_development_pilot/run_manifest.json \
  --out-dir outputs/pm_v2_development_pilot_judging \
  --max-api-calls 720 \
  --max-estimated-usd "$PMV2_PILOT_JUDGE_MAX_USD" \
  --max-input-tokens-per-call 12000
```

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/21_judge_pm_v2_action_sweep.py \
  --run \
  --compatibility-pilot \
  --pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --outcomes outputs/pm_v2_development_pilot/action_outcomes.jsonl \
  --sweep-manifest outputs/pm_v2_development_pilot/run_manifest.json \
  --out-dir outputs/pm_v2_development_pilot_judging \
  --max-api-calls 720 \
  --max-estimated-usd "$PMV2_PILOT_JUDGE_MAX_USD" \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_PILOT_JUDGE_DRY_RUN>
```

只有 `summary.json` 的 compatibility gate 为 `PASS`，且 `artifact_attestation.json` 完整，才允许完整 sweep/judging。这里的 PASS 不只检查 schema/MAD：还会在这 18 个纯 train states 上，用冻结的 quality−risk−cost 标尺检查 oracle action 总体与逐 regime 多样性、最大单动作份额、M0/R0/RS oracle 覆盖、state 内 quality range/variance，以及 strategy-helpful/harmful 和 memory-helpful/harmful 的方向分离。任一阈值不通过即 `NONREPORTABLE`，不得投入后续约 3.7 万次 full development calls。pilot 失败时停止并修协议；不能跳过 attestation，也不能把 calibration/internal states 换进 pilot 来决定是否继续。

### 5.5 No-API：18 项盲化人工 judge compatibility spot-check

双-family schema/MAD/label-feasibility gate 通过后，完整 7,488-response sweep 前还必须用真人标签锚定两个 development judge。YAML 冻结为每个 regime 从 pilot 的两个 train states 中确定性选 1 个，并配 2 个有诊断意义的 actions，共 `9 × 1 × 2 = 18` 项。packet 不显示 action/condition/model/family/cost/LLM score，只显示评分所需上下文、匿名 selected context 与回复；人工只填写六个 response 维度的 `1..5` 整数、七个 risk 维度的 `0..3` 整数、annotator ID 和 notes，禁止 overall/support/composite 字段。

先生成 packet（0 API）：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/32_prepare_pm_v2_pilot_human_spot_check.py \
  --pm-v2-config configs/pm_v2.yaml \
  --states data/pm_v2/pm_v2_states.jsonl \
  --evaluator-contexts data/pm_v2/evaluator_contexts.jsonl \
  --pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --outcomes outputs/pm_v2_development_pilot/action_outcomes.jsonl \
  --labels outputs/pm_v2_development_pilot_judging/action_labels.jsonl \
  --raw-results outputs/pm_v2_development_pilot_judging/judge_results.jsonl \
  --judge-compatibility-summary outputs/pm_v2_development_pilot_judging/summary.json \
  --judge-compatibility-attestation outputs/pm_v2_development_pilot_judging/artifact_attestation.json
```

至少两位 annotator 独立复制并填写完整 packet 后分析（0 API）：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/33_analyze_pm_v2_pilot_human_spot_check.py \
  --completed <ANNOTATOR_A.csv> <ANNOTATOR_B.csv>
```

分析会分别对每个 raw judge family（不是只对双-family median）逐维计算 LLM-vs-human MAE 与 within-one rate，并逐维检查 human-human within-one rate；另行报告 cross-family median 仅作完整性对照。任一 family、任一 response/risk 维度或人工一致性未过 YAML 阈值，gate 即为 `FAIL`。只有 `pilot_human_spot_check_report.json` 和同目录 `artifact_attestation.json` 对当前 config/states/evaluator-contexts/pilot-plan/outcomes/labels/raw-results/judge-attestation/人工 CSV 的 exact hashes 均为 `PASS`，才允许创建 full sweep 的 cost plan。

## 6. 完整 16-action sweep 与完整双-family judging

### 6.1 Full sweep：468 × 16 = 7,488 calls

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/06_run_action_sweep.py \
  --dry-run \
  --pm-v2-config configs/pm_v2.yaml \
  --runtime data/pm_v2/runtime_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --strategy-bank data/strategy/strategy_cards.jsonl \
  --completed-pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --pilot-sweep-summary outputs/pm_v2_development_pilot/summary.json \
  --pilot-sweep-attestation outputs/pm_v2_development_pilot/artifact_attestation.json \
  --judge-compatibility-summary outputs/pm_v2_development_pilot_judging/summary.json \
  --judge-compatibility-attestation outputs/pm_v2_development_pilot_judging/artifact_attestation.json \
  --pilot-human-spot-check-report outputs/pm_v2_development_pilot_human_spot_check/pilot_human_spot_check_report.json \
  --pilot-human-spot-check-attestation outputs/pm_v2_development_pilot_human_spot_check/artifact_attestation.json \
  --out-dir outputs/pm_v2_sweep \
  --max-api-calls 7488 \
  --max-estimated-usd "$PMV2_FULL_SWEEP_MAX_USD" \
  --max-input-tokens-per-call 12000
```

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/06_run_action_sweep.py \
  --run \
  --pm-v2-config configs/pm_v2.yaml \
  --runtime data/pm_v2/runtime_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --strategy-bank data/strategy/strategy_cards.jsonl \
  --completed-pilot-plan outputs/pm_v2_development_pilot/pilot_plan.json \
  --pilot-sweep-summary outputs/pm_v2_development_pilot/summary.json \
  --pilot-sweep-attestation outputs/pm_v2_development_pilot/artifact_attestation.json \
  --judge-compatibility-summary outputs/pm_v2_development_pilot_judging/summary.json \
  --judge-compatibility-attestation outputs/pm_v2_development_pilot_judging/artifact_attestation.json \
  --pilot-human-spot-check-report outputs/pm_v2_development_pilot_human_spot_check/pilot_human_spot_check_report.json \
  --pilot-human-spot-check-attestation outputs/pm_v2_development_pilot_human_spot_check/artifact_attestation.json \
  --out-dir outputs/pm_v2_sweep \
  --max-api-calls 7488 \
  --max-estimated-usd "$PMV2_FULL_SWEEP_MAX_USD" \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_FULL_SWEEP_DRY_RUN>
```

full sweep 的 dry-run 和 run 都会先重算同一条 pilot lineage：pilot plan 必须是当前 config/runtime/backend/strategy/semantic-sanity 上的 18 个纯 train states；pilot action sweep attestation 必须为 180/180 `COMPLETE`；双-family judge compatibility 与 label-value feasibility 必须为 720-call `PASS`；18-item human spot-check 的 report/attestation 也必须 exact `PASS`。这些 summary/manifest/outcome/label-signal/human-attestation hashes 会进入 full cost SHA、run manifest 和最终 attestation。缺失、篡改、旧 endpoint、不同 semantic lineage 或 holdout 污染都会在 7,488-call plan 创建前 fail closed。

正式 sweep 不使用 `--max-cards`、`--actions` 或 ad-hoc 子集。结果必须是无重复、无缺失的 7,488-row state-action matrix。

### 6.2 Full judging：7,488 × 2 families × 2 schemas = 29,952 calls

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/21_judge_pm_v2_action_sweep.py \
  --dry-run \
  --outcomes outputs/pm_v2_sweep/action_outcomes.jsonl \
  --sweep-manifest outputs/pm_v2_sweep/run_manifest.json \
  --compatibility-summary outputs/pm_v2_development_pilot_judging/summary.json \
  --compatibility-attestation outputs/pm_v2_development_pilot_judging/artifact_attestation.json \
  --out-dir outputs/pm_v2_judging \
  --max-api-calls 29952 \
  --max-estimated-usd "$PMV2_FULL_JUDGE_MAX_USD" \
  --max-input-tokens-per-call 12000
```

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/21_judge_pm_v2_action_sweep.py \
  --run \
  --outcomes outputs/pm_v2_sweep/action_outcomes.jsonl \
  --sweep-manifest outputs/pm_v2_sweep/run_manifest.json \
  --compatibility-summary outputs/pm_v2_development_pilot_judging/summary.json \
  --compatibility-attestation outputs/pm_v2_development_pilot_judging/artifact_attestation.json \
  --out-dir outputs/pm_v2_judging \
  --max-api-calls 29952 \
  --max-estimated-usd "$PMV2_FULL_JUDGE_MAX_USD" \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_FULL_JUDGE_DRY_RUN>
```

完整 judging 不允许从失败 schema row 继续拼接，也不允许混用不同 endpoint/config。每条聚合 label 必须携带 composite hash、每维 MAD 和双-family provenance。

## 7. No-API：label/data gate、训练、校准和 internal holdout

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/19_audit_pm_v2_data_labels.py

PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/22_train_pm_v2.py
```

训练前必须满足：完整 action matrix、动作 oracle 多样性、M0/R0/RS 覆盖、regime 对齐、每维和每 action-dimension 的 low-MAD coverage。所有中位数 label 都保留；MAD 越大，该 head 的训练权重越低。

PM-v2.1 使用 user-group bootstrap ensemble；calibration 对每个用户先取 max-over-states×actions nonconformity，再拟合每个 response/risk head 与 composite 的 split-conformal radius，固定 `z` 不通过 coverage 搜索。selection grid 中每个候选都由 YAML 冻结的同一 quality−risk−cost objective 标尺评分；候选不能通过减小自己的 risk/cost penalty 机械抬高调参目标。internal test 以独立 user-block Wilson 下界检查 head-wise interval coverage；冻结的 evidence threshold 为 `0.60`，在 16 个 internal users 下要求至少 14 个完整 user-block 命中，而不是把每个 head 都设成实际上近似 16/16 的门。internal 还检查 quality/support/risk/cost、动作熵与最大动作份额、M0/R0/nonfallback M0+R0、两类 fallback、每个 regime 以及与 cost-matched fixed 的 user-cluster paired bootstrap。deployment non-inferiority/tradeoff 与 learned-routing advantage 分开报告；进入 external 的必要条件是 quality、emotional support 和 utility 三个 paired CI lower bound 都**严格大于 0**，全 tie 不能算 learned advantage。

`training_report.json` 的 `status` 非 `COMPLETE` 时停止。`--allow-nonreportable` 只用于诊断，不能用于 reportable freeze 或 external API。

## 8. No-API：盲化人工审计

packet 的抽样种子、条数和所有阈值来自 YAML；脚本没有可临时更换 human seed 的 CLI。

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/27_prepare_pm_v2_human_audit.py
```

至少两位 annotator 独立填写副本；不得看到 action ID、policy 名称或 LLM judge 分数。六个 response dimensions 与七个 risk dimensions 都要标注，尤其不能把 emotional support 当作 composite 的替代品。

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/28_analyze_pm_v2_human_audit.py \
  --completed <ANNOTATOR_A.csv> <ANNOTATOR_B.csv>
```

human–LLM MAE/Spearman、within-one 和 human inter-rater kappa 任一 YAML gate 失败时不可冻结。

## 9. No-API：固定基线与不可变 study freeze

PM-v1 的 8,160-row EvoEmo baseline turns 是外部冻结工件，不复制进 Git。当前本机
从私有 vault 解析并重新校验该对象；换机器时必须把变量改成同一 SHA-256 的受控
artifact 路径：

```bash
export PMV1_BASELINE_TURNS="$( \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  /home/tokkio/metacom_workspace/artifact_vault/resolve_artifact.py \
  --vault /home/tokkio/metacom_workspace/artifact_vault \
  --collection metacom_v1_artifacts_20260714 \
  --relative-path outputs/evoemo_selective/turns.jsonl \
)"

printf '%s  %s\n' \
  9bd51edea120790431fe43603210253595bd71f273b76a82036f52521ba22ee4 \
  "$PMV1_BASELINE_TURNS" | sha256sum -c -
```

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/29_prepare_pm_v2_fixed_baselines.py

PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/26_freeze_pm_v2_study.py \
  --seed-audit data/pm_v2/train_seed_dialogues.jsonl.audit.json \
  --external-baseline-turns "$PMV1_BASELINE_TURNS"
```

freeze 会绑定 seed/data/evaluator-context/sweep/judge/compatibility/human/internal/checkpoint/config/fixed-track hashes。固定输出至少包括 calibration-selected cost-matched action checkpoint 和 `ME+R0` checkpoint。

## 10. External generation：script 24 dry-run 同时是 action/OOD no-API preflight

External action preflight 对 fallback 与 learned routing 分开统计：正式 gate 只使用
freeze 中精确评分 turns `[3, 8]`；`severe_ood` / `no_feasible` fallback rate 使用该
评分矩阵的全部 states；M0、R0、
M0+R0、最大动作占比、动作熵和 distinct-action 数只使用
`fallback_type=none` 的 learned rows。Fallback 选出的安全动作不能为 learned
routing 的 abstention 或 diversity gate 提供虚假通过证据；该统计口径同时写入
generation manifest、preflight report 和 study freeze。

完整 10-turn fixed tracks 仍做 no-API action diagnostic，但该 diagnostic 不参与
paid-entry PASS，不能掩盖 turns 3/8 上的动作塌缩。freeze 另外内容寻址精确的
204-unit 外部矩阵；script 24 每个条件只生成这 204 个 fixed-context cases，不再
生成 1,020 turns。没有选择 turn 的 CLI，生成后的 unit IDs 必须与该 frozen hash
逐项完全一致。ledger 一旦非空，后续 dry-run 只能复现完全相同的 call plan 与
cost estimate。

`scripts/23_select_pm_v2_actions.py` 已禁用；它无法证明调用方 runtime 与 freeze 一致。唯一入口是 freeze-bound 的 `scripts/24_run_pm_v2_evoemo.py --dry-run`。

External generation 的预算价格固定在 study freeze（保守代理 0.15/0.60
USD per MTok）。两个 CLI 价格参数仅作可选一致性断言；省略时直接使用
freeze 值，传入 0 或任何不同值都会在生成 cost plan 前失败。

Learned PM 的 dry-run：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/24_run_pm_v2_evoemo.py \
  --dry-run \
  --freeze outputs/pm_v2_study_freeze.json \
  --checkpoint outputs/pm_v2_model/pm_v2.joblib \
  --condition pm_v2 \
  --out-dir outputs/evoemo_pm_v2 \
  --max-api-calls 250 \
  --max-estimated-usd "$PMV2_EXTERNAL_GENERATION_MAX_USD" \
  --max-input-tokens-per-call 12000
```

同样对两个 PM-v2 fixed conditions 分别 dry-run：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/24_run_pm_v2_evoemo.py \
  --dry-run \
  --freeze outputs/pm_v2_study_freeze.json \
  --checkpoint outputs/pm_v2_model/pm_v2_cost_matched_fixed.joblib \
  --condition pm_v2_cost_matched_fixed \
  --out-dir outputs/evoemo_pm_v2_cost_matched_fixed \
  --max-api-calls 250 \
  --max-estimated-usd "$PMV2_EXTERNAL_GENERATION_MAX_USD" \
  --max-input-tokens-per-call 12000

PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/24_run_pm_v2_evoemo.py \
  --dry-run \
  --freeze outputs/pm_v2_study_freeze.json \
  --checkpoint outputs/pm_v2_model/pm_v2_me_r0_fixed.joblib \
  --condition pm_v2_me_r0_fixed \
  --out-dir outputs/evoemo_pm_v2_me_r0_fixed \
  --max-api-calls 250 \
  --max-estimated-usd "$PMV2_EXTERNAL_GENERATION_MAX_USD" \
  --max-input-tokens-per-call 12000
```

先检查 learned PM 的 severe-OOD/no-feasible fallback、M0/R0/M0+R0、nonfallback、最大动作份额和 entropy gate；再检查 `pm_v2` 与 cost-matched fixed 的预计 token 成本符合 freeze 中的 10% 相对偏差阈值。只有全部 PASS 才逐条件执行相同命令的 `--run`，并加入各自 dry-run SHA：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/24_run_pm_v2_evoemo.py \
  --run \
  --freeze outputs/pm_v2_study_freeze.json \
  --checkpoint <FROZEN_CONDITION_CHECKPOINT> \
  --condition <FROZEN_CONDITION_NAME> \
  --out-dir <MATCHING_DRY_RUN_DIRECTORY> \
  --max-api-calls 250 \
  --max-estimated-usd "$PMV2_EXTERNAL_GENERATION_MAX_USD" \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_THIS_CONDITION_DRY_RUN>
```

生成完成后必须在同一 matched unit matrix 上比较实际 `input_tokens`。`external_evaluation.maximum_cost_matched_relative_deviation=0.10`：learned PM 与 cost-matched fixed 的 mean observed input-token 相对偏差超过 10% 时，停止 response judging；不能继续称为 cost-matched。

## 11. Forced-swap 技术/无效性 gate：先于 full external judging

development judge families 与 external families 必须不重叠。script 30 使用 freeze 中两个不同 external families，对 40 个 matched units 做两个候选顺序；预期 40 × 2 orders × 2 families = 160 calls。

先 dry-run：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/30_eval_pm_v2_forced_swap.py \
  --dry-run \
  --freeze outputs/pm_v2_study_freeze.json \
  --turn-paths outputs/evoemo_pm_v2/turns.jsonl outputs/evoemo_pm_v2_cost_matched_fixed/turns.jsonl \
  --generation-attestations outputs/evoemo_pm_v2/artifact_attestation.json outputs/evoemo_pm_v2_cost_matched_fixed/artifact_attestation.json \
  --out-dir outputs/pm_v2_forced_swap \
  --max-api-calls 160 \
  --max-estimated-usd "$PMV2_FORCED_SWAP_MAX_USD" \
  --max-input-tokens-per-call 12000
```

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/30_eval_pm_v2_forced_swap.py \
  --run \
  --freeze outputs/pm_v2_study_freeze.json \
  --turn-paths outputs/evoemo_pm_v2/turns.jsonl outputs/evoemo_pm_v2_cost_matched_fixed/turns.jsonl \
  --generation-attestations outputs/evoemo_pm_v2/artifact_attestation.json outputs/evoemo_pm_v2_cost_matched_fixed/artifact_attestation.json \
  --out-dir outputs/pm_v2_forced_swap \
  --max-api-calls 160 \
  --max-estimated-usd "$PMV2_FORCED_SWAP_MAX_USD" \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_FORCED_SWAP_DRY_RUN>
```

这不是小样本显著性检验，也不用于调模型。它检查 schema 完整、order disagreement、跨 family 方向/相关性和预注册 futility continuation。任一检查不通过，状态为 `NONREPORTABLE`，full external 停止。40 个 pilot units 的 IDs 和选择 contract 写入 attestation；script 25 必须将它们从 confirmatory full sample 中排除。

## 12. External pointwise schema smoke：4 calls

forced-swap PASS 后、full pointwise judging 前，必须用一个已从 confirmatory sample
排除且在 freeze 中精确绑定的 forced-swap unit，运行同一套匿名 pointwise
response/risk prompt 与 structured schemas。矩阵固定为 1 condition × 2 external
families × 2 schemas = 4 calls；它只验证 schema transport、usage accounting、ledger
和 attestation，不允许据此宣称 raw-family 评分质量。

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/35_run_pm_v2_external_pointwise_schema_smoke.py \
  --dry-run \
  --max-api-calls 4 \
  --max-estimated-usd 1 \
  --max-input-tokens-per-call 12000
```

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/35_run_pm_v2_external_pointwise_schema_smoke.py \
  --run \
  --max-api-calls 4 \
  --max-estimated-usd 1 \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_POINTWISE_SCHEMA_SMOKE_DRY_RUN>
```

只有 `summary.json.status=PASS`、4/4 schema/usage PASS 且 attestation 与 frozen
forced-swap selection 完全一致，script 25 才能进入 full core；该检查发生在任何
full judge client 创建之前。

## 13. Full external multi-family pointwise evaluation

只有 observed cost-match 与 forced-swap gate 均 PASS 才运行。script 25 从 freeze 读取 condition matrix 和两个 external judges；输入 turn files 与 generation attestations 必须逐一匹配。先 dry-run：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/25_eval_pm_v2_external.py \
  --dry-run \
  --freeze outputs/pm_v2_study_freeze.json \
  --turn-paths "$PMV1_BASELINE_TURNS" outputs/evoemo_pm_v2/turns.jsonl outputs/evoemo_pm_v2_cost_matched_fixed/turns.jsonl outputs/evoemo_pm_v2_me_r0_fixed/turns.jsonl \
  --generation-attestations outputs/evoemo_selective/artifact_attestation.json outputs/evoemo_pm_v2/artifact_attestation.json outputs/evoemo_pm_v2_cost_matched_fixed/artifact_attestation.json outputs/evoemo_pm_v2_me_r0_fixed/artifact_attestation.json \
  --key-claim-verification outputs/pm_v2_forced_swap/summary.json \
  --key-claim-verification-attestation outputs/pm_v2_forced_swap/artifact_attestation.json \
  --pointwise-schema-smoke-summary outputs/pm_v2_external_pointwise_schema_smoke/summary.json \
  --pointwise-schema-smoke-attestation outputs/pm_v2_external_pointwise_schema_smoke/artifact_attestation.json \
  --max-api-calls 6000 \
  --max-estimated-usd "$PMV2_FULL_EXTERNAL_JUDGE_MAX_USD" \
  --max-input-tokens-per-call 12000
```

确认 call plan 已排除 forced-swap 40 units、condition/attestation 全覆盖、两个 judge families 不同且均与 development families 隔离后才 run：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/25_eval_pm_v2_external.py \
  --run \
  --freeze outputs/pm_v2_study_freeze.json \
  --turn-paths "$PMV1_BASELINE_TURNS" outputs/evoemo_pm_v2/turns.jsonl outputs/evoemo_pm_v2_cost_matched_fixed/turns.jsonl outputs/evoemo_pm_v2_me_r0_fixed/turns.jsonl \
  --generation-attestations outputs/evoemo_selective/artifact_attestation.json outputs/evoemo_pm_v2/artifact_attestation.json outputs/evoemo_pm_v2_cost_matched_fixed/artifact_attestation.json outputs/evoemo_pm_v2_me_r0_fixed/artifact_attestation.json \
  --key-claim-verification outputs/pm_v2_forced_swap/summary.json \
  --key-claim-verification-attestation outputs/pm_v2_forced_swap/artifact_attestation.json \
  --pointwise-schema-smoke-summary outputs/pm_v2_external_pointwise_schema_smoke/summary.json \
  --pointwise-schema-smoke-attestation outputs/pm_v2_external_pointwise_schema_smoke/artifact_attestation.json \
  --max-api-calls 6000 \
  --max-estimated-usd "$PMV2_FULL_EXTERNAL_JUDGE_MAX_USD" \
  --max-input-tokens-per-call 12000 \
  --accept-cost-estimate-sha256 <SHA_FROM_FULL_EXTERNAL_DRY_RUN>
```

外部正式报告六个 response dimensions、冻结 composite、七个 risks、observed input tokens，并给出按 user/scenario 聚类的 paired/bootstrap intervals。必须包含 PM-v2、calibration-selected cost-matched fixed、`ME+R0` 以及 freeze 中的 context-only、structured、raw-session 和 full-history 条件。

## 14. 停止规则与成功标准

任一步满足以下任一条件就停止后续付费调用：

- dry-run budget/hash/lineage/attestation 失败；
- compatibility pilot 失败；
- 7,488 outcome 或 label matrix 不完整；
- dimension constant、exact duplicate、相关性、MAD coverage 或 human gate 失败；
- internal reportability gate 失败（`training_report.json.status != COMPLETE`）；
- external action/OOD/diversity gate 失败；
- cost-matched fixed 与 learned PM 的预计或 observed tokens 超过 10% 偏差；
- forced-swap 技术/无效性 gate 失败；
- 4-call external pointwise schema smoke 未精确 PASS。

PM-v2.1 只有在实际结果同时证明以下事项后才算解决 PM-v1 的核心经验问题：

1. learned、非 fallback 的 action 分布有足够熵和多样性，不是近常量动作；
2. M0、R0、M0+R0、memory-on+R0 和 RS 都在合适 regime 被使用；
3. 与同预算 fixed 相比，质量/支持、风险、成本和 conservative utility 达到预注册边界；
4. interval coverage、OOD/fallback 和 human calibration 均通过；
5. 排除 pilot units 的 confirmatory full evaluation 支持主结论，forced-swap
   技术/顺序稳健性结果不与其矛盾；forced-swap 本身不冒充 confirmatory effect
   estimate；
6. 负面结果原样报告。

在这些结果真正产生前，只能写“PM-v2.1 的结构性修复和 fail-closed 验证链路已实现”，不能写“PM-v2.1 已证明学会最优 quality–risk–cost 平衡”。
