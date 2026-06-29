# MetaCom V3.3 EvoEmo PM Readiness Check

本检查不调用任何 API，只验证冻结 PM 能否在 EvoEmo fixed tracks 的真实外部状态上完成 pre-evidence 决策。

## 结果

- 状态：BLOCKED
- 期望检查状态数：1020
- 成功检查状态数：0
- 错误数：1020
- freeze sha256：`0e6cb4e2c84da57532d04bb98bf23379acd70c9d00014ee18b96a99666d28798`

## 解释

当前冻结 PM 在 EvoEmo fixed tracks 上全部触发 severe OOD，正式 `scripts/15_run_evoemo.py` 会在生成 API 调用前 fail-closed。

主要原因不是泄露或脚本崩坏，而是外部 EvoEmo 的长期历史规模明显超过 synthetic 训练分布。例如首个样本已经出现 `session_index=33`、ME 目录约 9935 tokens，而当前 PM 的训练安全域来自较短 synthetic longitudinal states。

## 结论

不能直接用当前冻结 PM 跑 confirmatory EvoEmo PM 外部实验。可继续跑非 PM baselines / fixed policies，但不能声称这是 PM 的外部验证。

合理下一步有三条：

1. 训练一个外部兼容的 PM 特征版本，例如 capped/log-normalized inventory metadata，并在 development validation 重新选择阈值。这个不需要重跑 full judging，但需要重新训练、重新 freeze。
2. 将 EvoEmo 当前轮只作为 baseline / rule / fixed diagnostic，不报告 PM 主张。
3. 扩展 synthetic development 的 memory inventory 范围到 EvoEmo 规模，再重新 sweep/judge/train。这最干净但最贵最慢。

## 首个错误样例

```text
RuntimeError: PM input is outside the validated pre-evidence feature domain; use a preregistered OOD baseline or retrain on a matched longitudinal development set. report={'n_rows': 16, 'n_dimensions': 28, 'outside_value_fraction': 0.44642857142857145, 'rows_with_any_outside_fraction': 1.0, 'outside_dimensions': 15, 'scalar_outside_fraction': 0.07142857142857142, 'catalog_outside_fraction': 0.0, 'max_outside_margin': 5.375278407684165, 'severe_scalar_ood': True, 'severe_catalog_ood': False, 'recommendation': 'ABORT_OR_USE_OOD_BASELINE'}
```
