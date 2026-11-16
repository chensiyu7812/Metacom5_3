# PM-RL1 数据与现有工具核验（2026-11-15）

本稿是综合研究审计的只读证据附件。核验范围为公开源、活跃派生资产、官方代码/论文与本地适配代码；未运行模型、训练、付费评分，也未修改研究合同。未读取已禁用的 11/80 用户自造纵向数据。现有记录中的旧结果保留原身份。

## 关键结论

1. **EvoEmo 的 18 个构造人物、401 段会话是当前公开全量，不是本项目只下载了一小部分。** 本地 `project/data/external/evo_emo.json` 为 4,482,088 字节，SHA256 `f30698e87fddaeff51270a666c654da604f487a3456ec60d2b6ae08a6fecd420`，Git blob `debae3bb229f56654f13ead9d5d7470c7ece9b11`。本次用 `git hash-object` 独立计算，与官方 pinned commit `692624208acc077b8867698c1d6fcd998dee641a` 和今天 main 的同一文件元数据完全相同。新增版本下载不能凭空扩大人物数。
2. 当前自然前缀 train/dev/test 96/18/48 是项目抽样；可重新普查 train/dev 的更多合法前缀来估计覆盖，但多切几个前缀不会增加独立人物，也不能据生成结果挑正例。旧 10 个历史价值测试是受多重条件约束的样本，不能把 10/96 解读为“只有 10% 需要记忆”。
3. **工具是可用的，但各自测量对象不同。** ESC-ROLE 提供可复现模拟交互，ESC-RANK 提供官方七维外部比较，ES-MemEval QA 提供记忆事实/时间/冲突/未知能力，Summary 提供整合能力，DG 提供受控记忆表现。这些都没有直接提供“资源对当前自然支持的增量帮助性”标签，也没有提供“读后还要不要继续”的标签。
4. **有一个值得优先复用的旧资产：1,924 条 QA/Summary 剂量生成已经完成。** 不能再写“全是准备包”。但未发现已完成官方评分；1,631 个去重评分 payload 仍 pending。可复用生成做低成本来源/长度/差异和部分事实核验，不是现成 RL 自然支持奖励。
5. ME 中 `action_observed_outcome=4`、非空 outcome 文本 7 是抽取产物统计，不是原始会话的完整语义普查。**目前无法下结论说来源只有四条有效行动史，也无法承诺重新抽取就一定足够。** 应用小型人工召回审查区分抽取遗漏与来源确实缺失。
6. 最需要补的桥梁是：同一合法自然前缀下，不同真实来源资源带来的、经过人工核验的支持行为和帮助性变化。不是再找一个大模型总分，就能把现有所有数据拼成这个桥梁。

## 1. 数据资产与身份核验

| 资产 | 本地事实 | 已有价值 | 不能自动得到的证据 |
|---|---|---|---|
| ESConv | 1,300 对话；18,376 条 strategy 标注；7,681 条 feedback 标注；本项目 split 为 train 934 / validation 186 / test 180 | 支持策略示例、完整情境、原始用户反应、SFT/RS 开发来源 | 每一种策略的因果效应；对新 G 的外部资源增量；逐条专业临床适当性 |
| ESConv RS bank | 活跃精确处理单元 13,172 | 已有来源定位、检索、去同源机制；可重用索引与原文定位 | 13,172 个独立方法/知识点；每条适用条件已知；支持效果标签 |
| FailedESConv（官方补充） | 官方仓库明确公开 196 个原采集负样本；本次未加入本地活跃数据 | 可作为失败模式和低反馈案例的补充候选，降低只看成功对话的偏差 | 不能把整段失败归咎某个句子或策略；不能将新来源自动混入旧冻结 train/test |
| ESC-Eval | 本地英文 331，中文 324；英文 ESConv 源 158、非 ESConv 源 173 | 可复现外部交互测试与跨来源切片 | 自然真人疗效、长期记忆轨迹、单轮 PM 正确动作标签 |
| EvoEmo | 18 构造人物、401 会话；本地与官方当前 main 同字节身份 | 严格过去历史、实体/时间/冲突证据、多会话支持上下文 | 18 位真实用户随访；大规模独立泛化；丰富行动—后果证据已被证明 |
| ES-MemEval Public | QA 1,427；Summary 125；DG topic 34 | 分任务的记忆外部评测、源证据核查、检索/停止工程验证 | 用 QA 正确率替代自然支持质量；用 DG 记忆引用替代用户收益 |
| 历史 QA/Summary 剂量生成 | 148 targets × 13 conditions = 1,924 条；85 QA、63 Summary；全自然结束；1,631 unique scoring payload | 无新 G 调用即可检查剂量、重复、错误、低成本事实子集 | 当前 Gemma/P2 下的结果；当前无硬 cap 新动作域的效果；已合格评分标签 |

