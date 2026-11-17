# B0 结果：合法前缀普查、owner/family 先行折分与曝光登记

- 证据等级：**engineering_only**（确定性 CPU 普查；计数是公开源数据的精确事实，表面线索不是需求标签）
- 模型/GPU/付费调用：0 / 否 / 0
- 输入、代码、输出哈希：见同目录 `manifest.json`；复现命令也在其中
- 代码：`project/src/metacom_pm/rl1v3/prefixes/{census,exposure}.py`，脚本 `project/scripts/rl1v3/B0_prefix_census.py`，测试 `project/tests/test_rl1v3_b0_prefixes.py`（23 项）

## 1. 做了什么

1. 读取已净化的 EvoEmo 运行时产物（不读原始评测 JSON），对每个 `chronological_rank ≥ 1` 的会话，把"seeker 话语紧接 supporter 回复"的每个位置登记为合法切点；前缀严格等于 `turns[:cut+1]`，历史严格限于同 owner、rank 小于当前会话的会话。
2. 每行分开 `visible`（只由当前前缀、严格过去会话及其时间戳计算）与 `eval_only`（会话总长、切点后轮数、来源类别、family、整会话哈希等依赖未来或谱系的信息）。只有 `visible` 未来可经 C0 Observation 进入策略。
3. 先按共享来源 family / 相同 transcript 合并 owner，再分折；前缀、训练条件、教师样本和终点都继承 owner 的折。
4. 机械扫描仓库已追踪产物，登记 owner/会话/前缀的历史曝光。

## 2. 真实覆盖（自然分布，每个合法切点权重 1）

| 项 | 数值 |
|---|---|
| owner / 会话 / rank≥1 会话 | 18 / 401 / 383 |
| 有合法切点的会话 | 383 |
| 合法切点（前缀）总数 | **4,119** |
| 其中当前会话是 ESConv 种子会话 | 702 |
| 其中当前会话是 EvoEmo 生成会话 | 3,417 |
| 每会话最多 2 个前缀时的容量 | 766 |
| 每会话切点数 p50（min–max） | 11（4–20） |
| 严格过去会话数 p50（p90） | 11（22） |
| 严格过去历史词数 p50（p90，max） | 4,794（9,260，14,283） |
| 与上次会话间隔天数 p50（p90） | 15（44） |
| cutoff_rank 分桶 1 / 2–4 / 5–9 / 10+ | 195 / 560 / 959 / 2,405 |

每个 owner 的切点数 131（p17）～359（p8）。

**表面线索（只描述末尾 seeker 文字的英文正则命中，不是需求率）**：回指 1.8%、时间标记 9.5%、求建议 0.8%、问号 7.1%、风险关键词 0%。按 owner 平衡后几乎相同。

**解释边界（2026-11-17 修正）**：这些比例只说明末尾话语里出现了多少特定词面。它们**不能**解释为真实的记忆或方法需求率，**也不能**作为"绝大多数对话不需要历史"的证据。原因有三：用户可能不用回指词就依赖过去的事实或失败建议；正则只看末尾 seeker 文本，没有读严格过去的历史；命中词面也不等于回复必须引用历史。真实需求层只能由 B1 依据严格过去来源和精确跨度建立 NeedCard 后估计，并且需要人工校准。本文件早先写过"与 11/05 结论方向一致：明确依赖历史的情境很少"，那句话过度解释，现已撤回。

**自然分布与训练抽样分开保存**：B0 只产生自然分布（`prefix_census.jsonl`、`census_summary.json`，每个合法切点权重 1），以后不会因为 B1 过采样而修改。B1 的训练抽样必须另存为独立文件（含 selection_reason、自然权重和 owner/family 折），所有主结果都另按本自然分布报告一次。

## 3. 折分（owner/family 先行）

| 折 | owner | 合法切点 |
|---|---|---|
| 1 | p6, p10, p11 | 679 |
| 2 | p13, p16, p18 | 654 |
| 3 | p2, p5, p17 | 589 |
| 4 | p3, p9, p15 | 715 |
| 5 | p1, p8, p12 | 910 |
| 6（固定，历史 test） | p4, p7, p14 | 572 |

