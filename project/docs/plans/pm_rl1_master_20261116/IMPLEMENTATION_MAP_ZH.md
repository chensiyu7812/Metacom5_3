# PM-RL1 实施工作单与现有代码映射

2026-11-16（Asia/Tokyo）。这是主方案的实施附件，按当前文件和函数核对。本文只给方案，不执行模型、训练、付费或正式评价。所有新模块/命令均明确标为“待实现”；旧脚本的 `prepare` 也可能加载 tokenizer、读取冻结私有数据或生成新包，不能把名称当成无副作用保证。

## 1. 已有能力与必须补的连接

| 能力 | 已核实的代码 | 可复用部分 | 必须改动/补齐 |
|---|---|---|---|
| 完整严格过去会话 | `paper1/multi_view_memory/candidate_adapter.py`；`rl1/representation.py` | 原文、owner/rank/来源检查 | 新摘要正文另立身份，原RAW不覆盖 |
| 资源目录与获取 | `rl1/resource_organization.py` | OrganizedItem、规范交付、原生容量、逐步GET | `existing_item`目前只提取past_report/full_source_conversation/ai_action；`directory`硬读完整MS；必须支持新reader view |
| 原文绑定 | `rl1/resource_value_probe.py:match_session` | 原文与隔离合法历史精确对应 | 当前硬读`full_source_conversation`；新增按source hash/span绑定摘要的方法，不能让summary冒充raw通过旧函数 |
| 内容可见性 | `rl1/organized_policy_interface.py` | HeadSession、白名单Observation、无正文NoText、初始承诺程序 | 新摘要与混合扩读需要新interface identity；私有来源ID不进入actor |
| 检索 | `OrganizationCatalog.rank`；QA脚本176中的BGE路径 | 当前词重叠作为历史对照；BGE来源/向量校验方法 | 新共享retriever适配器，明确过滤、查询更新、排序及tie-break；BGE状态编码不等于检索已接通 |
| 全可见正文编码 | `organized_features.py`、`organized_encoding.py` | 原生窗口分块、缓存、向量身份、计时 | 摘要/新资源正文改变即重新绑定；池化信息损失另测，不等于信息无损 |
| 实际回复与内容身份 | `organized_feedback.py`、`generation.py`、`cache.py`、`cached_generation_worker.py` | 完整messages、实际G/runtime/token/draw绑定，缺测pending | 新Gemma/renderer须接对应生成适配器；不只凭模型目录名复用Llama/P2缓存 |
| 人评连接 | `human_reference_reuse.py`；脚本139 | 原证据和实际回复精确匹配 | 新回复必须新判断；55异质记录不能统一冒充55奖励样本 |
| 监督与反馈共享 | `organized_supervision.py` | prepare_targets、prepare_supervised、comparison_union | 新反馈契约与成本；未测计划保持未知，不给OneShot较少反馈 |
| BC/PPO协调 | `organized_learning.py`、`qualified_learning.py`、`organized_rollout.py` | 优化、checkpoint、恢复、策略版本/轨迹绑定 | 当前资格/固定规模假设须适配，不能把新机制实验包直接塞进去 |
| OneShot | `organized_oneshot.py:ProgramReturnModel` | 初始视图、可变长度程序、预测收益搜索 | 冻结搜索预算；当前`formal_search_budget_frozen=False`，不声称穷尽最优 |
| 完整参考客户端时间 | `client_latency.py`、`latency_serving.py` | client send→首/尾文本，阶段计时与超时记录 | 目前是local_reference_queue_client；网络/Tokkio语音桥接另做 |
| 官方能力评价 | `esc_rank_runtime.py`、`esc_eval_official_parser.py`、`paper1/execution/dg_official.py`、`paper1/evaluation/static_official_scoring.py` | 官方解析、prompt及部分运行模板 | 为新最终系统建立独立runner/输入绑定；不把旧冻结脚本换输入后仍称原实验 |