关键本地定位：

- `project/configs/paper1_public_only.yaml:55`：ESConv hash、ESC-Eval commit、ES-MemEval version/hash。
- `project/src/metacom_pm/paper1/data/materializer.py:42`：1,209 论文计数与 1,427 公开身份、18/401/125/34。
- `project/src/metacom_pm/paper1/data/es_memeval.py:26`：公开版本与论文版本边界。
- `project/data/paper1_authority/esc_eval_english331_source_overlap_summary_v1.json:6`：331/173/158 及来源分布。
- `project/docs/PM_RL1_DATASET_DIAGNOSTICS_AND_RESEARCH_PATH_20260930_ZH.md:19`：活跃数据普查与局限；该文件含历史状态，不能把旧 155 SFT、2048/4 GET 等沿用为当前状态。
- `project/docs/PM_PAPER1_STATIC_AMOUNT_EXECUTION_20260917_ZH.md:141`：2026-09-19 追加完成记录；149 行为 1,924 完成，170 行为 1,631 去重 payload。

本次直接复算结构（不读取测试答案内容作为设计反馈）：ESConv 1,300；strategy 字段 18,376；feedback 字段 7,681；EvoEmo 18 人、401 session、355 question groups 内 1,427 questions、125 summaries、34 subsequent topics。注意这些不是独立实验样本数。

论文 Table 2 同时写了 18 人/401 会话和平均 27.2，会与 401÷18≈22.28 不一致；报告应以可复算公开原始计数为准，不传播 27.2。也不能自行删 218 道 QA 来凑论文 1,209。

## 2. 如何把 ESConv 真正用于 RS

应复用已存在的训练 split、来源 ID 和检索骨架，改变的重点是**被检索文本到底提供什么**。现有一个支持者回复 + 策略指令，只测试有限形式的策略提示/风格样例，不等于完整的决策案例。

建议的新资源构造（待新版本，不覆盖原 treatment）：

1. 从 train 对话定位目标支持行动，保留行动前公开情境、完整支持行动、随后可观察反应和明确反馈的距离/覆盖范围。
2. 将“原文事实”“原始反馈”“研究者解释”“未观察到的结果”分栏。反馈通常不是逐个策略独立随机试验，不能写成该策略有效的因果证明。
3. 加入适用线索和不适用边界；若由模型推断，标成待验证解释，不能冒充外部专业知识。真实需要专业依据的部分，需外部方法来源或专业审查。
4. 保持 AI 身份衔接。人类 supporter 自我披露可以作为案例材料，却不能要求 G 编造自己的亲身经历。
5. 新 RS 只通过实际对照证明价值：OFF、强通用指导、适用完整资源、匹配长度/话题但不适用资源；先直接投递检验内容价值，再测检索。

潜在外部资源价值不要求模型参数里绝不存在相同知识；它至少要在固定部署 G 上补足可靠执行、具体情境匹配或可查证依据。若同样内容变成一段短常驻提示就稳定有效，应比较常驻版本，不能将检索开销本身算贡献。

ESConv 官方 FailedESConv 的 196 个失败对话值得作为**有明确目的的新增候选**，补失败现象与反馈范围，不是必须全部导入。应先做 source overlap 与许可确认，再另分开发/确认用途。它与 ESConv 属同采集家族，不能自称独立跨来源验证。

## 3. ESC-Eval / ESC-ROLE / ESC-RANK：有用且应分工

**官方交互流程可复用。** 作者代码 `evaluate.py` 先给 ESC-ROLE 角色卡，再进行 5 轮 seeker→supporter，得到整段对话；角色卡和模拟器秘密信息不能给 PM/G。`score.py` 对完整对话调用七个英文/中文 adapter。当前 main 是官方作者/实验室路径，项目正式重现仍应绑定已有 pinned commit。

