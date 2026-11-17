# C0 0.2.0 候选接口：提交 WS-B 复审，尚未冻结

本轮不修改 B 业务模块、不合并 PR、不修改 H0/全局 EXECUTION_STATE。
审阅输入固定于 WS-B `b664ea07b032740486741ce95ce5447a11f7aadf`；原审阅和原验收测试保存在 inputs，B0 原模块/4,119 行普查的完整 SHA 在 tests/fixtures/rl1v3/wsb/PROVENANCE.json。

## 必改项及迁移

| 项目 | 实际实现及调用约束 |
|---|---|
| R1 | `TerminalKey.domain_id` 必填。finite_head_v1 将动作与对应 record 组一起按 RS/MP/ME/MS 排序；每头最多一次。adaptive_v1 保留实际顺序。`ExecutionTrace` 独立保存实际动作、record 组、ReadingView，`verify_key` 检查其规范化结果。固定每头交付包时，65 条路径对应恰好 16 个键；不能把不同 record 包假装成同一终点。 |
| R2 | `acquired` 为逐动作的非空 tuple[tuple[str,...],...]，长度等于非 STOP 动作数。拒绝空组、错组数及重复 record。OFF 为 STOP + 空组。旧平铺 acquired_record_ids 在 0.2.0 中拒绝。 |
| R3 | 动作和 mask 共用参数化 `EXPAND_MS(j)`。ReadingView 有 view、expandable、expanded_from_ordinal（均为公开阅读序号，无私有来源 ID）。只允许展开已经读过、允许展开、未展开的 SUM；交付 RAW。finite 不允许展开；adaptive 总读数≤5，同头 GET≤2。 |
| R4 | `Checklist` 绑定 prefix_id/NeedCard SHA/items/total_weight/writer_identity，校验唯一项及精确十进制权重和。B 在实验启动时对每个 prefix 调用 `io.bind_checklist(registry, checklist, needcard)`，所有终点使用 `load_checklist` 取得同一对象；同一目录下不同表不能覆盖，发布采用原子硬链接。改变检查表必须建立新实验登记目录。TerminalRecord 内嵌表及 SHA，核验前缀/全部判项覆盖/GSC 固定分母。feedback_id 单独绑定裁判模型、提示、解析器及聚合 manifest；不进入回复键。 |
| R5 | ItemVerdict 分别保存 J1/J2 quote 与 SourceSpan。None 表示未跑，uncertain 表示已跑不确定。分歧时 final 必须 uncertain，例外须显式 HumanAdjudication（人、原记录 URI/SHA、回复 SHA、判定、理由）；回复 SHA 交叉检查。`verify_evidence(response,prefix,sources)` 校验引文、原始字符跨度、owner/dataset/family、当前可见切点或完整严格过去。机械检查不代表语义或人评资格。 |
| R6 | hard_factual/hard_safety 分别支持 None/uncertain/pass/fail。未测硬约束、未完成判项或未验证证据不能进入 research_qualified/human_confirmed。未完成双判且无人裁决时 GSC 必须 (None,None)，不能写零。奖励由 B 实现，B 必须对 pending 返回未就绪而非数值奖励。 |

`TerminalKey.for_prefix(prefix, ...)` 绑定 owner、内容前缀 ID 和运行上下文 SHA；后者包含 cutoff/time/family 闭包但排除 fold/split/stratum。bank/index/renderer/step2/G/decode 均参与键哈希；跨用户、上下文及版本测试覆盖。生成侧必须按规范化头顺序渲染 finite 包；实际轨迹只影响执行回放/真实等待，不改变该回复缓存键。

终点表写入流程：验证 PrefixSpec 来源上下文 → 固定 NeedCard 和检查表 → 运行合法读取并保存 ExecutionTrace → TerminalKey.for_prefix → 请求/回复哈希 → 独立 feedback_id 的评分。每条 TerminalRecord 使用同一个 prefix 检查表；`verify_evidence` 成功后才允许设置 evidence_validation=verified，资格等级还须由 B 的资格证据决定，字段值不能代替真实验证。

