# MetaCom V3 Evaluation Benchmark Plan

日期：2026-08-13
状态：`V3-P0 EVIDENCE ARCHITECTURE + OFFICIAL SCALE MAPPING FROZEN / V3-P1 MEASUREMENT QUALIFICATION PENDING / NO INFERENCE AUTHORITY`

机器合同：`data/v3_authority/v3_evaluation_freeze_contract_v1.json`

## 当前冻结裁定

整体状态为 `P0_EVIDENCE_ARCHITECTURE_FREEZE_COMPLETE_OFFICIAL_SCALE_MAPPING_REPAIRED_P1_MEASUREMENT_QUALIFICATION_REQUIRED`。这只表示证据责任和考法已冻结，不表示量表可靠性、数值及格线或generator已经合格。目前的42/90 stress-test回复继续保留，但先比较8B、70B与Qwen 3.7 Plus；若更换generator，旧轮归档为不可补成正式混栈矩阵的诊断。

ES-MemEval身份已按结果盲原则解决：正式主任务命名为`ES-MemEval-Public-v1.0.0-1427`，逐题身份清单覆盖1427行/18 owner，明确不声称复现论文1209题。ESC本地协议、重叠筛查、ESC-RANK公开artifact责任、same-stack reference和margin推导均已冻结。P1剩余的是执行性的测量资格化：修复scorer runtime、双人非正式anchor、Risk fixture、数值margin登记与generator选择。

官方实现的静态审计已经完成，详见 `V3_P0_IMPLEMENTATION_AUDIT_AND_EXIT_PLAN_ZH.md` 和 `data/v3_authority/official_benchmark_implementation_audit_v1.json`。这一步确认了ESC-Eval 655张高质量卡的公开身份，但也确认官方runner/scorer不能原样作为合格测量工具；ESC-Judge的公开100角色无法还原论文实际25角色，且仓库没有实现双向位置互换。因此“官方协议锚定”和“本地测量资格化”必须同时成立。

## 考卷与主张映射

| 考卷 | 主张 | 主指标 | 单位 | 不允许的外推 |
|---|---|---|---|---|
| ESC-Eval | generator 的多轮 ESC 基础能力 | 官方Fluency、Expression、Empathy、Information、Skill、Humanoid、Overall七维；完成率另列 | role card / dialogue | PM价值、临床效果 |
| ESC-Judge | generator 相对 reference 的 E-I-A 支持策略 | Exploration/Insight/Action pairwise | synthetic role | 绝对及格分、真实用户效果 |
| ES-MemEval | 长期记忆能力 | retrieval、Token F1、BERTScore、conflict、abstention、false answer | user | RS价值、独立于EvoEmo的新用户复现 |
| ESConv | RS/R0 单会话 PM | blind pairwise Quality、atomic Risk、Cost、selection | dialogue | 纵向 memory |
| EvoEmo response | RS/MP/MS/ME 与 joint policy | same-state Quality/Risk/Cost、marginal、interaction | 18 users | 204+ states 视为独立样本 |
| Atomic Risk Audit | 个性化完整性 | 8类事件 + uncertain | reply/exposure/owner | 完整临床安全 |

## 冻结前必须完成

1. 每个 benchmark 的官方仓库、tag/commit、许可证、文件 hash、样本数和语言；
2. role/user/dialogue/question 的统计单位与 cluster rule；
3. train/dev/test 与已使用开发数据的 source、dialogue、semantic overlap；
4. scorer/judge 的模型身份、prompt、版本、seed、turn cap、retry 和失败处理；
5. reference model 及同栈复跑，或无法复跑时的明确不可比边界；
6. noninferiority margin 的来源和 sensitivity；
7. primary/secondary outcomes 与 multiple-comparison 处理；
8. deterministic input/output token、latency、retry、USD 成本账本；
9. hard safety/integrity event 与 `UNCERTAIN` 的处理；
10. benchmark 运行只能决定是否通过，不能反向修改 selector、sample 或 treatment。

完整P0退出门已物化为 `data/v3_authority/p0_exit_checklist_v1.json`，九个证据架构门完成。此前量表合同混入项目自定义维度的问题已经修正；P0仍只代表“证据架构与推导程序冻结”，不代表scorer、人评、数值decision line或generator已通过。

## ESC-Eval 资格方案

