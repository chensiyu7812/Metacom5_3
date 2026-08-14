# PM V1.5 记忆实现、联合调用与 MS same-stack feasibility

日期：2026-08-10  
状态：零 API 架构修复与诊断完成；生成、评审和付费执行仍未授权

## 结论

用户指出的问题是成立的，而且不是一个孤立标注错误：**从“召回到一个 session / profile / event”到“让 generator 在当前回复中正确使用它”之间，原链路缺了一个独立的资源实现与联合编排层。**

但是，修好这一层不会自动让 MP、MS、ME 三个 head 都学会。它解决的是三者共享的 Step2 调用故障；各 head 仍有各自的候选、标签和独立样本限制。

当前最准确的状态是：

- RS 已正式学出条件性路由：grouped OOF balanced accuracy `0.742`，不是 always-on/off 塌缩。
- MS V2 已把“session gold × turn candidate”错位改成 session 对齐，OOF balanced accuracy `0.5993`，比随机有信号，但按事先冻结的 `0.60` 门差 `0.00067`，正式状态仍是 fixed-off。
- 新的零 API realization 诊断证明：383 个 actual Rank-1 session 都能从当前可见 seeker 文本选择一个非寒暄、source-exact 的 prior seeker span；无 abstention、无当前文本逐字冗余。
- 这只证明“可以形成干净的 generator 输入”，尚未证明该 span 真能改善回复。下一项决定性证据仍是同栈 always-off / fixed-high / frozen learned-MS 的真实回复比较。

## “Thanks 被标 ON”到底说明了什么

旧逻辑把 EvoEmo 的作者关系作用在 session 上，却把某一句 seeker turn 当成执行候选。于是只要该句所在 session 是当前 session 的祖先，句子本身即使只是 `Thanks, I really appreciate it` 也会继承正标签。

这同时污染两个层面：

1. Step1 学到“祖先 session 中任意一句都值得开”；
2. Step2 可能把一条无功能的句子硬塞给 generator，然后把失败误归给 PM 或记忆无用。

V2 已把检索候选改成完整 strictly-past raw seeker session，解决第一个单位错位。此次新增的 realization 层再从 actual Rank-1 session 中，用当前可见 seeker 文本选择一个 exact prior seeker turn，解决“整段 session 不能直接喂给 generator”的问题。

零 API 实测结果：

- actual Rank-1 rows：383；
- 65/383 个 raw session 含至少一个低信息 turn；
- 用 seeker-only BGE turn selection 时，低信息 Top-1：0/383；
- exact span 成功：383/383；
- selector abstention：0/383；
- 与当前可见文本逐字冗余：0/383；
- 选中 span 长度中位数 18 words；raw session 中位数 208 words；中位压缩比 8.7%。

因此，旧 `Thanks` 故障不是“BGE 什么都理解不了”，而是**标签单位和执行单位未分开**。V2 + exact-span realization 已在当前 383 rows 上机械消除这个具体故障。

## 新的完整调用链

```text
catalog
  → actual Rank-1（检索对象）
  → PM requested 4 bits（是否请求组件）
  → component realization（选择可用的 exact 内容/行为约束）
  → joint feasibility projection（处理缺席、冗余、冲突和竞争）
  → one typed response plan（一个回复计划）
  → generator uptake
  → deterministic guard / fallback
  → Quality / Risk / Function / Cost 独立测量
```

这条链把过去混在一起的四个问题分开：召回错、PM 开关错、资源实现错、generator 使用错。

## 四组件不再是四段并列素材

| 组件 | 在回复中的逻辑角色 | 正确实现 | 不再允许 |
|---|---|---|---|
| MP | `SILENT_RESPONSE_MODIFIER` | 改变格式、负担、节奏或实际建议约束 | 为证明调用而念出 profile；事实存在就算做功 |
| MS | `TENTATIVE_CONTINUITY_BRIDGE` | 用一个 source-exact prior span 建立谨慎连续性，并允许用户纠正 | 把过去升级成现在；整段 session 强制吸收；只提“以前说过” |
| ME | `DECLINABLE_PAST_OPTION` | 把 exact action + result 当作一个可拒绝选项 | 把一次结果写成规律、因果或保证 |
| RS | `PRIMARY_SUPPORT_ACT` | 完成一个原子支持动作；它拥有回复的主要 discourse act | 与 ME 另起第二个任务或附加多轮负担 |

