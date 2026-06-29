# MetaCom V3.3 EvoEmo Selective Generation 完成说明

更新时间：2026-06-29

## 结论

EvoEmo / ES-MemEval-style fixed-input selective generation 已完成。

- 输出目录：`project/outputs/evoemo_selective/`
- 状态：`COMPLETE`
- expected dialogues：816
- completed dialogues：816
- expected turns：8160
- completed turns：8160
- failures：0
- malformed：0
- OOD preflight：ok
- artifact attestation：已生成

## 条件

本轮 generation 使用 8 个条件：

- `no_memory_r0`
- `no_memory_rs`
- `session_rag_rs`
- `full_history_rs`
- `all_structured_rs`
- `best_fixed`
- `strong_rule`
- `pm`

设计为：

```text
34 scenarios × 3 seeds × 8 conditions = 816 dialogues
816 dialogues × 10 turns = 8160 turns
```

## 绑定 artifact

本轮 generation 绑定：

- freeze：`project/outputs/study_freeze_stable.json`
- checkpoint：`project/outputs/final_model_m2b_stable/pm_final.joblib`
- selection：`project/outputs/selection_stable.json`
- fixed tracks：`project/outputs/evoemo_fixed_tracks/fixed_seeker_tracks.jsonl`

`artifact_attestation.json` 记录了完整生成文件的 SHA256 与行数。

## Review 包说明

为避免 GitHub review 仓库体积过大，本包没有包含以下大文件正文：

- `dialogues.jsonl`，约 227 MB；
- `turns.jsonl`，约 199 MB；
- `raw_api_calls.jsonl`，约 19 MB。

这些文件的路径、大小、行数与 SHA256 已写入：

- `project/outputs/evoemo_selective/artifact_attestation.json`

如果需要复核正文，可在原始实验机目录读取：

```text
/home/tokkio/esconv_experiment_bundle/policy_manager_35/outputs/evoemo_selective/
```

## 下一步

下一步不再是 generation，而是评价：

1. EvoEmo pairwise-only response quality evaluation；
2. 若质量非劣或更好，再跑 selective memory / strategy audit；
3. 最后更新论文主表和 claim boundary。

