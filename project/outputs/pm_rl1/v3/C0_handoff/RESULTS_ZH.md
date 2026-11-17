# C0 跨线复审通过后的交接清理

B 的正式复审（`c6c6808ae018c098f04af72af9824e7433cfc065`，原文固定在 inputs）接受 R1–R6 和 N1–N8。C0 共享 contracts/io 和 Schema 保持 `8aab9f25` 的内容，未单方再改字段。

已处理 B 提出的合入事项：

1. A 的验收改名为 `project/tests/test_rl1v3_c0_a_acceptance.py`；`test_rl1v3_c0_wsb_acceptance.py` 的最终所有权和实现完全留给 B。删除复制的 B0 `census.py.txt`；A 只使用带 SHA 的 B0 普查数据、已登记 canonical hash 向量和实际原文，继续核验 4,119 个切点/前缀身份。旧副本只存在于历史 commit，未覆盖历史结果。
2. family 命名与 B0 完全一致：`esconv:esconv_XXXX` 和 `evoemo_owner:pN`。A1 实测 84 个 overlap family / esc1198 共享来源，不需要 B0 改 protocol 或重映射。
3. 在独立、detached 的临时工作树试合并 A 的清理后代码和 B `c6c6808a`，**无文件冲突**；不提交合并、不推送临时树、不改 integration。两线全部 `test_rl1v3_*` **278 passed / 0 failed / 0 skipped / 0 xfailed，17.66 秒**，包括 B 正式验收与 B5 C0 接入测试。A 自有 V3 测试 **202 passed**。CROSSLINE_INPUTS.json 固定输入 commit/tree，trial_merge.log/pytest XML 和日志可核对。

首次尝试用 `git merge-tree --write-tree` 返回 128，原因是本机 Git 2.34.1 不支持该选项（原错误在 merge_tree.log）。实际修复是独立 detached worktree + `merge --no-commit --no-ff` 的临时试合并；未把失败当成成功，也未动共享分支。

B 报告其试合并树全量 CPU 为 2,070 passed / 0 failed / 2 环境 skip；这是 B 的结果，不冒称为 A 运行。A 已提交的 C0 全量是 2,018 passed / 0 failed / 1 tokenizer 环境 skip / 11 GPU deselected（e499b1ef）；A1 新增 17 项通过。契约提交 `8aab9f25` 的 GitHub CI run `44046041069` 已 success。

**C0 内容已获 B 复审通过，可提交集成冻结；尚未正式冻结。** 最后一项由集成负责人执行：合入真实 integration 提交并在该提交上重跑 CI。各分支和临时树的绿灯不能替代该步骤。A 不修改全局 EXECUTION_STATE/H0，不合并 PR #4/#5/#6。

A1 资产审计完成于 `273721ab`，其文件快照与 manifest 绑定当时源码；本次测试重命名不会反写旧清单。source registry/bank-v0/retrieve.read 尚未交付；必须在正式冻结后按既定顺序开工。GPU/生成/训练/付费均未运行。
