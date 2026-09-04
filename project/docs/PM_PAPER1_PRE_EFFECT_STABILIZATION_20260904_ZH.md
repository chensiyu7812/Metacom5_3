# Paper-1：Pre-Effect Stabilization（2026-09-04）

状态：`ACTIVE / RESEARCHER-AUTHORIZED / PRE-OUTCOME`。

本修订只关闭正式 effect 前发现的两个构念漂移和两个机械复现问题。它不修改 Multi-View ontology、401 candidate pool、BGE/Top-k、packing、Threshold V4、本地 Generator 或官方评价，也不新增经验通过门。formal outcome=0、PM training=0，四把 outcome lock 保持 CLOSED。

## 1. Primary multi-head allocation

MP/ME/MS 的三个 L2 heads 分别预测“跨过本任务 material-benefit 标准”的概率。它们不预测收益幅度，独立校准后的 `p-threshold` 也不是跨 head 共享的效用单位。因此 primary policy 不再使用 `(p-threshold)/incremental-p95-latency` 排序。

Primary 只执行：

1. 每个 head 独立检查 mechanically eligible 与 threshold-positive；
2. 用调用前 lookup 估计完整 qualifying bundle；
3. 完整 bundle 低于适用预算时全部保留，按 canonical order 只负责渲染；
4. 完整 bundle 发生预算碰撞时，不臆造跨 head 优先级，全部 optional memory fail closed 到 R0+M0，并记录 collision。

更紧部署预算下的 subset/ratio 方法以后可以作为明确命名的 sensitivity，但不得冒充 Paper-1 primary 或 expected-utility learner。

## 2. “足够收益”与 equivalent

`equivalent` 的含义固定为：盲评老师看不出可辨别的净质量/适切性优势，因此额外资源没有达到 material benefit，训练目标为 0。只要一个合格 pairwise verdict 已明确给出 equivalent，微小方向性指标不得重新覆盖它。

- ESC：Overall 的一个 ordinal step 仍是离散 primary；Empathy、Information 和其余维度全部报告，但单维下降 1 分不再自动 veto。pairwise 与 Overall 反向为 uncertain，明确 equivalent 为 equivalent。
- QA：官方 0/1/2 semantic correctness 的一个 ordinal step仍可给方向；明确 pairwise equivalent 为 equivalent，反向为 uncertain。
- Summary：不凭空发明 Event F1 数值阈值。V2 中任意方向性 Event F1 必须获得同向 pairwise 确认且 LLM Score 不反向；pairwise equivalent 为 equivalent，无 pairwise 为 uncertain。
- DG local：方向性 Weighted Score 必须获得同向 pairwise correctness/appropriateness 确认；equivalent 为 equivalent，无 pairwise 为 uncertain。局部 label 仍不声称全局 sequential oracle。

这使当前 Paper-1 保持“预测 material benefit 的概率”，而不是退回“任何非零指标变化都算收益”。

## 3. 401 identity 与 Generator termination

401 identity audit 必须检查最终 session rows、802 success caches、attempt prompt hashes、accepted-unit compiler identity 和 promoted artifact 的字节哈希。全部统一时关闭问题，不重跑 session；该审计不判断 candidate 质量。

Generator termination audit 只读取 EOS/EOT 配置、finish reason、output tokens、task/arm 和故障字段，不读取回复质量。现有小样本只能判断实现是否明显错误；RS、更多 memory targets 与动态 DG 覆盖完成前不冻结最终 output caps。

## 4. 稳定后执行顺序

完成本修订、身份审计和 termination 初审后，不再优先扩展 latency/simulator contract。主线切回：candidate factuality QA → 96-presentation dual-human teacher reference → teacher identity/qualification → amount calibration → matched focal-head ON/OFF effects → four L2 PM heads → grouped OOF Threshold V4 → sealed audit → official confirmatory evaluation。

这里的 teacher reference 计数固定为：80 个基础语义 pair，加 16 个仅交换 A/B 的反序 presentation，共 96 个 blinded pair presentations；两名 primary rater 各自独立完成全部 96 个 presentation，因此 primary 数据共有 192 份 rater-pair judgement。第三人或 consensus adjudication 另计，不进入这 192 的 agreement 分母。该集合与 Natural-turn Appropriateness 的 96-slot proposal 是两个不同样本。

正式 DG 的本地官方 Mistral judgement 另采用预结果冻结的 arm-balanced schedule：同一 owner/scenario/turn/observation/judgement-kind 的六个系统请求相邻，并按固定 seed 做循环平衡；禁止先完整评分一个 arm 再评分另一个 arm。此设计只减少 arm 与 batch-context 的混淆，不保证单题确定，也不改变官方 temperature 省略、prompt、schema 或 metric。
