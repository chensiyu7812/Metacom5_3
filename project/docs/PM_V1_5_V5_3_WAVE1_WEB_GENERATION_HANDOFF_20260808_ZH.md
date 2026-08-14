# PM V1.5 V5.3 Wave 1 网页端生成交接

日期：2026-08-08

## 两阶段范围

### Wave 1A：只生成两个 canary

1. ChatGPT：`p2r_formal_gpt_u010`，family caregiving，13 sessions；
2. Claude：`p2r_formal_claude_u005`，relationships，15 sessions。

只有两人均满足下列条件，才进入 Wave 1B：

- 单用户正式 V2 validator 为 `MACHINE_PASS_BATCH_AND_SEMANTIC_REVIEW_PENDING`；
- hard issue = 0；
- 两人合并后 preference quota 仍可达；
- exact/normalized overlap 审计没有阻断；
- 集中语义复核确认人物、时间线、行动—结果、未解决事件和背景事件没有串号。

### Wave 1B：再生成其余十一人

分配已冻结在 `v5_3_wave1b_scale_assignments_v1.json`。Wave 1A 未通过前不开始。

## 网页端逐用户工作流

每次只处理一位用户，不在同一个网页输出里连续生成多人。

1. 把对应的 `01_world_prompt.txt` 作为新会话首条任务交给网页模型；保存模型返回的唯一 JSON 对象为 `world.json`。
2. 使用脚本 95 对 `world.json` 做结构预检并生成三个 chunk prompt。
3. 在同一网页会话依次提交三个 chunk prompt；每次只保存返回的唯一 JSON 对象。
4. 使用脚本 96 确定性拼装四个文件并运行正式 V2 validator。
5. 机器通过不等于最终入库；两位 canary 完成后统一做 batch/overlap/semantic review。

生成 world prompt：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
/home/tokkio/snap/metacom_v33_pm_v1_5_repair/.venv-pm-v1-5/bin/python \
scripts/v1_5/95l_materialize_v5_3_wave1_web_prompts_v1_5.py \
  --user-id p2r_formal_gpt_u010
```

拿到并保存 `world.json` 后生成三个 chunk prompt：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
/home/tokkio/snap/metacom_v33_pm_v1_5_repair/.venv-pm-v1-5/bin/python \
scripts/v1_5/95l_materialize_v5_3_wave1_web_prompts_v1_5.py \
  --user-id p2r_formal_gpt_u010 \
  --world-json /绝对路径/world.json
```

拼装并验收：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
/home/tokkio/snap/metacom_v33_pm_v1_5_repair/.venv-pm-v1-5/bin/python \
scripts/v1_5/96l_assemble_validate_v5_3_wave1_web_user_v1_5.py \
  --user-id p2r_formal_gpt_u010 \
  --world /绝对路径/world.json \
  --chunk /绝对路径/chunk1.json \
  --chunk /绝对路径/chunk2.json \
  --chunk /绝对路径/chunk3.json
```

Claude canary 只需把三条命令中的 user ID 换成 `p2r_formal_claude_u005`。

## 已完成的方案验证

使用现有正式通过的 GPT 13-session 用户与 Claude 15-session 用户做了零 API 往返：

`canonical user → world + 3 chunks → deterministic assembler → official V2 validator`

结果：两人均通过，hard issue 总数 0，profile/preference/relationship/event/session/candidate ID inventory 无丢失。这证明分段协议、拼装器和正式 validator 可以闭环。

它不证明网页模型首稿必然通过。真实产出若不通过，应报告具体 validator issue；不得悄悄改合同、删候选或把 construction condition 当标签。允许让网页模型按明确 issue 修正该用户草稿，但必须保留版本与修正记录。
