# PM-RL1 开发结案与验收接口（2026-10-14）

本轮完成开发16题的派生接收、原始裁判理由审计和后续验收接口。**真实裁判仍未取得奖励资格；候选修订未启用，真实封存24对未开封，自然PPO未运行。**

接续基线是 `work/paper1-rq1-integration-20260816`，HEAD `0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28`，开始时工作区干净。此前本地审计结果保留。本轮全部代码为新增文件，旧评分器、环境、奖励及原始答案没有改动。控制合同仍是 `pm_rl1_completion_20260930_v2/execution_contract.json` 和 `PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md` 第8节。

| 阶段 | 已有证据／本轮增量 | 尚不能声称 |
|---|---|---|
| 环境／PPO工程 | 已有环境与工程测试；本轮补冻结资格约束下的自然任务协调接口及零模型冒烟 | 自然任务PPO已训练或获益 |
| P1/P2 | 已有来源表示、冻结执行器和共同回复池，本轮保留其身份 | 所有新探索回复已有可靠终值 |
| 开发人评 | 16题都有实质备注；15题明确偏好、1题明确无法判断；Du是派生记录 | 两套独立评审、一致性统计或80个样本 |
| 裁判 | 32个开发主评分及1个既有重检探针逐一核对请求、原始输出、解析结果、版本 | 结构有效等于语义正确或奖励合格 |
| 验收接口 | 冻结→选择性接收→24对/12复评→原资格算术；未知、技术失败、来源和版本守卫 | 真实24对或12次复评已经通过 |

保留固定候选库存、四类GET与STOP、最多4次获取、只看已取正文、STOP后冻结执行器生成。没有未来用户模拟、联合训练、删除、重查或新模型竞赛。128/384仍由合同的低对比度状态与完整引擎小时投影决定。

代码入口：

- `scripts/rl1/106_close_p3_development.py`：从已经打开的开发记录重建派生接收与原始评分审计，不触碰真实密文。
- `scripts/rl1/107_p3_acceptance_workflow.py`：draft、freeze、receive、import-scores、qualify、batch-plan；输出新建，阶段分开。
- `scripts/rl1/108_run_p3_acceptance_batch.py`：显式选择候选后绑定新runtime；默认run只离线核对，必须加`--execute-local`才加载模型。新运行不冒用98的旧runtime。
- `calibration_intake.py`：逐字段保留原值、原备注、引文来源、未知及Du来源。
- `calibration_workflow.py`：冻结和题目/回复/来源/运行绑定；复用`calibration_decision.decide`的既定门槛。
- `natural_runner.py`：策略只收到Observation；GET无模型调用，STOP等待绑定的生成/测量，未知或失败没有终值。
- `judge_completion_candidate.py`：**仅提议的一次语义修订**，不替换默认模块；q/m、公式及解析规则不变。

建议使用合同允许的一次开发后语义修订，具体差异见本地报告和候选diff。依据是q尺度应用不一致、主体归因与引文错误、将可选探索误判为施压；不是要求裁判逐题迎合人工偏好。当前P3实际应用修订计数仍为0；既有重检探针、先前建议及本轮候选文件不计为已应用。采用候选后须重评开发回复并复核，再冻结；不能用开发重评证明独立可靠性。

单人有限校准是原计划第8.3/8.4节已有路线，可采用Chen原始观察。开发风险保留22侧none_detected、1侧local、3侧severe、6侧未知；事实指认与严重程度分开，不以“相当”证明无误、不以“不自然”推断风险。没有必须重填整套题包的要求。

本地交付根目录：`project/outputs/pm_rl1/development_closeout_20261014_v1/`。`CURRENT.json`指向最终派生结果`acceptance_final/`；完整中文报告、逐项CSV、原始理由、候选diff、下一次运行清单、成本估算和测试回执均在此目录。含私人标注的输出继续留在本地忽略目录，没有提交或上传。

离线回归：

```bash
cd /home/tokkio/Metacom5_3/project
PYTHONPATH=src PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES='' \
  /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  tests/test_rl1_calibration_workflow.py tests/test_rl1_human_calibration.py \
  tests/test_rl1_calibration_decision.py tests/test_rl1_completion_judge.py \
  tests/test_rl1_environment.py
```

新后端的真实GPU加载、vLLM兼容性和新版裁判语义效果没有在本轮实跑。技术恢复的导入保留首试分母；驱动不自动重试或选分。真实运行遇到技术失败、语义不确定、尚缺人类事实确认或预算余量不足时保存并停止受影响阶段，不假称资格通过。
