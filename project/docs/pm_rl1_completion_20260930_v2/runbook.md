# PM-RL1 v2 接续执行手册

主文档：[可行执行与研究完成方案](../PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md)。2026-10-01已完成P1、P2；第三轮NLL重载通过，586条主回复＋53条base对照全部自然结束，见[P2实施结果](../PM_RL1_P2_EXECUTOR_RESULTS_20261001_ZH.md)。4条目标的准入解析缺陷及跨加载逐字复现限制均已披露。P3统一来源已准备，奖励校准、自然PPO及新人工标注仍未完成。

## 当前可验证入口

以下只读／格式检查命令已在本机采用相同程序验证；它们不运行模型或实验：

```bash
git -C /home/tokkio/Metacom5_3 status --short
git -C /home/tokkio/Metacom5_3 diff --check
python -m json.tool /home/tokkio/Metacom5_3/project/docs/pm_rl1_completion_20260930_v2/execution_contract.json
```

执行前读取 [execution_manifest.json](execution_manifest.json) 核对HEAD、模型路径、源文件身份、已知缺口；[execution_contract.json](execution_contract.json)是事前计划参数，[budget_estimate.json](budget_estimate.json)是未扣缓存的数量情景。manifest的P0完成不开放未满足依赖的P3/P4。

## 已执行工作包P1（保留事前范围）

1. 以当前 `render.py`、`data.py`、`source_repair.py`、`source_quarantine.py` 为起点，列出主体、时间、RS动作说明与预算计费的变更。
2. 从已有dataset diagnostics读取72条train/dev MP待审队列；沿用101条旧审查和overlay。不读禁用项目自造数据，不打开test gold做语义反馈。
3. 定义新schema，强制来源和可用时间；缺失的事件／确认／结果保留unknown。新增字段不能免费暴露给PM。
4. 按主文档冻结24个ME来源片段、六个dev诊断前缀及共同合法计划。校验source span、as-of、角色和全MS。
5. 接入所有方法共同的initial_plan_mask，重算新版预算可达性。对这些改动运行针对性回归，不重跑E0来补进度。
6. P1冻结后才制作新生成请求和运行最多72条诊断。新旧生成身份分开；旧输出不覆盖。

实际交付位于 `project/outputs/pm_rl1/completion_20260930_v2/P1/`：`source_review_registry.json`、`renderer_freeze.json`、`capacity.json`、`diagnostic_manifest.json`、`phase_closeout.json` 均已生成。变更说明在实施报告中，没有另建原先建议名 `representation_delta.json`。

原定72条完成后，针对整段JSON引发的对话分析／拒答，做了一次接口修复及16条额外本地生成。`interface_repair_v3/plan_deviation.json` 明确记录P1实际88次G，未改原72条；这是执行偏离，不是原事前额度。当前 renderer 为 `DirectReplyRenderer`。旧LoRA的历史话语归属错误仍保留，不宣称完全通过语义验证。

## 已验证的本地执行入口

以下是本轮实际运行入口。脚本76、78、80拒绝覆盖既有冻结；不要对已完成目录重新运行它们来“更新结果”。75依赖已经准备并绑定哈希的两个有限来源队列，模型及完整本地数据并未包含在远端公开包中。

```bash
# 工作目录：/home/tokkio/Metacom5_3
python project/scripts/rl1/75_record_p1_source_review.py
CUDA_VISIBLE_DEVICES=0 CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/76_prepare_p1_representation.py
CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1 PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/77_run_p1_diagnostics.py
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/78_prepare_p1_interface_repair.py
CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1 PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/77_run_p1_diagnostics.py --out project/outputs/pm_rl1/completion_20260930_v2/P1/interface_repair_v3
python project/scripts/rl1/79_close_p1_representation.py
HF_HUB_OFFLINE=1 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/80_prepare_p2_executor_slots.py
```

本轮最终RL1测试命令在 `project/` 下运行，176 passed：

```bash
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest tests/test_rl1_*.py --junitxml=outputs/pm_rl1/completion_20260930_v2/P1/tests_final.xml
```

