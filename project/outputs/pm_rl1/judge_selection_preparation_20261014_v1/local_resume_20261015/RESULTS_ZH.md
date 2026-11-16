# PM-RL1 原 Gemma A/B 首轮接续结果

生成时间：2026-10-15T11:28:02.679130+09:00。本轮已停止，等待研究者审阅。**原 8 项中 A/B 各开始 1 项，共 2 次；两次均为完整输出的严格 JSON 解析失败，余下 6 项按既定 STOP 未派发。累计 66＋2＝68/140。** 原批准的新增 8 次／累计 74 次上限未提高、未重置。

## 接续身份与工程边界

仓库真实路径 `/opt/tokkio-data0/tokkio_projects/Metacom5_3`，分支 `work/paper1-rq1-integration-20260816`，HEAD `0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28`。四配置 plan `d8671e36f5ea83eb6813225553c2c9141f48d690e9cd15bd335fce1154595e8e`；原实现 `474555b605e4108e91fe1d2ebba9eb4c32795ec61fdab1582ac061993539cfba`；独立工程接续代码 `57fdb5cf99a1286c789808e2ed2141cb9f2cc4884fcfec63955cac2161753661`。原合同 SHA256 `fccc28f6f014782876a0083a346129558abf62e64923b4021825e56463104b60`。原 608 个交付文件、上轮 30 个回执文件、既存 9 个工作文件均哈希不变。

原阻塞阶段 `live_runs/engineering.AB.stage_result.json`（SHA256 `427fdec76f0b6d81f854e0baf9f705f5520ae6713de1a8c10126164dbee7944b`）保留。接续 `_01` 保存诊断中断历史，`_02` 保存这两次实际执行；二者均绑定原父阶段、批准、请求清单，后者还关联前者。没有新实验、新抽样或新增额度。原 8 项仍属于各配置原 40 次开发清单。

模型 `google/gemma-4-12B-it`，revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`，A `enable_thinking=False`，B `True`。共用已校验权重，BF16、SDPA、greedy、原环境、单卡 A6000 UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4` 均不变；未重下载、未安装依赖、未量化、未改提示或评分。实际输入长度分别 28,187／28,185，与先前完整原生模板回执相同；上下文 262,144、最少输出预留 32,768，未静默截断。各配置完整参数在 `results_private.json` 的 planned/executed_configuration 中；冻结配置里的旧 readiness 描述仍保留，实际可运行状态以本次 artifact_preflight 与结果为准。

## 八项完整状态

|原顺序|配置|题号|状态／未派发原因|正式 q / m / U|输入 tokens（实际；未派发为预检）|
|---:|---|---|---|---|---:|
|1|A|dev02B|已开始；完整输出解析失败，配置停止|null / null / null|28187（实际）|
|2|B|dev02B|已开始；完整输出解析失败，配置停止|null / null / null|28185（实际）|
|3|B|dev15B|未派发：该配置首项失败，保留 STOP|null / null / null|16999（预检）|
|4|A|dev15B|未派发：该配置首项失败，保留 STOP|null / null / null|17001（预检）|
|5|A|dev37A|未派发：该配置首项失败，保留 STOP|null / null / null|20379（预检）|
|6|B|dev37A|未派发：该配置首项失败，保留 STOP|null / null / null|20377（预检）|
|7|B|dev37B|未派发：该配置首项失败，保留 STOP|null / null / null|20375（预检）|
|8|A|dev37B|未派发：该配置首项失败，保留 STOP|null / null / null|20377（预检）|

未知运行失败、超时、输入／输出截断均未观察到；正式解析失败 2 次，未派发 6 项单独列出。没有正式语义分数，不能把缺测当 0，也不能把未派发项计为模型失败。失败请求保留 started/raw/response/result 四件记录，未重试；两个 STOP 均保留。

## 完整输出、计量与绑定

|配置|单次耗时 s|生成路径 s|输出总 tokens|thinking / final / format|峰值 allocated / reserved bytes|自然结束|
|---|---:|---:|---:|---|---|---|
|A|102.104192|102.091279|664|0 / 663 / 1|39844562944 / 44660948992|是，EOS 106|
|B|133.014091|133.002148|1105|490 / 610 / 5|39843838976 / 44660948992|是，EOS 106|

