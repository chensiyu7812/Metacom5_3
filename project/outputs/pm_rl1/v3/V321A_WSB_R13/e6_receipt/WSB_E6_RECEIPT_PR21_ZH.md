# WS-B 独立回执：PR #21 执行器（Gate E6），以及 #23 修复的复跑

- **#21 固定 HEAD `46349ccf`**：**不签收（NOT_SIGNED）**。故障注入共 47 项检查：43 项通过，4 项失败。失败的 4 项对应 4 个缺陷：高 2、中 1、低 1。
- **#23 修复 HEAD `67169816`**（代码 `26343dc6`；A0 binding `c9eb9169…`，PP1 binding `2a14cac2…`）：同一 harness 复跑后**签收（SIGNED）**，范围限于 CPU 故障注入，见 §5。
- **签收不是授权**：E6 签收不构成 A0 或 PP1 的运行授权。授权须另签 binding SHA 与最终 checkout HEAD，并满足 E1（G0e 身份冻结）、E2（A0 实测）和 E5（研究者授权）。

## 审查对象与方法

- **对象**：PR #21 HEAD `46349ccf02fef477bfc8fd76114bf1e38044e1d3`（代码 HEAD `575011b4`）中的：
  - `generator/limited_run.py`；
  - `generator/limited_hf_worker.py`；
  - `scripts/rl1v3/limited_g0e_run.py`；
  - 计划文件 `A0_MIN_PLAN.json`（`43f175c5…`）与 `PP1_PLAN.json`（`bc51f931…`）。
- **独立性**：
  - B 自己写了故障注入 harness：[V321A_e6_harness.py](../../../../../scripts/rl1v3/V321A_e6_harness.py)；
  - A 的执行器只作为被测对象运行；
  - 没有使用 A 的测试或验收函数作为判定依据，所有期望都由 B 给出。
- **替换的依赖**（都由 B 编写，只用 CPU）：
  - HF worker → 假 worker：使用同一 JSON 行协议，并记录它收到的每个请求；
  - `nvidia-smi` → 假脚本：可设定 UUID、空闲显存、占用进程、调用失败、第 N 次后变化；
  - DATA 根目录 → 每个场景一个临时目录，锁、claim、日志都不碰真实路径；
  - 模型字节清单 → 模型目录中一个真实的小文件（config.json），哈希正确或故意写错，避免读取 24 GB 权重。
- **隔离**：
  - 每个场景在独立子进程中运行，因此可以对监督进程发信号；
  - 运行期间没有加载模型，没有访问 GPU。
- **结果文件**：[E6_HARNESS_RESULT.json](E6_HARNESS_RESULT.json)（47 项明细）、[E6_RECEIPT.json](E6_RECEIPT.json)、[harness_run.log](harness_run.log)。
- **复跑**：`python scripts/rl1v3/V321A_e6_harness.py --wt <固定 HEAD 的 worktree> --out <目录>`。

## 1. 研究者列出的十项要求

