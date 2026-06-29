# MetaCom V3.3 Stable PM 重训与 EvoEmo Readiness 报告

## 为什么需要这一步

原冻结 PM 使用 `text_metadata` 特征，EvoEmo fixed tracks 上 1020/1020 状态触发 severe OOD。主要原因是 EvoEmo 长期历史规模大于 synthetic 训练域，例如 session index 与 memory token/count 明显更大。

本轮不重跑任何 LLM judge，也不重跑 ESConv。我们只修改 PM 的 pre-evidence feature 表达方式，并复用已有 full judging 与 M2b 标签重训。

## 修改

- 新增 `text_metadata_stable` 特征模式。
- 对 count / age / estimated tokens / session_index 使用训练域上限 cap。
- 不读取 actual memory snippets，不使用 catalog fingerprint，仍是 pre-evidence metadata + current text。
- 恢复 synthetic action sweep 当时使用的 pilot Strategy Bank 到单独路径：`data/strategy/pilot_strategy_cards_for_synthetic_sweep.jsonl`，不覆盖正式 ESConv Strategy Bank。

## 内部 validation 结果

PM stable consensus：

- response score: 0.576
- misuse risk: 0.063
- memory omission risk: 0.298
- strategy risk: 0.242
- safety risk: 0.517
- cost: 553.3

Strong rule：

- response score: 0.542
- misuse risk: 0.125
- memory omission risk: 0.152
- strategy risk: 0.022
- safety risk: 0.272
- cost: 673.7

解释：stable PM 保留了旧 PM 的主要 tradeoff：response 更高、misuse 更低、cost 更低；但 omission / strategy risk 仍弱于 strong rule。论文仍应采用 tradeoff / PM+guardrail 叙事，不应写 PM 全面优于 rule。

## Stable Freeze

- stable freeze: `outputs/study_freeze_stable.json`
- freeze sha256: `e3e0e33ce3227a3032dc7929eb6f615c42784630739c2b79351da7f4d904571f`
- checkpoint: `outputs/final_model_m2b_stable/pm_final.joblib`
- selection: `outputs/selection_stable.json`

## EvoEmo Readiness

- status: READY
- expected states: 1020
- checked states: 1020
- errors: 0
- constraint fallback used: {'False': 1020}

PM action distribution on EvoEmo fixed tracks readiness：

```json
{
  "MSE+RS": 521,
  "MPMS+RS": 165,
  "MP+RS": 128,
  "MS+RS": 72,
  "MPE+RS": 62,
  "ME+RS": 34,
  "MSE+R0": 27,
  "ME+R0": 3,
  "MPMS+R0": 3,
  "MS+R0": 2,
  "MP+R0": 2,
  "MPMSME+RS": 1
}
```

## 测试

- `pytest -q`: 50 passed.

## 下一步

现在可以用 stable freeze 跑 EvoEmo generation。建议先跑 full generation（NVIDIA 免费），再先做 pairwise-only final judging 控制成本；确认回复质量非劣后再补 memory / strategy selective audit。
