# 仓库完整材料同步说明 2026-11-16

本次同步按研究者要求，将本地 Metacom5_3 的代码、方案、研究过程和实际结果交给网页版审阅。阅读入口是根目录 [README_FOR_REVIEW.md](../../README_FOR_REVIEW.md)。这次工作是材料同步，没有执行模型实验、重新训练或采用新的研究方案。

**同步前的差异。** GitHub 默认分支 `main` 为 `3c7e416a55aaca265fef63a39d9f101cde787f5b`；本地研究分支为 `work/paper1-rq1-integration-20260816`，HEAD 为 `982cf0bf9f9479dce276576cbd71612201f02004`。本地比远端同名研究分支多 32 个提交，比默认分支多 146 个提交。默认分支是本地 HEAD 的祖先，可以通过 fast-forward 同步并保留历史。

**实际覆盖以清单为准。** [FILES.jsonl](repository_sync_20261116/FILES.jsonl) 逐项记录项目文件路径、字节数、SHA256 与上传表示；[SUMMARY.json](repository_sync_20261116/SUMMARY.json) 汇总数量；[EXCLUSIONS.json](repository_sync_20261116/EXCLUSIONS.json) 说明例外。清单及验证记录自身不作递归哈希，最终版本由 Git 提交和树对象确定。

本次纳入：

- 原有和未同步的全部代码、测试、配置、数据合同、历史文档，以及 11 月 15—16 日新增的方案、资源规范、会话摘要设计和审阅材料。
- 原先被 `.gitignore` 排除的实验材料：实际输入和回复、评分、人评、运行配置、来源与曝光记录、统计、错误及等待记录、运行时源码快照、策略权重与特征文件。保留原路径，使文档中的证据链接可用。
- `/home/tokkio/成果归档/PM-RL1` 的项目材料。4,679 个普通文件中，4,369 个与仓库已有内容相同，通过 [ARCHIVE_FILES.jsonl](repository_sync_20261116/ARCHIVE_FILES.jsonl) 映射；310 个独有路径复制到 [archive](repository_sync_20261116/archive/)。不沿符号链接重复复制仓库，外部旧项目与图稿未混入当前项目。详细范围见 [ARCHIVE_SCOPE.json](repository_sync_20261116/ARCHIVE_SCOPE.json)。
- 研究者在本次会话提供的两份项目上下文原文，见 [SOURCE_MATERIALS.json](repository_sync_20261116/SOURCE_MATERIALS.json)。它们是讨论及审阅来源，其中的方案文字和终端记录不能自动当作已验证的实现结果。

**明确例外。** Git 内部对象、Python 缓存、测试缓存、安装元数据和本地环境不作为研究材料上传。发现的一份校准标签解密私钥保留本地，不上传其内容。文件名含 `PRIVATE` 的公开数据派生物、盲映射和已完成人评不会仅因名称被排除；本次公开后，不应再把这些历史材料称作未曝光的新确认集。

**唯一超限文件。** `project/outputs/pm_rl1/organized_initial_encoding_20261103_v2/FEATURES_PRIVATE.json` 为 106,360,300 字节，超过普通 GitHub 单文件限制。原文件保持不变；上传其同目录的 [FEATURES_PRIVATE.json.gz](../outputs/pm_rl1/organized_initial_encoding_20261103_v2/FEATURES_PRIVATE.json.gz) 无损副本。解压内容与原文件的 SHA256 相同，原始大小、哈希和压缩文件哈希见 [LARGE_FILES.json](repository_sync_20261116/LARGE_FILES.json)。克隆后如需运行依赖原文件名的脚本，可从仓库根目录执行：

```bash
gzip -dk project/outputs/pm_rl1/organized_initial_encoding_20261103_v2/FEATURES_PRIVATE.json.gz
```

其他原始研究文件按原字节上传，不改变既有实验身份。外部预训练模型安装目录不在本项目树内，没有复制进仓库；已在项目树内的训练产物包含在清单中。`.gitignore` 保持原来的默认保护；这次明确登记的历史快照单独加入 Git，不代表以后所有新运行输出都自动适合发布。

**给网页版的阅读顺序。**

1. [原始目标](PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md)、[当前状态](PM_RL1_CURRENT_STATUS.md)、[进度索引](PM_RL1_PROGRESS_INDEX_20260930_ZH.md)。
2. `project/src/metacom_pm/rl1/` 的当前环境、资源、反馈和学习实现；`project/src/metacom_pm/paper1/` 的共用数据、记忆编译及官方评价模块；相应阶段脚本和测试。
3. [自然支持历史价值实验](reviews/20261105/pm_rl1_history_necessity_human_review/RESULTS_ZH.md)、[QA 与资源视图结果](reviews/20261111/pm_rl1_typed_resources/RESULTS_ZH.md)及它们引用的原始输入、回复和判断。不要把 QA 事实正确率当作自然支持帮助性。
4. [研究审计](reviews/20261115/pm_rl1_research_audit_and_route/REPORT_ZH.md)、[资源准备结果](reviews/20261115/pm_rl1_resource_organization_and_execution/RESULTS_ZH.md)、[MS 摘要设计](reviews/20261116/pm_rl1_session_summary_design/DESIGN_ZH.md)。
5. 对照 [Codex 主方案](PM_RL1_MASTER_EXECUTION_PLAN_20261116_ZH.md)与 [Claude V2](PM_RL1_EXECUTION_PLAN_V2_20261116_ZH.md)，检查目标覆盖、反馈可靠性、动作范围、组合效应、基线输入、数据曝光、成本和执行依赖。

**现有状态冲突予以保留。** 部分入口写 V2 已取代原方案，但 V2 正文仍写待研究者确认，且状态表 `plan_adopted_by_researcher=false`。本次同步将这些原始材料一并交付审阅，没有将其解释为研究者已经采用 V2，也没有修改它们来消除分歧。目录中的旧计划、历史训练结果及失败实验同样保留各自日期和用途。

**验证边界。** 本次检查文件级覆盖、来源哈希、压缩还原、凭据模式及链接目标，不宣称逐行验证所有年代的代码，也不把上传完成当作新研究结果。验证记录见 [VALIDATION.json](repository_sync_20261116/VALIDATION.json)；自动测试运行状态应以相应 GitHub 提交的 Actions 为准。
