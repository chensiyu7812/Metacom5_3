# Policy Manager — PM-RL1 当前研究入口

更新：2026-10-22（Asia/Tokyo）。`Metacom5_3`是历史仓库名，方法名为Policy Manager（PM）。

**当前：P1来源/表示和P2执行器适配已完成；自动奖励仍未合格，自然任务PM强化学习更新为0，正式比较与独立终评尚未完成。** 最近严格交付诊断已收口：当前裁判试验累计307次评分/审查尝试，容量374；最后原8槽共5次尝试、3有效、2格式失败、3未派发。容量或脚本存在不表示后续实验已获运行许可。

## 先读这几处

- [2026-10-22再次复核：研究脉络、最新证据和版本状态](project/docs/pm_rl1_workspace_20261022/RESEARCH_REVIEW_ZH.md)
- [研究全景：目的、方法、数据、方案、进度和结果](project/docs/pm_rl1_workspace_20261022/RESEARCH_OVERVIEW_ZH.md)
- [当前唯一主方案](project/docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md) · [最新状态](project/docs/PM_RL1_CURRENT_STATUS.md)
- [完整研究阶段落实与待决定事项](project/docs/pm_rl1_workspace_20261022/COMPLETION_EXECUTION_ZH.md)
- [逐阶段时间线与证据](project/docs/pm_rl1_workspace_20261022/EVIDENCE_TIMELINE_ZH.md)
- [工作区与目录指南](project/docs/pm_rl1_workspace_20261022/DIRECTORY_GUIDE_ZH.md)
- [执行手册](project/docs/pm_rl1_completion_20260930_v2/runbook.md) · [执行合同](project/docs/pm_rl1_completion_20260930_v2/execution_contract.json)

本机统一入口为`/home/tokkio/PM-RL1/README.md`。 全部HOME成果实体归档在`/home/tokkio/成果归档/`，旧工作树、图稿、审计和部署资料分别分类保存；HOME阶段包旧名已收起。HOME交付已按用途和日期归档，原仓库、代码、数据、模型及实验身份保留。完整原README见[整理前快照](project/docs/pm_rl1_workspace_20261022/README.before.md)，其中多轮“当前/待批”描述是历史时点，不作为现行执行顺序。

## 研究对象与已有成果

PM-RL1研究同一轮回复前的顺序信息获取：固定候选排序，最多四次GET_RS/MP/MS/ME，随后STOP并由冻结执行器生成一条回复。策略只看公开前缀、已取正文与合法metadata；没有未来用户模拟。它是旧Paper-1的后继研究，不等于旧四个独立L2收益头。

| 环节 | 当前证据 |
|---|---|
| 环境 | 观测隔离、GET/STOP、预算/缓存/回放及有限E0学习验证 |
| P1 | 72条MP＋24条ME来源审查，角色/时间表示及新版可达计划 |
| P2 | 493条弱目标、一次三epoch LoRA、639条比较回复；保留重复键准入和跨加载复现限制 |
| P3 | 开发人评已收到，多轮裁判/关系/任务参照/反馈诊断已做；自动奖励未获资格 |
| P4—P7 | 真实BC起点、自然任务PPO、正式策略对照、独立评价和主表仍待完成 |

[P1结果](project/docs/PM_RL1_P1_REPRESENTATION_RESULTS_20261001_ZH.md) · [P2结果](project/docs/PM_RL1_P2_EXECUTOR_RESULTS_20261001_ZH.md) · [开发接收](project/docs/PM_RL1_DEVELOPMENT_CLOSEOUT_20261014_ZH.md) · [长期两阶段方向](project/docs/PM_RL1_TWO_STAGE_ROUTE_20261015_ZH.md)。NLL降低和工程测试通过不构成支持质量或RL收益证明。

## 代码、数据与原始证据

- `project/src/metacom_pm/rl1/`：当前环境、表示、执行器、测量与反馈协调。
- `project/scripts/rl1/`：分阶段入口；按冻结协议定位，不能直接把最大编号脚本当下一步。
- `project/tests/test_rl1_*.py`：当前CPU回归。
- `project/outputs/pm_rl1/`：本地原始请求、训练、模型与结果；含私人材料，通常不在公开仓库。
- `project/docs/pm_rl1_completion_20260930_v2/`：执行合同、阶段JSON、顺序和历史快照。
- `project/docs/reviews/`：可发布的结果摘要；不能代替完整本地日志。

当前代码复用了Paper-1共享来源与工具，不能为整理目录而直接移走`paper1`、旧合同或模型路径。目录和证据的细分见[工作区指南](project/docs/pm_rl1_workspace_20261022/DIRECTORY_GUIDE_ZH.md)。

## CPU检查

已有环境中按仓库现行CI范围执行：

```bash
cd project
pytest -q -m "not gpu" tests/test_paper1_*.py tests/test_rl1_*.py
python scripts/paper1/00_validate_integration_base.py
```

新环境所需依赖定义在`project/pyproject.toml`。这些命令不等于启动GPU实验、付费调用或自然任务训练；整理本身只进行路径、内容和导航校验，未重新运行研究实验。

后续版本核对实际执行了CPU回归；本机完整集成与干净检出的结果、私有产物依赖及跳过范围见[版本验证记录](project/docs/reviews/20261022/pm_rl1/VERSION_REVIEW_ZH.md)。

## 保留的历史边界

研究变更前阅读[AGENTS.md](AGENTS.md)。旧Paper-1使用公开ESConv、ESC-Eval和ES-MemEval/EvoEmo，保持官方指标、资源语义与结果锁；当前PM-RL1的q/m代理评分不能改称官方ESC-Eval结果。项目废弃的自造80/11用户纵向数据及其衍生物不用于当前研究。

[旧Paper-1执行清单](project/docs/PM_PAPER1_EXECUTION_CHECKLIST_20260903_ZH.md) · [历史发布/进展索引](project/docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md) · [2026-10-02发布说明](project/docs/PM_RL1_STAGE_PUBLICATION_20261002_ZH.md)。
