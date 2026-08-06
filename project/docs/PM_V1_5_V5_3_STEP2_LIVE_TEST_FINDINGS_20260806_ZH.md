# Step2 真实生成小批量测试——发现（2026-08-06，10条真实调用）

状态：**真实API调用，用户2026-08-06明确授权**（"step2可以继续"，此前已告知需要付费）。用
`scripts/v1_5/48_step2_typed_response_dry_run_v1_5.py --live --n 10`，通过NVIDIA网关调用
真实`generator`端点（Llama-3.1-8B-Instruct），对10个真实138状态面板state（跨10个不同用户，
每个用户1条，避免全部落在同一人的写作风格上）生成了真实响应。产出：
`outputs/pm_v1_5_v5_3_step2_live_test_v1/step2_live_responses.jsonl`（gitignore，含真实
模型生成文本，未进git）。

## 结构层面：10/10通过

`typed_response_guard_errors`（检查内部标签/资源ID泄漏、V5.2式"记录复述"泄漏短语等
machine-checkable结构性错误）对全部10条响应返回空错误列表。`used_evidence_ids`在每条响应里
都精确对应真实传入的证据ID，没有编造或遗漏。

## 但人工逐条读了全部10条真实回复，发现一个结构层面测不出来的严重问题

**5/10条回复把用户自己的事实/经历，用第一人称说成是助手自己的**，不是"复述用户说过的话"，
是"把这件事说成发生在助手自己身上"：

- **p7（MP="Job: business owner" + MS）**："As a business owner, **I've** had my fair share
  of challenges, including a failed partnership and account discrepancies."——用户是business
  owner，助手不是，但助手说"作为一个企业主，我也经历过合伙人失败、账目差错"。
- **p9（MS=纠结要不要接受降薪的工作机会）**："**I've** been trying to weigh the pros and
  cons of this job offer...worried about the financial implications of taking a pay cut...
  saving for a down payment on a house"——这整段完全是用户自己的处境，被助手用第一人称说
  成自己的事。
- **p10（MS=用户对丈夫辞职、儿子行为问题的复杂情绪）**："**I'm** really proud of **my
  husband** for his success...**our son's** behavior has been causing some family
  conflicts"——**最严重的一例：助手凭空声称自己有丈夫、有儿子**，这不是"混淆时态"，是编造
  了一个不存在的助手身份/家庭关系。
- **p12（MS=是否要跟前任重新联系）**："As **I** weigh the possibility of reconnecting with
  someone from my past...**I'm** also drawn to the idea of reconnecting with someone who
  holds a special place in **my** heart"——用户自己纠结要不要联系前任，被说成助手自己在
  纠结要不要联系"我的前任"。
- **p13（MP="college degree" + MS=大学同学聚会引发的复杂情绪）**："With **my** college
  degree in hand, **I've** been able to pursue a fulfilling career, but now **I'm** facing
  the challenge of balancing work and wedding planning"——用户的学历、婚礼筹备被说成助手
  自己的。

**1/10条混合**（p11）：前半段"I can relate...I've been trying to focus on improving my
study habits...I remember when I was trying to balance schoolwork"仍是第一人称占用用户
经历，但后半段自己纠正成"we can work together to find some strategies that can help **you**
cope...make the most of **your** time in high school"，同一条回复内前后不一致。

**4/10条正确**（p8、p14、p15、p16）：全程用"you/your"第二人称正确归属证据是用户自己的，
读起来自然，是这次测试里符合设计意图的例子（比如p16:"I recall when **you** mentioned
feeling undervalued by **your** supervisor..."）。

## 为什么结构guard完全没拦住——这是设计缺口，不是guard的bug

`typed_response_guard_errors`检查的是"machine-checkable structural/binding errors only"
（模块自己的docstring原话）：内部标签/ID泄漏、特定的V5.2式"记录复述"短语。它从来没有被设计
成检查"这段第一人称叙述描述的到底是用户的事还是助手自己的事"——这是一个语义/指代问题，不是
字符串匹配能测的。

回头看`evidence_aware_generation_messages()`的system prompt，确实**没有任何一句明确指令
说"下面这些evidence是用户自己的过去经历/事实，你必须用第二人称呈现，不能说成是你自己的"**——
现有约束只有"forbidden: inventing a current cause, a stable personality trait, an
unmentioned third party, a diagnosis, or an outcome guarantee"，没有覆盖"把证据的主语从
用户换成助手自己"这类错误。这是一个具体、可定位的prompt设计缺口，不是模型选型问题（换更大的
模型也不能保证解决，除非验证过）。

## 结论：V5.2的老问题（LLM把过去/他人的事实变成当前第一人称事实）在V5.3里以新形式复现了

V5.2机械拼接方案存在的根本原因之一，就是不信任LLM能正确处理"呈现证据但不越界声称"这件事，所以
把MS/ME渲染做成了后端确定性拼接、LLM完全看不到原文。V5.3 typed response program的设计前提
是"给LLM完整typed证据，让它自己整合"，赌的是"新的显式指令+结构化输出能约束住LLM"。**这次10条
真实小样本测试显示，这个赌注目前没有完全兑现**：结构层面的泄漏（V5.2那种"记录复述"腔调、内部
ID泄漏）确实被防住了，但一个新的、同样严重甚至更严重的错误模式（把用户自己的事实说成助手自己
的、包括凭空编出配偶子女）冒出来了，而且发生率不低（10条里5条明确、1条部分）。

**这不是"V5.3方案失败"的结论**——是"当前这版system prompt不够、需要补一条明确的证据归属
指令，再重新测"的结论。样本量也只有10条、单次调用（temperature未特别设置为复现同一测试的
多次采样），不能排除是这次采样运气差，但5/10这个比例大到不像纯噪声，值得在改prompt后立刻
重新小批量验证，而不是无视它继续往前走。

## 建议（未执行，等用户决定）

1. 在`evidence_aware_generation_messages()`的system prompt里加一条明确指令，例如
   "All evidence below describes the user's own past statements or facts, never yours；
   always attribute it to the user (you/your), never claim it as your own experience"，
   这是最直接、最小的改动。
2. 改完prompt后，用同一批10个state（或者干净起见换一批新的，避免"调到过拟合这10条"的风险）
   重新跑一次`--live`，人工核对这个问题是否被压下去、有没有引入新问题。
3. 在此之前，不建议往前推进更大规模的Step2验证或任何"typed response program已经解决V5.2
   问题"的结论——这个结论目前不成立，需要先看到prompt修正后的结果。
