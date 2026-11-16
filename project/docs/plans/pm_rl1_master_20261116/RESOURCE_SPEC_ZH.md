# PM-RL1 四类资源内容与存储合同

版本：2026-11-16。状态：主方案的待实现资源合同，不是已部署资源库。用户已经要求加入会话结束摘要；旧MS完整原文规则保留为历史MS-RAW身份，新MS-SUM另立版本。四个逻辑资源头仍为RS、MP、ME、MS。摘要不是第五类资源，方法与案例也不是两个新策略头。

## 1. 四类资源分别存什么

| 资源 | 内容及粒度 | 结构化字段 | 给G的读取正文 | 不放入本类 |
|---|---|---|---|---|
| RS方法 | 一份有出处的方法单元：适用线索、可采取行为、限制和原适用领域 | method名称、来源领域、适用/不适用条件、行动选项、限制、来源命题ID、关联案例ID及关联状态 | 简短方法说明、适用条件、边界、必要例子；说明来源的原域及待确认项 | 从模型臆造的专业规则；关于当前用户的隐藏心理判断；目标资源收益标签 |
| RS案例 | 一个完整先前情境＋完整连续支持行动块＋紧随用户反应 | 原对话/视频家族、原轮次、原策略标签、反馈及其作用范围、未知、方法关联 | 完整所选前情、行动和反应；反馈范围清楚，不截成一句“好回复” | 当前目标的未来；与目标同源/改写案例；把礼貌感谢写成疗效 |
| MP | 一条相对稳定的个人事实及其版本，如关系身份、职业、持续生活约束 | slot、事实陈述、主体、报告时间、有效区间及不确定性、更正/冲突关系、时点投影状态 | 当前切点可支持的自足事实，必要的时间/冲突提示 | 临时情绪、一次行动、从一次拒绝推断的永久偏好；回应偏好史 |
| ME | 一次事件/经历/状态变化；应对尝试和主观反应只是其中一类 | 事件描述、主体、时间、建议/意向/尝试/报告反应/未知、观察内容、关联事件及其证据 | 自足事件描述、时间、行动阶段、本人报告的反应及未知 | 把建议当执行；把本人感受当因果疗效；无依据连接不同事件 |
| MS-SUM | 一次完整结束会话的独立摘要，保留过程与尚未解决事项 | 源会话、摘要叙述、主题/约束/支持过程/结果未知等命题索引、句级来源锚点、写入器身份 | 会话日期＋紧凑叙述＋必要条目；不附完整审计引文 | 当前会话的结束摘要倒灌同会话中途；唯一滚动总摘要覆盖所有历史 |
| MS-RAW | 同一过去会话的完整逐轮原文 | 源会话、原轮次、说话者、原文、完整性与hash | 完整逐轮原文；不截断或冒充摘要 | 临时拼接片段、作者提供的summary/observation/gold |

RS方法和案例分开存储、通过有依据的关联连接。候选GET_RS交付单元必须在实验manifest中固定为单方法、单完整案例或确定性方法＋案例包；不让不同策略使用不同打包规则。原反馈是案例观察，不是GET_RS的收益标签。目标同源排除在打包前执行；未知祖先谱系不得被当作已隔离。

MP、ME直接以原文为证据，不只从摘要二次抽取。MS-SUM把信息放回会话过程；它与MP/ME出现同源内容是正常的，不代表应盲目去重。一次明确拒绝或偏好先放ME及MS相应上下文；未经稳定性和当前时点支持，不升级为MP永久属性。

## 2. 物理存储与目录

第一版采用可复核的UTF-8 JSON/JSONL，不依赖新数据库服务。下面路径是**新运行版本目录内部布局**，不是声称已经创建的生产目录。

```text
project/outputs/pm_rl1/resource_bank_v2/<bank_version>/
  manifest.json                         # 输入/编译器/各文件hash、使用范围
  sources/source_records.jsonl          # 不可变源记录；完整会话/方法原文
  sources/blobs/<sha256>.<ext>           # 原始文件字节，保留原格式
  resources/rs_methods.jsonl            # 一行一方法
  resources/rs_cases.jsonl              # 一行一完整案例
  resources/mp_assertions.jsonl         # 一行一事实版本，不覆盖旧值
  resources/me_events.jsonl             # 一行一事件/经历版本
  resources/ms_summaries.jsonl           # 一行一会话摘要版本
  resources/ms_raw_views.jsonl          # 一行一完整原文视图及来源引用
  provenance/claim_ledgers.jsonl        # 命题→原话跨度、审查、来源关系
  projections/<prefix_identity>.json    # 私有合法候选/MP时点投影，供构建器
  index/metadata.sqlite                # 可选；可由JSONL重建的查询目录
  index/embeddings.npy                  # 固定BGE向量，可重建，非事实来源
  index/vector_rows.jsonl               # 行号→内部资源身份与索引版本
  index/index_manifest.json             # 模型/分块/归一化/索引文本hash
  validation/schema_report.json
  validation/source_report.json
  validation/semantic_review.jsonl
```

