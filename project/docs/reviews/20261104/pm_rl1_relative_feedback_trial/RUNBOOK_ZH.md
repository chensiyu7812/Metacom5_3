# 本轮复核入口

在仓库根目录执行。以下复核只用CPU，不生成文本、不评分、不重训：

```bash
env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python project/docs/reviews/20261104/pm_rl1_relative_feedback_trial/verify.py
env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=project/src /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -q project/tests/test_rl1_relative_diagnostic.py
```

实测核验退出0；6项测试通过、退出0。核验读取原始ON/OFF评分输入、自然回复和公共BGE状态，确认限定树STOP闭合，重新计算17条成本，加载3个最终模型确认参数与记录一致，并复核原裁判响应/执行脚本快照/人评期望和预算账本未改。

代码入口：

- `project/scripts/rl1/158_try_relative_feedback.py`：有界本地相对裁判准备、执行、收口。已有目录含加载启动记录，禁止无声重跑；原执行脚本在产物目录归档。
- `project/scripts/rl1/159_bounded_real_diagnostic.py`：成本、真实状态、引用规范化和限定BC/PPO。一般相对反馈本次已停止，无训练。
- `project/scripts/rl1/160_run_exact_equivalence_control.py`：相同评分输入负对照的独立作用域，已完成prepare/states/run，不要对原目录重训。
- `project/src/metacom_pm/rl1/reusable_latency.py`：可跨策略参数更新的成本环境；不同部署须重新核验，未测方法开销不能借用。
- `project/src/metacom_pm/rl1/relative_diagnostic.py`：相对判断与AB交换一致性，缺失/不确定继续为null。

本轮训练CPU环境如上；状态构建沿用原本地tokenizer环境和真实编码缓存。唯一一次裁判GPU执行使用既有Qwen3.5-9B及 `paper1-judges-py312` 环境、原A6000/CVD1守卫、完整原生上下文与自然EOS；180秒技术超时单列。没有模型/API备选派发或环境包安装。

报告中的时间误差、策略期望及资金状态可直接从核验JSON复算。短路径误差敏感性是事后分析，没有借此挑选模型或重训。5个情境都是训练内且按回复相等后选，不应当作独立测试集或全研究效果。
