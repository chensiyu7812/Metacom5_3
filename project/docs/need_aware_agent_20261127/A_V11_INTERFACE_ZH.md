# A → B v1.1 接口与复现命令

共同 HEAD：`51b385b8bd57d60a133206c36003ea1b33a1e8bf`。A 工作目录 `/opt/tokkio-data0/tokkio_projects/Metacom5_3-naa-v11-data/project`。不重复合并旧 A/B，不覆盖旧树。以下命令均为 CPU；目标输出必须不存在，重跑使用新目录，不能覆盖冻结材料。

```bash
export PYTHONPATH=src
N=/opt/tokkio-data0/naa/20261128/a_v11
R=/opt/tokkio-data0/naa/20261127
P=$R/venv/bin/python

$P scripts/need_aware/prepare_v11.py allocate --source "$R/source" --old "$R/artifacts" --scored "$R/evaluation_wp2/automatic-v2-terminal-final/scored" --out /new/path/ALLOCATION.json
$P scripts/need_aware/prepare_v11.py materialize --source "$R/source" --old "$R/artifacts" --allocation "$N/ALLOCATION.json" --out /new/path/wp3
$P scripts/need_aware/review_v11_wp2.py --old "$R/artifacts" --scored "$R/evaluation_wp2/automatic-v2-terminal-final/scored" --allocation "$N/ALLOCATION.json" --out /new/path/review
$P scripts/need_aware/finalize_wp2_review.py --packets "$N/wp2_review/PACKETS.private.jsonl" --notes "$N/wp2_review/SOURCE_NOTES.private.jsonl" --out /new/path/annotations

$P scripts/need_aware/prepare_wp4.py --old "$R/artifacts" --source "$R/source" --allocation "$N/ALLOCATION.json" --prefeval "$R/upstream/PrefEval" --prefeval-exposed "$R/prefeval/runtime/tasks.generation.jsonl" --out /new/path/wp4
$P scripts/need_aware/freeze_v11_rules.py --wp3 "$N/wp3" --wp4 "$N/wp4-final" --old "$R/artifacts" --out /new/path/rules

CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python scripts/need_aware/cpu_wp4_batch.py --targets "$N/wp4-final/targets/fit.jsonl" --tokenizer /opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b --out /new/path/CPU_BATCH.json
$P scripts/need_aware/validate_v11_real.py --old "$R/artifacts" --source "$R/source" --prefeval "$R/upstream/PrefEval" --new "$N" --out /new/path/CPU_RECEIPT.json
$P scripts/need_aware/create_v11_candidate.py --root "$N" --out /new/path/candidate

CUDA_VISIBLE_DEVICES= /opt/tokkio-data0/tokkio_envs/naa-cpu-py311/bin/python -m pytest -q tests/test_need_aware_*.py
```

`allocate` 仅旧 C 错题审查按结果选题；确认、训练分组和开放任务只按固定 hash。`materialize` 保持旧 bridge 任务、答案、选项顺序和历史完全一致。新确认 140 题选项一次生成后冻结。源历史缺失 payload 的唯一归一化见 `wp3/normalizations.json`。

## WP3 runtime / evaluation

`RuntimeTask` / `EvidenceRecord` 无 schema 变更。B 读取 `wp3/runtime/tasks.mcq.jsonl` 及同 root 的历史，C/C+noise 才能读 `wp3/direct/direct.jsonl`。其余检索/Writer 不得读取选项或 evaluation。Gemma 固定 ID 在 `wp3/selection.json`；旧 bridge 位于 `wp3/bridge`。C+noise 原 Direct 完整保留，背景选择不能看答案；`HistoryResolver.resolve_direct(..., 'C')` 可用于两个 Direct 诊断臂，运行臂身份仍保留 C+noise。

共享提示模块 `metacom_pm.need_aware.data.short_protocol` 只有无 gold 的协议文本、64 token 上限及 instruction。保留题面和共同 recall 语义；替换旧要求长推理/字面括号的选择题尾指令。WP3 是 modified 协议，不回改 WP2。

每个 B request index 增加：

- `scoring_protocol: naa-short-mcq-v1`；`task_sha256: digest(RuntimeTask.to_dict())`；`decode.max_new_tokens: 64`。
- 原 `logical_id/task_id/arm/model_label/model_id/persona_group/request_sha256/status` 契约不变；C/C+noise 缺失时 hash=null。
- 结构性 `structural_reason=direct_unlocated` 或 `direct_over_cap`。后者须给 `full_direct_tokens` 和 `input_cap` 的 native 证明，不截断 Direct。
- 非 Direct 容量失败保留计划可评价分母，按技术 `capacity_exceeded` 导出，含原 `capacity` receipt；不能冒充结构缺失。

每个 cell 导出全部冻结位置。沿用 WP2 `result_kind/run_id/attempt_count/failure_kind/finish_reason/output/reused_exact`，失败输出为空；超时、运行错误、中断、未尝试分别记录。A 负责严格评分：