以上路径默认相对`project/src/metacom_pm/`；脚本路径见第4节。Tokkio部署代码未在本轮仓库文件名扫描中发现，不能据此断言整台机器不存在，但也不能把当前参考队列脚本称为已完成Tokkio接入。

## 2. 最容易导致“方案看似齐全但跑不通”的四处

1. **反馈与成本接口不是即插即用。**`OrganizedEpisode.__init__`强制`type(cost) is TokenCost`；`QualifiedRoute`要求旧q/m资格及`QUALIFIED_MEASUREMENT_USE`，`OrganizedRun`也检查这些绑定。新的人工配对反馈和真实秒数目标必须另立可验证适配器。不能伪造旧资格通过检查，也不能把旧token惩罚和新秒惩罚重复扣除。
2. **训练规模写死在旧协调器中。**`make_run_manifest`要求12 owners×8＝96 train前缀、3 owners/18 dev、seeds17/29/43；当前收集batch为16。新12开发＋24诊断是机制实验，不是现成可训练清单。需要参数化新分组/规模manifest并留住旧回归。
3. **正式保留集路径尚未开放。**当前`OrganizationCatalog`只接受`train/dev`。最终确认材料不能改名为dev以绕过检查；需独立只读评估构造路径/用途控制，禁止其产物进入训练。
4. **原文扩读和语音端点未实现。**`GET_MS`只取当前MS排名首项；`EXPAND_MS(j)`尚无动作/特征/OneShot实现。参考客户端也没有Tokkio用户话语结束、首个有效语音和语音完成事件。这些是明确的后期工程任务。

## 3. 依赖顺序和工作单

主入口使用P00–P17编号，本文I0–I11是实现切片，不是第二套进度。对应为：I0→P00/P01；I1→P03；I2→P05/P06/P07且依赖P02；I3→P02/P07/P10；I4→P08；I5→P04/P09；I6→P02/P04/P10；I7→P10/P11；I8→P09/P12；I9→P13；I10→P14/P15；I11→P16/P17。以主方案工作单的状态为唯一进度。

主方案已选定新接口默认：所有方法共用显式容量/头耗尽STOP保护层，OneShot称OneShot-Guarded；旧step/replay的raise语义保留原身份，新版本需单独实现与测试。Random仅按开发实测校准并冻结，不按确认耗时事后匹配。来源/hash/owner错误不能被保护层改成正常STOP。

每一单关闭时必须保存`input_manifest.json`、源/代码/协议hash、实际产物清单、检查结果与结论范围。建议新运行根目录为`project/outputs/pm_rl1/master_20261116_v1/<run_id>/`，每次身份变化另立run，不覆盖旧结果。以下文件名是待实现的新产物合同，不表示文件已经存在。

### I0 统一输入和暴露用途

- 输入：11/15版本复用清单、24源会话审查、12RS候选、3方法草稿、3MS摘要样例、现行曝光metadata。
- 实现：来源登记/祖先家族闭包、source hash、合法切点、development/confirmation用途表。只从既有隔离train/dev导出建立开发资源，不重新读取废弃来源。来源未知不能默认独立。
- CPU验收：同owner严格过去；当前源会话末尾摘要不能用于本会话中途；目标同源RS/改写/视频排除；缺失家族标pending；同一请求旧复用必须精确匹配实际回复。
- 输出：`source_registry.jsonl`、`family_map.jsonl`、`exposure_registry.jsonl`、`version_dependency.json`、`reuse_join_report.json`。
- 下一步：开发可继续；独立确认不足同时进入补源任务，不等训练结束才处理。

### I1 四资源写入与读取视图

