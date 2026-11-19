# PP1 最终运行前验收（仅准备）

B [固定 #19 回执](https://github.com/chensiyu7812/Metacom5_3/pull/19#issuecomment-6985130856) 已确认 16/16 精确载荷、原生重分词、owner/严格过去时间、RAW 完整性及可见内容。#20 4624600d 的 PP1 候选协议 SHA 为 b23b91eb2a9d9abf849d481f5952d591abfd5fea8ec55f0bdcffb28da987d2e3。这两份证据不授权执行，也没有独立审查本轮新执行器。

| 项目 | 当前证据 / 状态 |
|---|---|
| 固定请求 | 直接读取 #19 原文件，不生成替代 PP1 文件；SHA 9af4a17328c3bf730899d3724452a06a7929e63962b7c2ef09319a168722226c |
| 顺序 | p15、p16、p13、p2、p8、p11、p5、p3；每 owner 先 OFF 再 RET-MS |
| 原生输入 token | 326/1087、162/1022、795/1766、750/1561、137/900、251/1168、678/1406、446/1115；每次另留 320 |
| G/decode/renderer | 与 A0 的完整 baseline 相同；原 G0e Notes、no-plan、greedy/320；无 DP |
| 精确计划 | cpu_v2/PP1_PLAN.json 的 request IDs 顺序、文件 SHA、执行器 HEAD/hash；IDENTITIES.json 汇总 |
| 执行器 | 新 isolated supervisor；精确白名单只送 messages/input_ids/decode；native retokenization 再校验；不调用在线 BoundEpisode/ReplayCache |
| 次数 | 1 load、0 warmup、最多 16 physical calls、0 自动重试；与 A0 4 次独立 |
| STOP | 首个技术失败立即停；第三个 length 保留原响应并停止；总硬预算 1200 s，load600 / 单次300 均受剩余总预算约束 |
| 日志 | 先持久 START，再调用；保留原返回、EOS/length、input/output tokens、时间、显存、链式事件 SHA；未知完成与未运行尾项 pending，length 另记 truncated_pending |
| 去重 | 全局独占锁、一次授权 claim、唯一新 job 目录、无旧输出缓存命中；重复授权/目录不重入 |
| 来源 | 加载前执行 #19 check_bundle：8 个绑定、16 snapshots、双 horizon、RAW/owner/family/frontier 和旧载荷核对 |
| 模型加载 | 与 A0 一致。任何兼容性失败都停，不切换 vLLM、模型或精度 |
| 资源 | A6000 空闲门槛 40 GiB；所有临时/缓存/日志在数据盘；root≥1GiB、data≥4GiB。当前 root 未达门槛 |
| A0 | 必须是独立获准且成功的 4 次真实 HF 作业收据，baseline 相同；CPU fixture 不能代替 |
| B/人评 | 固定输入已签收；新执行器待审。8 份统一 QH 背景已有，但人工确认/冻结、筛查、1 名整理者+2 名审阅者与工具仍待 B/研究者闭合 |
| 运行授权 | 尚无针对最终交付 HEAD、PP1 plan SHA 与这 16 次调用的研究者授权 |

沿用 B 约 11 分钟的未实测估计，硬上限 20 分钟；fresh hash 也占总预算，实际不足则停止，不能加时补齐。预计显存 26–36 GiB 仍为估算。A0 的最短/最长 OFF 诊断不等于已实测 PP1 全部上下文成本。

每作业单独的 JSON 模板明确 authorized=false。签署时必须填实际最终 checkout HEAD、研究者与可核查的决定链接、G0e 路径、执行器复核证据，并且 PP1 填已批准协议 SHA、固定筛查/QH SHA、人员工具证据及 A0 成功收据路径/hash。没有把权限从文件或上一作业自动传递。

预检命令（CPU，环境见 RUNBOOK）：

~~~bash
python project/scripts/rl1v3/limited_g0e_run.py check \
  --plan project/outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/PP1_PLAN.json
~~~

本轮不执行 run。engineering_ready 仅表示 CPU 材料和机制状态；research_qualified=false、authorized=false。