`tests_final.xml`已被阶段收口绑定；后续测试写新文件名，不覆盖已冻结证据。脚本79可以校验并重建字节一致的收口产物。

## 已执行工作包P2

`project/outputs/pm_rl1/completion_20260930_v2/P2/slot_freeze.json` 已冻结684个条件（train576、dev108），无缺失或替换；每种剂量类别覆盖全部96个train前缀／12个owner。另固定12个dev行为输入，各类别2个、每owner4个，包含既有身份错误。

作者只见实际交付输入，核验者另外检查已取得资源的完整来源。684次首试、固定37条协调者AI抽查及唯一39条修复后，冻结493条弱目标（413train／80dev）。原始核验格式因提示／parser不一致产生39次废弃启动，原记录保留；只有一次格式补充，额外调用计入技术J备用。接纳标签不是人类真值，resource_behavior不是已核实的资源使用率。

训练后另发现7份原始核验JSON含重复键，其中4条进入训练／开发目标（train3／dev1）。默认JSON解析覆盖了先前主张；493是实际程序准入数，不是493份完整原文都严格合格。另作4条事后AI读源检查并披露，保留493条训练、权重及原NLL，不改写结果或重训。P3已有`judge._pairs`拒绝重复键；勿把冻结P2解析器当作以后可直接复用的严格解析器。

一次三epoch训练完成78次更新。36条固定诊断全部自然结束；第一轮有两条确证严重说话人／主体错误，第二、三轮仍有不确定案例。依据事前排除规则及NLL选第三轮，新进程重载的整体和逐例NLL差均为0。`executor_freeze.json`绑定最终权重、完整推理栈、renderer及来源缓存协议。

以下为真实入口与先后依赖，供审计／从缺失阶段继续；已有freeze及人工式协调者记录不应重建覆盖。协调者37条来源阅读记录及36条行为阅读记录来自实际逐条检查，不能仅运行脚本伪造完成。

| 顺序 | 实际入口 | 完成条件 |
|---|---|---|
| 绑定示范 | `81_bind_p2_supervision.py` | P1和684输入身份已匹配 |
| 首试作者 | `82_run_p2_local_jobs.py --stage author` | 684条原始输出均有状态 |
| 来源核验输入 | `83_prepare_p2_reviews.py` | 全部作者已结束；37条协调者阅读记录另存 |
| 唯一格式补充 | `83b_prepare_p2_review_format_fix.py` → `82b_run_p2_review_format_fix.py` | 保留旧39次启动，建立新的684条核验身份 |
| 严格解析及抽查登记 | `84_collect_p2_reviews.py --review-root project/outputs/pm_rl1/completion_20260930_v2/P2/review_format_v2` → `84b_record_p2_coordinator_audit.py` | 不升级拒绝／技术未解决为接纳 |
| 唯一修复 | `85_prepare_p2_repairs.py` → `82_run_p2_local_jobs.py --stage repair` | 实际39条，不扩展为新的提示搜索 |
| 修复核验 | `83c_prepare_p2_repair_reviews.py` → `82_run_p2_local_jobs.py --stage review_repair` → `84_collect_p2_reviews.py --repair` | 18接纳、14拒绝、7未解决 |
| 目标与训练代码冻结 | `86_freeze_p2_targets.py` | 493目标、行为输入及87–89脚本全部绑定 |
| 一次适配 | `87_train_p2_executor.py` → `88_diagnose_p2_epochs.py` | 3epochs及固定36条行为输出 |
| 选择与重载 | 实际填写`behavior_reviews_private.json` → `89_select_p2_executor.py` → `87_train_p2_executor.py --reload` | 原文／输出片段绑定；新进程检验通过 |
| 共同比较输入 | `90_prepare_p2_common_pool.py`、`90b_prepare_p2_secondary_inputs.py` | 在新checkpoint输出之前已冻结586＋条件53个合法槽位 |
| 运行身份 | `91_freeze_p2_executor.py` | 来源协议及完整模型运行身份绑定 |
| 共同回复 | `92_run_p2_common_pool.py --arm primary`、`--arm secondary` | secondary只在选择LoRA时运行；全量保留失败 |
| 收口 | `93_close_p2_executor.py` | 检查旧2,735产物、输入／响应／缓存／测试后写新阶段结果 |

