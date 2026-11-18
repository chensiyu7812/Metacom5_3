# Paper 1：Function 可观察性与四臂 Panel V2 修订

日期：2026-08-13  
状态：`ACTIVE ZERO-API / PANEL V2 REBUILD REQUIRED / NO LIVE CALL AUTHORITY`

机器合同：

`data/pm_v1_5_contracts/paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json`

版本注册：

`data/pm_v1_5_contracts/paper1_experiment_version_registry_v1.json`

## 决定

保留旧审计的事实：一个 Codex 在旧 treatment 的 6 个 MS telemetry-positive 回复中判了 1 个 confirmed、5 个 not confirmed，并在 13 个 safe-nonuse 回复中未发现漏记使用。这个结果继续用于诊断 `used_evidence_ids` 低精度、候选冗余和主题错配。

但它不再拥有以下权限：

- 不能称为独立人评或合格 LLM judge；
- 不能判 V4 `R0+MS delta` 失败；
- 不能凭“至少两条”二元标签卡住开发；
- 不能估计正式 Function rate。

原因不是放宽标准，而是原问题不可稳定识别：单看一条自然语言回复，评审者很难证明某句话“绝不可能由 current context 产生”，也不应被要求复原 generator 的隐性推理链。

## Function V2 怎么测

### 第一层：结构实现，硬门

- requested evidence 是否真正进入冻结 compiler/generator；
- owner、time、source 是否正确；
- wrong-owner、future、answer、ID、scaffold leakage 是否为零；
- USE/ASK/IGNORE 与 fallback 是否可审计。

### 第二层：可观察贡献，机制证据

盲评同状态 `R0` 与 `R0+component`，同时看到 exact authorized source 和 current context，只判断回复差异：

- `CLEAR`：有具体、source-supported 的差异，不只是通用温暖、长度、建议或 current echo；
- `PLAUSIBLE`：有合理 source-consistent 差异，但唯一归因不够强；
- `NONE`：没有可观察的 source-conditioned contribution；
- `UNCERTAIN`：归因或组件边界有合理分歧，保留为不确定，不强制算失败。

Function 是机制证据，不是 ITT validity filter；Risk 单独测，不能因为回复另有风险就抹掉已经发生的资源贡献。

### 第三层：系统价值，外测主结果

正式成败仍由同栈 Quality、absolute Risk、Cost、adaptive baseline value，以及 ES-MemEval 的客观 QA/temporal/conflict/abstention 共同决定。

第一版 MS 不需要 `0.80` Function rate，也不需要人类对每个细粒度案例精确一致。最低有意义闭环是：EvoEmo 出现非零、可复现的可观察贡献且无 critical misuse；ES-MemEval 同时证明 memory-required QA 相对 no-memory 改善，并在相对 fixed-high 更低成本下保持准确率/风险。

## 开发晋级门

不再使用“单独数够两条 binary Function 就晋级/少一条就失败”。修复 treatment 可以晋级，当且仅当：

- 结构硬门通过，critical leakage/misuse 为零；
- Quality 方向非负，material Risk 不向坏；
- 预先定义的 clear-use opportunity 不是全为 `NONE`：至少一个 `CLEAR`，或至少两个不同 owner 的 `CLEAR/PLAUSIBLE`；
- hard-ignore controls 大多数正确 IGNORE/NONE，且没有 critical forced use；
- `UNCERTAIN` 原样报告。

真正阻断条件是：critical owner/time/source 错误、全部 clear-use opportunity 都没有可观察贡献、Quality/Risk 明确恶化，或 panel 本身没有资格回答问题。

## 为什么现有 56-call panel 暂不执行

它对 compiler smoke 有价值，但不能作 MS 科学资格 panel：

- MS 候选按“最近一条”选，不是 learned selector，也不是预先审查的 use opportunity；
- 多个候选只是问候语，例如 “Hey, do you have a moment to chat?”；
- 还有明显主题错配和 current-context echo；
- 缺 wrong-owner、stale/conflict、uncertain-continuity controls；
- 只有 12 个 state 四臂齐全。

因此撤回“批准全部 56 次即可执行”的请求。旧计划可以作为新 panel 选择少量 IGNORE/compiler smoke 的来源，但不能原样绑定 live scientific run。

## Panel V2 最小构成

- 至少 4 个不同 owner 的 `CLEAR_USE`：具体、相关、非重复、严格过去事实；
- 至少 2 个不同 owner 的 `ASK`：continuity 确实不确定；
- 至少 4 个不同 owner 的 `IGNORE`，覆盖 current echo、低信息问候、主题错配、wrong-owner、stale/conflict；
- 至少 12 个状态四臂完整；RS main effect 与 interaction 只用这 12 个完整状态；
- MS main effect 可额外使用合法两臂状态，但必须另报分母；
- 总 generator calls 尽量不超过 64；generator 继续冻结 Llama 3.1 8B。

opportunity 分层只用于资格测试 treatment，不能变成 selector gold。正式确认仍必须回到冻结 learned selector。

## 主张与版本边界

方法版本仍是 `PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2`；历史 routing 结果不改。本次只升实验修订版本：

- compiler：`R0_DELTA_COMPILER_V4_0`，不变；
- measurement：`FUNCTION_OBSERVABILITY_V2`；
- panel：`FOUR_ARM_PANEL_V2`，需重建；
- live run：未授权。

可以先完成 `SELECTIVE_RS_PLUS_MS_PM` 里程碑：RS 在 ESConv+EvoEmo 闭环，MS 在 EvoEmo+ES-MemEval 闭环。如果全部过门，它支持一个有意义的 selective strategy + session-memory PM 主张。

但完整 Paper 1 predicate 仍是 `RS_pass AND count_pass(MP,MS,ME)>=2`。以后救回 MP 并把它加入最终 claimed system 时，受影响的 EvoEmo/ES-MemEval final-system 比较必须补跑或扩展；不能把纯 RS+MS 结果改名为含 MP 的最终系统。

## 唯一下一步

零 API 重建 Panel V2，机器审计 strata、owner、source、四臂完整性和哈希；完成后再提交一个 exact run identity、调用数与成本上限供批准。当前不授权 generator、judge、fit 或 external call。