- 主运行必须保持官方 role cards、交互方式和七维完整报告；
- ESC-RANK公开仓库没有逐条人工标注与split ID，因此不再无期限“寻找后再开始”：其论文construct和655卡考卷保留，修复版scorer作描述性七维外部指标，作为单独绝对pass/fail工具明确为`UNQUALIFIED`；
- published Llama3-8B/ChatGPT/ESC-specialized 分数只作背景，不能与不同代码、模型版本和 prompt 的新分数直接作正式 NI；
- 同栈reference冻结为NVIDIA `meta/llama-3.3-70b-instruct`，与8B交错复跑；hosted route不暴露不可变weight revision的限制必须披露；
- generator选择由硬可靠性、executor、同栈E-I-A和Risk共同决定，不用ESC-RANK Average设一个伪精确分数线；
- low-burden guardrail 单独审计，防止建议数量奖励制造“高分但不合适”的系统。

原论文七维与公开adapter的固定映射为：`Fluency→fluency`、`Expression→diversity`、`Empathy→empathic`、`Information→suggestion`、`Skill→tech`、`Humanoid→human`、`Overall→overall`。`completion_rate/low_burden/no_premature_action/safety_signal_handling`是项目guardrail，不得伪装成ESC-RANK官方维度。

G0不直接宣告generator合格。它在24张英文卡（ESconv 8、MHP 5、ExTES 5、Psych 3、EPITOME 3）和16个owner-unique executor开发包上比较8B、70B与`qwen3.7-plus-2026-05-26`。executor包完整复用一个已退役开发面板，8B结果可能已知，因而只用于工程能力诊断，绝不是held-out PM证据；每包固定比较R0-only与最大授权delta，且后者在12包同时含MS和RS，不能据此识别单头效应。硬门失败者淘汰；剩余候选只按Pareto支配关系筛除，不制造加权总分。多个非支配候选进入ESC-Judge双顺序与人类anchor；最终选中者必须再跑完整英文ESC-Eval和完整executor。

## ESC-Judge 稳健性方案

- 以同一 synthetic role 分别运行 candidate 与 reference；
- 保持对称顺序或随机化顺序，报告 position sensitivity；
- Exploration、Insight、Action 分别报告，不用单一 Average 掩盖阶段差异；
- judge family 与 generator family 尽量分离，并保留一小批人工 anchor；
- 只作 robustness，不代替 ESC-Eval 绝对定位。

每个candidate/reference pair必须以A/B与B/A两个顺序评判。顺序翻转导致胜者翻转时标记`POSITION_UNSTABLE`；`TIE`、`INVALID`、`REFUSAL`均单列，不得强制归入candidate胜或负。

官方论文的实验边界也必须保留：25个合成角色、375个对话三元组、o1-mini judge；人工一致性只在随机抽取的100对、两位博士级标注者上验证。论文报告的85%/83%/86%是该设置下 Exploration/Insight/Action 的匹配率，不是跨 judge、跨语言或真实用户的通用可靠性保证。

## PM 自定义专项考卷

- 同一个 current context、candidate pool、retrieval、R0、generator、seed policy 和输出预算；
- 只改变资源选择或一个 component delta；
- Quality 用 state-specific checklist 的匿名 pairwise；
- Risk 用 source-aware atomic event；
- Function 看 current context、授权 source 与匿名回复，作为 mechanism evidence；
- Cost 使用实际 generator input/output tokens，并分开报告 retrieval/retry/latency/USD；
- 所有统计按 dialogue/user 聚类，重复 state/seed 只增加簇内精度。

正式Risk由两名独立盲评员覆盖所有treatment reply及同状态baseline，而不是只抽样。所有event presence分歧、`UNCERTAIN`和material/critical标签进入第三方裁决；零critical只能报告“未观察到”及单侧上界，不能写作零风险。具体协议见 `data/v3_authority/risk_adjudication_protocol_v1.json`。

## 通过线冻结原则

- 绝对分数与相对 reference 同时报告；
- margin 不能从正式结果倒推；
- 小开发 slice 允许方向性晋级，正式结论必须给 cluster uncertainty；
- critical integrity event 不被平均分掩盖；
- Function 非零、可归因、可复现，但不要求每次 ON 都有清晰可见的措辞；
- 任何无法验证的比较标 `INCONCLUSIVE`，不能强制判为 pass/fail。

当前预注册硬线包括generator对话/turn有效率≥95%、executor结构有效率≥90%、必需slot实现≥80%、适用事实忠实度≥90%，以及相对fixed-high的实际generator input tokens至少降低10%。Quality/Risk的数值NI margin在P1由非正式双评anchor与Risk fixture登记，最大Quality margin不得超过paired-preference-probability的0.10；仍不得从正式outcome反推。完整规则见`evaluation_margin_justification_v1.json`。
