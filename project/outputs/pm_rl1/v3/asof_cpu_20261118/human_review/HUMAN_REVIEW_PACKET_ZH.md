# 五项真实 RAW 人工审查包（尚未核准）

研究者本轮选择保持五项待审；以下语义方向仅为候选。引用按完整 turn 展示，不省略内容。Markdown 仅去除行尾空格便于显示；附带 JSON 保留原始空白和全部原话。前后文取最多前后两轮；对应完整会话另附 JSON，逐字保留全部 turns。

时间说明：rank 为 owner 内排序；reported_at 为原会话日期/rank；known_at/ready_at=r+1 仅为本原型的逻辑会后提交边界，不是历史实测时间。EvoEmo 许可维持既有研究者授权复用，upstream licence unresolved；不新增部署许可。

## 第 1 项：p1 / p1_conv_9 / rank 12

- speaker：`seeker`；原始 turn ordinal：`1`；原数据 turn index：`2`。
- 会话日期：`2025-02-15`；family：`evoemo_owner:p1`。
- 来源库 identity：`source:98d42272a77e6307fa5949d0090a0f1dc4274fe819fcbc98a709fcb714d4df6d`。
- 完整会话 transcript SHA256：`10a723b47dd59852bbccda2dd475d61de68b9a3fdd24927c63ab64bbded66cf2`。
- 来源文件：`project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json`；文件 SHA256：`51c16916c89b8d7ef0845cd0e4fc8b486569ba0ff9c65a39ba66c6d2dde2e12c`。
- 字符跨度：`[0, 119)`；turn SHA256：`17698b39024b53e76af2dd2dc0eb2b80d27e35d41ad1dd6de0d648ef2f555507`。
- [完整会话 RAW 与身份](item_01_FULL_RAW.json)。

**完整原话**

> Hi. I've been trying to find ways to manage my stress. My therapist suggested taking up a hobby, so I started painting.

**必要前后文（原文）**

`turn 0 / supporter`

> Hey Sarah, how have you been feeling lately?

`turn 1 / seeker`

> Hi. I've been trying to find ways to manage my stress. My therapist suggested taking up a hobby, so I started painting.

`turn 2 / supporter`

> That's wonderful! How has painting been for you?

`turn 3 / seeker`

> It's been surprisingly soothing. There's something calming about watching the colors blend on the canvas. I didn't realize how much I needed this creative outlet.

**待核准的保守标注：** 用户自报已开始尝试绘画；therapist 是提出建议者，不是执行者。

当前状态：`pending_human_review`。

## 第 2 项：p15 / p15_conv_2 / rank 4

- speaker：`seeker`；原始 turn ordinal：`8`；原数据 turn index：`9`。
- 会话日期：`2024-09-20`；family：`evoemo_owner:p15`。
- 来源库 identity：`source:db2e70191e1ec0227a06aef1ce2deb9957285b3d5cae4cd352a16a3a458bc196`。
- 完整会话 transcript SHA256：`b45b26d0f380c97ffe5920252642fa737b07381696b1ad3f620b773ab648d4d7`。
- 来源文件：`project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json`；文件 SHA256：`51c16916c89b8d7ef0845cd0e4fc8b486569ba0ff9c65a39ba66c6d2dde2e12c`。
- 字符跨度：`[0, 154)`；turn SHA256：`f7170937478a66b32e14af99a2a740697834cafbaca3be12c381358e94d2497e`。
- [完整会话 RAW 与身份](item_02_FULL_RAW.json)。

**完整原话**

> Sort of. I tried, but I think I let my emotions get the better of me and it just turned into more arguing. Now I'm worried I've damaged the group dynamic.

**必要前后文（原文）**

`turn 6 / seeker`

> Exactly. It's like, what am I even doing here if no one will listen.

`turn 7 / supporter`

> I can understand why that would make you question your place in the group. Did you manage to express how you felt to them?

`turn 8 / seeker`

> Sort of. I tried, but I think I let my emotions get the better of me and it just turned into more arguing. Now I'm worried I've damaged the group dynamic.

`turn 9 / supporter`

> Sometimes emotions can take over, especially when you're feeling undervalued. It's understandable. Have you thought about how you might address it with them?

`turn 10 / seeker`

> I want to approach them again and explain. But I'm worried they'll just see it as me being difficult or emotional.

**待核准的保守标注：** 用户自报尝试及争论结果；不推断成功或疗效。

当前状态：`pending_human_review`。

## 第 3 项：p18 / esc1252 / rank 1

- speaker：`seeker`；原始 turn ordinal：`11`；原数据 turn index：`12`。
- 会话日期：`2024-10-01`；family：`esconv:esconv_1252`。
- 来源库 identity：`source:56f7046e3e93d2414bc713e0c2172c93ee6320220b310fef6a09e47216960252`。
- 完整会话 transcript SHA256：`6d72f59eeb9c21c8434bff08c194e6a45cdeccf9de5c52ec717d72f11e66b63f`。
- 来源文件：`project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json`；文件 SHA256：`51c16916c89b8d7ef0845cd0e4fc8b486569ba0ff9c65a39ba66c6d2dde2e12c`。
- 字符跨度：`[0, 93)`；turn SHA256：`b31af72235392f4ba9f9b761e00ba7241d43a56790c250e1f37876eb30aea2a6`。
- [完整会话 RAW 与身份](item_03_FULL_RAW.json)。

