# MetaCom V3 Evaluation Freeze Audit

日期：2026-08-13

## Overall Assessment: P0 evidence architecture and official scale mapping complete; P1 measurement qualification required

当前 V3 的四层证据方向正确，P0已完成数据身份、官方实现责任、scorer用途、margin推导程序、统计单位与主张边界冻结；官方ESC-RANK七维映射错误也已纠正。evaluation仍未达到可以裁定“PM学会/没学会”的状态，因为P1数值校准、runtime资格、judge/人类一致性和generator选择尚未执行。内部 Quality/Risk/Function panel 只保留为开发诊断。

## 已验证

1. **ESConv 数据身份通过。** 本地 `ESConv.json` 与官方 commit `f262d06` 的远程文件 SHA-256 均为 `aa0556...d9af`；包含1,300个dialogue、38,365个turn。统计单位冻结为dialogue，只进入RS单会话track。
2. **EvoEmo公开身份可定位。** ES-MemEval仓库tag `v1.0.0` 指向commit `6926242`；`evo_emo.json` SHA-256为`f30698...d420`，包含18个合成用户和401个session。统计单位是user。
3. **ES-MemEval版本冲突已证实。** 正式WWW 2026论文是1,209 QA；公开`v1.0.0`文件是1,427 QA，多218道。125个summary与34个generation scenario一致。418题只是历史项目子集。
4. **ESC-Eval适合作为外部资格考，但有明确construct边界。** 论文评测655张角色卡、14个模型、约8.5K段对话和59,654项人工标注；同时依赖模拟用户、GPT-4抽取角色卡和14名非英语母语标注者。建议rubric对超过五条有效建议给最高分，与本项目低负担原则不完全一致。
5. **ESC-Judge适合作为敏感性分析。** 它提供E-I-A成对比较和位置互换流程，但论文实证只有25个合成角色，judge为o1-mini，人工核验是两位博士级标注者对100个pair的判断。

6. **官方实现并不等于可直接复现。** ESC-Eval公开的英文331与中文324张高质量卡总数与论文655一致，但仓库没有依赖锁或许可证文件，runner硬编码旧候选模型，scorer还存在`ESC-RANK1/fluency`路径不一致。ESC-Judge公开100个`roles-v1`角色，却没有给出论文25角色身份；当前comparison脚本也没有实现A/B双向互换。
7. **ES-MemEval的公开历史无法恢复1209题。** `v1.0.0`仓库只有两个公开commit，数据文件未发生变化；检查到的公开issue也没有解释或列出1209/1427映射。因此不能靠继续翻git解决，必须获取权威ID或明确采用独立命名的1427-row public task。
8. **V3已采用可复现的公开身份。** 主任务冻结为`ES-MemEval-Public-v1.0.0-1427`，逐题manifest包含1427个唯一row ID、问题/答案/证据hash和capability，但不含原文。论文中必须同时披露它不是final-paper-1209的精确复现。

## Issues Found

1. **Resolved with claim boundary — ES-MemEval formal row identity unavailable.** V3不再等待不可见的1209 ID，而是使用完整public-v1.0.0-1427并禁止精确论文复现措辞；418题仍不得替代主任务。
2. **Resolved at design level — ESC-RANK cannot supply an absolute pass line.** 公开仓库无逐条人标或split ID；修复版scorer仅作描述性七维外部指标。generator决策改由硬可靠性、executor、同栈70B、ESC-Judge与Risk共同支持。
3. **Resolved — Training/exam overlap.** 228张ESConv/ExTES同源卡已逐项冻结；若两源都用于SFT，英文主考卷隔离为103张。
4. **Resolved at design level — PM Quality/Risk margin derivation.** P0已冻结非正式双评anchor、上限与登记流程；具体数值必须在P1、正式outcome前写入。
5. **Resolved at design level — Atomic Risk.** taxonomy、双评、裁决、`UNCERTAIN`、owner cluster、18包/36分配和gold承诺已冻结；实际双评资格属于P1。
6. **Medium — Current stress run is incomplete.** 42/90只能说明执行进度；48次缺失补齐前，arm差异和head结果均不可计算。

## KPI与通过标准建议

- Generator primary：ESC-Eval七维、overall和completion；ESC-Judge E/I/A只作pairwise sensitivity；另列low-burden、安全信号处理guardrail。
- Memory primary：QA Token F1/BERTScore、retrieval Recall@k/nDCG@k、abstention false-answer、summary event-F1和generation observation metrics；LLM评分为secondary。
- PM primary：same-state blind Quality、atomic Risk、actual generator input tokens；Function、requested-to-received、latency和USD为secondary/diagnostic。
- 不建立Quality/Risk/Function/Cost复合总分；任何主指标恶化不能由成本或Function抵消。
- fixed-high成本线暂定输入token至少降低10%；其余margin待calibration/reference后冻结，不能事后从正式结果选择。

## Required fixes before P0 exit（已完成）

1. ~~获取或重建正式1,209题ID。~~ 已完成替代路径：冻结`ES-MemEval-Public-v1.0.0-1427`及逐题manifest，并禁止写精确论文复现。
2. ~~固定ESC-Eval代码/data/scorer commit，在公开human annotation上重算校准表现。~~ 已确认人标不公开，冻结“描述性可用、绝对pass不合格”的替代责任。
3. ~~冻结一个same-stack generator reference，预先确定cluster和NI margin推导方法。~~ 已选NVIDIA Llama 3.3 70B并冻结规则。
4. ~~冻结ESC-Judge版本、judge、位置互换、tie/invalid处理和少量human anchor。~~ 设计已冻结，P1执行待单独批准。
5. ~~物化ESConv/ExTES与ESC-Eval source/dialogue/semantic overlap表。~~ 已完成228行与103卡隔离考卷。
6. ~~完成atomic Risk codebook、双评/裁决与critical-event上界。~~ 设计与fixture已完成，P1执行待批准。

## 2026-08-13 执行进展

P0九个证据架构门均已进入可审计实现。这里不再用“9/9”暗示评价有效性已经解决：Risk人类资格、数值margin、scorer/judge可靠性和benchmark结果仍在P1阻塞正式判决。G0现比较8B、70B和Qwen 3.7 Plus，不能用ESC-RANK Average单独选模型。

旧48次冻结生成不再自动成为下一步：先选择generator；保留8B才补，换70B则旧42/90归档，禁止混栈补齐。

## Confidence

对“应暂停head循环并先完成evaluation freeze”的结论为高置信。对具体NI数值目前不设置信度，因为必要的scorer calibration、same-stack reference与人类anchor尚未执行；此时给出精确阈值会制造伪精确。