16 个 requested action 仍保留，没有改成少于 16 个动作。新增的是 `requested → feasible → realized` 三段账本：如果某组件没有安全 exact realization，或 MS/ME 的关系是未知、重复、冲突，就由所有 policy 共用的确定性 projector 抑制该组件，并记录原因。

## 为什么过去多次修 prompt 仍会循环失败

反复失败不是一个单点，而是同一组根因在不同阶段换了表现形式：

1. **候选单位错位**：session-level 关系被下放到任意 turn；现已修。
2. **相关性冒充增量价值**：同主题不等于对当前回复有用。旧 D3 MS 40 对有 38 ties，就是这个问题。
3. **检索对象冒充执行证据**：整段 session、profile 字段或 event 不能原样作为 generator 指令；此次新增 realization 层。
4. **所有 ON 资源被当成并列事实并强制使用**：V5.3 虽修掉 V5.2 的末尾拼接，但 prompt 仍写“every evidence item ... use all”。这会制造 MP 引用、MS/ME 重复和多组件负载。
5. **没有联合逻辑**：MP 是 modifier、MS 是 continuity、ME 是 option、RS 是 act；旧执行器没有优先级、冲突或抑制语义。
6. **标签不是完整真值**：EvoEmo `influenced_by` 是 positive-only author lineage。没有边不等于“不该用”，有边也只证明 session 关系，不证明某一 exact span 当前有增量。
7. **Function 测量边界不稳**：最近双人校准的 aggregate Function 为 A `15/24`、B `9/24`；MP 为 `2/6` 对 `0/6`，ME 为 `6/6` 对 `4/6`，RS 为 `3/6` 对 `1/6`，而 MS 两人均为 `4/6`。主要分歧是“做功”定义和组件边界，不是所有回复完全不可判断。
8. **独立 group 很少且用户异质**：MS 只有 17 个 connected owner groups，部分 fold 很好、两个 fold 较差。增加 state rows 不能等价增加独立用户。

## 修好调用逻辑后，MP / MS / ME 会不会都解决

不会自动全部解决，但会显著改善三者共同的下游执行，并让剩余失败可以正确归责。

| 组件 | 调用/组合修复能解决 | 仍未解决 | 当前判断 |
|---|---|---|---|
| MS | 无用 turn、整段强塞、过去/现在混淆、与 RS/ME 竞争 | author graph 非完整 suitability gold；17 groups；真实回复净收益未知 | 最有希望先形成“RS + 一个记忆头”的系统证据 |
| MP | 不再要求 profile citation；作为 silent modifier 使用 | 何时 preference 被触发、profile 是否真正改变建议仍缺稳定 gold | 需要 response-transformation 标签，不能用 profile presence 代替 |
| ME | action/result 作为可拒绝 option；与 MS/RS 的功能分工清楚 | typed action-result 覆盖稀疏；跨事件 transfer 条件难 | 执行侧可修，学习侧仍受覆盖限制 |
| RS | 明确为 primary act，避免多动作 | 与 ME 的负担冲突仍需联合测试 | 正式路由已通过，可作为稳定骨架 |

换句话说：**这次修复不会伪造更强的四头分类信号；它会阻止一个本来选对的资源在 Step2 被用坏，也会阻止 Step2 的错继续回写成 PM 的 OFF gold。**

## same-stack feasibility 怎么做才有意义

固定样本仍是 17 个 connected owner groups，每组按 protocol hash 选 4 states，共 68 states。三个逻辑 policy：

1. always-off：`M0+R0`；
2. fixed-high MS：有 actual Rank-1 就请求 `MS+R0`；
3. frozen cross-fitted learned MS：使用已经消费、不可修改的 OOF decision。

