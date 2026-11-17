# WS-A A1/A1b 正式交接与跨线回放（2026-11-18）

本轮保全并正式交付已有来源/bank，新增可调用的薄适配层及未验证 RS-v0 策略类别目录。没有重建输出资产、重新扫描64GB、运行GPU、Generator、NeedCard writer、训练或付费调用。A1/A1b 仍等待 integration owner 合入 PR #8 及在集成提交验收，未修改全局状态或宣称 completed。

## 提交、保全与身份

- 冻结 C0 `pmrl1v3-contracts-0.2.0` / `pmrl1v3-json-1`，integration 基础 `8bcd326e5158482e3e4ad1760f82b117a58d1e2c`。共享34文件和32 Schema与冻结记录相同，集合SHA `6262fdac86a611a13023736ec38711e2cf894b6af5fe4cde4be18e8f13490d82`。
- A1准备 `69a850c5` → 正式 `7116b8bd430727cebe7fd05c328486bd9a4d1f99`；A1b准备 `01a95114` → 正式 `c9dd5aae7bff5262455fb6cc6942142a5abb35b9`。准备父子链 `d0bde000 → 69a850c5 → 01a95114` 完整，Git connectivity检查退出0。本地 `backup/pmrl1-v3/a1-preparation-69a850c5`、`backup/pmrl1-v3/a1b-preparation-01a95114` 固定安全引用，见 PREPARATION_PRESERVATION.json。
- 新读取端口 `14fd459e473cc3e98ab8b4dbddf73216e9314759`；RS目录及初次原生端口验收 `a26998f088c3e0a410793faa188b0a1939fb5c7e`。继续正式 PR [#8](https://github.com/chensiyu7812/Metacom5_3/pull/8)，未在已集成PR #5堆叠功能。
- 原准备44文件中43份逐字不变，仅 `retrieve/v0.py` 扩展显式token前账单和私有容量测量；原始数据、manifest、失败日志、资源ID、迁移关系均未改。旧 REAL_REPLAY 的 ReadingView、实际读取轨迹、规范回放与 TerminalKey 完全一致。
- source=`sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02`
- bank=`bank:02d0a4b1e62fd033c02b4fdc8e76d8796b285aa058cb59201aacde2c13ce8dd9`
- index=`index:227cca582de991e1ef823e0122e842be7316bf4339acc73c88992870ff1846f3`

## 五层统计，避免混用分母

以下全量数值来自已保全、绑定SHA的4119前缀准备实测，本轮没有伪称重跑16476次全量GET。详情见新增 ASSET_CONVERSION_SCORECARD.json；本轮24前缀读取单列。

| 头 | 原始资产 | 来源/跨度核验 | bank实际记录 | 至少一个合法前缀可读的唯一记录 | 实际读到的唯一记录 | 原全量GET成功 |
|---|---:|---:|---:|---:|---:|---:|
| MP | 713候选 | 713 | 387 | 343 | 169 | 3610/4119 |
| ME | 1523候选 | 1523 | 1525 | 1461 | 500 | 4108/4119 |
| MS | 401 RAW会话 | 401 | 401 | 383 | 352 | 4119/4119 |
| RS | 1300 ESConv来源 | 875合法train来源 | 875完整案例 | 875 | 316 | 4119/4119 |

bank合计3188：3185 unverified、3 development_reviewed，无研究级事实认证。MP旧池缺失325项中324继续隔离、1按既有证据改为ME；另1旧池MP改为ME。ME=1523旧ME+2转入，其中1旧ME已按证据修复为unknown阶段。跨度可验证并不解除324项历史排除。没有将evo_emo评测summaries作为MS-SUM。

原全量GET 15956/16476成功（96.844%），520次无合法候选；唯一可得记录3062/3188，实际选中1337条。这两个“唯一记录”统计不是GET次数。来源仍为401个人会话+875外部案例；84重叠family和341非train来源排除；esc1198的p13/p18多owner关联保留。

本轮固定24覆盖前缀×4头=96次根GET，93成功（96.875%）、3次MP无候选；唯一读到MP20/ME23/MS24/RS15。它是覆盖样本，不是全量来源普查，也不是召回准确率。读取不成功不会伪造ReadingView或推进成功读取序号。

## B5真实跨线结果

B所有者的修复已在 [PR #9](https://github.com/chensiyu7812/Metacom5_3/pull/9) 代码提交 `d06715bf6893710c8b21f2c91c7cac42c0111e85` 中实现；A未修改B业务。

1. 实际运行B的 `B5_real_replay_v2.py`，在B自己的环境24/24通过。运行期间HEAD由a077变为d067，但55个相关源码/config字节前后不变且逐文件与d067提交blob匹配，保留原始记录。
2. 再以干净、固定d067的B稀疏工作树直接调用其未修改的 `bank_replay_v2.replay_prefix`，传入A14fd的新PrefixPort。24/24通过，21个前缀各16子集、3个因MP无候选各8子集，共360终点、1413条实际GET顺序。独立加载bank/tokenizer回放24/24相同；容量压力及拒绝不推进状态各24/24；ready_at等于cutoff的21条合法边界已覆盖。实际加载16模块全部匹配指定提交，未复制B代码。与B自有适配器的键、资源ID、正文hash、token账单完全一致。

证据在 `B5_native/`、`B5_joint/`；后者含可重放harness、输入文件SHA、加载模块SHA、原始输出及比较。此为两个已提交实现的联合工程验收，**不是已合入integration的验收**。B v1历史工具仍不支持完整读取上下文，不能继续用它作为新接口的验收版本；本轮v1的真实失败结果保留在 `B5_v1_failure/`，未将它改绿。B v2版本为 `pmrl1v3-b5-bank-replay-v2`。

## B1目录与直接调用

A端口协议 `pmrl1v3-a1b-read-port-v1`：

```python
from metacom_pm.rl1v3.bank.v0_port import make_port_factory
factory = make_port_factory(root=repo)
prefix = factory.prefix(b0_row)
port = factory(prefix)
history = port.legal_sessions()             # 严格过去、同owner
available = port.availability()             # 合法候选数，独立于容量
r = port.read('RS', acquired=(), input_tokens_before=port.base_tokens)
# 成功后再把 r.reading 放入 acquired；失败不得增加 ordinal。
key = port.terminal_key([r])
trace = port.execution_trace([r])
assert port.replay(key).acquired == key.acquired
```

`input_tokens_after`沿用C0保守账单；`token_account()`另外返回原生完整prompt的实际token数。计时elapsed_ms是测量值，不属于稳定内容身份。Bank build/load和source_registry build/load保持原入口；日常接入只load既有manifest，不需要重建。

RS目录协议 `pmrl1v3-rs-v0-strategy-catalog-1`，目录ID后缀 `7323c7f40e7b99cff5b7e7bcc10354c9360b7a0a6016a3495ee13124998d344f`，输入Schema `rs-v0-catalog-1`。875案例内原始12403个supporter策略标注组成8标签、7可选择类别、Others不可选；定义unknown，质量unverified，非A4方法卡。旧11590策略与13172 treatments只保留关联，不相加，也不把旧guidance/treatment文本升级为建议。

B v1接口 `catalog.for_needcard_writer()` 已实际构造24/24 ready输入。又调用B d067的 `needs.protocol_v2.build_pack`，直接传A的catalog对象，使用固定Qwen原生tokenizer：24/24 ready，输入2763–27009 tokens，没有截断；无目录时明确blocked_catalog。`B1_V2_CATALOG_PREFLIGHT.json`绑定6个实际B模块、目录文件及tokenizer SHA；未调用writer。

## 相关性与剩余质量限制

RELEVANCE_POOL.jsonl保留93条实际根读取的词面分、当前用户问题、查询窗口、来源跨度；RELEVANCE_SPOTCHECK.json固定抽取覆盖顺序首尾两前缀的8条，属于助手开发检查，不是人评或独立金标。4条在致谢告别轮无须使用，1条主题不匹配，3条主题相关但需尊重时间更新。示例：纽约同居计划查询的RS词面分0.667，召回疫情焦虑案例；分数不能代表收益。旧南部/西北部求学记录虽相关，不能覆盖当前纽约计划。

这是确定性v0词面检索，未做A5 BGE/BM25/RRF，也未证明召回或回复质量改善。案例原话可能含不适当建议、supporter自我披露及旧事实；unverified标记与引用来源必须保留。来源许可仍承袭原research-only/部分上游许可未解决状态，未重新授权。G0/G1、生成终点、Judge标签、OFF对照、人评、训练均未执行。

## 测试及失败修复

- bank/port/catalog针对测试42通过；全V3 413通过，严格门禁0skip/xfail/failure/error；32Schema检查通过，integration-base本地PASS。
- 完整CPU 2246 passed、1历史skip、11 GPU deselected，耗时547.08秒。唯一跳过为旧Llama tokenizer路径不存在，不能算完整覆盖。TEST_RESULTS.json记录命令、环境和XML身份。最终PR HEAD的GitHub CI在推送后单独核对并记录PR正文/交接评论，不用先前a077或中间提交绿灯替代。
- 目录首轮测试1失败是测试误向decode_contract传dict，改为规范JSON后仍完整核验12403来源跨度，保留原失败日志。
- B1 v2交接脚本首轮已构造24输入，但归档模块元数据时遇到namespace module的`__file__=None`；修正归档逻辑后全流程退出0，未修改B断言/业务。
- 新建完整B隔离工作树遇到磁盘空间不足，未删除既有工作树或历史结果；改在有空间的数据盘使用稀疏工作树，仅取所需B代码和覆盖清单。精确SHA检查仍完整执行。

可向B正式交付端口和目录；B5已经能实际回放24覆盖前缀，B1工程输入阻塞已解除。合入顺序仍为PR #8 → B同步integration/PR #9 → 集成提交真实回放。B1真实writer与后续B2评判/生成实验仍需独立模型授权和相应依赖；本轮不开放GPU或调用权限，不修改H0、main、PR #4或全局EXECUTION_STATE。
