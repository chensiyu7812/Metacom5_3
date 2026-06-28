# MetaCom V3.3 Pre-GitHub 红队审计报告

审计时间：2026-06-28 JST  
项目目录：`/home/tokkio/esconv_experiment_bundle/policy_manager_35`  
审计目的：检查当前项目在上传 GitHub / 交给外部模型审计前，是否存在数据逻辑、泄露、作弊、因果顺序、实验设计或代码实现风险。

## 0. 总结结论

当前内部 development 链路已经比较完整，未发现需要重跑 full judging 的硬伤：

- synthetic action sweep 完成并有 attestation；
- full judging 完成并有 attestation；
- M2b selected-set omission audit 完成并有 attestation；
- M2b 之后的 CV 训练与内部选择结果可解释；
- `text_metadata` 主 PM 不读取真实 memory snippet、retrieval score、selected IDs、生成回复或 judge label；
- user-heldout fold 没有 card/state/user 交叉；
- 当前测试 `44 passed`；
- targeted secret scan 没有发现真实 API key。

但当前项目还不能直接作为“确认性外部实验完成”的论文复现包：

- preflight 状态仍是 `API_PILOT_READY`，不是 `CONFIRMATORY_READY`；
- official ESConv 尚未接入；
- Strategy Bank 仍是 pilot/prebuilt，overlap audit 未验证；
- `outputs/study_freeze.json` 尚未创建；
- EvoEmo / ESConv 外部脚本仍有 attestation 和参数链路问题；
- 当前结果只能支持 synthetic development 内部结论，不能支持外部长期记忆迁移结论。

最重要的一句话：

> full judging 不需要因为本次发现的问题重跑；但外部 ESConv/EvoEmo 跑之前必须修脚本与冻结链路，否则外部结果会被质疑为未冻结、未绑定、可能评分旧文件。

## 1. 已通过项

### 1.1 测试与基础健康

运行结果：

```text
PYTHONNOUSERSITE=1 PYTHONPATH=src python -m pytest -q
44 passed
```

`scripts/99_release_preflight.py --skip-tests`：

```text
status: API_PILOT_READY
confirmatory_ready: false
```

这说明代码基础可运行，但正式外部确认性条件未满足。

### 1.2 Full judging 完整性

目录：

```text
outputs/full_judging_gemini_flash_lite_v3
```

完整行数：

```text
memory_omission:      3456 / 3456
memory_opportunity:  1728 / 1728
memory_use:          7680 / 7680
response_pairs:     24720 / 24720
strategy_omission:   5568 / 5568
strategy_use:        5568 / 5568
```

`judging_summary.json`：

```text
status: COMPLETE
all validations ok: true
```

attestation：

```text
stage: full_judging
status: ATTESTED
attestation_sha256: 3e77d1bf42f184f99acdbaa625ce67195c4a34c2ee9649e4af69b6fef420e32c
judge_protocol_sha256: 6f6304c88b69547b97c13947dd87da86addee4f590616ff1947957aacb85458e
```

当前 `judging.py` 没有保留 `allow_resume_hash_mismatch` 之类的绕过参数。run manifest 仍绑定原始协议 hash。

### 1.3 M2b 完整性

目录：

```text
outputs/m2b_selected_set_omission_gemini_flash_lite_v3
```

结果：

```text
memory_selected_set_omission: 7680 / 7680
status: COMPLETE
stage: m2b_selected_set_omission
attestation_sha256: 6ce02397073b9715e218a2704186167a7c9d7d063f9ced930634fc3b4adb0f51
```

M2b 已绑定 full judging attestation：

```text
full_judging_attestation_sha256: 3e77d1bf42f184f99acdbaa625ce67195c4a34c2ee9649e4af69b6fef420e32c
```

### 1.4 标签覆盖完整

当前 action-level expected keys：

```text
expected action keys: 11136
response labels missing: 0
memory misuse labels missing: 0
memory omission labels missing: 0
memory decision labels missing: 0
strategy risk labels missing: 0
strategy decision labels missing: 0
```

