# Snapshot hash 交换规范：pmrl1v3-json-1 / asof-sidecar-1

这是已有 #15 快照格式的明确化，不修改原 65 快照或其身份。新导出沿用该编码；writer 身份独立。B 不需要导入 A 的任何代码。

## 规范

1. 解析完整 snapshot JSON，拒绝重复对象键、NaN、Infinity 和非 JSON 值。只删除顶层 `snapshot_sha`；不删除 qualification、writer、time_basis、source_frontier_sha256 或其他字段。嵌套同名字段如有仍保留。
2. 对象键递归按 Unicode 码点升序排序；实际格式键全为 ASCII。dataclass 是字段对象，tuple 是数组。数组顺序**不排序**，null/false/空字符串不可互换。输出为紧凑 JSON，分隔符为 `,` 和 `:`，无缩进、BOM、结尾换行。
3. UTF-8；非 ASCII 字符直接编码，不能做 NFC/NFD 等 Unicode 归一化。不转义 `/`；引号、反斜线及控制字符按 JSON/Python `json.dumps` 规则转义。源跨度 start/end 是 Python Unicode 码点偏移，不是 UTF-8 字节或 UTF-16 code unit 偏移。
4. 本批快照数值均为整数；不存在浮点数。独立实现只需处理有限安全整数、string、bool、null、array、object；不宣称 RFC 8785/JCS 兼容。
5. 对上述字节做 SHA-256，输出 64 位小写 hex。此值应等于文件中的 `snapshot_sha`、BINDINGS 对应值和另一 horizon 的值。文件本身含结尾换行，其 file SHA 与 snapshot object SHA 是不同对象。

最小独立实现（Python 标准库）：

```python
import json, hashlib
def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result
snapshot = json.load(open("snapshot.json", encoding="utf-8"),
                     object_pairs_hook=unique)
payload = {key: value for key, value in snapshot.items()
           if key != "snapshot_sha"}
encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
assert hashlib.sha256(encoded).hexdigest() == snapshot["snapshot_sha"]
```

`HASH_TEST_VECTORS.json` 给出对象、规范文本、UTF-8 hex 和 hash，包括组合字符/分解字符保留不同的情况。完整检查器为 `project/scripts/rl1v3/check_e1_exports_standalone.py`，只有标准库依赖，并额外重查真实 RAW/frontier/跨度/owner/payload；A 提供该脚本不是 B 独立审核完成。

## 身份闭包

- `source_frontier_sha256` 是整个 `source_frontier` 的同规则 object hash，不剔除字段。
- 会话局部 `source_sha256` 只含 owner_id、session_id、dataset、chronological_rank、date、family_id、ancestor_family_ids、license、complete、transcript_sha256。它不含全文件 raw_sha256、全 registry hash 或 fold；后者只进入输入审计。
- ledger `record_id` 为 `asof-record:` 加同规则 object hash，计算时只把该行 record_id 替为字符串 `pending`，其他字段保留。
- snapshot 的 ledger_prefix / views 按 `(reported_at.session_rank, record_id)` 排列，frontier 按 source rank 排列，所有数组原顺序均参与 hash。重排后再 hash 不是同一快照。
- dual horizon 的 horizon 元数据放在 BINDINGS 和各自完整 ledger 文件，不写入历史 snapshot。因此追加未来会话不能更名过去 snapshot。改变真实过去原话则应改变 transcript/source/ledger/snapshot 身份。
- RS 是另行预装外部版本，使用实验准备日期；不拿它与个人会话 rank 比大小，也不声称它在历史真实部署时已经安装。

## 复跑

```bash
python project/scripts/rl1v3/check_e1_exports_standalone.py \
  --bundle project/outputs/pm_rl1/v3/qualification_e1_20261118/cpu_v3 \
  --sources project/outputs/pm_rl1/v3/A1_preparation/final/registry/sources.jsonl \
  --out /new/path/independent-check.json
```

这个规范也可用于独立重算旧 #15 的 65 份 snapshot，但不能把本轮新 writer 的快照替换为旧身份。
