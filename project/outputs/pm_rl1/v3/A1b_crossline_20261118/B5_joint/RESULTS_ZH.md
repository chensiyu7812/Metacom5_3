# A 新端口与 B 提交版回放器联合验收（2026-11-18）

A 端口提交 `14fd459e473cc3e98ab8b4dbddf73216e9314759` 的 PrefixPort 直接交给 B `d06715bf6893710c8b21f2c91c7cac42c0111e85` 的原版 bank_replay_v2.replay_prefix。B 使用数据盘干净 detached 稀疏工作树；A 资产只读使用现有树，所有实际导入的 A 模块逐 SHA 与 14fd459e 提交 blob 核对一致。未编辑/复制 B 业务代码，未改共享 C0。

实际结果：

- 固定 24/24 覆盖前缀通过，无失败。
- 21 个前缀有 16 个可达子集；3 个只有 8 个，原因均为 MP 没有合法候选。
- 共 360 个可达终点、1413 条实际 GET 顺序；21 条 ready_at 等于 cutoff_rank 的记录合法通过。
- 24/24 独立 bank/tokenizer 重新加载回放一致；24/24 容量压力检查通过，均实际验证失败读取不推进状态。
- 与第一轮 B 自有适配器的身份、所有终点 key、输入 token、逐头根读取 record_ids/正文 hash/tokens 完全相同。
- 本轮耗时 114.42 秒，退出码 0；0 GPU、模型推理、训练和付费调用。读取原生 tokenizer 文件，不读取模型权重。

summary.json / replay_reports.jsonl 保存 B 原始验收结果；INPUT_FILES_SHA256.json 绑定真实来源、bank、index、覆盖样本及 tokenizer。EXECUTION.json 保存实际加载模块、提交 blob 核对、运行前后身份及 harness SHA。输入文件运行后再次核验无变化。完整重放条件由固定 A/B 源码、全部输入 SHA、前缀、身份和确定性子集/顺序枚举共同固定；不将哈希摘要伪称内嵌完整 Trace。

这是合入前的联合工程预演，不表示 A1/A1b 已集成，不表示 B1/B2/B6e 完成；无 Generator 输出，真实终点仍 pending。另一 B 会话的 d06715bf 为其正式提交，但包含其其他 B1/B2 工作，如何拆分/合入由集成负责人串行协调。

复现脚本位于父目录 run_a_port_b_replay.py。其对逻辑失败、源码 blob 不符、运行期间代码变化和 B 工作区不干净均返回非零；不弱化 B 原有断言。第一次完整 B 工作树因根分区空间不足失败后，改为数据盘稀疏工作树；失败副本由 Git 自动撤销，其他工作区未触碰。
