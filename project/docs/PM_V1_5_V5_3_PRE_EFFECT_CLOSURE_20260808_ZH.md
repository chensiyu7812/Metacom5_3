# PM V1.5 V5.3 正式 Effect 前收口决定（2026-08-08）

## 结论

本轮不读取新quality/risk outcome，不调用付费API。四项方法问题已在结果前处理：

1. Step1不再把quality、risk、functional use与cost悄悄压成一个未明权重的gold。四个组件使用低容量component bundle；primary预测“可采用的开启”，risk只在支持足够时作辅助概率，cost由运行时确定。
2. 正式Step2 recovery固定为`deterministic_fallback`。一次逻辑臂最多一次自由生成；bounded rewrite只作开发诊断。
3. 建立4语义族×16动作的64-case内容独立Step2资格计划，逐条记录requested、realized、function、grounding、atomic、risk和fallback。结构计划不冒充真实generator通过。
4. ±0.05非劣界只作为参考解释，不再作为“PM是否学会”的单一二元门。样本按真实user/family/group和feature rank冻结，宽CI如实报告。

## “及格、能用”的三级证据

- `SUPPORTED`：非平凡ON/OFF选择、胜恒开恒关与matched controls，系统QRC点估计及cluster CI均满足参考比较。
- `DIRECTIONALLY_USABLE`：PM确实学会非平凡选择、优于matched/trivial controls，质量没有实质恶化的点估计且risk或cost改善，但独立cluster少导致CI宽。
- `NOT_SUPPORTED`：恒开/恒关坍缩、未胜matched controls、质量点估计实质变差或组件支持不可解释。

因此16个sealed用户若产生宽CI，不会被写成“自动失败”；它限制证据强度，但不能抹去真实的可学习与端到端方向。所有点估计、CI和失败例仍完整报告。

## 当前完成与待执行

已完成（零API）：

- Step1多目标estimand代码与冻结入口；
- 正式deterministic fallback默认实现；
- static release与16动作结构计划的recovery语义统一；
- 64-case语义资格计划与review字段；
- 64-case的36个语义surface已对ESConv、EvoEmo/ES-MemEval和当前11人formal intake完成exact/normalized 8-gram审计，碰撞均为0；
- feature identifiability/effective-N审计器；
- 全局问题账本新增立即修复及`PENDING_MUST_WATCH`项。

当前P2R开发蓝图的审计结果也揭示了一个必须在正式训练前处理的容量约束：虽然共有868行、381个counterfactual group，但MP/MS/ME各只有20个独立用户，RS有36个；保守可支持的primary feature数分别只有4/4/4/7，明显小于当前12–15个可变列。因此正式trainer不能“有什么列就全喂进去”。完整80人formal blueprint生成后须重跑审计、去掉常量和不可部署列，并将primary head压到实际用户簇支持的低容量；多余特征只进入探索性消融。

待执行：

- 用正式同栈generator运行64-case资格计划，需要独立预算identity与用户费用授权；
- 正式80人catalog及current-state blueprint完成后，重跑shortcut、feature rank和有效group审计；
- paired effect产生后才检查label shape、class support与最终effect N；
- interaction、rater sensitivity和外部同源报告按账本执行，禁止结果后修surface/prompt。

## 责任边界

正式报告按以下链路归因：

`source/oracle candidate → actual Rank-1 → structural eligibility → PM requested action → Step2 realized action → functional contribution → grounding/risk → QRC`

检索没找到、PM关错、generator没用和资源本身没收益必须分别报告；任何一层不得替另一层背锅。
