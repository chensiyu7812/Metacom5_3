# MetaCom V3 P0 官方实现审计与退出计划

日期：2026-08-13  
状态：`P0 IN PROGRESS / 5 OF 9 REQUIRED GATES COMPLETE / NO API AUTHORITY`

## 结论

公认 benchmark 必须进入论文，但“公认”不等于“官方仓库可直接复现”。本轮零 API 审计已经把 ESC-Eval、ESC-Judge 和 ES-MemEval 的论文、代码、数据与模型表面分别定位。结果支持继续使用它们，同时要求在正式执行前加一层本地测量资格化。

这不是再造自定义 benchmark。外部论文仍定义 construct、数据与参考分布；本项目只补齐官方 artifact 没有冻结的运行环境、样本身份、顺序效应、失败处理和测量可靠性。

## 官方实现审计

| 对象 | 已钉死 | 发现 | 当前可用性 |
|---|---|---|---|
| ESC-Eval | commit `9ad46e7`；英文331、中文324，共655张高质量卡；ESC-Role/ESC-RANK revision | 无许可证与依赖锁；runner硬编码旧候选模型和5轮；scorer有`ESC-RANK1/fluency`路径不一致；base model未钉revision | 官方协议和数据锚有效；runner/scorer未资格化 |
| ESC-Judge | commit `1ad30da`；Apache-2.0；公开`roles-v1`为100个角色 | 论文25角色身份未公开；无依赖锁；judge temperature=1；未实现A/B双向互换；脚本默认模型混有o1-mini/o4-mini | E-I-A敏感性 construct 有效；不能声称精确论文复现 |
| ES-MemEval | tag `v1.0.0` / commit `6926242`；公开1427 QA、125 summary、34 generation | 公共git历史只有两个commit且数据未变化；没有公开issue解释1209/1427；无法从历史恢复正式1209题ID | 可跑“public v1.0.0 1427-row task”；不能冒充正式1209复现 |

## 为什么这改变后续执行

过去内部循环的根本问题不只是 judge 弱，而是测量责任混在一起：基础 ESC 能力、计划执行、记忆能力、PM 选择价值和个性化风险被少数自定义评分共同裁定。V3 现在拆成：

1. ESC-Eval 主资格化 generator，ESC-Judge 只做 E-I-A 成对敏感性；
2. 给定批准 plan/evidence 的 executor test 判断 generator 是否能执行资源；
3. ES-MemEval 判断长期 memory capability；
4. 同状态 baseline matrix 判断 learned PM 是否比规则、匹配随机和 fixed-high 更会选；
5. 原子 Risk 双评审计判断个性化完整性。

因此，第一版 PM 不再被一个模糊 Function judge 否决。Function 只需提供非零、source-aware、可复现的机制证据；主因果结论来自同状态 Quality、Risk 与 Cost。

## P0 的真实完成条件

P0 目前尚未完成；数据身份、官方实现/本地协议 dry run、训练—考试重叠、统计单位和主张边界五门已经完成。以下其余事项完成后才允许继续 head 调参、formal judge 或微调：

1. ~~对 ES-MemEval 作一次明确选择。~~ 已冻结`ES-MemEval-Public-v1.0.0-1427`、1427行逐题身份和非精确1209复现边界；
2. ~~为三个官方 benchmark 建立本地协议 wrapper 和 runtime 边界。~~ 已物化655张ESC-Eval卡、ESC-Judge 25/100角色选择、150个双向E-I-A单元和ES-MemEval 1427行身份；真正模型依赖等候选/reference/scorer身份冻结后再锁；
3. 资格化 ESC scorer/judge；不能复现的官方 scorer 必须标 `UNQUALIFIED`，不能静默替换；
4. 冻结同栈 reference，再从人类分歧、重复性、位置效应和实用差异推导 NI margin；
5. ~~物化 ESConv/ExTES 与 ESC-Eval 的 source、exact、normalized、semantic overlap。~~ 228张同源卡已完成全源比对；若两源都用于SFT，英文污染隔离主考卷为103张；
6. Risk packet/schema/盲分配的无正式数据 dry run 已完成；仍须两名人类评审在看gold前完成18包/36任务资格化，并冻结裁决与margin。

机器可读清单见 `data/v3_authority/p0_exit_checklist_v1.json`。只要任一 REQUIRED gate 未完成，状态就保持 `P0_NOT_COMPLETE_BLOCKS_HEAD_TUNING_AND_FORMAL_JUDGING`。

## 下一批最短工作

下一批仍然不花 API：

1. 完成 Risk 18包的双人盲评资格化；
2. 恢复并资格化ESC-RANK公开人标校准；若不可恢复，预声明其不合格并冻结替代方案；
3. 冻结同栈reference、ESC-Judge身份和human anchor的小额执行设计；
4. 用人类分歧、位置效应、同栈变异和实用差异推导margin，再单独请求预算与执行批准。

本轮所有新物化均为零API、零正式回复：benchmark dry run为655卡、25角色、150个双向判卷单元；overlap为228张卡，exact/containment均为0、语义最高0.892；Risk为18包、9个安全控制、36个双评任务。Risk公开packet ID已去除事件/正负标签，gold在双评锁定前只公开SHA-256承诺、本体由Git忽略。语义相似度不被解释为原始对话精确来源，source标签才是SFT污染隔离的决定规则。

42/90 的外部 stress 回复继续保留。它们不作废，但在 P0 完成前不按旧标准作最终判决；48条 continuation 也不因本文件自动获得执行授权。

## 主张边界

- ESC-Eval/ESC-Judge 通过：只说明冻结 generator 在合成多轮 ESC 考卷上的资格；
- ES-MemEval 通过：只说明冻结 memory 系统在指定公开 artifact 上的能力；
- 三项 PM 外测通过：才支持 learned state-action selection 在冻结 generator 下有增量价值；
- Atomic Risk 无 material/critical 增加：只支持观察条件下的个性化完整性，不能写临床安全。

当前方法的价值不是保证实验必胜，而是保证最终正面结果能回答论文问题，并且负面结果能定位到 generator、executor、memory、treatment 或 selector，而不是继续困在“到底是系统失败还是考卷失败”的循环里。
