本次将当前 PM-RL1 方案、代码和开发结果同步到研究分支。P1/P2 已完成并披露限制；P3 已完成初版开发评分与40对人工校准工具，真实人工标签、奖励资格和自然支持 PPO 仍待完成。

## 审阅入口

- [本阶段结果、限制和发布验证](https://github.com/chensiyu7812/Metacom5_3/blob/work/paper1-rq1-integration-20260816/project/docs/PM_RL1_STAGE_PUBLICATION_20261002_ZH.md)
- [全部进展索引](https://github.com/chensiyu7812/Metacom5_3/blob/work/paper1-rq1-integration-20260816/project/docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md)
- [可行完成方案](https://github.com/chensiyu7812/Metacom5_3/blob/work/paper1-rq1-integration-20260816/project/docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md)
- [公开结果清单](https://github.com/chensiyu7812/Metacom5_3/blob/work/paper1-rq1-integration-20260816/project/docs/reviews/20261002/pm_rl1/MANIFEST.json) · [公开概览 notebook](https://github.com/chensiyu7812/Metacom5_3/blob/work/paper1-rq1-integration-20260816/project/docs/reviews/20261002/pm_rl1/stage_results.ipynb)

## 本阶段实现与结果

- 能力反推、结构特征分析、完成方案v2、结构化工作包、预算和后续操作手册。
- P1：来源/角色交付修复、共同70计划观测；114个train/dev前缀共6,899个可达计划；88次生成全部自然结束。
- P2：493条弱目标（train413/dev80），一次三epoch LoRA；选中epoch3、重载NLL一致；586条主回复和53条base对照均自然结束。
- P3：完整来源q/m评分、严格解析、证据引用、离线表单、逐题加密、开发部分接收与固定资格计算；32次开发评分和1次预定复核探针均自然结束、结构有效。本地引擎约29.18分钟，新增API费0；吞吐估计不冒充完整PPO排期。
- 26份结果/冻结记录及16份分析资产的来源哈希；前次75份公开结果与2,735份历史本地产物保持原样。
- 通用人工工具和测试已公开；两份内含在用控制题/分组的制卷脚本暂缓公开并登记哈希。完整表单、盲映射、逐题机器评分、私钥及模型权重留本地，保持待开展的人评有效。

## 结果限制

4条已入选P2弱目标受重复JSON键准入缺陷影响；实际493条训练数据未被事后改写。6组跨加载同输入回复仅2组逐字一致，根因未确定。NLL改善不代表支持质量改善。P3尚无真人标签，封存评分和12次独立重复评分未执行；初版解析成功不等于裁判校准合格。

本PR还保留前次上传的环境/E0工程、R04B裁判实验、数据普查以及CPU CI可移植修复。此前pytest故障来自被忽略的本地产物、绝对路径和未声明依赖，并非Git冲突；详情见9月30日发布记录。

## 验证

- 干净检出CPU suite：1,206 passed，1项既有tokenizer路径skip；没有新增skip。
- 32项集成/锁状态检查、compileall、wheel构建及HTML/JS打包检查通过；3个公开notebook代码单元通过。
- 54条阶段结果来源哈希、2,735份旧产物哈希复核通过；现有人工校准包冻结信息一致。
- 首轮干净检出发现本地Python未安装已声明的json-repair==0.52.4，8项旧测试报错。在隔离测试环境补齐固定依赖后全量复跑通过，研究环境和仓库解析语义不变。
- 最终提交 `0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28` 的两套GitHub检查均已完成并通过：[pull_request 检查](https://github.com/chensiyu7812/Metacom5_3/actions/runs/36956078871) · [push 检查](https://github.com/chensiyu7812/Metacom5_3/actions/runs/36956072998)。

本次未修改CI工作流、增加测试跳过或改写旧实验结果；发布过程无模型调用、训练、人评或API消费。未合并到main。
