# PM-RL1 关系参照A/B离线准备

已完成主方案顺序更新、12条已有材料及部分关系草案、28槽固定设计、最小runner适配和离线测试。运行未批准，参照语义仍有3项窄复核；当前225/289、自然更新0，新增真实请求/费用0。

唯一当前主方案：仓库 `project/docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md`（本阅读包附CURRENT_MASTER_PLAN_ZH.md快照）。32轨迹实现保留，原80次提案仍未批准。

阅读顺序：

1. [集中启动单](START_REQUEST_ZH.md)：28槽、外传、费用/容量、3项窄复核及结果分支。
2. [固定材料和关系参照](MATERIALS_AND_REFERENCES_ZH.md)：英文回复、原证据、已有判断与草案分层；完整源见CURRENT_AND_HISTORY_EN.txt。
3. protocol.json / schedule.json / analysis_rules.json：冻结身份、次序及判读。
4. offline_verification.json：机械/接口测试，不是语义合格证据。
5. code/：114入口、关系适配模块、113准备脚本及相关测试的本地快照。

协议：`b63ed6c1ad7e2ceb9a1ac3c4c022c634dfc0a045819a083f2a1571b2b2c15d04`。现有框架：paired.run＋DeepSeekTransport＋原账本/严格解析/outer_format；未另建同功能传输runner。B沿用两消息传输，在system尾部增加显式参考数据，完整user原文不变；这是新输入版本，不声称提示整体未变。

只读复核：

```bash
cd /opt/tokkio-data0/tokkio_projects/Metacom5_3
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/rl1/114_run_relation_reference.py --check
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/rl1/114_run_relation_reference.py --report
```

真实--live必须同时有外部真实批准及参照复核文件，PENDING在凭据/网络/新live目录之前拒绝。代码不自动生成APPROVED。不要从本README推导运行授权。

本包含私人开发材料，仅本地阅读；不上传、不提交或推送。两个未执行准备草稿原样存档，未产生评分或重置历史。
