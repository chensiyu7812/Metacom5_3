# B 独立工程审阅协议（CPU）

本记录由独立 B 审阅代理编写，接受本轮研究者的跨线验证指令。它是 AI 工程复核，不是人评、专业语义批准、原 WS-B owner 的正式采纳，也不修改 H0 / EXECUTION_STATE。

基线为 integration `320a33d1d871199d171f998300ce926b341ca1a8`。范围限于新 as-of sidecar、真实历史切点、字段可见性及请求身份；不加载模型、不运行 GPU / Judge / 训练或付费 API。

## 预先固定的审查项

1. 独立解析固定 A1 Registry 的 `sources.jsonl`，不使用 A 的候选筛选函数计算期望集。对至少三名 owner、每人多个真实会话切点，逐条比较完成状态、source / known / ready 时间、dataset / owner / family、原始 transcript SHA。
2. 追加 cutoff 后会话不能改变早期 source frontier、snapshot 内容或身份。不得把含未来会话的 Registry 全局版本直接混入历史 snapshot 哈希。
3. 来源回填和事实生效时间不等于获知时间；延迟 ready 必须在相应历史切点拒绝。同会话即使离线文件完整，也不可写回当前长期记忆。
4. batch 与逐会话 streaming 对同一 cutoff 产生同一哈希；重复 append 幂等，冲突重复 ID 必须报错。旧记录不得就地修改。
5. 支持者建议不可被标为用户已完成；第三方主体不可默认为本人。更正 / 矛盾边必须由当时可用、同 owner 的精确原文支持；未审边不改变有效状态。
6. C0 0.2.0 及32份 Schema 保持原字节。内部 `rejected` 阶段如需通过旧 ReadingView，须显式映射 `unknown` 并在阅读正文保留拒绝事实，不扩展公共 enum。
7. PrefixAsOf、SourceFrontier、writer、snapshot、source/family/cutoff 是 executor 私有绑定。PM 仅接收现有 Observation；Generator 仅接收 VisiblePrefix / 已购买 ReadingView 的白名单正文。NeedCard、gold、评分、候选 ID、source hash、future、未读正文均不可进入可见输入。
8. 新 writer / snapshot / 资源正文 / renderer / G / decode / Step-2 等身份变化必须产生新请求身份。旧 TerminalKey 只能作为私有映射来源，不能重命名，也不能继承旧 response / reward。

## 证据边界

精确跨度一致仅证明原话曾出现；不证明归纳、当前有效性、方法适用性或自然支持增益。缺人工审查保留 `unreviewed`；模型抽取与生成保持 pending。资源或语义未就绪时，控制端必须 fail closed，而不是补空资源或零奖励。

最终收据须记录实际测试数、失败与修复、被检查文件 SHA、真实 cut 列表及独立计算结果。任何测试通过均不表示 A4/A5/A6/A7 或研究级资源收益完成。

## 固定真实切点与独立参考

在实现 API 可用之前，已独立解析 A1 `sources.jsonl`，为 A 选定的 p1 / p15 / p18 构建全部 65 个真实历史切点（分别31 / 21 / 13）。切点固定为每个 rank≥1 会话的首个 seeker 后接 supporter 的位置，未按资源效果或生成结果筛选。最后一个会话之后不存在下一真实 prefix，不伪造一个切点。

`independent_oracle.py` 不导入 A materializer / filter，直接核对 owner、dataset、complete、source rank、reported / ready rank、日期，并记录每个期望来源的 family 和 transcript SHA。`RAW_FRONTIER_ORACLE.json` 是其固定输出；这是历史可知来源参考，不是语义金标。

另以共享 family 的真实反例做串库检查：p13 的 esc1198（rank14）与 p18 的 esc1198（rank7）具有同一 transcript SHA，但 owner 不同，不能因此合并个人记忆或跨 owner 读取。
