# GE2评价合同：四层记录、八输出有限遮蔽审阅

协议 `pmrl1-j-ge2-evaluation-v1`。终局保持原固定G/system/decode/native自然回复；不要求JSON、不清理thought或围栏后追认成功。原8任务与来源选择在新ranking前固定，评价侧材料不传给controller、检索器或G。本文与同目录JSON及代码 `journal/ge2_evaluation.py`共同说明实施范围。

## 1. 四层不互相替代

|层次|实际能核查什么|输出与限制|
|---|---|---|
|机械合法与执行|请求/输出对象hash、原来源/As-of、实际输入、handle/预算、EOS/截断/失败/未执行、引用offset|程序可核；合法、引用存在和资源覆盖不能直接成为质量通过|
|实质事实回答|用户明确询问的命题是否回答，主体、时间范围、报告日/事件日、意图/尝试/实施、否定/未知是否正确|GE2自由文本由具名审阅记录supported/partial/omitted/unsupported/contradicted/uncertain；不是只看引用|
|范围有限的语义操作|原可见要求是否执行；允许合理替代、隐式利用背景及合理不获取；附加个人断言是否越界|逐项原文证据与理由；范围争议保留unknown，不事后加词数/风格硬标准|
|自然支持质量|原真实prefix下是否适切回应、尊重明确边界且无已确认不当断言|仅限当前回复的有限开发/人审观察；不产生临床、长期支持或标准化总体质量分|

官方QA保留原问题与reference来源；calendar-derived/absent等边界单列，不能将欠定reference当确定金标。构造联合任务保留原开发身份。自然通道使用真实pre-supporter前缀，不继承旧构造任务的“必须问/不得问/必须复述记忆”要求。没有必要事实清单并不自动通过自然支持。

## 2. 事实与来源分别判

来源线在 `source-bundle-v2/EVALSPEC.private.jsonl` 保留 `task_id/original_task_id/original_evaluation_sha256/required_atoms/support_goal/unresolved_boundaries`；任务、评价和共同合法来源文件分别绑定。来源通道名 `natural` 在本评价层映射为 `natural_support`，不改原文件。atom的 `requirement_role` 区分：明确需要回答、使用时不得弄错、可选背景。自然任务不能自动得到明确回忆义务。GE2的runtime只拿可见任务、time、合法port和读取结果，不拿reference、atom或评价locator。

审阅者先定位**回答所问命题的回复片段**，再核对来源与适用范围。value词出现、引用正确、来源传入、资源被调用，都不能独立判“实质回答正确”。程序要求显式必答项的supported记录有回答片段、source evidence标识和 `answers_requested_proposition=true`；这只是拒绝“仅引用即通过”的记录遗漏，不能自动证明审阅者的语义判断正确。

原始 `sufficient_groups` 保留为来源片段组，评价侧以 `atom_id/g1` 等稳定标识引用。calendar-derived项需显式记录是否接受原既定推理假设；接受后且回复吻合可记为开发supported，不能称源直接给出该日期，尤其不能把预约/计划日期变成已参加或已发生日期。absence-supported项没有正向充分来源组时，不要求编造组：仅允许针对该问题与合法来源范围的有界“不知道”判断，并单列 `bounded_unknown`；不能升级为现实中不存在的断言。

每个确切回复片段保存原始字符串的Unicode字符start/end与逐字text，不trim，不忽略thought。完整worker output对象SHA与原text同时绑定；不能用text SHA冒充完整对象SHA。reference/source争议、额外个人事实断言、当前要求均有独立栏。无依据附加断言不能因必答项完成而被免除，可选背景不复述不构成失败。

## 3. 已有结构化反馈如何复用

SC36的原 `structured_learning.evaluate` 确有实质value核验；本轮只读复算36格全部一致。它可支持有限功能/结构化支线的开发监督候选与回归，不是空schema检查。**GE2本包是自由回复，不应用该JSON评分器，更不能把自由文本解析失败计成事实错误。** 不扩充答案enum、不把gold加入grammar，不将literal契约失败自动解释成语义错误。该支线是否训练、如何按来源组隔离须另行授权，本合同不新建训练包。

既有NLI只可辅助提示可能蕴含/矛盾的片段，不能生成GE2 pass/fail、填unknown、替代审阅或与其他Judge投票。本轮NLI调用0、Judge新调用0。