作者／核验调用使用本地Qwen环境，训练／诊断／共同池使用Llama环境，均绑定A6000；不改用HTTP旧cap，也不静默换GPU。准确运行形式：

```bash
# 工作目录：/home/tokkio/Metacom5_3；以下示范入口不表示应重跑已完成阶段。
CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1 /opt/tokkio-data0/tokkio_envs/paper1-qwen35-vllm-py312/bin/python project/scripts/rl1/82_run_p2_local_jobs.py --stage author
CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1 /opt/tokkio-data0/tokkio_envs/paper1-qwen35-vllm-py312/bin/python project/scripts/rl1/82b_run_p2_review_format_fix.py
CUDA_VISIBLE_DEVICES=1 CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1 PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/92_run_p2_common_pool.py --arm primary
```

`92`首次完整加载后曾因Python的EOS元组与持久化JSON数组比较不等而拒绝启动；当时没有发出G请求。现比较完整规范化配置哈希，冻结模型／消息／参数不变，旧失败目录、旧runner及启动记录仍保留。后续resume只复用已经完整结束的真实输出；未结束attempt不自动重发。

本阶段原185项RL1测试记录为`P2/tests_supervision.xml`；CI范围的Paper-1＋RL1集成回归另写`P2/tests_ci_integration.xml`，不覆盖历史测试证据。

最终收口检查通过：53组base／LoRA模型输入相同，42个前缀都有真OFF，旧2,735个产物大小／哈希不变；CI范围1,172通过、1项旧tokenizer路径依赖跳过。共G1,398次、来源准入J762次，RL奖励J0次，新增API0美元。

`phase_closeout.json`与公开`p2_results.json`保存实际结果；`replay_disposition.json`和公开`p2_replay_addendum.json`另记跨加载限制。6个重合第三轮输入仅2个逐字一致，其他4个生成中途分叉，根因未确定。未来比较复用共同池的实际bytes，不能用相同seed重新生成后覆盖原回复，不能把有限行为筛查当作后续无错保证。该补充不触发重新训练或重新挑选checkpoint。

## P3来源输入准备

`94_prepare_p3_common_evidence.py`已给共同42个前缀准备完整、同owner、strict-past的统一来源。`P3/common_evidence/input_freeze.json`绑定原文、当前cut、speaker contract和tokenizer；每个方法使用同一份来源，计划／执行器／成本留在协调者侧。准备程序不读取新回复内容、评分或test前缀，不生成任何标签。

```bash
HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES='' /opt/tokkio-data0/tokkio_envs/paper1-qwen35-vllm-py312/bin/python project/scripts/rl1/94_prepare_p3_common_evidence.py
```

已有freeze时不要重跑覆盖。来源文本本身为666／11,880／31,766 tokens（最小／中位／最大），这还没有加评分提示、回复及schema。这是来源准备时的快照；后续上下文检查、盲审包和初版试跑见下节，评分器资格仍待真正的人类校准。

## P3固定考卷、初版评分器与人工交接

2026-10-01 已实现脚本95–104及 `judge_completion.py`、`human_calibration.py`、`calibration_decision.py`。当前是**初版候选及人工工具已落地，尚未建立奖励资格**。实际完成数、耗时、测试与哈希由 `p3_development_results.json` 和本地 `P3/development_closeout.json` 记录；只有该结果文件存在且源记录相符，才称试跑完成。

抽题先锁条件再读候选回复，按固定hash选计划。40对保持8自然＋8控制用于开发，16自然＋8控制用于封存；另锁8自然备用。已有失败涉及的3个用户及其全部事实沿革归开发，其余12个用户归封存／备用。同一个人的主体、事件和状态更新不会跨组；完整历史会话的跨owner逐字复用检查未发现重复，不据此宣称所有语义复用已穷尽。

