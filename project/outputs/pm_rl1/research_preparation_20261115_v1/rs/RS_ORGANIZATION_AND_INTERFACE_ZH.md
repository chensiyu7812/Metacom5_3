# RS 离线组织与共享检索接口草案

这是 2026-11-15 研究准备产物，不改变 Paper1 或 RL1 的生产接口/冻结协议。当前有 12 张可追溯候选完整案例、3 个有来源的方法草案，均尚未证明对 G 有增益。完整不等于优质，有来源不等于已通过日常情感支持适用性验证。

## 两层资源如何组织

**方法单元**保存可靠出处、原始适用领域、动作定义、出处支持的边界、待审的日常 ES 适用条件、已审核/未审核的案例链接。方法本体与 AI 对何时适用的猜测分字段；禁止把后者写成专家规则。`METHOD_UNITS_DRAFT.json` 的 3 个单元只是来源清楚的沟通行为草案，不是治疗手册，也不是已成立的 G 能力缺口。第三条许可式建议来自官方 PDF 的检索正文，正式使用前还需定位到 PDF 页码。

**案例单元**保留完整前情→连续 supporter 行动块→紧随其后的 seeker 反应，并指向完整原会话。原标签、原评分、语义审核注释分开。会话整体情绪变化、后续反应和当前行动不得混为单一因果效果；真实生活后续未观察即 unknown。方法与案例是多对多链接，只有审核后才建立链接；当前不依词面标签自动认领某方法。

独立设置审计层，放来源原文、内容 hash、原卡身份、审核者、版本与判断依据。不要把这些信息全塞给 G。资源正文的运行时视图要明确是其他人的案例；可以观察对方怎样回应，不能把对方生活事实当作当前用户记忆，更不能复制成人类亲身经历。

## 外部资源的价值要求

方法可能已在 G 参数中出现，公开案例也不能保证未在预训练中出现。因此不宣称新颖性或“G 绝不知道”。操作化标准是：在固定 G、固定公开上下文及推理预算下，取得资源是否稳定提高回答质量/对约束的利用，并能抵偿检索、读取与 prompt 成本。外部观察证据、具体方法步骤与失败边界是候选增量；通用标签不是自动成立的增量。

## Query-first 与逐步披露

建议做离线 adapter 规范，待小试验通过后才实现正式接口：

```text
SearchRequest {
  query_text: 当前用户公开问题 + 已获取证据所支持的明确缺口,
  acquired_resource_ids, target_lineage_ids, lineage_complete,
  resource_type: RS | MP | ME | MS,
  retriever_version, top_k, budget
}
SearchResponse {
  candidate_handles, public_cost_metadata, availability,
  internal_rank_log  // 离线审计；不含当前 target 未来结果
}
GET(handle) -> acquired_evidence_with_provenance
STOP -> G(公开当前上下文, 已获得资源), only_one_reply
```

统一 query 构造规则、统一候选/索引版本、统一检索器、统一 top-k/cost 预算提供给固定基线和 PM；禁止为 PM 提供更好的检索器后把检索器差异记成策略学习收益。索引可以含资源正文供检索器计算，但 PM 未 GET 前不能偷看资源正文或标有未来收益的摘要。候选 handle/资源类型/客观大小成本等与正文的边界要预注册；若展示语义摘要，摘要也是读取内容，应在所有方法中一致提供并计入成本。

RS 可先以“一份方法说明 + 一个经过审核且匹配的案例”作为不可再分的取得单元，随后与只方法、只案例比较。不要为了制造多个 RL 动作而硬拆；只有单独取得确实有用且代价不同，才支持方法→补案例的自适应披露。完整上下文太长时先检验按源 turn 索引给出的自足窗口，并保持可回到完整来源；当前候选文件保存全文，不静默改变完整 MS 的定义。

MP 是长期相对稳定的人物背景，ME 是有时间/来源的事件及行为—反应经历，MS 是严格在当前决策之前的完整源会话。三者来自同一底层来源身份系统，可以互相定位与升级读取；它们不复制三套互不一致的“用户事实”。ME 的行为—反应经历只能说该用户曾如何反应；不能把一次经历变成永恒偏好。

