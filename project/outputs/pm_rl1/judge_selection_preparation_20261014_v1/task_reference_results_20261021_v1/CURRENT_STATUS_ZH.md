# PM-RL1 当前状态

更新：2026-10-21T14:06:32.505438+00:00。唯一当前研究入口：[统一推进方案](PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md)。

共享任务参照A/B固定32次已全部完成，累计253→285，活动容量349；本批285硬边界已到，运行关闭。每臂16，技术有效32，模型unknown/技术失败/未派发/重试0。12条回复、5个已暴露情境、2位owner；独立验证0、新独立人评0。

母亲情境OFF/ME/RS两组完整读数在两臂均稳定，公开任务理由一致；同期A没有出现预定要修的标准切换，不能宣称B的额外任务卡带来改善。04B两臂仍在两种允许读法间变化，U差0.5翻转职场RS/OFF边界；35B事实核查相同而m=.25/1不同，但该已测负收益符号未变。B一份理由将双读作为local依据，未由后果锚点充分解释，单列为评分依据问题。不改原分，不把未决变成模型unknown或独立人评。

建议停止扩充任务卡；下一研究优先项是明确歧义与后果严重度的有限反馈处置，并用已有结果回放其决策影响。自动关系仍待实现验证，本批A也含人工/分析者辅助关系，不能直接部署或进入自然PPO。四头顺序获取/读后决策、OFF/FixedDev/匹配随机/OneShot/BC-init/BC-union/PPO/NoText、多种子及独立评价全部保留。

实际输入237206、输出154988 token（含thinking137186，不重复加），请求合计784.03秒，评分窗口790.04秒，GPU0。按完整usage保守入账$0.2571474，API试验及共享后续累计$1.602273，未结0；完整历史账$3.10951591。原API累计$3.15/共享$20守卫不变，容量余64不是新调用授权。正式研究仍未落实在$20内，未选择128/384或删除比较。

协议`22bc262f8aee60c3f7a1efef4fe402f8ee742302faa3e26db9189621d0a7c936`；第4次共同提示组合只用于本诊断。官方Flash/high公开映射DeepSeek-V4.1-Flash-1017，32回执fingerprint相同，不称固定权重。账户管理各1次，凭据仅进程内使用。原合同、53项冻结文件、187份历史started、旧66次基数、9份STOP、旧分数和账本前缀保持。

仓库真实路径`/opt/tokkio-data0/tokkio_projects/Metacom5_3`；分支`work/paper1-rq1-integration-20260816`；HEAD`0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28`。未切分支、提交、推送、上传、打开封存/PM测试、生成或训练；自然更新仍0。

本地完整结果：`project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/task_reference_results_20261021_v1/REPORT_ZH.md`。home结果目录及ZIP：`PM_RL1_TASK_REFERENCE_RESULTS_20261021`。私人原文仅在本地忽略目录及私人包；此文件可作为可分享摘要。

此前状态原文完整归档在本批`documentation_before/project__docs__PM_RL1_CURRENT_STATUS.md`；历次批准/修订/STOP均保留。本批结束，等待集中研究决策，没有下一批执行授权。
