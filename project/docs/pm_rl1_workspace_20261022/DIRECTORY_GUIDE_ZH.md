# HOME成果归档与当前目录

2026-10-22第二轮完整归档。本轮按研究者“成果和产物都做个归档”的补充要求，把实体移入`/home/tokkio/成果归档/`，并收起第一轮留在HOME顶层的60个历史兼容链接。第一轮只建立分类导航、保留大量旧入口的状态已经被本轮取代。

## 1. 唯一归档位置

```text
/home/tokkio/成果归档/
├── README.md
├── PM-RL1/                 全部PM-RL1交付、历史方案、人评、Paper-1前序资料
├── 旧PM项目/               PM v1主库及两个Git工作树
├── 论文图稿/               figure1、figure3、概念图、绘图工具检查
├── 审计与复核/             原audits及其报告、环境和审计记录
├── Tokkio部署资料/         原HOME散落YAML/JSON、Helm和cns-info
├── 工程测试产物/           主仓库旧pytest临时产物
├── 入口历史/               原PM_RL1_CURRENT_ENTRY_20261021.md
└── 整理记录/               本轮映射、校验、Git状态与路径恢复工具
```

[打开归档总目录](/home/tokkio/成果归档/README.md) · [所有原路径到新位置](/home/tokkio/成果归档/整理记录/20261022_完整归档/全部原路径映射.csv)。

HOME只保留一个`PM-RL1`快捷入口，指向归档中的PM-RL1工作区；`Metacom5_3`仍指向实际主仓库`/opt/tokkio-data0/tokkio_projects/Metacom5_3`。两者是少量日常入口，数十个阶段包旧名已不再铺在HOME。

## 2. 各类成果的新位置

| 原位置/类别 | 归档实体位置 | 处理 |
|---|---|---|
| 第一轮PM-RL1统一工作区 | `成果归档/PM-RL1/` | 整体迁入，HOME保留单一PM-RL1入口 |
| 原136项阶段包、ZIP、方案和标注 | `PM-RL1/02_阶段交付`、`03_历史方案与说明`、`04_人评原件`、`05_Paper-1前序资料` | 保持用途/日期分类及原名，未删除或合并 |
| `chensiyu78120818` | `旧PM项目/chensiyu78120818` | 旧PM v1主库，仍为pm-v1-frozen |
| `chensiyu78120818-table3` | `旧PM项目/chensiyu78120818-table3` | 用Git worktree move迁移；原未提交release_manifest和ZIP保留 |
| `chensiyu78120818-camera-ready-24state` | `旧PM项目/chensiyu78120818-camera-ready-24state` | 用Git worktree move迁移；主库迁移后repair指针 |
| `figure1`、`figure3`、`fig1_concept.png`、`excalidraw-check-20260908` | `论文图稿/`下同名项目 | 成稿、源文件和原环境一起保留 |
| `audits` | `审计与复核/audits` | 历史审计报告和复现环境完整保留 |
| `helm-values`、`helm-local-charts`、`cns-info`、根目录9个YAML/JSON文件 | `Tokkio部署资料/`下同名项目 | 原始字节、权限、时间戳保留，未读取凭据内容来修改配置 |
| 主仓库`pytest-of-tokkio` | `工程测试产物/Metacom5_3_pytest-of-tokkio` | 跨文件系统复制后逐文件核对，再移除旧副本；不是研究训练结果 |
| 原HOME“当前入口”文件 | `入口历史/` | 保存快照，日常使用统一入口 |

归档中的ZIP仍与解压目录一起保留。第一轮检查的49包中39个文件集合一致、2个解压目录含后补文件、8个没有相邻同名解压目录；不能全部视为可删除重复。

## 3. HOME剩余项目

现在HOME顶层只有21个可见项目：归档总目录、两个当前研究入口、模型/环境、RAG项目、凭据入口和系统标准目录。

`models`、`base_model`、`miniconda3`、`nltk_data`、`rag_project`、`new_rag`和`snap`保留原位；这些是运行资源或独立项目，未作为散落交付删除。`metacom5_3.env`、`tls.crt`、`tls.key`和隐藏用户配置也保留原位。没有移动其他用户的HOME。

## 4. 当前研究仍怎样访问

- [研究全景](RESEARCH_OVERVIEW_ZH.md)：目的、方法、数据、方案、进度、结果与限制。
- [阶段证据时间线](EVIDENCE_TIMELINE_ZH.md)：区分准备、运行、技术STOP与已收口结果。
- [唯一主方案](../PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md)与[当前状态](../PM_RL1_CURRENT_STATUS.md)继续控制研究，归档不改变研究许可。
- [PM-RL1归档索引](/home/tokkio/成果归档/PM-RL1/00_归档文件索引.md)列出原136项。
- `PM-RL1/06_代码与原始实验`指向原主库、RL1源码/脚本/测试、执行合同与原始outputs。
- `PM-RL1/07_旧PM项目与图稿`的内部链接已改指归档后的实体。

主仓库`project/src/metacom_pm/rl1`、`scripts/rl1`、`tests/test_rl1_*`、数据、模型、原始`outputs/pm_rl1`、研究合同与预算账本没有迁移或改写。仅旧pytest临时目录归档。核心代码位置及作用仍见研究全景和源码；旧Paper-1与历史版本不因归档变成当前方法。

## 5. 旧绝对路径怎样处理

归档后的日常导航使用新位置。旧实验、历史manifest或环境脚本中可能写死原HOME路径；这些冻结记录保留原文，没有为了目录变化重写实验身份。第一轮的60个旧名兼容链接本轮主动收起。

需要重放依赖旧路径的历史代码时，可按需建立兼容路径：

```bash
python /home/tokkio/成果归档/整理记录/20261022_完整归档/archive_home.py enable-legacy
```

用完后收起：

```bash
python /home/tokkio/成果归档/整理记录/20261022_完整归档/archive_home.py disable-legacy
```

工具只建立或移除指向归档实体的链接；遇旧路径被新文件占用会拒绝覆盖。默认不启用，HOME保持整洁。旧虚拟环境的绝对shebang也可通过该方式恢复所需路径；未声称无需恢复路径即可原样执行所有历史环境。

## 6. 验证和保全

本轮迁移23个根项目（其中包含上一轮整个PM-RL1归档），核对21,710个普通文件、4,573,868,185逻辑字节，原内容/权限/时间戳在实体迁移时一致；改接52个内部符号链接，收起60个HOME链接。三个Git工作目录的HEAD、分支、已修改/未跟踪状态保持一致。

导航更新另有修改前备份与变更日志。原始研究产物不因导航调整而被改分、覆盖或删除；没有提交、推送或启动实验。第一轮验证/回退脚本已标为历史，不再作为当前目录布局的操作入口。

[本轮整理与恢复说明](/home/tokkio/成果归档/整理记录/20261022_完整归档/README.md)。第一轮完整清单和哈希仍保存在`成果归档/PM-RL1/90_整理记录/20261022`。
