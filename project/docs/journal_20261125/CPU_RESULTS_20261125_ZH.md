# PM-RL1-J 首批实际 CPU 交付（2026-11-25）

本轮已完成真实源获取、两探针复现、资源与任务候选、CPU 分类重训及首批可执行生成申请。没有 G0e 新回复或资源效益结果。A0 已获研究者本轮批准，但原设备守卫在加载前拒绝：固定 GPU 被其他项目占用。M/RS 尚未获运行批准。

## 身份和依赖

- 独立工作树 `/home/tokkio/Metacom5_3-journal`，分支 `pmrl1-j/cpu-resources-20261125`，基于固定 `b07db1046c948a77643a646bb845a21e74c10044`。
- 四份指定文件完整读取并保留；没有合并 #23/#26/#27/#28，没有修改历史 A/B/G、H0/C0、J00 或既有冻结证据。G0e/E6 不重签。
- 私有临时组合：A `df21b11c96165c1a3dd8ef0edf76df2788ee3e45`、B `7eeff1cf8dcd889e4a08e9a2a723dbe3f864e118`、G `73fdb12f29b6970a268eeda704d73e1bd35b1c3e`。531 个源文件逐文件记录来源与 SHA；跨工作流改动路径冲突 0，C0 原字节保留。它是依赖快照，不是一个已合并的全栈 HEAD。
- 全部 RAW、gold、逐条任务、预测、模型和运行证据位于私有 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/`；本提交只含代码、测试及聚合说明。

## 来源和探针

AnnoMI 官方仓库固定到 `42936645ec3857a9c84ab296a36a3c34b779ef49`；`AnnoMI-full.csv` blob `dd8aba7b07953bf6c37c3e6e4771485e62e36b32`，SHA256 `3b60fec5e9d83cbb18ade0e412fb9afaef3b81724748a5d715f844bdd7432c9f`。2023-03-14 full 版本；仓库没有 LICENSE 文件，许可依据是[作者扩展论文 Data Availability](https://www.mdpi.com/1999-5903/15/3/110)明确的 Public Domain License 声明。演示视频转录不是真实疗效数据，不推定原视频的其他权利。

已实际取得 TIP35 2019 正式[第三章](https://www.ncbi.nlm.nih.gov/sites/books/NBK571068/)和[第六章](https://www.ncbi.nlm.nih.gov/sites/books/NBK571066/) HTML，SHA256 分别为 `4ac626852f88220f66fa95e12c32d0da3d3e10ff2b794535b4419eef9ca53cf5`、`f2ee19ac9a3f1d884ba7354c56d5edb5b1cb352d44021306f041f8cf3ee430ed`。NCBI 页脚标明公共领域；同时保留 SAMHSA 出版声明中第三方版权材料和收费分发例外。方法只摘取作者正文并做非临床适配，不收入第三方 exhibit。原 `/books/` 地址返回验证码，SAMHSA PDF 返回 403，失败记录保留；未将这些错误页认作资料。

两份原始 `.cjs` 未改预期 hash，实际执行成功。对主方案/入口公开的 44 项数值或四位小数比较，44/44 一致。主要结果：

| 项目 | 实际结果 |
| --- | --- |
| EvoEmo | 18 构造人物，401 会话，4,119 合法切点 |
| QA | 1,427 行，1,420 问题哈希，355 owner/question-group |
| 证据 | 1,144 全可解析，18 部分，5 全不可解析，260 空引用 |
| 全历史词面诊断 | Top4 hit-any 684/1144，hit-all 520/1144 |
| AnnoMI 原探针 NB | 629/834，75.42%，macro-F1 0.7024 |

复现不等于探针所有解释成立。AnnoMI 的 13,551 行是**注释行**，只有 9,699 个唯一话语；支持者 6,826 注释行对应 4,882 话语。7 个多标注会话产生 3,852 个额外注释行。原 source probe 会在上下文中重复这些话语；原始数字及脚本保留，新资源按话语合并文本并保存全部标注。唯一相邻 client→therapist 位置仍为 4,743（高质量 4,331），原文/角色/视频一致性冲突 0。

## 不抹除分歧的行为识别对照

保持原 96/23 视频组开发划分，组重叠 0。先跑固定 TF-IDF logistic，再做唯一话语等权重训：TF-IDF 只在唯一训练文本拟合；每句话全部原标注保留，每条注释 loss 权重为 `1 / 该句标注数`，无多数票替换、无重调超参。

| 模型 | 正确/测试数 | 准确率 | macro-F1 | input 类召回 |
| --- | ---: | ---: | ---: | ---: |
| 原 NB | 629/834 | 75.42% | 0.7024 | 0.4157 |
| TF-IDF logistic，注释行训练 | 631/834 | 75.66% | 0.7160 | 0.4944 |
| TF-IDF logistic，唯一话语等权重训 | 624/834 | 74.82% | 0.7077 | 0.4494 |

等权模型的视频组 bootstrap 准确率 95% 区间为 [69.92%,78.93%]。不因下降换模型或改划分。训练为 4,048 唯一话语/5,992 注释行；测试 834 话语恰好全部单标注，7 个多标注会话全部在训练侧，不能用这个测试证明分歧条件下评价器可靠。

7 会话的 216 条十人标注支持者话语：112 全一致，104 有分歧，4 最高票并列、12 无绝对多数。主行为 pair agreement 0.8041，Fleiss κ 0.7365，已独立重算一致。同组 212 条 client 话语有 154 条分歧、10 最高票并列、19 无绝对多数，talk-type κ 0.4669。全部标签分布、逐标注者结果、混淆矩阵、子类一致性和众数/全一致子集敏感性均留档；κ 只覆盖这 7 个会话，子类的适用样本过滤/变动标注人数另行标注，不与原论文口径直接等同。此检测器只识别已说出的行为，未获得任务奖励或帮助性资格。

## 实际资源、任务与读取

**Memory：**91 份完整 SOURCE_EXACT RAW 历史会话与对应 Ledger；24 个真实前缀通过既有 PrefixPort 与 As-of 实读。另 2 个真实前缀通过 snapshot-only port → VerifiedEpisode → GET_MS → STOP，STOP 后 GET 被拒绝。没有把旧 324 个隔离 MP 解禁，没有生成或批准 SUM/typed 主张。

30 个原版 QA：IE/TR/CD/UM 各 6，abstention 6；12 个多来源题；4 owners、3 独立 family groups（p13/p18 合并），只用既有开发组，排除旧 QA 候选及旧 14 事实题。官方 pinned `qa_experiment.py`/`chat_room_builder.py`支持完整历史 QA；使用独立 EndHistoryQA sidecar，没有伪造 C0 对话切点或按 question-group 推定时间。原 gold 只留 EvalSpec，event→session 为粗定位，不注入 event gold 文本。

真实 RET Top4 在本批 24 个 answerable 题中 hit-any 17、hit-all 11；与全量网页探针的样本、文本和同分规则不同，不能称复现差异。DP 最多 4 来源。标注来源全命中不是必要性或充分性证明。独立重建的 5 个确定性产物 SHA 完全相同；实际计时不要求字节重复。

**RS：**6 个 METHOD 候选，分别覆盖双向顾虑、反映、自主、许可式信息、用户主导行动、拒绝后调整。12 个不同视频家族的源片段各构造一对最小显式需求/许可/时机变体，共 24 任务、每域 4 个。它们是构造的非临床约束任务；部分单句指代不完整，不能声称已验证原临床情境适用性。

初次 CASE proxy 暴露错误：sustain 不等于明确拒绝，包含 would 不等于征求许可，风险词遗漏药物/饮酒。原候选留存，逐项处置后另建 12 个可读 exact CASE/反例（10 视频家族，与 12 任务家族零重叠，每技能 2 个）；其中 3 个明确 proxy 反例。positive_eligible=0、professional_approved=0；不把它们称作已证明适用的正例。本次 144 臂不含 CASE，未追加 CASE 调用。

RAW/Method 指向同一 TIP35 段落，但非临床适配改变了部分规范目标（例如平衡自主而非促进特定改变），所以比较是“原文 vs 非临床适配”，不是纯压缩效应。Generic 只是预定一般沟通对照，未实证认定等质量。

## 请求冻结与评价

新 journal renderer 保留同一 G0e 系统/权重/解码，将历史报告、可选方法、外部示例分开；所有新臂共用此身份，OFF 不加空 Notes。它不复用 PP1 renderer 或旧奖励。

| 请求集 | 逻辑臂数 | 唯一实际调用 |
| --- | ---: | ---: |
| Memory：OFF/DP/RET/matched-other ×30 | 120 | 114 |
| RS：R0/Generic/Legacy/Professional-RAW/Method/F-resident ×24 | 144 | 144 |
| 合计 | 264 | 258 |

6 个空证据 abstention 的 DP 与 OFF 完全同 payload，保留逻辑分母并精确复用。264 个 payload 全部用固定 native tokenizer 独立逐 token 重算一致；16384 运行上下文、320 输出 reserve 下全部可达，最大输入 3897。模型原生 262144 上限未当作运行许可。120 Memory 原问句、30 DP 集合、30 RET 检索及 canary 检查通过；36 个空资源 Memory payload 与旧 G0e OFF 完全一致。

冻结 EvalSpec 提供源定位、必要项、禁止项、可接受替代与审核状态。确定事实使用严格规范化，不把复杂语义 substring 计为成功；其他语义项待独立判定。task Y 按 pass/fail/uncertain 及技术失败分开，unknown 保留 [0,1]、固定分母。未校准分类器不作奖励；TerminalRegistry / ReplayBinding / TerminalTable / RealInstance 桥已接通门禁，但本轮真实终点 0、可训练研究实例 0。

首次请求封装出现 TimePoint JSON→C0 类型错误，失败 requests-v1 原样保留；修复显式类型重建，并使非容量异常直接失败，防止误报科学不可达。requests-v2 才是当前冻结候选。

## 工程验证与保留边界

R1 修复局部来源身份，并在真实 bank 中发现、修掉 `registry.version` 的间接全文件依赖；改变全语料 hash/source ID 但保持局部会话不变的实际回归通过。R2 绑定 snapshot/port 并核对实际交付 ID/正文。R3 STOP、R4 缓存隔离独立验证。R5 保留关系操作、有效区间、审核/处置字段；仅合成机制验证，未冒充真实更正链语义签收。

联合 CPU 测试 31/31 通过、0 skip；DP 默认选中 bug 的真实 Chrome 检查 8/8 通过。中文翻译尚未签收。mask 内部预读/测量成本尚未单列，不能称在线成本公平验证完整。PP1/FC-MS 原身份和待办保留，不阻塞这次受控请求。

## A0 与首批明确申请

A0 新授权保存在私有 engineering/A0_AUTHORIZED_20261125.json。原 #23 HEAD、plan `43f175c56d…`、binding `c9eb916989…` 校验通过；启动前指定 GPU 空闲不足，0 load/0 call/0 claim，不换设备、不干预其他项目、不自动重试。授权仍保留，不再要求 G0e/E6 签收。

**本次申请仅首批 20 次 M/RS 技术冒烟：**Memory 每臂 2 条（8），RS 每臂 2 条（12），固定任务哈希顺序，包含在 258 次总候选中；1 load、0 warmup、0 retry、总硬限 1200 秒、加载 600 秒、单请求 300 秒、最多 320 输出 tokens；原指定 GPU，收费 API 0。任务结果不用于重抽；第三次 length stop、超时/OOM/身份/设备/磁盘异常停止本作业。其余 238 次不获自动运行许可。A0 尚无吞吐实测，1200 秒是保守硬帽，不是预计完成时间。

冻结计划对象 SHA256：`6c91cc7cedfbd5b3f915ff60616c32d5332cb7ae33e427adbc535bf9e8bad839`。

20 请求文件 SHA256：`f47b7db732191cae162599eb8245c67ece2fb8fe9efaa5c244f6dfc36e8e8a48`。

私有 `smoke-v2/` 包含固定执行器副本、SMOKE_PLAN.json、请求、checkpoint、独立 CPU 准入复验和未批准模板。check 不接触设备/模型；未批准、A0 转用、扩额至 21 次均拒绝。具体命令见 `REPRODUCE_ZH.md`。不得把 pending 模板改为 true 代替研究者批准。
