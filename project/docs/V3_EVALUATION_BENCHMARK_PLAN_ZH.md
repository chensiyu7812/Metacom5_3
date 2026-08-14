# MetaCom V3 Evaluation Benchmark Plan

日期：2026-08-13
状态：`OFFICIAL-FIRST ACTIVE / CUSTOM GATES RETAINED AS NONPRIMARY HISTORY / NO INFERENCE AUTHORITY`

当前唯一机器authority：`data/v3_authority/v3_official_first_evaluation_authority_v1.json`

## 2026-08-14 Official-first总纠正

在ESC-Eval人评暴露出自定义`2.5`门槛与研究者实际质量判断冲突后，项目停止让自定义evaluation反复控制研究。所有项目自设及格线、Quality/Risk/Function、executor、head panel、same-state baseline矩阵、改写版judge和prompt修复实验，全部降级为**保留但默认不执行的开发历史**。唯一继续全程主报的项目自定义量是实际Cost（tokens、检索/embedding、retry、latency、USD），且Cost不得改写官方分数。

当前研究主线只有：

1. **ESC-Eval官方协议**：331张公开英文高质量卡、固定ESC-Role、五轮交互、官方wrapper、官方七维和ESC-RANK。官方没有统一pass line，因此报告七维画像及其在论文参考模型分布中的位置，不再制造“2.5即合格”。
2. **ES-MemEval官方公开任务**：`Public-v1.0.0-1427`全部QA、125个summary和34个dialogue-generation scenario，使用官方prompt、baseline和指标。正式论文1209题与公开1427题身份不一致必须披露，不能伪装精确paper-row复现。

两张官方考卷完成后，先逐条判断它们能支持哪些论文主张。只有明确证明某个必要主张在官方任务结构上不可识别，才允许预注册一个最小补充实验；不能再先造门、反复内部循环，再用它决定研究是否成功。

## 当前冻结裁定

### 2026-08-14 人评后的方法论纠正

ESC-Eval原论文没有发布统一的“及格线”。此前在结果前冻结的`Information >= 2.5`是项目内部development规则，不是官方门槛；它保留为历史预注册记录，但不再有权把模型宣布为“ESC-Eval官方不合格”，也不能据此要求generator增加建议。当前24卡结果必须称为“研究对齐prompt上的ESC-Eval官方七维rubric画像”，不能称为官方wrapper复现或完整ESC-Eval。

官方`Information`维度同时评价建议的数量和有效性：少于五条但全部有效可以得到较高分，很多建议且全部有效才会达到最高档。论文自身也指出，通用模型会通过更长、更结构化的建议获得较高建议分，却在人类感和以人为本上较弱。MetaCom强调的自主决定、低负担、不过早行动和家庭/伴侣关系干预风险，因此必须作为独立补充构念报告，不能塞进官方七维，也不能为了刷`Information`而牺牲它们。

新的证据顺序是：

1. 先按官方wrapper、五轮ESC-Role和官方七维跑具名“官方协议复现”，把结果放到论文已发表参考模型分布中，不制造pass/fail；
2. 再报告当前研究对齐prompt的人评画像，用于判断这个generator是否适合MetaCom实际产品理念；
3. 最后单独通过自主性、低负担、关系干预风险、完整性和approved-plan/evidence executor，才把generator冻结给所有PM与baseline。

对应机器裁定为`g0_esc_eval_methodology_correction_v1.json`。此前拟议的“为了补Information而新增更多建议”的prompt-v2在任何新生成前撤销。

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
- generator选择由硬可靠性、ESC-Eval官方七维双人盲评、executor与项目Risk共同决定；ESC-RANK只作描述性自动化，E-I-A只作可选敏感性分析；
- low-burden guardrail 单独审计，防止建议数量奖励制造“高分但不合适”的系统。

原论文七维与公开adapter的固定映射为：`Fluency→fluency`、`Expression→diversity`、`Empathy→empathic`、`Information→suggestion`、`Skill→tech`、`Humanoid→human`、`Overall→overall`。`completion_rate/low_burden/no_premature_action/safety_signal_handling`是项目guardrail，不得伪装成ESC-RANK官方维度。

G0不直接宣告generator合格。2026-08-14的方法修正把两种不同责任正式拆开：

