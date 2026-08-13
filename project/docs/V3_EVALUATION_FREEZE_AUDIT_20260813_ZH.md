# MetaCom V3 Evaluation Freeze Audit

日期：2026-08-13

## Overall Assessment: Needs revision before new head decisions

当前 V3 的四层证据方向正确，但 evaluation 尚未达到可以裁定“PM学会/没学会”的状态。内部 Quality/Risk/Function panel 只可保留为开发诊断；正式研究必须先完成数据身份、官方实现、scorer、margin、统计单位与主张边界冻结。

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
2. **Critical — No qualified generator pass margin.** 当前没有在公开人工标签上校准ESC-RANK，也没有同栈reference和outcome-blind NI margin；而官方scorer仓库本身存在路径与环境缺口，因此不能仅凭一个ESC自动分数决定微调。
3. **High — Training/exam overlap unresolved.** ESC-Eval角色卡和ESC-Role训练来源含ESConv/ExTES；若以后用这些数据做generator SFT，必须先冻结考试身份并做source/dialogue/semantic overlap筛查。
4. **High — PM Quality/Risk margins not anchored.** 现有pairwise judge可作测量组件，但尚无公开anchor、人类小样本校准、跨judge稳定性和practical-effect依据来冻结NI margin。
5. **High — Atomic Risk taxonomy is ahead of adjudication.** 事件类别已明确，但还缺双评、分歧裁决、`UNCERTAIN`处理和owner-cluster上界方案。
6. **Medium — Current stress run is incomplete.** 42/90只能说明执行进度；48次缺失补齐前，arm差异和head结果均不可计算。

## KPI与通过标准建议

- Generator primary：ESC-Eval七维、overall和completion；ESC-Judge E/I/A只作pairwise sensitivity；另列low-burden、安全信号处理guardrail。
- Memory primary：QA Token F1/BERTScore、retrieval Recall@k/nDCG@k、abstention false-answer、summary event-F1和generation observation metrics；LLM评分为secondary。
- PM primary：same-state blind Quality、atomic Risk、actual generator input tokens；Function、requested-to-received、latency和USD为secondary/diagnostic。
- 不建立Quality/Risk/Function/Cost复合总分；任何主指标恶化不能由成本或Function抵消。
- fixed-high成本线暂定输入token至少降低10%；其余margin待calibration/reference后冻结，不能事后从正式结果选择。

## Required fixes before P0 exit

1. ~~获取或重建正式1,209题ID。~~ 已完成替代路径：冻结`ES-MemEval-Public-v1.0.0-1427`及逐题manifest，并禁止写精确论文复现。
2. 固定ESC-Eval代码/data/scorer commit，在公开human annotation上重算校准表现。
3. 冻结一个same-stack generator reference，预先确定cluster和NI margin推导方法。
4. 冻结ESC-Judge版本、judge、位置互换、tie/invalid处理和少量human anchor。
5. 物化ESConv/ExTES与ESC-Eval source/dialogue/semantic overlap表。
6. 完成atomic Risk codebook、双评/裁决与critical-event上界。

## 2026-08-13 执行进展

本审计列出的 implementation、overlap 和 Risk mechanical 三项已经进入可审计实现：官方commit与本地runtime边界已锁；ESC-Eval中228张ESConv/ExTES同源卡已完成source/exact/normalized/semantic物化；Risk已生成18个fixture包和36个盲评任务。这里不回写原审计判断：Risk仍未通过人类资格化，scorer/reference/margin也仍阻塞P0退出。
7. 之后才补48次冻结生成并按新评价层级判读；不允许回到旧Function veto。

## Confidence

对“应暂停head循环并先完成evaluation freeze”的结论为高置信。对具体NI数值目前不设置信度，因为必要的scorer calibration、same-stack reference与人类anchor尚未执行；此时给出精确阈值会制造伪精确。
