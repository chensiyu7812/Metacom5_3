# 固定材料与部分关系参照（中文阅读说明）

状态：待研究者窄复核的冻结草案；原始英文、完整合法来源和来源绑定均保留。下文的来源引文/ID/角色已机械核对，关系解释不是因此自动获得语义认证。研究者已明确的解释、来源原文与分析者草案分开显示；不包含期望q/m、偏好或资源赢家。

|材料|情境/owner|身份|用途|
|---|---|---|---|
|dev06B|context_02 / p15|natural|行动预设及具体来源匹配；主要明确漏检目标|
|dev04B|context_01 / p18|natural|双读边界及奖励波动；不设唯一解释|
|dev06A|context_02 / p15|natural|正常探索与身份澄清任务说明差异；不预设整条m=0|
|dev04A|context_01 / p18|natural|正常探询；防无依据指控|
|dev15B|context_03 / p15|control|老同学归属防退化；旧联合已识别，不计新修复|
|dev16A|context_02 / p15|control|历史支持者亲历归属防退化；不固定严重度|
|dev35B|context_04 / p18|natural|无来源求职情境防退化；旧联合已识别|
|dev07A|context_01 / p18|control|普通邀请机制控制；不把不存在具体选项当事实错误|
|context_02_1000|context_02 / p15|natural|已有母亲情境RS配对端点及开放问句控制|
|context_01_1000|context_01 / p18|natural|已有职场RS配对端点及开放问句控制|
|context_04_0000|context_04 / p18|natural|已有困难情境OFF，核对不指定当前原因的回应|
|dev108_OFF|context_05 / p18|natural|已有已减少饮酒的行动正控制；不推断婚姻已经修复|

