# PM V1.5 V5.3 网页端用户目录生成合同 V2.1

日期：2026-08-09  
用途：只用于 ChatGPT Pro / Claude 网页端生成新的长期用户目录。  
机器权威：`data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2_1.json` 与 `data/pm_v1_5_contracts/v5_3_catalog_assignments_v2_1.json`

## 唯一使用规则

本文件是独立、完整、面向网页作者模型的合同。对于所有尚未生成的新用户，它同时取代 2026-08-07 V1 和 2026-08-08 V2。**不得把 V1、V2 与本文件一起上传，也不得让网页模型自行合并版本。**

每次只生成 assignment manifest 指定的一个用户。网页模型只能看：

1. 本合同；
2. 本地程序为该用户导出的一个阶段 prompt；
3. 当前阶段允许的因果世界切片。

禁止向网页模型提供外部考卷原文、外部数据集原文、Step1 effect outcome、construction condition、worth-opening 标签、检索分数、compiler 白名单或其他用户内容。

现有 11 个用户属于 grandfathered catalog：保留原正文和实际更新数，重新经过 V2.1 机器门即可；不得因为 V2.1 改了排程而重写。

## 研究目标与边界

目标不是让作者模型直接决定记忆是否应开启，而是构造能支持后续检索、同状态 ON/OFF paired effect 和四个低容量 head 学习的可审计长期历史。

目录必须提供以下可观察差异：当前相关与过时、同主题不同 owner、同主题不同事件、可复用行动—结果、未解决行动、只有背景信息、已解决冗余、明确拒绝、无证据。目录本身不含正负收益标签。训练监督只能在 current state 生成后，冻结生产检索器的 actual Rank-1，再从冻结 Step2 同状态 ON/OFF 的 quality、material grounding risk、resource function、cost 四个独立结果产生。

80 用户是平衡的第一版研究样本，不是窄置信区间或“必定学会”的保证。正式 effect 数量只在 development sentinel/pilot 观察到可辨识边际效应后一次性冻结。

## 冻结总体规模

- 80 个用户；ChatGPT Pro 40、Claude 40；8 个 primary superdomain，每域 10 人。
- 每位作者在 10 个 session-depth position 上各有 4 人，解除作者与历史长度的完全混杂。
- session position 对应 13、15、17、19、21、23、25、27、30、33 sessions。
- 每用户 4–6 个 recurring topic threads、7 个 base profile fields、3 个 base response preferences。
- 全体 profile update 规划总量 64，但每用户的 `profile_update_count` 由 assignment 独立指定，不能从 session depth 推断。
- preference version：60 stable、10 replacement、10 withdrawal；版本更新是额外历史行，不减少三种 base preference。
- 每用户固定 8 MS、8 executable-core reusable ME、2 natural-coverage reusable ME、5 unresolved ME、4 context ME。
- 关系数、事件数、style、world seed、candidate schedule seed 以单用户 assignment 为准。

这些是生产容量与平衡约束。最终科学分母以 compiler-valid、去重、actual Rank-1、current-state 与 effect-feasibility 审计后留下的项目为准；禁止为了凑数改写 query、正文或标签。

## 三阶段、隔离聊天的生成流程

### A. 世界规划

在一个全新的网页聊天中运行 `01_world_prompt.txt`，只返回一个 JSON object。世界规划包含完整 chronology，但不生成 dialogue。

必须含：2–3 secondary superdomains；4–6 thread；冻结数量的 relationship/event；完整 session plan；七个 base profile 和 assignment 指定的 update；三种 base preference 及可选 version；四种 `qa_transport_bundles`。

### B. 本地校验与因果裁剪

把世界 JSON 交回本地 materializer。只有通过 ID、数量、时间、版本、引用和 QA bundle 验证后，才生成三个 chunk prompt。本地程序仅给 chunk realizer 看截至该 chunk 末尾有效的事实，删除更晚的 relationships、events、profile/preference versions 和 session plan。

### C. 对话实现

**每个 chunk prompt 必须在另一个全新的网页聊天中运行。**不得在生成 world 的原聊天继续，也不得在三个 chunk 之间复用聊天记忆。这样作者模型不会通过聊天上下文保留被裁掉的未来事实。

每个 chunk 只返回：`sessions`、`profile_history_items`、`response_preference_history_items`。本地 assembler 合并三段，网页模型不得自行合并或补写其他阶段。

## 世界与对话硬规则

- 全部内容为英文、完全合成，不得影射真实人物或复制任何外部文本。
- 对话每 session 2–6 个严格交替 turns，以 user 开始；summary 12–40 English words。
- 事实只在 `valid_from_session` 后出现；旧版本在新版本开始前一 session 结束；同一 field 当前只能有一个 active version。
- relationship 的姓名、身份或可识别代称不得提前出现；owner、speaker、entity、event、thread 不得合并或错置。
- recurring thread 必须跨至少 3 sessions，并出现不止一种 resolution status；全用户要覆盖短、中、长时间距离。
- 不得在自然对话中出现 MP/MS/ME/RS、candidate、Step1、Rank-1、stored profile、authorized evidence、action ID、construction condition 等内部词。
- 任何 source/action/result span 必须逐字符出现在同 session 的 user turn；`candidate_text == literal_source_span`。
- executable-core reusable ME 必须同时具有具体第一人称过去行动与观察到的结果；natural-coverage challenge 保留同样语义但允许自然句法变化。
- unresolved ME 有行动但没有结果；context ME 既无行动也无结果。不同角色必须在相同 thread 中形成困难负例。
- candidate 的 session 和 thread 由私有 seed 冻结；作者模型不得移动 slot、增删 candidate 或自行按 subtype 选择固定时间位置。

## QA 运输结构

每个新 V2.1 用户的 `qa_transport_bundles` 必须恰有四种：

- `temporal_sequence`：至少两个有序 evidence sessions；
- `conflict_or_update`：至少两个有序证据，能判断旧信息与更新；
- `user_model_trajectory`：至少两个有序证据，体现状态演化；
- `abstention_no_evidence`：证据列表为空，世界中确实没有答案。

这些只用于 ES-MemEval 风格运输诊断，不进入 response PM 的 effect 标签或模型特征。

## 批次隔离与验收

user_id、counterfactual_family、template_cluster 必须各自绑定单一 split；broad_capability 必须跨 fit/dev/sealed 出现。`semantic_family` 本身不是 split isolation key；完整 broad-family-held-out 只作额外运输诊断。

每累计 5–10 人运行目录级审计：exact duplicate 为零；normalized 8-gram 只触发来源显著性复核；作者、领域、style、长度、session 深度、模板与 construction condition 做 nuisance probe。原始语义文本能预测语义能力不是 shortcut 失败。

单用户通过只代表 schema、owner/time/version、span、typed ME 与可检测的 future literal leakage 合法。整批训练仍需通过去重、split、nuisance、semantic review、current state、actual Rank-1 与 paired-effect feasibility。任何 effect outcome 出现后不得回改 catalog、query、guard 或门槛。

## 网页作者模型的最终指令

严格执行当前阶段 prompt，只输出其中指定的 JSON，不解释、不加 Markdown、不补充未要求字段。若 prompt、assignment 与本合同冲突，停止输出并报告冲突；不得猜测。assignment metadata 仅用于构造，最终不得作为 PM feature 或出现在用户自然语言中。
