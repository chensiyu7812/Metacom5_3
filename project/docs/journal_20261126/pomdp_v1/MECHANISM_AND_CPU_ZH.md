# SEARCH / EXPAND / STOP：有限机制原型与真实 CPU 结果

本轮完成 16 个真实来源任务、5 个透明程序的 **80 条 CPU 路径**，没有启动 Generator、LLM 控制器、GPU、API 或训练。80 条路径产生 58 个不同的终局输入；所有终值仍为 `pending / reward=null`。这证明读口和受限转移可运行，不证明序贯方法、RL 或长期支持有效。

16 个任务来自 8 个 source-derived 情境的事实/自然支持变体，使用既有开发缓存中最多 3 个连通来源家族；这是公开构造人物的来源材料与新构造任务，不是 16 名真实受试者或独立未见样本。同一情境的目标变体及多条策略路径不能增加独立样本数。

## 与原方案的关系

| 层次 | 已明确的范围 | 不能据此声称 |
|---|---|---|
| 长期情感支持方向 | 利用跨会话个人知识形成合适回复；更长期使用与协同是研究方向 | 已有真实用户心理转移、长期疗效或校准心理 belief |
| 早期 V1.5 / V2.1 | 固定生成器前的四资源开关、即时 quality/risk/cost 路由 | 原有四 bit 方法已经实现 POMDP / RL |
| 09-28 原始 PM-RL1 | 当前轮最多 4 次 GET，同头可重复；固定 BGE 排序与 query；至多 70 个计数终点；STOP 一次生成 | 后续用户模拟、跨轮回报、读后改 query、心理状态网络 |
| 11月 V3.1 Phase-1 / 实际 FiniteHead | 每头至多一次、静态 query、16 subset，确定性 GET 与终点表 | 读后改变检索目标、任意重复检索 |
| V3.1 Phase-2 计划 | adaptive query、每头最多 2 单元、EXPAND_MS、总 GET≤5、有序程序 OneShot | 文档已列出的模块已经实际实现或已有收益 |
| 本次独立 CPU 原型 | `SEARCH(query)`、`EXPAND(observed_handle)`、`STOP`；最多 4 次获取，已读词可用于后续 query | Phase-2 全部完成、MP/ME 可用、联合 RS、已学习策略或真正长期心理模型 |

依据：[09-28 原始方案 §0、§5–6、§11–12](../../PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md)、[V3.1 §6.4–6.10](../../PM_RL1_SOLUTION_PLAN_V3_20261116_ZH.md)、[期刊主方案 §3、§6](../../journal_20261125/MASTER_PLAN_ZH.md)、[V1.5](../../PM_V1_5_FINAL_RESEARCH_PLAN_ZH.md)、[V2.1](../../PM_V2_REDESIGN_PLAN_ZH.md)。更早的[失败与限制复盘 §13](../../PM_V1_FAILURE_LIMITATION_POSTMORTEM_ZH.md)也明确区分资源路由与 POMDP belief。这里是在核对可见文件的操作定义，不否定研究者更早的长期陪伴愿景；长期愿景不能替代当前实现和效果证据。

## 实际转移与权限

复用既有 `load_development_cache → As-of Ledger → materialize → SnapshotPrefixPort`，仅从隔离的开发缓存读取，保留原 fold 与来源家族。16 个任务的完整合法池分别有 11–26 个历史会话；没有使用评价侧 source locator 缩小候选池。真实 PrefixSpec 只绑定 owner、时间和来源边界，策略看到的是另行冻结的当前任务。

SEARCH 复用既有 Time-Lexical 排序：词面重合、最近报告顺序、record ID 决胜；返回前两个会话中与 query 词面重合最多的**完整原始 turn**，同分取最早 turn。它是精确 RAW-SPAN，不是摘要或 MP/ME 断言。EXPAND 只接受该 episode 实际返回过的 opaque hit handle，并交付整个父会话。每次来源再次检查 owner、strict-past 和合法池身份；MP、ME、RS 全部 masked。Hybrid 沿用既有 RRF 接口并有 score coverage 回归测试，本轮没有运行 BGE 编码或将词面结果称为 Hybrid 实测。

