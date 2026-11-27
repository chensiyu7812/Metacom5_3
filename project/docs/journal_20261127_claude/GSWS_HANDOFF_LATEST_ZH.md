# GSWS／语义能力交接登记（最新）

更新：2026-11-27（JST）G6收口后，Claude Code。供Codex与Claude之间无损接续；只登记身份、决定、结果、位置、授权与下一动作。

## 当前身份

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/chensiyu7812/Metacom5_3 |
| 接续起点 | `7847b839`（Codex `pmrl1-j/gsws-phase1-20261126`）；此前提交`dae9b486`、`8369621a`、`1d4d20e0` |
| 本分支 | `pmrl1-j/gsws-claude-handoff-20261127`，工作树`/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws-claude`（无其他Agent修改，沿用） |
| 未动 | main、PR #28、MIDSTATE4、旧220次额度、fold6、其他冻结工作树与执行器；未合并任何分支 |

## 已完成

1. `dae9b486` GSWS v3恢复：无独立增量，收口。[GSWS_V3_RESULTS_AND_DECISIONS_ZH.md](GSWS_V3_RESULTS_AND_DECISIONS_ZH.md)
2. `8369621a` 身份修正、G1、G2-R（T1i）、INSPECT_CLAIM接口。[SEMCAP_G1_G2R_RESULTS_ZH.md](SEMCAP_G1_G2R_RESULTS_ZH.md)
3. `1d4d20e0` G4：未建立回复价值与按需收益。[G4_SYSTEM_CONTRAST_RESULTS_ZH.md](G4_SYSTEM_CONTRAST_RESULTS_ZH.md)（第二至五点解释由G6报告第二节纠正）
4. 本次 G6：接口v2（U0、问答关联、风险命题允许NONE、P/B′共享命题）、`evidence_state` v3（跨会话差异不作状态变化结论）、独立性检查、48状态预测前冻结；筛查32次调用后按冻结门槛**停止**（实质性可修复失败0）。[G6_CLOSEOUT_AND_DIRECTION_ZH.md](G6_CLOSEOUT_AND_DIRECTION_ZH.md)

## 研究决定

- **在线INSPECT_CLAIM实验线已关闭**；保留全部成果；不申请G7。
- G1身份合同为共同基础设施；T1i保留为候选，最合理的后续位置是离线Memory Writer/历史语义整理（不自动写入确定事实）。
- 不执行：G5、MAVEN辅助、GSWS重跑、G3、C′、BC、PPO；动态SEARCH/EXPAND/STOP作为独立研究问题保留，不启动新的GPU实验。
- 身份感知投影`memory_record()`已实现但**未接入**生产写入路径（`ge2_memory.py:171`、`pomdp_memory.py:174`）。

## 授权范围

- 已用完：v3 clockfix；G1；G2-R；G4（96/112）；G6（32/128，门槛停止，余额不结转）。
- 待批：无。没有提出新的GPU或付费申请。

## 私有数据位置

`R=/opt/tokkio-data0/tokkio_runs/pmrl1-j-semcap-20261127`：`authorization/`（G1、G4、G6批准原文与绑定）、`g6-select-v1/`、`g6-prepare-v1/`、`g6-run-01/`、`g6-dryrun-cpu-v*/`、`g1-blind-v1/`、`g4-*`、`g1-*`、`dcs-seeds-v1/`、`g2r-data-v1/`、`g2r/`、`external-data/`。复跑：[SEMCAP_G1_G2R_REPRODUCE_ZH.md](SEMCAP_G1_G2R_REPRODUCE_ZH.md)（含G4、G6节）。

## 下一动作

1. 独立评审（均pending，等待独立评审者）：GSWS 12＋8；G1 8对（运行后按不依赖输出的规则定义，已注明）；G4 B对A 8对。
2. 可做的CPU工作（不需GPU批准，不自动启动训练）：
   - 支持需求与重要内容遗漏的问题定义与评价规范；
   - 离线记忆整理中T1i的审计集设计；
   - Memory Writer身份标签接线方案；
   - INLI测试集去重后留作一次性确认；
   - 独立数据来源与标注规范。
3. 任何新的GPU实验都需研究者另行明确批准。
