# Gemma A/B 本地首轮执行结果：前检阻塞

时间：2026-10-15（Asia/Tokyo）；执行入口 02:08:45–02:09:37 JST。**8 个计划项均未派发，真实评分 0 次。** 本文为本地私人明细，不用于上传。

## 接续与协议核验

真实仓库 `/opt/tokkio-data0/tokkio_projects/Metacom5_3`；分支 `work/paper1-rq1-integration-20260816`；HEAD `0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28`，未变化。已读取根目录及 RL1 命名空间 AGENTS、控制合同、可行执行方案、最新四配置协议／预算／执行清单及验证记录。旧两配置目录保持历史。原 9 个未跟踪文件保留。

四配置 plan：`d8671e36f5ea83eb6813225553c2c9141f48d690e9cd15bd335fce1154595e8e`；implementation：`474555b605e4108e91fe1d2ebba9eb4c32795ec61fdab1582ac061993539cfba`。当前 33 项 runner 单测通过；原交付 608 项文件哈希一致。旧每轮 33 条 request/raw/measurement 逐 ID 对应，首轮 SQLite 33 项也对应；旧合计 66，新池无已有 live started 记录可复用。一次语义修订以现有 protocol 与运行产物核对，未新增。

## 权重、环境与输入

使用现有 paper1-judges-py312 环境：Transformers 5.17.0、torch 2.7.1+cu128、tokenizers 0.23.2、safetensors 0.8.0。无依赖安装、量化、换卡或提示修改。官方元数据当次读取为非 gated，七个必要文件与冻结元数据一致；无需接受新增协议。

