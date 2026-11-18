# PM-RL1 V3.2 集成协调只读审查（2026-11-18，日本时间）

本报告以临时 integration coordinator 身份提交。审查者此前开发了 WS-A 的 #10/#12/#13/#15；这些 PR 的自测及 A 派生的“B 角色 AI 工程审阅”均不作为跨线验收。这里引用的 WS-B 跨线证据来自原 WS-B 工作线的 #11/#16 和其在 #15 的评论，仍按其实际覆盖范围解释。

结论：七个 PR 的最终 HEAD CI 均成功，新增文件之间无文本冲突，但当前不能直接按编号一次性合入。建议分为“文档候选入库”“旧 G0e 工程链集成”“as-of 联合集成”三段；#11/#12 有正式绑定/base 阻塞，#15 有未闭合的 WS-B 验收，#16 有本轮复现的五类接口问题。所有合并均等待研究者确认具体队列，本轮未执行。

科学前提：四资源尚未证明支持质量增益。P2 的资格表、盲评协议、CPU 原型和 CI 只属于工程准备，P2 资源价值资格保持未完成；不得据此晋级 research_qualified、bank-v1、正式奖励或 A4/A5/A6/A7。研究者此前的 V3.2 CPU 推进授权有效；正式 H0 采纳与 EXECUTION_STATE 登记仍未由本轮代办。

1. **核验对象和真实状态**

最新远端 integration 核验为 `320a33d1d871199d171f998300ce926b341ca1a8`。以下是 GitHub 实际 HEAD，不取 PR 描述中的历史阶段 HEAD。GitHub 的 mergeable=true 只表示各 PR 相对当前 base 可合，不表示科学资格或联合接口已通过。

