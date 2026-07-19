# PM-v1.5 快速会议版：研究合同与执行顺序

> **2026-07-18 审查修复提示：** 下一次正式运行的方法定义已由
> `PM_V1_5_PROTOCOL_REPAIR_CONTRACT_ZH.md` 取代。新合同引入正式、受限且计费的
> source-level Step-0，区分 requested/attempted/realized action，并重组机制、固定策略和
> 外部效率三层 gate。V8.2 已真实消费并 fail-closed；中央配置现已固定为 release 状态，
> 但 approval manifest 仍为空，因而任何付费调用继续 fail-closed。旧 V8.3 dry-run 已失效；
> V8.4 已真实执行并在 transport/schema 层 PASS，但 exact surface 复核发现
> readiness 未进入两个 Strategy case 的可见话语，且旧自动审核没有绑定付费九例；
> 因而 V8.4 已归档为 `CONSUMED_PASS_SEMANTICALLY_SUPERSEDED`。V8.5 两次真实调用
> 都因 provider 的通用 role list 以 user 结尾而 fail-closed，identity 已消费。V8.6 将历史
> 改成 schema-level `user_text → assistant_text` exchanges，由本地 compiler 保证角色顺序，
> 已真实 PASS：9/9 accepted、12 次物理尝试、0 fallback；3 次 initial failure 均为
> `unique_current_user_text`，没有复现 role-order bug。随后绑定该 exact attestation 的
> V3 双家族语义审核真实执行：DeepSeek 首次调用成功，Gemini 的 OpenAI-compatible
> `response_format` 请求在第二次物理调用返回 terminal HTTP 400，identity 已消费并
> fail-closed。该失败不能证明 rubric schema 不受支持；V4 已将 Google judge 冻结为官方
> native `generateContent + responseJsonSchema` transport，保留相同模型、严格 schema 和
> 本地 Pydantic 验证，并将 Gemini 排为首个物理调用以最小化再次不兼容的花费。由于
> V8.6 的历史 attestation 绑定了整份配置和共享 API 代码，不能在新代码上重新盖章复用；
> V8.7 已改为只绑定 generator-relevant config projection，今后的 judge-only 修改不会再
> 误伤上游 pilot。V8.7 进一步把 pilot 预算上限冻结进 YAML，消除了依赖隐藏 CLI
> 参数而产生多个 cost identity 的歧义；identity `920807ec…84e8` 已真实执行并
> `CONSUMED_PASS`：9/9 accepted、12 attempts、3 次 bounded repair、0 fallback，
> 18,288 input / 1,964 output tokens，约 `$0.0039216`。当前没有 active approval；
> V4 native-Gemini semantic review 已真实消费并在测量有效性上 fail-closed：120 个
> logical calls 最终成功，但 targeted controls 0/24。旧单字段 v1 因本地 Gemini usage
> parser 漏分项停止；v2 验证了精确 token 记账，却只得到 7/14 内容正确，并在第 15 个
> logical call 的首次 malformed JSON 上按旧合同立即终止，并非耗尽重试。balanced v3
> 随后真实消费两次：Gemini PASS；DeepSeek verdict 与逐字 quote 正确，却把 memory text
> 引到 `memory_id`，原始 surface 还带 `We` 前缀，旧 client 又静默截取 JSON。当前 v4
> 将 record metadata 移出 citable evidence，并把 citation integrity 与 verdict accuracy
> 分开记录。v4.0 `acb07969…f7caf` 因短时 provider availability 仅完成 1/16 endpoint calls，
> 已消费且无法提供测量结论。v4.1 将 transport 与 malformed-output 计数拆开，显式审计
> 确定性 JSON wrapper 规范化，单项不可用时继续冻结矩阵。fresh 16-call dry-run 已双目录
> 复现，identity `22265947…936d`，最大 160 physical / `$0.037195`；
> 中央 approval 为空。本诊断不是 formal gate，不能授权
> training、V5、52 users，也不支持真实用户需求识别/真实改善主张。
> 本文保留为 2026-07-17 版本的历史设计
> 背景，与新合同冲突时以新合同为准。

