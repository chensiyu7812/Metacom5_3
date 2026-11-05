# 本轮人评收口复算

工作目录：`/home/tokkio/Metacom5_3`。全部 CPU/标准库，不加载模型、不调用评分、不启动训练。

```bash
python project/docs/reviews/20261105/pm_rl1_history_necessity_human_review/verify.py
```

`ingest.py` 是本次答案的一次性入库脚本，已执行；使用排他创建，禁止覆盖已有产物。正常复核只运行 `verify.py`，不删除结果后重跑入库。

私有输入：原 `history_necessity_probe_20261105_v1` 冻结包、旧 `incremental_help_human_review_20261105_v1` 45 条参照、本轮 `history_necessity_human_review_20261105_v1/RECEIVED_ANSWER_PRIVATE.json`。

私有输出：同一新目录下 `INTAKE_PRIVATE.json` 保存显示顺序、回复/证据身份、原始理由及关系来源；`ANSWER_REGISTRY_PRIVATE.json` 保持原 45 条并增加 10 个答题单元；`REFERENCE_INDEX.json` 声明混合记录粒度；`SUMMARY.json` 保存主排序判定及排除程度不确定两题的敏感性；`OUTPUT_MANIFEST.json` 绑定 5 个文件。

核验包括：旧 94 文件封印、新 5 文件封印、10 题绑定和 30 个关系（含 2 个直接比较缺失标识）、旧 45 条不变、Q03/Q06 不确定程度、未臆造 Q05/Q09 的 D/OFF、无数值奖励、8 个错误输入拒绝情形，以及固定门槛复算。它验证处理正确，不把研究结果标为科学 PASS。

结果用途：关闭当前正收益扩张分支、保留开发参照、整理避免无效读取与等待的研究结论；不是 PPO 可用奖励授权。无需重复问卷。