- 输入：I0合法来源和`RESOURCE_SPEC_ZH.md`/schema。
- 待实现：版本化资源编译器；分别生成RS方法/案例、MP时点槽位、ME事件阶段、MS_RAW/MS_SUM。摘要writer只读已结束源会话，不读目标问题或gold；生成发生在GET之前。
- 最小改动：为`existing_item`显式选择reader/search text；更新`directory`的MS分支；摘要来源绑定不调用假定raw正文的`match_session`；保留old schema可重放。
- CPU验收：挂电话/工作坊/社群/指代四类反例；错误source hash、错speaker、错offset、未来summary、未完成session、未知当前状态被升级等必须拒绝；完整MS原文逐字可恢复；审计引文不默认注入摘要reader。
- 输出：`resources/*.jsonl`、`source_anchors.jsonl`、`writer_manifest.json`、`reader_payloads.jsonl`、`resource_validation.json`。schema通过不替代专业适用性或语义审查。

### I2 同源RAW/SUM表示包和资源机制包

- 输入：I1通过来源检查的候选、冻结开发G及tokenizer、目标前缀/来源家族manifest、事先确定的反馈协议。
- 待实现：新只物化payload的比较脚本；复用`OrganizedRenderer`思路，冻结实际messages与原生token；准备阶段不得调用G/J。
- RAW/SUM子实验：固定同源会话、排序和其他资源，OFF/RAW/SUM；可选SUM＋RAW诊断单列，不称按需回查。RAW超容量项单列，不能截断或静默删除。
- 资源机制实验：B/F/R/M/MF/MR/D_R/D_M与原七配对；不自动做所有摘要版本×所有条件的大网格。每个condition有精确来源、适用状态、未适用原因和request identity。
- CPU验收：OFF为空可选资源；同目标G及基础指导一致；错配资源也是真实来源；所有目标未来和评价标签不出现在messages；去重只在精确请求一致时进行。
- 输出：`prefix_manifest.jsonl`、`condition_payloads.jsonl`、`request_registry.jsonl`、`comparison_plan.json`、`capacity_report.json`、`generation_manifest.json`。
- 进入生成前必须收口：G/runtime、资源/renderer、帮助性量表、评审安排、源分组统计、补测上限和预算；这不是再次询问研究方向。

### I3 实际生成、盲评和结果连接

- 复用：`LocalNaturalGenerator`及当前Gemma候选运行参考、GPU guard、原子请求账本/缓存、实际EOS记录。脚本167/176/178是历史协议参考，不直接覆写它们的冻结输入。
- 待实现：绑定新manifest的通用runner和盲评导出/导入；提交人评的顺序盲化、反向呈现或重复校验依预定协议，不靠人工挑赢例。
- 验收：自然结束/超时/失败分开；缺生成或反馈保持pending；人评绑定准确current prefix、实际reply hash及合法证据；回复编辑或G改变使旧偏好不可直接迁移。
- 输出：`generation_results.jsonl`、`attempt_ledger`、`blind_presentations.jsonl`、`feedback_receipts.jsonl`、`mechanism_results.json`。
- 分支：资料不足修资源；G误用做I4；检索问题留I5；测量不足改锚点或人工有限表。负面结果保留，不反复补抽同协议直到通过。

### I4 条件执行适配与G0/G1绑定

- 复用参考：脚本87/88/91的P2训练/诊断/冻结流程、脚本163/164/165/166的后续修订；其中旧弱目标不作为新帮助性金标。
- 待实现：同前缀相关/无/无关资源成组监督数据，事实与约束变化有原文支持；OFF目标不得泄漏隐藏历史。独立分组开发用于epoch/adapter选择。
- 验收：不仅NLL下降；比较G0与G1各自ON−OFF、无关记忆误用及基础支持质量。保持同训练预算与数据来源记录。adapter/runtime/chat template/decoder各自hash。
- 输出：`conditional_supervision.jsonl`、`adapter_manifest.json`、`G0_G1_results.json`、`executor_decision.json`。
- 分支：无可保留G1时保留G0并报告RQ-X范围；RQ-SX保持未回答，不能用单G结论代替。