M2b 修复了旧 M2 中“非 M0 动作 omission 恒为 0”的问题。

### 1.5 Split 审计

User folds：

```text
card overlap: 0
state_id overlap: 0
user overlap: 0
text overlap: 36
semantic family overlap: 12
```

解释：

- user-heldout 成立；
- counterfactual siblings 没有跨 train/val；
- 当前文本在 user folds 复用，是 synthetic controlled-counterfactual 设计的一部分；
- 因此不能声称 open-domain current-text generalization，只能声称 user-heldout controlled setting。

Semantic folds：

```text
card overlap: 0
state_id overlap: 0
semantic family overlap: 0
text overlap: 0
user overlap: 16
```

解释：

- semantic-heldout 成立；
- 但用户不 heldout；
- 不能把 user-fold 与 semantic-fold 的结论混成一个泛化 claim。

### 1.6 当前 PM 内部结果

当前主要内部结果来自：

```text
outputs/internal_pm_vs_rule_ci_m2b_text_metadata_seed17.json
```

PM minus Strong Rule，state-cluster 95% CI：

```text
response_score:          +0.0336  CI [ +0.0233, +0.0443 ]
misuse_risk:             -0.0619  CI [ -0.0738, -0.0501 ]
cost:                  -120.3854  CI [ -145.33, -96.22 ]
memory_omission_risk:    +0.1458  CI [ +0.1247, +0.1672 ]
strategy_decision_risk:  +0.2208  CI [ +0.1661, +0.2766 ]
safety_risk:             +0.2445  CI [ +0.2031, +0.2859 ]
```

解释：

- 纯 PM 在 response、misuse、cost 上明显优于 strong rule；
- 纯 PM 在 omission、strategy risk、overall safety 上明显劣于 strong rule；
- 因此不能写“PM 全面跑过 strong rule”；
- 可以写成质量/成本/误用优势与 coverage/safety tradeoff。

Coverage guardrail 诊断显示：

- PM + rule memory/strategy coverage guardrail 可恢复 conservative coverage；
- 但这是 hybrid variant，不是纯 PM；
- 不能把 guardrail 结果偷换成 pure PM 结果。

## 2. 没发现的硬泄露

在当前 synthetic 主链路中，未发现以下直接泄露：

- future memory 进入当前 state；
- selected memory snippets 进入 PM 输入；
- retrieval scores 进入 PM 输入；
- generated response 进入 PM 输入；
- judge labels 进入 PM 输入；
- gold action、role card、scenario gold 进入 PM 输入；
- API key 写入配置文件。

`configs/experiment.yaml` 只包含 `api_key_env` 字段，没有明文 key。

## 3. 需要收紧的因果/输入边界

### 3.1 主模型 `text_metadata` 是干净的

`FeatureBuilder(mode="text_metadata")` 使用：

- current-session text；
- inventory availability/count/age/token metadata；
- action features；
- 不使用 catalog fingerprint；
- 不使用 actual memory snippets。

这符合“pre-evidence / content-blind metadata-aware PM”的主线。

### 3.2 `full` / `catalog_only` 不是 content-blind

`FeatureBuilder(mode="full")` 和 `catalog_only` 会使用：

- query-to-catalog similarity；
- raw source-level catalog fingerprint。

这些 fingerprint 来自 memory text 的缓存摘要，不是 retrieval snippet，也不是 judge/gold 泄露；但它们削弱“完全不看内容”的表述。

因此：

- `text_metadata` 应作为主模型；
- `full` / `catalog_only` 应作为 catalog-aware diagnostic/ablation；
- 论文不能把 full mode 称为 content-blind PM。

### 3.3 Strong Rule / guardrail 使用 catalog fingerprint

`StrongRulePolicy` 会用 current query 与 `catalog_fingerprint` 的相似度做 source selection。

这仍是 pre-evidence，因为它没有读取 actual snippets；但它是 catalog-aware。

比较时必须写清楚：

- 主 PM：text + inventory metadata；
- strong rule：catalog-aware heuristic；
- guardrail：PM + catalog-aware rule coverage。

