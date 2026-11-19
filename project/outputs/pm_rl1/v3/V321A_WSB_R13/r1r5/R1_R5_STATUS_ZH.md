# R1–R5 修复进度（与 PP1/FC-MS 解耦）

- **范围**：这些问题只影响在线 RL 环境（BoundEpisode、ReplayCache、RELATION 交换），不阻止静态的资源质量比较。
- **计划**：见上一轮的 [修复计划](../../V321A_WSB/r1r5/R1_R5_REPAIR_PLAN_ZH.md)。

| 项 | 状态 | 证据 |
|---|---|---|
| R3：STOP 后 done 仍为 False，之后的 GET 依然成功 | **已修复（待 WS-A 签收）**：STOP 现在把 done 置为 True，之后的 GET 或 STOP 都返回 `after_stop`；终止键不变 | 先写测试 `test_r3_stop_ends_the_episode_and_a_later_get_is_after_stop`，确认失败后再修复，现在通过 |
| R4：同内容重试时缓存报错；存在可变别名 | **已修复（待 WS-A 签收）**：同内容 put 是幂等的；put 和 get 都做深拷贝；内容不同仍然拒绝 | 先写测试 `test_r4_identical_retry_is_idempotent_and_values_are_isolated`，失败后修复，现在通过 |
| R2：BoundEpisode 构造时没有完整验证 | 未修复：需要改构造接口（传入 registry、prefix、snapshot/port），先与 WS-A 对齐接口 | — |
| R1：binding 身份经 registry 间接依赖整个文件的 raw_sha256 | 未修复：需要与 A 的 `SNAPSHOT_HASH_SPEC` 对齐字段集 | — |
| R5：adapter 遇到 RELATION 记录时报 KeyError | 未修复：需要 A 提供真实的更正链样例 | — |

- **其他测试**：test_rl1v3_v32_wsb.py 中原有的测试全部仍然通过（共 39 项）。
- **代码提交**：`8198f09d`。冻结的 #16 产物没有改动。