一次下载至 `/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3`，共 23,951,746,871 字节（其中权重 23,919,549,408 字节），约 229.76 秒。固定 revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`；权重 SHA256 `5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d`。两配置文件校验通过。下载只请求公开模型文件，没有向 HF 或其他第三方发送研究材料。

A/B 各 40 个原定完整输入只作本地 tokenization；最长 A 28,187、B 28,185。原生上下文 262,144，预留输出 32,768；预留不是生成截断上限。没有裁剪来源或额外评分。每项输入长度、消息/schema 哈希及原回复 SHA256 见下表与 JSON。

## 八个计划项完整状态

共用模型 google/gemma-4-12B-it、固定 revision、BF16、SDPA、greedy、900 秒技术保护和原解析器；仅原生 enable_thinking 不同。表内配置均为**计划配置**：实际没有加载或推理，不能称已执行配置。首四题保留于各自 40 项清单。

| 本地顺序 | 配置 | 题号 | 原生输入 tokens | 状态 | q / m / U | 耗时、输出 tokens、显存峰值 |
|---|---|---|---:|---|---|---|
| 1 | A / thinking=False | dev02B | 28187 | 未派发：GPU 前检拒绝 | null / null / null | 不适用，未推理 |
| 2 | B / thinking=True | dev02B | 28185 | 未派发：GPU 前检拒绝 | null / null / null | 不适用，未推理 |
| 3 | B / thinking=True | dev15B | 16999 | 未派发：GPU 前检拒绝 | null / null / null | 不适用，未推理 |
| 4 | A / thinking=False | dev15B | 17001 | 未派发：GPU 前检拒绝 | null / null / null | 不适用，未推理 |
| 5 | A / thinking=False | dev37A | 20379 | 未派发：GPU 前检拒绝 | null / null / null | 不适用，未推理 |
| 6 | B / thinking=True | dev37A | 20377 | 未派发：GPU 前检拒绝 | null / null / null | 不适用，未推理 |
| 7 | B / thinking=True | dev37B | 20375 | 未派发：GPU 前检拒绝 | null / null / null | 不适用，未推理 |
| 8 | A / thinking=False | dev37B | 20377 | 未派发：GPU 前检拒绝 | null / null / null | 不适用，未推理 |

每项均无模型评分理由、模型引用或原始输出；这些字段明确留 null。不是 uncertain 评分，不是超时、截断或解析失败，也不是语义失败。没有已开始评分需要恢复，没有补分、补零或从片段提取分数。

### 输入／回复身份

- A / dev02B：request `c4cf390ab7cf88c0b71712dd6e208ddda40614520a47dc67d587807a04c362ea`；seed `1589814349`；全池顺序 `1`。
  origin_job `48943d027a25c8aeb220a104a9d5f795a8ebacf1887fe289e00c8f0195b245c9`；reply SHA256 `d5d2feace80d57f635cb1424570f5ffd4fe3d9c9ef39dfc7c58d73c0a23819a7`。
  messages `f0d80377ac3152b0219ca572ac7291f5cb61ceba09073e8fae556afe750fba30`；schema `2bc2a7eef0af9a3981ade8fbb6d03097cd56f88a1589a0b2ff05ed98a0c4a94e`；legal evidence `17c742c775ac1f9bd9ad395a0c8790ca3cd43b3eda811238e99519c9a5bb7151`。
- B / dev02B：request `d2c0cf8756dc0e02f290b2114439f4f90847c64999ec44858a7a3ffddfbe5ff5`；seed `1589814349`；全池顺序 `2`。
  origin_job `48943d027a25c8aeb220a104a9d5f795a8ebacf1887fe289e00c8f0195b245c9`；reply SHA256 `d5d2feace80d57f635cb1424570f5ffd4fe3d9c9ef39dfc7c58d73c0a23819a7`。
  messages `f0d80377ac3152b0219ca572ac7291f5cb61ceba09073e8fae556afe750fba30`；schema `2bc2a7eef0af9a3981ade8fbb6d03097cd56f88a1589a0b2ff05ed98a0c4a94e`；legal evidence `17c742c775ac1f9bd9ad395a0c8790ca3cd43b3eda811238e99519c9a5bb7151`。
- B / dev15B：request `ba358344ad688a3ff84cdd6dd8d6e343f5491b34e5c75fa3abe6d1b379a58e4b`；seed `3485033069`；全池顺序 `5`。
  origin_job `3474491d9f3ec8280132cc1034886865d9ddb14364d0e44f5bec67983626283d`；reply SHA256 `0229cd6adcded5a7082ace51b60fd17ccbe7ec0816670dafcce687120a27cbe5`。
  messages `b541f867fe73507f59d1300aa70bc56cb5ffa9f2370885ce0c9a932879d8f3fe`；schema `0c1163b9008d6abb2db9b9ef79819f95da2b752b6cec9375ce859676e30d8d73`；legal evidence `e1eb5ab571b184bf88f3f7c6ecb685de2d94b2cc8cad9e67b00e4b8f9ca94640`。
- A / dev15B：request `55131330e98f3f673a02e446ccdac642d0b09b9d919ff79386a09fae04cc61f1`；seed `3485033069`；全池顺序 `6`。
  origin_job `3474491d9f3ec8280132cc1034886865d9ddb14364d0e44f5bec67983626283d`；reply SHA256 `0229cd6adcded5a7082ace51b60fd17ccbe7ec0816670dafcce687120a27cbe5`。
  messages `b541f867fe73507f59d1300aa70bc56cb5ffa9f2370885ce0c9a932879d8f3fe`；schema `0c1163b9008d6abb2db9b9ef79819f95da2b752b6cec9375ce859676e30d8d73`；legal evidence `e1eb5ab571b184bf88f3f7c6ecb685de2d94b2cc8cad9e67b00e4b8f9ca94640`。
- A / dev37A：request `3cead5129c37c24d29aa966d19b09daec70d5b7f91508feda947677f3db072c6`；seed `1289145443`；全池顺序 `11`。
  origin_job `15f53163114f3723613a9948077af3660dc76bf79099d2fd41727d97c479b2d4`；reply SHA256 `d0a1a8917cfb159953fc77e03b7608485ba3c5463047f9c814b22e19efff0e2b`。
  messages `a9d193bce591df9d82805aca346f5d25354d1bd4abf243df396eb8795a34a877`；schema `ed40a528507706eeadadb35ebe4fce87f934e5c311e51df32e0f2271eb0fbf59`；legal evidence `bd4c73276b4513951cd258adb7de9c7c64c8f1906fba3c6ac13d669287ac5aec`。
- B / dev37A：request `8c7224b3b716abe28a52348b68afecd4821543b468b8350481b9f96287cd9c75`；seed `1289145443`；全池顺序 `12`。
  origin_job `15f53163114f3723613a9948077af3660dc76bf79099d2fd41727d97c479b2d4`；reply SHA256 `d0a1a8917cfb159953fc77e03b7608485ba3c5463047f9c814b22e19efff0e2b`。
  messages `a9d193bce591df9d82805aca346f5d25354d1bd4abf243df396eb8795a34a877`；schema `ed40a528507706eeadadb35ebe4fce87f934e5c311e51df32e0f2271eb0fbf59`；legal evidence `bd4c73276b4513951cd258adb7de9c7c64c8f1906fba3c6ac13d669287ac5aec`。
- B / dev37B：request `6ab1e20d2684b7ffc04a8f357f39a7c18baaafef018b732c9e7ff4af385ddace`；seed `3186990144`；全池顺序 `15`。
  origin_job `d10f097a4a7c84fe6eca455607d005ed5176da8e059e9ab4c29a374f2eb569b0`；reply SHA256 `22fe0dfc4428796db2afbc13e496ea23bb48eb52f2ec3930badad08d5fb5ff8a`。
  messages `9f78c1d34125f3df43b6383463494cf2d2f64d413393dc0e5e19ebe4d133d413`；schema `ed40a528507706eeadadb35ebe4fce87f934e5c311e51df32e0f2271eb0fbf59`；legal evidence `bd4c73276b4513951cd258adb7de9c7c64c8f1906fba3c6ac13d669287ac5aec`。
- A / dev37B：request `ddc781a409f765b4d60814556d6f70962a33eea835f3ab6520c3523f8003ba1c`；seed `3186990144`；全池顺序 `16`。
  origin_job `d10f097a4a7c84fe6eca455607d005ed5176da8e059e9ab4c29a374f2eb569b0`；reply SHA256 `22fe0dfc4428796db2afbc13e496ea23bb48eb52f2ec3930badad08d5fb5ff8a`。
  messages `9f78c1d34125f3df43b6383463494cf2d2f64d413393dc0e5e19ebe4d133d413`；schema `ed40a528507706eeadadb35ebe4fce87f934e5c311e51df32e0f2271eb0fbf59`；legal evidence `bd4c73276b4513951cd258adb7de9c7c64c8f1906fba3c6ac13d669287ac5aec`。

## 具体阻碍与监测限制

runner 的 `selection.py:316–320` 要求指定 UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4` 至少 45,000 MiB 空闲且 utilization.gpu 恰为 0%。A/B 均得到 `designated GPU not idle/free; never kill or switch devices`。两配置独立前检均阻塞，故无符合条件的配置可继续。