### I5 共享实际检索与检索效果保留

- 待实现：共享BGE检索适配器。先合法过滤后排序；定义静态prefix查询和动态prefix＋acquired查询版本，tie-break、重复来源、RS子类型组装统一。保留词面基线。
- 复用：QA176的完整来源/BGE向量绑定方法；`organized_encoding.py`仅用于状态编码和缓存，不作为检索已经完成的证据。
- CPU验收：改变隐藏候选正文不得直接改变actor输入；改变被取得正文可按公开规则改变下次查询；OneShot/BC/PPO调用相同locator；未取得向量和gold不入Observation；缓存不能跨encoder/query版本误用。
- 输出：`retrieval_manifest.json`、`ranking_receipts.jsonl`、`retrieval_vs_direct_results.json`、`retrieval_timing.jsonl`。
- 进入策略学习：检索路径可重放，错误类型和实际收益保留已测；直接有用而检索失效时先修检索。

### I6 新反馈与真实成本适配

- 待实现：`EffectObservation`和`MeasuredCost`的版本化合同；允许有效人工配对、独立维度判断、tie、uncertain、pending、technical_failure分别存在。旧q/m分数与新配对效用不静默互换。
- 真实秒数成本接`client_latency.seconds_return`或新适配器，但当前函数只给`candidate_not_training_qualified`，尚未接PPO。决定使用绝对等待还是ON相对OFF增加、主要端点及权重/约束时，所有方法一致且在确认结果前固定。
- CPU验收：pending不入优化；同一结果只结算一次；秒成本不同时再扣token代理；trace/runtime/deployment不匹配拒绝；人工有限表没有的terminal返回unknown。
- 输出：`feedback_contract.json`、`cost_contract.json`、`measured_terminal_table.jsonl`、`feedback_coverage.json`、`measurement_use_record.json`。
- 有限人工表分支：只在实测终点支持的范围内做有限计划学习；不得对任意新PPO终点插值填零。扩大on-policy探索之前须有取得新可靠反馈的可运行路径。

### I7 固定、OneShot和BC

- 复用：`organized_supervision.prepare_targets/prepare_supervised/comparison_union`、`organized_oneshot.ProgramReturnModel`及原MLP训练基础。
- 待实现：新run manifest与协调器配置，分组train/dev规模由清单决定；旧96/18、batch16、seeds17/29/43配置保留为历史回归，不被新机制样本冒充满足。
- 验收：全部方法使用同反馈union、可见信息、retriever、G和成本；OneShot只基于初始Observation选完整程序，不用未来正文筛可行性；冻结搜索计算预算，报告近似搜索而非全局最优。
- 输出：`policy_training_manifest.json`、`shared_feedback_union.json`、`baseline_checkpoints/`、`baseline_results.json`及可复现训练日志。

### I8 顺序、PPO与可选原文扩读

- 复用：`OrganizedRun`、`OrganizedRollout`的恢复/轨迹/优化流程，改动只在新domain、feedback、cost和schedule适配处。
- 先在四头GET域比较BC/PPO、OneShot、简单停止及NoText。当前NoText只遮PM已读正文，retriever仍可用正文；需另加固定查询对照才回答整个系统的读后检索价值。
- 混合MS域是独立扩展：新增`EXPAND_MS(j)`或明确共享父文优先规则，更新action schema、mask、policy head、program encoder与baseline；j是已取得摘要的公共序号，内部source ID不进入actor。不是把一个新动作塞入旧range(5)代码。
- 验收：新动作非法索引/未读摘要/重复扩读/超容量拒绝；原文实取、实交付、实计费；已读摘要不退款；比较方法同域。G/J仍只在STOP路径，扩读不调用摘要器。
- 输出：`sequential_results.json`、`no_text_and_fixed_query_results.json`；如实施混合域另有`hybrid_domain_manifest.json`和其同域结果。

