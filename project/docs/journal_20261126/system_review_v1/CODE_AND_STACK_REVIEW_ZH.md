# 动态研究路径的代码与组合栈审查

审查基线：`c40b90c99cb991cf1c2793ffbe9927a0011885ab`。结论：**Share with caveats；有限范围已完成，全系统科学资格验证仍为 Partial。** 本轮是只读深审及独立 CPU 核验，没有修补冻结实现、改写 DR3、重跑模型或重建 J00。源数据适配、质量判断及完整延迟分析由本轮另两份审查负责；这里不重复其私有评语。

最需优先处理的是状态身份：一个合法可达的状态 hash 可以对应不同的 `last_hits` 与不同的下一次可见观察。现有实际调用还绑定独立 observation/payload SHA，因此此发现**不等于已经发生历史返回串接或结果污染**；它限制的是只靠 state hash 恢复、合并轨迹、缓存策略状态或建立学习状态。

## 1. 确切范围与版本

实查链条为：开发源适配 → SourceRegistry → As-of/Ledger → SnapshotPrefixPort → SEARCH/EXPAND → 可见观察/控制器 → Journal renderer → 独立动态 worker/监督器 → 原始 journal/collector。另读旧 TerminalRegistry/RealInstance 的接口，检查其能否承接新动态状态；没有运行 BC/PPO、评审模型或新 G。

依赖清单是实测文件身份，不是把 journal HEAD 当作全栈。[DEPENDENCY_MANIFEST_PUBLIC.json](DEPENDENCY_MANIFEST_PUBLIC.json) 记录 28 个相关模块的解析路径、源流、具体 commit 与 SHA，以及完整固定清单的核验结果。[COMPLETE_CODE_FILE_CLOSURE_PUBLIC.json](COMPLETE_CODE_FILE_CLOSURE_PUBLIC.json) 进一步公开全部 531 个组合栈文件的 path/SHA/来源 commit、613 个原 DR 执行器文件的 path/SHA，以及 81 个 grammar vendor 文件的 path/SHA；这是完整代码闭包身份，不包含文件正文或 RAW 数据。

| 层 | 实际身份 | 本轮核验 |
|---|---|---|
| journal | `c40b90c99cb991cf1c2793ffbe9927a0011885ab` | 已跟踪文件无本轮修改 |
| 私有组合栈 base | `b07db1046c948a77643a646bb845a21e74c10044` | 原逐文件清单 531 个全部匹配 |
| A | `df21b11c96165c1a3dd8ef0edf76df2788ee3e45` | 15 个来源文件 |
| B | `7eeff1cf8dcd889e4a08e9a2a723dbe3f864e118` | 42 个来源文件 |
| G | `73fdb12f29b6970a268eeda704d73e1bd35b1c3e` | 6 个来源文件；其余 468 个来自 base |
| DR `packages-v2/executor` | 原 plan 内 inventory | 613 个文件全匹配；与当前组合栈的共有文件差异 0、缺失 0 |
| 当前分析增量 | collector、decision diagnostics、dynamic analysis | c40 比 DR 执行器多 3 个分析模块，未伪装成当时已运行代码 |

组合栈中的 `journal` 是指向 `/home/tokkio/Metacom5_3-journal/project/src/metacom_pm/rl1v3/journal` 的软链接；新实验真正运行的是已独立复制冻结的 executor。两者的角色不同。本轮正在开发而不属于 c40/DR 的模块另列为工作树增量，不计为历史执行依赖。未合并 A/B/G 分支。

实际生成环境为 Python 3.12.14、Transformers 5.17.0、Torch 2.7.1+cu128、tokenizers 0.23.2、safetensors 0.8.0、隔离 xgrammar 0.1.21；81 个 grammar vendor 文件匹配。vLLM 0.10.1 虽安装，本次实际 backend 是 HF。CPU 单测环境则为 Python 3.11.15、Transformers 4.57.6、Torch 2.3.1+cu121、tokenizers 0.22.2，不把这些单测等同于真实生成环境兼容证明。依赖清单还列出两环境全部已安装 distribution 名称和版本，均经 metadata 读取而未 import GPU 包；**安装清单不等于本次实际 import/运行依赖**。

SourceRegistry 在逐文件来源清单归属 `base b07db104`。下文为便于沿 A 接口阅读链接到 A 的同路径文件；已实际比较 Git blob，base 与 A 的 SHA256 同为 `337a779ece14ab87bd95a75a279b0a34257bc4ecc030fae54ba7940af071032d`，所以是同字节代码的两个可定位版本，并非声称该文件由 A 修改。完整等价证明列于依赖清单的 `source_registry_base_A_equivalence`。

