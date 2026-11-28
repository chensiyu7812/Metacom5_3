# Policy Manager / Need-Aware Agent — 当前研究入口（2026-11-28，v1.1）

**研究名称与原三个RQ不变。** 本分支沿用NAA（Need-Aware Agent），服务长期陪伴数字人的用户理解、需求感知及自适应帮助。WP2真实开发实验已收口；下一步WP3复用GE2建立强原文供给基线，一次修复、不开展独立RAG优化课题；WP4核心是同证据下的目标条件化适用性与实际回复行为，允许经过数据支持的Generator适配。RS/Support Skills及长期状态维护等仍为总体系统资产。参见 [现行唯一主方案 v1.1](project/docs/need_aware_agent_20261127/MASTER_PLAN_ZH.md)、[本轮A/B实施任务](project/docs/need_aware_agent_20261127/WORK_ORDERS_ZH.md)、[AGENTS.md](AGENTS.md)。WP2真实交付：[A PR30](https://github.com/chensiyu7812/Metacom5_3/pull/30)、[B PR31](https://github.com/chensiyu7812/Metacom5_3/pull/31)，尚待实施人员安全集成，不自动合并。新GPU、训练、付费及正式测试未授权。以下历史入口及结论原样保留，只用于历史复现，非当前执行顺序。

---

# Policy Manager — PM-RL1 仓库审阅入口

更新：2026-11-16（Asia/Tokyo）。本次同步用于让网页版审阅本地项目的代码、研究方案和原始证据。同步范围、文件缺口及核验结果见[仓库同步说明](project/docs/REPOSITORY_SYNC_20261116_ZH.md)，逐文件清单见 [FILES.jsonl](project/docs/repository_sync_20261116/FILES.jsonl)。上传资料不代表采用新研究方案，也不产生新的实验结果。

建议按以下顺序阅读：

1. [原始研究目标与方案](project/docs/PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md)：在冻结执行器下、生成回复之前进行资源选择、顺序获取与策略学习；区分当前 PM-RL1 和旧 Paper-1。
2. [最新状态](project/docs/PM_RL1_CURRENT_STATUS.md)与[进度证据索引](project/docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md)：均保留多个历史时点，不能把旧段落的“当前”“待执行”直接当作今天的结论。
3. [11-05 自然支持历史价值结果](project/docs/reviews/20261105/pm_rl1_history_necessity_human_review/RESULTS_ZH.md)与[11-11 QA / 资源视图结果](project/docs/reviews/20261111/pm_rl1_typed_resources/RESULTS_ZH.md)：自然支持价值检验未达预设门槛；14 道事实题中 OFF / 定向原资源分别答对 0 / 13。QA 结果不等于自然支持帮助性、顺序策略或 PPO 已有收益。
4. [11-15 研究审计](project/docs/reviews/20261115/pm_rl1_research_audit_and_route/REPORT_ZH.md)、[资源准备实物与剩余项](project/docs/reviews/20261115/pm_rl1_resource_organization_and_execution/RESULTS_ZH.md)、[11-16 会后摘要设计](project/docs/reviews/20261116/pm_rl1_session_summary_design/DESIGN_ZH.md)：新方法、案例和摘要仍有候选或未验证部分。
5. [Codex 主方案](project/docs/PM_RL1_MASTER_EXECUTION_PLAN_20261116_ZH.md)与 [Claude V2 方案](project/docs/PM_RL1_EXECUTION_PLAN_V2_20261116_ZH.md)：逐项比较范围、反馈来源、评价和执行依赖，再核对实际代码。

**方案采用状态存在冲突。**入口文件和最新状态已写 V2 取代原工作单，但 V2 正文仍规定研究者确认后生效，[V2 状态表](project/docs/plans/pm_rl1_v2_20261116/EXECUTION_STATE.json)的 `plan_adopted_by_researcher` 为 `false`。本审阅入口将 V2 作为候选修订材料展示，不把此次上传解释为采纳其动作上限、奖励或完成标准。

当前源码主要在 `project/src/metacom_pm/rl1/`，实验入口在 `project/scripts/rl1/`，回归测试在 `project/tests/test_rl1_*.py`；共享来源、记忆编译及官方评价代码在 `project/src/metacom_pm/paper1/`。研究记录和原始产物需结合本次同步清单阅读。已有工程训练和成本负对照，不能由下方旧快照中的“训练为 0”推断后续从未训练，也不能将这些训练当作自然支持正收益证据。

## 2026-10-22 历史入口快照

以下内容保留该时点的原有描述、命令与结果；其中“当前”“唯一主方案”“待回收”及训练次数均属于 2026-10-22 历史状态。当前审阅从上方入口开始。

更新：2026-10-22（Asia/Tokyo）。`Metacom5_3`是历史仓库名，方法名为Policy Manager（PM）。

**当前：P1来源/表示和P2执行器适配已完成；自动奖励仍未合格，真实BC检查点与自然任务PM强化学习更新均为0，正式比较与独立终评尚未完成。** 累计308次尝试，包括旧307次评分/审查尝试与1次Claude配置拒绝；Claude已按研究者要求暂缓。学习协调器、BC/OneShot/NoText接口及586条历史生成的来源绑定缓存接线已完成工程检查。新的8对开发盲评与6条问题回归材料已交付，尚未收到答案。容量或脚本存在不表示后续实验已获运行许可。

## 先读这几处

- [最新后端复核：内容评分缓存、有限恢复、公共引擎与学习接线](project/docs/reviews/20261022/pm_rl1_backend/BACKEND_REVIEW_ZH.md)
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
| 学习与核验准备 | BC/OneShot/NoText及完整反馈batch协调已接线；586条历史G结果离线复用；新开发人评材料已交付、待回收 |
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

本次GitHub发布另外使用全新Python 3.11环境和CI指定的CPU PyTorch验证：1,429项通过、131项跳过，pytest退出码0；32项集成检查通过。发现并补齐`jsonschema`运行依赖。跳过项依赖私人引擎/输入、可选BGE依赖或本机冻结tokenizer，不算已验证集成；详见[发布验证回执](project/docs/reviews/20261022/pm_rl1_publication/VALIDATION.json)。

## 保留的历史边界

研究变更前阅读[AGENTS.md](AGENTS.md)。旧Paper-1使用公开ESConv、ESC-Eval和ES-MemEval/EvoEmo，保持官方指标、资源语义与结果锁；当前PM-RL1的q/m代理评分不能改称官方ESC-Eval结果。项目废弃的自造80/11用户纵向数据及其衍生物不用于当前研究。

[旧Paper-1执行清单](project/docs/PM_PAPER1_EXECUTION_CHECKLIST_20260903_ZH.md) · [历史发布/进展索引](project/docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md) · [2026-10-02发布说明](project/docs/PM_RL1_STAGE_PUBLICATION_20261002_ZH.md)。