| PR | HEAD SHA | 当前 base（及 SHA） | 状态 |
|---|---|---|---|
| [#10](https://github.com/chensiyu7812/Metacom5_3/pull/10) G0e | `73fdb12f29b6970a268eeda704d73e1bd35b1c3e` | `pmrl1-v3/integration` / `320a33d1d871199d171f998300ce926b341ca1a8` | Open、Ready、未合并 |
| [#11](https://github.com/chensiyu7812/Metacom5_3/pull/11) WS-B S3 | `dd33e1311eea56a9312e99c7f237e928ee09fe12` | `pmrl1-v3/integration` / `320a33d1d871199d171f998300ce926b341ca1a8` | Open、Draft、未合并 |
| [#12](https://github.com/chensiyu7812/Metacom5_3/pull/12) G0e 补充 | `8ba20d21da4bdcbb552946241563bd41dbe46c6c` | `pmrl1-v3/ws-a-g0e-cpu` / `73fdb12f29b6970a268eeda704d73e1bd35b1c3e` | Open、Draft、未合并 |
| [#13](https://github.com/chensiyu7812/Metacom5_3/pull/13) 四资源审查 | `ea2f5bde04caba4590b26c80a572d66caa4a2d08` | `pmrl1-v3/integration` / `320a33d1d871199d171f998300ce926b341ca1a8` | Open、Ready、未合并 |
| [#14](https://github.com/chensiyu7812/Metacom5_3/pull/14) V3.2 方案 | `f26e7cf8e2c4a728a0d36078700ea676b47223ef` | `pmrl1-v3/integration` / `320a33d1d871199d171f998300ce926b341ca1a8` | Open、Draft、未合并 |
| [#15](https://github.com/chensiyu7812/Metacom5_3/pull/15) as-of CPU | `b63635f3621f3a5d252099efcd58ae2d1958dce2` | `pmrl1-v3/integration` / `320a33d1d871199d171f998300ce926b341ca1a8` | Open、Ready、未合并 |
| [#16](https://github.com/chensiyu7812/Metacom5_3/pull/16) WS-B V3.2 | `a9cf0cca0fecd044a5a4e2a4066355a9a8123dc5` | `pmrl1-v3/ws-b-s3` / `dd33e1311eea56a9312e99c7f237e928ee09fe12` | Open、Draft、未合并 |

所有 PR 均没有 GitHub `APPROVED` review。#10/#13/#15 的 Copilot COMMENTED 只是“额度不足，未能审阅”，不能计为审查通过。跨线工作线收据与 GitHub approve 状态分别记录，不能相互冒充。

| PR | 最终 HEAD CI | V3 passed（均零 skip/xfail） | 公共 CPU passed |
|---|---|---:|---:|
| #10 | [44202885285 success](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44202885285) | 490 | 2,255 |
| #11 | [44254141953 success](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44254141953) | 566 | 2,331 |
| #12 | [44213269571 success](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44213269571) | 513 | 2,278 |
| #13 | [44254295904 success](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44254295904) | 476 | 2,241 |
| #14 | [44295714382 success](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44295714382) | 466 | 2,231 |
| #15 | [44301809117 success](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44301809117) | 580 | 2,345 |
| #16 | [44305002847 success](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44305002847) | 603 | 2,368 |

七次公共 CPU CI 均另有 63 skipped、1 GPU deselected：历史 engine/relation 输入缺失 32、engine/task 输入缺失 28、sentence_transformers 缺失 1、冻结 Llama tokenizer 缺失 1、rg 缺失 1。逐 job 步骤和原始日志已核对，包括 integration-base/outcome-lock success；跳过不算覆盖。原始证据见 `GITHUB_SNAPSHOT.json`、`PR_STATUS_TABLE.json`、`ci-pr10.log` 至 `ci-pr16.log`。

2. **依赖、文本冲突和兼容边界**

Git 祖先关系中只有 #10→#12、#11→#16 两条堆叠依赖。按各 PR 自己的 base 计算，增量文件数依次为 61、80、67、12、3、241、73，共 537，全部是新增且两两无路径重叠。基于 integration 的只读 union tree 为 `aefeff6cfa5d9c57461762cf062f713efe31f2fa`；它只是审查用文件树，没有 merge commit、分支推进或正式 integration 验收。

- #10→#11 是正式执行依赖：B 要在 #10 真正合入后同步 integration，重新生成 G0e 绑定附录。#11 当前的临时演练不能替代该步骤。
- #12 必须等 #10 合入后 retarget 到 integration。不得按现在的 base 把 #12 合入 #10 工作分支。建议 #11 正式验收后再处理 #12，使最新 A/B 版本一起复核。
- #13 的只读审查可独立入库；其证据引用 #12 固定提交/材料，不代表必须先合 #12。复跑须能读取这些固定 Git 对象。
- #14 是方案/下一轮指令，可以作为文档候选先入库；这不登记 H0，也不启用模型任务。文档中“候选”的旧表述不能撤销研究者后来明确给出的 CPU 授权。
- #15 不引入 #10/#12 的业务代码，历史复核脚本读取 #12/#13 固定 Git 对象。其 typed renderer 是不可执行提案，不是已经接通的新 G0e 请求端口。
- #16 的增量依赖 #11；其 B→A 适配器和资格证据引用 #15。B 可从未合入的 #15 固定 SHA 做独立审阅，因此不存在“必须先合 #16 才能审 #15”的循环依赖。
- #15 的 `compile/asof.py` 与 #16 的 `asof/binding.py` 是不同层，不是可互换实现。两者入库不会自动产生一个有 snapshot 约束、真实读取端口和原生分词的完整研究环境。
- C0 contracts、32 份公共 Schema、全局 EXECUTION_STATE 与 integration 字节相同。#10 另增 `schemas/rl1v3_g0e/ModelInput.schema.json`，它是独立模型 payload schema，不是 C0 改版。

3. **本轮复现的合入前问题**

下面均在精确 #15/#16 代码的 union tree 上验证，未修复生产代码。复现脚本为 `reproduce_interface_findings.py`，结果为 `INTERFACE_COUNTEREXAMPLES.json`。fixture 只用于机械反例，不是人工语义核准或真实模型结果。

| 编号 / 优先级 | 问题与复现 | 影响和建议验收 |
|---|---|---|
| R1 / 高 / #16 | B frontier 将 registry `source_id` 纳入身份；旧 source_id 哈希包含整个 SourceSession，其中 `raw_sha256` 是全来源文件 SHA。仅改该文件 SHA、保持每个历史 transcript 不变，p1/p15/p18 的 r5 **3/3 binding 与复合终点键改变**，变更前后 `validate()` 都通过。 | 删除显式 registry hash 仍未消除间接的全语料依赖。B 应使用经 A/B 同意的会话局部身份，将旧 source_id 仅作审计映射；未来追加/全文件 hash 变化下，完整 binding 和 terminal cache key 都要独立重验。该规则供各 tier 共用；本反例使用 legacy binding 控制其他变量，不声称验证了研究资格。 |
| R2 / 高 / #16 | `BoundEpisode.__init__` 只核六个环境版本字段及 prefix_id/context；owner 改错、cutoff 改 0、frontier 清空，`AB.validate` 报 prefix/frontier 错误，constructor 却接受。 | episode 入口必须消费已验证的 binding 或自行调用完整验证，并绑定实际读取 snapshot/port；不能让 invalid binding 因未调用独立校验函数而进入新终点。 |
| R3 / 高 / #16 | `try_step(STOP)` 原样返回 s，未标 done；即使 fixture 的 STOP 区间为 complete，后续 GET_MS 仍成功。 | STOP 完结语义与 pending/partial reward 状态分开；完成 STOP 后后续 GET 必须 typed after_stop。需要真实 STOP→GET 序列测试，不能只手工构造 done=True。 |
| R4 / 中 / #16 | ReplayCache 首次 put 自动添加 binding 字段，第二次原样 put 因与带元数据的旧值比较而抛错；get 返回内部 dict，外部修改它或修改传入嵌套对象都能改变已存结果。 | 同内容重试应幂等，异内容拒绝；输入/输出隔离或使用不可变值，防止绕过 write-once。检查缓存资格与绑定身份不可被别名修改。 |
| R5 / 高 / #15↔#16 | A 合法导出的待审 `RELATION/UPDATE` 机械 fixture，交给 B `wsa_adapter.to_cut` 得到 `KeyError: 'RELATION'`。B 的 HEAD 映射只列 MP/ME/MS_RAW/MS_SUM。 | 私有交换格式须保留 relation、operation、target、known/ready、事实有效区间和失效链。更正后新增关系不能被丢弃或报错；未核准关系不能改变事实投影。无需因此立即改公共 C0。 |

定位（固定 HEAD）：[R1 binding.py L120](https://github.com/chensiyu7812/Metacom5_3/blob/a9cf0cca0fecd044a5a4e2a4066355a9a8123dc5/project/src/metacom_pm/rl1v3/asof/binding.py#L120)、[旧 source_id L66](https://github.com/chensiyu7812/Metacom5_3/blob/320a33d1d871199d171f998300ce926b341ca1a8/project/src/metacom_pm/rl1v3/sources/source_registry.py#L66)、[R2/R3 episode L69](https://github.com/chensiyu7812/Metacom5_3/blob/a9cf0cca0fecd044a5a4e2a4066355a9a8123dc5/project/src/metacom_pm/rl1v3/env/research_v32.py#L69)、[R4 cache L143](https://github.com/chensiyu7812/Metacom5_3/blob/a9cf0cca0fecd044a5a4e2a4066355a9a8123dc5/project/src/metacom_pm/rl1v3/env/research_v32.py#L143)、[R5 adapter](https://github.com/chensiyu7812/Metacom5_3/blob/a9cf0cca0fecd044a5a4e2a4066355a9a8123dc5/project/src/metacom_pm/rl1v3/asof/wsa_adapter.py)。

其他待核验风险：#16 的 `pr13_file` 运行时解析远端分支名，而非强制指定 #13 commit；新复跑应固定本报告 HEAD 和输入 hash，不以“仍为 54 条”代替原样校验。#16 的 G 白名单扫描只有两个旧 fixture 请求，未覆盖完整 120 个正式绑定请求，更未覆盖 #15 新 renderer 的实际原生 payload。

4. **跨线审阅账本及 #15 的利益冲突处理**

| PR | 已有独立/跨线证据 | 尚缺的验收 |
|---|---|---|
| #10 | 原 WS-B 在 [ROUND7_STATUS](https://github.com/chensiyu7812/Metacom5_3/blob/dd33e1311eea56a9312e99c7f237e928ee09fe12/project/outputs/pm_rl1/v3/WSB_S3/ROUND7_STATUS_ZH.md) 明确检查 #10 `73fdb12f`，临时演练 8/8、120 终点、身份和 payload。 | 是集成前兼容性证据。#10 合入后 B 必须在真实 integration base 重做附录；本协调者不把自己作为 A 的测试当成 B 批准。 |
| #11 | 包含 B 对旧正式 integration 的 B5/B1 回执；A/#12 有针对 G0e 的联合复核材料。 | 最终 dd33e131 的新增奖励审查/接口不是被早期 A/B 演练完整覆盖；正式 G0e 附录未生成。B 自测不等于独立审阅。 |
| #12 | A 在合成树上运行 B 自有 addendum，并保留独立 A 重建的逐项一致证据。 | 尚无针对 #12 最终 HEAD 的原 WS-B 明确签收；不能以 A 运行 B 脚本替代。retarget 后需 B 对新旧 key、payload、token 和 A0 保全再确认。 |
| #13 | #16 的原 WS-B 审计独立复现 MP 全历史 latest 问题，并核对原 54 项资格。 | 这是对特定结论/输入的交叉印证，不是对 #13 全 PR 的 GitHub approve 或语义金标批准。可按只读工具/分析文档审阅。 |
| #14 | #16 是原 WS-B 按 V3.2 方向做的 CPU 准备。 | 未见正式 plan approve/H0；按候选文档入库，不将方案合并当执行状态采纳。 |
| #15 | [原 WS-B owner 评论](https://github.com/chensiyu7812/Metacom5_3/pull/15#issuecomment-6978675343) 与 [#16 独立收据](https://github.com/chensiyu7812/Metacom5_3/blob/a9cf0cca0fecd044a5a4e2a4066355a9a8123dc5/project/outputs/pm_rl1/v3/V32_WSB_P0P2/ASOF_JOINT_RECEIPT_ZH.md)，明确针对 b63635f3，独立 RAW oracle 检查 65/65。 | X5a 双 horizon 未检验；snapshot_sha 未由 B 重算；真实更正链未提供；新 typed renderer/请求身份不在该收据的完整验收范围。#15 内 A 派生 B-role 的 100 tests 不替代这些缺项。 |
| #16 | B 提供自己的新代码、独立 A 数据复核和 603 项自测。 | 本轮 R1–R5 应由 WS-B 修复并回复固定 HEAD；B 接口变更需 A/B 双方按对象逐项签收，再由协调者复核。作者自测或本协调者发现问题都不是验收通过。 |

WS-B 评论由共享 GitHub 账号发布，其工作线独立性根据明确的“WS-B owner”署名、B 自有检查器和 PR #16 代码来源记录；不宣称是不同 GitHub 账号或人工语义审核。本次只读审查未发布新评论、请求 review 或改动 PR 元数据；上述未闭合项继续作为队列阻塞，不假报“已取得完整 B 验收”。

对 #15 当前数据做的只读核对：65 个 JSON 的 canonical SHA 均可重算一致，但这只是协调者核对，**仍须 B 独立重算并签收**。当前完整 ledger 93 行：68 RAW、5 MP、9 ME、11 SUM；RELATION=0，valid_from/valid_to 非空均为 0，人工核准=0。B 的 65 个切点只见到其中 4 个唯一 MP，和完整 ledger 的 5 条不冲突。真实更正证据尚无；A 应明确报告这一限制，不能用人工合成关系补充为真实语义证据。

snapshot SHA 的现有实现规范可供 A 编成交换文档：对象中仅去掉顶层 `snapshot_sha`，保留 payload 其余字段；dataclass→字段对象、tuple→JSON array；UTF-8、sort_keys=true、ensure_ascii=false、紧凑分隔符、禁止 NaN/Infinity、无 Unicode 归一化、无结尾换行，然后 SHA256。来源见 #15 `compile/asof.py:318–328` 和既有 `io.py:1–51`。数组顺序是身份的一部分，不能与 B 对转换后 records 的摘要校验和混称。双 horizon 仍需 A 另交：3 owner 各至少一个相同 prefix 的 past-only/full-history 成对文件，并让 B 用自己的规则验证。

5. **建议的可执行队列（尚未授权执行）**

推荐顺序：**#13 → #14 → #10 → 暂停等待 B 正式绑定 → #11 → #12 → 暂停等待 as-of 联合验收 → #15 → #16**。#13/#14 是可独立前置的文档/工具段；业务顺序不变。用户可以只确认前一段，后段保持 HOLD。当前不得直接执行整条队列。

| 次序 | 合入前动作和接受条件 | 合入后的实际影响 |
|---|---|---|
| 1 #13 | 核对固定 3188/83/54/120 输入、manifest、只读脚本及科学边界；保留最新 HEAD CI。 | 新增审查文档/诊断脚本/待执行提案，不改 bank 或排序。 |
| 2 #14 | 审阅 V3.2 与 V3.1 的阶段映射；候选文件不登记 H0，不把 P2 准备标完成；Draft 转 Ready 属后续获准队列操作。 | 新增研究方案和 A/B 指令，无运行或治理状态改变。 |
| 3 #10 | 引用原 B 对 73fdb12f 的集成前技术检查；在新的实际 base 核对最终 HEAD CI及受保护文件。 | G0e CPU 请求端口/A0 申请入 integration；不是正式 G0，不产生模型结果。 |
| 暂停点 A | 原 B 同步真实新 integration，在新目录运行 B6e_g0e_binding_addendum；8 prefix、120 endpoint、471 顺序；只允许 renderer/Step-2/G/decode 身份预期变化，原资源组不变；旧 reward 不命中，STOP 全 pending，完整 payload 无泄漏。重跑严格 V3/full CPU/最终 HEAD CI。 | 此时才形成正式 G0e 工程绑定；不能把临时 union tree 的结果写为正式验收。 |
| 4 #11 | B 提交上一步新附录并说明 dd33e131 后的增量；针对新增反馈/终点接口完成跨线审阅，最终 SHA CI 成功后转 Ready。 | 追加 B2-v3/B1/B6e/B8e 工程准备；仍无合格 NeedCard、J1 或研究奖励。 |
| 5 #12 | #10 已合入；将 base 从 A 工作分支改到 integration，检查 diff 仅余补充增量；同步最新 B 接口，由原 B 签收最终 HEAD；验证原 100 OFF/native IDs、83 样本、120 请求不变。 | 增加绑定/加载守卫/A0 v2 申请和审阅材料，不增加 GPU 授权。 |
| 暂停点 B | A 提交双 horizon、SHA 规范和真实更正限制；B 补做 X5a/hash；A/B 处理 RELATION 交换及 R1，签收 PrefixAsOf→frontier→snapshot→ReadingView→renderer→复合 key 全链。 | 建立机械层可消费接口，语义和资源价值依旧 pending。 |
| 6 #15 | 原 B 在最终 A HEAD 上补完上述机械验收，并单独审 typed renderer 的可见字段与新旧身份；本协调者不得以自己的测试批准本 PR。 | 独立 sidecar/RAW 重放/待审类型化材料入库，旧 bank 不替换。 |
| 7 #16 | WS-B 修复 R1–R5；#11 已合入后 retarget 到 integration，保留旧 dd33e131 冻结产物；以实际合成接口复跑 CPU，A/B 对最终 SHA 签收；迁移提案仍不应用。 | 新绑定、复合键、观察白名单和未执行 P2 协议可作为 CPU 准备；不能开放正式训练/生成。 |

每一个上游合入或 HEAD 更新都会使当前“基于 320a33d1/父 PR”的 CI 成为历史证据。后续必须记录新的 base/head、变更增量和相应 CI，不复用旧测试数字冒充新 HEAD 验证。优先保留原提交祖先关系；若采用 squash，必须明确子 PR 的重定基线/提交映射并重新验收，避免 #12/#16 重复带入父 PR。

6. **接口冻结和迁移验收清单**

| 接口 | 必须冻结/复核的对象 | 责任与当前状态 |
|---|---|---|
| PrefixAsOf / frontier | owner 内 rank、completed/known/ready、family closure、prefix context；会话局部 source hash；全文件/全 registry hash 只留审计旁路 | A 提供双 horizon，原 B 独立核对；R1 未闭合 |
| snapshot / writer | 精确 canonical payload、writer 文件身份、ledger prefix、relation、validity、RAW/SUM fallback；双 horizon/批流/重启同一 hash | A 提供、B 独立重算；X5a、真实更正覆盖及 R5 未闭合 |
| ReadingView / G | C0 字段、内部 rejected→公共 unknown 的兼容表达、主体/阶段/来源及合理忽略规则；PM 与 G 不见 NeedCard/Judge/私有 ID/未来/未读正文 | 原 B 对 #15 的新 renderer 单独验收；旧 G0e 120 需正式重扫 |
| G0e / typed proposal | #10 固定 Notes 和 decoder；#15 新 renderer 保留新请求身份、input_ids=null、executable=false | 新提案未获得原生 token/capacity/实际阅读证据，不可直接送入 G0e executor |
| TerminalKey / cache | 旧 C0 key、A 的 request-proposal identity、B 的 composite key 三类分别存储；新身份不迁移旧 reward | R1/R2/R4 修复后重验；所有正式 STOP 仍 pending |
| C0 迁移 | #16 提议 TerminalKey 加 asof_binding_sha256、IndexManifest 加 writer/frontier；是未采用提案 | 当前继续 C0 0.2.0 + 私有复合键。若未来采用，必须另交 reader/writer 兼容矩阵、Schema/版本/fixture/manifest 升级范围及旧 key 读取策略，并获 A/B 审阅和研究者批准 |

迁移中特别注意：既有 `C0FiniteHeadEnv` 明确只接受 `pmrl1v3-contracts-0.2*`；不能只加字段或改版本号而不处理消费者。tier/资格标签排除于内容身份不等于允许无审批晋级，研究资格须有独立审批与语义证据记录。

P2 保留原 54 输入：16 ELIGIBLE、24 LEGACY_DIAGNOSTIC、14 BLOCKED；不换样、不恢复 324 MP。原 83 是 20/40/23（同样按 ELIGIBLE/LEGACY_DIAGNOSTIC/BLOCKED 顺序）。ELIGIBLE 是机械资格，不是值得读或有帮助。RS 的 R0/F/METHOD/METHOD+CASE、76 对盲评、S7 补充集和 J1 8192/16384 都是未执行/未采用方案；原 800-token JudgeIdentity 不暗改。方法来源/许可/适用、人工标签、同 G/OFF 支持收益、奖励资格和真实等待均未完成。

7. **本轮验证和交付范围**

- 只读 GitHub：七个 PR 的 metadata、评论、reviews、threads、最终 HEAD workflow/job/log；原始 JSON/日志落在本审查目录。
- 本地独立 bare 镜像中核对祖先和增量；只构造新增文件 union tree，没有 Git merge、没有 push、没有改 PR base/state/review。
- union tree 上选取八个 G0e/绑定/as-of/审查/V3.2 接口测试文件，**195 passed / 0 skipped / 0 failed，50.43 s**，见 `combined-interface-tests.log/.xml`。本轮未再跑训练/优化器测试或模型；已有全套 CI 如上独立读取。这个定向结果不是全量联合 CI，也不是 B 正式验收。
- 五类反例另行执行，结果保留；现有测试通过没有覆盖这些反例。本次没有以“CI 绿”消除它们。
- 65 snapshot SHA 只读重算 65/65，完整 ledger 的真实更正/有效区间/人工核准为零，见 `SNAPSHOT_STATIC_AUDIT.json`。
- `TREE_AUDIT.json`、`UNION_TREE_RECEIPT.json`、`QUEUE_CANDIDATE.json` 可供后续执行者按固定 SHA 逐门检查；更新任一 HEAD 后这些回执应保留为历史记录并另出新版。

未改 integration/main/H0/EXECUTION_STATE/公共 Schema/旧冻结证据，未合并任何 PR，未运行 GPU、Generator、Judge、训练或付费调用。下一步是研究者确认具体合并队列，以及各工作线按上述固定对象补齐审阅/修复证据；本报告不包含合并授权。