模型是本机冻结 `Gemma-4-12B-it-707f0a3`，revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`、架构 `Gemma4UnifiedForConditionalGeneration`。本轮新读并核对 tokenizer/config/chat template 等 6 个小文件 SHA；23,919,549,408 字节权重只核文件大小并继承四包 `MODEL_BYTES_VERIFIED` 的既有完整 SHA 证据，**没有重新加载或重新声称本轮做了权重全字节审计**。模型/Tokenizer 每文件 SHA 与两环境版本均在清单中。C0 合同仍是 `pmrl1v3-contracts-0.2.0`。

## 2. 优先级与三类证据

`observed_failure` 表示实际已发生的失败；`code_confirmed_limit` 表示由代码及有限 CPU 反例证实的限制；`potential_unmeasured` 表示后果或适用性尚未实测。限制不自动等于质量失败。以下建议均针对未来新身份，本轮没有修改旧实现。

| ID / 优先级 | 分类 | 具体问题及证据 | 建议 |
|---|---|---|---|
| E1 / P1 | code_confirmed_limit | `pomdp_memory.py:249–252` 的 state hash 未含 `last_hits`；`109–132` 的观察却包含它。两条合法三次 SEARCH 路径实证同 state hash、异 observation hash。 | 新版本显式定义完整状态/观察序列化，至少绑定 `last_hits`；恢复要求 trace、完整 observation 与 payload 全部一致。旧 hash 不迁移重写。 |
| E2 / P1 | observed_failure | DR3 OneShot 是有效 JSON、模型 EOS，但 `_query` 的初始词表约束拒绝了未观察词；`dynamic_runtime.py:300–386` 捕获异常后停止整个来源配对作业，导致当前路径没有终局，另 9 槽未执行。 | 报告为控制动作约束拒绝，不能当生成失败或 10 个语义失败。未来若改变语法/词表约束或故障隔离粒度，另立协议，不修 DR3 输出。 |
| E3 / P1 | code_confirmed_limit | `_rank` 不排除已读来源；EXPAND 不移除先前 span；`_views` 按内容 hash 键排序。实际 24 次 EXPAND 都重含已供 span，12 个终局保留 span+parent；有内容的 16 个普通路径中 9 个报告日期非单调。 | 把重复收费、交付内容冗余、无新 parent 与任务信息增量分别记账。若试去重/时间序新表示，只能作新比较，不能假定必优。 |
| E4 / P2 | code_confirmed_limit | handle 仅按 nonce+record ID；再次命中同 parent 时 `handles` 不更新初次 span。实际 1 次重查的新 span 与保留的 hit 文本不同；新 span 仍在 `readings` 中，不能叫全部证据丢失。 | 新接口明确 handle 指 parent 还是当前 hit，并保留 span 版本/最新命中引用；当前恢复按原完整观察，不自行覆盖。 |
| E5 / P1 | code_confirmed_limit | Top4 宏是 1 次检索+4 次完整父会话读取；普通路径最多 4 个 SEARCH/EXPAND，且先付 span 费用。相同 4096-token cap 没有使动作粒度相同。NoText 是透明规则而非另一个同模型无文本控制器。 | 作为不同系统基线报告质量与完整成本，不能把差异只归因于序贯性或读后文字。保留真正同状态、同可行动作域的局部对照。 |
| E6 / P1 | code_confirmed_limit | 旧 `RealInstance`/DP 是最多 16 个四头子集；当前动态 query、handle、读取次数、观察与费用不由子集决定。动态运行始终返回 `formal_reward=None`，没有接成可训练动态终点表。 | 先完成新状态/轨迹身份和合法终值资格接口；不能把同 MS 内容或同 MS bit 当同学习状态，也不能将工程 PPO 接口称研究学习已完成。 |
| E7 / P2 | potential_unmeasured | Ledger 的 known/ready 是 session-end 逻辑重放；现有 RAW 代表历史报告，不证明事实现在仍成立，也没有历史线上 Writer 到达时间测量。 | 在长期部署、异步更新与当前事实有效性主张前单独验证；本轮不据 replay 时间宣称部署新鲜度。 |
| E8 / P2 | potential_unmeasured | `outcome_adapter.py:133–138` 接受传入资格 receipt 的字段及 SHA 格式，但此函数自身不读取/验证该外部资格证据文件。动态实验当前没有进入此晋级路径。 | 未来启用训练前明确可信资格凭据的产生/核验边界；不能仅凭一个形式合法字典认定已完成独立语义资格化。未发现本次借此晋级。 |

精确代码定位（均按基线/固定依赖）：

- [状态、观察、查询及重复读取](https://github.com/chensiyu7812/Metacom5_3/blob/c40b90c99cb991cf1c2793ffbe9927a0011885ab/project/src/metacom_pm/rl1v3/journal/pomdp_memory.py#L96-L261)：`96–104` 渲染顺序；`134–167` 动作/查询/检索；`189–246` handles、费用与内容；`249–252` 状态 hash。
- [控制器语法与动作校验](https://github.com/chensiyu7812/Metacom5_3/blob/c40b90c99cb991cf1c2793ffbe9927a0011885ab/project/src/metacom_pm/rl1v3/journal/pomdp_controller_protocol.py#L39-L194)：`39–69` 静态 grammar；`130–158` OneShot 初始词表；`161–194` ToolAgent 的真实可见词/handle。
- [动态 Top4 与整包停止](https://github.com/chensiyu7812/Metacom5_3/blob/c40b90c99cb991cf1c2793ffbe9927a0011885ab/project/src/metacom_pm/rl1v3/journal/pomdp_dynamic_runtime.py#L171-L203)：`171–203` 宏操作；`300–386` 六臂固定顺序、单控制失败与整包停止。
- [原四头 RealInstance](https://github.com/chensiyu7812/Metacom5_3/blob/7eeff1cf8dcd889e4a08e9a2a723dbe3f864e118/project/src/metacom_pm/rl1v3/train/real_instances.py#L38-L106)：`56–62` 16 子集奖励；`68–95` 固定头回放/DP；`98–106` 不完整实例排除。
- [资格接口](https://github.com/chensiyu7812/Metacom5_3/blob/c40b90c99cb991cf1c2793ffbe9927a0011885ab/project/src/metacom_pm/rl1v3/journal/outcome_adapter.py#L129-L157)：收据字段检查和 RealInstance 桥；本次没有调用它把 DR 结果升级成正式 reward。

## 3. 实际重复、排序与状态核验

[MECHANISM_PROBES_PUBLIC.json](MECHANISM_PROBES_PUBLIC.json) 中的状态反例只使用 synthetic 两来源，不引用真实问答或 gold。两条轨迹为 `SEARCH(initial)→SEARCH(alpha)→SEARCH(beta)` 与 `initial→beta→alpha`，nonce 与来源相同，最终内容、handle 首次创建顺序、访问数和累计 token 费用相同，只有 `last_hits` 排序不同；状态 hash 一样，观察 hash 不一样。这里没有通过手动修改私有字段制造差异。`allowed_tokens` 当前可从初始 query 和已交付内容重建，`status` 当前随 done 变化；没有把这两个遗漏一并声称为已证明的独立冲突。

同一 synthetic episode 中再次 EXPAND 已展开的 handle，G payload 不变而状态与收费改变。这证明“同内容可复用质量”不等于“同轨迹/同成本/同控制状态”。本轮未宣称复用的延迟是实际在线延迟。

从全部冻结 DR 事件独立统计见 [OBSERVED_TRAJECTORY_COUNTS_PUBLIC.json](OBSERVED_TRAJECTORY_COUNTS_PUBLIC.json)：

| 检查项 | 实际分母与结果 | 解释限制 |
|---|---:|---|
| 成功 SEARCH / EXPAND | 22 / 24 次 | 不含 STOP；不是模型质量成功次数 |
| 完全相同 query 重复 SEARCH | 0/22 | 不等于没有检索同一来源 |
| SEARCH 没有新 parent | 3/22 | 同 parent 仍可能有不同 span，不能直接叫无信息 |
| EXPAND 重含此前已交付 span | 24/24 | 完整 parent 可能有额外必要信息；语义收益另测 |
| 终局同时有 span 和其 parent | 12 条 | 不把它们合并成两个独立来源 |
| 普通有内容终局日期非单调 | 9/16 | 排序由 hash 确定；不包括 Top4 宏与无资源 STOP |
| 有资源的控制器观察字段精确重复 | 2/2 个观察 | `hits.reading_text` 与 `readings` 重复，合计 1908 字符中 954 重复；是字符，不是 native tokens |
| 新 span 命中但 hit 仍为初次文本 | 1 次 | 新文本仍在 readings 中；未测决策影响 |

这些是表示和操作证据，不是凭重复率、排序或省 token 即宣布改进质量。没有按结果重选样本，也未用新提示词追求正结果。

## 4. 已确认的保护与尚未证明的性质

入场来源沿固定 [SourceRegistry:124–170](https://github.com/chensiyu7812/Metacom5_3/blob/df21b11c96165c1a3dd8ef0edf76df2788ee3e45/project/src/metacom_pm/rl1v3/sources/source_registry.py#L124-L170) 校核真实 prefix、owner、dataset、严格过去 rank、ready rank、报告日期及失效操作。[As-of:194–206、272–323](https://github.com/chensiyu7812/Metacom5_3/blob/df21b11c96165c1a3dd8ef0edf76df2788ee3e45/project/src/metacom_pm/rl1v3/compile/asof.py#L194-L323) 核完整 RAW 与全部来源跨度，物化只取合法 frontier 且 known/ready 已到达的条目；非批准语义项仍 quarantine，当前有效性默认 unknown。

[SnapshotPrefixPort:26–51](https://github.com/chensiyu7812/Metacom5_3/blob/c40b90c99cb991cf1c2793ffbe9927a0011885ab/project/src/metacom_pm/rl1v3/journal/memory_port.py#L26-L51) 只桥接 `MS_RAW/raw_available`。动态 factory 在 `pomdp_dynamic_runtime.py:123–168` 绑定 constructed task 与真实 prefix anchor，生成 snapshot-local 候选池，每条路径再核 source binding、每次检索/展开再检查合法性。动态检索使用当前 task query，不是默认原对话 query；代码没有将评估 source 指针送给排序。MP/ME/RS 仍 masked。

这里复用 PrefixPort 的源银行/身份，但动态 SEARCH/EXPAND **不是调用旧四头 `PrefixPort.read('MS')` 来完成每步**，而是新 SearchExpandEpisode 在经过该银行合法性过滤的记录上实现读取。旧 `PrefixPort.action_mask()` 的内部预读行为不能直接推断成动态 episode 的行为。动态 `observe()` 会渲染并计数已交付内容，但不会获取未读正文/score。

当前 Time-Lexical 是词集合交集比例，加 recency、record ID tie-break；span 在所有角色来源句中选词重合最大者，同分取最早句。Hybrid 接口有代码，但 DR 的 factory 没有传入 semantic scorer，故本次不是 Hybrid/BGE 实验。支持者建议、包装词及常用词的检索影响见本轮源适配审查，不能把“源精确”与“是用户事实”混同。

[renderer:51–86](https://github.com/chensiyu7812/Metacom5_3/blob/c40b90c99cb991cf1c2793ffbe9927a0011885ab/project/src/metacom_pm/rl1v3/journal/renderer.py#L51-L86) 明确历史资源身份、HTML 转义资源，绑定 system/tokenizer/notes/renderer，超容量不截断。模型返回、request、observation 和 journal 有独立 SHA。53 次模型返回均 EOS，其中一次控制动作未通过词表校验；这两层没有混算。

仍未证明：任意新用户/长历史上的检索有效性，所有自然支持任务的可校准 reward，动态状态训练的收敛或泛化，长期心理模型，异步线上 Writer 时延和客户端可见 TTFT。CPU 依赖/协议通过不证明这些性质。

## 5. 计量与复跑边界

计量只复核接口解释：同 boot 的 monotonic 纳秒；冷来源/Tokenizer/Ledger 与 model load 单列；每条 path 从 factory/合法性检查前开始；guard、日志和 callback 开销包含在真实父区间。嵌套 spans 不相加。`mask_observer_ns` 可能含 GPU 同步/搬运；first nonempty text 可能只是 `thought` 标记，不是有效语义首段；client TTFT 与未独立测量的日志耗时仍为空。固定臂序、首次 STOP 冷首推及后续暖缓存不能给出无条件因果延迟优势。详细数值由本轮延迟审查负责。

以下只读脚本可复跑版本核验、真实事件聚合及三个 synthetic 机制反例；它不 import 模型、不开 GPU、不重算 private 语义评分。`--out` 必须新目录。

```bash
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  project/scripts/rl1v3/journal_review_pomdp_stack.py \
  --repo /home/tokkio/Metacom5_3-journal \
  --stack-manifest /opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/DEPENDENCY_MANIFEST.json \
  --plan-path /opt/tokkio-data0/tokkio_runs/pmrl1-j-dynamic-20261126/packages-v2/batch-01/PLAN.json \
  --collection /opt/tokkio-data0/tokkio_runs/pmrl1-j-dynamic-results-20261126/collection-final-v1 \
  --out /opt/tokkio-data0/tokkio_runs/pmrl1-j-system-review-20261126/engineering/replay-new
```

审查保留正反证据：未观察到组合栈字节漂移或此调用链越过 owner/未来过滤；已证实状态 hash 不足与多处表示/比较边界；未测量的科学影响维持未知。所有改动建议均未应用于冻结协议。
