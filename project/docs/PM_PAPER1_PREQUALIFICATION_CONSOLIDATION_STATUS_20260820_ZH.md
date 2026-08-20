# Paper 1 PRE-QUALIFICATION CONSOLIDATION 状态（2026-08-20）

结论：**离线 build 已完成；尚未达到开启任何 calibration lock 的条件。** 四把 outcome lock 全部 `CLOSED`，本轮 paid API、Generator、evaluator、outcome、PM training、formal ESC/ES-MemEval 调用均为 0。

| 层 | 当前状态 | 已有证据 | 尚缺 |
|---|---|---|---|
| Authority / four locks | FROZEN | 新 amendment、Master Register、四锁 fail-closed tests | 无 |
| RS canonical retrieval | READY | 15,061→13,172；11,883 states 直接 canonical Top-8；k=1/2/3/4/6/8 coverage=100%；cap384 truncation=0 | 人工 resource semantics qualification |
| RS treatment uptake | READY（harness） | OFF=无 RS、ON=恰好一个 exact move；无 utility filter；blind adherence schema | 隔离 Generator experiment 尚未授权/运行 |
| Memory precision | IMPLEMENTATION_PENDING | v7 general MP/ME/MS schema、prompt、deterministic gates、unit tests；旧 MP20/ME12 仅 DEV replay | 接入 live runtime、重编 401 sessions、全新 held-out human qualification |
| MS audit | AUDIT_REQUIRED | 按 continuity type/status 分层的 exact-turn packet | 人工审查 |
| ESC-RANK runtime | EXPERIMENT_REQUIRED | ≥24GiB fail-closed harness、pinned identity、限定 path patch manifest | pinned model/adapter tree hashes、云 GPU runtime、重复性/延迟/VRAM结果 |
| Evaluator comparison | EXPERIMENT_REQUIRED | ESC-RANK/Qwen/DeepSeek/独立家族候选位；human-blind protocol | exact proxy model identities、human reference、agreement/bias/cost结果 |
| ESC split | READY | `large_52` balance 最优的 no-outcome feasibility | researcher 显式 freeze；不是 FROZEN |
| RQ2 folds | READY | `K=5, seed=0`：1586 targets 全且仅一次；fold sizes 317/317/317/317/318 | researcher 显式 freeze；不是 FROZEN |

RS Top-8 额外事实：旧 raw Top-4 事后 collapse 会使 k=2/3/4 分别有 51/201/663 个 state 不足额；直接 canonical ranking 后全部补齐。随着 k 增大，同一 source card 下的不同 atomic moves 同时进入 bundle 的比例从 k=2 的 11.82% 增至 k=8 的 62.24%，因此该字段必须在 amount calibration 作为无 outcome bundle-structure diagnostic 报告，不能事后过滤。

Memory 状态不能写成“已修好”：v7 contract/gate 已构建，但尚未替换 v6 live runtime，也没有新 Qwen 输出。旧 MP20/ME12 只证明新 schema 能表达已知 failure modes，不证明 Qwen 会稳定遵守，更不是 held-out qualification。

下一合法顺序仍是：RS human semantics audit 与 memory runtime repair/held-out qualification并行完成；随后做 RS uptake 与 ESC-RANK runtime/evaluator qualification；研究者再显式 freeze `large_52`、`K=5 seed=0` 及必要身份；之后才可能分别申请 RQ1/RQ2 calibration unlock。

最终工程验证：Paper-1 CPU suite `669/669` 通过；RTX 2070 GPU-marked engineering suite `11/11` 通过；integration validator=`PASS` 且 `outcome_calls=0`；`git diff --check=PASS`。
