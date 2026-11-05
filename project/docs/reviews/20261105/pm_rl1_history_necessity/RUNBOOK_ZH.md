# 本批复核与回收

本批生成已完成，不再次执行 `run` 或替换输出目录来重试。只读核验：

```bash
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/docs/reviews/20261105/pm_rl1_history_necessity/verify.py
```

执行入口为 `project/scripts/rl1/175_probe_history_necessity.py`，本次顺序为 `freeze → prepare → run → collect`。`run` 复用冻结的 167 执行器和 172 局部 GPU 检查；首次冻结检查曾因误将 OUTPUT_MANIFEST 的 hash 与 CATALOG_MANIFEST 比较而失败，已修正验证对象后成功冻结，发生在任何本批 G 调用之前，没有改变协议、筛选标准或原来源。

`build_review.py` 仅构建本批固定页面，不对旧问卷写入。私有产物中的 `HUMAN_PACKET_PRIVATE.json` 绑定显示字母和回复，`REUSED_HUMAN_PRIVATE.json` 保留 G07/G08 的原记录、原证据和哈希，`CONTENT_AUDIT_PRIVATE.json` 是助手的来源内容观察，不是人类偏好。

答案回收必须核对页面 `study`：`c52a56fd81d55d112ce227063bbdbcff0d0fb3325df03c03c2adde5a298e4e78`。

- 8 组三条的显式排序可得 C/OFF、C/D，D/OFF 作为辅助对照；并列保留并列。
- 2 组双回复只补 C/D，C/OFF 来自保留的旧记录，不要求重答，不重复计为新的独立观察。
- 允许分批、不确定和更正；未答仍缺失。新答案应追加版本，不能覆盖原始提交。匿名字母不可凭语义猜测对应条件。
- 若理由指出事实错误，须回到完整当前及合法历史核对，不能将对风格的不同偏好直接标作事实错。
- 原文说明“略好/有实质改善”与排序分开保存；不将例示分数、相当或排序映射成 q/m、精确零收益或 PPO 奖励。
- 按 `SCREENING_PROTOCOL.json` 的固定门槛报告联合胜出、owner、损失、不确定和来源误用。完整判断未通过时不继续追加例子；通过只授权下一项受限路径/等待/反馈研究。

输出目录中的 `OUTPUT_MANIFEST.json` 封存生成与问卷阶段。后续人评文件另建增量清单，不改写本次清单及原 45 条登记。
