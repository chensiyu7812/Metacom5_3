# B 活跃工作树真实回放观察（2026-11-18）

使用既有 B5_real_replay_v2.py，独立 --out 目录，未修改或复制活跃 B 代码。

- 24/24 前缀通过：21 个有 16 子集，3 个有 8 子集（MP 无合法候选）。
- 容量压力检查 24/24 通过，均实际测试读取拒绝后的状态保持。
- 21 条 ready_at 等于 cutoff_rank 的资源合法通过。没有 Generator 输出，终点仍 pending。
- 原生 tokenizer CPU，221.9 秒；0 模型、GPU、付费调用。
- 运行前 HEAD 为 a0771e1e5b73605778341647be89f067769a01ce，运行期间另一 B 会话提交至 d06715bf6893710c8b21f2c91c7cac42c0111e85。55 个预记录源码/config 文件运行前后字节未变，且全部与 d06715bf 提交 blob 相同（B_COMMIT_BINDING.json）。保留原始 dirty/HEAD 事实，不将其说成当时已合入。
- 本轮仍使用 B 自己的 A1bPort 与本树旧 Reader；A 新端口的独立组合验收另在 data0 的 joint-a14fd-bd067-20261118-v1 执行。
- 独立 detached B 完整 checkout 曾因 /home 分区空间不足失败，git 自动撤销失败目录；没有删除任何既有工作树。之后在 data0 创建 --no-checkout 加稀疏工作树成功。实测 /home 余 2.2 GiB，data0 余 346 GiB。

静态发现但本轮未触发的工程限制：B runner 当前写报告后直接结束，逻辑 passed=False 时未显式返回非零；本次实际全通过，未据此伪造失败结果。后续验收 wrapper 应对失败汇总返回非零。原始 B 输出主要保留 key/trace 哈希及确定性回放条件；共享 C0 未改。
