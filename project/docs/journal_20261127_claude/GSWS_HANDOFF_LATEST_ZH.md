# GSWS／语义能力交接登记（最新）

更新：2026-11-27（JST）第三阶段（G4），Claude Code。供Codex与Claude之间无损接续；只登记身份、决定、结果、位置、授权与下一动作。

## 当前身份

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/chensiyu7812/Metacom5_3 |
| 接续起点 | `7847b839`（Codex `pmrl1-j/gsws-phase1-20261126`）；第二轮`8369621a`；本阶段基于`8369621a` |
| 本分支 | `pmrl1-j/gsws-claude-handoff-20261127`，工作树`/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws-claude`（无其他Agent修改，沿用） |
| 未动 | main、PR #28、MIDSTATE4、旧220次额度、fold6、其他冻结工作树与执行器；未合并任何分支 |

## 已完成

1. 第一轮（`dae9b486`）：GSWS v3恢复80调用，无独立增量（收口）。[GSWS_V3_RESULTS_AND_DECISIONS_ZH.md](GSWS_V3_RESULTS_AND_DECISIONS_ZH.md)
2. 第二轮（`8369621a`）：身份修正、G1、G2-R（T1i为INSPECT_CLAIM候选）、INSPECT_CLAIM接口。[SEMCAP_G1_G2R_RESULTS_ZH.md](SEMCAP_G1_G2R_RESULTS_ZH.md)
3. 第三阶段（本次，主报告[G4_SYSTEM_CONTRAST_RESULTS_ZH.md](G4_SYSTEM_CONTRAST_RESULTS_ZH.md)）：
   - CPU前置：`semcap/g4_context.py`（三通道共用身份/时间/ID投影）、`evidence_state` v2（冲突vs随时间变化、超容量分窗）、`agent_skill` v2（逐条外部案例隔离）、输出过滤、ID枚举；subject/time_scope经实测**不参与**判断（只记录）；22项测试。
   - 16状态（S/U/H/O各4；ESConv 8、EvoEmo 8个owner）与检查项、8对盲评材料预测前冻结。
   - G4实际：96 LLM调用、1加载、868.7 s、0技术失败。A 16/16无违反、B 16/16、N 15/16、C 15/16；B等待+9.5 s，N +16.2 s；C 0/16次调用检查。运行时48条命题T1i 41/48、T0 38/48。**未建立语义能力的回复价值与按需收益**；瓶颈为命题形成、证据接口与调用决策，不是判断模型。

## 研究决定（本阶段）

- G1身份合同为共同基础设施；T1i保留为候选（T0/T1/T2全部保留）。
- 停止：MAVEN辅助、GSWS三臂重跑、G3；G5（T1i再训练）暂不批准且G4不支持继续NLI微调。
- 未在固定证据下显示收益前，不接回动态SEARCH/EXPAND/STOP，不做BC/价值学习/PPO。

## 授权范围

- 已用完：v3 clockfix；G1；G2-R；G4（96/112，余额不结转）。
- 待批：[NEXT_RUN_REQUEST_V3_ZH.md](NEXT_RUN_REQUEST_V3_ZH.md) G6（先用A筛出有改进空间的状态，再在独立留出集上做接口v2＋风险命题的B′对照；≤128调用、1加载、2,400 s、A6000）。

## 私有数据位置

`R=/opt/tokkio-data0/tokkio_runs/pmrl1-j-semcap-20261127`：`authorization/`（G1、G4批准原文与绑定）、`g4-candidates-v1/`、`g4-prepare-v1/`、`g4-run-01/`、`g4-blind-v1/`、`g4-cpu-checks/`、`g4-dryrun-cpu-v{1,2}/`，以及第二轮的`g1-*`、`dcs-seeds-v1/`、`g2r-data-v1/`、`g2r/`、`external-data/`。复跑：[SEMCAP_G1_G2R_REPRODUCE_ZH.md](SEMCAP_G1_G2R_REPRODUCE_ZH.md)（含G4节）。

## 下一动作

1. 等研究者对G6逐项批准。
2. 不需批准的CPU工作：证据接口v2（当前话语ID、问答成对引用）；风险命题形成提示；G6候选选择与检查项冻结；Memory Writer（`ge2_memory`/`pomdp_memory`）身份标签接线；DCS独立来源扩充与四类错误对照；INLI官方测试集去重后留作一次性确认。
3. 独立评审待办（均pending）：GSWS 12＋8、G1固定8对、G4 B对A固定8对。