这不是作弊，但不能说两者输入完全等价。

## 4. 当前代码风险

### P0：外部 EvoEmo 生成脚本当前不能直接确认性运行

`src/metacom_pm/evoemo.py::run_evoemo_dialogues` 当前要求：

```text
simulator_id: required
interaction_mode="fixed" 时 fixed_tracks_path required
```

但 `scripts/15_run_evoemo.py` 没有传：

```text
simulator_id
fixed_tracks_path
interaction_mode
```

结果：

- 直接运行正式 EvoEmo generation 会 TypeError 或 ValueError；
- 外部实验前必须修。

### P0：EvoEmo metrics 脚本没有强制绑定 generation attestation

`run_official_evoemo_metrics` / `run_selective_evoemo_metrics` 已支持：

```text
generation_attestation_path
expected_freeze_sha256
```

但 `scripts/16_eval_evoemo_official.py` 和 `scripts/17_eval_evoemo_selective.py` 没有传这些参数。

风险：

- 可能评分旧的 `dialogues.jsonl`；
- 可能评分不属于当前 checkpoint/selection/freeze 的 generation；
- 外部结果证明链不闭合。

外部 confirmatory 前必须修成 fail-closed：

- generation attestation 必填；
- expected freeze sha256 必须匹配；
- dialogues path 必须在 generation attestation outputs 中。

### P0：ESConv evaluation 没有 artifact attestation

`run_esconv_policy_evaluation` 会写 `summary.json`，但目前没有为 ESConv evaluation 生成 artifact attestation，也没有强制验证 `outputs/esconv_sweep/action_outcomes.jsonl` 的 sweep attestation。

风险：

- 可能拿旧 ESConv action outcomes 做 final judge；
- ESConv 结果链不能完全复现。

外部 confirmatory 前应补：

- ESConv sweep attestation；
- ESConv eval attestation；
- freeze hash binding。

### P0：目前没有 study freeze

preflight：

```text
confirmatory_ready: false
study_freeze_valid: false
```

因此现在不能运行 reportable external evaluation。

### P0：official ESConv / train-only Strategy Bank 未准备好

preflight 显示：

```text
official_esconv_and_evoemo_present: false
strategy_bank_rebuilt_and_overlap_audited: false
esconv_test_runtime_present: false
```

当前 `data/strategy/strategy_cards.jsonl` 是：

```text
status: PREBUILT_PILOT_BANK
confirmatory_overlap_check: NOT_VERIFIED_IN_PREBUILT_BANK
```

不能用于正式 ESConv/EvoEmo external claim。

### P1：M2b 在训练/选择脚本中仍是 optional

`load_memory_labels(..., m2b_path=None)` 会让非 M0 动作 omission 回到旧逻辑，即 M2 中非 M0 omission 默认为 0。

虽然当前 M2b 训练/选择时已经显式传入 `m2b_path`，但脚本层面仍允许忘传。

建议：

- V3.3 当前主线脚本应默认使用正式 M2b 路径；
- 或者在 `10_train_pm.py` / `10b_train_cv_grid.py` / `11_tune_validation.py` 中加 `--allow-no-m2b` 才能跳过；
- 否则未来很容易不小心训练出 invalid omission head。

### P1：final model 尚未按当前主线训练冻结

当前主要结果来自 CV fold checkpoints：

```text
outputs/models_cv_m2b/text_metadata_user_fold*_seed17.joblib
```

尚未发现一个清晰的：

```text
outputs/final_model/pm_final.joblib
outputs/selection.json
outputs/study_freeze.json
```

注意 `scripts/11b_train_final_pm.py` 默认 feature-mode 是 `metadata_only`，而当前主结果用的是 `text_metadata`。

正式前必须显式：

```text
--feature-mode text_metadata
--m2b-path outputs/m2b_selected_set_omission_gemini_flash_lite_v3/memory_selected_set_omission_judgments.jsonl
```

### P1：`raw_catalog_fingerprint_exposed` 报告字段有 bug

`training.py` 中：

