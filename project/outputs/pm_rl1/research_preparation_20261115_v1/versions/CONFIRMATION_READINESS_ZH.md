# 英文自然支持与记忆确认材料可行性（metadata 快查）

**当前可以继续开发，但尚不能承诺已有一套未暴露的英文自然支持记忆确认集。** 本次仅检查已有来源/分组/暴露 metadata 与报告，不读 test 正文或 gold，不完成全部历史分支逐条曝光连接。JSON 中未核定数量记为 `null / PENDING`，不把未知写成零可用。

| 材料 | 可确认的开发量/现有分配 | 确认集可用量 | 已知限制 |
|---|---|---|---|
| EvoEmo | 18 构造 owners、401 sessions；train 12 owners/96 prefixes，dev 3/18；当前开发共 15 owners/114 prefixes | 原 test 为 3 owners/48 prefixes；**未暴露确认量 pending** | test 的 p14、p7 共 32 prefixes 已在旧完整历史人评材料中曝光；剩余 p4 的 16 条不能据此称未暴露，3 个 test owners 均有旧 QA/Summary 参照链接 |
| ESC-Eval 英文外源角色 | 全部 331 卡，158 ESConv；外源 173 卡，其中既有冻结 calibration 52、confirmatory 121 | **仍可称未暴露的量 pending**；121 是历史分配量 | Claude 报告至少用过 12 张卡；尚未把具体卡键与 52/121 及其他开发登记完整连接，不能计算 121−12 得到剩余量 |
| AnnoMI 候选 | 上轮作者来源审计记录 133 个高/低质量 MI 示范；本准备包已接纳开发条目 0；全项目接纳数未穷尽核定 | 本准备包已接纳确认条目 0；来源核验与未暴露量 pending | 尚无本轮可绑定的本地导入/分组 manifest；只检查了两个常用外源目录顶层，不能声称全盘绝对不存在 |

EvoEmo 的直接依据是 `source_and_capacity_20260928_v1/source_exposure_v2.json`：状态明确为 `SOURCE_GROUPED_DEVELOPMENT_ROSTER_NOT_UNTOUCHED_TEST`，允许的措辞是“未用于新参数优化、披露既往研究暴露”，禁止“sealed, researcher-unseen confirmatory test”。train/dev 不妨碍继续开发；旧 test 可保留其原分组用于限定范围评估，但不能变成新的独立确认。p13 与 p18 共享 `esc1198`，已有隔离分支；语义改写/事实家族仍未穷尽核验。

ESC 外源 173 卡的来源为 EPITOME 5、ExTES 70、MHP 73、Psych 25。52/121 来自正式 frozen assignment，不采用早期 small24 的可行性方案。它能支持不同来源的模拟交互/迁移检验，**没有为记忆模块补上同一人物的真实严格过去多会话历史**。角色卡完整秘密信息仍只给模拟 seeker。

AnnoMI 当前能补的是方法行为与反例。它不自动提供同 owner 纵向记忆，也不保证方法对当前 G 有额外收益。应先绑定下载版本、按原始示范/视频来源分组和任务适用性，再谈开发/确认划分。这里的“未暴露”仅涉及项目开发用途，不能保证语言模型预训练从未见过公开材料。

下一步只需做三件有明确终点的事：保留 EvoEmo 已知暴露措辞；对 ESC 的卡键/角色 hash 做历史与 Claude 分支曝光连接；若论文必须声称独立英文自然支持记忆确认，就另找合法纵向来源家族，或明确收窄为当前构造人物上的分组评估。不要靠多切前缀、AnnoMI 方法卡或 ESC-Role 角色卡假装补足这一缺口。
