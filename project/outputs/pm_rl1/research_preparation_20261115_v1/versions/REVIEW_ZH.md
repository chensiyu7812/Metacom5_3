# PM-RL1 版本与资产复用审阅（2026-11-15）

本文件是离线准备，配套 `VERSION_REUSE_MANIFEST.json` 与可重复执行的 `build_version_manifest.py`。本次核对 39 个代码/协议/汇总文件的 SHA256，登记 10 个 Claude 回复池的文件哈希与行数。**没有完成新旧请求逐条连接；没有宣称找到多少条可直接复用的新实验标签。** 没有模型加载、生成、裁判调用、训练、付费或生产代码改动；未读取 test gold 或废弃 11/80 来源。

## 1. 必须分开的版本

| 版本 | 本次确认 | 不能混用之处 |
|---|---|---|
| 旧 Paper1 1,924 回复 | base Llama-3.1-8B，QA/Summary，静态 k=1–4 | 不是 P2/Gemma，不是自然支持；chat-template 身份也与 P2 不同 |
| P2 586 主回复＋53 对照 | epoch_3 LoRA 与同输入 base；586 中 train 336、dev 250；53 均 dev | P2 的弱目标拟合不证明质量提升；跨加载 6 组仅 2 组逐字重现，seed 不能替代实际 reply 哈希 |
| QA 86 与 typed 42 | 两协议 runtime 完全一致：`cf84d46e…`，Gemma-4-12B-it-707f0a3、BF16/SDPA、thinking=false；协议与输入不同 | 候选 G 未推广；QA 正确不等于自然帮助；typed 42 尚无质量标签 |
| Claude 分支 | 同名 Gemma 模型目录；另有 Llama 参照、ESC-Role 模拟对话、单轮回复等不同池 | 模型目录相同不足以证明模板/解码/运行相同；模拟五轮、期望数字分数和官方离散分数各自保留 |
| 原 70 计划 | 四个 GET 上限、候选 2048 资源 tokens、固定排名前缀 | 仅历史身份；不能描述当前新有序程序 |
| 当前 organized 程序 | STOP/RS/MP/MS/ME，已去除任意 top-k/4 GET 限制，剩余原生上下文边界 | 当前实际 locator 是词集合重合，不是 BGE；BGE 5139 维特征与 BGE 检索必须分开登记 |

`common_pool/summary.json` 的 `INPUTS_FROZEN_EXECUTOR_PENDING` 是输入准备时快照；完成状态应由 P2 `phase_closeout.json` 核对，不能用旧 pending 覆盖后来完成。

## 2. 可复用到什么程度

| 资产 | 当前可保留、复用 | 触发重生成/重评的变化 |
|---|---|---|
| 586＋53 | 完全同请求、来源、G/runtime、实际 reply 的缓存；符合原证据绑定的人评 | 更换 G、资源正文、取回结果、renderer、draw 后的新请求；改写 reply 后原偏好失效 |
| 1,924 | 原 QA/Summary 同任务同版本回复、旧官方评分基础设施 | 转成当前自然支持、Gemma 或新资源输入；不为完成新主线先耗资补齐全部旧评分 |
| 55 人评参照 | 36 pair、8 triplet、8 single q/m、3 supplement，按原证据和实际回复匹配 | 不是 55 独立受试者或统一偏好标签；新回复需新判断；略好/相当/不确定不擅自转精确 q/m |
| QA 86 | 已有外部事实增量与检索/执行诊断；同输入回复 | QA 结论不直接变自然支持 reward；新证据表达需重生成 |
| typed 42 | 已有七臂实际回复，可用于原输入的复查或人评 | 修复缺失指代、换工作视图、追加完整案例即新输入；已有 G 秒数不等于 E2E |
| Claude 各池 | 反例、实验覆盖、强泛化指导对照、原回复和原评分 | 先补分支身份、暴露分组、测量口径再考虑连接；不能直接并入当前训练集 |
| 本轮新资源样本 | 源会话、精确跨度、合法切点、原文索引可复用 | 完整 RS 案例和新记忆视图的实际 G 输入尚未产生，后续应统一版本生成 |

复用判断的最小闭合单位是：合法来源与切点 → 检索查询和实际有序资源 → 完整 messages → G 权重/adapter/模板/解码 → draw → **已记录实际 reply** → 原评价证据与量表。研究标签还须满足原分组/暴露和用途限制。精确回复复用不等于可把历史生成时间当成新方法延迟。

## 3. 最少新增模块的接入方式

1. 新增一个版本化资源视图编译器及 manifest。复用 `typed_resource_views.py` 和 `OrganizedItem`；MP/ME 携带源跨度、时间与状态，MS 保留完整父会话，扩读单独记账；RS 案例保留情境、动作、真实后续反馈、适用边界。不能以待答金标选择工作视图。
2. 在 `OrganizationCatalog.rank` 外接一个明确命名的检索适配器。选择 BGE 或词重合并冻结版本；统一 PPO、OneShot、NoText 的 locator。只用当前可见前缀与已取得内容更新 query，不能偷读未购买正文。
3. 在 `OrganizedRenderer` 接入新正文 schema。保留当前四类动作，先将方法卡/案例作为 RS 的两种资源类型，结构化证据/完整父文作为既有 memory 的资源视图；不要立刻重写动作空间和训练器。若要显式 EXPAND 或独立方法卡动作，应另立接口版本、重新核对基线和动作概率。
4. 复用 `human_reference_reuse.py`、`organized_feedback.py`、`organized_supervision.prepare_targets` / `comparison_union` 和 `OrganizedRun`。新增的关键工作是精确反馈连接与实测延迟接入；BC/PPO 优化器、缓存/恢复、NoText 对照都可保留。缺测保持 pending，不能填零。

## 4. 正式实验之前仍未冻结

- 主 G、完整提示和资源 renderer；目前不能把 Gemma 候选自动改称正式版本。
- 新 RS/记忆表示、检索方法/查询更新、动作域和 OneShot 搜索预算。
- 自然支持反馈的可辨认性、误用定义、相当/不确定处理；旧 55 参照只减少重复工作，不自动获得 reward 资格。
- 按 owner/source family 隔离的开发/最终评估用途，尤其 Claude 反复筛选过的情境暴露。
- 用户等待的完整路径与缓存策略、质量—等待操作点及秒系数。tokens 是诊断，G component seconds 是分段时间；旧延迟主张不能转成现在的 Tokkio p95。

已有真实 BC/PPO 成本负对照（3 seeds、384 轨迹）证明训练链可用；ON/OFF 实际回复相同是合法零质量差的特殊条件，不证明已学会正收益资源选择。下一批样本应先闭合“新资源 → 实际回复 → 可辨反馈 → 实测等待”，再送入现有训练器；无需另起一套 RL 框架。