### I9 G与PM原配/交叉换配

- 前提：I4有可保留G1，I7/I8分别训练PM0/PM1。
- 实现：相同冻结评估前缀上G0+PM0、G0+PM1、G1+PM0、G1+PM1；两G各保留相同简单基线。反馈仍来自各G的实际回复，训练反馈预算公平，不能跨G拷贝效用标签。
- 验收：renderer可兼容但G/tokenizer/runtime各自绑定；评估不更新PM；失败/不可行独立记录；数据分组不因换配改变。
- 输出：`cross_pair_manifest.json`、`G_PM_cross_pair_results.json`，解释RQ-SX及资源价值随G变化的范围。

### I10 冻结最终评价

- 待实现：只读heldout构造入口；把source split与用途分开验证，不能为了通过当前train/dev检查改标签。最终manifest先冻结G/PM、资源、检索、renderer、测量、种子及报告表，再揭示确认结果。
- 官方ESC-Eval：复用官方7维parser/adapter/runtime，角色秘密只给seeker。新增完整对话运行adapter；Claude分支仅是实现参考，先核分支身份与曝光。
- ES-MemEval：QA/Summary/DG按原官方协议分表报告；单轮自然帮助性是另一表。`static_official_scoring.py`是parser，不是自动完成全实验的runner。
- 独立自然支持：使用已核定家族/owner来源；确认材料不足时报告范围，不把历史已见材料改名未见。新的指标/提示不可冒充官方原版。
- CPU验收：heldout无训练引用；来源/曝光分组可查；解析失败不填0；裁判原始输出、解析版和任务单位保留；禁止在最终结果后选G/threshold。
- 输出：`final_freeze.json`、`official_ESC_results.json`、`official_memory_results.json`、`independent_support_results.json`、`failure_registry.jsonl`。

### I11 完整等待、Tokkio与研究收口

- 复用：`ReferenceStreamClient`和`latency_serving.prepare_online/stream_generate`做本地完整路径；现脚本154是旧固定情境协议，创建新manifest版本。
- 待实现：Tokkio transport与事件桥接，记录用户话语结束、ASR完成、PM/检索/编码、G首有效文本、TTS首有效语音、语音完成。首个有效内容不以占位声/无内容ack代替；实际网络并发与硬件/cache策略记录。
- 比较：相同G和场景配对、方法顺序交替/随机、暖机与冷启动分开，失败等待保留；写入摘要成本另报并按实际访问次数摊销。秒数代理不能当正式部署实测。
- 输出：`deployment_regime.json`、`client_traces.jsonl`、`speech_traces.jsonl`、`quality_wait_frontier.json`。
- 完成标准：主方案各RQ有结果或明确未回答范围；方法、来源、原始结果、代码/模型/协议版本、统计、局限和复现runbook齐全。正面假设未成立不等于可以伪造“完成”；若某外部依赖未取得，论文的对应主张必须收窄或保留未完成。

## 4. 已存在的入口与命令边界

以下CLI参数从源码argparse核实；**它们是现有历史协议入口，不是新主方案的一键runner**。只有在明确需要复核旧包时使用，不能让新输入覆盖其固定输出目录。