两次最终内容都以字面量 Markdown ` ```json ` 围栏起始，以围栏结束；原生处理器成功分离通道并自然结束，但冻结的 `judge_completion.parse_completion` 对完整 final 严格 `json.loads`，报 `Expecting value: line 1 column 1 (char 0)`。失败归类为解析失败，并非超时、输出未完或语义不确定。没有去围栏、截取内层 JSON、填补分数或修改解析器。原文内任何数字均未写成正式 q/m/U。

- A：request `c4cf390ab7cf88c0b71712dd6e208ddda40614520a47dc67d587807a04c362ea`；配置 `451be1e2cf2c735b122710ddf3f723108be286702d18c5dd435870e7ae6f5002`；原始输出文件 [A raw](../live_runs/gemma4_12b_bf16/c4cf390ab7cf88c0b71712dd6e208ddda40614520a47dc67d587807a04c362ea.raw.json)，完整原生解析输出与理由／引用 [A response](../live_runs/gemma4_12b_bf16/c4cf390ab7cf88c0b71712dd6e208ddda40614520a47dc67d587807a04c362ea.response.json)。
- B：request `d2c0cf8756dc0e02f290b2114439f4f90847c64999ec44858a7a3ffddfbe5ff5`；配置 `393a13d52203691d2a6e0019d3f5936041687c8e63119c01701f22133af4d387`；原始输出文件 [B raw](../live_runs/gemma4_12b_bf16_thinking/d2c0cf8756dc0e02f290b2114439f4f90847c64999ec44858a7a3ffddfbe5ff5.raw.json)，完整原生解析输出与理由／引用 [B response](../live_runs/gemma4_12b_bf16_thinking/d2c0cf8756dc0e02f290b2114439f4f90847c64999ec44858a7a3ffddfbe5ff5.response.json)。

两项共用 dev02B 输入／回复绑定：messages `f0d80377ac3152b0219ca572ac7291f5cb61ceba09073e8fae556afe750fba30`，schema `2bc2a7eef0af9a3981ade8fbb6d03097cd56f88a1589a0b2ff05ed98a0c4a94e`，回复 SHA256 `d5d2feace80d57f635cb1424570f5ffd4fe3d9c9ef39dfc7c58d73c0a23819a7`，合法来源 `17c742c775ac1f9bd9ad395a0c8790ca3cd43b3eda811238e99519c9a5bb7151`。全部 8 个完整 request/config/input/reply/evidence 身份与原始文件哈希见 [results_private.json](results_private.json)；可直接查看的逐项表见 [eight_slots_private.csv](eight_slots_private.csv)。原始完整来源保留在固定 plan，不向外发送。

生成路径耗时 A 102.091279 秒、B 133.002148 秒，合计 **235.093427 秒**；共享加载一次 **10.235682 秒**，从共享加载入口至阶段完成的驻留窗口 **251.159757 秒（约 4.186 分钟）**。这是 runner 实测墙钟区间，包含相应前处理／查询／同步开销，不是 CUDA 内核活跃时间或利用率积分；共享加载与驻留时间不按 A/B 重复相加。最大 allocated 约 37.108 GiB，reserved 约 41.594 GiB。校正后的进程整体墙钟 285.492392 秒（含文件核验、前检与退出），退出码 0。

本轮新增 API／付费调用费用 **0 美元**，下载流量 **0**；上一轮唯一下载的 23,951,746,871 字节不重复计费。未提供本机 GPU 电价或租赁单价，不能把 GPU 时间换算成实际货币成本；能耗未测量。既有共享付费账本仍为 1.50724291 美元、未结责任 0，账本哈希不变。旧两轮请求／原始输出／测量重新核对各 33；新池真实 started 恰为 2，无孤立记录、无重复派发。详见 [最终完整性审计](final_integrity_audit.json)。

## GPU 守卫与诊断

未改变加载前空闲显存至少 45,000 MiB、利用率恰为 0% 的条件。原 `selection.py` 一次查询和笼统拒绝缺少日志；新独立入口精确匹配 UUID，并保留每次 GPU CSV、计算进程 CSV、完整 NVIDIA XML 的原始 stdout/stderr、退出码、时间、进程与明确拒绝原因。查询失败、解析失败、进程信息不可见与成功空列表分开处理。

|接续／检查|开始—结束（JST）|空闲 MiB|利用率|可见 PID|结果／拒绝原因|
|---|---|---:|---:|---|---|
|01/0001|11:15:26.427—11:15:35.481|48551|2%|未列出|utilization_not_zero, process_visibility_context_unreadable|
|01/0002|11:15:45.483—11:15:54.128|48551|2%|未列出|utilization_not_zero, process_visibility_context_unreadable|
|01/0003|11:16:04.130—11:16:12.894|48551|2%|未列出|utilization_not_zero, process_visibility_context_unreadable|
|01/0004|11:16:22.896—11:16:32.155|48551|2%|未列出|utilization_not_zero, process_visibility_context_unreadable|
|01/0005|11:16:42.157—11:16:50.935|48551|0%|未列出|process_visibility_context_unreadable|
|01/0006|11:17:00.937—11:17:10.168|48551|2%|未列出|utilization_not_zero, process_visibility_context_unreadable|
|01/0007|11:17:20.170—11:17:28.838|48551|0%|未列出|process_visibility_context_unreadable|
|02/0001|11:18:28.185—11:18:39.062|48551|0%|未列出|通过加载前原空闲条件|
|02/0002|11:18:54.499—11:18:54.776|25157|0%|619502|通过驻留模型进程检查（仅本进程）|
|02/0003|11:18:54.789—11:18:55.071|25157|0%|619502|通过驻留模型进程检查（仅本进程）|
|02/0004|11:20:36.894—11:20:37.193|5631|75%|619502|通过驻留模型进程检查（仅本进程）|
|02/0005|11:20:37.206—11:20:37.446|5631|0%|619502|通过驻留模型进程检查（仅本进程）|

原只读等待窗口从 **11:15:26.427950** 到 **11:20:26.427950 JST**，校正后在 **11:18:39.062832** 完成通过检查，未重置 5 分钟。初版新增辅助 `/proc/1/ns/pid` 检查时错误地把 PermissionError 设为拒绝；这不是 NVIDIA 进程查询失败。该工程错误已纠正为单列可见性限制，第一版代码和全部 7 个检查不删除。只对明确匹配的本轮自有等待进程 PID 618955 发出 SIGINT，发生在无模型请求的 sleep 间隔；同学和其他用户进程未被操作。见 [工程修复记录](ENGINEERING_REPAIR_ZH.md) 及 `diagnostic_interrupt_receipt.json`。

12 次执行检查的 36 条 NVIDIA 查询全部成功；初始空列表仅代表查询当时未列出进程，不证明不存在隐藏／瞬时／随后出现的任务。加载后 4 次只列出本轮模型 PID 619502；驻留阶段沿用原排除其它进程的守卫，模型自身显存和负载不重复按加载前阈值检查。没有以“未列出进程”推断 2% 负载的来源，也没有放宽阈值。

退出后另做一次只读结尾观察（不用于派发，也不是新的等待窗口）：2026-10-15T11:24:38.750976+09:00，空闲 48551 MiB、利用率 2%，进程查询成功且未列出进程，按原空闲规则仍会拒绝此时加载；本轮模型进程已退出。原始回执在 `post_run_read_only/gpu_check_0001.json`。执行前检的全部原始输出在两个 `live_runs/continuations/.../gpu_check_*.json`；本报告不把结尾观测覆盖到执行前的事实。

## 语义复核范围与下一步

仅查看两次已完整结束的 final 文字，作为本地诊断；不修复正式解析、不把思考片段当评分，也不计为新独立人评。两者均把帮助他人的动机与脆弱感归给当前 seeker/user，并引用 C:T006；该条直接支持这两点。但 dev02B 不覆盖 dev15B 的“朋友／历史支持者／新 AI”主体陷阱。dev15B 未派发，主体陷阱检验仍待原清单。

可见的诊断问题：A 将 R001–R003 标为 supported 并引用 C:T006；B 将全部五个单元标为 non_factual。R003 同时包含一般支持和对用户个人动机的具体陈述，B 的理由一方面承认其反映用户已表达的动机，另一方面否认个人事实断言；这与冻结的混合断言检查要求存在不一致，至少缺少按该要求展开的解释。它只是一条已观察到的语义诊断，不转化为 m/U，也不据此排名。完整锚点和绑定见 [semantic_diagnostic_private.json](semantic_diagnostic_private.json)。

dev37A/B 等义对照均未派发，不能以本次 A/B 同一回复的差异冒充等义测试；第 35 题及其它风险留在原开发清单，没有临时加题。工程上已证实权重／环境／指定 GPU 可以加载并完整生成，尚不具备按冻结接口持续得到正式评分的条件。两配置停止，奖励资格未建立，不能宣称准确或获胜；DeepSeek C/D 未运行，不作四配置排名。

**最小下一步是先审阅这两份完整格式失败记录，决定是否另行批准仅针对外层格式的接口修正及其后续执行范围。** 本轮未实施该修正、未解除 STOP、未重算这两次分数，未运行任何恢复请求。工程守卫修订与裁判语义修订分别记录：本轮语义修订增量 0，总数仍为 1。余下开发、冻结、封存 24 对、12 次复评、自然任务训练和两层联合训练均未启动。没有提交、推送或上传任何材料。

测试：先于实际模型请求完成 53 项离线测试（20 项接续／守卫，33 项原 runner），覆盖阻塞后接续、跳过已开始／已完成、孤立输出保守计数、不可覆盖、失败配置停止而同伴可继续、同学计算／图形进程导致阻塞、查询异常与可见性、阈值不变及 5 分钟上限；日志 [tests_corrected.log](tests_corrected.log)。工程入口与测试位于上级 `resume_engineering.py`、`test_resume_engineering.py`，不修改原执行器或裁判。
