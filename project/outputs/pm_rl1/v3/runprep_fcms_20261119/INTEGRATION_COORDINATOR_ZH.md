# Integration coordinator 只读记录

此文属于集成协调角色；WS-A 作者身份的工程自检在主报告，不作为自己 PR 的独立批准。没有创建 merge commit、retarget 父 PR、修改 main/integration、H0、EXECUTION_STATE 或冻结记录。

PR_CI_SNAPSHOT.json 是本轮 GitHub 当前 HEAD/base、workflow 与实际 job steps 的只读快照。#10–#20 全部 OPEN、未合并；各自 HEAD workflow success，integration-base/outcome-lock 步骤实际 success。这不是通用接口已合格或全仓 tests/ 无失败的证明。

| PR | HEAD | 真实祖先链 / 推荐 |
|---|---|---|
| #10 | 73fdb12f | integration；优先由 integration owner 走正式集成流程，或研究者书面固定该身份仅供受限运行 |
| #11 | dd33e131 | integration；运行上依赖 G0e，需 #10 处理后联合验证 |
| #12 | 8ba20d21 | #10 的子 PR；检查加载、缓存、绑定；不能把它 merge 到 A 的 #10 工作分支当集成 |
| #13 | ea2f5bde | integration；资源审查材料可独立审阅，不是 MS-RAW 试点前置 |
| #14 | f26e7cf8 | integration；研究方案候选，采用与代码入库分开 |
| #15 | b63635f3 | integration；as-of 原型，先处理本链父节点 |
| #16 | a9cf0cca | #11；R1–R5 未闭合，在线环境 HOLD |
| #17 | 3dafb2aa | #16；协议按固定 SHA 可先研究审阅，不能掩盖父链问题 |
| #18 | 0a91ff33 | #15；B 已机械 PASS_WITH_NOTES，语义与许可不签收 |
| #19 | 4ac9ab3d | #18；B 已独立验收 16 固定输入，不得改该 HEAD 以免使回执失效 |
| #20（B 补充） | 4624600d | #17；PP1 停止规则已对齐，QH 已构建但人工/协议冻结仍待办 |
| 本轮 A Draft | 代码 575011b4，交付 HEAD 见 PR | #19；新增执行器与 FC-MS 候选，与旧输入相隔离；新内容 B 审核 pending |

明确推荐的集成顺序：

1. G0e 最小链：integration owner 优先审 #10；若正式集成，B 针对真实 integration 重跑 G0e payload/STOP 附录，再处理 #11、#12 的相应增量。若选择研究者固定 #10 身份路径，则所有 PR 仍不合并，受限作业依然单独签署与验收。
2. MS 证据链：#15 → #18 → #19 → 本轮 A Draft。B 已完成 #18/#19 固定 HEAD 的机械检查，原先“尚无 B 回执”的阻塞关闭；不能把旧回执扩展成新执行器/renderer 的批准。每个父节点处理后由 integration owner 调整子 PR base、重验增量与联合接口。
3. 在线环境链：修复 R1–R5、独立审阅并联合复跑后再 #16 → #17 → #20。#17/#20 的版本化科研方案可单独讨论采用，不要求先合入未修的在线环境。#13/#14 独立，不拖延 MS 最小路径。

## 保留风险与静态 PP1 边界

- R1：B 来源身份含整份 RAW 文件 hash；不能宣称旧 TerminalKey 具备未来追加不变性。#18 snapshot 的双 horizon 证据成立于其独立规范；旧 key/result/reward 不迁移。
- R2：BoundEpisode 入口 owner/cutoff/frontier 验证不完整；本次执行前消费固定 #19 check_bundle，不把该入口用作合法性证明。
- R3：在线 STOP 后还能 GET；本次只有固定的 OFF/RET 载荷列表，无在线动作扩展。没有改变 Step-1 语义，也没宣称修好 B。
- R4：旧 ReplayCache 的可变别名/非幂等风险未修；新作业用独立、逐次持久 START、一次授权 claim、唯一目录，不读旧输出缓存。CPU 故障测试已检验新机制，真实 GPU 子进程尚未获准测试。
- R5：RELATION 交换 KeyError；本轮 RAW-only 不消费关系链，不解除通用集成阻塞。

#20 最新完整 CI：44361073158，V3 667 passed，public 2432 passed / 63 历史 skips / 1 GPU deselected；额外全仓对照仍有 99 旧失败，B 已证明同环境失败集合不变。此处保留其适用范围，不把绿色 public CI 写成全仓无失败。

没有最终合并授权。integration owner 还需回复 G0e 路径及最终执行器验收；研究者决定身份固定、A0/PP1 两项运行、协议/人员/许可。新 renderer/DP 工具交原 WS-B 复核，不安排 A 的另一个代理冒充 B。