## 防同源泄漏

每例有 `esconv_dialogue:*` 与规范化完整文本 hash 两类 family ID，旧 RS card 全部反查到原 dialogue/turn。任何 target 若源自该 dialogue，包括摘要、改写、EvoEmo 派生物，都需要把这些祖先 ID 纳入 `target_lineage_ids` 后再检索。`allowed_for_target()` 对相交/未知 lineage 均拒绝，机械检查已覆盖。当前这里只建立原始源和完全同文的身份，**并未声称完成全部衍生语料的别名闭包**；正式选 target 前必须完成那一步，不能只靠文本 hash 宣称没有污染。

## A/B 怎么用这批产物

1. 先根据来源真实性、事实可靠性、语境自足、方法定义与适用边界审核资源。`SEMANTIC_REVIEW_ZH.md` 逐卡列出发现的问题。审核不得看到当前 target 的结果后回填“适用规则”。可保留差例做失效对照，但不要给 G 无标识地当推荐范例。
2. 在独立开发 target 上冻结固定 query/共享检索/家族排除。此 12 张是 schema 和审核流程试片，不是足以估计泛化增益的正式 bank。必须报告入库率、检索不到比例、被排除比例、每一类失败。
3. 固定 G，先同 target 配对比较无 RS、旧 RS、方法草案经审核版、完整案例经审核版、两者组合；不能把过滤坏卡与提高质量的收益误算为 RL 收益。方法与案例不同 token 时既报自然成本，也用同一规则的预算敏感性对照；不靠塞无关 token 声称严格等价。
4. 增加同成本打乱/无关 RS 对照，区分证据作用、额外注意力与 prompt 格式效应。原 feedback 可供来源理解，是否暴露评分需冻结并做去评分敏感性检验，避免 G 因高分盲信案例。评分和远后续默认留审计层；即时反应可以作为异源案例观察正文。
5. 先确认资源存在可靠增量，再看共享自然检索能否找到，再训练 PM 的获取/停止。资源无增量时定位是冗余、质量差、情境不匹配、G 未使用还是成本过大；不能再用 PM RL 替资源制造价值。

## 外部来源目录

- ESConv：本地 `data/external/ESConv.json` 与既有 train manifest，本次只选 train 且不属于 manifest 标记的 EvoEmo overlap。上游：[官方仓库](https://github.com/thu-coai/Emotional-Support-Conversation)。仅保证原文与原标签可追溯，不赋予专家或疗效身份。
- [AnnoMI 官方仓库](https://github.com/uccollab/AnnoMI)：官方 README 已核查；包含 133 个 MI 示范会话及专家行为标签。high/low 是示范质量，不是临床疗效；full 版本含 annotator_id，同一 utterance 可有多标注记录，不能把它们当独立案例。下一轮可按原视频/会话 family 引入部分案例作为外部领域对照。本轮未下载/构造 AnnoMI 卡。
- [SAMHSA TIP35 Chapter 3](https://www.ncbi.nlm.nih.gov/books/NBK571068/) 与 [active-listening roadblocks 表](https://www.ncbi.nlm.nih.gov/books/NBK571068/table/ch3.t5/)：网页主路径一度触发浏览器检查，检索返回正文与表内容可核对上述两条短释义。原领域是物质使用障碍咨询；日常 ES 适用性、中文解释与 G 增益均待独立审核。本轮没有用其疗效结论为 ESConv 案例背书。

## 复算

```bash
python /home/tokkio/Metacom5_3/project/outputs/pm_rl1/research_preparation_20261115_v1/rs/build_rs_case_candidates.py
```

固定种子、固定策略配额、不同 train dialogue，无目标信息与反馈分数参与选样。为保证原有多样性使用了结构筛选（至少 6 个前序 turn、完整行动/反应且源后续仍有交互）；这限制了总体代表性。复算重建原文卡、来源副本、核对视图与机器检查，不覆盖此审核台账/方法草案。读取 aggregate JSON 时解析全文件，但仅遍历 train 行字段并输出 train 卡；未抽取、展示、分析或用 test/validation 会话选例。