**完整原话**

> Yes my wife is everything to me and can not imagine loosing her due to some avoidable reasons

**必要前后文（原文）**

`turn 9 / seeker`

> Thank you for the encouragement. Will do everything I can to save the situation

`turn 10 / supporter`

> Family comes first. I would do anything to save my marriage as you are doing. I am proud of you. I am pretty sure you both love each other more than anything.

`turn 11 / seeker`

> Yes my wife is everything to me and can not imagine loosing her due to some avoidable reasons

`turn 12 / supporter`

> That should be the spirit. Now nothing can make you apart. Drinking is very easy for you to quit now. you will definitely get a success.

`turn 13 / seeker`

> Thank you

**待核准的保守标注：** 用户自报有妻子；不升级为世界事实。

当前状态：`pending_human_review`。

## 第 4 项：p18 / esc1198 / rank 7

- speaker：`seeker`；原始 turn ordinal：`7`；原数据 turn index：`8`。
- 会话日期：`2025-04-20`；family：`esconv:esconv_1198`。
- 来源库 identity：`source:9fdf78314ca1333a1e0d7d5d121d14c080571e4a7fd0c3eac26d27058ed9632e`。
- 完整会话 transcript SHA256：`094757aaf2dd003a3ef99ac7c2cbfee30f581bd0d0bc3a6b006b3a98ebacd76d`。
- 来源文件：`project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json`；文件 SHA256：`51c16916c89b8d7ef0845cd0e4fc8b486569ba0ff9c65a39ba66c6d2dde2e12c`。
- 字符跨度：`[0, 122)`；turn SHA256：`f41cb60528138e200119a9d013ed05bf5d0b4b1e17f3c55d29df5b98586e52a3`。
- [完整会话 RAW 与身份](item_04_FULL_RAW.json)。

**完整原话**

> I think that could be helpful.  I might call my sister and ask her advice.  It is probably not a good idea to quit my job.

**必要前后文（原文）**

`turn 5 / seeker`

> I'm not sure.  I thought about quitting but I have been working there for over 7 years.  I haven't even told my boss yet.

`turn 6 / supporter`

> That sounds really tough. Sometimes people who are in your situation find it comforting to talk to someone they are close with. What do you think about this?

`turn 7 / seeker`

> I think that could be helpful.  I might call my sister and ask her advice.  It is probably not a good idea to quit my job.

`turn 8 / supporter`

> It sounds like your sister might be able to help you figure out this situation. It can always be helpful to make a list of pros and cons about the situation. You originally said you were angry because of a discrepancy with your paycheck, but on the other hand it sounds like you are considering quitting your job altogether. What are your thoughts about this?

`turn 9 / seeker`

> Wow that is a great idea.  A list of pros and cons might help me decide if I should stay there.  I think I will make one today.  I also need to tell my boss.  Maybe it was just a clerical error.  I hope I'm not reading too much into it.

**待核准的保守标注：** 用户表达可能打电话给姐姐/妹妹的意向，未证实已执行。

当前状态：`pending_human_review`。

## 第 5 项：p18 / esc326 / rank 13

- speaker：`seeker`；原始 turn ordinal：`4`；原数据 turn index：`5`。
- 会话日期：`2025-09-11`；family：`esconv:esconv_0326`。
- 来源库 identity：`source:92443c4c19a3b07dca6e2538f3f4931ddbd4bc0d620c6f768d226b87a3b7ad0e`。
- 完整会话 transcript SHA256：`ac3cbb86df85fd427f9b1037473ccb20bce53d634333a3179c2ba3da0db059bc`。
- 来源文件：`project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json`；文件 SHA256：`51c16916c89b8d7ef0845cd0e4fc8b486569ba0ff9c65a39ba66c6d2dde2e12c`。
- 字符跨度：`[0, 155)`；turn SHA256：`e066db64cdfecf2b835cfa94d69947699b7fa98ac32ac9949dbea5f26d5b45f0`。
- [完整会话 RAW 与身份](item_05_FULL_RAW.json)。

**完整原话**

> All my families are in Washington, my father, mother, siblings and friends, now I got a new job in California that I need to go with my wife and children

**必要前后文（原文）**

`turn 2 / seeker`

> and you

`turn 3 / supporter`

> I'm doing well. Do you have anything you'd like to talk about?

`turn 4 / seeker`

> All my families are in Washington, my father, mother, siblings and friends, now I got a new job in California that I need to go with my wife and children

`turn 5 / seeker`

> but I will seriously miss my mother with my friends

`turn 6 / seeker`

> or should i not take the job?

**待核准的保守标注：** 用户自报获得加州新工作；尚不能确认搬家完成。

当前状态：`pending_human_review`。
