# MetaCom V3 P0 官方实现审计与退出计划

日期：2026-08-13  
状态：`P0 EVIDENCE ARCHITECTURE + OFFICIAL SCALE MAPPING COMPLETE / 9 OF 9 ARCHITECTURE GATES / P1 MEASUREMENT QUALIFICATION NEXT / NO INFERENCE AUTHORITY`

## 结论

公认 benchmark 必须进入论文，但“公认”不等于“官方仓库可直接复现”。P0已经把 ESC-Eval、ESC-Judge 和 ES-MemEval 的论文、代码、数据、评分角色、reference、阈值推导和主张边界全部冻结；正式执行前仍须在P1完成本地测量资格化。

这里作了一项方法论纠正：**P0负责冻结怎么考，不负责先把人评和考试全部做完。** Risk双人fixture、ESC-Judge人类anchor和Quality/Risk数值margin属于P1校准；它们仍是正式判决前的硬门，但不再把设计冻结拖成内部无限循环。

这不是再造自定义 benchmark。外部论文仍定义 construct、数据与参考分布；本项目只补齐官方 artifact 没有冻结的运行环境、样本身份、顺序效应、失败处理和测量可靠性。

## 官方实现审计

| 对象 | 已钉死 | 发现 | 当前可用性 |
|---|---|---|---|
| ESC-Eval | commit `9ad46e7`；英文331、中文324，共655张高质量卡；ESC-Role/ESC-RANK revision | 论文的59,654是约8.5K对话×7维评分；公开仓库没有逐条人标或7:1:2 split ID；scorer有路径、浮动base revision、宽松数字parser和英文角色中文替换问题 | 官方考卷有效；修复版ESC-RANK只作七维描述性外部指标，不能单独定及格 |
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

## P0 的真实完成状态

P0九个证据架构门现已全部完成；这不等于测量有效性已经解决。原合同曾把项目自定义维度混入ESC-Eval outcome，现已严格纠正为原论文七维与公开adapter逐项映射：

`Fluency/fluency`、`Expression/diversity`、`Empathy/empathic`、`Information/suggestion`、`Skill/tech`、`Humanoid/human`、`Overall/overall`。完成率、低负担、不过早行动和安全处理单独报告。

1. ~~对 ES-MemEval 作一次明确选择。~~ 已冻结`ES-MemEval-Public-v1.0.0-1427`、1427行逐题身份和非精确1209复现边界；
2. ~~为三个官方 benchmark 建立本地协议 wrapper 和 runtime 边界。~~ 已物化655张ESC-Eval卡、ESC-Judge 25/100角色选择、150个双向E-I-A单元和ES-MemEval 1427行身份；真正模型依赖等候选/reference/scorer身份冻结后再锁；
3. ESC-RANK已完成公开artifact审计：论文/考卷构念有效，修复后可作描述性指标；由于逐条人标未公开，绝对pass/fail用途明确标为`UNQUALIFIED`；
4. 同栈reference已选为NVIDIA同接口`meta/llama-3.3-70b-instruct`，五轮、temperature=0、交错执行与provider alias不可精确钉权重的边界已冻结；
5. ~~物化 ESConv/ExTES 与 ESC-Eval 的 source、exact、normalized、semantic overlap。~~ 228张同源卡已完成全源比对；若两源都用于SFT，英文污染隔离主考卷为103张；
6. Risk packet/schema/盲分配的无正式数据设计门已完成；两名人类评审在看gold前完成18包/36任务资格化并冻结数值margin，是P1正式判决前门槛；
7. outcome-blind margin合同已冻结：P0冻结推导、硬工程门与上限，P1用非正式anchor登记数值，不得从正式结果倒推。

机器可读清单见 `data/v3_authority/p0_exit_checklist_v1.json`。当前状态明确为“架构与量表映射完成、P1测量资格待完成”；它不授权API推理、人评执行、微调或正式pass/fail。

## 下一批最短工作：P1

下一批不再回到head内部循环，而是做一次有边界的测量与generator资格化：

1. ESC-RANK静态overlay preflight已完成：InternLM2/adapters revision、两处路径修正和只接受完整`0..4`的parser均已锁；P1还需隔离依赖环境、权重下载与load smoke（须另批）；
2. 已为8B、同栈70B与Qwen 3.7 Plus生成24卡ESC screen和16包既有开发executor诊断的G0 identity、调用量和预算；后者明确不是held-out PM证据，批准后先跑transport canary，再完成screen；
3. Risk 18包双评与非正式Quality anchor只用于量表校准，登记数值margin后即关闭，不消费正式PM回复；
4. 硬门合格且Pareto非支配的候选才进入ESC-Judge/人类anchor；最终选中者完成G1全英文ESC-Eval和executor后冻结。若不再使用8B，旧42/90轮只归档为诊断，不再补成混栈“正式结果”。

公开审计阶段为零推理：14个主adapter身份、论文Table 4 hard/±1 accuracy、官方代码缺陷和0行公开逐条人标均已物化。随后在隔离Python 3.11环境下载固定revision的ESC-Role、InternLM2和ESC-RANK，并在A6000完成零生成加载烟测：14个adapter全部挂载，API调用0、生成token 0。NVIDIA与阿里云只做鉴权模型目录GET确认冻结路由存在，凭据未落盘；真实推理仍须绑定identity和费用批准。

42/90 的外部 stress 回复继续保留。它们不作废，但在 P0 完成前不按旧标准作最终判决；48条 continuation 也不因本文件自动获得执行授权。

## 主张边界

- ESC-Eval/ESC-Judge 通过：只说明冻结 generator 在合成多轮 ESC 考卷上的资格；
- ES-MemEval 通过：只说明冻结 memory 系统在指定公开 artifact 上的能力；
- 三项 PM 外测通过：才支持 learned state-action selection 在冻结 generator 下有增量价值；
- Atomic Risk 无 material/critical 增加：只支持观察条件下的个性化完整性，不能写临床安全。

当前方法的价值不是保证实验必胜，而是保证最终正面结果能回答论文问题，并且负面结果能定位到 generator、executor、memory、treatment 或 selector，而不是继续困在“到底是系统失败还是考卷失败”的循环里。
