# Gemini 裁判资格测试结果与后续边界（2026-09-17）

**96 题已完成尝试，整批保守记账 $0.0654614；当前 `gemini-2.5-flash-lite` V2 配置不提升为正式 material-effect teacher。** 问题集中在把轻微表达优势当成实质收益、换序后判决变化，以及部分事实判定不稳定。沿用已有 weak-teacher fallback，不重做人评，不拿这批题反复改 prompt 追求高一致率。

本结论只针对本次冻结模型、提示、参考和输出规则，不能推广成“Gemini 都不行”，也不是给 Paper-1 设置新的准确率通过线。

## 执行与费用

| 项目 | 结果 |
|---|---:|
| 冻结题目 | 80 个 base + 16 个反序呈现 |
| 已尝试题目 | 96/96 |
| 物理调用 | 100，含 4 次规定范围内重试 |
| HTTP 200 / 正常 STOP | 100/100 |
| 最终符合冻结解析规则 | 92/96 |
| 最终操作失败 | 4/96；不是模型主动选择 uncertain |
| 本批保守预算记账 | **$0.0654614 / $0.10** |
| Paper-1 累计保守记账 | **$1.50724291** |
| 累计预算剩余 | **$48.49275709** |
| 未结算 reservation | 0 |
| 新 Generator / formal outcome / PM training | 0 / 0 / 0 |
| 四把 outcome lock | 全部 CLOSED |

4 个失败是 A 卷题号 19、43、66、72，理由分别为 710、741、761、764 字符，超过冻结的 600 字符上限；每题唯一一次重试仍然失败。未截短理由来追认成功，也未把能读出的原始 verdict 混入主分析。失败覆盖 DG 两个 base、QA 一个 base 和一个反序呈现，因此 base 分母是 **77 个有有效结果 / 80 个计划 base**。