入口前只读快照为 48,551 MiB 空闲、0%；旁路监测随后观察到 0%、0%、2%、2%，均未列出 compute process。runner 未保存拒绝时 query 的原文；只能确认守卫拒绝及邻近采样，不能声称知道精确拒绝值或非零利用率的原因，也不能将此描述为已确认其他实验占卡。没有终止任务、修改 0% 判据、再次执行或更改部署。

进程退出码为 0，仅表示 runner 正常写出了阻塞回执，**不是工程门通过**。`live_runs/engineering.AB.stage_result.json` 的 loads 为空、started=0；GPU residence 原字段为 null，因为计时从未启动。由无加载、无派发可确认本轮模型驻留与生成时间均为 0。

## 主体与等义核查边界

本轮没有模型输出，不能评价 A/B 的主体识别或等义一致性。仅对既有输入锚点核对：15B 当前来源 C:T005 明确 old college friend，C:T009 和 C:T013 延续该朋友的帮助；待评分回复的 “Talking with me” 是原清单欲检查的主体归因位置。新 AI、历史支持者与朋友不得互换。37A/B 的唯一文字变化是 “I’m”／“I am”，来源相同、其余建议相同；暂无新 q/m/U 可检验。

这些是输入检查，不是对 Gemma 的实验结论；完整本地引文在 `source_anchor_review_pending_private.json`。第35题、其余开发、重复／变体及未覆盖风险仍留原开发清单，没有临时加题。Du 派生记录未当独立人评，未重做人评，未解封任何材料。