| 部件 | 建议用途 | 输入/输出与实施 | 限制与必要核验 |
|---|---|---|---|
| ESC-ROLE | 冻结系统后的外部交互压力测试；开发中少量检查回复是否造成循环/信息推进 | 角色卡只给 seeker；PM 每轮看到当前公开对话；STOP 后 G 回复再喂 seeker；保存全部消息和资源 hash | 不是人类，模拟偏差要披露；同一轨迹的五轮不能当五个独立用户；修改一个系统回复后不能继续复用另一个系统的既定后续当作真实反事实 |
| ESC-RANK | 七维官方结果表；辅助发现大类退化；人评校准后可考虑范围受限的开发排序 | 使用现成 runtime 和官方 parser；记录每维 raw 输出与 parsed score；全模型共用同一模板/adapter身份 | 不能默认把 0–4 粗粒度对话分数当微小单轮 RS 收益奖励；官方 Humanoid 口径含风格/AI表述倾向，不能解读为临床有效性 |
| 来源切片 | 跨源测试 RS 是否只学会 ESConv 风格 | 173 非 ESConv 英文卡为既有主迁移切片；158 同源为敏感性切片；保留完整 331 结果 | 既有校准/确认划分与历史曝光需逐条账本核对；Claude 新开发用过的卡不能再自称未见 |

可落地接口位置：

- `project/src/metacom_pm/esc_eval_official_parser.py:17`：官方按字符 0→4 首个包含值解析；strict 全字符串只作为补充诊断。
- `project/src/metacom_pm/paper1/evaluator_qualification.py:28`：官方 prompt 顺序与项目七维命名映射。
- `project/scripts/paper1/35_score_official_esc_rank_blind_qualification.py:99`：从 pinned `score.py` 读取 prompts；该脚本是资格核验 runner，不能改名当正式评价。
- `project/src/metacom_pm/paper1/execution/rq1_prompts.py:80`：既有 supporter request 构造；原 Paper-1 固定输出 cap 与当前 RL1 自然结束不同，迁移时明确版本而非静默混用。
- `project/scripts/paper1/82_audit_rs_and_dg_calibration_readiness.py:58`：本地 G + 本地 ESC-ROLE + 本地 ESC-RANK 可无付费 API；瓶颈是 GPU 时间；旧五点剂量网格只是当时规划，不能自动移植为当前新实验。

**低成本优先用法**：先复用已有轨迹与评分做误差分类，回收已经交付的人评用于诊断；在资源机制实验中仅对冻结的少量条件做外部多轮核验；最终系统冻结后再跑共同完整协议。不要为每个提示微调都跑所有卡×所有剂量×七维，也不要用不断换裁判代替资源效用证据。

## 4. ES-MemEval / EvoEmo：事实验证、能力外评与自然支持要接好边界

**QA 是当前最明确可以推进的支线。** 它能检验取回事实、跨会话推理、冲突、弃答、停止，但这些任务要用相应题型/分母报告。官方 gold 可在评价域使用；PM 的运行时不能看到 gold/evidence 指针。自然前缀不能直接继承官方完整历史 QA 的答案，因为时间可见性不同。

**Summary** 适合检查是否保留事件链、时间与关系，把 MP/ME 的短视图与完整 MS 对照。可以先复用旧 819 条输出和已审查来源，减少新 G 生成。官方 event-level 指标依赖评审，不能用 ROUGE 自动替代语义正确性。

**DG 是有价值但偏向“展示记忆”的能力测试。** 官方 supporter prompt 明确要求表现记得，即使相对当前话题不太相关；官方 seeker 也被要求用隐晦线索引出历史回忆。源码依据：

- `project/src/metacom_pm/paper1/execution/dg_official.py:85`：模拟 seeker 被要求诱导回忆。
- 同文件 `:124` 和 `project/src/metacom_pm/paper1/execution/rq2_prompts.py:83`：supporter 显示记忆指令与 60-token cap。
- `project/data/paper1_public_memory/es_memeval_public_official_visibility_audit_v1.json`：36 个 pinned source 文件、完整数据表面、RAG query、截断及 scoring 可见性审计。

因此 DG 可以回答“系统是否正确利用相关个人历史”，却不能单靠其 weighted score 证明“用户真正更获支持”或“该调用而调用”。应保留官方评价并另列自然支持帮助性，而非修改官方 prompt 后继续沿用官方名称。

官方主 RAG 使用 BGE-M3、FAISS、session-level Top-4；QA/Summary 查询是当前问题，DG 是每轮最新 seeker utterance。QA/Summary 官方组装输入存在 16K budget 的尾部截断；DG 官方运行 10 轮，supporter/seeker 输出 cap 60。Full-History 的“源库存完整”不代表实际 prompt 全部保留；需记录真实输入和被截断内容。

