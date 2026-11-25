# PM-RL1-J：研究者与 Codex 的执行入口

## 当前状态
- 主方案：[MASTER_PLAN_ZH.md](MASTER_PLAN_ZH.md)。本分支独立于 A/B，尚待研究者采纳，不改变任何既有运行授权。
- 两个真实数据探针已在网页连接器取得的实际 Git blob 上执行（JavaScript 函数运行，不是本机GPU或完整项目CI）。
- 本分支不包含任何原始研究对话、答案、私人回执、模型权重或身份信息。主方案包含聚合结果。此提交不宣称新系统已经可运行。

## 立即复跑（在实验服务器已有 Node.js 环境；不需要 GPU）
使用真实的四份固定文件，不能用同名其他版本替代。不要把原始文件复制到公开分支。

```bash
node project/scripts/rl1v3/journal_source_probe.cjs \
  "$EVOEMO_RAW" "$EVOEMO_SANITIZED" "$ESMEMEVAL_QA_IDENTITY" "$ANNOMI_FULL" \
  > "$PRIVATE_OUTPUT/source_probe.json"
node project/scripts/rl1v3/journal_annomi_behavior_probe.cjs "$ANNOMI_FULL" \
  > "$PRIVATE_OUTPUT/annomi_behavior_probe.json"
```

四个路径由 J00 资产清单和上游固定版本确定；脚本会检查 Git blob SHA1（不是普通文件 SHA1），文件不符即停止。不要覆盖既有输出。若缺 AnnoMI 文件，先从 https://github.com/uccollab/AnnoMI 获取与脚本匹配的 AnnoMI-full.csv，核对数据使用说明、版本、哈希并登记到本地资产表。不要为跑通脚本改变预期哈希。TIP35 原始方法来源：https://www.ncbi.nlm.nih.gov/books/NBK571071/ 及 Chapter3：https://www.ncbi.nlm.nih.gov/books/NBK571068/。AnnoMI 2023 扩展论文（https://doi.org/10.3390/fi15030110）Data Availability 将数据描述为 Public Domain；其视频是示范而非真实疗效记录。其他数据权限仍按 J00。
  
## 第二个真实探针：已观察行为的自动识别
使用 AnnoMI 支持者话语及专家 main_therapist_behaviour 标签，固定视频组划分，训练简单词/二元词多项式朴素贝叶斯（非 LLM、非临床模型）。训练5992话语/96组，测试834话语/23组，组交集0；多数类267/834=32.01%，macro-F1 0.1213；NB 629/834=75.42%，macro-F1 0.7024。other F1 .8653，question .7837，reflection .6831，therapist_input .4774（召回 .4157）。
这个真实开发结果说明专业标签能支持一个自动行为检测器的起点，但 advice/输入类漏检明显，不能直接做正式奖励。输入是已经生成的回复，不是当前用户前缀；任务是识别做了什么，不是判断应该做什么。没有生成G0e回复，没有证明资源有收益。两探针使用相同的开发暴露划分，不是两个独立确认实验。

## 第一轮不可再次停在清单
1. 协调者以主方案为唯一新增候选研究说明，将 J00 回执映射进去。无需重做J00。确认采纳和授权边界。
2. A 使用 #23 固定执行器准备原 A0 4次真实调用，按既有授权流程执行；并行获取资源、实际运行上述探针、完成可读 SOURCE_EXACT / RS 小候选及统一读口。
3. B 实际构造30个QA和24个RS开发任务清单，证据与答案隔离，完成最小程序checker及专业行为评价开发；与A生成首个受控请求包，不能仅交schema。
4. A/B 联合提交冻结实验manifest、实际输入合法性复验、首批G运行时预算和明确停止条件。获授权后立即执行M/RS试验。PP1/FC-MS保留原身份，与受控试验并行。
5. J04之后按主方案的直接提供→实际检索→联合四格→可学习空间→学习→独立评价推进。若收益为零，不允许不断换Judge或补抽有利结果；按归因层修正或收窄论文。

交付要求：实际运行命令、日志、输出计数、失败、来源/模型版本、下一步与完成/未完成状态。不能把 mock、待运行输入、测试通过或裁判未经校准的评分写成正式成果。
