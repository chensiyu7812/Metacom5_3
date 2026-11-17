# B 侧真实 bank-v0 调用说明（准备版本，待 C0 冻结后正式集成）

C0 沿用 `pmrl1v3-contracts-0.2.0` / `pmrl1v3-json-1`；未修改共享字段。source、bank 与 index 各有独立版本。v0 index 是有明确身份的词面排序清单，**不伪造 C0 Dense/BM25 IndexManifest 中的 encoder/vectors 字段**；该强制编码器 schema 留给 A5，本次使用 `pmrl1v3-index-lexical-static-v0.1` 的私有 manifest。

从仓库根目录运行，设置 `PYTHONPATH=project/src`，使用现有 CPU Python 环境：

```python
import json
from pathlib import Path
from metacom_pm.rl1v3 import contracts as K, retrieve
from metacom_pm.rl1v3.io import canonical_json, decode_contract
from metacom_pm.rl1v3.sources import source_registry
from metacom_pm.rl1v3.bank import bank_v0
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer

root = Path.cwd()
outputs = root / 'project/outputs/pm_rl1/v3'
registry = source_registry.load(outputs / 'A1_preparation/final/registry')
bank = bank_v0.load(
    outputs / 'A1b_preparation/measured_v1/bank', registry,
    expected_version='bank:02d0a4b1e62fd033c02b4fdc8e76d8796b285aa058cb59201aacde2c13ce8dd9')
example = json.loads((outputs / 'A1b_preparation/measured_v1/REAL_REPLAY.json').read_text())
prefix = decode_contract(K.PrefixSpec, canonical_json(example['prefix']))
key = decode_contract(K.TerminalKey, canonical_json(example['terminal_key']))
tokenizer = NativeTokenizer(
    '/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3',
    outputs / 'A1_reuse/ASSET_REUSE_MANIFEST.json')
reader = retrieve.Reader(bank, prefix, tokenizer, g_id=key.g_id,
                         decode_id=key.decode_id, step2_id=key.step2_id)
result = retrieve.read(reader, 'ME', bank_version=key.bank_version,
                       index_version=key.index_version)
assert isinstance(result, K.ReadSuccess)
source_spans = [span for rid in result.record_ids for span in bank.by_id[rid].source_refs]
replayed = reader.replay(key)
assert isinstance(replayed, K.ExecutionTrace)
replayed.verify_key(key)
```

真实示例为 p1 / esc245 / cut_turn=1；原轨迹 GET_MS→GET_ME→GET_MP→GET_RS→STOP 和规范化轨迹均保存在 REAL_REPLAY.json。STOP 仅重放完整 TerminalKey，不伪造 Generator 输出、奖励或 B2 标签；相应表项保持 pending。

`retrieve.search(bank, head, prefix)` 返回私有 RetrievalResult，先 owner/严格过去/ready/family/train/版本合法性，再静态末三轮词面排序，确定性 tie-break；每头交付一条完整记录。`reader.availability()` 是合法候选数量，不是 top-1 数或容量。`reader.action_mask(acquired)` 再检查容量。ReadSuccess 中 record_ids 可定位私有原文跨度；只将 reading 交给 PM/G，不序列化整个记录、来源或检索结果到 Observation。

`read` 是无状态接口：调用者传入已成功的 ReadingView 元组 `acquired`。失败返回 C0 ReadFailure：empty、unavailable、capacity、invalid_action 或 integrity/version_mismatch，没有 ReadingView，也不推进序号。replay 另明确拒绝 owner 或版本差异。真实重复读取的 record_ids/ReadingView/输出哈希一致；独立实际耗时不要求逐字节相同。

原生 tokenizer 只读取固定的 tokenizer/config/template，实际 token ID 已复现 A0 全部 100 请求。reading.tokens 是真实正文 token 数；ReadSuccess.input_tokens_after 取完整 chat-template 提示实测值与正文加法账中较大者，确保上下文容量不足时整条拒绝，不截断、不偷偷换低排名资源。READ_RESULTS 同时保存实际完整提示 token 和保守计账。B5 核心现有 input_tokens 是正文加法账，不能冒充完整 G 请求长度；完整原生容量由 read 单独检查，A6 仍需把正式请求包装统一绑定。

B5 接口无需改业务模块；测试 `test_actual_b5_can_use_real_read_without_business_changes` 已实际运行。回调模式：

```python
from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv, TerminalIdentity, TerminalTable
state_box = {}
def read_for_b5(head):
    return reader.read(head, acquired=env.readings(state_box['state']))
env = C0FiniteHeadEnv(
    prefix=prefix, history_sessions=prefix.cutoff_rank,
    availability=reader.availability(), read=read_for_b5,
    identity=TerminalIdentity(**reader.identity),
    table=TerminalTable({}, table_id='pending_real_generation'),
    prefix_tokens=reader.base_tokens)
state_box['state'] = env.reset()
state_box['state'], _, _, _ = env.step(state_box['state'], 'GET_ME')
key = env.terminal_key(state_box['state'])
# env.step(..., 'STOP') 在缺少真实终点输出时按 B5 原接口抛 PendingTerminal。
```

B1 来源用 `registry.visible(prefix)` 的严格过去会话和 `prefix.visible()` 当前原话，原始 turn idx 映射保存在 Entry。`registry.entry` 等私有原始查找器用于来源核验，不能绕过 prefix 可见性门。旧方法/案例 repair/quarantine、325 个旧 MP 排除说明及全部旧→新 ID 映射保存在 migration.jsonl。没有确认关系传播或语义验证等级升级。

正式 B1/B2 的依赖放行仍须 C0 正式冻结、新工作分支/PR CI 与集成验收。本地真实来源/读取与 B5 回放已可复现，不等于任务已标 completed。
