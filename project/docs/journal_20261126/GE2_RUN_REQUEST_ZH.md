# GE2 独立运行申请：同一链路的检索、使用与决策诊断

状态：**冻结CPU准入已完成，未获本包GPU授权，尚未执行。** 本申请仅针对 `packages-v2`，不转用原220次、旧DR或MIDSTATE4授权。研究者批准须绑定下面计划对象、请求范围SHA及执行器身份。

## 范围与预算

冻结8题：G01–G03官方事实QA、G04–G06真实pre-supporter自然前缀、G07–G08旧SMV联合任务。选择发生在新检索结果前，完整历史QA与真实时点前缀分开；不按模型输出替换任何题。共同normal四臂为 **STOP / FixedTop4 / LLMOneShot / LLMToolAgent**。5个事实/联合题另有 **DirectEvidence**，只作能力诊断。

共 **37个实际终局槽 + 最多8个OneShot控制 + 最多40个ToolAgent控制 = 最多85次实际调用**。4个独立作业，均1次加载、0 warmup、0 retry、1200秒总硬限，合计4800秒。每个任务所有条件留在同一作业，终局不缓存、不复用旧输出。未用调用不转移给其他任务。

|作业|任务|终局槽|OneShot上限|Tool控制上限|调用上限|加载/硬限|
|---|---|---:|---:|---:|---:|---|
|GE2-1|G01/G02|10|2|10|22|1 / 1200秒|
|GE2-2|G03/G04|9|2|10|21|1 / 1200秒|
|GE2-3|G05/G06|8|2|10|20|1 / 1200秒|
|GE2-4|G07/G08|10|2|10|22|1 / 1200秒|

普通臂共享5次工具原语、4096去重后源容量、16384模型上下文上限、原终局320新token、同source registry/As-of/renderer和同模型。Top4为SEARCH+4次parent EXPAND，没有旧5对4原语差异。OneShot一次提交程序，可对未来SEARCH的rank做引用；ToolAgent每次观察真实结果后决定。两者各最多768累计控制输出token，单次decode上限等于其尚余额度；最多5次Tool控制后获取已达上限时强制STOP，不花第6次无选择的模型调用。

本地Agent路径上限600秒并受整个作业截止时间约束，预留300秒终局；这是实验运行边界，不是用户体验SLA。当前工作负载是否可在硬限内全部完成仍须实测，不能以token吞吐推定客户端延迟。最大控制输出12288、终局输出11840 tokens，合计24128，仅为辅助上界，不预估为实际产量。

## 固定身份

清单文件SHA256：`2fb7ae94eda42068e8f2fd0e4fff1c36cc18bcc9e780e3addbe2a17ae4ae5c2d`。

执行器inventory对象SHA256：`c8bdfa61b536635687b11442e459cfdc0630ae064adcf13324a7deb5707e21e4`。

共同controller合同对象SHA256：`02b6b443adeacb08dba131a000d0f0c47083db5a721645892fd329e845525684`。

|作业|PLAN对象SHA256|REQUEST_SCOPE文件SHA256|
|---|---|---|
|GE2-1|`6dbbedd179a6b7f35b232ea2790070389014ad44ee6257afdf6a0cc821c91954`|`5b44ea59b6c3611af78dda9813830ae7ae7bf92643e9a57074ce744e53c46b05`|
|GE2-2|`bdd9bb2bd9178cc6588057bcbe582fba6c5a003ff42461cf939d5ce3bad98724`|`5de60dd047f32af01d4a0a0ba5956a78e14621ca4346435467c09a5ca2d25194`|
|GE2-3|`baa70d78d169a31b0e4c4e999b6f0ada578d8ae041c27b6307abaddfc15a7b7d`|`5850346adec49810bb594f979c5f4088fa454720b76e6fe50bb4f028200351df`|
|GE2-4|`f335ddd6078d6c1a8ead032c9410d20dee5897ab1b0f48e4ef082499ae1bd1ee`|`4affe7be89e22bc82fd83e55f03b67983e4f2a8b80629cc53d6f5dab292ba77d`|