更新时间：2026-07-19
当前收口状态：V8.11.1 已真实 `CONSUMED_PASS`：9/9 accepted、10 次物理调用、
1 次普通 content repair、0 transport retry、0 fallback；9 例有 8 个不同 current turn，
唯一重复组是同一 user/family/split 的合法反事实对。identity `6876e2d3…25ed` 永久
禁止复用，approval map 与 pending map 均为空。其 artifact 中“full generation 前需要
independent human semantic review”的 scope 句是旧 V4 流程的历史描述，不是当前执行门；
权威顺序是正式 468-state corpus 生成后执行 actual-468 structured QA v3，并在 7,488-action
sweep 前 fail-closed。为保留已通过 attestation，不回写或重签历史 artifact。

状态：免费代码与 fail-closed 链路已搭建；历史整包 generation compatibility
transport pilot 已失效，V8.1 逐例试运行在 9 个 case 中有 2 个话题 lint 失败。当前合同已改为
surface-only 逐 case 生成和每 case 最多一次预预算 repair，必须在新目录重跑，
不能视为仍然有效的上游 gate，更不是论文 efficacy 结果。其余正式链路尚未执行，也没有
真实 V1.5 主结果。任何 dry-run、脚手架测试或旧 V1 诊断都不能写成论文结果。

## 1. V1.5 到底要支持什么主张

V1.5 的正式主张分成两层，不能混写。

### 1.1 外部回复层主张

冻结后的 EvoEmo 评测只在以下两项同时成立时输出 `SUPPORTED`：

1. PM-v1.5 相对 `best_fixed`（代码中的条件名；语义上是固定
   `MPMSME+RS` structured-high-resource policy）的冻结 quality composite
   非劣效：按 `user_id` 聚类的配对 bootstrap 95% CI 下界不低于 `-0.02`；
2. 同一配对比较中，PM-v1.5 的 `observed_input_tokens` 差值 95% CI 上界严格
   小于 0。

判定由 `src/metacom_pm/v1_5_external_claims.py` 自动写入
`claim_assessment.json`。外部 judging 运行成功只代表数据完整，绝不自动代表主张
成立；任一条件失败都必须报告 `NOT_SUPPORTED`。

quality composite 不是只靠 emotional support 和 personalization 两项。主分析冻结为六个
独立维度：emotional support、personalization、memory appropriateness、factual
grounding、temporal consistency、non-intrusiveness；judge 不输出 `overall`，最终
composite 由冻结权重确定性计算。GPT-4o 对全部 192 个正式 unit 做主质量判断；Claude
只对预冻结的 54-unit（每用户 3 个）分层样本做敏感性分析，不与 GPT 分数取中位数、
也不混入主效应估计。Claude 结果无论同向或反向都必须报告。这是 V1.5 的成本—证据
折中：主矩阵每 unit 只有一个 judge，不能写成“全量双家族复核”。batched prompt 也可能
产生 contrast/context bias；循环位置平衡、双 order transport pilot 和 Claude 分层敏感性
能检查但不能彻底消除该局限，论文 limitations 必须明示。

evidence/resource-use risk 不进入上述质量—成本主张。两家 judge 对预冻结的 36-unit
（每用户 2 个、覆盖 turn 3/8）分层样本做独立 batched audit。只有相对 `best_fixed` 的
用户聚类 CI 上界不超过冻结的 [0,1] 风险 margin 0.05 时，才允许写“预注册分层审计未
发现 PM 增加证据误用问题”；这不是总体安全性、临床风险或真实部署风险结论。

