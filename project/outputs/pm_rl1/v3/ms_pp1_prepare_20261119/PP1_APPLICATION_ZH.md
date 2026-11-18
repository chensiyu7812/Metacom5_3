# MS-RAW PP1 GPU 运行前申请草案

**PREPARED_NOT_AUTHORIZED；本轮不执行。** 申请内容是 8 个固定前缀的 8 OFF + 8 RET-MS，共 **16 次**，没有 DP、warmup、Judge、NeedCard writer、训练或付费调用。对应 B #17 `3dafb2aa` 第 8.1 节的程序试点；只检验流程、表单和审阅耗时/一致性，不检验资源效应。本文件不宣布 B 协议已采用。

精确清单：`cpu_v2/REQUESTS_16.jsonl`。逐项原请求 SHA、PP1 admission SHA、token SHA、prefix/snapshot/frontier/来源绑定、G0e/decode/renderer/Step-2 均已给出；可读表见 `REQUEST_LIST_ZH.md`。整体 plan SHA 和文件 SHA 见 `cpu_v2/PREPARE_SUMMARY.json`、`cpu_v2/PP1_PLAN.json`、`cpu_v2/MANIFEST.json`。任何变更必须新建申请身份。

## 相同条件和身份

- 16 个 model_input 与原 G0e 请求完全相同；这次重新运行原生 CPU 分词并逐 token 核对。原 request_id/TerminalKey 保留，PP1-admission 是另加的运行许可和审计身份，不能用来导入旧响应/reward。
- 统一为 G0e HF、Gemma-4-12B-it revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`、原 G0e Notes renderer、相同系统提示与当前 prefix、no-plan Step-2；greedy、seed 0、batch 1、max_new_tokens 320。详细 EOS/pad/suppress 参数原样保留。
- RET-MS 保留原 lexical-v0 Top-1 完整 RAW 和正文；没有重新优化排名。DP-MS 尚未独立选取/人工确认，因此只给出 8 个 pending proposal，payload/token IDs/request_id 均为空，不在这 16 次中。
- #18 的 direct renderer 与其 63 份预览完整保留。本次没有把新 renderer 夹入旧 16 个输入，也没有把旧 RET 改名为 DP。

## 加载与容量

指定单张 A6000，UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`；只使用获准的本地 HF 环境（Python 3.12.14、torch 2.7.1+cu128、transformers 5.17.0、tokenizers 0.23.2），bf16、SDPA、TF32 关闭、确定性设置和原 decode 不变。模型路径、全部文件字节/hash、运行参数在 `BASELINE.json` 和 plan 中。HF 的 vLLM 包存在不代表使用 vLLM；不替换架构或设备。

获准后的顺序：最终 integration/executor/code 与请求清单验证 → 独占锁/设备空闲及至少 40 GiB free → 全部模型文件新鲜 SHA → A12 checkpoint header/shape/software pin 守卫 → `AutoModelForMultimodalLM.from_pretrained`（local_files_only、trust_remote_code=False、ignore_mismatched_sizes=False、output_loading_info=True）→ 验 missing/unexpected/mismatched/alias/meta → 移到批准的单张 GPU 并 eval → 再核全部 native IDs → 按清单一次执行。不能运行原 A0 批次来代替此 16 次清单；A0 实测需单独已有授权/收据，不计入或暗增 PP1。

输入 **137–1766** token，加 320 输出最多 **2086**，均小于 HF runtime 16384。权重文件约 **22.28 GiB**；不折扣 sliding window 或 K/V sharing 的保守 KV 计算约 **0.668 GiB**。峰值规划 **26–36 GiB**，其激活、加载、allocator 余量是估计，不是 GPU 实测。启动至少 40 GiB free、运行至少保留 4 GiB；不占用或终止其他项目进程，不自动换卡/量化/后端。

B 原稿估计加载 3–5 分钟、16 次合计约 5 分钟；本申请规划总计 8–20 分钟，**未实测**。每请求 timeout 300 秒，加载最多 600 秒，全阶段硬上限 1200 秒。16×300 秒本来可能超过全局上限，故全局上限优先，到时保留未执行后缀为 pending。不能把“<20 分钟”当作完成承诺，也不能以 CPU 分词耗时代替吞吐。

## 停止与日志

缺授权/B 回执/集成验收、载荷或身份不符、泄漏、加载失败、OOM、timeout、空输出、设备争用/显存不足、总时限：停止自己的任务。`finish_reason=length` 原样保存为 truncated，不重问；累计第 **3** 个 length 即停止（>2/16）。质量差、未引用历史、误用或不恰当建议是后续评价对象，不是自动重生成/删样理由。

`PP1_LOG_SCHEMA.json` 定义清单/许可/代码/模型/硬件/载荷身份，LOAD、START、RESULT、FAILED、FINISHED 事件、token IDs/原始文本、finish_reason、显存与本地耗时。START 必须在物理调用前原子落盘；记录存在但结果不明时拒绝重试。新的 PP1 日志目录独立，不读取旧 reward/result；日志里的原文/臂身份与匿名人评材料分离。CPU reference 状态机已检查顺序、重复、未完成请求、三次 length 和技术失败停止；持久执行器仍须在实际 integration 的最终 SHA 上由 B 验收。

## 执行准备清单与最小决定

已完成：固定 8 prefix、原 16 载荷和原生 token 身份、完整来源/双 horizon/可见投影清单、可复跑 CPU 核查、owner 抽查、独立 DP 审阅池、运行参数/预算/停止条件/日志规范。

待完成（职责明确，不扩大到四资源）：

1. **原 WS-B**：#18 与本次 16 载荷的独立回执；本次 A 检查不替代。B 当前回执状态见 `B_REVIEW_STATUS.json`。
2. **B/指定人工整理者**：仅 8 个前缀的 S 筛查及条件独立 QH 背景，安排两名审阅者。A 提供全部合法 RAW；不把 RET/DP 选材当背景。人工审批数仍为零。
3. **integration owner 与 A/B**：依推荐链完成获准集成、真实 G0e 绑定及最终执行器/加载守卫接线验收；补 A0 已授权实测。尚不声称本申请可以直接调用现有 A0 runner。
4. **研究者的最小决定**：确认 PP1 仅程序用途的协议版本、结果是否并入后续分析及其事前规则；指定筛查/QH 整理与两位审阅人；上述收据齐全后，明确批准绑定最终 plan/request/executor SHA 的单次 16 调用（沿用既有来源研究复用范围，完整上游许可仍未解决）。这不是本轮已获得的权限。

DP 的独立选材是未来 OFF/DP/RET 比较前置，不是本次 OFF/RET PP1 前置。43 条 MP/ME、原五项人工标注、RS METHOD/CASE、MS-SUM、完整四头 RAG 均保持独立资格，不阻塞 MS-RAW 材料准备。现有 8 个 owner/前缀不因历史看过而排除；必须登记检查、设计、调参和结果使用，禁止根据待报告结果调参、换样或改评价标准。
