# #16 接口问题 R1–R5 的修复计划（WS-B 修复，WS-A 签收）

- **范围**：这些问题只阻塞 G-RWD（在线环境、BC/PPO、更正链）。它们**不会重新阻塞**静态的 PP1 和 FC-MS：后两者是“固定请求 → 生成 → 人评”，不经过 BoundEpisode、ReplayCache 或 RELATION 交换。
- **原则**：
  - 每一项先写失败测试，再修复；
  - 冻结的 #16 产物不改；
  - 修复以新版本发布（binding v2、env v2），旧版本只作为审计映射保留。
- **本轮状态**：只完成计划，没有改代码。以下工作量是 CPU 估计。

| 编号 | 问题（已确认） | 修复 | 先写的失败测试 | A 签收的内容 | 工作量 |
|---|---|---|---|---|---|
| R1 | binding 身份经 registry 的 source_id，间接依赖整个文件的 raw_sha256 | binding v2：frontier 身份改用 A 规范中的会话局部 `source_sha256`（10 个字段）；旧 binding 只作审计映射 | 改动无关会话的文件字节，binding 身份不得变化 | 字段集、哈希规范与 A 的 `SNAPSHOT_HASH_SPEC` 一致 | 0.5 天 |
| R2 | `BoundEpisode` 构造时没有调用完整验证 | 构造时调用完整验证，并绑定实际的 snapshot 与 port | 用错配的 snapshot 构造，必须失败 | 验证项清单 | 0.5 天 |
| R3 | STOP 之后 done 仍为 False，之后的 GET 依然成功 | STOP 把 done 置为 True；之后的 GET 返回带类型的 `after_stop` | 真实执行 STOP → GET 序列 | 与 C0 的 STOP 语义一致 | 0.25 天 |
| R4 | 同内容重试时缓存报错；get 返回内部对象，存在可变别名 | 同内容 put 幂等；put 和 get 都做深拷贝并冻结 | 同内容 put 两次；修改 get 的返回值后再次 get，内容不变 | 缓存键与 TerminalKey 的关系 | 0.25 天 |
| R5 | adapter 遇到 RELATION 记录时报 KeyError | 交换格式保留 RELATION/UPDATE、target、known/ready 与有效区间；未批准的关系不改变事实投影 | 带 RELATION 的合成 ledger：投影与没有关系时相同；批准后按规则变化 | 交换格式字段；批准状态的来源 | 1 天 |

**顺序**：R3、R4（小、独立）→ R2 → R1（需要 A 对齐哈希规范）→ R5（需要 A 的真实更正链样例）。

**完成标准**：

- 5 项的失败测试先红后绿；
- V3 严格套件 0 skip；
- A 在 PR 中签收；
- G-RWD 的 R4 项转为 PASS。

**时间**：可在研究者批准版本 A 后作为单独的 PR 进行，与 PP1、FC-MS 并行。
