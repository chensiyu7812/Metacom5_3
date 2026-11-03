# 复算与接续

不需要GPU、模型下载、凭据或网络。以下工具只分析缓存，不会调用provider或optimizer。输出目录必须是新目录；禁止覆盖已执行产物。

```bash
python project/scripts/rl1/151_analyze_real_decision_branches.py \
  --output project/outputs/pm_rl1/decision_branches_20261104_v2
python project/docs/reviews/20261104/pm_rl1_decision_branches/replay_findings.py
python project/docs/reviews/20261104/pm_rl1_decision_branches/verify.py
```

以上为实际执行命令，均已退出0，前两条的已有目录不可直接重复创建。最后一条可重新核验现有产物。重算151时指定新目录；`replay_findings.py`明确绑定v2，重算须在新版本副本中声明新输出目录，不能改写已记录版本。

主要输入：`organized_initial_training_20261103_v2`、`actual_training_feedback_20261103_v1`、`human_answer_reanalysis_20261103_v2`、`reference_guided_review_20261103_v1`。原RS库和24个train目录从原输入哈希表定位，逐项核验。没有读取封存人评或废弃合成训练目录。

`BRANCHES_PRIVATE.json`中，动作历史与实际资源集合分别保存；没有STOP时保持null。`cached_equivalent_terminal_endpoints`核对跨顺序是否已有相同资源的终点，不以未测为0。`EXACT_COST_PREFERENCES_PRIVATE.json`只适用于已缓存相同证据/回复的终点。

当前只提出`pmrl1-c02-history-benefit-20261104-v1`一个新问题；备用三情境页不作为必填。收到答复后，把原答复逐字追加到新intake产物，绑定`PRIORITY_QUESTION_PRIVATE.json`中的证据、回复、A/B映射和问题范围。先报告它改变了哪项判断；不改旧q/m，不复制到其他回复。

若只有偏好：更新排序诊断，保留数值奖励缺失。若有q/m或区间：保留原值，核对量纲和影响，按完整输入精确去重。新的人评不自动授予模型裁判全域资格，也不自动满足原487程序反馈覆盖。

下一次本地G干预可优先比较：C03同条件更换首次MS为已核实的工作边界会话；C01仅替换无来源支持的ME概括。都需要新请求/环境身份并保留旧对照，当前未派发。C01原一次ME未改变回复，故不能优先假设修正它会带来终局收益。

自然BC/PPO接续采用明确范围的反馈批次，先监督拟合，再按原16轨迹完成一次PPO更新并重采样；不把准备工作、源文修正候选或接口测试当真实学习。
