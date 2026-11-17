# WS-B 正式 integration 验收：B5 回放 v2、A1/B1 cross_check、NeedCard v2 CPU 预检

- 证据等级：engineering_only。本次运行包括：
  - 只用 CPU；
  - 读取 tokenizer、config 和模板文件；
  - 模型、GPU、付费调用都是 0；
  - 不能证明资源相关性或自然情感支持收益。
- 目录：`integration_acceptance_320a33d1/`，包含三个运行的原始输出、日志、收据、`ACCEPTANCE.json` 和 `MANIFEST.json`。

## 1. 绑定

| 项 | 值 |
|---|---|
| 运行 HEAD | `320a33d1d871199d171f998300ce926b341ca1a8`（PR #8 和 PR #9 依次合入后的 integration 末端） |
| PR #8 合入 | `b591863e`（集成负责人） |
| PR #9 合入 | `16644abb`（集成负责人）；从 `16644abb` 到 `320a33d1`，src、scripts、configs、tests 都没有差异 |
| 运行方式 | 三个脚本都是 integration 上的原样版本，只加 `--out`；运行时跟踪的文件没有任何改动，退出码都是 0 |
| 验收提交 | `05b0e0b1`，这是本分支的第一个提交，早于任何代码改动 |

本次没有使用任何旧 PR CI 或集成前的结果来代替；集成前结果只作比对。

## 2. 结果

| 目标 | 结果 |
|---|---|
| B5 状态 | `formal_on_integration`（`a_integrated` 为 true） |
| 24 个前缀 | **24/24 通过** |
| 可达终点 | **360**（21 个前缀各 16 个，3 个各 8 个；那 3 个是 MP 无合法候选） |
| 合法读取顺序 | **1,413**（21 × 65 + 3 × 16；每个前缀的数量都等于 Σ C(k,j)·j!） |
| 真实动态容量 | 容量压力 24/24 通过；被拒绝的读取不推进状态（24/24）；静态掩码与动态掩码分歧为 0 |
| ready_at 边界 | 21 条 `ready_at == cutoff` 的记录判为合法 |
| 版本身份 | sources `c6ad9b15…`、bank `02d0a4b1…`、index `227cca58…`、renderer `e7678cc1…`、Gemma tokenizer `79ff7ef6…` |
| pending 语义 | 所有 STOP 都保持 pending，没有填任何奖励；只有 OFF 时只有 OFF 有奖励 |
| 重复回放 | 第二轮独立从磁盘加载，24/24 完全相同 |
| A1/B1 cross_check | 401 个会话、4,119 个前缀，**内容零差异**；前缀差异和覆盖差异都为 0；85 条 `excluded_for_overlap` 与 B0 规则一致；4 个元数据标签字段按设计不同 |
| NeedCard 输入 | **20/20 ready**；3,739–27,009 token，合计 277,880；没有截断；writer 调用 0 次 |

## 3. 比对

| 比较对象 | 结果 |
|---|---|
| 集成负责人在 `16644abb` 上的验收运行 | B5 的 24 份逐前缀报告在 17 个字段上完全相同；cross_check 与预检摘要除 code_head 和耗时外完全相同；预检输入和类别目录逐字节相同 |
| WS-B 在集成前 `173bed23` 上的运行 | 24 份逐前缀报告完全相同；摘要只有三个字段不同（status、a_integrated、cross_port_comparison），差异是预期的 |
