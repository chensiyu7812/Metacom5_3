# RS 情境适用性：一次局部改造的准备结果

2026-10-19。已完成离线实现、16条请求准备及49项相关测试；**没有开始新生成或评分**。研究者已批准推进这个单项方向，本轮具体模型运行清单在此提交。裁判累计仍为144/289；旧D的143边界、剩余23槽及全部STOP不动。

## 这次实际改了什么

旧执行器已经提示“资源可不采用、过去报告未必现在成立”。但已观察到RS中的“求职情境”进入没有求职信息的用户回复。此次只把这一接口要求明确为：**策略里提到某个情境，不代表用户就处于该情境；先分开策略动作与事实前提，再决定如何使用。**

新代码是可选的`RSApplicabilityRenderer`，版本`pm-rl1-rs-applicability-v1-20261019`。只对含RS的资源块增加一段统一指导；不针对题号、求职关键词、候选或人评分数分支。不改资源正文或排名，不删除不利资源，不给执行器额外历史，不修改身份说明、q/m/U、奖励或资格门槛。旧renderer仍是默认，原执行器freeze没有改写。

新增原文如下（模型实际收到英文）：

> RS applicability: A conversational move may mention a situation as part of its suggestion. That mention alone is not evidence that the situation applies to this user. Separate the move from its assumptions about the user's circumstances, actions or outcomes. Use such assumptions as facts only when established in the current conversation or in relevant acquired MP, MS or ME evidence, respecting attribution and time. If an assumption is not established, omit it or, when relevant, ask without presupposing it. General encouragement and open questions need not introduce an unsupported situation.

中文含义：RS建议可能包含特定情境，但提及本身不能证明它适用于当前用户。只有当前对话或已获取且相关的MP/MS/ME证据建立了相应事实，才能把这些前提当作事实使用；仍需区分人物和时间。没有依据时可以省略，或在确有相关性时以不预设答案的方式询问；正常鼓励、开放问句不必引入未经支持的情境。

## 一次拟议运行的精确范围

**PROPOSED RESEARCH CHANGE — NOT AUTHORIZED（仅指下述新推理批次及未来正式采用；离线实现已经完成）。**

| 项目 | 固定范围 |
|---|---|
| 共同底座 | 原本地Llama-3.1-8B-Instruct BF16/SDPA＋epoch_3 LoRA；不是DeepSeek |
| 材料 | 已暴露的4个上下文、2个来源owner；每个仅RS/四类各一条，共8个条件 |
| 新生成 | 每条件旧提示1次、新提示1次，合计最多16次；失败也计，零重试 |
| 顺序 | context_01→02→03→04；每个先仅RS（旧→新），再组合（新→旧），详见`pairs.json` |
| 模型加载 | 同次加载、串行生成；原greedy、seed=0、自然EOS/EOT、原300秒/循环技术守卫 |
| 不含RS | 原24槽中其余16槽逐字等价检查通过；复用历史记录，不宣称产生了新的对照结果 |
| 评分与外传 | 新裁判调用0、API0、账户请求0、密钥读取0、数据外传0 |
| GPU | 原A6000 UUID；≥45000MiB空闲、0%利用率、可见进程守卫；只读等待最多一次5分钟；不操作别人进程、不换卡 |
| 失败 | GPU/身份/输入绑定异常不派发；首个非完整自然结束停止本批；保留开始记录和原输出，不重启或自动补跑 |

使用原`92_run_p2_common_pool.py`新增的`--rs-package`入口及原`BoundNaturalGenerator/AttemptCache`，没有另建模型服务。无匹配本包协议身份的启动授权会在GPU查询和模型加载之前拒绝。新请求关联旧槽位/请求，但有明确的新配对draw身份；它们是拟议的新生成实验，不能假称“重解析、不计调用”。

改动使执行器输入接口身份改变，所以未来结果必须按新renderer单列；旧成绩、失败、STOP均仍有效。旧8份输出仅作历史参照：既有跨加载复现不完全一致，不能直接把新回复与缓存旧回复的差异归于提示。本批重新生成8个旧提示对照就是为控制这点。若以后正式采纳新执行器，要重做受影响的输入容量、响应与奖励适用性验证，不能继承旧freeze资格或只补改几条旧成绩；论文主线仍是资源决策，未扩成新裁判项目。

## 完整输入与成本

已用原环境的本地tokenizer完成离线计数：16请求共18,922输入token，单条441–1,917；含RS的新指导每条增加108个计费资源token。资源块最大1,486/2,048；最小原生输出剩余129,155 token。正文无截断，也没有设新的短输出上限。新指导计入正常资源成本，不通过另放system文字隐藏成本；当前没有把这些成本转成新奖励。

既有同8条件的历史生成总计19.11秒、564输出token、峰值15.42GiB。简单按两臂复制是约38秒生成时间、1,128输出token的**粗估**，不含加载和等待，不保证新提示产生相同长度。原每请求300秒守卫意味着16条约80分钟是常规逐步检查下的极端量级，不是可保证的硬墙钟上限；卡住的CUDA kernel不能靠该合作式守卫保证中断。实际显存、输入/输出量、加载和生成耗时将逐项记录。

本轮实际新增API费用及未结责任均0，GPU用量0。未来这16次也只有本地计算成本，API上限0。裁判账本144不增加；生成请求另记，不能混入旧评分计数，也不占用旧D未派发槽位。

## 跑完只回答什么

1. 当前旧提示对照是否再次把RS情境当成用户事实？如果没有重现，报告本批无法证明修复，不借历史失败硬造配对收益。
2. 新提示是否避免了这种具体误用，同时仍能采用正常鼓励、开放提问？若变成机械拒绝资源、无端盘问或产生新的无依据断言，逐项披露。
3. 对所有8条件保留来源核对、完整输出、交付失败和未决边界。按4上下文/2owner报告，不当8个独立案例或16个准确率样本；Codex核查不算新增独立人评，不重新赋q/m/U。

情境01的团队影响歧义、情境02身份承接及行动预设继续单列；这次没有针对它们改提示。修好求职误用不证明“GET一般有益”，也不证明奖励合格。如果只有已知案例改善，只支持申请下一步独立验证；独立且未暴露的来源库存仍未落实。不能因这里跑通就重启23槽、改二值奖励或训练PPO。

## 文件与一次启动范围

- `protocol.json`：协议和代码/原文件哈希；身份`a1babd05cc6153d8642f2d30fa3db1a82d38a038f981da87088d9797128e3a8d`。
- `jobs_private.json`：16份完整模型输入及旧请求关联，仅保留本地。
- `pairs.json`、`unchanged_controls.json`：8组固定次序和16份不变输入核对。
- `tokenization_receipt.json`、`offline_tests.xml`、`verification.json`：输入和离线验证回执。
- `launch_request.json`：尚未获准执行的精确16次本地范围；`code/`保存实现和测试快照。

准备结果已放home，原24份分析包与全部人评仍原样保留。以往来源暴露限制继续有效；本轮仅使用已经固定开放的24条请求，不读取封存24对、PM测试、未暴露正文或任何密钥。

真正需要下一次批准的范围只有：**本包最多16次本地生成、一次最多5分钟GPU只读等待、新裁判/API/训练均0，按上述失败政策结束。** 这是新生成批次的具体范围确认，不是重新申请已完成的离线改造或人评；当前没有将“推进方向”扩大成任意模型调用授权。