V1.5 当前没有可支持确认性 latency 优势的交错测量设计。因此 latency 只能作为
描述性诊断：脚本 25 会从同一 scored unit matrix 生成
`latency_diagnostic.json`，汇总各条件的 mean/median/P95 和 PM-minus-baseline 配对
点差，并硬编码 `confirmatory_latency_claim_allowed: false`。论文不能写成“显著降低
latency”。若会议稿必须把 latency 放入正式主张，需要另加冻结的 interleaved
latency 实验；不能拿顺序运行的 wall-clock 时间补写结论。

### 1.2 路由层主张

“调用较合适的资源”只由 synthetic internal-test 的完整反事实 action matrix 支持：

- 每个 state 都实际生成并判断全部 16 个合法 action，而不是用启发式标签猜结果；
- PM 与在 calibration split 选出的 same-token cost-matched fixed policy 做用户聚类
  配对比较；内部 advantage gate 不通过时禁止进入外部生成；
- 冻结报告给出 regret、oracle-hit-rate、memory-source precision/recall/F1、M0
  判断、RS 判断、quality-acceptable rate 和 excess observed cost。

这些是“在本研究的 synthetic 状态和模型 judge 定义下的决策质量”，不是人工确认的
资源正确性，更不是临床、真实世界或用户获益主张。

### 1.3 明确不主张

- 不声称临床改善、真实用户改善、安全有效性或现实世界资源选择正确；
- 不声称做过人工评测、人工校准或人工 Strategy Bank 审批；
- 不把自动语义审核写成人评替代的等价证据；
- 不把 forced-swap canary 写成 PM efficacy 证据。

## 2. 训练与测试必须统一的机制

以下内容在 development、内部测试和外部评测中由配置、attestation 与 study freeze
共同锁定：

| 项目 | V1.5 冻结值/纪律 |
|---|---|
| Strategy Bank | `data/strategy/strategy_cards_v1_5.jsonl`，11,590 张，来自 823 个 ESConv 对话；正式 52 个 development seed 来源已逐实例排除，8 个策略家族均保留 |
| 泄漏排除 | `escN -> esconv_N` 确定性映射与既有 Jaccard 规则取并集；已移除 `0539/0585/1212` 的 26 张卡 |
| supporter prompt/cap | 同一 `SupporterGenerationContract`；temperature 0；300 output-token cap；length/未知 finish reason 失败 |
| memory/strategy retrieval | 同一实现、top-k、minimum-score 和 source 定义 |
| Evidence Filter | 全链路关闭；PM-v1.5 是纯 pre-retrieval router |
| fixed seeker | 独立 `outputs/evoemo_fixed_tracks_v1_5/`；300 API cap；任何 truncation、缺轨或旧 V2.2 bundle 都拒绝 |
| 配置与 checkpoint | `configs/pm_v1_5.yaml`、`pm_v1_5.joblib` 及两个 fixed checkpoint 独立命名和哈希 |
| 外部单元 | 同一 EvoEmo、simulator、3 个 robustness seeds、turn 3/8；freeze 后不可改变 |

不同用户拥有不同的 memory 内容是研究对象本身，不属于配置漂移。需要统一的是 memory
构造/检索机制，而不是强迫 train/test 存储相同文本。

RAG card 与测试文本不重合是必要条件，但不是单独充分条件。还必须同时保证：来源级
排除、split 用户隔离、近重复审计、同一检索合同、测试前冻结以及测试后不调参。当前
bank 的剩余 turn-level 命中是通用寒暄/共情短句，应保留审计报告并在方法中说明，不能
宣称“字面零重合”。最新 v2 turn-level audit 把每条命中反查到 card 的
`source_dialogue_id`：13 条均为跨来源通用短句，确定性同源命中为 0。

`v1_5_create_freeze.py` 会重新核对上述 bank/seed/audit 的内容哈希、84 个来源排除、
875 条 train seed、development 与 external 的三项 retrieval 参数，并要求 sweep/judging
确实覆盖 468 states × 16 actions = 7,488 outcomes/labels。任一旧 bank、旧 seed、pilot
矩阵或 retrieval 漂移都会在 external 付费生成前失败。