运行时隔离已有强基础：`project/src/metacom_pm/paper1/data/materializer.py:70` 的 sanitized loader 只读取合法 ID、时间、原始 dialogue 和任务问题；不读 observation、summary、主题、basic_info、答案、evidence、未来场景说明。旧组件可继续复用，不需要推倒重建。

建议的适配次序：

1. 将 QA/summary 源证据审查与旧生成结合，先确认 MP/ME/MS 各自保存和丢失哪些所需信息；保留 Unknown/不可观测，不能挑只适合 MS 的题再评四头。
2. 用当前主 G、当前共同检索器验证强固定 1/2 条、简单停止、OneShot；旧结果只作开发参照。
3. 在自然支持中建立独立“历史改变当前回复决策”的桥接材料：原始当前前缀 + 严格过去来源 + 能核验的上下文误解/重复建议/偏好冲突；最后用人评判断是否更有帮助。
4. 桥接材料按生成前来源特征选择；同时保留普通不需记忆的情境；不能只保留生成后赢 OFF 的样本来估计自然收益率。
5. 资源有效且存在情境差异后才学习调用；只有读后信息改变后续资源选择/停止才承担顺序主张。

## 5. 还缺什么，如何补而不绕圈

| 缺口 | 现有资产能否直接补 | 有边界的补法 | 何时停止或调整 |
|---|---|---|---|
| RS 方法/案例是否具有增量价值 | 现有反馈、策略标注只是候选依据；旧短指令结果不充分覆盖完整案例构念 | 小型来源完整资源 + 适用/不适用对照；生成前固定条件 | 一次针对明确失败原因修订后独立确认仍无效，不能继续无限扩库找正例 |
| 原始历史中的行动/偏好/结果覆盖 | 抽取统计不能回答；原文仍在 | 从 train/dev 按人物/主题分层抽固定历史，人工标“意向/建议/已尝试/主观反应/后果未知”，与抽取召回对比 | 召回好而来源稀少→补外部纵向来源；召回差→修抽取，不需要换整个数据集 |
| 自然支持帮助性标签 | 旧人评是有限开发资产；官方评分不等于此标签 | 事实依据核验 + 盲评增量帮助性，保留平局和不确定；限定自动评分使用范围 | 无法分辨→缩小主张/增加针对性人工证据，不强行填零开训 |
| PM 动作好坏标签 | 不由策略标签或 observation relevance 自动给出 | 同一前缀不同合法读取条件的实测质量与等待表；允许多个相当动作 | 如果同一固定方案支配所有情境，报告固定方案，不能强行均衡四头 |
| 顺序获取必要性 | 现有基准没有直接提供 | 观察真实资源内容是否改变下一最优 GET/STOP，比较同域 OneShot | 无差异→主张停在条件选择；PPO 不可替代顺序信息价值证据 |
| 独立人群/真实多次支持 | 当前 18 构造人物与模拟器不足 | 查找合法可用真实纵向支持语料；若没有，需另外设计有同意/审查的采集，或明确受限合成基准结论 | 增加模型改写、切更多轮不会补独立人群 |
| 专业方法有效性 | ESConv 是支持对话材料；不自动等同专家流程 | 评估 AnnoMI 等专业行为来源，限范围采用；专业审查方法适当性 | 专业标签不能扩张成整体临床效果；论文支持目标以单轮回复/模拟能力为限 |

不建议同时执行所有补法。先做“原始来源覆盖/能力缺口”的一个审查包，判定应修资源表示还是确需新来源；再做能区分内容价值、检索错误、G 使用错误、评价不敏感的条件实验。这比多轮整套试验更能定位失败。

## 6. 许可与来源边界（仅本次核验所及）

