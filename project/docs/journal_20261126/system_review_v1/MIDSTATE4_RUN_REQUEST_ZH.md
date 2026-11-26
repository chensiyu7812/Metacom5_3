# MIDSTATE4 明确运行申请：两个恢复状态 × 两个终局分支

状态：**CPU 准备完成，等待此新包的明确运行授权；尚未启动 GPU 或加载权重。** 原 DR1–DR4 授权及旧 STOP 输出不转作本包授权或物理结果。仅提交以下 4 次终局生成，不申请新控制器调用、训练、重试或自动后续运行。

## 冻结范围

| 顺序 | 原预选任务 | 恢复后动作 | 实际 G 输入 tokens | 真实终局上限 |
|---|---|---|---:|---:|
| 1 | T01 | STOP | 355 | 1 |
| 2 | T01 | 原观察 rank-1 hit EXPAND → STOP | 1034 | 1 |
| 3 | T03 | STOP | 356 | 1 |
| 4 | T03 | 原观察 rank-1 hit EXPAND → STOP | 1092 | 1 |

保持原 goal、turns、已读源、handles、剩余预算、合法动作域、原 G、renderer、tokenizer、decode 和评价合同。每个分支独立完整重放至相同已恢复状态，再执行固定动作；没有查询 gold 来选 hit。全部候选的 CPU 来源增量、重复与可达性见 [MIDSTATE_CPU_DIAGNOSTICS_ZH.md](MIDSTATE_CPU_DIAGNOSTICS_ZH.md)。

私有包：`/opt/tokkio-data0/tokkio_runs/pmrl1-j-system-review-20261126/midstate/package-v4/`。

| 身份 | SHA256 |
|---|---|
| PLAN 对象（审批绑定） | `4276bf86e6e1012092018aeb6b0a8b82a9544988f74cc5c407919740b7b1e9b0` |
| PLAN 文件 | `509fb47e1cd9e83a42f7712c0664d5f68686ccff5f97e6c561b4887608110ba3` |
| REQUESTS_PRIVATE.jsonl | `64e5a8ca854e9381bd0d14508e4bff2661c36a2407e209bb4eb4f6a2fbe786e6` |
| RESTORED_STATES_PRIVATE.jsonl | `3c51b729d2a7d68234cb16a132bdf26393946ddd67aa31c4298f60803ba05398` |
| executor inventory 对象 | `e4451cbae935d07bea31a134ed42e91069a8abdaa74188297771105024f7ca97` |

完整 4 个 frozen request ID、payload SHA、原依赖和逐文件 executor SHA 均已写入该包，无待补 prompt 或动态选题。传给旧 worker 的外层请求另外绑定实际 boot/deadline/ordinal，因此运行时外层 request SHA 会新生；其 frozen request ID 与完整 payload 必须逐项匹配上述白名单。

## 预算、执行与拒绝边界

- 同一既有 Gemma-4-12B-it 固定 revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`、HF、原 GPU UUID，最多 **1 次模型加载、0 warmup、4 次 terminal、0 controller、0 retry**。
- 整包硬限 **1200 秒**，包含审批后模型字节核验、源启动、模型加载、恢复和 4 个分支；load 最多 600 秒、单请求最多 300 秒，均受全局剩余时间约束。没有 GPU 自动替换或空闲等待重试。
- 原 G decode 完全保留，最多 320 输出 token；任一终局 length、空输出、身份/时钟漂移或技术异常即停止整包，不补跑剩余端点、不改提示词。未执行与技术失败保持独立空质量。
- 新 supervisor 强制唯一四项 ordered allowlist；原通用 worker/guardian 原样复用。旧 worker 的通用 22-call 内部边界没有被改写为本包授权，本包更窄的四次边界由绑定的新 supervisor 执行。独占锁、设备/存储守卫、父进程死亡及截止时间 kill、稳定原状态 scope 的一次性 claim 同时保留。
- CPU `check` 验证原依赖、613 项原 executor 文件未变、新模块/脚本、requests/states、rank-1 动作及完整预算；准备和检查没有读取权重或访问设备。真正的模型字节核验与加载只在新明确授权通过之后运行。

新运行入口为冻结 executor 内 `journal_run_pomdp_midstate.py run --plan …/PLAN.json --approval … --run-root …`，新授权 `protocol=pmrl1-j-restored-midstate-four-v1`、`job_kind=JOURNAL_RESTORED_MIDSTATE4`，须绑定上述 PLAN 对象 SHA、4/1/1200/0/0 预算及实际研究者批准证据。单纯存在 PLAN 或 CPU_READY 不构成授权。

## 真实时间与解释边界

每个分支先重放并核验原状态。`BRANCH_DECISION_START` 在恢复核验完成后记录同一 Linux boot 的 `CLOCK_MONOTONIC`；起点后真实执行 EXPAND/STOP、合法性检查、packet/tokenization、运行守卫、worker 往返与 G，至终局验证结束计 `decision_to_validated_reply_ns`。恢复 replay、模型加载与整包时间单列；恢复不假装零成本，也不计入这个已恢复决策点条件下的分支时间。

源池沿旧运行路径预先在内存构建，故 EXPAND 测的是该已有内存池的实际展开/校验/表示成本，不声称外部网络读取或冷磁盘获取。无 terminal cache、无旧响应或旧延迟复用；两个 STOP 都需要新物理生成。没有独立日志跨度则 logging cost 留空，client TTFT 仍未观测，首非空文本不宣称语义有效。

每个成功分支还直接保存从决策起点到 worker 的 `first_generated_token`、`first_non_special_token`、`first_nonempty_decoded_text` 的实际单调时间差；缺少事件则留空，`client_ttft_ns/useful_text_ttft_ns` 始终为空。后端调用异常单独写 `MODEL_REQUEST_FAILED`，包含 request ID、实际调用耗时、已有 failed-wire 文件绑定、未观测部分输出为空及零重试。若守卫自身失败，只有全局停止记录而无完整守卫失败跨度；此时相应耗时仍未知，后续 collector 从原 journal 保留此前已完成分支，不能因 summary runtime 为空将它们抹掉或把缺失成本补零。

固定顺序、一次加载、零 warmup 使 T01 STOP 成为首个真实推断；worker 保留 `first_inference_after_load`。因此四个实际时间只作有限条件下观测，不能当作无冷启动/顺序混杂的因果延迟差，也不估 p95。最多检验两个指定状态的 rank-1 展开是否改善原任务；不能证明全动作最优、完整 POMDP 无用或可直接启动 PM/RL 训练。原 5 项真人待裁决状态、评价 unknown 与 formal reward 空值均保持。
