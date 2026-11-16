# PM-RL1 外部研究与补缺核验（2026-11-15）

本稿是独立只读调查与设计建议，不改变项目当前合同，不启动模型、训练或付费调用。核验对象为论文及作者仓库/数据卡；未把“论文说开源”自动等同于当前可下载、可复现、可合法再分发。没有安装候选全栈，也未验证运行兼容性。

## 首要结论

**现有研究可以补方法、资源结构、评价维度和对照实现；没有发现可以直接替代 PM-RL1 的同一公开前缀下资源 ON/OFF/组合反事实收益表、实际端到端等待数据、以及读后动作改变的收益证据。后面三项必须在本项目的固定 G 和资源接口上实测。**

选择原则是按缺口引入最少组件，而不是把所有数据集和裁判堆入主流程。外部论文正结果与本项目不矛盾：它们往往训练/更换 G、让动作代表支持策略或 token、使用模拟用户未来情绪奖励、对比更弱基线，或者只测事实 QA；本项目要证明的是冻结 G 下“为哪份外部内容支付读取成本”的选择价值。

建议优先级：先利用现有 ESConv 完整上下文和失败样本；用 AnnoMI 补充有标注的方法及反例；借 ESCA/D²RCU 的检索—执行拆解；用 Adaptive-RAG/AACO 的结果驱动选择方法构建强简单基线。其他候选先作为条件性补充，不能成为又一轮换模型比赛。

## 1. AnnoMI：可补“方法动作是什么”，不能补“疗效是什么”

