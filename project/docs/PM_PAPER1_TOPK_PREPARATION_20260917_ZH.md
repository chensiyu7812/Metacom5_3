# top-k 校准准备（2026-09-17）

已从当前 BGE 排序和既有分组生成候选清单，尚未生成校准 outcome 或选定 `k*`。准备脚本为 `scripts/paper1/69_summarize_natural_end_and_calibration_inventory.py`；本地输出在 `outputs/paper1_calibration/preparation_20260917_v1/`。

后续已完成具体抽样与请求物化：[85 QA＋63 Summary 校准包](PM_PAPER1_STATIC_AMOUNT_CALIBRATION_PACKAGE_20260917_ZH.md)。下文的 20,176 条保留为全量盘点；实际首轮准备为 1,924 条，尚未生成或付费评分。

## 已物化的范围

- QA 1,427 个目标、Summary 125 个目标；每个目标 MP/ME/MS 三头，各有 `k=1/2/3/4` 的精确 ranked prefix，共 18,624 行；每目标共用一个 true-OFF，完整静态 grid 名义上共 20,176 条生成配置。
- 每行绑定 target、task、head、k、realized k、candidate IDs/content hashes、outer fold 和 exact-evidence component。不含 gold、回复或评分；candidate token 数不冒充含 envelope 的实际请求长度。
- 保留 1,586 targets / 477 components / 5 folds、seed=0；每个 held-out fold 的 k 只由 fold 外校准 outcome 决定。开发时看过材料不触发整批剔除 97 个关联目标。
- RS 仍为 52 calibration / 121 confirmatory cards。52 张全覆盖的初始五点 grid 是 260 条轨迹；实际轮数和 scorer 调用须按官方 harness 展开。
- DG 的 34 个场景仍在每轮当前 seeker utterance 出现后检索；不能把静态 query 代替真实多轮校准。

## 接下来如何执行

先选预算可承受、按 task / component 覆盖的 calibration 子集，并保存选入概率和分组。上面的全量候选清单是工作量盘点，不代表现在要全部运行。QA/Summary 可缓存相同 OFF 和相同完整请求；各 held-out fold 的选择步骤只使用其训练侧合适的校准行。

所有比较组采用同一自然结束 Generator 版本。先精确 render messages 和资源 envelope，核对总上下文容量，再展开官方评分器／DG simulator 的实际调用数并计费。生成长短随模型自然停止变化，费用和延迟按实测或明确的技术最坏边界计算，不用短输出截断制造低成本。当前余额仍是 $48.49275709，尚未形成新收费执行包。

选择规则沿用既定方案：先找官方 primary 均值最高的 k，将 `mean(k) >= mean(best) - SE(best)` 纳入 one-SE 集合，再依次选平均 Generator 输入 tokens 较少、k 较小、canonical 顺序较前者。SE 使用既定 cluster unit。只有最佳均值位于 k=4 且 k=3 不在其 one-SE 集合，才一次性扩展到 6/8。

各任务的量标定主指标分别为 ESC Overall、QA official semantic correctness、Summary Event F1、DG Weighted Score，并保留原有 guards 与分项报告。裁判研究关注“能否确认实质差异”；量标定关注“哪种资源量具有足够的官方质量”，两项工作可以并行准备。

资源输入容量与输出长度是两个问题。完整 raw-session MS 在 k=4 的已知精确资源块最大为 QA 3,639、Summary 3,101 tokens，不能继续套旧 384-token memory cap。下一轮容量应容纳所选精确资源包，不能通过截掉已分配记忆改变处理。