```python
"raw_catalog_fingerprint_exposed": feature_mode == "full_fingerprint"
```

但合法 feature mode 是：

```text
full, text_only, metadata_only, catalog_only, text_metadata
```

所以即使 `feature_mode="full"`，报告也会错误显示 `false`。

这不影响当前 `text_metadata` 主结果，但会误导审计 full mode 是否暴露 fingerprint。建议修成：

```python
feature_mode in {"full", "catalog_only"}
```

### P1：文档有外部 claim 过头风险

`docs/CLAIM_BOUNDARIES_CN.md` 写：

```text
可主张：... EvoEmo 外部长期记忆迁移。
```

当前应改成：

```text
完成冻结版 EvoEmo 外部评测后，才可主张外部长期记忆迁移。
```

否则会把未完成外部实验写成已完成 claim。

### P1：GitHub 不能直接上传整个项目目录

当前目录包含大量 legacy scripts / outputs：

- V31 / V32 source；
- legacy paper artifacts；
- 旧 EvoEmo n=30；
- old RL / POMDP / distress scripts；
- old paper asset generator；
- stale models；
- historical outputs。

这不是当前主实验泄露，但会让外部审计严重混乱。

建议做一个 clean repo/package，只放：

```text
src/metacom_pm/
scripts/00-20 + 09b + 10b + 11c + 11d + 99
configs/experiment.example.yaml
docs/current protocols
tests/
data/synthetic/
data/external/evo_emo.json
data/strategy/strategy_cards.jsonl + audit, clearly marked pilot-only
outputs/full_judging_gemini_flash_lite_v3/
outputs/m2b_selected_set_omission_gemini_flash_lite_v3/
outputs/models_cv_m2b/
outputs/selection_m2b_text_metadata_fold*_seed17.json
outputs/internal/CI and guardrail diagnostic reports
```

不要公开：

```text
legacy_paper_artifacts_20260620_1358/
outputs/v31_api_full/
outputs/v32_*/
old n=30 EvoEmo outputs
old POMDP/RL/distress scripts unless moved to legacy/
raw API logs if not sanitized
personal config with actual endpoint/key values
```

## 5. 论文设计逻辑风险

### 5.1 当前内部结果不是外部结果

当前可报告为：

```text
synthetic development / internal controlled counterfactual evaluation
```

不能写：

```text
external validation completed
EvoEmo confirms long-term memory transfer
ESConv confirms response quality
```

### 5.2 Pure PM 没有全面超过 rule

当前 pure PM：

- response 更好；
- misuse 更低；
- cost 更低；
- omission 更高；
- strategy risk 更高；
- overall safety 更差。

因此论文主张应是：

> PM 学到质量/成本/误用的资源分配 tradeoff；强规则在 conservative coverage 上仍更稳。PM+coverage guardrail 是一个后续或扩展变体，可以弥补 omission/strategy safety。

不能写：

> PM 全面优于 strong rule。

### 5.3 Safety-first 不是救命万能药

Safety-first PM 诊断显示 strategy risk 可降，但 omission / overall safety 仍不如 rule。

这说明：

- omission head 不是完全没用；
- 但当前 PM 对 conservative memory coverage 的学习不如 strong rule；
- 这是一个研究发现，不是失败。

### 5.4 Guardrail 是 hybrid，不是 pure PM

Coverage guardrail 结果很有价值，但必须命名为：

```text
PM + rule coverage guardrail
```

它不是 pure PM，因此不能拿它的 safety 结果替代 pure PM。

### 5.5 不能声称 RL / POMDP

当前代码没有：

- closed-loop user state transition；
- future reward；
- off-policy RL estimator；
- learned environment；
- real user feedback；
- policy gradient / value iteration。

应继续称为：

```text
supervised pre-evidence resource allocation
```

RL / ESC-Eval / RLHF-ESC 可以写 future work 或下一篇。

## 6. 是否需要重跑 full judging

当前结论：

```text
不需要。
```

理由：

