# 原预选 T01/T03 读后状态：实际 CPU 恢复及 EXPAND 可达性

本轮从 `c40b90c99cb991cf1c2793ffbe9927a0011885ab` 推进，只恢复上一轮预选的两条 ToolAgent 首次 SEARCH 后状态。未改题、改排序、选新案例或读取 gold 来选择展开对象；原 DR3 及历史证据不变。没有加载模型权重或启动 GPU/API/训练。

## 恢复的实际边界

读取 `decisions/exact-final-v1` 和核验过的原事件，沿原任务、source registry、严格 past 合法池、原 nonce、原 SEARCH query 重放至指定事件。两状态均通过：原 state SHA、完整 observation 字节及 SHA、原 G payload SHA、native token 数。另冻结并核对完整 snapshot，包括 handles、last_hits、已读内容、允许 query 词、expanded 集合、访问数、累计 token、done/budget 标志。

仅相同 state hash 不够：冻结旧 `state_hash()` 没有编码 `last_hits`，而其顺序属于真实观察。新恢复薄层以完整 trace + observation + snapshot 比较补足核对；没有修改旧状态哈希或旧记录。原内容按 hash key 排序，span 和 parent 用不同内容 key，故展开时保留原 span；这里不做去重、重排或压缩。

T01 恢复后的 G 输入 355 tokens、工具累计 123 tokens，T03 为 356 与 117。两状态均已用 1 次获取，剩 3 次；有 2 个实际可见 hit，允许 STOP/SEARCH/EXPAND。源合法性来自原 Prefix/As-of 绑定，不以主题相关性代替合法性。

## 全部当时可见 EXPAND 候选

每个候选从独立恢复的同一状态执行实际 CPU EXPAND；没有在一个候选展开后继续测试另一个。这里的“新增源话语”按原 owner/session/turn/quote 来源身份去重，是源覆盖量，不是有用事实数或任务得分。

| 任务 | 原观察排名 | parent 话语数 | 新增唯一源话语 | 重含已读话语 | 新增工具 token | 展开后 G token | 展开后剩余工具 token | 剩余获取 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T01 | 1，固定选中 | 24 | 23 | 1 | 594 | 1034 | 3379 | 2 |
| T01 | 2 | 23 | 22 | 1 | 753 | 1201 | 3220 | 2 |
| T03 | 1，固定选中 | 24 | 23 | 1 | 647 | 1092 | 3332 | 2 |
| T03 | 2 | 26 | 25 | 1 | 593 | 1038 | 3386 | 2 |

4/4 候选均通过原 source 合法性、动作与 token/context 预算。各新增一个 parent 内容块；parent 包含此前已读 span，原 G 同时接收两者，因此“新增完整块”和“新增唯一源话语”不同。T03 的第二候选话语更多、token 更少，但仍严格选第一排名；没有按 gold、覆盖增量、成本或预期收益改选。

选择规则是原观察最高排名合法 hit EXPAND 后 STOP；若该 hit 不能安全执行，薄层会停止为 not-ready，不换成另一候选追求正结果。本轮两个第一排名均可执行。其他合法 SEARCH 的 query 空间没有枚举，也不把本包当作所有继续动作的最优搜索。

## 选择冻结后的独立 evaluation-side 供证核查

另一源审工作线在 rank-1 选择及 payload 冻结后，才打开原 EvalSpec 对四个候选核对必要原子引用群。结果单独保存在 evaluation side，没有进入 runtime、检索或选择函数；候选排序和 4 份 payload 均未改变。这里核的是原引用群在实际输入的完整交付，不是 Generator 正确回答或必要信息的穷尽判定。

| 任务 | 候选排名 | 必需引用群 | 原状态已完整供给 | 展开后完整供给 | 新增群 | 仍未完整供给 |
|---|---:|---:|---:|---:|---:|---:|
| T01 | 1，固定选中 | 3 | 1 | 2 | 1 | 1 |
| T01 | 2 | 3 | 1 | 1 | 0 | 2 |
| T03 | 1，固定选中 | 2 | 0 | 1 | 1 | 1 |
| T03 | 2 | 2 | 0 | 1 | 1 | 1 |

T03 两候选补齐的是不同引用群；没有因此追加第二次 EXPAND。本次两条已选分支各增加一个完整必要引用群，但都仍有一个群未完整供给，不能将“23 新源话语”解释成足够回答全部问题。两个实际请求中的完整 parent source refs 已逐条核对到实际 decoded input。任务成功保持 unknown，评价仍用旧合同。

## 实际 CPU 验证与局限

`package-v4` 完成 4 份真实源 payload 的恢复、原语执行和严格相等核对：T01/T03 各一份 STOP 与一份 rank-1 EXPAND→STOP。另用明确标注的 CPU transport fixture 走完新执行薄层，共 4 次本地 fixture 返回、0 次模型调用；fixture 文本不是模型回答，不进入研究质量或延迟结果。12 项专名 CPU 测试通过，覆盖完整观测与 snapshot 漂移、不可跳过 rank-1 拒绝、重复展开真实收费、四调用边界、失败无重试、旧授权不可转用、恢复后计时起点及真实 observer 时间差字段。

冻结包的 `CPU_CHECK_PUBLIC.json` 给出全部公开 token、源计数与身份；`RESTORED_STATES_PRIVATE.jsonl`、`EXPAND_CANDIDATES_PRIVATE.jsonl`、`REQUESTS_PRIVATE.jsonl` 与 CPU fixture 全事件留在私有根。没有公开 RAW、私人目标、gold 或完整回复。候选 task success 与 formal reward 全为空；合法可达和源增加并不保证 Generator 正确利用。

两份新 STOP payload 与旧 STOP 端点一致，可在未来仅核对质量稳定性。旧输出不能填充本次物理调用，旧时间不能填充新分支时间。本包尚无真实生成结果。
