# ME 同栈核实——发现（同栈可信，2026-08-06）

状态：**同栈可信**——用的是真实`evoemo.build_evo_memory()`分块器（不是自己写regex扫原始对话）
和真实`v1_5_v5_2_atomic_memory.compile_atomic_reusable_outcome()`编译器（V5.2 locked composer
的`_me_clause`就是直接调用这个函数，见`v1_5_v5_2_locked_composer.py:79`——这不是只给诊断用的
函数，是生产环境Step2渲染ME候选时真实会跑的那一行）。这次核查取代本会话早前一个已撤回的错误
结论（"EvoEmo全库只有4条ME候选"），那个数字是绕开`build_evo_memory()`、自己用regex扫原始对话
得到的，方法本身错了。

复现：`scripts/v1_5/47_me_verification_same_stack_v1_5.py`，产出：
`outputs/pm_v1_5_v5_3_me_verification_v1/me_compiler_coverage_by_user.jsonl`（gitignore，
未进git）。

## 结论先说：ME的问题不是"候选太少"，是"候选很多，但严格编译器几乎全部拒绝"

对138状态资格赛面板里的全部12个唯一用户，跑`build_evo_memory()`拿到真实ME候选池，再对每条候选
的字面文本跑`compile_atomic_reusable_outcome()`：

| 指标 | 数值 |
|---|---:|
| 12个用户的ME候选总数（真实分块器产出，不是原始对话轮数） | 747 |
| 通过严格原子结果编译器的候选数 | 3 |
| 整体通过率 | **0.40%** |
| 至少有1条候选能通过编译的用户数 | 2/12 |

逐用户明细（候选池普遍在37-100条之间，不是"候选稀缺"）：

| 用户 | 候选池大小 | 可编译数 |
|---|---:|---:|
| p7 | 59 | 0 |
| p8 | 100 | 0 |
| p9 | 58 | **2** |
| p10 | 56 | 0 |
| p11 | 69 | 0 |
| p12 | 61 | **1** |
| p13 | 71 | 0 |
| p14 | 51 | 0 |
| p15 | 67 | 0 |
| p16 | 78 | 0 |
| p17 | 40 | 0 |
| p18 | 37 | 0 |

## 为什么是这个结果：编译器的匹配面比EvoEmo对话的写作风格窄得多

`compile_atomic_reusable_outcome()`要求同一句话或紧邻的下一句里，同时出现：(1) 一个第一人称
局部动作短语（`I/we tried/used/chose/decided to/asked/...`），(2) 一个明确的结果短语
（`helped/worked/eased/reduced/improved/felt better/did not help/backfired`等），且总长度
限制在5-70个词、360字符以内（`_bounded_local_span`）。这是V5.2故意收紧的设计（模块docstring：
"V5.1把整个seeker episode当成可复用事件，只要关键词出现在chunk里任何地方；V5.2故意只接受同一
句或紧邻下一句里的一个局部第一人称动作+结果"），目的是杜绝V5.1那种"把整段对话当证据、结果被
稀释成含糊的场景描述"的问题。

但EvoEmo的对话风格是合成、情绪化的第一人称自述（"I've been trying to..."、"It's been
challenging..."），极少出现"我做了X，然后帮助了/没帮助"这种紧凑的动作-结果句式；更常见的是把
动作和情绪状态分散在几句话里，或者只描述情绪状态本身，没有一个可执行的"我尝试了什么"。这不是
编译器写错了正则——是EvoEmo这批数据的写作风格跟V5.2编译器设计时假设的"用户会紧凑地说一句
可复用的过去经验"这个前提不匹配。

## 结论：ME需要的是数据/表示层面的修正，不是检索排序或embedding模型选型

- **这不是MS/MP那种"排序打分函数选型"问题**：候选池里99.6%的条目根本到不了排序这一步——它们
  在Step2 locked composer尝试渲染`_me_clause`时就会因为`compile_atomic_reusable_outcome()`
  返回`None`而直接抛`ValueError("ME literal span is not an atomic reusable outcome")`
  （`v1_5_v5_2_locked_composer.py:81`），排序打分函数（无论lexical还是BGE）打分打得再准，也
  没有material可选。
  换句话说，即使ME的检索排序完美无缺，V5.2的locked composer在几乎所有真实EvoEmo场景下都会因为
  ME候选编译失败而无法渲染ME内容——这解释了ME在早期V5.2实验里几乎不出现的现象，根源在编译器
  覆盖率，不在排序。
- 这精确回答了"ME搞清楚问题本身"：**根因是表示/编译覆盖率（representation/compiler coverage）**，
  不是候选稀缺（候选池37-100条，很充足），也不是排序质量。
- 可能的修正方向（留给后续决策，本次核查不推荐具体方案）：放宽编译器接受的句式范围（风险：
  重新引入V5.1"稀释证据"的问题，这正是V5.2想避免的）；或者针对EvoEmo这类合成数据的写作风格
  设计一个不同的、同样严格但匹配面更宽的编译规则；或者承认EvoEmo数据本身不适合评测ME这条通路，
  需要额外收集/构造更符合"紧凑动作-结果句式"的数据。这些都需要跟V5.2设计者（避免重新引入V5.1
  问题的顾虑）对齐后再动编译器代码，本次核查的范围只到"确认问题所在"为止。