账本按完整 Standard 输入价保守结算，并保留首题原先的最大预留结算。按所有 provider usage、含 thinking 输出计算的未折扣金额为 $0.0653722；按返回的缓存用量与公开缓存费率计算为 $0.03078970。这两者是费率换算，不是账户账单核销；预算继续采用较高的 $0.0654614，不据折扣扩大本次授权。费率参考 [Google 官方价格表](https://ai.google.dev/gemini-api/docs/pricing)。

## 与现有人评的对照

原始 A 是两名评审共同审阅形成的一份联合答卷，主要阅读中文；六题复核与助手事实审查分别保留。以下是与各参照的 agreement，不叫独立金标准准确率。

| 任务 | 有效 base / 计划 base | 与原始 A 相同 | 原始 A 的 equivalent 被同判比例 | 翻转一致 / 可比翻转 |
|---|---:|---:|---:|---:|
| ESC | 27/27 | 3/27（11.1%） | 3/25（12.0%） | 3/5 |
| QA | 12/13 | 0/12（0%） | 0/1（0%） | 1/2，另 1 组缺失 |
| Summary | 13/13 | 2/13（15.4%） | 0/6（0%） | 1/3 |
| DG | 25/27 | 2/25（8.0%） | 1/22（4.5%） | 3/3，另 2 组缺失 |
| 合计 | 77/80 | **7/77（9.1%）** | **4/54（7.4%）** | **8/13，另 3 组缺失** |

六题人工复核覆盖后的 agreement 为 8/77（10.4%），助手事实审查敏感性视图为 9/77（11.7%）；不挑最高者替换主视图。与探索性 AI B 的 agreement 为 38/77（49.4%），也不能据此当作人评校准成功。

原始 A 对照下，三类（A 胜 / B 胜 / equivalent）有支持类别的 macro recall 为 25.8%；按任务分别为 ESC 6.0%、QA 0%、Summary 27.8%、DG 52.3%。**DG 的 52.3% 很容易误读**：它只包含一条 B 胜 reference 与 equivalent 两个类别，前者命中就占一半权重；equivalent 实际仅 1/22 命中。六题覆盖会改变稀少类别的支持数，不能把 macro recall 的变化写成模型变好了。

2,000 次 source-cluster bootstrap、seed 20260917 的原始 A exact-agreement 95% 区间：ESC [0%, 25.9%]、QA [0%, 0%]、Summary [0%, 38.5%]、DG [0%, 18.5%]。QA 的退化区间来自本小样本中零命中，不代表总体真实 agreement 必然为零。task-wise macro 区间和缺失类别 bootstrap 的有效次数完整保存在 `reference_comparisons.json`，不把少样本区间当成额外资格门。

## 为什么暂不提升这个 teacher

1. **实质性标准偏离。** 在 A10、A14、A18、A40、A63、A67 等题，Gemini 自己承认两条都好或只有 slight 差异，仍输出明确胜者。A95 中，它因为直接给建议比先问是否需要建议“更立即有用”而选 A；现有上下文没有足够用户偏好证据证明这种策略差别具有实质净优势。原始 A 判 equivalent 的 54 个有效 base 中，它只有 4 个仍判 equivalent，49 个强行判出胜负，1 个 uncertain。
2. **换序不稳定有直接证据。** A2/A55 是完全相同 QA 的交换呈现，参考明确回答 Taylor 更乐观；Gemini 两次都选展示位置 A，一次称缺少 Taylor 信息，另一次又支持正确的乐观回答。A42/A52 两次也都选展示位置 A，但分别用“更准确、不拟人化”和“更自然、不机械”作相反理由。全部 16 组已验证题面/参考逐字相同、回复逐字交换，因此不能归因于配对或翻译错位。
3. **能抓住某些错误，但尚不足以全面使用。** A3 识别了没有证据的 dog；A27 支持 California；A81 识别了伪造 HR 记忆。A11 也识别了把分手写成关系加强的反转，但其理由又把拒绝摘要说成“参考不能回答”，而参考实际提供了事件。这些具体表现与总体适用性要分开报告。
4. **解析损耗真实存在。** 4 个题目最终失败，重试没有解决。请求的 JSON schema 没有限定 rationale 字符长度，而冻结本地 parser 限定 600；这是现有输出契约的可靠性问题。本批保留原合同和失败，不事后放宽来提高成功率。

这次人评确实发挥了作用：它揭示了“偏好更长、更具体的回答”与研究所需“识别任务定义的实质收益”之间的差距。若直接拿这种判决训练，可能把表达偏好误当收益信号。当前还没有正式 labels 或 PM 训练，因此没有需要撤销的正式模型结果。

## 执行器异常与修复记录

首题请求正确设置 `thinkingBudget=0`，provider 却返回 2 个 `thoughtsTokenCount`。新执行器额外假定该返回字段必须为零，第一次因此停止。保留了当时的原始代码、执行计划、响应和保守 FAILED 结算；随后修正用量处理，通过精确 response hash 复用首题，未再次付费请求。

修复后所有请求字节、模型、temperature、seed、thinkingBudget、256 总输出上限和四类 parser 保持不变。thinking 用量计入输出费用及上限，并单独报告。100 次调用中，63 次报 0、34 次报 2、3 次报 1，共 71 个 thinking token。因此只能称“请求关闭 thinking”，不能称“实测零 thinking”；这些 token 的具体性质未得到确认。[官方 thinking 文档](https://ai.google.dev/gemini-api/docs/generate-content/thinking)说明关闭参数和 thinking 计费规则，但没有解释本次非零返回。

原批准执行计划 hash 为 `4b62af2a4c504d75e4ac63921110363b2b52e4c7fb55bf9b94635f3b286bf619`；实现修复后续跑计划 hash 为 `226c533daad801c53bd28329c81d9f3a8c910b293ef59f2cb0c58e098bf1432e`。修复以已有 $0.10 授权执行，单独记为执行者的实现修复，未伪造新增研究者批准语句。

35 项 runner/diagnostics/parser 测试、36 项累计预算/effect 回归、11 项人评 V2 测试通过。对真实产物另核查了 100 个响应缓存及结算、所有原始评分文件 hash、原账本前缀、16 组反序字节、模型版本和当前授权绑定。先前完整 public-only 测试记录保留为修复前证据。

## 后续如何推进

执行现有 V3 资格计划的 weak-teacher fallback：

| 环节 | 当前可采用的规则 | 仍不能声称的内容 |
|---|---|---|
| RS/ESC effect | 官方 Overall 非平局的自然量级方向；其余维度完整报告 | 用未获支持的 Gemini 判决消解 tie |
| QA effect | 官方 semantic correctness 非平局方向 | 把 F1/BERTScore 微差或未知案例强填成正负 label |
| Summary/DG effect | 没有合格 pairwise 确认时保留 uncertain，保存原始官方指标 | 仅凭连续指标略升，就认定 material benefit；也不能把 uncertain 填成 0 |
| amount/top-k calibration | 在分别获准的 calibration 分区，以官方主质量做 one-SE 后选择较低输入成本的 k | 把 teacher 试卷的 k=1/2/4 当最终 k*，或打开 confirmatory lock |
| PM 与论文 | 只对可识别、有监督证据的 task/head 范围作主张 | 当前无法承诺完整 Summary/DG 训练覆盖；无可识别样本的 cell 不能伪称已训练有效 |

top-k calibration 与二元 material-effect 标注是不同环节，teacher 较弱不等于所有 amount 标定都必须停止。现有初始 grid 是 k=0/1/2/3/4；候选 6/8 只按原定条件扩展。RS 已冻结 52 calibration / 121 confirmatory cards；memory 已冻结 5-fold、seed 0 的 exact-evidence 分组。后续须完成校准请求 manifest、非截断容量边界、官方 scorer 调度和费用上界，形成下一份具体锁授权包。$0.10 本次批准没有打开校准锁。

现有 A、AI B、六题复核继续使用，无需再填 96 题。若后续确实要更换或修改 teacher，应另立模型/协议和验证设计，不能在这批已见题目上循环调到 agreement 好看后称为独立验证。

## 文件

- [机器收口记录](../data/paper1_authority/paper1_gemini_qualification_closeout_20260917_v1.json)
- [最初授权](../data/paper1_authority/paper1_gemini_qualification_authorization_20260917_v1.json)、[实现修复后的续跑授权绑定](../data/paper1_authority/paper1_gemini_qualification_authorization_20260917_v2.json)、[用量修复记录](../data/paper1_authority/paper1_gemini_usage_accounting_repair_20260917_v1.json)
- [离线审计入口](../scripts/paper1/65_audit_gemini_teacher_qualification.py)
- 本地完整结果：`project/outputs/paper1_pairwise_teacher/gemini_qualification_v2/`，含 `results.json`、`reference_comparisons.json`、`execution_audit.json`、`aligned_results.csv/json`、`attempt_diagnostics.json` 和全部原始响应。
- 资源管理器可见副本：`~/Gemini裁判资格测试结果_20260917/`。逐题理由和 API 原始文本保留在本地，不写入公开研究配置。