- **发现的跨 owner 泄漏**：`esc1198`（ESConv 对话 1198）同时是 p13 的 rank 14 和 p18 的 rank 7 历史会话，transcript 完全相同。纯哈希分块会把两人分到不同折，所以按 family 合并后 first-fit 分配；因此 p15、p17、p18 的折与纯哈希分块不同（`folds.json` 同时保存了纯哈希方案和被移动的 owner）。所有单 owner 情形下该规则与纯哈希分块完全相同。
- **G1 owner 划分候选**（B10 manifest 最终核定）：G1 训练 = 历史 dev（p1/p15/p18）∪ 第 5 折的 family 闭包 = {p1, p8, p12, p13, p15, p18}，共 6 人；其余 12 人分 4 折，历史 test 为最后一折。p13 因与 p18 共享 esc1198 被闭包带入 G1 训练，恰好凑成 6 人。
- ESConv 族重叠：84 个 ESConv 对话是 EvoEmo 的种子会话（ESConv train 59 / validation 14 / test 11），与 `esconv_split_manifest_v1_5` 的 `excluded_for_evoemo_overlap` 集合完全一致。**WS-A 的 RS 资源库必须按 family 排除这 84 个**（RESOURCE_SPEC T24）。

## 4. 曝光登记（机械下界）

- 所有 owner 都来自公开 ES-MemEval，仓库也公开了派生产物：`unexposed_confirmation_eligible=false` 对 18 人全部成立。真正未曝光的确认需要新授权来源并在冻结前封存。
- 会话级：401 个会话全部出现在至少一个已追踪的历史目录中（共 61 个目录，多数是普查/诊断）。会话 id 出现在人评目录中的 owner：p3、p6、p9、p10、p11、p13、p16、p17。
- 前缀级（旧 rl1 `PrefixSpec.identity` 精确匹配）：172 个本次前缀曾出现在 human_review / training / judge_or_feedback 目录中；按类别分别为人评 42、训练 50、判官/反馈 171。**历史 test owner p4/p7/p14 各有 16 个前缀出现在判官/反馈目录中**（无人评、无训练），所以第 6 折只能说"未用于训练和人评"，不能说未曝光。
- 局限：只能识别会话 id 和旧 rl1 前缀身份；其他历史身份方案、未追踪的本地文件和对话记录没有覆盖，所以"未命中"不代表没见过。

## 5. 无泄漏测试与审计

- 全量审计（4,119 行）：每行都能从源数据重建前缀、哈希一致，切点为 seeker→supporter，历史全部严格过去，`visible` 可复现，prefix_id 无重复，结果为 0 失败。
- 单元测试包括：改写切点后内容和未来会话时 `visible` 和前缀哈希不变；前缀文本不含切点后内容；在 seeker→seeker、最后一轮或 supporter 轮切点会被拒绝；篡改哈希或 cutoff_rank 会失败关闭；family 跨越固定第 6 折或容量不足时失败关闭；rank 不连续时失败关闭；共享 transcript 会合并 owner；真实数据的折互斥、family 闭合、G1 划分闭合，两次构建逐字节一致。

## 6. 自然分布与训练过采样

普查只给出自然分布，不做任何重采样。每行带 `sample_key = sha256("pmrl1v3|sample|"+prefix_id)` 和 `natural_weight=1`。B1 可以按需求层过采样（history+both 50% / method 20% / none 30%，每会话最多 2 个）用于训练，但每个入选行必须记录 selection_reason 和自然权重；主评价另按自然分布报告，不能用训练混合比例代替。

## 7. 给集成负责人和 A 的事项

1. **CI**：本分支基线的 workflow 只运行 `tests/test_paper1_*.py tests/test_rl1_*.py`。A 的 C0 提交 `50c9ade0` 已加入 `tests/test_rl1v3_*.py`，合入 integration 后 B0 测试会被收集。push 触发分支仍不包含 `pmrl1-v3/**`，所以只有 PR 会触发 CI。
2. `rl1v3/__init__.py` 由 C0（A）创建；B0 没有创建它，`rl1v3` 目前按隐式命名空间包导入，避免 add/add 冲突。
3. 本模块暂用本地 canonical JSON（sorted keys、紧凑分隔、UTF-8、`allow_nan=False`）。C0 的 `io.py` 冻结后，B0 改用它并以新 protocol 版本重新生成身份，不静默沿用旧标签。
4. C0 的 `PrefixSpec` 需要能从普查行无损构造：`prefix_id, owner_id, session_id, cut_turn, cutoff_rank, timestamp, turns` 来自 `materialize_prefix()`；`fold` 来自 `assignment.fold`；`stratum` 由 B1 填，并且只属于评价侧。
