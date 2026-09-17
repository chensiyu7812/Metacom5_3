# Policy Manager Paper 1 官方 ESC-Eval 兼容性修订（2026-09-02）

状态：`ACTIVE / RESEARCHER-AUTHORIZED SCOPED PRE-OUTCOME AMENDMENT`

机器合同：`project/data/paper1_authority/paper1_official_esc_eval_compatibility_amendment_20260902_v1.json`

## 1. 修订原因与时点

研究者于 2026-09-02 明确要求 Paper-1 的能力结论必须与整个研究主张一致，并由 prior-work 官方 evaluator 支撑。此时四把 outcome lock 均为 `CLOSED`，formal ESC-Eval、formal outcome 与 PM training 均为 0。

2026-09-01 的 A6000 runtime qualification 成功加载固定 InternLM2-chat-7B 与七个 ESC-RANK English adapters，完成 42 次真实推理；峰值 allocated VRAM 约 14.81 GiB，七维均值约 4.81 秒，原始输出在重复间 byte-exact 一致。该 run 唯一的 `BLOCKED` 原因是项目自加的 `^[0-4]$` full-string parser 对官方 adapter 的稳定 labelled-sentence 输出解析为 0/42。

固定 ESC-Eval commit `9ad46e7b5e247e824dae4633910eaa82be668beb` 的 `score.py`（SHA-256 `1d775462adc7687d84ceb19d3648c3c917abf7ceed8b052b1fed8e4740f12724`）并不要求整串纯数字。官方语义是按 `label_list=["0","1","2","3","4"]` 顺序，返回第一个作为字符出现在 raw response 中的 label；若均未出现则写 `-1`。

继续用项目自设 full-string parser 作为主判定会把一个可运行的官方 evaluator 人为判为不可用，并偏离 `PM_PAPER1_OFFICIAL_EVALUATION_PRIORITY_20260816_ZH.md`。因此本修订发生在任何正式 outcome 之前，属于官方兼容性纠正，不是看过 PM 或 benchmark 结果后的调分。

## 2. 精确覆盖范围

本修订只覆盖：

1. ESC-RANK runtime qualification 的主 parser；
2. parser 有效率与重复性 readiness gate；
3. evaluator qualification 中“候选 winner”不得取代 RQ1 官方主 scorer 的解释。

本修订不改变 rubric、prompt、base model、七维 adapter 映射、0–4 scale、greedy decoding、公开数据边界、Generator、实验 arms、ESC split、RQ2 folds、PM learner、训练 label、Cost 地位或论文主张。

## 3. 主 parser 与诊断 parser

主 parser 必须逐字复现固定官方 `score.py`：

```text
for label in ["0", "1", "2", "3", "4"]:
    if label in raw_response:
        return int(label)
return INVALID  # upstream writes -1
```

项目不得为了提高表面 robustness 改成 first-occurring digit、regex 抽取、adapter-specific 句式或“多数字冲突即 invalid”并仍称其为官方主 parser。多 label、full-string ordinal、raw response form 可以并且必须作为 supplemental diagnostics 记录，但不得覆盖官方主分数。

每条 trace 至少保存：raw output、official parsed ordinal、official validity、official label hits、multiple-label diagnostic、strict-full-string diagnostic、prompt hash、adapter、latency。

runtime `READY` 要求：42/42 official parse valid、同 item/dimension 的 official vector 在两次重复间一致、raw output 在两次重复间一致、模型/adapter/代码身份与显存门槛通过。strict diagnostic 不构成 readiness gate。

## 4. 七维身份与正式评价地位

固定映射为：

- `fluency` -> Fluency；
- `diversity` -> Expression；
- `empathic` -> Empathy；
- `suggestion` -> Information；
- `human` -> Humanoid；
- `tech` -> Skillful；
- `overall` -> Overall。

正式 RQ1 主结果只能使用固定官方 ESC-Eval/ESC-RANK 七维与客观 Cost。Qwen、DeepSeek 和研究者指定的独立模型家族仍按 2026-08-20 consolidation 参加相同 24-item 双盲人类 reference 的 validity/agreement/bias/cost qualification，但角色是 supplemental qualification/sensitivity；无论其人类一致性如何，均不得静默取代 RQ1 主表中的官方 scorer。

如果官方 ESC-RANK 与人类 reference 一致性有限，必须在主结果旁如实报告 reliability/bias sensitivity；不得通过选择更有利于 PM/Ours 的替代 judge 修复论文结论。

## 5. 失效、保留与重跑

失效：

- 2026-09-01 基于 full-string parser 的 runtime `BLOCKED` 解释；
- 旧 patch manifest v1 中把项目自设 parser 语义列为不可变主门禁的部分；
- 任何把 general judge winner 解释为可替代官方 RQ1 scorer 的文字。

保留：

- 原始 42 条 GPU 输出及其 hash；
- 模型、adapter、ESC-Eval commit、`score.py`、环境与资产 attestation；
- 24-item 双人 blind reference 及 Humanoid/Skillful 机械 normalization；
- splits、catalog、BGE ranking、memory artifacts 与全部零 outcome 证据。

必须重跑：

1. 同一 3-dialogue × 2-repeat × 7-dimension runtime qualification；
2. 通过后，对冻结 24-item blind set 运行官方 ESC-RANK，并分别对 RATER_A/RATER_B 报告 QWK、Spearman、MAD、pairwise consistency、bias、latency 与 GPU cost；
3. authority、parser、harness、asset 和 integration tests。

## 6. 停止边界

本修订只授权 zero-outcome evaluator qualification。四把 outcome lock 继续 `CLOSED`；不授权正式 ESC-Eval calibration/confirmatory、Generator PM arms、ES-MemEval outcome、effect construction 或 PM training。资格证据完成后仍按 consolidation 顺序推进，不得越级。