| 要求 | 场景 | 结果 |
|---|---|---|
| 未授权启动必须拒绝 | A1–A8：未授权、A0/PP1 授权互用、plan SHA 不符、调用数不符、checkout HEAD 未钉住、G0e 身份未固定、缺执行器审查、缺研究者；F3：worker 单独启动或伪造监督 pid | **通过**：全部在调用 nvidia-smi、写 claim、写日志、启动 worker 之前就拒绝 |
| 授权身份与执行器、模型、tokenizer、plan/request SHA 匹配 | A9 请求文件被改、A10 执行器脚本被改、A11 跟踪文件被改（工作区不干净）、B7 模型字节哈希不符；模型文件清单含 tokenizer.json、tokenizer_config.json、chat_template.jinja | **通过**：B7 在 LOAD_START 之前就 STOP，没有启动 worker |
| GPU UUID、空闲显存、根盘容量 | B1 UUID 不符、B2 空闲 < 40,960 MiB、B3 GPU 上有其他进程、B4 nvidia-smi 失败、B5 根盘 < 1 GiB、B6 TMPDIR 未重定向；B8 运行中途 GPU 被占用 | **通过**：B1–B6 在写 claim 之前拒绝；B8 在运行中停止，之后不再有 START，worker 被清理 |
| 原子 START/RESULT 日志 | C1：事件顺序；假 worker 收到第 n 个请求时，磁盘上已有 n 个 REQUEST_START；B 根据文件字节重算哈希链 | **通过**（语义说明见 §3） |
| 任何技术失败立即停止 | D1 worker 报错、D2 worker 崩溃、D3 空输出、D4 返回不是 JSON、D5 A0 首个 length、D6 A0 重复结果不同、D7 加载时 OOM | **通过**：都停在出错的那一次调用，之后没有 START，pending 记录正确，worker 被清理 |
| 第三次 length 截断停止 | D8（PP1，第 2、5、9 次为 length） | **通过**：在第 9 次停止；3 个 truncated 保留；7 个未执行 |
| 1,200 秒总时限 | D9（假时钟）：最后一次调用只获得剩余的 100 秒，超时即停；E1（真实时间）：硬截止 6 秒，杀掉挂起的 worker 和它的子进程 | **通过** |
| OOM、超时、信号中断后的子进程清理 | E1 硬截止、E2 worker 忽略 SIGTERM（升级为 SIGKILL）、E4 对监督进程发 SIGINT | **通过** |
| | **E5 对监督进程发 SIGTERM** | **失败（高）**：见 E6-D1 |
| | **E6 对监督进程发 SIGKILL** | **失败（中）**：见 E6-D2 |
| | **E3 worker 自己退出，留下子进程** | **失败（低）**：见 E6-D4 |
| START 已记录、RESULT 不明时拒绝重试 | C1b 同一授权再运行；E5/E6 中断后同一授权被 claim 挡住 | **通过** |
| | **F1：为同一计划另签一份授权** | **失败（高）**：见 E6-D3 |
| 不跨作业复用缓存、不偷偷追加调用 | C1 恰好 4 次物理调用，没有预热；F2 第二个作业在锁被占用时被拒绝；代码中没有结果缓存；每个作业启动新的 worker | **通过**（但 E6-D3 会导致同一计划被重复调用） |

## 2. 缺陷与修复要求（A 修复，B 复跑）

| 编号 | 级别 | 复现 | 现象 | 修复要求 |
|---|---|---|---|---|
| **E6-D1** | 高 | E5 | 对监督进程发 SIGTERM 后，它直接退出，没有写 STOP 或 SUMMARY。worker 在自己的 session 中成为孤儿，把正在进行的调用跑完（harness 中是 12 秒；真实的 generate 或模型加载会一直占着 GPU 直到结束）。父进程一侧的看门狗定时器随父进程一起消失 | 监督进程把 SIGTERM/SIGHUP 转成异常，使 drive() 记录 STOP，并让 close() 杀掉整个进程组。worker 侧要加三样：PR_SET_PDEATHSIG=SIGKILL；一个看门狗线程，发现 getppid() 不再是受准的监督进程就立即退出；监督进程把每次操作的绝对截止时间传给 worker，worker 自己也执行这个截止 |
| **E6-D2** | 中 | E6 | SIGKILL 无法捕获，后果与 D1 相同 | 同 D1 中 worker 侧的三项措施 |
| **E6-D3** | 高 | F1 | “不得重试”的 claim 以授权文件的哈希为键。为同一计划另签一份授权（文字稍改即可），就会把全部请求重新跑一遍，即使已有 START 没有结果。harness 中，4 次的计划实际发生了 6 次物理调用 | claim 改以 plan_sha256 为键，一个计划只执行一次；或者在任何属于本计划的日志中存在未决 START 时拒绝运行，除非新授权明确引用那份日志，并且由一个新计划只覆盖从未开始过的请求。同一计划下，已验证或未决的调用都永不重跑 |
| **E6-D4** | 低 | E3 | worker 进程自己退出时，close() 跳过了 killpg，它在同一进程组中留下的子进程会存活。真实的 HF worker 不应该派生子进程 | close() 一律对 worker 的进程组执行 killpg(SIGKILL) 并回收，忽略 ProcessLookupError |

## 3. 其他观察（不是失败）

1. **日志语义**：
   - START 对应 REQUEST_START，在发送请求之前 fsync 落盘；
   - RESULT 对应 REQUEST_RETURNED（原样保存）加 REQUEST_VALIDATED；
   - FAILED 没有逐请求的事件，由 STOP 表示（含 reason 和 pending）。建议增加 `failed_request_id` 字段。
   - 监督进程被杀时不会有 STOP。读取方必须把“有 START、无 RESULT”视为未决；修复 D1/D3 后应由执行器强制执行。