## 成本、工程状态与停止点

旧评分 66 + 本轮 0 = 66；本轮上限 74、原上限 140 均不变；语义修订仍 1。新增 API 费 0 美元，下载约 230 秒，A/B 文件与 token 检查分别 30.14／28.47 秒，runner 前检进程 51.82 秒（不是 GPU 推理时间）。Gemma 加载／生成 GPU 时间 0；每请求 token 用量、耗时和显存峰值均不适用。没有电价／租卡或人工计价，不能将这些成本填零。

共享付费账本保留原 SHA256，累计 1.50724291 美元，边界后新增 0，1,250 项预留均已结算；只描述账内记录，未读取供应商账户。DeepSeek C/D 实际调用 0，第三方研究数据传输 0，无四配置最终排名。

当前具备固定文件与完整输入检查条件；**尚不具备经实测确认可继续本地开发筛选的工程条件**：首4工程门没有运行，模型加载、长输入 prefill、自然终止、实际 usage、峰值显存、速度与语义表现均未知。不能用离线测试或本次下载宣称裁判准确、获胜或奖励合格。

最小下一步：先审阅本轮阻塞记录，再在指定 A6000 满足既定空闲守卫时接续这 8 个未派发项；共享权重直接复用，不重新下载。现有 runner 已写入不可覆盖的 AB 阶段 schedule/stage_result，直接再次运行原命令会因文件存在被拒绝。后续需要保留本次阶段历史的明确接续回执／入口，保持请求身份和真实累计数，不能删记录、换输出目录逃避计数，或自行放宽 GPU 判据。本轮未实施该接续，不启动任何恢复或下一阶段。

## 文件索引

- `engineering_final_results_private.json`：推荐读取的完整八槽及当前状态；计划／实际配置分列。
- `eight_slots_private.csv`：八槽表，所有缺测为空；`engineering_results_private.json` 是前一版采集快照，其中 configuration_actual 实为计划配置，以 final 文件明确区分为准。
- `audit_preflight.json`、`baseline_current.json`：实际仓库、旧调用逐项身份、账本及环境。
- `approval_engineering_AB.json`：本轮用户授权的范围副本，原 PENDING 模板未改。
- `official_metadata_current.json`、`download_receipt.json`、`download.log`：官方元数据及唯一下载；下载回执中的 pending 校验状态是当时快照，后续成功以 A/B readiness 为准。
- `gemma_A_readiness.json`／`gemma_B_readiness.json` 与各自 log/time：官方哈希及完整输入。
- `runner_invocation.json`／`runner_process_receipt.json`／`runner.log`／`gpu_monitor.jsonl`：唯一执行入口与旁路监测。
- 上级 `live_runs/engineering.AB.schedule.json`／`engineering.AB.stage_result.json`：不可覆盖的原阶段记录（包含 C/D 的未授权跳过项）。
- `source_anchor_review_pending_private.json`：仅输入锚点复核，非模型语义结果。
- `current_runner_tests.log`：33 项当次离线回归。

本轮只新增路线说明、可分享当前状态与本地忽略目录的记录，保留原合同及修订历史。未提交或推送。