## 3. 数据与调参纪律

1. `train` 只拟合模型；
2. `calibration` 只选择 selector 超参数和 fixed comparator；
3. `internal_test` 在上述选择冻结后只查看一次，用于内部 reportability 与
   decision-quality；看过后再改模型，就必须更换新的 held-out 用户；
4. 只有 training report 为 `COMPLETE`、内部 learned-routing advantage 已验证、
   decision-quality 与 fixed-baseline 产物完整时才能创建 freeze；
5. freeze 后才允许正式 external generation；外部结果出来后不得回头改模型、margin、
   composite、baseline 或筛样规则；
6. EvoEmo 应称为“冻结后的 development-informed external evaluation”，不包装成完全
   pristine 的临床外部验证。

## 4. 唯一允许的执行顺序

每个付费阶段都必须先运行 `--dry-run`，保存完整 call plan，核对预算，并由用户明确
接受当前 `cost_estimate_sha256`（fixed seeker 使用对应的 dry-run acceptance hash）。
`--run --overwrite` 被禁止；发生一次已花费的失败后不能用覆盖文件伪装成同一确认性运行。

| 顺序 | 动作 | API 调用规模 | 进入下一步的条件 |
|---:|---|---:|---|
| 0 | clean bank、split manifest、875 条 clean seed、overlap audits | 0 | 已完成且后续只认其 SHA |
| 0.5 | 专用 Python 3.13.2 venv 中运行 `v1_5/19_preflight_semantic_runtime_v1_5.py` | 0 | exact package/device/dtype/user-site 与 3×384 canary `PASS`；真实 BGE 长上下文 strict `PMV2State` 构造、Step-0/state 文本与向量 hash 相等、implicit truncation=0；通用 readiness 20-case 结果只报告；compiler-owned 12 个 readiness surface 必须 12/12 被 frozen BGE 识别 |
| 1 | `v1_5/20a_run_generation_compatibility_pilot_v1_5.py` | 成功路径 9；18 个 content attempts；上限 54 个 physical attempts | observable-state-support v18 + fresh V8.11.1 必须 PASS；同一 user/family/split 最多两对完全相同的 current turn、每组最多 2，9 例至少 7 个独立表达，跨 user/family/split 与人工 nonce 均禁止；两对上限逐例执行；每个 content attempt 各有最多 3 个 transport slots，最终 fallback 必须为 0 |
| 2（历史失败） | `v1_5_run_automated_semantic_review.py` V4 | 已真实执行 120 logical / 144 physical | native transport 成功，但测量工具 targeted controls 0/24，永久 `CONSUMED_FAILED_CLOSED`；不得重跑或作为上游 PASS |
| 2.1（已消费校准） | `v1_5/20c_prepare_v4_single_field_diagnostic_v1_5.py` + `20d_run_v4_single_field_diagnostic_v1_5.py` | V4.2 实际 8 logical / 12 physical | 8/8 完成；确定性=1.0、verdict=.875、citation=.875。Gemini 一次 citation section 不足；DeepSeek 一次把 `explore_first` 错当成必须出现“ready”字样。identity 永久 consumed；结果只用于修订正式测量合同 |
| 2.2（已落实为正式合同） | actual-468 structured QA v3 | 0（合同/测试） | 4 个确定性字段代码硬验；仅 context grounding、advice readiness 进入原子双家族 panel；readiness 有明确操作定义；引用只报告。不得把分歧改写成 gold 或据此调样本/阈值 |
| 3 | `v1_5/20_generate_pm_v2_development_data_v1_5.py` | 成功路径 468；最多 936 个 content attempts；每个 content attempt 最多 3 个独立 transport slots，physical 硬上限 2,808 | exact V8.11.1 attestation 的路径、raw/internal SHA 与 contract SHA 进入 cost identity；52 users × 9 个逐例 surface，每例最多一次 content repair，transport retry 不消耗 repair；允许的同文反事实由 history/catalog 区分且逐 bundle/split 审计；468 states 完整并反平衡 |
| 3.5 | `v1_5_run_actual_corpus_semantic_review.py` | (468 × 2 原子语义 packet + 4 controls) × 2 家族 = 1,880 logical calls；冻结的 6-attempt 上界为 11,280 physical attempts（实际预算以 dry-run 为准） | 4 个 deterministic fields 全部 PASS；真实 packet 无双家族一致 `not_supported`；负控无双家族一致漏检；judge 分歧保留并报告；citation 只报告；provider-surface fallback 分 split 低于冻结上限 |
| 3.6 | `v1_5/20b_run_step0_shortcut_audit_v1_5.py` | 0 | 完整 468 states 上的单阈值和 train-only user-group 多变量 probe 均未达到冻结的 near-oracle 上限；报告与数据 attestation 内容寻址绑定 |
| 3.7 | `v1_5/20b_preflight_rule_grid_v1_5.py` | 0 | 只读 train/calibration states、不读 outcome/internal；候选至少形成 2 种 state-level policy mapping，且最大 pairwise disagreement 不低于冻结下限；报告在 sweep/训练前绑定 |
| 4 | `v1_5/06_run_action_sweep_v1_5.py --v1-5-full-sweep-scope` | 7,488 | 验证 actual-468 structured QA 与 Step-0 shortcut attested PASS；旧 V4 明确不进入 formal binding；真正 `scope=full`；每 state × 16 action 完整 |
| 5 | `v1_5/21_judge_pm_v2_action_sweep_v1_5.py` | 29,952 | 7,488 × response/risk × 2 judge families；完整性与 judge-health gates PASS |
| 6 | `v1_5/22_train_pm_v2_v1_5.py` | 0 | 入口现场重验与 development 相同的 exact runtime；只用 train/calibration 调参；internal gate 为 `COMPLETE`，否则停止 |
| 7 | `v1_5/23_build_decision_quality_report_v1_5.py` 与 `29_prepare_fixed_baselines_v1_5.py` | 0 | 两份报告均与 checkpoint/training report SHA 一致 |
| 7.5 | `v1_5/12_build_esconv_test_v1_5.py` + `13_preflight_esconv_policy_v1_5.py` | 0 | 使用同一 PMV2 checkpoint、同一 BAAI/Step-0 与 transparent rule；自定义 70/15/15 split 的 169 个 non-overlap test dialogues 全保留；2,275 supporter turns 中按 outcome-free history-support rule 保留 2,112；仅允许 `M0+R0/M0+RS`，policy choice 不读 gold response/strategy |
| 8 | `v1_5/15a_build_evoemo_fixed_tracks_v1_5.py` | 由 dry-run 给出；当前数据设计为 1,020 个 seeker turns | 完整、无 truncation、独立 V1.5 bundle |
| 9 | `v1_5_create_freeze.py` | 0 | 重新验证步骤 3–8 的内容寻址链；同时绑定 ESConv build/policy artifacts 与 EvoEmo fixed tracks；任一外部结果出现后不得修改 PM 再跑另一外部环境 |
| 9.5 | V1.5 ESConv 两动作 sweep + orientation-balanced blind R0-vs-RS judging | 2,112 × 2 唯一 generation outcomes；judge 规模以独立 dry-run 为准 | learned/rule/always-R0/always-RS 共享完全相同的两份 outcome，不重复计 alias；dialogue-cluster CI；质量分别对两个 fixed 作非劣，Strategy 调用与 input cost 单独报告；不得声称长期记忆 |
| 10 | `v1_5/24...` 生成 learned、cost-matched-fixed、ME+R0；`24a...` 生成 4 个 reference baselines | 当前单元合同为 204 × 7 = 1,428 calls；最终以各 dry-run 为准 | 7 条 condition 的同一 frozen unit matrix 完整；learned/rule external artifact 自包含 runtime lineage 与 development/external score comparison，禁止外部调阈值 |
| 11 | `v1_5/30_eval_forced_swap_canary_v1_5.py` | 12 units × 2 orders × 2 families = 48 | schema、顺序稳健性和跨家族方向敏感性 PASS；12 units 从主评测排除 |
| 12 | `v1_5/36_run_external_batched_schema_order_pilot_v1_5.py` | 3 units × 2 schemas × 2 orders × 2 families = 24 | 使用 canary 排序后的前三个单元；schema 必须全通过，mean/max absolute order delta 还必须低于冻结阈值；只作 transport diagnostic |
| 13 | `v1_5/25_eval_pm_v2_external_v1_5.py` | 192 GPT 主质量 + 54 Claude 敏感性 + 36×2 risk audit = 318；以 dry-run 为准 | 七个 condition 全部进入每个 batched call；完整后单独生成 `SUPPORTED`/`NOT_SUPPORTED`、有边界的 risk audit 与非确认性 latency diagnostic |

