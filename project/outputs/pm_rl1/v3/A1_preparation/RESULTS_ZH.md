# A1 来源注册库准备结果（C0 冻结依赖未解除）

状态：独立代码、真实产物及 16 项 CPU 测试已通过；**不宣布 A1 completed**。基于 integration `d0bde000` 的 detached worktree 准备，C0 当前未正式冻结。未修改全局状态、B 代码、共享契约或 PR #5。

`source_registry.build(root)` 生成 1276 个来源：401 个个人完整 RAW（18 owner）及 875 个 ESConv train 会话。1300 个 ESConv 中按 family 先排除 84 个重叠、再排除 341 个非 train。`esconv:esconv_1198` 保留 p13/p18 两个 owner 关联及共同 family/折，不把共享来源合并成跨 owner 可读历史。

固定入口为 `rl1v3.sources.source_registry.{build,save,load}`。SourceSession 使用 C0 0.2.0 原契约；Entry 为仅供执行器使用的附加来源登记，保留旧 turn idx→ordinal、内容/文件 SHA、reported_at、ready_at、许可/质量/风险与曝光状态。`Registry.prefix` 重建的全部 4119 个 prefix_id 与固定 B0 普查逐条一致。`visible` 对严格过去、owner、family、日期和版本状态先过滤。当前切点后的正文不进入 VisiblePrefix。

只读取已审计的小文件并核验原 SHA，不重扫模型权重或全部 64GB。即使已净化 runtime 输入仍含 question_groups/summaries/subsequent_topics，新来源仅白名单投影 owner→sessions→turns，未复制这些评价字段。ESConv 只取 dialog 的角色与原话，排除 situation、survey_score 和 annotation。

时间规则明确区分：个人 reported_at 为来源日期/rank；ready_at=r+1 是可比较的**逻辑会话结束重放边界**，不是实测 writer 完成时间；未虚构事件有效期。ESConv 未提供历史日期，其 reported_at/ready_at 保持 null，以 `preinstalled_external_snapshot` 和 registry 版本绑定可用性，不比较外部 rank 与个人 rank。后续真实在线写入须用独立版本记录实际 ready_at。

版本：不可变目录与内容身份；`changes` 给出快照 ADD/UPDATE/INVALIDATE/NOOP。UPDATE 只表示来源版本变化，不宣称事实改变。带精确证据的 `invalidate` 产生新 registry，按系统获知时间生效，旧快照不变、过去前缀不受未来更正污染。

ESConv 上游注明仅供学术研究，见 https://github.com/thu-coai/Emotional-Support-Conversation/blob/main/README.md 。EvoEmo 许可未补作新授权，保留既有研究者允许的研究资产复用范围及 unresolved 状态；无部署许可推断。两者不构成未曝光独立测试来源。

运行：`PYTHONPATH=project/src python project/scripts/rl1v3/a1_build_source_registry.py --out /tmp/source-registry-replay`；产物见 `final/registry/`，输入 SHA、版本和拒绝逐项记录于 registry.json。16 项测试覆盖完整 4119 前缀、原文/角色/编号、跨 owner/时间/family/折篡改、不可覆盖、版本更新/失效及无特权字段；8.38 秒、零 skip/xfail。没有模型/GPU/生成/训练/付费调用。

当前 source 版本：`sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02`。下一项是独立 A1b 准备；正式交付与新工作分支/PR 等待 integration C0 冻结，不以准备接口冒充完成。
