# GSWS交接登记（最新）

更新：2026-11-27（JST），Claude Code。供Codex与Claude之间无损接续；只登记身份、决定、结果、位置、授权与下一动作。

## 当前身份

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/chensiyu7812/Metacom5_3 |
| 接续起点 | `7847b83995b64b9082096cf20f3d4a11ade8db84`（Codex `pmrl1-j/gsws-phase1-20261126`） |
| 本分支 | `pmrl1-j/gsws-claude-handoff-20261127`，工作树`/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws-claude` |
| 原Codex工作树 | `/opt/tokkio-data0/tokkio_projects/Metacom5_3-gsws`（未改动） |
| 远端检查 | `pmrl1-j/journal-plan-and-probe-20261125`为本分支祖先，无冲突；未合并任何分支，未动PR #28 |

## 已完成

1. **GSWS v3恢复真实实验**：4作业FINISHED，80调用（48终局EOS＋32解释），4加载（累计5），1205.1秒，0重试，0技术失败。
2. **开发审阅**：A0 11/4/1，A1 11/4/1，A2 13/1/2（pass/fail/unknown）；两解释均交付的10状态A1:A2=8:9；7/32解释未过校验回退RAW。专门表示无独立增量的证据。GSWS解释使本地Agent中位数+23.9秒。
3. **身份归因**：10-19/10-20原件已找到；冻结G0e与renderer把历史supporter映射为原生assistant是A场景冒认的结构原因；候选`semcap/identity.py`＋回归测试，未改冻结G0e。
4. **外部工具**：Maverick、MiniCheck实际接线；MAVEN-FACT官方无权重→自建训练入口（CPU冒烟）；Graphiti时间机制核查；Generative Belief仅借鉴表示。
5. **能力测试**：speaker32新开发集（预测前冻结）；宿主说话人限定使主体交换误通过8–12/13→1/13，加Maverick→0/13；剩余主要缺陷为“缺证据判矛盾”。

## 研究决定

- GSWS固定供证诊断收口，不重跑、不改提示追分。
- 身份作为系统上下文合同；所有方法共享；仅A场景改渲染。
- 语义能力层首个学习目标：说话人/阶段条件化的supported / contradicted / not-established。
- 语义能力按需调用；不启动BC/PPO。

## 授权范围

- 已用完：`GSWS_CLOCKFIX_RUN_REQUEST_ZH.md`的一次技术恢复（证据A/authorization-v3-clockfix）。不得再用于任何运行。
- 待批：[NEXT_RUN_REQUEST_ZH.md](NEXT_RUN_REQUEST_ZH.md)的G1/G2/G3。

## 私有数据位置

A=`/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-actual-20261127`：`results-v3-clockfix/`（原始回复、解释、审阅表）、`independent-review-packet-v1/`（12＋8盲包，pending）、`run-v3-0N/`（原始日志）。C=`/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-claude-20261127`：`speaker-dev-v1/`、`claim-support-cpu-v1/`、`factuality-smoke-cpu-v2/`、`external/`、`hf-cache/`。工具环境`/opt/tokkio-data0/tokkio_envs/semcap-tools-py311`。

## 下一动作

1. 等研究者对G1/G2/G3逐项批准。
2. 不需批准的CPU工作：①为解释器`evidence_ids`设计观察ID enum约束（消除引用格式回退）；②确定性的报告时间/当前时间交付（计划valid_at=陈述时间）；③核实对话NLI/矛盾类监督来源的可得性与许可；④为Maverick第三方指代建立小规模参考。
3. 12＋8独立复核等待独立评审者；无独立真人时保持pending。

文档：[主报告](GSWS_V3_RESULTS_AND_DECISIONS_ZH.md)、[复跑](GSWS_V3_REPRODUCE_ZH.md)、[身份](IDENTITY_AND_SEMANTIC_DEFECTS_ZH.md)、[工具](SEMCAP_TOOLS_ASSESSMENT_ZH.md)。