这里的开发／封存是**裁判校准分组**，没有重分PM训练／开发／test。封存材料使用train用户，没有读取最终test。24对自然材料中20对为资源差异、4对为执行器差异；已有base回复只覆盖原3个dev用户，所以4对执行器对照全部留在校准开发，不能宣称执行器差异已通过独立封存验证。24对中7对当前cut只有至多3条消息；允许适当的普通支持和真实平局，不要求使用历史才能获得高分。

初版评分器复用旧indexed/flat/explicit机制，增加新AI与历史支持者的明确角色契约，要求核查共情、赞扬、提问中夹带的具体事实，保留个人事实与一般支持的区别。q/m档位和效用公式不变。重复JSON键及非有限数拒收，原文引用由合法ID机械还原；缺测仍为空。相同来源和相同回复复用一次评分，40对实际对应79条不同单回复。另12条复评分使用独立draw，仍待最终冻结后执行。

Qwen3.5-9B使用完整合法来源、thinking模式、自然结束，无60／256之类任务输出cap。已锁108个校准／备用／重复／核查请求的完整输入为2,455–27,279 tokens；模型原生窗口262,144，没有截断来源。114个train/dev前缀的额外来源长度检查不产生回复或标签：最大纯来源37,418 tokens，有8个前缀比已测开发材料的来源更长。未来新请求仍须完整检查，不能把本次吞吐直接当成全部训练的保证。

人工交付位于本地：

```text
project/outputs/pm_rl1/completion_20260930_v2/P3/calibration/
  PM_RL1_40对人工校准包_20261001.zip
  human_handoff_final/rater_1.html
  human_handoff_final/rater_2.html
  human_handoff_final/填写说明.txt
```

每位独立评审填同样40对，A/B及题目顺序分别打乱；单人也可完成有限校准，但不能让同一人填两份并声称两人一致。原文、来源检索、风险片段复制、暂停保存和加密导出已做浏览器检查。全部真实表单保持未填写；保存、恢复、加密及解密往返仅用隔离的虚构UI样例测试。最终HTML补上当前cut日期并检查各导航入口，题目、来源、量表和form identity未改。

导出的JSON中每题答案单独加密。解密私钥只留本地；这是防止意外提前查看的工作流程，不宣称对掌握本地私钥的研究者构成不可绕过的安全边界。`99_ingest_p3_human_labels.py`只有开发标签入口，验证题保持密文；未收到真实人工文件时禁止用AI制作替代提交。

```bash
python project/scripts/rl1/99_ingest_p3_human_labels.py /实际收到的文件.json --rater rater_1
```

接收脚本需要 `cryptography`（已列入 `human-calibration` 可选依赖）。先核对form/source身份，记录第一份不可覆盖的提交；另一位评审使用对应rater参数。程序只输出接收回执，不在日志展开验证答案。评分者身份如有联合讨论需如实另记，不能当作两份独立结果。

收回开发标签后最多做一次语义修订，然后冻结完整运行身份、准入算法、人工来源及验证入口，才首次解开验证标签。若最终runner或运行身份变化，旧分数保留，按新身份重新测量并计入原校准调用预算，不能把新旧输出混称同一冻结裁判。初版32次开发测量及1次预定完整来源复核探针分别记账；探针不冒充12次独立稳定性检查，也不覆盖原单点评分。

`calibration_decision.py`已实现固定分母、明确方向、相当、分歧、单人限制、重复稳定性、严重漏检否决及低差异128配置的计算，并用合成代码样例验证。它只计算经核验输入，不生成来源事实裁决、不自动开启PPO；构造控制题时的预期不是人类标签。封存控制成立与否仍需来自原文和真正的人评，控制无效记证据不足，不换题补成功。

已产生本地推理时间，新增API费仍为0。后续预算使用实测含thinking的输出长度和批处理引擎时间，并区分重叠的单请求时延、串行情景、来源长度覆盖、模型装卸、生成及余量。128／384仍待人类校准和完整96小时排期决定；不以输出截断压低报价。原 `budget_estimate.json` 保留事前情景，新增实测单列，不回写旧报价。

