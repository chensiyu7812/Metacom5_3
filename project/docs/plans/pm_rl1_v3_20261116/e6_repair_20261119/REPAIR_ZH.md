# E6 必要修复候选：原计划不变，运行仍未授权

原 WS-B 对 #21 `46349ccf02fef477bfc8fd76114bf1e38044e1d3` 独立故障注入得到 47 项检查、43 通过、4 失败。原始结果由 B 保管：共享数据盘 `tokkio_runs/wsb_v321a/e6/final/E6_HARNESS_RESULT.json`。本记录不覆盖 B 回执，也不把 CPU dummy 当实际模型结果。

| B 失败项 | 最小修复 |
|---|---|
| E3：worker 退出但后代进程残留 | 在 model import 前启动独立 stdlib 监护进程；worker 的 pidfd 可读即清理本次私有进程组 |
| E5/E6：supervisor 被 SIGTERM/SIGKILL 后 worker 继续计算 | 同一监护进程观察 supervisor 的 pidfd，独立执行绝对全局截止；不依靠已死亡父进程内的 Timer |
| F1：更换授权文件可重跑未决 START | 一次性 claim 绑定 job kind、固定请求文件 SHA、有序请求 IDs、baseline SHA；旧 plan claim 与部分写入记录均拒绝重用 |

监护进程与 worker 同组，自己持续持有该 PGID，避免对已复用的进程组发信号；只清理本作业组。exec 保持 worker PID、模型调用、管道与设备身份。它不加载模型，不修改 decode，不产生额外物理调用。正常 supervisor 的全局及单调用 watchdog 保留。SIGKILL 无法保证写出 STOP，未匹配 START 加一次性 claim 是保守 pending 证据，不允许补发。root/GPU/模型 SHA/未授权拒绝门禁保留。

固定 Python/libc 未暴露 pidfd_open，主机 Linux x86_64 的内核支持该系统调用，因此采用经本机头文件核对的 syscall 434；其他不支持的平台拒绝启动，不退回易受 PID 复用影响的轮询。本次首轮4个新生命周期测试因此失败，修复兼容入口后 48 项定向 CPU 检查通过；初轮失败收据留在私有交付目录。

## 身份与验收

原 A0 plan SHA `43f175c56d6a3e12078ed26744fd4c09f92ab67b7eb34b0a3e28d0ef40815cb2` 与 PP1 plan SHA `bc51f93157648229f751b586be013af8d2ce42071dd95c03171f522f95d96380`、4/16 请求、G0e/system/tokenizer/Notes/greedy320全部保持。执行器代码修复提交由本目录两个 `*_EXECUTOR_BINDING.json` 绑定；它们仅含代码与旧计划身份，不含 RAW 或 prompt。

新执行器必须明确传 `--executor-binding`。CPU `check` 会同时验证旧 plan 的历史代码 SHA、新 binding 的源码/commit SHA，以及未变的请求/模型/容量身份。未传 binding 不能拿原 plan 的代码 hash 验新代码。实际运行时 researcher approval 还必须签 `executor_binding_sha256`（项目规范 canonical object SHA）与实际 checkout HEAD；旧审批不能转移。

CPU 检查形式：`limited_g0e_run.py check --plan <原计划> --executor-binding <对应新绑定>`。没有在本轮执行 `run`。

这项新绑定不是改写研究计划或冻结记录，也不是 B E6 签收。B 应针对交接的最终 HEAD 独立复跑 E3/E5/E6/F1 及相邻门禁。原 B harness 的 read_plan/authorize 包装须显式传入相应 binding，不能跳过 SHA 验证；B 自行修改并保存其测试身份，A 不代跑 B 验收。

完整 CPU/CI、B 新回执及真正最终 checkout HEAD 通过 PR 评论和私有交付目录补记；不得把此候选文档中的等待项写成 PASS。A0 仍须 G0e 研究身份签收、E6、最新容量与单独研究者授权。PP1 仍等待实际 A0，不能与新 renderer 的 FC-MS 混用。

本提交只有源码、纯合成回归及身份说明。RAW 路径/历史清单、A0 申请、容量、renderer token 成本和人工 DP 对齐材料均在仓库外，交 B 汇总许可治理；无新增公开 RAW、真实评审包或生成输出。没有修改 H0、EXECUTION_STATE、main、integration、原计划或旧证据，没有 merge 或运行授权。