```bash
$P scripts/need_aware/score_wp3.py --runtime "$N/wp3/runtime/tasks.mcq.jsonl" --evaluation "$N/wp3/evaluation/tasks.mcq.jsonl" --requests /B/requests.index.jsonl --predictions /B/Qwen35.B0.jsonl --model Qwen35 --arm B0 --out /new/path/scored-B0
$P scripts/need_aware/aggregate_wp3.py --cells /B/scored-cell-paths.json --policy "$N/rules-final/WP3_POLICY.json" --wp3 "$N/wp3" --out /new/path/aggregate.json
$P scripts/need_aware/compare_wp3_bridge.py --old-scored "$R/evaluation_wp2/automatic-v2-terminal-final/scored" --new-cells /B/bridge-scored-cell-paths.json --wp3 "$N/wp3" --policy "$N/rules-final/WP3_POLICY.json" --out /new/path/bridge.json
```

`scored-cell-paths.json` 键为 `Qwen35|B0` 等七个 Qwen cell 和 `G0e|B0/E0s/C` 三个 cell，值为私有 scored JSONL。Gemma 单 cell 评分用 `--task-ids` 指定冻结 ID 列表；不得自行挑已答对/已完成子集。桥接的四个新 cell 与旧 B/C 原分数相配，不混合协议。

## WP4 训练与开放

只用 `wp4-final/targets/{fit,tune,development}.jsonl`，训练禁止读 development；运行只读 `runtime/*.jsonl` 的 `messages`。来源审核、行为标签、目标和 rejected 字段均不进模型输入。PrefEval explicit 的用户可见偏好本身是合法历史，不是 PersonaMem 的隐藏偏好字段。

行包含 `group_id/variant_id/split/source_family/owner_id/construction/messages/target_text/action_target/acceptable_actions/rejected_action/pair_loss_mask/source_refs/evidence_sha256/annotation`。`rejected_text` 为 null，**不训练整句替代回复负例**。同组来源保持一致；真实撤回内容只留离线 provenance，运行侧只有无内容 tombstone。

B 可直接导入 `data.training_objective.encode_target`、`masked_action_logp`、`objective`。编码使用本机原生 chat template、关闭 thinking、完整保留目标，超过 2048 则报错，不静默截断。传入逐例 SFT loss、chosen/rejected 行为 token 平均 logp 和 mask。U2 与 U3 都执行相同三个 forward/backward 分支，U2 辅助项系数 0；不得省掉它们后仍声称算力匹配。组顺序固定 hash，组内全部变体保留，两个方法顺序相同。B 必须记录辅助计算开销、有效 target tokens、step、load/save/teardown 时间。

`TRAINING_CANDIDATE.json` 提供固定 base/revision、数据 hash、LoRA r8/alpha16、q_proj/v_proj、lr2e-4、1 epoch、microbatch1、accum8、465 个计划 optimizer steps（上限500）、seed 和同数据对照。**这是候选接口，不是已执行训练后端或 GPU 授权**；B 须核对真实模块、栈兼容、显存及时间，独立校准尚未完成。

开放构造开发材料为 `rules-final/open/runtime.jsonl` / `targets.private.jsonl`，60 组180变体；自然60任务由 `natural60.json` 引用原冻结文件。U0/U1/U2/U3使用相同合法证据、输入长度、输出 JSON 格式和停止条件；只向产品展示 `response`。U1规则出处/实现归 B。自然任务移除强制回忆后必须所有 U 臂一致，并作为 modified 开放协议单报。

构造任务 request 使用 `runtime_sha256=digest(runtime_projection(target_row))`，沿用 logical/model/request/run/attempt/status 身份。评审行使用 `variant_id/rater_id/rubric/output_sha256` 和六个维度，输出 hash 为 `digest(output_string)`。评审身份与盲映射本地保管，不公开。调用：

```bash
$P scripts/need_aware/score_wp4_open.py --targets "$N/rules-final/open/targets.private.jsonl" --requests /B/U0.requests.jsonl --predictions /B/U0.predictions.jsonl --ratings /private/two-raters.jsonl --method U0 --model Qwen35 --out /new/path/open-scored
```

无 ratings 时只统计技术/格式/action，不产生语义成功分数。自然60的 rubric 要逐题来源审阅，不能套用 constructed 的单一行为目标。100 条校准包已存在 `wp4-final/calibration/`，不是已经做完的人评。

## 联合候选边界

`joint-final/WP3_SLOTS.private.jsonl` 是实际 1,400 个任务绑定槽位，`CANDIDATE.json` 绑定全部数据/规则/native CPU batch hash。建议上限分列 WP3 57,600s、U0/U1开放14,400s、U2/U3训练各14,400s、训练后开放14,400s，总115,200s；推理物理尝试上限2,500，含重试。**这些是 A 的新候选上限，不是旧16小时授权的延用，也不是已测耗时或 B 已签收预算。**

交 B 补齐实际 native request manifest、U1/训练后端、加载/关闭余量和资源估计后，合成一份可执行申请。A 不重复占 GPU，不把缺少 B 执行实物包装成“联合完成”。长任务由程序自行落终态文件，不用 AI 轮询等待。
