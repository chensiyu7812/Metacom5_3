# 集成协调：#10–#18 与 MS-RAW/PP1（只读）

日期：2026-11-19（日本时间）。角色：integration coordinator。A 同时是 #10/#12/#13/#15/#18 的作者，故本报告不是这些 PR 的独立批准。WS-A 材料准备另见主报告。没有合并、retarget、改 main/integration/H0/EXECUTION_STATE 或冻结记录。

当前真实 integration 为 `320a33d1d871199d171f998300ce926b341ca1a8`。`PR_CI_SNAPSHOT.json` 逐项保留 GitHub 当前 HEAD、base、Draft、workflow 和实际 job steps。九个 PR 均 OPEN、未合并；各自 HEAD CI success，integration-base/outcome-lock 步骤均 success。#17 当前 HEAD 是 `3dafb2aa`，不能用其描述中的 `8541b951` 冒充最新 HEAD。

| PR | 当前 HEAD | base / 真实祖先依赖 | 本轮推荐 |
|---|---|---|---|
| #10 G0e | `73fdb12f` | integration | MS 运行链优先；由 integration owner 经受保护流程处理 |
| #11 B S3 | `dd33e131` | integration；运行上依赖 #10 | HOLD：#10 真合入后，B 在真实 integration 重跑 G0e 附录、payload 与 pending STOP 绑定 |
| #12 G0e 补充 | `8ba20d21` | #10 | HOLD：上游处理后 retarget integration，联合审查加载守卫、请求和缓存 |
| #13 四资源审查 | `ea2f5bde` | integration | 可独立审阅入库；不作为 MS-RAW 试点材料前置 |
| #14 V3.2 方案 | `f26e7cf8` | integration | 文档候选另行决定；A 不登记采用或 H0 |
| #15 as-of | `b63635f3` | integration | B 按最终 A 对象补闭合 hash/双 horizon/可见性后再处理 |
| #16 B as-of/env | `a9cf0cca` | #11 | HOLD：R1–R5 未修复；不得因 CI 通过直接合入 |
| #17 B Q0/QH/F、PP1 | `3dafb2aa` | #16（及 #11） | 协议可按固定 SHA 跨线审阅；合入须等父链，采用/执行仍需研究者决定 |
| #18 A 8-owner | `0a91ff33` | #15 | B 独立回执 pending；不能以本轮 A checker 批准 |

实际祖先边为 #10→#12、#11→#16→#17、#15→#18。各 PR 相对自身 base 的增量分别为 61/80/67/12/3/241/73/45/113 个新增路径，两两没有重叠。详见 `DEPENDENCY_AUDIT.json`。这是只读差异检查，没有组合运行，也没有创建 merge commit；无文本冲突不代表接口可互换。

推荐的处理顺序：

1. **G0e 链**：#10 → B 同步真实 integration 并重验 → #11 → #12。每个 HEAD/base 变化后重跑对应检查；#12 不得合入 A 的 #10 工作分支。
2. **MS 证据链**：原 B 验收 #18 固定 SHA 的 8 个前缀、16 hash/8 horizon、source/frontier/owner/family/可见载荷 → #15 → #18 → 本次 MS/PP1 准备 PR。子 PR 由 integration owner 在上游处理后 retarget 并核对增量。本链可与 G0e 链并行审查。
3. **在线环境链**：B 修复并独立说明 R1–R5 → 在真实上游上联合复跑 → #16 → #17。本次静态 PP1 不调用该在线环境，但不因此撤销其合入阻塞。#17 固定版本的 PP1 协议可先接受科研审阅，不要求先合入有问题的环境。
4. #13/#14 是独立文档段；其研究采用与 MS 运行许可分别处理。研究者本轮明确收窄优先级，MP/ME/RS/SUM 的未完成项不进入 OFF/RET-MS PP1 前置条件。

## 当前接口风险与 PP1 影响

R1–R5 的反例证据保留在 `qualification_e1_20261118/coordinator/INTERFACE_COUNTEREXAMPLES.json`，A/B 对应生产代码 HEAD 没有变化；本轮不重复把旧反例称为新测试，也没有代改 B 代码。

| 风险 | 当前状态 | 静态 PP1 与后续在线使用的区别 |
|---|---|---|
| R1：B source_id 间接依赖整个 RAW 文件 hash | 未闭合 | #18 的局部 snapshot/hash 保持；PP1 为保留原输入仍引用旧 TerminalKey/bank/index，因此**不声称 PP1 旧请求键具备未来追加不变性**。不可迁移旧 reward/result。在线新 binding 仍须改为经 A/B 同意的局部来源身份。 |
| R2：BoundEpisode 入口未做完整 owner/cutoff/frontier 验证 | 未闭合 | 本次只准备精确静态载荷、逐项核对来源。未来 GPU executor 必须在加载前消费已验清单，不能调用未经修复的 BoundEpisode 当资格证明。 |
| R3：STOP 后仍可 GET | 未闭合 | 静态 OFF 为 `[STOP]`，RET 为 `[GET_MS, STOP]`，清单没有后续动作；CPU `ProcedureLog` 只验证拟议执行日志的拒绝规则，**不宣称修好了 B 环境**。 |
| R4：ReplayCache 非幂等/别名可修改 | 未闭合 | PP1 申请要求新的 write-once 日志空间、START 先落盘、同请求最多一次、未知完成状态停止；没有旧缓存命中。CPU 状态机不等于持久 GPU 缓存已经实现验收。 |
| R5：RELATION 交换 KeyError | 未闭合 | 8 个 RAW 读取不消费 RELATION，不是该静态试点的前置；通用 as-of 适配器合入前仍需 B 修复。 |

G0e 是工程身份，不是已合格 G0。A0 加载/吞吐尚无获准实测；vLLM 不能替代固定 HF 后端。正式 PP1 执行前，还需受保护 integration 上的最终 executor/code SHA、加载守卫、B 回执、研究者绑定清单的授权。此报告只是合并和执行准备建议，不能作为绕过保护流程的许可。
