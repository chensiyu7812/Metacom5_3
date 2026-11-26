# 官方研究、实际数据和可迁移范围

完成于2026-11-27。七个官方仓库均实际获取固定代码；逐项读取与本研究有关的入口、数据格式/构造和训练/推理代码。没有执行上游训练或付费标注脚本。下表的规模区分本次实际解析与官方描述；下载成功不代表获得全部下游数据权利。

| 来源/固定代码 | 实际数据核查 | 许可证与隔离 | 本研究可借鉴与不能假定之处 |
|---|---|---|---|
| [ES-MemEval](https://github.com/slptongji/ES-MemEval/tree/692624208acc077b8867698c1d6fcd998dee641a) | Git中的EvoEmo文件4,482,088 bytes；沿用已审查20用户401会话及30 QA开发缓存，本轮只用允许家族 | 仓库未见LICENSE；不据公开可下载推定训练授权。EvoEmo与其ESConv祖先继续同家族隔离，fold6封存 | QA/DG评估资源；basic_info、observation、gold是评价资产，不进入GSWS。完整历史QA与实时前缀分开 |
| [ESCA](https://github.com/outsider-lj/ESCA/tree/04984f1df04876182816ddfda7ad5e0cfe612b41) | 实际下载标注JSON 10,189,807 bytes，自动格式/顶层计数1,300条；未把任何新对话正文交给模型或纳入任务 | 代码MIT；ESConv内容及衍生标注权利不能只凭根LICENSE一概推定。原数据整体在隔离下载区，仅格式统计；未完成逐条家族准入 | 有状态标签、SFT策略规划及生成器/RL路径；窗口标注存在目标后信息，不能直接用于实时状态监督。PsyQA/ER附属知识未完整公开，不能声称系统全部可复现 |
| [LongMemEval](https://github.com/xiaowu0162/LongMemEval/tree/9e0b455f4ef0e2ab8f2e582289761153549043fc) | [官方cleaned数据](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/tree/98d7416c24c778c2fee6e6f3006e7a073259d48f)的oracle文件实际下载15,388,478 bytes、500题；只做字段/类别统计，无任务答案用于GSWS | 代码及HF数据卡MIT。s/m清理版完整大文件未下载；oracle不是正常检索性能评估。外部评价候选封存，不作训练 | 时间检索、user-fact索引扩展及知识更新评估已有先例；真实长期陪伴目标/支持质量不能由QA直接替代。官方test不作教师训练题 |
| [PGMem](https://github.com/wonjunchoi23/pgmem/tree/879a7a964f898c2f654977f871041bf20d09c7ca) | 官方仓库PrefEval implicit_persona实际1,000行；列含conversation/preference/question等。还提供ImplexConv、PersonaMem入口，未声称本次全部处理 | 未见仓库LICENSE；原基准许可与任务既往暴露分别核对后才能训练。不能默认与其他来源无重合 | Context/Episode/State/Trait及证据边、扩展/有效性组织已实现；当前goal影响检索不是新概念。代码以LLM更新/检索与评估为主，不能把图更新说成学到了合格策略 |
| [Graphiti](https://github.com/getzep/graphiti/tree/c66d168a54b6c25b7522f0c6f6a625889d8c3603) | 实读edges、extract_edges、edge_operations；它是框架，不是现成独立语义监督数据集 | Apache-2.0；不意味着用户插入的任何数据均可公开或训练 | 双时序/validity、实体边提取与失效管理可借鉴；抽取和冲突解析仍依赖模型，不证明当前目标下理解或回复质量 |
| [Self-RAG](https://github.com/AkariAsai/self-rag/tree/1fcdc420e48f50a7d7ab1ece5494221b93252e99) | [官方训练集](https://huggingface.co/datasets/selfrag/selfrag_train_data/tree/cfa0c0f91d223ac47acbf582c96bbf5bef5d7c0e)实际HTTP206取首1MiB，850条完整记录；不是全量150K核验 | 代码/数据卡MIT；来源字段dataset_name需做原任务重合审查。未放进本轮训练或输入 | critic/teacher构造检索、相关、支持和utility反思标记，再用标准next-token目标训练；不是必须PPO。自评token不能替代本研究独立反馈 |
| [MAVEN-FACT](https://github.com/lcy2723/MAVEN-FACT/tree/9b1961cc28333e74972b9a48c28357549cb8403e) | 官方[Drive目录](https://drive.google.com/drive/folders/1GP8cdPlcUx5Om-lQse11LTDU-QFeAMom)可列train/valid；train实际下载135,513,936 bytes，2,913文档、67,984事件簇、73,939提及 | 仓库与Drive未见明确数据许可，训练准入pending。valid 32,481,835 bytes仅核查元数据，未下载；不能把官方全体112,276提及误称本次训练集统计 | CT+/CT-/PS+/PS-/Uu及触发词/证据、论元、时序等可作事件事实性辅助；不是个人状态归属或自然支持质量金标 |

官方代码/数据SHA、下载范围和CPU结果在[数据审查记录](gsws_phase1/PUBLIC_DATA_AUDIT.json)及[MAVEN实际解析](gsws_phase1/MAVEN_FACT_DOWNLOAD_PUBLIC.json)。MAVEN下载先用连接器，读取大文件超时后采用官方公开下载链接；下载文件SHA为`190522b44f0702af030161924d7cb94c4a06bd5d6e2b40d79f8f1eaa5886bab7`。不使用来源不明的镜像。

## ESCA因果窗口的实际代码证据

[Annotation_full_file.py](https://github.com/outsider-lj/ESCA/blob/04984f1df04876182816ddfda7ad5e0cfe612b41/data/Annotation_full_file.py)的`split_conversation`先取多个seeker组成窗口，再向后包含supporter；`process_data`把整个窗口送去为其中各seeker标状态。函数默认8/4，主程序另设4；不是只截到当前目标话轮。后续`data_reader.py`的前缀组装不能逆转标签已经看到未来的事实。

本次仅抽取该纯函数AST，输入明确合成的16话轮序列，4/2窗口返回3个上下文和12个目标配对。12/12包含目标后支持者，9/12包含更晚seeker。这是证明实现允许未来信息的反例，不是估计原1,300条数据的泄漏比例。没有为测试解封fold6正文。

因此原ESCA标签保留为离线研究资产。要用于实时GSWS监督，必须按允许训练家族的真实pre-supporter前缀重新产生因果标签，参考信息范围要可追溯，不能把原窗口答案裁剪后假称因果。当前下载区的自动JSON解析只统计顶层格式/条数；未进行逐对话文本或标签分析。ESCA、ESConv、EvoEmo来源重合已知，不能作为互相独立验证集。

## 监督候选与创新审查结论

MAVEN实际训练提及：CT+ 69,782；CT- 1,492；PS+ 2,262；PS- 285；Uu 118。CT+占94.38%，任何未来模型必须按类别、来源文档和最小语义对照报告，不能只展示准确率。它能监督来源中事件被陈述为何种事实性，不能直接监督“用户真实做过什么”或“怎样安慰最合适”。[官方EFD数据代码](https://github.com/lcy2723/MAVEN-FACT/blob/9b1961cc28333e74972b9a48c28357549cb8403e/trainEFD/data.py)实际映射五类，并有分类与T5训练路径；尚未在本项目训练。

ESCA已将状态用于规划，PGMem已有个人状态与证据层级，Graphiti已有时间更新，Self-RAG已有自适应检索与支持性反思。GSWS不能单凭“共享”“状态”“grounding”声称独立贡献。可识别的候选差异需在**相同合法观察、相同解释模型与匹配预算、相同G**条件下，实际证明角色/阶段/目标/未知的解释与更新改善，并追踪其对回复和后续获取决策的作用。普通阅读笔记与较强G是必要竞争解释；第一阶段尚未验证这些贡献。

LongMemEval保留外部评价用途；MAVEN在许可证解决后优先作语义辅助；Self-RAG可参考训练方式和有限通用支持性样本，但不能迁移其utility为自然支持reward。ESCA重标只在训练来源开展。所有新监督还需文档/会话家族去重；目前没有声称跨这七个来源已完成全量文本去重，也没有为此读取封存正文。