| 已存在脚本（相对project/scripts） | 已有参数/模式 | 作用与注意 |
|---|---|---|
| `rl1/131_prepare_resource_organization.py` | `--audit --output --tokenizer-dir` | 旧资源组织物化；加载tokenizer，需新schema适配 |
| `rl1/138_prepare_organized_policy_interface.py` | `--organization --output --g-tokenizer --bge-tokenizer` | 旧五动作接口和特征计划 |
| `rl1/139_audit_human_reference_reuse.py` | `--output` | 旧参照复用审计；新请求应走新精确join |
| `rl1/140_check_organized_learnability.py` | `--output --episodes {16,128}` | 学习机械验证，不是自然支持正结果 |
| `rl1/141_prepare_organized_training.py` | `--output` | 旧固定来源训练准备；不得直接套新36样本 |
| `rl1/142_encode_organized_training.py` | `--package --output` | 真BGE编码，不是纯CPU结构检查 |
| `rl1/143_generate_organized_initial.py` | `prepare/check/execute; --package --output --approval` | 实际生成入口；执行记录需与具体manifest及既有授权绑定 |
| `rl1/145_validate_organized_initial.py` | `--package --encoding --output` | 旧包验证 |
| `rl1/154_measure_reference_client_latency.py` | `prepare/run/summarize; --output` | 本地参考客户端，不是Tokkio |
| `rl1/176_probe_qa_resource_gain.py` | `screen/encode/controls/prepare/run/collect; --output` | 旧QA完整协议；encode/run均有实际计算 |
| `rl1/178_probe_typed_resource_views.py` | `prepare/run/collect; --output` | 旧42次typed协议；不是新summary实验 |
| `paper1/80_execute_official_static_scoring.py` | `--package --bound --out --execute --limit --timeout` | 旧QA/Summary执行器；可能付费，不能直接作为新授权 |

新增命令建议集中为**待实现**的`project/scripts/rl1/master_workflow.py`，提供`validate-sources / compile-resources / prepare-comparisons / collect-feedback / train-baselines / train-sequential / evaluate / measure-deployment`子命令。每个子命令先有`--manifest --output --preflight-only`，生成/训练/付费操作不得由preflight触发。该文件当前不存在，工作单先实现它再运行，不在本附件中给出伪可执行的新命令。

## 5. 现可运行的CPU回归命令

以下命令从项目根目录执行，使用本机已存在的Python环境；只运行公开fixture，不依赖私有输出或下载模型。它们验证当前基础，不表示新实现已经通过。本轮未运行这些测试，因为本轮只整理方案。

```bash
cd /home/tokkio/Metacom5_3/project
PYTHONPATH=src /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q -m 'not gpu' tests/test_rl1_resource_organization.py tests/test_rl1_resource_value_probe.py tests/test_rl1_typed_resource_views.py tests/test_rl1_organized_policy_interface.py -o addopts=
```

修改反馈/训练适配时执行对应现有回归：

```bash
PYTHONPATH=src /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q -m 'not gpu' tests/test_rl1_organized_supervision.py tests/test_rl1_organized_learning.py tests/test_rl1_organized_learning_bridge.py tests/test_rl1_human_reference_reuse.py tests/test_rl1_client_latency.py -o addopts=
```

新功能必须补真实边界测试：摘要源会话未来泄漏、来源hash更换、训练/确认分流、人工未知反馈不优化、实际秒成本不重复扣除、共享检索一致性、扩读权限/容量。不要仅断言新文件输出等于自己的快照。修改范围完成后，按仓库CI执行一次`tests/test_paper1_*.py tests/test_rl1_*.py`非GPU套件；无新变更或未解决失败时不反复全量测试。

## 6. 每次接续的最小执行规则

1. 读主方案、状态与下一未完成工作单，核对实际产物和hash；历史pending不能覆盖后来完成记录。
2. 先复用现有明确可用组件，只新增本单接口；遇到上述硬编码限制就写明适配，不绕过检查。
3. 本单的CPU预检和实际run分别记账；数据、生成、反馈、训练、确认结果五种完成状态不能互相替代。
4. 使用已有授权推进；旧Paper-1限制不否决已授权RL1或summary候选。新的实际调用按具体范围核对，不因脚本有`--approval`参数就机械重复请求方向许可。
5. 付费仍共享既有总账、在途责任额与USD20硬上限，不按阶段重置；指定GPU被占时不终止其他项目或偷换设备。
6. 对真实未解决的外部依赖，记录可继续的并行工作和会受影响的主张。不得用“方案已写完”冒充研究完成。