- full judging 行数完整；
- run manifest 绑定原始 judge protocol；
- artifact attestation 完整；
- M2b 是补充 selected-set omission audit，已完整绑定 full judging；
- 发现的问题主要在外部 evaluation scripts、freeze、文档 claim、final packaging，不会污染 full judging 标签本身。

需要重跑的只有以下情况：

- 修改 judge prompt/schema；
- 修改 M2b prompt/schema；
- 修改 runtime/action outcomes/pair graph；
- 换 training judge；
- 发现 full judging JSONL 被篡改或 attestation 失败。

目前没有这些情况。

## 7. GitHub / GPT5.5 审计前建议

### 7.1 先修代码 P0

1. 修 `scripts/15_run_evoemo.py`：
   - 增加 `--simulator-id`；
   - 增加 `--fixed-tracks-path`；
   - 增加固定 track 生成步骤或单独脚本；
   - confirmatory fixed mode 必须传 fixed tracks。

2. 修 `scripts/16_eval_evoemo_official.py` 和 `scripts/17_eval_evoemo_selective.py`：
   - 强制传 generation attestation；
   - 传 `expected_freeze_sha256`；
   - 确认 dialogues 是 frozen generation 产物。

3. 修 ESConv evaluation attestation：
   - `run_esconv_policy_evaluation` 输出 artifact attestation；
   - 验证 sweep action outcomes attestation。

4. 修 M2b optional 风险：
   - 当前主线默认要求 M2b；
   - 没有 M2b 时 fail closed，除非显式 debug。

5. 修 `raw_catalog_fingerprint_exposed` 字段。

6. 更新 claim docs：
   - 外部 claim 改成条件式；
   - pure PM / guardrail 结果分开。

### 7.2 再做 clean package

不要直接把整个目录推到 GitHub。建议创建：

```text
snap/metacom_v33_clean_review_package_YYYYMMDD/
```

包含当前主线文件和必要产物，并写一个 `CURRENT_ARTIFACT_INDEX.md`，明确：

- 哪些结果是 current；
- 哪些是 legacy；
- 哪些可以用于论文；
- 哪些只是 debug / pilot。

### 7.3 再交给 GPT5.5 / GitHub

推荐给 GPT5.5 的审计问题：

1. 是否还有 pre-evidence 因果边界破坏？
2. `text_metadata` PM 是否真的没有 snippet/retrieval/label leakage？
3. M2b 是否足以修复 selected-set omission？
4. PM vs rule 的 selection 是否对称、公平？
5. Guardrail 是否被正确表述为 hybrid variant？
6. 外部 ESConv/EvoEmo freeze/attestation 是否闭合？
7. 当前论文 claim 是否超过结果支持范围？

## 8. 当前可安全写进论文草稿的版本

当前最安全的内部结果表达：

> On controlled synthetic longitudinal development data, a supervised pre-evidence PM trained with blind pairwise response labels and separate memory/strategy audits improves response preference score, reduces memory misuse risk, and lowers retrieval/context cost compared with a strong catalog-aware rule policy. However, the pure PM is less conservative on omission and strategy-coverage risks. A rule-coverage guardrail restores conservative coverage but should be treated as a hybrid extension rather than the pure learned allocator.

中文：

> 在受控 synthetic longitudinal development 数据上，基于盲式 pairwise response 标签和分离式 memory/strategy audit 训练的检索前 PM，相比强 catalog-aware rule，在回复偏好分数、记忆误用风险和检索/上下文成本上更优；但 pure PM 在 omission 和 strategy coverage 风险上不如规则保守。加入 rule coverage guardrail 可以恢复保守覆盖，但这应作为 hybrid 扩展，而不是 pure PM 本体。

## 9. 当前不能写的版本

不能写：

- PM 已经通过 EvoEmo 外部长期记忆验证；
- PM 全面优于 strong rule；
- PM 提升真实用户情绪；
- PM 实现 RL / POMDP / RLHF；
- current synthetic validation 是 final test；
- Strategy Bank 已完成官方 ESConv train-only overlap audit；
- full/catalog fingerprint PM 是 content-blind。