V1.5 不运行 PM-v2.2 的 180-generation/360-judge compatibility pilot；这是快速通道的
明确范围缩减。代价是证据强度低于 V2.2，但不能用把全量 sweep 标成 “pilot” 的方式
绕过：V1.5 的 sweep 现在必须诚实记录为 `full`。

按当前冻结规模，上表从 compatibility pilot 到 external judging 的物理调用上限约 41,390，
其中 29,952 个来自 development 双家族 judging。V1.5 的“快”主要是省掉人工流程和
V2.2 的额外兼容性/复核层，不代表它是几十次调用的小实验；若时间窗口承受不了这个
规模，应在付费前另立一个明确降级、重新命名的 pilot，不能事后把不完整矩阵称作 V1.5
正式结果。外部付费 judge 部分已经从旧 pointwise 设计的 5,376 calls 降为 318 calls；
不是恢复 V1 老评测链，而是在当前 freeze/policy-lock/attestation 之后接入独立的 V1.5
batched scorer。

截至 2026-07-19，已记录以下 dry-run 与历史执行状态。generation compatibility
一行保留历史调用及预算哈希用于追溯，但该调用绑定旧配置，不能充当当前上游 gate：

| 阶段 | 当前 dry-run 上界 | 当前 hash |
|---|---:|---|
| generation compatibility | V8.4 transport/schema PASS 但语义性淘汰；V8.5 真实 FAIL；V8.6 真实 PASS：9/9 accepted、12 attempts、3 repairs、0 fallback、18,288 input / 1,942 output tokens、约 `$0.0039084`；没有 role-order failure | V8.6 attestation `15135ad9…7f2c`；identity `64a06993…ef85` 已消费并关闭，禁止复用 |
| 自动语义审核 | V4 native 测量合同失败；旧单字段 v1/v2/v3/v4.0 失败事实保留。v4.1 identity `22265947…936d` 已完成 16/16，20 physical attempts，花费约 `$0.0016565`；deterministic=1.0、semantic verdict=.75、citation=.875、joint=.6875，暴露了 source taxonomy、tri-state verdict 与 citation/outcome 混合问题 | v1/v2/v3/v4.0/v4.1 identities 均永久 consumed。v4.2 改为 8 code truths + 4 semantic items/8 calls；协议 `first-paper-scoped`，fresh dry-run/identity 尚待生成，绝非 formal gate |
| generation compatibility V8.7 | generator-relevant scoped lineage；预算从 YAML 独立 stage contract 唯一冻结为 18 attempts / `$0.018` / 4000 input tokens，拒绝冲突 CLI；真实结果 9/9 accepted、12 attempts、3 repairs（均为 `unique_current_user_text`）、0 fallback；18,288 input / 1,964 output tokens，约 `$0.0039216` | identity `920807ec…84e8` 与 attestation `09f1f90b…60c5` 已消费 PASS、禁止复用；当前无 active approval |
| generation compatibility V8.9 | observable-support v17；identity `e7b89550…600a` 真实执行时 context_only 成功，profile_needed 首次 HTTP 500；旧 runner 将每个 content attempt 的 transport cap 错设为 1，2 个 physical attempts 后停止，约 `$0.0003459` | `CONSUMED_FAILED_CLOSED_TRANSIENT_500`；不是内容/方法失败，identity 永久禁止复用 |
| generation compatibility V8.10 | transport-resilient identity `f518d8e3…eed4` 真实执行 4/9 后失败；6 physical、零 transport retry、约 `$0.0018943`；失败来自过严的全局 current-text 唯一门，而非 provider 波动 | `CONSUMED_FAILED_CLOSED`，永久禁止复用 |
| generation compatibility V8.11.1 | v18 controlled-counterfactual + V8.10 transport resilience；identity `6876e2d3…25ed` 已真实执行：9/9 accepted、10 physical、1 次普通 content repair、0 transport retry、0 fallback、8/9 unique current turns；attestation `dd96e1df…cfd7`、ledger `2f25e11e…3177` | `CONSUMED_PASS`；永久禁止复用。后续 compiler 修复使其 shared-code binding 正确失效 |
| 52-user generation 第一次尝试 | identity `85d1eda3…8788f` 真正执行到 user 1：9/9 surface 调用成功、0 retry/repair；随后固定 `health_routine_stress × MS semantic_decoy` 为 162 字符，超过本地 160 schema 而 fail-closed；约 `$0.004121`，users 2–52 未调用 | `CONSUMED_FAILED_CLOSED`；不是 provider/seed 内容错误；原 9-call ledger 不覆盖、不删除，可离线恢复 |
| generation compatibility V8.12 | 缩短 compiler-owned decoy；付费前穷举 216 个 family/source/role 模板，最大 155/160；identity `bebeb1b1…8564` 已真实 9/9 PASS：10 physical、1 content repair、0 transport retry、0 fallback，约 `$0.0031569`；attestation `d132e5ef…1c16` | `CONSUMED_PASS`，永久禁止复用 |
| 52-user resumable generation | exact V8.12 attestation + 原 9-call ledger 已在两目录恢复同一 user-1 bundle；fresh identity `799e1cce…a6a7`、binding `47e7d25f…e4e1`、plan `8ef7aeab…40c6`；剩余 51 users，459 success / 918 content / 2,754 new physical，上限 `$2.7235611` | `DRY_RUN_REPRODUCED_UNAPPROVED_NO_NEW_API`；必须在原 canonical 目录无 `--overwrite` 执行，禁止重生 user 1 |
| fixed seeker | 102 tracks / 1,020 calls；代理价上界 `$2.63391075` | acceptance `018c2c95…39353` |