1. **官方wrapper复现层**：只有完全保持官方prompt、模型特定生成参数和scorer处理时，才可称为官方零样本复现；其作用是published comparability，不能独自决定本研究用哪个generator。
2. **研究对齐资格层（主层）**：保持ESC-Eval 24张英文开发卡、五轮role-player与样本身份不变，但给所有候选同一份依据ESConv、LLM emotional-support preference-bias、ExTES、ESCoT和ESC-Judge冻结的supporter prompt。它明确要求按Exploration–Insight–Action阶段和readiness选择支持动作，不暴露策略标签或思维链。

旧identity `bd2b4a12...`只用了`You are a helpful assistant!`，又统一施加256-token上限；45个Qwen turn中25个、45个8B turn中21个以`length`结束。该轮已在`g0_bd2b_prompt_cap_measurement_closeout_v1.json`中关闭：可用于旧surface的transport/latency诊断和证明上限确实binding，禁止用于最大能力排序或generator通过/淘汰。

替代G0在相同24卡上以8B和Qwen 3.7 Plus non-thinking为主候选，Qwen thinking作能力上界敏感性；Nemotron只有先过单独transport gate才加入。误配的70B不再是候选。provider请求完全省略`max_tokens/max_completion_tokens`；回复长度、是否自然完成、低负担/啰嗦度、tokens与finish reason都成为结果，而不是研究者预先截断。Quality主评价使用ESC-Eval官方Fluency、Expression、Empathy、Information、Humanoid、Skill、Overall七维0–4分双人盲评；ESC-RANK只作描述性自动化，ESC-Judge E-I-A只作可选敏感性分析；延迟报告完整非流式端到端median/p90、吞吐与失败率，不虚构跨provider不可比的TTFT。

先跑2卡canary，仅检验transport、prompt、自然完成和预算机制，绝不从2卡选模型；再跑24卡development screen。硬门失败者淘汰，剩余候选按Quality、atomic Risk和latency的Pareto关系筛选，不制造加权总分，也不让低延迟覆盖质量失败。最终候选另跑approved-plan/evidence executor和更大资格集；executor仍只识别generator能否实现已批准内容，不是PM selector证据。

2卡canary已在identity `9852e4c4...`下完成：40/40 supporter turn成功，0次length finish，0条terminal trajectory，Qwen实际费用`$0.0194692`。8B、Qwen non-thinking和Qwen thinking均10/10首次成功；误配70B虽经重试得到10/10文本，但10个turn中只有4个首次成功，出现5次network timeout和1次HTTP 5xx。该70B观测不能代表Nemotron，也不得进入模型排序。其余成功请求的median latency约为8B 0.53s、Qwen non-thinking 2.15s、Qwen thinking 14.46s。Qwen thinking消耗8,965 billed completion tokens，其中provider报告8,302 reasoning tokens；non-thinking总计628 completion tokens，而两者推断的可见token分别663与628。该结果只证明新runtime与无截断合同可运行；Quality尚未正式判断，禁止从两张卡选择generator。

正确Nemotron route已物化为新的零调用identity。transport canary仍用同两张卡、同prompt、同role-player与同seed，10个supporter turn，不设输出上限，并把三类现象分开：只有HTTP 429/Retry-After叫明确限流；timeout/408/5xx叫route instability；正常完成但median/p90过线叫slow service。任一冻结操作门失败就停止Nemotron，不让它拖慢24卡主测；这只淘汰当前托管route，不是宣称模型本体能力差。

该Nemotron canary已在identity `92bd2e53...`下完成并通过操作门：10/10均首次成功，0次HTTP 429、timeout、5xx或terminal trajectory；成功请求median约1.69s、p90约3.23s，10次均自然`stop`且无length finish。托管响应在10次中均含独立reasoning字段，但NVIDIA usage未给出独立reasoning token计数，因此1,601 billed completion tokens不能伪装成可见回答token。此结果只证明低并发小样本route可用；Nemotron保留进入更大Quality/Risk/latency比较，仍未选择generator。

