# 选择性 Memory：15 题独立来源开发候选

这批仅完成 CPU 准备，新增 G 调用为 **0**。已冻结 15 个真实来源任务、评价范围、四个选择策略，以及 30 个 STOP/MS 唯一请求。最终唯一请求包是 `independent-memory/packages-v3`，使用 Time-Lexical Top4；原 Top1 读口产物及旧评价草稿保留，不申请额外 Top1 生成。新包不在 SC36 的运行批准内。

“独立”仅指排除了 J06 的六个 owner 家族。新任务来自 **3 个已有开发暴露的家族、5 个来源情境**；这些家族已用于 Memory30/M36、S36，SC36沿用原S36任务。不能称未见来源或确认性测试。原 family closure 和 split 保留：仅复用已有隔离缓存的 91 个完整会话，重建并校验其原资源身份；没有读取混合全库正文或封存 fold6 正文。一个共享祖先家族的两个 owner 同时保留在缓存闭包中，跨 owner 内容不进入检索。

15 题为事实查询、自然支持、联合各 5 题，覆盖当前充分、历史缺失、当前部分充分、无需历史、时间更新/冲突未知各 3 题。它们是五个情境的相关变体，不是 15 个独立来源样本。没有找到可确认的同时态真冲突；更新案例只检验不同时间的报告阶段与事件身份未知，不制造矛盾。

事实通道使用自然语言，只评价问题明确询问的事实槽；自然支持只要求完成可见支持操作与边界，不要求复述全部背景。联合通道才同时要求明确的事实槽与支持操作。禁止捏造已完成、永久有效、相同事件等，不意味着答案必须逐字重复否认。引文与 JSON 都不是必需输出格式；若自愿引用，机械定位允许一次 HTML 实体解码，并区分报告日期元数据与说话人正文。源/题/参考、实际供应、评价记录分开保存。

生成前独立审阅曾澄清更新情境的逐通道范围；没有改题、换来源、调策略或看新任务输出。原 C1 文件逐字保留，另一个简单基线只检查当前可见文本中的固定历史请求词。所有四策略只复用同一题的 STOP/MS 端点，不重复生成。

|CPU 项目|实际结果|
|---|---:|
|任务 / 完整 STOP–MS 配对|15 / 15|
|CPU 端点路径 / MS 读取|30 / 15|
|MS 会话呈现 / 不同历史会话|60 / 23|
|未来来源、错 owner、截断|0 / 0 / 0|
|唯一请求 / 模型调用|30 / 0|
|全部请求输入 tokens|55,684|
|单请求输入 tokens 范围|106–4,356|
|实际运行上下文 / 输出上限|16,384 / 320|

原 As-of Ledger、SnapshotPrefixPort、ReadingView、C0 STOP 约束与 renderer 均实际经过读回验证。每次 MS 是一个有限动作，读取排序前四个**完整**合法历史会话，按时间顺序呈现；超容量整体失败，不截句、不用参考指定来源。最终 Top4 是沿用此前已选的工程基线，在任何新生成前固定；不调 k 或排序权重。30 路读口 CPU 合计 7.686 秒，含状态/mask/预估工作，不含 tokenizer 初始化及 Ledger 构建，不等同生产端到端延迟。

|策略|STOP / MS|选择后输入 tokens|已供应必要来源组 / 必要槽位|
|---|---:|---:|---:|
|固定 STOP|15 / 0|1,986|10 / 17|
|固定 MS|0 / 15|53,698|17 / 17|
|原 C1|2 / 13|46,623|17 / 17|
|固定可见词基线|7 / 8|29,507|17 / 17|

**17 是十个事实/联合任务中必要事实或证据要求的呈现槽位**，包括一个明确被询问的时序边界；不是 17 个独立事实、会话或家族。同一来源跨通道重复，不能将这一分母作为独立统计样本。上表只证明声明的来源组已送入输入，未证明 G 使用、理解或正确回答。五个自然支持任务没有全背景复述清单；其中一个历史主题任务在 Top4 下仍缺少可选个性化来源，可按原题允许的非回忆/一般支持路径作答。原 Top1 下三个同情境问题均缺该来源的结果保留，未换题。

最终两批保持每题 STOP/MS 完整配对，分别为前 8 题和后 7 题。请求身份与原 G/renderer 绑定，旧批准会被拒绝。每包独立最多一次加载、零 warmup、零自动重试，禁止收费 API；当前均未批准。

|申请批|唯一调用|输入 tokens|输出 token 上限|规划秒数 / 硬限|Plan 对象 SHA256|
|---|---:|---:|---:|---:|---|
|SMV1|16|28,907|5,120|612 / 1,200|`8b8398f8a833be257f1bef3e9121a5ba46239a2b7724e765374b7d4b1184fb52`|
|SMV2|14|26,777|4,480|548 / 1,200|`dedfc14ae1018f6dcfdf14ff5c00bef18b515d371927f1057fe052058edd4705`|

合计 30 次唯一调用、2 次加载、2,400 秒硬上界。规划采用原实际生成吞吐参考与保守 10 token/s、每包 100 秒 setup 情景；当前输入更长，规划秒数不保证完成。完整任务 ID、请求 SHA、两包 CPU 准入、冻结 executor 与 229 项输入绑定见私有 `packages-v3`。公开身份见 [RUN_REQUESTS.json](independent_memory_validation_v1/RUN_REQUESTS.json)。旧 `packages-v1`、`packages-v2` 及旧启动脚本仅保留历史；本次唯一申请为 `packages-v3` 的 **SMV1 / SMV2**。