- 一手来源：[作者仓库](https://github.com/uccollab/AnnoMI)、[扩展论文](https://www.mdpi.com/1999-5903/15/3/110)。本次确认 `AnnoMI-simple.csv` 和 `AnnoMI-full.csv` 文件实际存在，约 2.4 MB / 3.8 MB；未下载正文。
- 公开资源是 133 个高/低质量 MI 示范的转写，含 therapist/client 顺序、视频来源、行为类型；full 版额外提供开放/封闭问题、简单/复杂反映、信息/建议/协商/选项等多标注员字段。
- 具体接入：按完整 transcript 分组；把局部“前情—支持行为—紧随其后的回应”保留下来，附真实技术标注，作为 RS 案例与行为评审校准材料。用不同 transcript 做开发和测试；所有同源视频片段在同一分区。仅把适合非临床情感支持的技能纳入本研究。
- 不能补的缺口：高/低质量是 MI 示范质量，不是随机治疗结果；change talk 不是长期改善；专家标注也不证明该材料会提升当前 G。不能把它整体替换为 ES 帮助性主裁判，不能把观察到的下一句转成资源调用最优标签。
- 污染控制：G 可能预训练见过这些公开内容；因此需要实测增益而非声称参数中绝无此知识。必须核对源视频和完整 transcript，防止同源片段跨集合。
- 数据单位注意：full 版带 annotator_id，同一 utterance 的多标注记录不能重复算独立话轮或训练情境；行为存在与主行为标注也不是相同定义。

可补充的专业方法依据是 [SAMHSA TIP 35 官方入口](https://www.samhsa.gov/resource/ebp/tip-35-enhancing-motivation-change-substance-use-disorder-treatment)及其[第 3 章](https://www.ncbi.nlm.nih.gov/sites/books/NBK571068/)。公开章文明确讨论反映倾听、矛盾心态、sustain talk 与咨询关系不协调等情境，提供方法、示例及条件。这类原方法资料可以支持 RS 的“为什么如此做/何时不适用”；AnnoMI 则提供被标注的具体对话实例。TIP35 原适用域为物质使用障碍治疗，不能直接把其治疗目标移植到日常情感支持。选择哪些微技能可用于本研究、是否忠实提炼，仍需具备相关训练的评审；这一审核无法由公开 dataset 的存在自动替代。

## 2. ESCA：可补策略与执行的分离、条件化知识构造

- 一手来源：[AAAI 2026 论文](https://ojs.aaai.org/index.php/AAAI/article/view/38807/42769)、[代码](https://github.com/outsider-lj/ESCA)。已读取 README 和 `data_reader.py`。
- 作者仓库有 `data/annotated_ensconv_with_states.json` 的使用说明、标注脚本、`build_kb.py`、`preprocess_add_knowledge.py`、策略规划器/提示生成器训练入口。README 明确 PsyQA 和 ER 知识数据因许可不能直接提供，需另行获得并转换为英文 QA。
- 具体接入：借鉴将 emotion intensity、dialogue behavior、stage of change 等解释性假设与策略执行分开的检查方式；借 KB 类型组织与“策略匹配知识”的实验拆解。先用项目合法来源填同样接口，不直接复制论文推断状态为 PM 金标。
- 不能补的缺口：其优化对象和 G 训练与 PM 的 GET/STOP 不同；情绪/信任等自动注释不是可直接使用的真实心理状态。源 ESConv 高度重叠；同栈、公平无资源/固定资源基线仍必须重跑。
- 关键复现提示：作者自己说明换为 Llama-70B 做 seeker/judge 后，与原 PPDPP/DPDP 结果不同。这正说明“模拟器/裁判一致”和版本绑定是必要条件，并非本项目天然可继承他人分数。

## 3. D²RCU / CASE：可借检索与生成利用的消融，不能把 commonsense 当用户事实

- 一手来源：[D²RCU 论文](https://arxiv.org/abs/2404.02505)、[D²RCU 作者代码](https://github.com/Bat-Reality/DDRCU)；[CASE 论文](https://aclanthology.org/2023.acl-long.457/)、[CASE 代码](https://github.com/jfzhouyoo/CASE)。作者仓库均可访问。
- D²RCU 提供示例选择、persona 信息与认知关系融合的实现；README 要求 BlenderBot-small-90M 和 DPR，含多步预处理。CASE 提供认知与情感图建模，预处理数据链接及 COMET 构造入口，依赖栈较旧。
- 具体接入：在已有 RS 库上增加“情境匹配”检索诊断，与现 BGE、随机、直接指定合适资源对比；分别测检索选对率、G 是否正确利用、最终帮助性。完整案例与单句示例可做有界的表示对照。
- 不建议现在移植整个 decoder/图网络。它会同时改变 G、表示与资源来源，导致无法定位收益。COMET 所生成的可能动机/反应须标为假设；不得写进 MP/ME 为当前用户事实。
- 两文正结果不是强现代 G 下 RS 的边际收益证明，更不是资源数量或停止策略的最优证据。

## 4. Value Reinforcement：可补“具体支持机制与案例依据”，但不是统一奖励

- 一手来源：[ACL 2025 论文](https://aclanthology.org/2025.acl-long.1395/)、[作者代码](https://github.com/holi-lab/ES-Value)。本次确认存在 `training/`、`simulation/`、`persona/`；README 提供 target value detector、reference generator、supporter 的 SFT/DPO 流程。未核验完整训练数据和全部权重可下载性。
- 具体接入：借其“目标价值—参考支持行为—回复”的案例组织方式；可选一个窄领域作为 RS 方法实验，而非永远把支持目标等同于让语言更积极。引用实际对话依据，保留观察与解释边界。
- 不能补的缺口：价值表达增加不等于用户被帮助；论文联合训练多个组件，不能把其系统提升全归给外部参考；Reddit 群体回应不是该用户的个人历史，也不自动有专业适当性。
- 不应把论文的价值奖励直接作为本项目唯一 ES reward，否则研究目标被悄然换成价值表达优化。

## 5. PPDPP / CSO：可借小规划器和偏好构造，标签语义必须重建

- 一手来源：[PPDPP ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/29e8437db7b549160ce03d336ff66f65-Paper-Conference.pdf)、[PPDPP 作者代码](https://github.com/dengyang17/PPDPP)；[CSO 论文](https://arxiv.org/abs/2503.05362)、[CSO 代码](https://github.com/XingYuSSS/CSO)、[ESC-Pro 数据卡](https://huggingface.co/datasets/XingYuSSS/ESC-Pro)。
- 本次确认 PPDPP 有 `agent.py/env.py/run.py/sft.py/data/`，README 只有标题，不能承诺开箱复现。CSO 有 MCTS `run.py`、偏好转换 `build_data.py/change_data.py/change_data_kto.py`；HF 确认 ESC-Pro 英文 JSON 数据卡、MIT 标签和更新时间，未下载全量。
- 具体接入：借鉴固定语言生成器外接小规划器的强对照；用本项目同一资源效果表训练 BC/OneShot，再比较顺序 PM。CSO 的偏好转换格式可参考，不能把其“选哪种支持策略”的标签直接映射为 GET_RS。
- 不能补的缺口：策略规划与信息获取不同；一个有用的支持动作不意味着需要读外部资源才能执行。模拟用户的 future reward 也不等于真实用户的帮助性。来源多依赖 ESConv，须执行同 dialogue/role/seed 分组去重。
- 算法动机不能依靠名称：他人用了 RL/MCTS，不说明本项目 PPO 必须优于同数据的简单选择器。

## 6. RLFF-ESC：能参考未来反馈验证，当前不宜移植为主路线

- 一手来源：[论文](https://arxiv.org/abs/2508.12935)、[作者代码](https://github.com/yt556677/RLFF-ESC)。README 已核验：用 Qwen2.5-72B 做模拟 seeker 和 critic，生成 future-reward 数据，训练 reward model，再 GRPO 训练回复生成器；独立评价采用 GPT-4o。
- 可借部分：把训练反馈与独立评价分开；记录模拟轨迹、终止判定和版本，分析模型是否利用裁判漏洞。
- 当前不接入的部分：未来对话模拟、未来情绪 reward、大 G 的 GRPO。这会改变“严格当前前缀—多次读取—单次最终回复”的任务，并增加新 reward/model/simulator 三层不确定性与成本。
- 其正结果支持该模拟与优化设置中的回复训练；不能直接证明我们的外部资源有价值或 PM 决策正确。

## 7. ESC-Judge / SAGE：补评价视角，但都需要本地校准

- 一手来源：[ESC-Judge EMNLP 2025](https://aclanthology.org/2025.emnlp-main.811.pdf)、[作者代码](https://github.com/navidmdn/ESC-Judge)；[SAGE 论文](https://arxiv.org/abs/2505.02847)、[作者代码目录](https://github.com/Tencent/digitalhuman/tree/main/SAGE)。这里 SAGE 指 Sentient Agent as a Judge，不是同名 self-retrieval 方法。
- 已核验：ESC-Judge 有角色构造、对话模拟和按 Exploration–Insight–Action 等维度成对比较的脚本/rubric；SAGE 有模拟器 profiles、逐轮内部状态/情绪的运行入口。二者都涉及额外模型推理，不能称免费标签。
- 具体接入：优先借 rubric 中能对当前回复核验的条目，盲评现有 ON/OFF 配对；多轮模拟只作为另列的稳健性验证。采用多个模拟器时保持角色/起点一致，报告换模拟器是否翻转排名。
- 不能补的缺口：模拟器的“我好多了”不是人的结果；人工认为模拟反应合理，也不同于真实干预有效。它们不是新的统一金标准。不能一面用同一模拟器训练，一面把该模拟器的分数当独立确认。

## 8. Adaptive-RAG / Self-RAG / AACO：补资源决策方法，而不是 ES 标注

- 一手来源：[Adaptive-RAG NAACL 2024](https://aclanthology.org/2024.naacl-long.389.pdf)、[代码](https://github.com/starsuzi/Adaptive-RAG)；[Self-RAG 项目](https://selfrag.github.io/)、[代码](https://github.com/AkariAsai/self-rag)；[AACO ICML 2024](https://proceedings.mlr.press/v235/valancius24a.html)、[代码](https://github.com/lupalab/aaco)。
- 可接入：Adaptive-RAG 的“先实际跑不同获取方案，再训练小路由器”很契合本项目；将 zero/single/multi 的 QA 标签方法替换为项目实测资源配置的帮助性/时间标签。Self-RAG 可借“是否需要、是否相关、证据是否支持、最终是否有用”的分层评价，避免相似度直接冒充效用。AACO 提供非贪心获取/停止及克隆策略的对照思想，适合检验互补资源是否真需要顺序读取。
- 工程资产：Adaptive-RAG 有预测结果处理和 classifier 流程；Self-RAG 有模型/训练数据/检索代码；AACO 有 rollout、mask、classifier 与配置。其完整训练栈不应替代现有 RL1 工程。
- 不能补的缺口：QA 的客观真值和 tabular 完整特征分布与 ES 反馈不同；AACO 的条件期望估计不能直接套在极少文本情境上。Self-RAG 自评不能当真值。Adaptive-RAG 原 repo 中“test predictions 构造 classifier validation”的做法不能原样带入本项目确认集。

## 需要审慎排队、不能当已补上的新数据

| 候选 | 本次核验 | 真能补什么 | 不能直接使用的关键原因 |
|---|---|---|---|
| [Psy-Insight](https://github.com/ckqqqq/Psy-Insight)、[论文](https://arxiv.org/abs/2503.03607) | `data/en_data_version7.json`、`cn_data_version7.json` 实际存在；有病例/主题分段、策略、方法、背景/解释字段 | 候选专业案例与上下文依据；可用于 RS 材料盘点 | 数据 README 的语言/数量及链接存在互换，不能照抄统计；session 可能是主题片段而非独立随访；全会话 background/guide/reasoning 可能包含未来信息；来源说明涉及 Books3 等，仓库自称继承许可不足以证明原作品再分发权。先核源、顺序与权利，不纳入立即可用主干 |
| [MusPsy](https://github.com/Rener2005/MusPsy)、[论文](https://arxiv.org/abs/2506.06626) | 官方目录有 dialogues、memories、usercards、train、userProfiles，MIT 文件可见 | 公开、可追踪的多会话构造与记忆跟踪方法；条件性外部稳健性数据 | 论文明确基于真实病例报告生成合成对话；不能称真实长期用户结果。完整 profile 或结局可能提前暴露未来。项目若扩公共来源，须版本化说明；不能偷偷作为当前 public-only 固定来源的替代 |
| [PRMB 论文](https://arxiv.org/abs/2603.11494) | 论文声称六会话 CBT reward benchmark；所给 [YouKenChaw/PRMB](https://github.com/YouKenChaw/PRMB) 本次读取 README 和目录均 404 | 可借“多会话一致性、pairwise 与 Best-of-N 分开验证”的评测设计 | 当前可用性未证实，不能依赖其数据完成关键里程碑；未完整核验标签来源，不称独立人评金标；CBT 目标与本项目自然 ES 不等同 |
| [FTA-Mem](https://arxiv.org/abs/2608.16303) | 论文可检索，未验证作者代码或数据可用性 | 借 fact-time-affect 和保留情境边界的记忆组织思路 | 主要证据为 ES-MemEval/LoCoMo QA，不能据此证明 ES 回复帮助性；当前不是可承诺交付的复现依赖 |

Psy-Insight 的来源说明见 [作者 source/copyright 文档](https://github.com/ckqqqq/Psy-Insight/blob/main/docs/data_source/data_source.md)。以上是具体可用性/来源问题，不是泛化的禁止使用结论。

## 仍需项目自己补的四种证据，以及最小可行补法

1. **资源边际作用。** 同一自然前缀、固定 G、相同基础指导，生成 OFF、直接合适 RS、实际检索 RS、错配 RS；记忆与 RS 的组合另做同前缀比较。先建立资源确有价值，再研究取得它的策略。外部策略标签只能作注释，不能作调用收益标签。
2. **评价可识别性。** 选来源事实、支持行为适当性、总体帮助性三个独立方面；先对有实际差异的配对做盲评校准。保留相当与不确定，检查长度、位置、提示风格偏差。无法验证的自动标签不回流训练。借现有人评和合格范围，避免再找一个全能裁判。
3. **个体历史改变支持行为的自然覆盖。** 对现有合法原文进行 outcome-blind inventory：已尝试方法、明确拒绝、用户报告结果、当前更正、关系/目标变化，以及是否当前回复真正需要这些信息。若不足，先报告覆盖缺口。公共扩源只引入能核对身份/时间/原文的记录；来源还不够时，实际新增同意参与的数据采集或缩小人群/主张，不能生成预设改善结局补成功样本。
4. **读后信息价值与真实成本。** 每次 GET 后记录公开观察和下一动作；比较同动作域 OneShot、简单停止、BC、PPO。只有读取内容改变最佳后续行为并改善质量—等待权衡时，才能声称序贯价值。返回同一资源但慢一点不是信息价值。训练与评测成本分开，计入 PM/检索/编码/G 的全路径。

## 外部文献如何落入执行顺序

- 现在：ESConv 完整案例与失败样本盘点 → AnnoMI 方法适用性小样核验 → 形成来源化 RS 条目与错误分类。保留完整来源，并为前缀可见性打标。
- 首轮资源实验：借 ESCA/D²RCU 的检索与执行分离，采用强共同指导和错配控制；使用人评为主的有界机制验证，自动量表只作已核验范围的补充。
- 资源有效后：借 Adaptive-RAG 形成实测效用表与强静态路由器；顺序性有证据后再借 AACO 的获取/停止问题构造检查 PPO 增量。复用现有 PM-RL1 代码，不重建大型新框架。
- 可选外部稳健性：ESC-Judge/SAGE 放在独立模拟评测附表；Psy-Insight/MusPsy 经过来源与任务适配后才考虑，不能成为第一轮结果的先决条件。
- 暂不开展：RLFF-ESC/CSO 式大规模未来自博弈、整套 G/PRM 联合重训、追逐新 reward checkpoint、把多个 benchmark 合成自定义总分。这些均不直接解决当前最窄的识别缺口。

“都用上后仍缺什么”的答案不是再缺一篇论文，而是缺与本研究干预一致的配对证据和独立验证。公开工具能减少构造成本，无法替代这一步。