实验结果写到独立的 `project/outputs/pm_rl1/<experiment_version>/evaluation/`。人工判定、裁判分、gold、实际回复、收益、策略选择正确性以及隐藏测试字段不得回写上述资源正文或检索索引。索引可以接入既有FAISS实现；首版不要求图数据库或额外向量服务。

完整RAW可在来源层只存一份，raw_view通过source hash引用它；运行时仍应实际展开并计入完整正文。磁盘去重不等于在线免费读取。审计侧表与reader正文分离，不能把几十条引文全部注入后仍宣称摘要已经压缩。

## 3. 共同字段与身份

配套 [resource_schemas.json](resource_schemas.json) 是JSON Schema draft 2020-12，可检验source、resource、provenance、index、evaluation五种记录的基本形状；具体schema名在 `$defs` 中。它是实现输入，不自动替代内容核验。

每个资源记录至少包含：内部ID、记录hash、head及表示版本、语言、owner（RS为null）、source_refs与family IDs、来源时序、真实构建时间、writer/prompt/runtime身份、审查状态、结构化body、reading_view及provenance引用。

`record_sha256`定义为删除该字段后，对其余记录进行UTF-8、键排序、无多余空白的规范JSON编码再求SHA256。原始blob hash与规范source-record hash分别存，不能把normalize后相等误称原字节相等。非有限浮点数不允许写入。变更源、字段、摘要文字、写入器/提示或表示方式均产生新记录身份。别名、替代、更正、冲突以显式边连接，不覆盖旧记录。

`reported_at`是报告/来源时间，`event_time`是事件时间，`built_at`是真实处理时间；未知值为null并注明未知，不能填造日期。历史数据只有日期或session rank时保留其精度。在线可用性还取决于任务ready_at；离线回溯物化标为reconstructed_offline，不假称当时已经建好。

## 4. 生成、更新与读取

### 4.1 共同离线编译接口

待实现统一接口：

```python
compile_resources(source_records, *, writer_identity, compile_config)
    -> resource_records, provenance_records, rejection_records, manifest

validate_bank(records, sources, provenance, *, scope_manifest)
    -> schema_checks, source_checks, chronology_checks, semantic_review_queue

materialize_at(prefix_spec, *, bank_manifest, representation_policy)
    -> private_catalog, projection_manifest

render_acquired(acquired_records, *, renderer_identity)
    -> sanitized_reading_blocks, exact_message_identity, native_token_usage
```

源文件加载/允许范围在调用前固定。写入器只接合法原文及来源metadata，不接未来目标问题、答案、收益、官方作者summary/observation。RAW无生成调用。方法解释、MP/ME抽取、MS摘要的模型输出只是候选；机械校验与必要语义审查分开。拒收保留原输入与理由，不能悄悄填成空摘要或零效果。

### 4.2 各类更新

| 资源 | 触发与处理 |
|---|---|
| RS | 新专业来源/新案例进入时创建候选；核出处、完整行动块、事实与适用范围。来源修订/审核变化另立版本，不根据目标生成赢家反选案例。 |
| MP | 新会话结束产生新的有证据事实版本。materialize_at先过滤严格过去，再处理明确更正；同时间冲突不自行投票。没有证据的“最新”不能自动替换。 |
| ME | 事件出现或有明确后续报告时追加。行动阶段由原话支持；前后是否同一事件需有链接证据。未知道结果保持unknown；无关事件不强合并。 |
| MS-SUM | 会话关闭后从该段完整原文独立生成，修订从原文重建。同会话任何中途目标都禁止使用其结束摘要；后台尚未ready时不可取得。 |
| MS-RAW | 会话关闭后冻结完整原文；重开/原文修订产生新版本。旧摘要仍绑定旧source hash，不能自动指向新全文。 |

同一源文可能支持多个视图。只合并精确重复且语义相同的陈述；时间、否定、作用范围或主体不同则保留。索引层可用同源关系避免重复候选，但不能删掉未读正文或让PM免费知道其内容。

### 4.3 四类资源运行时权限

| 信息层 | retriever/构建器 | PM/critic | G |
|---|---|---|---|
| 完整合法源库、owner/family IDs、未读正文/向量 | 内部可用，先做隔离过滤 | 不可见 | 不可见 |
| 当前公开前缀 | 可用 | 可见 | 可见 |
| 已取得reading_view及公开时间/状态 | 可用 | 可见；NoText另按消融遮蔽 | STOP后可见 |
| 来源hash及审计引文全集 | 用于来源校验和父文定位 | 私有hash/台账不可见；来源正文仅经已声明获取路径可见 | 所需来源正文可经已声明获取路径取得并计成本；审计台账不整份注入 |
| 私有评价、gold、目标未来、实际收益 | 仅独立评价域使用；不得进入retriever或资源索引 | 始终不可见，不能通过GET解锁 | 始终不可见，不能声明为资源后解锁 |
| 已读摘要的可见序号 | 可用于内部父文映射 | 可见 | 视renderer约定 |