后续 query 的规范词必须来自当前可见任务或实际已交付文本；这是一条可检查的词面权限规则，允许重组，禁止使用隐藏来源词或评价答案，但不保证语义相关。NoText 不接收正文、实体、已读向量、私有分数或 source IDs，query 词表始终只限初始任务。它可以读取 observed handle、是否展开和已付 token 等非文本结果。任意未观察 handle、读前使用隐藏词、未来/错 owner 来源、STOP 后操作都会被拒绝。

共同限制为 4 次获取、累计实际交付 4,096 tokens、G 上下文 16,384、保留输出 320；单次 query 至多 256 words。预算拒绝后只能 STOP，不重新检索更小条目。拒绝的 CPU 开销另存，不把未交付内容给策略。重复 SEARCH / EXPAND 合法但再次收取访问与交付 token；不会退还已读 span。当前 action mask 不预取正文、分数或成功读取结果。

现 C0 与 renderer 每头只允许一个 ReadingView，因此本原型用一个 MS-RAW 块承载逐项标有报告时间和范围的已读源片段及父文；没有更改 C0 或旧 renderer。父文展开后仍保留先前 span，存在冗余成本。完全相同的最终输入可在固定 G、decode、renderer 身份下复用生成；轨迹 hash、query 参数、已观察 handle、访问次数和实际费用始终单列，不能压成一个 subset。

内部 state 保存合法静态来源池、已读内容、handle、预算和路径。公开的 operational evidence ledger 只记录已观察项及未知终值，不拟合心理状态，也没有称其为校准 posterior。这里的部分观测对象是未读取资源的内容，不是臆造的用户心理变量。

## 实测结果

| CPU 程序 | 路径 | 成功获取总数 | 累计交付 tokens | 终局输入 tokens 合计 | 路径 CPU 秒 |
|---|---:|---:|---:|---:|---:|
| STOP | 16 | 0 | 0 | 1,832 | 0.147 |
| FixedTopK（k=2） | 16 | 48 | 25,418 | 32,388 | 0.961 |
| 透明预承诺程序 OneShot | 16 | 64 | 28,512 | 35,116 | 1.041 |
| SequentialRule | 16 | 64 | 26,803 | 32,168 | 1.047 |
| SequentialNoText | 16 | 48 | 25,418 | 32,388 | 0.761 |

另有共同合法池/Ledger/端口准备 **12.946 秒**，所有策略包括 STOP 均使用该准备；不能把 STOP 全成本写成 0。上表是一次 CPU 实测、无进程冷启动/模型加载/Generator 等待，不是部署延迟估计；不同运行顺序与缓存也影响其差异。累计交付与终局输入是两个口径：重复读取仍付费，G 规范内容只精确去重。

SequentialRule 在 16 题改变第二次 query，6 题出现新父会话；透明 OneShot 初态程序在 12 题出现新父会话。Seq 与 Fixed 的终局输入有 11/16 不同。新命中不等于必要证据，更不等于正确回复；不能用这些数宣布 Seq 更强。大小写词代理也会选到包装词等噪声，不进行根据结果的修词追分。

FixedTopK 与当前 NoText 的 16/16 输入一致：该透明 NoText 退化为固定两父会话程序，不能当成训练过的消融或独立方法效益证据。这里 FixedTopK 是共同 SEARCH/EXPAND 域内的 Top2，不冒充上一条 SMV 的整会话 Top4 或最强检索基线。