## N1–N8 处置

- N1 采纳：Observation.history_sessions 独立表示历史完整会话数。
- N2 采纳文档修正：允许 ReadingView.reported_at.session_rank 表示合法报告时间；没有日期不合成日期。不引入第二种可能冲突的 sessions_ago 时间格式。
- N3 采纳：OutdatedFact(old_span,new_span) 成对、同 owner 且时间向前；NeedCard 增加 writer_identity/input_sha256/span_validation_status 与实际跨度校验方法。
- N4 优先采纳：PrefixSpec.create 使用 B0 内容身份协议，构造/解码时重算验证；4,119 行身份逐条兼容。ancestor_family_ids 是当前及全部严格过去会话的 family 并集；verify_source_context 校验完整历史、切点和闭包。from_legacy 明示 historical_legacy，只能回放历史，不允许 for_prefix 产生 V3 终点。family 过滤不得替代为文本或 split 检查。
- N5 优先采纳：count 是合法 owner/cutoff/ready/family 过滤后的、与 query 无关的候选池大小，所有 arm 一致；不是交付条数、top-k 或得分。
- N6 优先采纳：ReadResult 是 ReadSuccess/ReadFailure 的 status 判别联合；失败 reason 类型化、无 ordinal/reading/record_ids，不生成 G 输入；实际已耗 elapsed_ms 仍记录。成功必须非空、真实 tokens 计入输入并预留输出容量。RetrievalResult.delivery_record_ids/delivery_tokens 为执行器私有打包信息。真正 retrieve.read 实现属于冻结后的 A1b，当前只交付接口及拒绝/容量校验。
- N7 采纳 availability/count-only；分数元数据消融暂缓至 A5 并单独升级身份、核算预检索成本。当前 score 不进入 actor/critic/G。
- N8（PR 评论补充）采纳可推导接口：Observation.remaining_gets 属性由 domain 与已读数量得到，finite=4−读数，adaptive=5−读数（展开也计一次）。不重复序列化可相互矛盾的预算字段；持久化全部公开输入足以重建属性。

## 版本、Schema 与回放

契约统一升级 `pmrl1v3-contracts-0.2.0`，拒绝 0.1.0 wire 和缺少嵌套版本的输入。canonical JSON 字节规则仍为 `pmrl1v3-json-1`，B0 哈希不变。31 个 dataclass 和 ReadResult 共 32 个 Schema；Schema 检查结构，跨字段/来源约束必须使用 decode_contract/verify 方法。所有 dataclass frozen、嵌套 tuple 不可变。

旧 Schema 原样存于 project/schemas/rl1v3/v0.1.0；旧结果/日志/manifest 不覆盖。旧 C0/A0 使用其记录的旧 commit 执行，不能拿新代码静默解码或重新解释旧 manifest。没有自动把旧缓存或旧判分迁移为新身份。

本轮回放命令：

```bash
PYTHONPATH=project/src python project/scripts/rl1v3/c0_replay_contracts.py \
 --input project/outputs/pm_rl1/v3/C0_revision/fixtures.json \
 --out /tmp/c0-v02-replayed.json
PYTHONPATH=project/src python project/scripts/rl1v3/c0_export_schemas.py --check
PYTHONPATH=project/src pytest project/tests/test_rl1v3_*.py
```

B 的原验收文件以输入证据保留。运行版只适配 0.2.0 必填参数/组结构、移除 xfail/skip，并改用精确固定的 B0 代码和压缩普查（CI 不依赖 ignored outputs）。原有 7 项保证和 6 项要求全部保留；另新增行为测试，不能以字段存在替代完整执行检查。

冻结条件仍是 B 复审通过、CI 通过和集成负责人统一合入；本文件不构成单方面冻结。