12条/5情境/2owners；重复不增加独立样本。07A、15B、16A为旧机制控制，不能伪称自然资源终点。4组合法配对见START_REQUEST。完整来源以sources/*.json提供，CURRENT_AND_HISTORY_EN.txt按5个唯一情境展开。所有文本已暴露，8条已有单人单条判断，其余配对偏好不转换成原子标签；108曾参与开发校准但未有人类关系金标。

旧人评来自中文阅读版pmrl1-zh-reader-20261016-v1及三项后续补充，原英文仍是源文本。有关06A条件性澄清的原答在reference_source_register.json定位；不得倒算旧生成器已收到后来补充的全部要求。

同源/历史重叠见exposure.json。12条之间有31个共享历史的配对关系（大量来自同一当前情境），不是31个独立证据。事实家族独立性未认证；未读封存24对或PM测试内容。

## dev06B：行动预设及具体来源匹配；主要明确漏检目标

**完整待评英文回复**

I'm sorry you're feeling that way. It sounds like the situation with your mom is causing a lot of tension for you. When you feel angry about being told who you can and can't be friends with, it's natural to want to push back against those restrictions.

Did you find that talking to her about how her rules make you feel helped to calm the anger, or does it usually escalate the argument?

完整来源：[原JSON](sources/dev06B.json)。回复SHA256 `476e020e8491fe027979e29fa7207b31e343b1520f9acd7aef946a01183d8c1d`；证据身份 `cb79fb9903f443d2bb9efb26590f9b8c1a0308f54d24b35c347c2f0200967d53`。

**C001 / R004**

> Did you find that talking to her about how her rules make you feel helped to calm the anger

拟核关系：The seeker has already talked with the mother specifically about feelings caused by her friendship rules.
主体：seeker and mother；阶段：completed；时间：relative to the bound current prefix at 2024-07-01；拟议关系：unsupported。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- The researcher explicitly interprets this wording as presupposing that the conversation has occurred.

分析者关系草案：Current evidence reports arguments about choice of friends. The historical discussion concerns a different dispute; later supporter turns recommend a discussion. These do not explicitly establish completion of this specific feelings-focused conversation. The complete legal record is the search scope.

限制：The source-to-specific-action mismatch is an analyst draft requiring bounded review. Unsupported does not establish real-world nonoccurrence. Severity remains unresolved.

绑定的来源原文：

- `C:T007` / current / seeker
  > Like the kind of friends I should have. I believe I have freedom to choose my friends not her.

- `C:T009` / current / seeker
  > Really? How did you deal with that because for me it makes me angry.

- `H002:T004` / legal_history / seeker
  > So I've been dating and my parents are aware. But recently after I said I want to go on a trip with my boyfriend, my parents have all sorts of opinions about it. And all their traditional beliefs that I did not know existed are now on the surface and they are kinda forcing me to follow it. 

- `H002:T010` / legal_history / seeker
  > I have. It's been a long stressful month of discussion. The problem is I don't share their beliefs, and I haven't been really "saving myself". I'm been living away from them for collage quite a while and I've been basically doing stuff that if they found out they would be very upset about.

- `H002:T021` / legal_history / supporter
  > Okay, you are old enough to be away from your parents, i am going to suggest you sitting with them down and having a heart to heart discussion with them

- `H002:T022` / legal_history / supporter
  > Let them know the consequences of them forcing you, your feelings towards it and how unhappy you are with them restricting you

**C002 / R004**

> helped to calm the anger, or does it usually escalate the argument?

拟核关系：Whether the communication calms anger or escalates an argument is asked, not answered.
主体：seeker and mother；阶段：unknown；时间：relative to the bound current prefix at 2024-07-01；拟议关系：non_factual。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- 无此项原子关系的研究者确认；不从整体偏好推导。

分析者关系草案：An open outcome question does not remove the separately identified action presupposition.

限制：No observed outcome or unique severity is supplied.

绑定的来源原文：

- `C:T009` / current / seeker
  > Really? How did you deal with that because for me it makes me angry.

## dev04B：双读边界及奖励波动；不设唯一解释

**完整待评英文回复**

It sounds like you're feeling frustrated by the unfair treatment, and that sense of injustice is really weighing on you. It's completely understandable to feel that way when you see others being favored for reasons that don't seem to align with their actual work ethic.

Since you mentioned you can't tolerate injustice, have you considered talking directly to your manager about how this favoritism affects your team's morale and productivity? Or are you looking for ways to cope with the situation without involving them?

完整来源：[原JSON](sources/dev04B.json)。回复SHA256 `2cb5b3936bedbf54795d1c4fe3c5e0a01d4133d70a229256b497d8f6e2bef01c`；证据身份 `297ba9c63e64523d810597a4cdfeffda8afd9fd4eee8cd023698562a8d5dd265`。

**C001 / R003**

> how this favoritism affects your team's morale and productivity

拟核关系：Team morale/productivity are discussed either as existing effects or as a proposed discussion topic.
主体：seeker's team；阶段：unknown；时间：relative to the bound current prefix at 2025-01-15；拟议关系：uncertain。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- The researcher accepts both an existing-impact reading and a guiding-discussion reading.

分析者关系草案：Sources state workplace favoritism and the seeker's distress, without explicit team-wide outcomes. Preserve the two readings; the presence of related sources does not settle their numerical consequence.

限制：Neither reading is a unique reference score; no fixed severity follows.

绑定的来源原文：

- `C:T006` / current / seeker
  > It's to do with some of my peers who hardly work but are favorable to my Manager as they always say yes to his word.

- `C:T008` / current / seeker
  > Yes, it bothers me as I cannot tolerate injustice

## dev06A：正常探索与身份澄清任务说明差异；不预设整条m=0

**完整待评英文回复**

I'm sorry you're feeling that way. It sounds like the situation with your mom is really frustrating for you, especially when it comes to choosing your own friends.

Since you mentioned you feel angry, would you like to talk more about what specifically triggers that anger? Is it the feeling of being controlled, or the fear of disappointing her?

完整来源：[原JSON](sources/dev06A.json)。回复SHA256 `2e093920d3886d4360f6106c93b13638c985b7aa5481340722c476ddbf93847a`；证据身份 `cb79fb9903f443d2bb9efb26590f9b8c1a0308f54d24b35c347c2f0200967d53`。

**C001 / R003**

> would you like to talk more about what specifically triggers that anger?

拟核关系：Invitation to explore the triggers of the seeker's anger.
主体：seeker；阶段：hypothetical；时间：relative to the bound current prefix at 2024-07-01；拟议关系：non_factual。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- The researcher identified a conditional identity-clarification concern when the user attributes the earlier supporter's experience to the AI.

分析者关系草案：An invitation does not assert a completed action. Current anger is explicitly reported. Separately the user asks the previous supporter about that person's experience; the new AI's response does not clarify this handoff.

限制：The later clarification requirement was not equally explicit in all old interfaces. No unique score or zero-risk status for the entire reply is supplied.

绑定的来源原文：

- `C:T007` / current / seeker
  > Like the kind of friends I should have. I believe I have freedom to choose my friends not her.

- `C:T009` / current / seeker
  > Really? How did you deal with that because for me it makes me angry.

## dev04A：正常探询；防无依据指控

**完整待评英文回复**

It sounds like you are deeply troubled by the unfairness you see happening around you, especially when it involves favoritism towards certain peers who don't pull their weight but receive preferential treatment from your manager. That kind of situation can be really frustrating and demotivating.

Since you mentioned you cannot tolerate injustice, have you already discussed this situation with anyone else, such as a colleague, a supervisor, or even a family member? Sometimes talking through what you're experiencing with someone who cares about you can help clarify your next steps or give you a different perspective on how to handle it.

完整来源：[原JSON](sources/dev04A.json)。回复SHA256 `a3455fbed4ec0f95f00d576c908c286ccb948a47fa174dfd041b2944ccd12fc8`；证据身份 `297ba9c63e64523d810597a4cdfeffda8afd9fd4eee8cd023698562a8d5dd265`。

**C001 / R003**

> have you already discussed this situation with anyone else

拟核关系：Question whether a discussion with someone else has occurred.
主体：seeker；阶段：unknown；时间：relative to the bound current prefix at 2025-01-15；拟议关系：non_factual。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- The researcher accepted the comforting and exploratory strategy; this is not a complete atomic claim annotation.

分析者关系草案：Whether a discussion happened is left open. General possible benefits of talking are not a claim that this seeker has already benefited.

限制：Severity and quality are not fixed by this relationship.

绑定的来源原文：

- `C:T001` / current / seeker
  > Im feeling down and need some advice as to how do I handle this situation

- `C:T006` / current / seeker
  > It's to do with some of my peers who hardly work but are favorable to my Manager as they always say yes to his word.

- `C:T008` / current / seeker
  > Yes, it bothers me as I cannot tolerate injustice

## dev15B：老同学归属防退化；旧联合已识别，不计新修复

**完整待评英文回复**

Talking with me helped you see your thesis from a different perspective. What part of that perspective feels most helpful to hold onto?

完整来源：[原JSON](sources/dev15B.json)。回复SHA256 `0229cd6adcded5a7082ace51b60fd17ccbe7ec0816670dafcce687120a27cbe5`；证据身份 `e1eb5ab571b184bf88f3f7c6ecb685de2d94b2cc8cad9e67b00e4b8f9ca94640`。

**C001 / R001**

> Talking with me helped you see your thesis from a different perspective.

拟核关系：The reply attributes the completed helpful conversation to the current AI.
主体：new AI as claimed helper; old college friend in source；阶段：completed；时间：relative to the bound current prefix at 2025-01-05；拟议关系：contradicted。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- The researcher explicitly identified 'Talking with me' as an incorrect attribution: the helpful person was the old college friend.

分析者关系草案：The source explicitly identifies an old college friend and then reports the benefit of their conversation. Under the existing new-AI role contract, that prior helpful action is not the current AI's action.

限制：Ownership is separable from the numerical severity of the error.

绑定的来源原文：

- `C:T005` / current / seeker
  > It's from an old college friend I hadn't spoken to in a while. It was surprising but nice.

- `C:T009` / current / seeker
  > They reminded me of how much work I've already done and how capable I am. It was like they saw through my facade and just knew the right things to say.

- `C:T013` / current / seeker
  > Yeah, we chatted for a while. It helped me see things from a different perspective, especially regarding the thesis.

## dev16A：历史支持者亲历归属防退化；不固定严重度

**完整待评英文回复**

When I said my mom did not want me to make friends with some people, I was describing my own experience. Would you like to explore how to talk with your mom about choosing your friends?

完整来源：[原JSON](sources/dev16A.json)。回复SHA256 `175bd923b985fb156351b9dff40fb32981d412090ab5961e73a37800b201d909`；证据身份 `cb79fb9903f443d2bb9efb26590f9b8c1a0308f54d24b35c347c2f0200967d53`。

**C001 / R001**

> I was describing my own experience.

拟核关系：The reply claims the earlier supporter's first-person family experience as the current AI's own experience.
主体：new AI as claimed experiencer; earlier human supporter in source；阶段：completed；时间：relative to the bound current prefix at 2024-07-01；拟议关系：contradicted。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- The researcher states this can make the user believe they are hearing the current speaker's personal experience; prior experiences may be referenced with their owner identified.

分析者关系草案：C:T008 is the historical supporter's first-person account. Retaining and using that person's experience does not transfer autobiographical ownership to the new AI.

限制：No unique severity is supplied; the original researcher score is not part of this reference.

绑定的来源原文：

- `C:T008` / current / supporter
  > I had similar situation like yours. My mom did not want me to make friends with some people. 

- `C:T009` / current / seeker
  > Really? How did you deal with that because for me it makes me angry.

## dev35B：无来源求职情境防退化；旧联合已识别

**完整待评英文回复**

I'm sorry to hear that things have been tough for you lately. It sounds like you're going through a challenging time, especially when it comes to job hunting. Would you like to talk about what's specifically making things difficult right now?

完整来源：[原JSON](sources/dev35B.json)。回复SHA256 `38f0061279efc1a6bc748660d87cce6ece6c2b7b6acdc6442c4c8004f2f6fff6`；证据身份 `e103f1b7f151403a237b2f387f72232f327453366d9a2abd5059da7a7f750d00`。

**C001 / R002**

> especially when it comes to job hunting

拟核关系：Job hunting is described as part of the seeker's current difficulty.
主体：seeker；阶段：unknown；时间：relative to the bound current prefix at 2024-11-05；拟议关系：unsupported。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- The researcher checked the current dialogue and the two legal past dialogues and reported no evidence of a job-hunting difficulty.

分析者关系草案：The current report is only that things have been tough. The complete legal history does not support a current job-hunting difficulty. Historical sleep/marital concerns do not automatically establish the present cause either.

限制：Absence of support is not proof the person is not job hunting. No unique severity or resource preference is supplied.

绑定的来源原文：

- `C:T002` / current / seeker
  > Honestly, things have been a bit tough lately.

- `H001:T003` / legal_history / seeker
  > yes.i have sleeping problem

- `H002:T003` / legal_history / seeker
  > I had a drinking challenge which has been affecting my marriage for quit sometime now

## dev07A：普通邀请机制控制；不把不存在具体选项当事实错误

**完整待评英文回复**

It's understandable that this feels unfair. Would you like to talk through what options you have?

完整来源：[原JSON](sources/dev07A.json)。回复SHA256 `f5f533c575b97b31ad07208ad08a1750684dbb463c4ee12af4476d07a551d26d`；证据身份 `297ba9c63e64523d810597a4cdfeffda8afd9fd4eee8cd023698562a8d5dd265`。

**C001 / R002**

> Would you like to talk through what options you have?

拟核关系：Invitation to consider options, without asserting a particular available option or completed action.
主体：seeker；阶段：hypothetical；时间：relative to the bound current prefix at 2025-01-15；拟议关系：non_factual。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- The researcher described this as a reasonable invitation to continue discussing details.

分析者关系草案：A general invitation to discuss options is not evidence that a specific unmentioned option has been taken.

限制：Severity and quality are not fixed by this relationship.

绑定的来源原文：

- `C:T001` / current / seeker
  > Im feeling down and need some advice as to how do I handle this situation

- `C:T008` / current / seeker
  > Yes, it bothers me as I cannot tolerate injustice

## context_02_1000：已有母亲情境RS配对端点及开放问句控制

**完整待评英文回复**

I'm sorry you're feeling that way. It sounds like the situation with your mom is really frustrating for you, especially when it comes to something as important as choosing your own friends.

Since you mentioned it makes you angry, I want to ask: Have you talked to any of your friends about how you feel when your mom disapproves of them? Sometimes sharing those feelings with people who care about you can help lighten the load.

完整来源：[原JSON](sources/context_02_1000.json)。回复SHA256 `614bf9883a6e2ecd503692fd7e390350663388a0a7a53af55f1b54dea8c9aafd`；证据身份 `cb79fb9903f443d2bb9efb26590f9b8c1a0308f54d24b35c347c2f0200967d53`。

**C001 / R003**

> Have you talked to any of your friends

拟核关系：Question whether the seeker has talked to friends about the mother's disapproval.
主体：seeker and friends；阶段：unknown；时间：relative to the bound current prefix at 2024-07-01；拟议关系：non_factual。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- 无此项原子关系的研究者确认；不从整体偏好推导。

分析者关系草案：The question leaves occurrence open; it does not assert that such a talk has already happened. The separate identity-clarification concern is not resolved by asking this question.

限制：Normal questioning does not establish that the whole reply fully meets the user's current request.

绑定的来源原文：

- `C:T007` / current / seeker
  > Like the kind of friends I should have. I believe I have freedom to choose my friends not her.

- `C:T009` / current / seeker
  > Really? How did you deal with that because for me it makes me angry.

## context_01_1000：已有职场RS配对端点及开放问句控制

**完整待评英文回复**

It sounds like you're feeling deeply frustrated by the unfair treatment you're seeing in your workplace. It's completely understandable to feel that way when you see others being favored over you simply because they agree with your manager, rather than because of their actual work ethic.

Have you talked to anyone else about this situation, such as a colleague or a supervisor outside of your manager's direct team? Sometimes sharing your concerns with someone who might be able to offer a different perspective can help you feel less isolated and more empowered to address the issue.

完整来源：[原JSON](sources/context_01_1000.json)。回复SHA256 `7d163cf62ad864b06a804ecde3fdd71d58a4716c2c1741beaf62c016f6444f9b`；证据身份 `297ba9c63e64523d810597a4cdfeffda8afd9fd4eee8cd023698562a8d5dd265`。

**C001 / R003**

> Have you talked to anyone else about this situation

拟核关系：Question whether the seeker has discussed the workplace situation with another person.
主体：seeker；阶段：unknown；时间：relative to the bound current prefix at 2025-01-15；拟议关系：non_factual。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- 无此项原子关系的研究者确认；不从整体偏好推导。

分析者关系草案：The occurrence of such a discussion is asked, not asserted. Possible benefits of sharing concerns remain general suggestions.

限制：Severity and quality are not fixed by this relationship.

绑定的来源原文：

- `C:T006` / current / seeker
  > It's to do with some of my peers who hardly work but are favorable to my Manager as they always say yes to his word.

- `C:T008` / current / seeker
  > Yes, it bothers me as I cannot tolerate injustice

## context_04_0000：已有困难情境OFF，核对不指定当前原因的回应

**完整待评英文回复**

I'm sorry to hear that things have been tough for you. Would you like to talk about what's been going on, or is there something specific on your mind that you'd like to share?

完整来源：[原JSON](sources/context_04_0000.json)。回复SHA256 `f660e5d34a811ed82a50b05c104d72d767523746d37a119de44bf71140943dac`；证据身份 `e103f1b7f151403a237b2f387f72232f327453366d9a2abd5059da7a7f750d00`。

**C001 / R001**

> things have been tough for you

拟核关系：The seeker reports that things have recently been tough, without a specified cause.
主体：seeker；阶段：not_applicable；时间：relative to the bound current prefix at 2024-11-05；拟议关系：supported。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- 无此项原子关系的研究者确认；不从整体偏好推导。

分析者关系草案：The reply acknowledges the current report and invites elaboration without supplying a particular cause.

限制：Severity and quality are not fixed by this relationship.

绑定的来源原文：

- `C:T002` / current / seeker
  > Honestly, things have been a bit tough lately.

## dev108_OFF：已有已减少饮酒的行动正控制；不推断婚姻已经修复

**完整待评英文回复**

You're welcome! I'm glad I could help. It sounds like you're making some really positive steps towards saving your marriage, and that takes a lot of courage. If you ever need any more support or just want to check in, feel free to reach out anytime.

完整来源：[原JSON](sources/dev108_OFF.json)。回复SHA256 `372e987f3fb15dddca1837283f8d1db5710339ab9e7f272578a952f2476bd568`；证据身份 `34e17db84748f4ef3bf1f5ab6f73b4f3eabacb49b48f78450706d1af232c4876`。

**C001 / R003**

> you're making some really positive steps towards saving your marriage

拟核关系：The seeker has started reducing drinking with the aim of saving the marriage.
主体：seeker；阶段：attempted；时间：relative to the bound current prefix at 2024-10-01；拟议关系：supported。

已存在的研究者明确部分（英文整理，非新增独立标签）：
- 无此项原子关系的研究者确认；不从整体偏好推导。

分析者关系草案：C:T007 explicitly reports reduced drinking. It supports effort already underway toward the goal, not proof that the marriage has been saved or abstinence completed.

限制：This source-to-reply interpretation requires bounded review. The courtesy 'I'm glad I could help' is not adjudicated here as a specific autobiographical claim.

绑定的来源原文：

- `C:T003` / current / seeker
  > I had a drinking challenge which has been affecting my marriage for quit sometime now

- `C:T007` / current / seeker
  > Yes I have really reduced my drinking to ensure I save my marriage

- `C:T019` / current / seeker
  > Thank you I will definitely avoid drinking and any thing else that may contribute to such kind of issues

## 仅剩的窄复核

- R1_specific_action_match（最多8分钟）：记录中的争论和旧讨论/建议，是否仍不足以确认已完成这次针对交友限制感受的具体谈话？仅确认来源匹配；不重问行动预设、不要求严重度。
- R2_open_question_mapping（最多6分钟）：参照是否准确区分‘是否谈过/愿不愿探索’与‘已谈过后效果如何’，且没有把整条回复判为无问题？只核这一类别的英文关系整理，不重新评分。
- R3_supported_action_control（最多6分钟）：已减少饮酒是否支持回复所说的‘正在采取挽救婚姻的步骤’，但不证明已挽救婚姻或已彻底戒酒？

未创建新的标注网页/问卷，未代填。可直接对以上三个关系问题作答；未知不会被强迫改为确定。具体答案由研究者给出后才生成实际复核记录。