除明确标为历史真实调用的一行外，这些 dry-run 数字只证明当前计划可计算且未创建 API
client，不等于授权执行。正式预算仍必须核对当前 endpoint/pricing 与完整 hash；任何相关
代码、配置、bank 或 seed 改动都会使上述 hash 失效。action sweep、development judging、
external generation/canary/judging 要等上游真实产物出现后才能得到精确 dry-run，不能继续
使用经验估算。

表中的统一 `$3/M`、`$15/M` 只是 fail-closed 授权上界，不是论文指标，也不是钱包实付
预测；各 NVIDIA-hosted family 是否免费或受额度约束，应由各 provider 账户单独记载，
不能从 HTTP 500 或响应体缺字段这类传输/兼容性错误反推额度结论——`api.py` 只把
HTTP 429 当作限流信号单独处理，其余错误类型都不构成额度证据。论文中的 cost 主指标
始终是各生成条件真实记录的 `observed_input_tokens`，与这张 API 采购预算表是两件事。

## 5. 外部 canary 与主评测的关系

冻结时确定性选 12 个 unit：

- forced-swap canary 只验证 judge 能否对故意交换的成对响应保持 schema 成功、顺序稳定和
  基本方向敏感；
- batched schema/order pilot 使用其中排序后的前三个 unit，并真实覆盖 quality/risk 两种
  schema、两个 order 和 GPT/Claude 两家；除 schema 成功外，还用冻结的 mean/max
  absolute order delta 阈值作数值放行；