资源库JSON不能直接作为Observation传入。`reading_view`由白名单投影，仅含正文、时间与必要历史状态，不带私有ID/标签/收益；呈现给PM的序号由获取顺序分配。所有已取得正文最终交给G，除非另立明确的表示替换实验；没有隐式退款或删减。

## 5. 检索和MS两阶段接入

索引先过滤owner、严格过去、split及目标来源家族，再用统一固定BGE；第一版不同时训练retriever。index search_text可包含有来源的实体/关键词，但不得用当前gold构建。保留原文检索入口，避免摘要删掉的信息永远不可召回。词面基线继续保留身份。

MS-S1只切换RAW/SUM表示，固定相同源会话集合、排序和G；不会因为SUM更短自动加会话，容量不同时报告共同可行集合及覆盖差异。`GET_MS`动作不变，schema/renderer/输入缓存身份改变。

MS-S2才定义可选原文回查，如 `EXPAND_MS(j)`（j为已经取得摘要的可见序号），或冻结共享的父文优先规则。当前生产代码均未实现定向回查。新混合域须给OneShot、BC、PPO相同能力，计原文检索、编码、输入及等待；单条原文超原生容量时显式不可行，不改名为截断“完整MS”。不新增任意top-4、4-GET、2048-token限制。

## 6. 编译器必须额外执行的跨记录检查

JSON Schema不能证明以下事实，必须另有验证代码与审查记录：

1. 所有source_refs存在且hash相同；span角色、segment、offset、quote精确一致，多个原turn ID命名空间不能混用。
2. 摘要/MP/ME的语义由原文支持，指代、否定、主体、时间、行动阶段未改变；引用存在不等于概括正确。
3. owner相同、source rank严格小于目标会话cutoff；MS-SUM来源已完整关闭，真实在线ready_at已到。RS目标家族/改写闭包已排除；未知谱系有明确处置。
4. MP更正图无循环，明确更正才改变时点状态；case行动/反应轮次连续且前情完整；MS-RAW无轮次缺失。
5. reader确实是白名单投影；JSON全文、评价分、未读向量、来源私有ID未越界。
6. 索引与资源identity绑定；模板/模型/正文变化使旧消息缓存失效；已记录实际reply的人评只按精确绑定复用。
7. 实际renderer在原生tokenizer下计算完整输入，溢出不截断、不静默跳过首项；GET不调用G/J/摘要器。

建议测试直接使用来源矛盾、同会话摘要泄漏、未知谱系、角色/offset错误、摘要与raw父文错配、读者越权、覆盖更正等反例，不只检查生成JSON能否被本程序读回。

评价记录另存`measurement_mode`。`paired_off`必须绑定同前缀冻结OFF的request identity；测量完成时还须绑定其实际reply SHA256，和被评终点的实际reply SHA256一起核验。`better/equivalent/worse`均表示终点相对该OFF，不能由其他配对传递推断。序数score若写入，只能与对应标签一致；尚未转换为奖励可为null。`absolute`无比较对象，单位及资格由独立protocol定义，不自动与配对符号分同量纲。配对的同前缀、同G/基础提示和实际回复一致性是跨记录校验，schema形状正确不能单独证明。

`pending_score`表示尚未完成评价；`completed_uncertain`表示评价已完成但不能可靠判断，必须保留实际reply及配对OFF，judgment为uncertain、score为null。最多一次预定语义复核，`semantic_review_round`为0或1；复核仍不确定就完成不确定记录，不永久pending，不填0，也不以成本负项代替未知质量训练。GET成本在轨迹中记录，首版终端奖励统一结算`r_quality − λ×C_online_total`；GET不再重复扣费。此处评价score只存质量信号，λ与完整在线秒数在独立轨迹/奖励合同中绑定。

可用既有环境重跑结构校验：`/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/docs/plans/pm_rl1_master_20261116/validate_resource_schema.py`。脚本内存fixture只是字段/状态测试，不是研究样本、奖励标签或来源真实性证据。

## 7. 尚待主方案闭合的依赖

存储结构与生成/读取机制已有具体设计；未解决的不是再挑一种文件格式，而是：统一writer实际保真率、专业方法的适用性审核、可靠帮助性反馈、未暴露英语纵向确认材料，以及资源收益是否足以覆盖真实成本。它们必须分别实测或落实人力/来源，不能由schema验证通过代替。
