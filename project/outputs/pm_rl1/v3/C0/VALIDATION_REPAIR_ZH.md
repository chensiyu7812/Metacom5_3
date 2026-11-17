# C0 全套验证中的历史工作树适配修复

C0 共享代码仍为 50c9ade0，字段、Schema 和 IO 未变。最初的完整本地非GPU套件结果：1935 passed / 2 failed / 1 skipped / 11 deselected（473.39秒）。失败原文保留在 pytest-full.log/xml，未隐去。

两项失败：RelationReferenceTests.test_read_only_entry_preserves_old_and_budget_history、TaskReferenceTests.test_history_and_exposure_not_inflated。旧协议的 attempt 清单是 /opt 原工作区绝对路径；在 /home/tokkio/Metacom5_3-ws-a 上，测试以副本路径去比较原协议路径，真实保护器按设计拒绝。不是新的付费调用或历史attempt增长。

修复只在这两项测试中：从协议既有 run_dir 的祖先找原冻结目录，令原历史守卫在其绑定的真实路径上执行；所有原哈希、计数、账本/activation不变断言保留。同时在不同工作树中明确断言副本路径仍被守卫拒绝，**没有重写协议、删除断言、增加skip或更改runtime**。第一次修复误将run_dir的上两级当作base，因live子目录仍错误；该次2失败日志保留在 validation_2。最终按明确祖先名称定位，相关两套测试+C0+A0共176 passed，见 validation_3。（其后新增A0 BatchEncoding回归另有13项定向通过。）

C0 首次 GitHub CI run 44038668594 已 success，包括原有阻塞pytest及 integration base/outcome lock 检查；这是50c9ade0的结果，不代表后续head已通过CI。最终本地全套复跑仍在执行，完成后追加独立记录，不覆盖上述证据。

边界：这两套是已有本地冻结资产集成测试，干净GitHub runner依既有来源存在性规则跳过；便携契约测试始终执行。最终全套的唯一已知skip是本机没有 /home/chenzhi 的冻结 Llama tokenizer；11个GPU测试按原命令-m not gpu排除。