- 12 个 unit 全部从正式 efficacy/非劣效主集合排除；
- 新的 V1.5 batched scorer 不调用共享 PM-v2.2 pointwise evaluator；旧 pointwise scorer
  与 4-call smoke 仅保留为 legacy fallback，不是论文主链路。forced swap 仍不证明 PM
  efficacy；正式主张只由第 1.1 节冻结的主质量/成本配对 CI 合同决定。
- 这一小节曾经只用一个名不副实的布尔字段
  `require_forced_swap_or_human_check_for_key_claims: true` 表达上面这段话，容易被
  误读成"仍在用 PM-v2.2 原版 forced-swap efficacy 检验"。已改成结构化的
  `external_evaluation.key_claim_gate`（`require_v1_5_forced_swap_canary: true`、
  `canary_role: judge_sensitivity_not_pm_efficacy`、
  `efficacy_decision: frozen_paired_quality_and_cost_ci`、
  `shared_pmv22_key_claim_verification: false`），单一事实来源在
  `src/metacom_pm/v1_5_forced_swap_canary.py:KEY_CLAIM_GATE`；
  `scripts/v1_5_create_freeze.py`（写入 freeze 前）和
  `scripts/v1_5/25_eval_pm_v2_external_v1_5.py`（外部评测前）都会核对配置/freeze
  里的这段内容与该常量逐字段一致，不一致直接 fail-closed。
  另外，`claim_assessment.quality_noninferiority_margin: 0.02` 是在 quality_composite
  的 [0,1] 归一化尺度上取的（`(原始1-5分-1)/4`），换算回原始1-5量表约等于0.08分，
  写论文时按这个换算表述，不要直接说"0.02分"。

