# GSWS／语义能力交接登记（最新）

更新：2026-11-27（JST）第二轮，Claude Code。供Codex与Claude之间无损接续；只登记身份、决定、结果、位置、授权与下一动作。

## 当前身份

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/chensiyu7812/Metacom5_3 |
| 接续起点 | `7847b839`（Codex `pmrl1-j/gsws-phase1-20261126`）；本轮基于`dae9b486` |
| 本分支 | `pmrl1-j/gsws-claude-handoff-20261127`，工作树`/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws-claude`（本轮无其他Agent修改，沿用） |
| 原Codex工作树 | `/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws`（未改动） |
| 未动 | PR #28、MIDSTATE4、旧220次额度、fold6、其他工作树；未合并任何分支 |

## 已完成

第一轮（`dae9b486`）：GSWS v3恢复80调用、无独立增量；身份根因；Maverick/MiniCheck接线；speaker32。详见[GSWS_V3_RESULTS_AND_DECISIONS_ZH.md](GSWS_V3_RESULTS_AND_DECISIONS_ZH.md)。

第二轮（本轮，主报告[SEMCAP_G1_G2R_RESULTS_ZH.md](SEMCAP_G1_G2R_RESULTS_ZH.md)）：

1. **身份代码修正**：外部案例seeker/supporter不再标为当前用户/当前AI；新增U（来源未确立），EvoEmo默认U，作为B须标`experimental_assumption`。
2. **G1实际完成**：24调用、1加载、274.7 s、0失败。两臂冒认0；误认情形下合同臂明确归属2/6、认领他人原话0/6（冻结臂0/6、1/6）；无误认时0多余声明；等待无增加。定位为系统上下文合同，后续所有方法共享。
3. **监督数据核查**：DNLI（镜像SHA与ParlAI官方一致）、DECODE、INLI、VitaminC实际下载检查；INLI为主监督，隐含蕴含不并入支持。
4. **DCS**：64个ESConv训练家族自然话语的同命题不同证据对照集（助手编写弱监督，train 312 / dev 152，家族不相交）。
5. **G2-R训练**：T1、T2（＋MAVEN辅助）、T1i（隐含为独立第四类，运行前登记的追加臂）；A4500账本1,460.8 s（约27分钟进程占用）。推荐模型`T1i/checkpoint-epoch2`。
6. **主要结果**：缺证据判矛盾INLI-dev 124→35/1000、event32/speaker32 scoped→0；DCS-dev macro-F1 0.816→0.893但家族层3好2差11平；MAVEN辅助无增量（停止）；整段对话下主体误支持8/14未被训练解决；发现并修正“隐含=矛盾”捷径。
7. **Agent接线**：`semcap/evidence_state.py`（三态＋implied＋unprocessed、metrics、ECE、InspectClaim）、`semcap/agent_skill.py`（INSPECT_CLAIM动作校验、合法观测绑定、修订、冲突、G注记）；测试17项通过。

## 研究决定（本轮新增）

- 身份合同＋正确角色渲染作为所有后续方法的共同合法上下文。
- 语义能力层主任务：对话证据状态（supported/contradicted/not_established），implied单列、不写入确定事实库；技术失败为unprocessed。
- 停止MAVEN辅助头路线；不执行G3。
- 宿主说话人限定只适用于明确自报型命题；Maverick按需而非默认。

## 授权范围

- 已用完：v3 clockfix；本轮G1（24/24）；G2-R（GPU 3小时上限内用约27分钟，额度不结转）。
- 待批：[NEXT_RUN_REQUEST_V2_ZH.md](NEXT_RUN_REQUEST_V2_ZH.md) G4（Agent最小系统对照，≤112调用，A6000）、G5（DCS独立扩充后再训练，A4500≤1小时）。

## 私有数据位置

本轮`R=/opt/tokkio-data0/tokkio_runs/pmrl1-j-semcap-20261127`：`authorization/`、`g1-*`、`dcs-seeds-v1/`、`g2r-data-v1/`、`g2r/`（检查点、预测、账本、错误清单、轨迹）、`external-data/`。上一轮A、C目录见[GSWS_V3_REPRODUCE_ZH.md](GSWS_V3_REPRODUCE_ZH.md)。复跑见[SEMCAP_G1_G2R_REPRODUCE_ZH.md](SEMCAP_G1_G2R_REPRODUCE_ZH.md)。

## 下一动作

1. 等研究者对G4/G5逐项批准。
2. 不需批准的CPU工作：①Memory Writer（`ge2_memory`/`pomdp_memory`）接身份情形标签；②G4的16个状态选择与命题形成提示冻结；③DCS新来源扩充与四类错误对照；④共同输出过滤去除“thought”思考标记；⑤解释器`evidence_ids`枚举约束（上一轮遗留）。
3. GSWS 12＋8独立复核与G1固定8对仍待独立评审者；无独立真人时保持pending。
