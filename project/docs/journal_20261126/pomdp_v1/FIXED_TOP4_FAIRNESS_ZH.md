# FixedTop4 整会话 CPU 压力对照与比较边界

补充的唯一一次压力对照已完成：**16/16 题的完整 Top4 会话都能进入共同 4,096 交付-token cap**，无须截断或跳过更高排名。共交付 64 个完整父会话，最大交付 3,334 tokens；实际 G 输入最大 3,977、总计 55,113 tokens。没有启动 G；原 80 条路径、任务、来源和 Seq 规则保持不变。

这直接说明原 FixedTop2 并非容量上限迫出的强静态基线。Top4 复用同一初始 query、完整合法池、Time-Lexical 排序、原 tokenizer/G renderer；没有读取评价侧 refs/gold 来选会话。私有 TOP4_READS 与实际 TOP4_REQUESTS 已保存。首次公开汇总因整数 JSON key 报错，16 次真实读取及 payload 已完整保存；只从这些文件恢复汇总，没有重新检索、改规则或增加模型运行，原构建脚本保留归档。

| 条件 | 完整父会话读取 | G 输入总 tokens | 操作口径 |
|---|---:|---:|---|
| 原 FixedTop2 | 32 | 32,388 | 每题 SEARCH + 2 EXPAND，共 3 primitive |
| 原 SeqRule | 32 | 32,168 | 每题最多 4 primitive，另交付检索 snippets |
| 新 FixedTop4 macro | 64 | 55,113 | 每题 1 检索 + 4 完整父读取，共 5 操作，无 snippets |

因此 Top4 **不是**旧 4-access 动作域内的一次免费 GET，也不是严格 action-matched 对照。相同 token/context 上限并不等于相同操作域。它提供的是更有竞争力的实践静态参照；读取数、检索 CPU、完整输入与生成费用均需保留，不能只计一个 macro call。

建议后续六臂中的 fixed 采用该 Top4 macro，明确其操作差异；“读后序贯是否有价值”的严格比较主要依靠 **同一 LLM、同一 primitive 域、同一 token/access cap 的初态 OneShot 与逐步 ToolAgent**。OneShot 预承诺后不能读内容改计划，ToolAgent 的每次控制调用全计。若研究要求六臂完全同动作域，就必须先另立允许四命中/五 primitive 的共同域，再让所有方法共享它；本轮没有静默扩大 Seq、重跑到正结果或实现该新域。

未来提案 v2 保留原 8 个 source-only 选题、六臂、最多 88 次总调用，改为 **每个来源情境的 fact/support 两目标成组**：4 作业、每作业最多 12 终局 + 2 OneShot + 8 Agent 控制＝22 次物理调用（精确复用前）；共 4 loads、每包 1,200 秒、总硬限 4,800 秒、0 warmup/0 retry。按 10 output tokens/s，每包输出上界 6,912 tokens 约 691.2 秒，加 100 秒准备为 791.2 秒；prefill、控制往返与慢请求仍有不确定性，不保证全部完成。

已具体准备的 32 个确定臂 payload 中有 30 unique，输入 61,626 tokens、最大 3,906。LLM 动态 payload 未知部分仍需运行时逐步绑定。`authorized=false, execution_ready=false`；22-call 分包不能套用旧 20-call checker。动态 runner/admission 尚未实现，旧 v1 与全部历史产物保留。本补充不是 GPU 运行批准，也不增加任务或 88-call 上限。

公开聚合：[TOP4_PRESSURE_PUBLIC.json](TOP4_PRESSURE_PUBLIC.json)、[BOUNDED_PROPOSAL_V2_PUBLIC.json](BOUNDED_PROPOSAL_V2_PUBLIC.json)。供证覆盖由独立源复验另报；完整来源供应仍不等于生成成功、支持效益或正式 reward。