## 6. 当前实现与剩余工作

已实现的免费部分包括：真实 `version: pm-v1.5`、独立配置/目录/checkpoint、clean
bank/seed 实例级隔离、EF 全链路关闭、历史自动审核/校准诊断、actual-468 structured
QA/fallback runner、9–18-call casewise generation pilot、完整数据
attestation、真实 full-sweep gate、两家族 judging、internal decision-quality、fixed
baseline 派生、无截断 fixed-track 验证、轻量 study freeze、12-unit canary、4-call external
legacy pointwise smoke、24-call batched schema/order pilot、318-call batched 主评测规划、
stratified risk audit、external claim assessment 以及对应的 fail-closed 测试。freeze 还会独立
重验 bank/seed lineage、development/external retrieval lock 和完整 468×16 链，不能只靠
目录名或某个阶段的 `COMPLETE` 字段放行。

尚未完成的是可支撑论文主链的“正式语义测量结果”、模型训练、freeze 和 external
evaluation。V8.7 已真实 PASS；V4 也已真实执行但在测量有效性上 FAIL，不能静默继承。
当前 balanced proxy runner 只诊断既有 calibration controls：它必须同时正确接受 matched
positive、把缺乏完整支持的 matched negative 判为 `not_supported`，并通过代码真值。citation
pointer 完整性单独报告，不再篡改语义 outcome。诊断通过后可继续设计正式 measurement
contract；即使表现很好，也不能扩大为真人效果主张。第一篇只报告 synthetic-state、
LLM-judged proxy utility，并把无人工金标签、无真实用户和自然度仅作有限 lint 明确列为局限。
一次只批准一个付费阶段。若任一 gate 失败，应保留失败产物并停止，不得在同一冻结协议下
不断换模型/提示词直到通过。