68 states 中 frozen learned policy 为 MS ON 37、OFF 31。因为 learned arm 在每个 state 必然与 always-off 或 fixed-high 完全相同，执行时按 `state × feasible action × seed` 去重：

- 逻辑 policy observations：204；
- 一次 seed 的真实物理 generator calls：136，而不是 204；
- 每个 policy alias 保留，统计仍按三个 policy 报告；
- 三个 policy 使用完全相同的 current state、actual Rank-1、span selector、joint projector、generator、seed、guard 和测量。

主要问题不是再设置一个武断“及格线”，而是最终比较：

- learned 相比 always-off 是否没有方向性质量损失，并在 predicted-ON strata 出现真实 functional use / positive quality signal；
- learned 相比 fixed-high 是否明显减少注入上下文；
- learned 是否不增加字面 material risk；
- 所有 requested → received → used → functional 漏斗能否完整定责。

这次结果不会把 MS 的 routing BA `0.5993` 改写成 PASS。它回答另一个更接近论文主张的问题：**这个冻结 policy 放入真实同栈后，是否比 always-off 和 fixed-high 更有用。**

## 哪些是可解决工程问题，哪些是研究局限

可在当前研究中解决：

- Rank-1 与 exact evidence 分层；
- MP/MS/ME/RS 角色、顺序、冲突、抑制和 burden 预算；
- 同一 projector/adapter 应用于所有 baseline；
- requested / feasible / received / used / functional 五段责任账本；
- generator 不再看到整段 raw session，也不再被命令无条件 use all；
- function 只测组件贡献，risk 只测字面风险事件，quality 与 cost 分开。

无法靠当前 18 个纵向用户彻底消除：

- open-world 语义适用性没有完整人工 gold；
- 17 个 connected groups 带来的宽不确定区间；
- 自然语言中任意复杂隐含意图、讽刺、多实体因果和长期状态推理；
- 单次 generator 输出的随机性。

这些限制不要求假设“语义问题不存在”。正确做法是定义有限可测语义边界：owner/time、exact source、当前 seeker query、非寒暄、非逐字冗余、tentative continuity、declinable analogy、explicit boundary；超出边界时系统应投影 OFF 或报告 OOD，而不是冒充理解。

## 接下来的单一路线

1. 冻结新的 realization/composition contract、实现树和 tests；禁止再直接使用旧 `use all evidence` prompt。
2. 把 exact-span MS 编译进新的 typed response plan，完成零 API prompt/guard fixtures；这一步不改 PM。
3. 建立 68-state / 136-call content-addressed phase manifest；确认 baseline aliases、费用上限与 API identity 后才开放生成。
4. 一次完成 responses；先机器审 requested/feasible/received/guard，再进行 blind human quality/function/risk。
5. 结果只决定 frozen MS 的系统 feasibility，不准回改 label、feature、threshold、sample 或 prompt。
6. 若 MS 有方向性系统收益，则第一篇论文以“RS 正式 learnability + frozen MS directionally usable + 同栈 baseline 改善”为最小成功主张；MP/ME 继续作为次要/局限结果，而不是拖住整篇论文。

## 机器权威文件

- Realization/composition candidate：`data/pm_v1_5_contracts/paper1_memory_realization_and_joint_composition_candidate_v1.json`
- Same-stack feasibility candidate：`data/pm_v1_5_contracts/paper1_borderline_ms_same_stack_feasibility_candidate_v1.json`
- Zero-API diagnostic：`outputs/pm_v1_5_paper1_ms_memory_realization_diagnostic_20260810/report.json`
- 实现：`src/metacom_pm/v1_5_memory_realization_v2.py`
- Role-aware response plan：`src/metacom_pm/v1_5_memory_response_plan_v2.py`
- 测试：`tests/test_v1_5_memory_realization_v2.py`
- Response-plan 测试：`tests/test_v1_5_memory_response_plan_v2.py`
