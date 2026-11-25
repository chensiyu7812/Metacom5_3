# 原八道日期题：独立检索生成申请

状态：CPU 准入及五项守卫测试通过，尚未授权，尚未调用模型。此前76次授权不适用于此包。

保留原来已经冻结的全部8题、24逻辑臂、22个唯一payload；请求字节未改。三个条件为 RET-v1-filtered、Time-Lexical、Hybrid。每批4个完整任务、12逻辑臂、11次实际调用，批内各有1次精确payload复用。

|批次|计划对象 SHA256|请求文件 SHA256|
|---|---|---|
|T1|`c455e671ced0c3b6b76c42992315a8b17af2b34586b39d26a6698369714a3d39`|`71c7f250fefb26c1df8fafc47acac829c945ef45de5746785d67b6cc7b4b4349`|
|T2|`d76db0d9c9ab3f0442d45007a4cc3e1e9d0a2132009f680166d4bff0ac6b1be0`|`d7768ea1175796bbe2d40b9977e0548ee91a39692363d50d9d789bf7638bf2f0`|

原指定GPU、原Gemma模型及生成配置，每批1次加载、0 warmup、0 retry、1200秒总硬限；两批合计22次调用、2次加载、2400秒硬上界。沿用独占锁、设备空闲守卫、请求领取、模型字节核验及原停止规则。GPU被其他项目占用则不启动。保守耗时情景各约687秒，仅为预算估计。

T1/T2 实际冻结输入分别为31,692/28,491 tokens。旧RET先取Top4再过滤、不补位，八题合计仅返回8个会话；Time-Lexical及Hybrid各返回32个。三臂均未供应未来来源。已支持的必要原子供证分别为6/20、15/20、19/20，另两题有参考待定或范围冲突；不能将差异全部归因于混合检索算法。完整历史原RET及原官方QA身份不变。

独立执行器 `journal/temporal_run.py` 绑定原候选冻结清单、逐臂供应、全24请求及原模型/守卫。CPU准入逐项核验完整配对、原顺序、精确复用、时间合法性、请求与执行器SHA。评估沿用既有规则，unknown保留；最终同时报告返回会话数、供证、token、耗时及逐题回答。

私有计划位于 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-closeout-20261125/temporal22-v1/batch-01/PLAN.json` 和 `batch-02/PLAN.json`；公开数值摘要为同目录 `REQUEST_PUBLIC.json`。完整请求/来源/参考不上传GitHub。

CPU复跑（使用数据卷既有冻结输入；新输出目录不可覆盖）：

```bash
env PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src CUDA_VISIBLE_DEVICES= \
 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1v3/journal_prepare_temporal_run.py \
 --candidate /opt/tokkio-data0/tokkio_runs/pmrl1-j-keycap-20261125/temporal_generation/candidate-v1 \
 --template /opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125/rs_complex/package-v2/batch-01/PLAN.json \
 --repo /home/tokkio/Metacom5_3-journal --out /opt/tokkio-data0/tokkio_runs/temporal22-reproduce-NEW
```

更换输出绝对路径会产生新的计划对象身份；原授权必须只使用上表固定原对象，不得转移到复跑副本。