下一轮四配置full G0已零调用物化：24张开发卡×五轮×Llama 3.1 8B、Qwen 3.7 Plus non-thinking、Qwen 3.7 Plus thinking、Nemotron 3 Nano，共480次supporter调用与480次本地role-player生成；其中Qwen付费调用240次，judge调用为0。四个配置全部在新identity下重跑，不把不同日期、不同candidate set的canary回复拼进正式矩阵。两卡Qwen实际费用线性外推约`$0.2336`，只是规划点估计；runner仍按无输出cap的65,536-token最坏预留逐次熔断。生成完成后按ESC-Eval官方七维做人类主评价、原子Risk审计和描述性ESC-RANK评分，不以transport指标选择模型。

该full G0生成现已完成：469/480个turn成功，Qwen实际费用`$0.2963172`。Llama 3.1 8B、Qwen non-thinking、Qwen thinking均120/120成功、24/24对话完成且无transport失败；Nemotron仅109/120成功，出现17次HTTP 503和3/24条terminal trajectory，turn有效率90.83%、完整对话率87.5%，均低于冻结的95%硬门。因此当前NVIDIA hosted Nemotron route退出部署generator选择；其109条成功回复只能在共同完成卡上作明确标注的描述性质量分析，不能删掉失败卡后伪装完整结果。Quality、原子Risk和低负担尚未评分，故8B与两种Qwen之间仍未选定generator。

官方ESC-RANK七维本地评分在执行前已零调用冻结：三种可靠性合格配置各24条完整对话，Nemotron仅21条完整对话且只作描述性分析，共93条对话×7维=`651`次本地推理，费用`$0`。primary parser仍严格要求完整`0–4`，同时保留只接受官方adapter固定标签句式的格式敏感性派生；不采用“任意位置找数字”的宽松parser。identity为`c22b402c...`，且该identity不授权quality选型或付费judge。

该identity现已在物理A6000上完成651/651次评分，费用`$0`。严格裸数字parser为0/651有效，原因是公开adapter稳定输出带维度标签的句子，故结论是输出协议不兼容而不是四个generator全部质量失败。预冻结的固定标签句式sensitivity为651/651有效，但Fluency、Expression、Empathy在三种可靠性合格配置的全部24张卡上完全同分，Overall也几乎恒定；Suggestion与Humanoid呈相反方向的局部差异，不能支持单一优胜者。两次因CUDA ordinal映射错误而落在A4500的部分尝试已隔离、不参与正式汇总。ESC-RANK因此完成了“公认外部描述性考卷”的责任，同时实证确认其不能独立承担generator选择。

### 公平generator选择协议

generator选择现在由`generator_esc_eval_primary_selection_v1.json`主控，`generator_fair_selection_protocol_v1.json`保留通用公平约束。“公平”不仅指同prompt，还包括：同24张官方英文开发卡和五轮轨迹、相同role-player与按位置共享seed、无研究者输出cap；模型/provider标签对评审不可见；card/dialogue是统计单位，turn与七个维度不是独立样本；transport失败、无效输出与完整性事件全部保留为ITT结果；Quality、Risk、cost、latency不合成一个总分。

当前三种可靠性合格配置各有24段完整对话，共72段。主评价不是新增LLM自定义盲评，而是两名独立盲评者逐段按ESC-Eval官方七维0–4分评分：72段×2人=`144`个dialogue assignment、共`1008`个维度评分。任一维度相差至少2分、无效对话或完整性疑虑进入第三位盲评裁决。先过可靠性与完整性硬门，再看Overall主指标及Empathy、Skill、Information关键维度；只有质量和风险等价时，成本和延迟才可决胜。

该双评审包现已物化为`g0_esc_eval_human_review_packet_manifest_v1.json`：两位评审顺序独立、逐段而非成组展示，公开页面不含具体模型、provider、卡片或source标识。数值development决策线也已在任何人评分数出现前冻结于`generator_esc_eval_development_decision_contract_v1.json`；聚合程序不会自行修改门槛或强行制造winner。

此前物化的144-call E-I-A judge canary（identity `6bfd7830...`）已经在任何调用前废止：0调用、`$0`，runner会拒绝执行。它只是ESC-Judge风格的可选敏感性工具，不是ESC-Eval官方七维评价，不能选择generator。现有24卡只支持具名开发筛选；论文级英文资格需在全部331张官方英文高质量卡，或事先冻结并明确命名的英文分层确认子集上复核，不能把24卡称为完整ESC-Eval。

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
