# MetaCom V3 Evaluation Benchmark Plan

日期：2026-08-13
状态：`V3-P0 EVIDENCE ARCHITECTURE + OFFICIAL SCALE MAPPING FROZEN / V3-P1 MEASUREMENT QUALIFICATION PENDING / NO INFERENCE AUTHORITY`

机器合同：`data/v3_authority/v3_evaluation_freeze_contract_v1.json`

## 当前冻结裁定

整体状态为 `P0_EVIDENCE_ARCHITECTURE_FREEZE_COMPLETE_OFFICIAL_SCALE_MAPPING_REPAIRED_P1_MEASUREMENT_QUALIFICATION_REQUIRED`。这只表示证据责任和考法已冻结，不表示量表可靠性、数值及格线或generator已经合格。目前的42/90 stress-test回复继续保留；generator主线比较8B与Qwen 3.7 Plus，正确的NVIDIA补充候选是`nvidia/nemotron-3-nano-30b-a3b`，且必须先过小型transport gate。若更换generator，旧轮归档为不可补成正式混栈矩阵的诊断。

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
- 2026-08-14纠正：此前把用户指定的Nemotron误写成NVIDIA `meta/llama-3.3-70b-instruct`。70B原始结果只保留为误配route诊断，不能用于generator选择；正确route为`nvidia/nemotron-3-nano-30b-a3b`，先按冻结的429、失败率与median/p90延迟门槛做2卡transport canary；hosted route不暴露不可变weight revision的限制仍须披露；
- generator选择由硬可靠性、executor、同栈E-I-A和Risk共同决定，不用ESC-RANK Average设一个伪精确分数线；
- low-burden guardrail 单独审计，防止建议数量奖励制造“高分但不合适”的系统。

原论文七维与公开adapter的固定映射为：`Fluency→fluency`、`Expression→diversity`、`Empathy→empathic`、`Information→suggestion`、`Skill→tech`、`Humanoid→human`、`Overall→overall`。`completion_rate/low_burden/no_premature_action/safety_signal_handling`是项目guardrail，不得伪装成ESC-RANK官方维度。

G0不直接宣告generator合格。2026-08-14的方法修正把两种不同责任正式拆开：

1. **官方wrapper复现层**：只有完全保持官方prompt、模型特定生成参数和scorer处理时，才可称为官方零样本复现；其作用是published comparability，不能独自决定本研究用哪个generator。
2. **研究对齐资格层（主层）**：保持ESC-Eval 24张英文开发卡、五轮role-player与样本身份不变，但给所有候选同一份依据ESConv、LLM emotional-support preference-bias、ExTES、ESCoT和ESC-Judge冻结的supporter prompt。它明确要求按Exploration–Insight–Action阶段和readiness选择支持动作，不暴露策略标签或思维链。

旧identity `bd2b4a12...`只用了`You are a helpful assistant!`，又统一施加256-token上限；45个Qwen turn中25个、45个8B turn中21个以`length`结束。该轮已在`g0_bd2b_prompt_cap_measurement_closeout_v1.json`中关闭：可用于旧surface的transport/latency诊断和证明上限确实binding，禁止用于最大能力排序或generator通过/淘汰。

替代G0在相同24卡上以8B和Qwen 3.7 Plus non-thinking为主候选，Qwen thinking作能力上界敏感性；Nemotron只有先过单独transport gate才加入。误配的70B不再是候选。provider请求完全省略`max_tokens/max_completion_tokens`；回复长度、是否自然完成、低负担/啰嗦度、tokens与finish reason都成为结果，而不是研究者预先截断。Quality以ESC-Judge的Exploration、Insight、Action双顺序pairwise为主，ESC-RANK七维只作描述性敏感性，人类小anchor在最终冻结前执行；延迟报告完整非流式端到端median/p90、吞吐与失败率，不虚构跨provider不可比的TTFT。

先跑2卡canary，仅检验transport、prompt、自然完成和预算机制，绝不从2卡选模型；再跑24卡development screen。硬门失败者淘汰，剩余候选按Quality、atomic Risk和latency的Pareto关系筛选，不制造加权总分，也不让低延迟覆盖质量失败。最终候选另跑approved-plan/evidence executor和更大资格集；executor仍只识别generator能否实现已批准内容，不是PM selector证据。

2卡canary已在identity `9852e4c4...`下完成：40/40 supporter turn成功，0次length finish，0条terminal trajectory，Qwen实际费用`$0.0194692`。8B、Qwen non-thinking和Qwen thinking均10/10首次成功；误配70B虽经重试得到10/10文本，但10个turn中只有4个首次成功，出现5次network timeout和1次HTTP 5xx。该70B观测不能代表Nemotron，也不得进入模型排序。其余成功请求的median latency约为8B 0.53s、Qwen non-thinking 2.15s、Qwen thinking 14.46s。Qwen thinking消耗8,965 billed completion tokens，其中provider报告8,302 reasoning tokens；non-thinking总计628 completion tokens，而两者推断的可见token分别663与628。该结果只证明新runtime与无截断合同可运行；Quality尚未正式判断，禁止从两张卡选择generator。

正确Nemotron route已物化为新的零调用identity。transport canary仍用同两张卡、同prompt、同role-player与同seed，10个supporter turn，不设输出上限，并把三类现象分开：只有HTTP 429/Retry-After叫明确限流；timeout/408/5xx叫route instability；正常完成但median/p90过线叫slow service。任一冻结操作门失败就停止Nemotron，不让它拖慢24卡主测；这只淘汰当前托管route，不是宣称模型本体能力差。

该Nemotron canary已在identity `92bd2e53...`下完成并通过操作门：10/10均首次成功，0次HTTP 429、timeout、5xx或terminal trajectory；成功请求median约1.69s、p90约3.23s，10次均自然`stop`且无length finish。托管响应在10次中均含独立reasoning字段，但NVIDIA usage未给出独立reasoning token计数，因此1,601 billed completion tokens不能伪装成可见回答token。此结果只证明低并发小样本route可用；Nemotron保留进入更大Quality/Risk/latency比较，仍未选择generator。

下一轮四配置full G0已零调用物化：24张开发卡×五轮×Llama 3.1 8B、Qwen 3.7 Plus non-thinking、Qwen 3.7 Plus thinking、Nemotron 3 Nano，共480次supporter调用与480次本地role-player生成；其中Qwen付费调用240次，judge调用为0。四个配置全部在新identity下重跑，不把不同日期、不同candidate set的canary回复拼进正式矩阵。两卡Qwen实际费用线性外推约`$0.2336`，只是规划点估计；runner仍按无输出cap的65,536-token最坏预留逐次熔断。生成完成后另行冻结E/I/A双顺序Quality、原子Risk和描述性ESC-RANK评分，不以transport指标选择模型。

该full G0生成现已完成：469/480个turn成功，Qwen实际费用`$0.2963172`。Llama 3.1 8B、Qwen non-thinking、Qwen thinking均120/120成功、24/24对话完成且无transport失败；Nemotron仅109/120成功，出现17次HTTP 503和3/24条terminal trajectory，turn有效率90.83%、完整对话率87.5%，均低于冻结的95%硬门。因此当前NVIDIA hosted Nemotron route退出部署generator选择；其109条成功回复只能在共同完成卡上作明确标注的描述性质量分析，不能删掉失败卡后伪装完整结果。Quality、原子Risk和低负担尚未评分，故8B与两种Qwen之间仍未选定generator。

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