2. **write_once 的方式**：是 O_EXCL 加 fsync（文件和目录），不是先写临时文件再 rename。崩溃时可能留下写了一半的文件；代码有意保留它作为未决证据，读取方需要容忍最后一条无法解析。
3. **执行器审查证据**：`executor_review_evidence` 只检查是否非空。应改为绑定 B 的 E6 回执：URL、回执 sha，以及它覆盖的执行器 HEAD。
4. **模型与 tokenizer 校验**：tokenizer 文件在加载前与权重一起做逐字节哈希。24 GB 的实际哈希约 170 秒，计入 1,200 秒总预算。
5. **只做了代码审查的部分**：真实 worker 的“只加载一次”和“原生 tokenizer 结果与请求 ids 相同”，因为假 worker 替代了真实 worker。需要在 A0 实测时由日志证明。
6. **未跟踪文件**：未跟踪文件不在干净检查范围内（`--untracked-files=no`）。PYTHONPATH 下如果有未跟踪的 `sitecustomize.py`，worker 启动时会导入它（低风险）。

## 4. 复跑条件

A 修复 D1–D4 后，在新的固定 HEAD 上，B 用同一 harness 复跑。

- 47 项必须全部通过；
- 另增 2 项：
  - SIGTERM 或 SIGKILL 监督进程后，worker 在 2 秒内消失；
  - 对同一计划另签的授权必须被拒绝。

全部通过后，B 才签收 E6。签收本身仍然不构成 A0 或 PP1 的运行授权。

## 5. #23 修复的复跑：签收（CPU 故障注入范围）

- **对象**：Draft PR #23 HEAD `67169816bddaf50206f9847300673d4887713c4d`（代码 `26343dc69ba1616fad293319a26a86b0b1b0816d`）。
  - A0 binding `c9eb9169897686c018b657c39b766689b78058441976774eb34107f8da0d65e1`；
  - PP1 binding `2a14cac2f2598fdbeb47c1ce6f9159fa2518ec592707d84d8999dd1bd6f71b2d`；
  - 原计划 A0 `43f175c5…` 与 PP1 `bc51f931…` 不变。
- **A 的修复**：
  - 启动 worker 之前，由 `limited_worker_guard` 建立 pidfd 监护和绝对截止时间。监护进程留在 worker 的进程组内，监督进程或 worker 任何一方消失，或到达截止时间，就对整个进程组发 SIGKILL；
  - claim 改为绑定请求集合：同一计划或同一请求集合已有 claim 时一律拒绝；
  - 增加独立的 executor binding，授权必须携带它的 SHA。
- **复跑结果**：

| 运行 | 结果 |
|---|---|
| Python 3.11，全部场景，另加 2 项 binding 检查（授权缺 binding SHA 被拒；运行不带 binding 被拒） | **49/49 通过**：[E6_HARNESS_RESULT_PR23.json](E6_HARNESS_RESULT_PR23.json) |
| Python 3.12（实际执行环境，没有 `os.pidfd_open`，走 ctypes 系统调用路径），进程、日志、重试类场景 | **20/20 通过**：[E6_HARNESS_RESULT_PR23_PY312.json](E6_HARNESS_RESULT_PR23_PY312.json) |

- **四个缺陷全部关闭**：
  - D1：SIGTERM 后 worker 在 2 秒内消失，不再继续计算；
  - D2：SIGKILL 后同样如此；
  - D3：同一计划的新授权被请求集合 claim 拒绝，物理调用不增加；
  - D4：worker 退出后，进程组中的子进程被清理。
- **仍保留的观察**（不阻塞签收）：
  - SIGTERM 仍然不写 STOP/SUMMARY。未决的 START 是持久记录，并且已经强制不可重试；
  - FAILED 没有逐请求的事件；
  - `executor_review_evidence` 仍然只检查非空，授权文件应引用本回执的 URL、#23 HEAD 与 binding SHA。
- **签收范围**：执行器的准入、身份、守卫、日志、停止、进程清理与不重试。真实 worker 在真实模型上的“只加载一次”和“原生 tokenizer 相等”，须由 A0 的日志证明。
- **机器可读版本**：[E6_RECEIPT_PR23.json](E6_RECEIPT_PR23.json)。