- ESConv 官方 LICENSE 是 CC BY-NC 4.0，README 也注明学术研究用途；其派生 RS 应保留来源和许可。见官方 [LICENSE](https://github.com/thu-coai/Emotional-Support-Conversation/blob/main/LICENSE)。
- ESC-Eval 官方根目录此次未见单独 LICENSE；角色卡来自多个源，模型也有各自条款。公开可下载不等于可任意再分发/商业部署；本次仅作研究适配审计，不作法律推断。
- ES-MemEval 官方根目录此次未见单独数据/代码 LICENSE；论文页 CC BY 4.0 是文章许可，不能自动扩展成每项数据资产许可。后续若要公开再分发应逐项确认。
- 上述许可核验不妨碍当前只读研究审计，也不要求为本次分析额外审批。

官方来源（实际查阅）：

1. [ESConv 作者仓库](https://github.com/thu-coai/Emotional-Support-Conversation)：当前 1,300 对话、FailedESConv 196、反馈与策略材料。
2. [ESConv 原论文](https://aclanthology.org/2021.acl-long.269/)：任务及策略研究背景。
3. [ESC-Eval 原论文](https://aclanthology.org/2024.emnlp-main.883/)：角色模拟—人工评价—ESC-RANK 框架。
4. [ESC-Eval 作者代码](https://github.com/AI45Lab/ESC-Eval/blob/main/evaluate.py)：5 轮交互；[score.py](https://github.com/AI45Lab/ESC-Eval/blob/main/score.py)：七维 adapter 和 parser。
5. [ES-MemEval 作者仓库](https://github.com/slptongji/ES-MemEval)：运行接口、data 与任务脚本；[固定版本数据](https://github.com/slptongji/ES-MemEval/blob/692624208acc077b8867698c1d6fcd998dee641a/data/evo_emo.json)。
6. [ES-MemEval 作者论文](https://cslinzhang.github.io/home/files/WWW-tiantian.pdf)：数据构造、任务和指标；全文有计数/版本及 DG 评分天花板的注意事项，主报告优先引用可核验原始数据与源码。

本次证据边界：未完整逐句审查 401 会话中的所有行动结果，未重跑官方基准，未验证所有新模型 runtime 的可用显存/吞吐，未收取新人工评分。以上缺口不能写成已解决。

## 7. 补核：ESC 模型确已在本机落盘，代码可具体复用

本次逐项静态检查确认，不必重新下载这些资源：

- ESC-ROLE：`/opt/tokkio-data0/tokkio_external/ESC-Eval/ESC-Role/2e2a4733d2e71da242f348aad165fe171acd5df7`，config/tokenizer config 与 model index 存在，index 所列 8 个权重 shard 全部存在。
- ESC-RANK 基座 InternLM2-Chat-7B：`/opt/tokkio-data0/tokkio_models/huggingface/hub/models--internlm--internlm2-chat-7b/snapshots/c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2`，index 所列 8 shard 全部存在。
- ESC-RANK adapters：`/opt/tokkio-data0/tokkio_models/huggingface/hub/models--haidequanbu--ESC-RANK/snapshots/450bf2eb5376c79e371aaf432925810243de1527`，fluency/diversity/empathic/suggestion/human/tech/overall 的全部 7 个英文目录都有 config 和权重，每个权重 10,494,088 字节。
- 已有运行证据目录 `/opt/tokkio-data0/tokkio_runs/claude_esc_pilot_20261111/` 存在 `dialogues.jsonl`、`dialogues_r2.jsonl`、`tree_dialogues.jsonl`、`esconv_val_rank_scores.jsonl` 等非空产物；与代码加载路径相符。静态落盘核验和历史运行证明资源可复用，不等于本次重新实测了当前空闲 GPU/环境加载。

具体代码复用：`gen_loop.py:22` 绑定本地 ESC-ROLE，`:26` 为官方角色 prompt，主循环可抽成冻结外评 adapter；保留角色信息只给模拟 seeker 的边界。`:40` 的 BASE2 与其策略/检索条件是 Claude 开发实现，不能不加说明地当旧 Paper-1 官方 supporter 条件。`score_rank.py:15` 绑定已落盘权重，`:23` 读取官方 prompt，`:58` 组装整段 transcript，`:72` 是官方数字解析；这些可用作批量评分实现参考，但正式输出仍应做 pinned model/prompt/parser 身份核验。

`score_rank.py:76` 额外计算“首个输出数字位置上 0–4 条件概率期望”，记录在 `expected`；这不是官方七维 ordinal，也没有因变成小数就获得微小资源收益测量资格。可保留为敏感性诊断，不能替代官方整数结果或直接晋升 PM 奖励。`--keys` 支持开发只跑特定维度以节省 GPU 时间；正式七维结果应完整报，不根据显著性选维度。

对原 24-item 资格脚本 `35_score_official_esc_rank_blind_qualification.py`，可重用其身份检查与 prompt/adapter 映射函数，但该脚本有冻结输入 hash，不能拿它直接灌新材料然后绕过检查；新评测应单独薄 wrapper，保留旧脚本原身份。角色回合推理与七维评分可以分批串行加载以控制显存，而非要求全部模型常驻；部署真实延迟另测，不能把离线换模型加载时间混成产品 PM 延迟。