固定 GPU：`GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`。固定模型：`Gemma-4-12B-it-707f0a3`，revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`；沿用原 G0e 自然语言生成、decode 和 renderer，不使用 SC36 的新语法约束。合计最多 **30 calls / 2 loads / 0 warmup / 0 retry / 2,400 秒**，每包独立 1,200 秒；不允许其他请求或收费 API。

|作业|完整 requests 文件 SHA256|
|---|---|
|SMV1|`e515277942817e1157bbfe3f1ca96fc4c8b1cee398c07724d6f1a52202cfb991`|
|SMV2|`30d3d7461231549c9e259ec067787ebb2f618f32fb85c0f1d7c40f8193e0dcfd`|

共同 executor inventory object SHA256：`d5ac6e2df91b1b10fd0c6ea15c37646cbcd87304d7d3ad3bc1ff1aa6598afc60`。

最终 catalog 文件 SHA256：`51470d87ec9af85e03a47a31baf45cf6a585a351480a0e6353c9e26649a702f8`。

新 plan 绑定评价完整性修复和其反例证据；30 行请求、任务、来源、策略和预算与上一包逐字保持。当前授权仍全部为 false，旧 SC/J/Memory 批准不能转用。审批后仅使用两个新入口（参数依次为该包批准文件和全新数据盘 run root）：

```bash
bash /opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126/independent-memory/RUN_SMV1_V3_AFTER_APPROVAL.sh NEW_SMV1_APPROVAL.json NEW_SMV1_RUN_ROOT
bash /opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126/independent-memory/RUN_SMV2_V3_AFTER_APPROVAL.sh NEW_SMV2_APPROVAL.json NEW_SMV2_RUN_ROOT
```


已生成 30 行未运行评价记录，每行绑定 task/request/payload/EvalSpec。validator 检查身份、原子范围、实际供应引文、输出精确引文、EOS/技术失败和未审状态；它不自动判断语义正确性。后续事实完成、支持操作、额外无源断言、主体/时间/阶段、拒答、未知和成本分别记录。语义审阅仍是未独立资格化的开发观察，`formal_reward=null`；合理拒答不算事实完成，空事实清单也不能自动使自然支持成功。

最终复核修复了一项评价完整性漏洞：旧程序未把额外断言、来源/参考争议传播到任务完成区间。已用两个合成反例复现旧 `[1,1]` 误收并验证新程序拒绝。**完整任务不允许额外无依据事实断言**：额外 `unsupported` 或确认违反要求的争议使区间为 `[0,0]`；没有其他确定失败时，额外 `uncertain`/`unresolved` 或未解决争议使区间为 `[0,1]`，不能确定通过。可选背景可以不复述，但不能借“可选”放过已观察到的错误断言。所有追加状态均校验枚举，空争议表也必须明确标为已审；程序只传播人工输入的开发观察，不自行解决语义争议。旧程序/模板/运行包保留，新运行身份只绑定修复后的评价器。题目、原 EvalSpec、来源、策略和全部请求逐字不变，未新增模型调用。修复记录见 [EVALUATION_INTEGRITY_REPAIR.json](independent_memory_validation_v1/EVALUATION_INTEGRITY_REPAIR.json)。

25 项测试通过，其中 20 项为合成边界测试、5 项读取上述隔离私有产物。覆盖封存 owner 拒绝、家族闭包、原文变异拒绝、完整 Top4 时点合法性、原查询/策略不变、运行输入隔离、自然支持范围和未运行评价不能伪成功。工程准入另有 5 项合成测试及两包实际 CPU check。公开逐题计数见 [TASK_COVERAGE.json](independent_memory_validation_v1/TASK_COVERAGE.json)；不含真实题目、答案、源文或回复。

本地复核使用已有私有根与固定依赖栈，不下载或加载权重：

```bash
export SMV_RUN=/opt/tokkio-data0/tokkio_runs/pmrl1-j-sc36-20261126/independent-memory
export PYTHONPATH=/opt/tokkio-data0/tokkio_runs/pmrl1-j-20261125/stack/project/src
SELECTIVE_MEMORY_VALIDATION_PRIVATE="$SMV_RUN" \
  /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q \
  project/tests/test_rl1v3_journal_selective_memory_validation.py \
  project/tests/test_rl1v3_journal_selective_memory_validation_run.py
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  project/scripts/rl1v3/journal_selective_memory_validation_run.py check \
  --plan "$SMV_RUN/packages-v3/batch-01/PLAN.json"
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  project/scripts/rl1v3/journal_selective_memory_validation_run.py check \
  --plan "$SMV_RUN/packages-v3/batch-02/PLAN.json"
```

已在新目录实际重建：任务、评价、策略文件和全部 30 行请求逐字一致。对新增公开材料的有限检查未命中 2,299 个私有长字符串；这不替代人工隐私审阅。

从已冻结设计重建任务与实际读口的完整命令保存在私有 `REPRODUCE_CPU.sh`；输出使用新目录，不能覆盖封存版本。`source-bundle-v3` 是当前源/规则身份，`requests-top4-v1` 是当前读口身份，`evaluation-preparation-v2` 含逐题可读来源、供应表、完整性契约与待审模板。公开聚合清单见 [MANIFEST.json](independent_memory_validation_v1/MANIFEST.json)。