源复验实际通过 320 个交付单元：完整 source turn 精确匹配、完整 parent 未截断；80 条 query provenance 与状态链通过。原型最初有一个所有格分词边界 bug：大小写代理从完整词提取根词，validator 正确拒绝。保留 cpu-v1 和失败日志，仅加“候选词本身属于已读词表”的修复，cpu-v2 全部完成；没有改变任务、source、预算或基于覆盖率挑选规则。独立源覆盖检查由另一条工作线完成，覆盖不作为任务成功。

## 唯一有限后续提案

在检索结果之前按 source 条件冻结 4 情境×事实/自然支持两目标，共 8 题：当前已足够、计划/执行未知、真实报告更新、分散事实各一个。其余 8 题只保留 CPU 边界诊断，不因结果更换入选题。

未来六臂 v2 为 STOP、FixedTop4 macro、**同一 LLM 初态一次性完整计划 OneShot**、普通 LLM ToolAgent、SequentialRule、SequentialNoText。另一次无 G 压力对照证明 16/16 Top4 均符合共同 token cap；它是 1 检索＋4 父读取，不冒称旧 4 primitive 同域，详见[公平性补充](FIXED_TOP4_FAIRNESS_ZH.md)。透明 CPU OneShot 不替代强 LLM 基线。LLM OneShot 只看初态，承诺至多 4 次 SEARCH/EXPAND；后续 EXPAND 用早先 search/rank 的符号引用绑定真实 observed handle，不能看结果改计划。ToolAgent 每次仅看实际公开 observation，至多 4 次控制调用。双方每任务控制输出上限均为 768 tokens（OneShot 1×768，Agent ≤4×192），所有控制输入、输出、等待和加载单独计费。

最多 **48 次终局 G + 8 次 OneShot 控制 + 32 次 Agent 控制 = 88 次**，精确缓存前上限。v2 已生成 32 个确定程序终局 payload，其中 30 unique，输入合计 61,626 tokens、最大 3,906；另外两个 LLM 臂的动态输入尚未知，不能假称已有全部静态 request hash。只在实际逐步动作后绑定它们。旧 v1 提案保留。

终局保持原 Gemma-4-12B-it `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`、原 G0e renderer/decode/max_new_tokens=320。v2 建议每来源情境的 fact/support 两目标完整六臂为一作业，最多 4 作业/4 loads，各 1,200 秒、总限 4,800 秒、0 warmup、0 retry，只限原 GPU `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`。每包最多 22 calls，按既有实测下取 10 output tokens/s 估算，全部输出上限 6,912 tokens 对应 691.2 秒，加 100 秒准备为 791.2 秒；prefill、控制往返与慢请求仍有不确定性，不是完成保证。

**本轮提案 `authorized=false, execution_ready=false`。** 动态控制—终局守卫 runner 与独立 admission 尚未完成；现交付具体初始控制请求、严格动作/计划 parser、预算对象及确定臂 payload，不能直接用旧 SMV/J06/SC 授权启动。没有为了验证接口再申请一批新 GPU 调用。控制格式/协议失败是技术失败，不填成任务质量 0；成功调用、格式正确和命中目标来源都不是 reward 资格。

## 文件与复跑

公共实现：`journal/pomdp_memory.py`、`pomdp_memory_prepare.py`、`pomdp_memory_proposal.py`，脚本 `journal_prepare_pomdp_memory.py`、`journal_report_pomdp_memory.py`。旧 FiniteHead、SMV、SC、G/C0 均未修改。

19 个 synthetic CPU 测试覆盖预算与 STOP、错 owner/未来、未读 query、跨 episode handle、完整动作白名单、NoText、重复费用与同内容不同轨迹、Hybrid 接口、controller parser、初态 OneShot 来源引用。实际 CPU 路径与源复验单列，synthetic 测试不冒充真实 G 输出。

```bash
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
project/tests/test_rl1v3_journal_pomdp_memory.py
```

完整私有复跑命令与可读 80 路 trace 留在 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-pomdp-20261126/engineering`。公开只提供计数、成本、实现与文件 SHA，不发布问题、RAW、gold 或私有评阅。