本次33次调用的引擎时间为1,750.58秒，四并发及启动／收尾空档合计每完成请求约53.05秒；单请求含thinking输出中位数5,994 tokens。这与执行器约百token回复的成本不是同一件事。沿用原槽位上界及剩余核查／技术余量，128／384方案的后续J引擎部分在本次批处理速率可迁移的假设下约51.66／74.30小时，**尚不含后续G、装卸、表征及训练等完整排期**。单请求时延相加的188／271小时仅是线性敏感性参考；这些时延在本次运行中相互重叠，且串行时速度可能改变，不能声称实测串行就需要这些时间。

因此P4反馈执行需要按固定策略版本收集完整batch，复用已冻结G/J缓存，并验证终值反馈的批处理吞吐；不能把本次四并发报价直接套到逐episode同步评分。全部奖励齐全后再更新，保持on-policy轨迹记录。正式冻结128／384前补全长来源覆盖、生成和装卸成本；本次没有因此启动PPO、改奖励、改输出长度或再开候选模型搜索。

## 现有代码复用地图

| 待实现工作 | 已有代码或脚本 | 复用边界 |
|---|---|---|
| renderer与资源身份 | `project/src/metacom_pm/rl1/render.py`、`data.py`、`source_repair.py`、`source_quarantine.py` | 另建新版身份；不覆盖旧实验 |
| 观测与预算 | `env.py`、`schema.py`、`observation_features.py`、脚本70 | 统一initial_plan_mask；按新文本实际计费 |
| 监督与LoRA | `executor_encoding.py`、`executor_coverage.py`、脚本59–64 | 新槽位清单、新输出目录；旧脚本可能硬编码旧目录，不原样重跑 |
| 评分 | `judge_scoped.py`、`judge_flat.py`、`judge_explicit.py`、`evidence.py` | 已有分项机制；显式字段v5准备不等于语义合格 |
| 学习与恢复 | `e0_learning.py`、`e0_value_initialization.py`、`cache.py` | 复用更新／恢复逻辑，替换toy反馈，不复制toy完整效用函数 |
| 真任务基线 | 现有ResourceEnv、观测编码、真实反馈记录 | OneShot／BC-union／自然PPO runner仍须实现并校验 |
| 数据风险 | 脚本69–73和既有dataset diagnostics | 复用统计与待审队列，不重新清洗全部QA |

带参数runner在实现后核对实际 `--help`；无参数冻结脚本核对代码入口，并用实际运行验证，再把准确命令加入本文件。不要照建议名猜测命令已经存在，也不要给无参数冻结脚本随意追加`--help`触发实际执行。

## 阶段状态和继续条件

- P1完成进入P2；在P2期间可准备评分schema、表单、训练恢复和基线代码。
- P2冻结X*后组装校准包。新LoRA失败则继续base；不为获得好结果再开SFT网格。
- 校准默认40对，额外8对只按事前低对比条件启用。开发标签与封存标签分开存放；反序／复评分用独立测量draw且不能命中原评分缓存。主文档只要求单点评分重复，不另建第二个pairwise裁判。
- P3达到指定用途后，按吞吐冻结128／384；模型更新前写入实际checkpoint、提示、指标、预算和恢复配置。P4每批奖励完整才更新。
- 若反馈失败，自动准备B0的来源、覆盖和人工成本，保留四头失败。B1需要实际的范围选择与人工投入，不能仅由本文件启动。
- 任何test输出之前冻结P5。PPO未胜、LoRA未改善、人工平局都不是改test、改奖励或追加seed的理由。

## 如何处理等待

需要人类时先交付已经可填写的盲审包、来源入口、工作量及标签用途；保留待回答状态。等待期间继续不依赖这些标签的任务。不能以时间经过代替人工回答，不能让AI代填后称人评。

每阶段的`phase_closeout.json`至少记录：计划和实际数、输入与输出哈希、版本身份、测试、缺失与拒收、实际G/J及审核条数、设备时间、付费责任、下一动作。失败时保留原始请求、回复、采样策略和optimizer状态。

新增API默认0；不查询密钥、不启用付费fallback、不改旧账本。发布、push、merge和B1范围变更不由这个runbook自行触发。
