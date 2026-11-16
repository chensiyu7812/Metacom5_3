# 第一轮整理记录（历史）

本目录记录第一轮136项归档及当时60个顶层兼容链接。第二轮已将实体移入总归档，并收起这些链接；这里的路径/验证结果是当时快照。

**当前目录、校验与恢复请使用[第二轮完整归档说明](/home/tokkio/成果归档/整理记录/20261022_完整归档/README.md)。** 原记录、哈希、原README与Git快照保留。第一轮迁移/验证脚本已加提示，避免误操作新布局。

# 整理记录与回退

本轮已完成136项归档、60项HOME兼容链接及19个分类导航链接，减少76个原HOME条目。4,484个归档文件逐字节/权限/时间戳校验通过；原有2,068个受保护文件中仅总README因本轮导航重写而变化，原全文已备份。实验、合同、分数、账本和HEAD保留。

- `final_verification.json`：最后验证结论；`verify_workspace.py`可只读复核。
- `路径迁移清单.csv`、`moves.json`：原路径、新位置及兼容链接。
- `content_before.json`：每个归档文件的SHA256、大小、权限、mtime。
- `HOME顶层逐项清单.csv`：当前HOME逐项归属；隐藏项只登记名称。
- `主仓库逐文件目录.csv`、`主仓库目录统计.csv`：允许范围内28,491个文件的基线元数据；新增导航在基线之后写入。
- `inventory_exclusions.json`：缓存、Git、临时测试及弃用数据等排除边界。
- `ZIP与解压目录对照.json`：49包中39同内容、2有后补文件、8无相邻同名解压目录，均未删除。
- `研究依据文件哈希.csv`：73个被引用研究/代码/导航文件的当前快照。
- `git_before.json`、`git_before.patch`、`protected_files_before.json`：整理前状态与改动保全。
- `repository_README.before.md`、`HOME_CURRENT_ENTRY.before.md`：两个入口的旧正文。
- `git_info_exclude.before`、`git_info_exclude.after`：只排除本地pytest临时目录的变化。
- `archived_link_review.json`：检查1,039条归档链接，修复7处本次迁移造成的失效，原正文未改。

检查回退：`python organize_workspace.py rollback`；确认检查结果后执行：`python organize_workspace.py rollback --execute`。该操作仅将136项恢复原HOME位置，不删除新导航/记录，不自动恢复README和Git本地排除文件。遇文件变化或原路径占用即拒绝覆盖。此前只执行了检查，没有回退归档。

本目录包含本地路径、原始文件登记和用户资料的快照，保持在本机。当前统一入口是`/home/tokkio/PM-RL1/README.md`。
