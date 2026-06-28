# MetaCom V3.3 GitHub 审查前修复报告

日期：2026-06-28  
项目目录：`/home/tokkio/esconv_experiment_bundle/policy_manager_35`

## 结论

当前代码已经修到“可以提交给外部审查者检查内部 development 链路和外部评测入口设计”的程度；但仍不能声称 confirmatory external evaluation 已完成。

本轮修复不要求重跑已经完成的 full judging，也没有修改 full judging 标签目录。已有 full judging 与 M2b 标签仍可保留使用。

## 已修复的关键风险

### 1. M2b 不再静默缺失

此前如果训练或 validation selection 没有传入 M2b，代码会静默退回到非 M0 omission=0 的旧标签口径。现在：

- `train_pm(..., require_m2b=True)` 会在缺少 M2b 时 fail closed；
- `tune_validation_policies(..., require_m2b=True)` 会在缺少 M2b 时 fail closed；
- 底层函数默认值已改为 `require_m2b=True`，因此直接调用 Python API 也默认 fail closed；
- `scripts/10_train_pm.py`、`10b_train_cv_grid.py`、`11_tune_validation.py`、`11b_train_final_pm.py` 默认使用当前完整 M2b 标签；
- 只有显式 `--allow-no-m2b` 才允许非报告性 debug 退化。

新增测试：`tests/test_m2b_fail_closed.py`。

### 2. Validation selection 增加 provenance 与 attestation

`tune_validation_policies` 现在会验证并记录：

- synthetic action sweep attestation；
- full judging attestation；
- M2b attestation；
- checkpoint training attestation；
- runtime / outcomes / checkpoint / strategy bank SHA256。

selection 输出旁边会生成 `*.attestation.json`，stage 为 `validation_selection`。

已用 fold0 离线验证：

- 输入：`outputs/models_cv_m2b/text_metadata_user_fold0_seed17.joblib`
- M2b：`outputs/m2b_selected_set_omission_gemini_flash_lite_v3/memory_selected_set_omission_judgments.jsonl`
- selection attestation 自检通过。

### 3. EvoEmo fixed-input 外部评测链路补齐

新增脚本：

- `scripts/15a_build_evoemo_fixed_tracks.py`

正式 EvoEmo 现在推荐顺序：

1. 先生成 policy-independent fixed seeker tracks；
2. fixed tracks 生成 artifact attestation；
3. `scripts/20_freeze_study.py` 把 fixed tracks 和 attestation 一起锁进 study freeze；
4. `scripts/15_run_evoemo.py` 默认以 fixed mode 重放这些 tracks；
5. EvoEmo generation attestation 会绑定 fixed tracks attestation；
6. `scripts/16_eval_evoemo_official.py` 与 `17_eval_evoemo_selective.py` 必须验证 generation attestation。

这避免了“不同 policy 造成不同 seeker 世界线”的闭环混淆。

### 4. ESConv evaluation attestation 链路补齐

`run_action_sweep` 支持可选 `study_freeze_sha256`，但不传时不改变旧 synthetic manifest，避免破坏既有 full judging。

`scripts/13_run_esconv_sweep.py` 在正式 freeze 后会把 freeze hash 写进 sweep attestation。

`scripts/14_eval_esconv.py` 和 `run_esconv_policy_evaluation` 现在会：

- 验证 ESConv action sweep attestation；
- 确认所有 PM-vs-baseline response pairs 完整；
- 生成 `esconv_policy_evaluation` attestation。

### 5. 主张边界文档收紧

`docs/CLAIM_BOUNDARIES_CN.md` 已改为条件式：

- internal development 可报告 synthetic 上的 trade-off；
- ESConv / EvoEmo 只有在冻结外部实验完整跑通后才可作为外部主张。

`docs/RUNBOOK_CN.md` 与 `README_CN.md` 已同步 M2b、fixed tracks 和 attestation 要求。

### 6. Catalog fingerprint 表述修正

训练报告与 policy decision report 不再引用不存在的 `full_fingerprint` mode。现在：

- `text_metadata` 是主模型，不读 catalog fingerprint；
- `full` / `catalog_only` 被标记为 catalog-fingerprint-aware diagnostic modes；
- 论文主张应写成主模型 `text_metadata`，不要把 fingerprint-aware ablation 当主结果。

## 验证结果

### Python 编译

已对修改涉及的核心文件与脚本运行 `py_compile`，无错误。

### 单元测试

命令：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python -m pytest -q
```

结果：

```text
46 passed
```

### Release preflight

命令：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/99_release_preflight.py \
  --out release_preflight_after_github_ready_fixes_with_tests.json
```

结果：

- `status`: `API_PILOT_READY`
- `confirmatory_ready`: `false`
- `pytest`: passed
- `python_syntax`: passed
- `static_leakage_scan`: passed
- `synthetic_data_audit`: passed
- `pair_graph_audit`: passed

`confirmatory_ready=false` 是预期结果，因为当前还未完成：

- official ESConv 导入/重建 Strategy Bank；
- overlap-audited confirmatory Strategy Bank；
- ESConv test runtime；
- study freeze；
- final external generation/evaluation。

## 仍需审查者重点检查的边界

1. 当前 internal result 是 development evidence，不是 final external evidence。
2. PM 不是 RL/POMDP/RLHF，不应按 RL 论文主张写。
3. Pure PM 在 internal validation 上赢 response/misuse/cost，但输 omission/strategy risk；论文应写 trade-off，不写全面优于 rule。
4. Guardrail/hybrid policy 是诊断或后续变体，不应混成 pure PM 主结果。
5. EvoEmo external 在代码链路上已补齐 fixed-input 设计，但尚未实际完整跑通。
6. Study freeze 尚未创建；GitHub 审查可检查设计和代码，但不能把当前状态写成 confirmatory ready。
