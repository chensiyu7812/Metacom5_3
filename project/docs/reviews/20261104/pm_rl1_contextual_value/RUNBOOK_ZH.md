# 接收、复算与后续复用

实际执行，均已退出0：

```bash
python project/scripts/rl1/152_ingest_contextual_value_reference.py \
  --output project/outputs/pm_rl1/contextual_value_reference_20261104_v1
python project/docs/reviews/20261104/pm_rl1_contextual_value/verify.py
```

接收脚本需要新输出目录，不覆盖旧版本。核验脚本可重新运行，只核对现有输入、原答复绑定、原记录保留及成本算术。

本次对应`pmrl1-c02-history-benefit-20261104-v1`，已回答，不再作为pending问题。完整原话及界面问题ID在`INTAKE_PRIVATE.json`。`ANSWER_REGISTRY_PRIVATE.json`为旧34条逐项保持加本次1条；`REFERENCE_INDEX.json`登记新旧来源。旧库、原问题、原分析快照保持原样。

新引用的方向为`near_equivalent_with_small_A_edge`，不是旧hard-tie或strict-preference标签。接入任何后续程序时，必须保留其类型和原文；不得仅为了适配旧枚举改成严格平局，或仅取95/90填数值奖励。A/B已绑定到完整来源、回复和实际动作，展示顺序变化不得改变这些绑定。

`VALUE_SENSITIVITY.json`把真实成本、尚未测得的收益和假设算例分开。`CHECKS.json`还核验当前全池成本小于离散U最小档差的性质；适用范围是此缓存池与确定评分终点，不能推论策略期望回报也离散。

本次没有调整评分器、奖励、成本、训练范围或baseline，也未重新发问。下一步按报告中的质量—成本分析使用此参照；本例不再作为明显资源增益正例。自然学习仍须使用反馈完整的明确范围，不把本次接收当作PPO已启动。
