# 本次上传范围与 pytest 问题（2026-09-30）

## 仓库检查

上传前远端研究分支为 `work/paper1-rq1-integration-20260816`，HEAD `ba6917069cc6257ca8e64729509ce0f27e3cdc9b`；main 是其祖先，研究分支领先 97 个提交，没有分叉。既有 PR #3 的状态为 CLEAN / MERGEABLE，最新 push 与 pull_request 检查均通过。因此，没有证据把近期 pytest 问题归因于 Git 合并冲突。

旧的 [2026-09-04 失败运行](https://github.com/chensiyu7812/Metacom5_3/actions/runs/33834389318)日志明确显示，`test_paper1_dg_official.py` 访问了 GitHub runner 不存在的 `project/outputs/vendor_es_memeval/data/evo_emo.json`，抛出 FileNotFoundError。这个旧问题后来已经修复，不能说这次才修好。

## 本次实际复现与修复

从当前提交创建独立 worktree，仅复制待上传的代码、文档、合同与测试，不复制本机 `outputs/`。对活跃 Paper-1 + 新 PM-RL1 CPU 测试进行检查，复现 **10 个失败、8 个 fixture 错误**。根因集中于：

1. 新测试读取被 `.gitignore` 排除的费用报告、来源修复 overlay 和执行器实验目录。
2. 执行器 fixture 依赖 author_pointer 内的本机绝对路径。
3. 官方 Summary 解析依赖 `json-repair==0.52.4`，但库只在本地 vendor 目录，未声明为可安装依赖。

对应修复：

- 把可公开的原始报价／准备统计提升到 `docs/reviews/20260918/`，保留内容与来源哈希；费用脚本在没有本地准备目录时读取同一公开快照。
- 将实际公开来源 overlay 作为受控 regression fixture，继续验证旧事实不复活、关系失效的时间边界、角色扮演原文保留及证据绑定。
- 用小型、确定性的单元测试记录替代对 90 条私人运行结果的 fixture 依赖，仍验证拒收、准入完整性及 engineering 不能冒充研究资格；这些记录不是训练数据。
- 将 `json-repair==0.52.4` 声明为依赖；保留已有 vendor 优先和路径约束，同时允许干净安装使用同版本包，并拒绝错误版本。官方评分算法、解析规则及缺失处理不变。
- CI 同时运行 `test_paper1_*.py` 和 `test_rl1_*.py`；继续运行集成校验与 outcome locks 检查。没有用 `continue-on-error`、新加跳过或删掉失败断言掩盖问题。

本地可复现命令位于根 README。CPU 检查不需要本地输出目录、模型权重、API 凭据或 GPU。历史废弃测试不属于当前活跃测试范围，不把全仓库所有年代的 test 混为同一研究合同。

本次修复后的完整本地结果：**1,148 passed，1 skipped，11 GPU deselected**，约 267 秒；32 项集成检查全部通过，outcome_calls 为 0；compileall、wheel 构建和 5 个公开 notebook 单元执行均通过。跳过的是已有的本地 Llama tokenizer 可用性模块，不是新增跳过。机器可读结果见 [publication_validation.json](reviews/20260930/publication_validation.json)。GitHub 会独立安装依赖并执行相同的活跃测试命令，其状态以 PR 对应提交的检查为准。

## 上传内容与身份

发布包含本轮原始方案、两轮用户提供的网页版建议原文、全部待上传研究代码／测试／合同／报告，以及 75 个明确选定的结果统计、特征表和可移植 notebook。14 个 PM-RL1 运行目录的 2,735 个本地产物用文件大小与 SHA256 登记，便于追溯。

模型权重、原始调用载荷、盲映射和完整人工表继续保存在本地。没有把这些目录直接强制加入 Git。网页上可审阅的结果在 [进展索引](PM_RL1_PROGRESS_INDEX_20260930_ZH.md)中逐项链接。

实验原始哈希保持原样；上传时新增的依赖声明、路径适配与测试修复不能被说成当时跑实验所用代码。公开快照 MANIFEST 明确区分原始 source_sha256 和发布后的 published_sha256；notebook 只改成读取已发布统计，5 个标准 Python 代码单元重新执行，没有新做模型实验。

原始待上传的 204 个文件已逐字节保存到提交 `23e205b5aec159618cc392bc5cbafe67949828e0`；后续发布与 CI 修复单独提交。因此，旧实验代码既能按文件 SHA256 核对，也能从 Git 历史取得。

这次上传不改变研究结论：自然支持 reward 仍未合格，正式自然支持 PPO 尚未启动；数据修复建议尚未冒充已完成修复。旧 Paper-1 的合同与结果身份继续保留。
