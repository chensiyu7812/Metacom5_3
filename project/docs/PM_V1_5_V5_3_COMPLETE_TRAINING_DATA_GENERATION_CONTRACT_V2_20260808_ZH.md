# PM V1.5 V5.3 完整训练数据生成与验收合同 V2

日期：2026-08-08  
机器权威合同：`data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2.json`

## 结论

V2 合并了原项目合同与 2026-08-07 的外部数据反推审计。它不推翻已经通过 V2 复验的 11 个用户，也不要求等 80 人全部完成后才验证 Step2。V2 的目标是训练一个有限、低容量、可审计、能够超过 always-off 与透明规则基线的 PM，而不是声称解决复杂语言理解或真实临床陪伴。

正式链路固定为：严格过去的私有目录 → actual Rank-1 候选 → Step1 四个低容量价值头 → 16 动作联合投影 → typed Step2 → 确定性 guard/fallback → quality、grounding risk、resource function、cost 分开评估。

## V1 保留、V2 修正的内容

仍保留 80 用户、双作者、8 个 superdomain、13–33 sessions、48/16/16 用户簇 split、typed exact spans、严格 owner/time/version、外部文本零复制，以及同状态 paired effect 产生监督信号。

V2 修正七点：

1. `3008/2944/1088/2496` 是生产容量规划值，不是必须凑满的科学通过线。最终分母只能在 actual Rank-1、compiler、去重和特征可辨识审计后确定。
2. interaction 改成约 32–48 个语义一致的四候选 state；每个 state 跑完整 16 动作。禁止用不同 state 分配不同动作造成 state-action 混杂。
3. shortcut 只审 nuisance：作者、领域、长度、标点、style pack、session 位置和模板族。原始语义文本能预测语义条件不是作弊；那正是 PM 应学习的有限语义能力。
4. user、counterfactual family、近重复模板必须绑定同一 split；但同一种语义能力必须跨 fit/dev/sealed 出现。完整 family-held-out 只作额外运输诊断。
5. ME Rank-1 compiler-valid `0.70–0.85` 仅是支持范围诊断。不得为了命中区间改 query、改文本或晋升 Rank-2。
6. 每个用户的世界模型还需支持至少一个时间序列、多证据冲突/更新、用户状态轨迹和无证据/拒答槽。这些供 ES-MemEval 风格 QA 运输诊断，不进入 response PM 的 effect 标签。
7. quality、material grounding risk、resource function、cost 保持四个独立目标。cost 只在 16 动作联合投影时施加，不能因为“便宜”就把某组件 ON 标成正收益。

## 什么是合格数据

单个用户机器通过只证明 schema、主键、owner、时间、版本、source span 和 typed ME 合法。它不等于整批数据可以训练。

整批还必须通过：

- 用户/反事实/模板簇 split 隔离；
- exact duplicate 为零；normalized 8-gram 只进入来源显著性人工复核，不能由词法规则自动判定复制并强迫重写；
- 作者、领域、style、长度、session 深度与 condition 解耦；
- 同主题不同 owner、不同事件、不同动作/结果、旧版本、已解决、当前冗余、明确拒绝和 no-candidate 困难负例；
- construction condition 不进入特征，也不直接成为 worth-opening 标签；
- 候选在生成 current state 之后由生产检索器冻结，actual Rank-1 是唯一执行候选；
- 只从冻结 generator 同状态 ON/OFF 的 quality/risk/function/cost 效应产生训练监督。

现有 `profile_history`、`relationships`、`events`、`topic_threads` 与 sessions 共同构成可审计世界模型；不强迫现有 11 人补一个重复的 `latent_world_graph` 字段。style pack、world seed 和 schedule assignment 存在模型特征之外的 assignment manifest 中。

## 生成顺序

### Wave 1：13 个跨域哨兵用户

现有 11 人先用 V2 复验。随后只生成 13 个跨域哨兵，使尚未覆盖的领域、两位作者和短/中/长 session 深度尽早进入批次审计。每人仍单独输出完整 JSON，每累计 5–10 人运行一次目录级验收。

Wave 1 通过后再扩展到 80；若发现错误，只返工对应用户或模板族，不重写已经通过的用户，也不能看到 effect outcome 后回改 catalog。

### Step2 资格赛可并行

64 条 Step2 语义资格赛使用与用户 catalog 内容不相交的 4 个语义家族 × 16 动作。它验证 typed executor 在真实 endpoint 上的 speaker/owner、grounding、原子动作和 deterministic fallback，不产生 Step1 标签，也不决定剩余用户可否继续生成。

因此：可以一边生成 Wave 1，一边执行已经冻结身份和费用上限的 64 条资格赛；但在 Step2 资格结果出来以前，不启动正式 paid paired-effect generation。

## 训练与比较

四个 head 分开学习候选开启的条件性边际价值，最后投影到完整 16 动作。最低有意义结果不是“每个 head 完美”，而是：

- learned PM 相比 always-off 有可测的条件性收益；
- 相比 fixed-high / 旧 V1.0 / transparent rule / cost-matched fixed，在质量不显著变差的条件下减少 grounding risk 或上下文成本；
- 组件级失败和外部运输边界如实报告，不把 generator 失败写成 Step1 标签；
- 内部测无法由 ESConv、EvoEmo、ES-MemEval 覆盖的细粒度四组件能力，外部测真实运输与失败边界。

80 个用户是平衡的第一版研究样本，不保证狭窄置信区间。统计报告按用户簇计算 bootstrap/CI；state 数不能冒充独立用户数。结果若区间较宽，诚实报告即可，不得为了“通过”继续修改数据或门槛。

