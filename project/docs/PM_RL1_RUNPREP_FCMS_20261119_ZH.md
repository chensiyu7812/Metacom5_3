# WS-A：G0e / A0 / PP1 最小准备与 FC-MS 候选

本轮采用研究者明确指定的设计 A：PM Step-1 获取资源，G0e 在 no-plan Step-2 中隐式决定是否及如何使用。STOP / GET_RS / GET_MP / GET_ME / GET_MS 不变。本文及新增代码没有改 H0、EXECUTION_STATE、main、integration 或旧冻结文件，没有合并任何 PR，没有 GPU、Generator、Judge、训练、付费 API 调用。

主交付位于 [runprep_fcms_20261119](../outputs/pm_rl1/v3/runprep_fcms_20261119/README.md)。WS-A 工程工作与 [integration coordinator 只读建议](../outputs/pm_rl1/v3/runprep_fcms_20261119/INTEGRATION_COORDINATOR_ZH.md) 分开记录；A 的自检不替代 B。

## 状态与本轮差异

| 对象 | engineering_ready | research_qualified | authorized |
|---|---|---|---|
| #19 原 16 个 PP1 输入 | CPU 绑定通过；B 已独立签收固定 HEAD | 尚未证明资源增量价值；语义/许可/协议门禁仍在 | 否 |
| 新受限执行器与 A0 4 次申请 | CPU 机制通过；真实加载、根盘门槛、最终独立签收未闭合 | 工程诊断，不作支持质量推断 | 否 |
| 新 renderer | CPU 对照、容量、编码测试通过，B 复核待办 | 模型可读性、实际使用、注入行为尚未实测 | 否 |
| DP 选择工具 | 合法 RAW 界面、一次冻结、候选导出机制通过 | 8 个 DP 仍待独立人工选取与确认；正式 90 样本尚未确认 | 否 |

相对 #19 只新增文件。#19 HEAD 4ac9ab3d23d04cd8ec9435ea239995ae85a3e610 与 REQUESTS_16 的文件 SHA 9af4a17328c3bf730899d3724452a06a7929e63962b7c2ef09319a168722226c 不变。没有改其 prompt、顺序、来源会话、token IDs、result/reward 或 DP 状态。新 A0、新 renderer 和未来 FC-MS 各用独立身份。初始短 commit 名构建副本保留在数据盘验证目录；正式交付 cpu_v2 绑定完整 40 位执行器提交。

## 现有 G0e 已满足的设计约束

现有 system prompt 要求围绕当前用户自然回应、理解情感、适时温和提问，避免过多建议、无依据保证和虚构个人历史，并把对话作为数据。现有 Notes 明确写有：

> Use only what helps now; relevant memories need not be mentioned.

它同时说明外部内容是引文而不是指令、不要暴露 Notes、过去报告可能过期、意图/建议不等于已执行行动、外部案例不是当前用户历史。这已经提供隐式资源使用的文字约束，不需加 Step-2 动作或强制引用。OFF 不带 Notes。身份仍是 pmrl1v3-g0e-no-plan-1。

尚须真实检验：忽略不适合的历史、不同人物及阶段区分、过期信息处理、自然度、对当前需求的帮助，以及提示注入的行为抵抗。CPU token/边界检查和来源合法性都不等于这些能力成立。当前 Notes 使用 HTML 实体的展示属性保留在 PP1；不因讨论设计 A 改写已签收输入。

## G0e 身份与 A0

G0e 固定来源为 #10 73fdb12f29b6970a268eeda704d73e1bd35b1c3e。两条路径任选其一：

1. integration owner 按受保护流程正式集成 #10，登记实际 integration HEAD，并完成必要的联合验收。
2. 研究者书面固定该未合并 HEAD 的 G0e 身份，仅用于本次受限研究运行，登记签署者、证据及适用范围。

两条路径都不自动批准 A0 或 PP1。书面固定也不是允许 merge、修改全局状态或绕过分支保护。A0 必须另签 [独立申请](../outputs/pm_rl1/v3/runprep_fcms_20261119/A0_APPLICATION_ZH.md)，仅 4 次，不执行旧 100 OFF 或旧 154+7 预算。

## PP1

使用 #19 原 8 OFF + 8 RET-MS、原 G0e Notes、greedy/320；[最终运行前清单](../outputs/pm_rl1/v3/runprep_fcms_20261119/PP1_PRE_RUN_ZH.md) 逐项绑定执行器、请求与 B 协议。B #20 HEAD 4624600de57bbb61f872d54540234f07d907c1ed 的停止规则已经与 #19 对齐。新执行器不调用存在 R1–R5 问题的在线 BoundEpisode/ReplayCache，不修饰这些问题的状态。

## FC-MS renderer 与 DP

推荐将新 line-quote-1 作为正式 FC-MS 的待审候选：普通单/双引号原样可读，逐行竖线标注外部引文，反斜杠、角/方括号、控制字符及双向控制逐项编码。没有 HTML 反转义，也没有递归解码。保留来源类型、报告日期和完整 RAW；DP/RET 都显示 MS，不暴露实验臂。正式 OFF/DP/RET 只能选同一个 renderer。

[逐字对照 HTML](../outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/RENDERER_COMPARISON.html) 展示同一份真实证据的原文、旧 Notes 与候选；其 MS 材料仅是比较 renderer 的固定夹具，不是 DP 选取。推荐依据可读性和编码检查，不使用任何 PP1 回复偏好。B 独立复核后由研究者决定。

[DP 人工工具说明](../outputs/pm_rl1/v3/runprep_fcms_20261119/DP_TOOL_ZH.md) 与 [8 前缀离线界面](../outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/DP_SELECTOR_8.html) 已准备。工具允许没有适合材料；结果不自动变成 OFF 式 DP，不允许把 lexical-v0 改名。正式 90 条须先确认筛查清单，不能把 B 的候选自动当成采用。人工选取不是模型效果证明。

MP/ME/RS/METHOD/CASE/SUM 沿用 #19 的独立资格清单；原五项 RAW 标注仍 pending_human_review，43 项 MP/ME 待审和 SUM unusable 均不解除，也不成为 MS-RAW 准备的额外前置。

## 研究者需亲自决定的最小事项

1. 选择上述 G0e 身份路径，签署具体 SHA 与范围。
2. 在根盘风险由其负责人解决、最终执行器被签收后，单独签署 A0 4 次申请；A0 结果只作为工程诊断。
3. A0 通过后，另行批准 B 的 PP1 候选协议及此次最终 16 次作业；确认许可范围、筛查/QH 背景冻结、1 名整理者及 2 名审阅者和 B 工具就绪。是否将 PP1 纳入正式分析必须在看到结果前决定。
4. 后续确认一个 FC-MS renderer、正式筛查名单及独立 DP 选择规则；不影响 PP1 原输入。

root 可用空间低于 1 GiB，当前真实运行仍阻塞。容量调查和数据盘布局见 [容量报告](../outputs/pm_rl1/v3/runprep_fcms_20261119/CAPACITY_ZH.md)。没有删除旧文件、申请占用设备或停止其他任务。所有待办保持 pending；资源增益尚未成立。