私有包根：`/opt/tokkio-data0/tokkio_runs/pmrl1-j-ge2-20261126/packages-v2/`。四个 `batch-0N/PLAN.json` 和 `REQUEST_SCOPE_PRIVATE.json` 已绑定任务、来源、评价文件、Direct原文坐标、共同检索配置、完整执行器与model/tokenizer/decode依赖。动态后续payload无法事前知道，范围合同先冻结；每次实际调用须再绑定完整真实observation/content/snapshot、原生input_ids、source receipt和单调时间。没有占位prompt待临场选择。

沿用原Gemma-4-12B-it revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`、HF、原指定GPU及全部设备/磁盘/独占/父进程死亡守卫；不干预其他项目，不换卡，不申请模型训练。底层A/B/G组合保留，完整新631代码文件与81 vendor文件清单见[依赖闭包](ge2_v1/EXECUTOR_DEPENDENCY_PUBLIC.json)。单journal checkout仍不足以复现私有源与本机模型栈。

`packages-v1`是未获授权的准备快照；最终v2补齐“作业剩余时间少于单路径600秒时”的真实观察绑定。8题、来源、ranker、终局要求与评价没有改变，没有任何GE2模型输出。只认v2的申请身份，不接受v1或旧批准。

## 评价、失败及停止

- 检索R：实际原文供给、时间合法、必要原子来源群与成本。覆盖不是任务成功。
- 使用U：Direct充分供应的明确目标是否完成，主体/阶段/日期/未知是否正确。G02保留日期推导争议，G03的上下文不是事实不存在的证明；不能把这两题的所有失败归G。
- 决策D：完整逐题四臂质量、可靠性、实际等待、获取与STOP原因。没有中间反事实时保持动作适当性未知，不用需求标签或自报充分性补正确动作。
- 自由回复按已冻结分项合同审阅；原SC36评分器不用于自然回复。首fact G01与首natural G04各四普通臂的8输出有限遮蔽审阅已固定，未完成输出不换题。正式reward始终空，原5项真人复核pending。
- 控制器JSON/状态协议失败或length：保留原返回与失败，只终止该获取路径，用同一终局槽对已验证证据执行一次fallback。没有控制器重试，也不新增第二个G；系统可靠性标为降级，fallback语义另评。
- 源身份、模型、hash、时钟、设备、transport故障或全局截止：停止整包并保留已返回、技术未完成和未执行。不把未知技术状态判普通语义失败。grammar与decode无合法有限logits时不解除mask；后端故障不假设可继续。
- 终局length保留为该槽技术不完整，独立后续槽可在原预算内执行；不因正负科学结果停止、改候选、改prompt或换评价。

实际时间记录Agent入口、控制调用、工具、合法性、原生tokenization/renderer、PM结束、终局模型内部首非空文字与完整回复。来源冷启动、加载和首推断、实验守卫及嵌套计量单列；区间不重复相加。客户端首文本、有效文本、Tokkio首段语音未测则留空，不能由总生成时间推算。所有终局都真实执行，离线fixture或缓存不作延迟收益。

科学收口：若同信息同预算强静态/OneShot解释全部收益，停止当前GE2序贯优越性主张，不扩同类卡片/样本；若有可辨别质量或实测等待增量且未增加预定错误，才考虑独立验证及轻量策略。完整供证仍失败时只保留一次独立Step-2提案，不在这85次内加入。无BC/PPO、新Generator训练或自动后续。

MIDSTATE4的原4次申请另见[原固定申请](system_review_v1/MIDSTATE4_RUN_REQUEST_ZH.md)。本次不将其合并成89次，也不改变T01/T03 Rank1；批准GE2不等于批准MIDSTATE4，反之亦然。