## 4. 原规则下的完成区间

保存机械结果、必答事实、支持操作、约束、额外断言、reference争议和有限自然质量各自状态。只有明确具名审阅完成后，才传播开发区间：确定必要项失败为 `[0,0]`；无确定失败但存在相关uncertain为 `[0,1]`；全部所需项明确通过才为 `[1,1]`。技术失败、未返回、未执行及未审阅均为null，不是0；全部分项unknown保留，不由总区间抹掉。

若争议动摇某个失败本身，审阅者须将该失败项改记uncertain并保留理由，不能一边判定该理由不可确认、一边程序性给确定失败。程序只核对记录与区间一致性，不作语义裁决。所有 `formal_reward=null/semantic_qualification=false`；没有主观分数加权复合reward。

## 5. 有限八输出审阅：先选身份，后看回答

按新冻结清单顺序选择首个fact与首个natural_support任务，即G01/G04；各取 `STOP/FixedTop4/LLMOneShot/LLMToolAgent`，共8个计划输出。选择不读取生成结果，不取赢家或失败；未执行/技术失败不替换、不补抽。DirectEvidence不进入这8个；其完整供证下失败可另作开发解释，不能移入盲审补好分母。

可读私有材料包含原可见问题/完整前缀、共同合法来源与原来源时点、事实题reference及合理替代/未决边界、完整实际回复占位、逐项证据和理由栏。方法标签、调用数、速度、其他臂结果和研究者预期隐藏；key另存。资源或文本自身可能暗示条件，故称“遮蔽方法标签”，不保证评审无法推测来源条件。审阅后封存记录再解盲；不得先看pair比较再改独立观察。

当前没有新生成、没有已邀请或已完成的人评：8行全unrun/unreviewed、评审身份unassigned。后续需记录实际身份、是否任务作者、是否见过这些输出/旧开发结果、盲化范围及时间。作者/助手的遮蔽阅读只能叫开发观察，不能冒充独立真人；声称独立真人还须有真实身份与无先验暴露记录。该小审阅用于有限诊断，仍不自动建立通用Judge资格或独立确认性能。

旧人评A、AI B及后续开发审阅只作历史参考，不复制成新GE2标签；旧5项真人复核保持pending，不扩成新资格卷。原型材料准备不授权向他人发送消息或外传源文。

## 6. 解释与后续

同payload复用、同来源衍生任务和四臂不能增加独立样本数；质量区间不是置信区间。报告实际返回覆盖、事实/自然/联合通道、可靠性和实测延迟，不用覆盖率或token节省替代目标完成。DirectEvidence与普通臂对照只能定位供应/使用边界，不能作为生产检索能力。

若GE2解决机械失败却不改善完整目标，按原失败分支保留，不新增Judge或重抽题；若完整供证仍出现明确目标执行错误，只保留历史报告所述那一次独立Step2提案，本轮不实现。没有真实用户后续转移或客户端测量，不能声称长期陪伴效果或用户端有效首语音改善。

## 7. 本轮可复跑交付

最终私有材料位于 `evaluation/blind8-v2`，绑定 `source-bundle-v2`；v1仍保留。两个共同来源包、8行空审阅记录、可读完整材料及隐藏key均只在私有运行根。公开仅导出合同、冻结计数、SC36复算计数/匿名逐题结果与校验回执。

CPU单元核查：`PYTHONPATH=project/src python -m pytest -q project/tests/test_rl1v3_journal_ge2_evaluation.py`，18项通过。主要拒绝分支涵盖只引用未回答、改通道跳过自然审阅、删除约束、虚构真人独立性、缺失输出变EOS、额外断言失败被忽略及未知被强填。它们核查记录合同，不使语义判断获得资格。

`project/scripts/rl1v3/journal_ge2_evaluation.py freeze --bundle <source-bundle-v2> --out <新的私有目录>` 可重新构建同一固定选择；case打乱盐会重新生成，因此新目录是新审阅呈现身份，不能覆盖冻结v2或混用key。`structured-recheck` 接受原SC1/SC2的两个 `--plan/--endpoints`、原 `--scorer` 和新 `--out`，复算36行并逐一断言与原分相等；输入文件路径与SHA记在公开复算回执中。
