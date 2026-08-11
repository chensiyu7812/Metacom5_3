# Paper 1 首次真实可学习性结果与 MS 单位对齐修复

日期：2026-08-10

## 已经得到的真实结果

`PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V1` 完成了一次结果前冻结的 grouped OOF：

- RS 通过：balanced accuracy `0.7417`，recall `0.8069`，specificity `0.6764`，Brier 胜 prevalence；
- MS 未通过：balanced accuracy `0.5960`，recall `0.5457`，specificity `0.6463`；
- ME 明确未通过；MP 预先固定 OFF；
- 因而 Paper 1 的 `RS + 至少一个 memory head` 主门尚未通过。

RS 是目前第一个稳定的真实可学习 head。MS 的 OOF ROC AUC 为 `0.6541`，说明存在方向性信号，
但不能把接近 `.60` 写成 PASS，也不能通过降低阈值或门槛追分。

## MS 的根本问题不是再换一个 encoder

V1 的 MS gold 来自 EvoEmo 作者整理的 `event_experience.influenced_by`，它描述的是
`source session -> current session` 的事件关系；但 V1 的 actual Rank-1 候选是 source session 中的
某一条 seeker turn。由此形成：

> session-level gold × turn-level resource

只要所选 turn 来自祖先 session，V1 就标正；该 turn 本身是否承载被链接的事件并没有作者标注。
实际抽查已经出现当前 turn 只是打招呼、actual Rank-1 是 “Thanks, I really appreciate it”，但由于
它所在 session 是祖先而被标为正例。这样的标签即使被更强模型学会，也会鼓励无用或误导性的
记忆注入。

这不是阈值问题，也不是 BGE-M3 本身的失败。V1 已经把 BGE-M3 current-turn cosine 作为 MS
检索和模型特征；继续轮换 encoder 会重复 V5.2 的已知失败。

## 唯一允许的结构修复

V2 只修正监督单位，不修改作者 gold：

1. 每个已完成 prior session 形成一个 MS resource；内容只由该 session 的 seeker 原文依次组成；
2. 禁止读取或复制 EvoEmo 的 summary、observation、event text、QA answer/evidence；
3. 每个 current session 只取一个运行时合法 checkpoint：累计可见 seeker 原文首次达到 50 words
   的当前 seeker turn；在此之前 MS hard OFF，表示当前目标证据不足；
4. actual Rank-1 在严格过去的 session resources 中，用冻结 BGE-M3 对完整可见 current prefix 排序；
5. gold 仍然只是：actual Rank-1 的 source session 是否属于 current session 的作者标注祖先集合；
6. 每 session 只有一个学习单位；outer split 仍按 connected owner，p13/p18 仍绑定；
7. 模型只用四个低容量标量：BGE score、top1-top2 margin、memory age、词项 Jaccard；不再用
   3000 维 TF-IDF 把 17 个用户簇伪装成高容量文本训练；
8. `.60/.55/.55`、Brier、ON/OFF coverage 和 `0.5` 阈值全部保持不变。

这属于 label/resource unit alignment 的方法版本修复，不是看到结果后重写 gold、改门槛或补救样本。
V1 的 OOF 结果永久保留为失败证据，不覆盖、不重跑。

## 停止条件

V2 在 fit 前先做零 API capacity/audit。若正负标签不足、少于 12 个有正例的独立 owner group、
runtime/evaluator 隔离失败或 source fidelity 失败，则不训练。若通过，只允许一次 frozen grouped OOF。
V2 若仍未通过，MS 固定 OFF，Paper 1 主 PM 判失败；禁止 V3 阈值、encoder、标签或小包循环。

## V2 最终结果与更深一层根因

V2 的一次 final grouped OOF 已完成：pooled BA `0.59933`、recall `0.63309`、specificity
`0.56557`、ROC AUC `0.63348`，Brier `0.22084` 胜 prevalence `0.23121`，ON/OFF 为
`50.65%/49.35%`。等权 owner-macro BA 为 `0.60572`，但预冻结机械门使用 pooled BA，差
`0.00067`，因此正式状态仍是 `FAIL_FIXED_OFF`，不能改成 PASS。owner-cluster bootstrap 95% 区间
为 `[0.5277, 0.6625]`，说明 17 个 connected owner groups 的不确定性很宽。

结果后只读定责发现，剩余瓶颈是 author graph 的构念边界：`influenced_by` 是作者记录的正向因果
链接，并不是一张“所有适合调用的记忆 / 所有不适合调用的记忆”穷尽表。未链接不能自动解释为
不相关。383 个有候选 checkpoint 中：

- actual Rank-1 命中作者祖先 session：139；
- current session 有作者祖先，但 Rank-1 选中别的 session：103（retrieval miss）；
- current session 没有任何作者祖先：141（open-world unlabeled 被 V2 当作 negative）。

假阳性抽查中，有些 actual candidate 与 current state 在语义上确实相关，只是作者图没有该边；
假阴性中也有明显相关且作者链接正确的例子。也就是说，V2 已修复资源单位，却证明公共图本身只能
提供 positive causal anchors，不能单独充当穷尽 suitability gold。这解释了为什么模型有 AUC/宏平均
信号，却在跨用户折上不稳定。

V2 到此关闭，不再建立 V3 训练循环。后续若要继续使用当前模型，只能作为冻结的
`BORDERLINE_DIRECTIONAL_CANDIDATE` 做结果不回写训练的 same-stack system feasibility；正式论文仍需
把 V2 路由门记录为未通过。若 feasibility 显示相对 baselines 的真实回复质量、风险、功能和成本有
意义，才能据最终系统表现重新决定主张层级；若无意义则直接结束，不再重做标签。
