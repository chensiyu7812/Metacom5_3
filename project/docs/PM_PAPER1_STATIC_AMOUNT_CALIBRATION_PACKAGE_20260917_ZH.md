# QA／Summary 资源量校准执行准备（2026-09-17）

本轮已将全量盘点缩为具体首轮样本，并物化生成请求、分析映射和官方评分模板。**尚未生成新回复、调用评分 API 或选择 k***。A6000 当前运行其他项目任务，本轮仅使用 CPU 准备与核验。

## 样本与请求

从冻结的 1,427 个 QA、125 个 Summary 目标中，以 `任务 × owner × outer_fold` 分层。每个非空层先等概率抽一个 exact-evidence component，再等概率抽该组中的一个目标；seed=0 固定。每个目标的入选概率为 `1 / (层内组数 × 被选组内目标数)`，保存逆概率权重。抽样不读取回复、官方分数或收益标签。

| 项目 | QA | Summary | 合计 |
|---|---:|---:|---:|
| 入选目标 | 85 | 63 | 148 |
| 每目标生成条件 | 13 | 13 | — |
| Generator 请求／名义官方评分请求 | 1,105 | 819 | 1,924 |

样本覆盖 18 个 owner、5 个既有外层折。每目标 MP／ME／MS 各 k=1/2/3/4，另共用一个 true-OFF；其余可选资源关闭。OFF 在三个 head 的分析中引用同一输出，不重复生成或计费。分析映射共 2,220 行，不是 2,220 个独立生成样本。

抽样保证了结构覆盖，不保证足以识别很小的资源量差异。保留加权估计、owner 聚类不确定性及每折覆盖。开发时看过的关联目标不自动整批排除。

## 已核验的生成与评分条件

- Generator 保留冻结的 Llama-3.1-8B、官方 QA／Summary system prompt 和 Step2 资源呈现；使用 EOS/EOT 自然结束，不继承旧 256-token 截断。
- 所有输入已完整渲染并用冻结 tokenizer 计数：最小 260、中位 589、最大 3,497 tokens。候选按既有 BGE 顺序精确取前缀，不裁剪完整 MS 会话。
- 目标内 13 个条件形成相邻 microblock；目标顺序与块内条件顺序按固定 seed 打散。实际正式延迟仍需按其专门设计测量。
- QA／Summary 评分模板直接从固定版本官方源码抽取。与原方法在拦截模型调用后的实际 messages 逐字比较，两任务各两个含特殊字符样例均一致。
- 评分模型拟固定为 `gpt-4o-2024-11-20`，官方别名为 `gpt-4o`；temperature 和输出上限沿用上游省略形式。上游 QA 使用首个 `[0-2]` 数字；Summary 使用 JSON 修复后的事件计数及官方公式。模型身份已写入准备配置，尚未通过实际付费请求确认可用性。
- 当前只有生成请求完整确定；评分请求还缺待生成的 prediction。离线绑定脚本会核对回复身份、自然结束与完整输入，再生成真实 API payload 和预留额。没有回复时输出 0 条可发评分请求，不能拿占位文本去评分。

## 资源量选择规则

对每个 `task × head × held-out fold`，只使用该折之外的校准行。分别以 QA 官方 semantic correctness、Summary 官方 Event F1 为主指标；不做跨任务总分。

先在同一批完整配对目标上计算各 k 的逆概率加权均值，使用 owner-cluster bootstrap（seed=0、2,000 次）估计标准误。均值不低于 `best_mean − SE(best)` 的 k 进入 one-SE 集合，再选择平均 Generator 输入 tokens 较少、k 较小的点。k=0 保留为真实候选，不强制某个记忆头有收益。

缺失评分或未自然结束的目标在该 head 的所有 k 中一致排除，并报告缺失覆盖，不能给缺失补零分。实现产生的是 primary 指标建议，不直接冻结 k*；Summary 的官方语义／忠实度分项及异常计数仍需一并审阅。仅当 k=4 均值最佳且 k=3 不在 one-SE 集合时，按既定规则考虑一次 k=6/8 扩展；扩展不在本批 1,924 条请求内。

## 费用与下一步

本地生成 API 费用为 $0。GPT‑4o 标准输入／输出价格核对为每百万 tokens $2.50／$10.00，不预支缓存折扣。[官方价格](https://developers.openai.com/api/docs/pricing)

| 预算情景 | 假设平均回答 tokens | QA 裁判输出 | Summary 裁判输出 | 全批首试估计 |
|---|---:|---:|---:|---:|
| 短 | 256 | 8 | 512 | $7.845727 |
| 中 | 512 | 8 | 1,024 | $13.270368 |
| 长 | 1,024 | 16 | 2,048 | $24.208047 |

以上长度仅为计费情景，**不是输出上限，也不是实测报价**。完整回答与评分输出尚未生成，不能承诺某个价格一定完成全批。拟议阶段上限为含重试 $15，在既有 Paper-1 $50 总额内；当前总余额 $48.49275709。本轮没有获得或消耗这笔新评分额度。

实际执行时，每次请求以真实完整输入和模型原生最大输出空间预留费用，结算后再发下一次；整批达到阶段上限前停在下一条请求，不截短内容挤进预算。中断和失败保留；达到费用上限后不能将偏向已完成前缀的结果冒充完整校准。

接下来先在 A6000 可用后完成免费本地生成，再形成真实评分 payload 和费用预留清单；新付费运行仍按具体批次确认。本批仅准备 QA／Summary，RS 的 52 张校准卡和 DG 的逐轮真实 seeker 校准仍需后续完整执行，不能因此宣称四个 head 的 k* 已冻结。

## 文件与验证

- 准备：[77_prepare_static_amount_calibration.py](../scripts/paper1/77_prepare_static_amount_calibration.py)
- 评分请求离线绑定：[78_materialize_static_official_scoring.py](../scripts/paper1/78_materialize_static_official_scoring.py)
- 抽样与 one-SE：[amount_calibration.py](../src/metacom_pm/paper1/amount_calibration.py)
- [可公开的准备汇总](reviews/20260917/static_amount_calibration_preparation.json)

完整本地包：`project/outputs/paper1_calibration/static_sample_20260917_v1/`，含 148 行选题、1,924 条生成请求、2,220 行分析映射、1,924 个待补 prediction 的评分槽位、官方模板与来源哈希。相关 20 项测试通过；官方 prompt 字节对照通过；未生成、未计费、未训练。
