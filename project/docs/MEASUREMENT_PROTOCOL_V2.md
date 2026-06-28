# Measurement Protocol V2: Dual-Order Response Reliability and Non-Inferiority

版本：2026-06-22  
状态：pilot-calibrated measurement protocol；在 full judging、PM 训练、validation selection 和 confirmatory external evaluation 前冻结。

## 1. 为什么需要 V2

V3.2/V3.3 的原始 response pilot 使用 single-order A/B pairwise judge，并把 raw reversal consistency 作为硬门槛。Claude Sonnet 4.6 pilot 显示：

- memory / combination / chord response pairs 经常是两个都合理的情感支持回复；
- raw reversal consistency 对这些主观近似回复较敏感；
- same-order repeat consistency 很高，说明 judge 并非随机；
- M0/M2/strategy audit controls 已经稳定通过；
- Strategy RAG pair 的 response signal 明显强于 memory-combination pair。

因此，V2 不把 raw single-call reversal 当成训练标签可靠性的硬门。正式 response 标签使用 dual-order debiasing：

1. 对 training-eligible pair 同时评估 A/B 和 B/A；
2. 两个顺序选择同一 underlying response 时保留偏好；
3. 两个顺序不一致时解析为 `tie`；
4. raw reversal 和 raw position bias 继续报告为 diagnostics。

这不是降低旧门槛，而是把 gate 对齐到实际使用的 dual-order 标签机制。该协议必须在 full judging 前冻结，不能根据 full judging、validation、external test 结果再修改。

## 2. Response Quality 的角色

Response quality 在本研究中是主要安全约束之一，但不是唯一胜利指标。

本研究不主张 PM 必须显著提高每个场景的回复质量。主张改为：

> PM 在固定生成器下，尽量保持 response quality 非劣，同时降低不必要资源调用、记忆误用/遗漏风险和上下文成本。

Response quality 由 blind pairwise response judge 评估：

```text
PM response vs baseline response -> win / tie / loss
NetWin = P(PM wins) - P(PM loses)
```

非劣标准：

```text
lower 95% CI of NetWin > -0.05
```

即 PM 相对 strongest preregistered baseline 的 response quality 最坏不能低于 5 个百分点以上。若该条件失败，不能声称质量保持。

## 3. Memory 和 Strategy 的独立标签

Memory 质量不能只靠 blind response preference 判断。由于固定生成器可能对不同 memory evidence 产生质量相近的回复，memory 维度的监督来自独立 audit：

- `M1`: memory opportunity / relevance / stale-risk inventory audit；
- `M0`: omission appropriateness、missed memory opportunity、unsupported personal claim；
- `M2`: selected source utilization、unnecessary exposure、stale/conflicting use、unsupported personal claim、source-set appropriateness。

Strategy 维度分开评估：

- blind response pairs 中同 memory 条件的 `R0 vs RS`；
- strategy relevance、utilization、over-structuring、premature advice；
- strategy omission appropriateness。

Strategy RAG 不能被计作 long-term memory credit。`M0+RS` 不能获得 memory-use credit。

## 4. Pilot Gate V2

### Hard Gates

Pilot 必须满足：

- judging complete；
- pair graph audit ok；
- held-out control accuracy `>= 0.85`；
- same-order repeat consistency `>= 0.80`；
- dual-order agreement rate `>= 0.65`；
- strategy pairs have response signal：strategy pair tie rate `< 0.50`；
- M1 / M0 / M2 / strategy / strategy omission / response outputs complete。

### Diagnostics, Not Blocking

以下必须报告，但不阻塞 full judging：

- raw reversal consistency；
- raw position bias；
- overall and by-pair-type tie rate；
- dual-order disagreement resolved-to-tie count；
- response preference distribution。

Raw position bias 只在 single-order audit rows 上计算。Dual-order rows 的 `A/B` 已经表示 `action_a/action_b` 的 identity，不再是 presentation position。

## 5. Baselines for Quality Non-Inferiority

不以外部 SOTA 端到端 generator 作为主比较对象。本研究的 PM 是固定生成器之外的资源分配层，公平比较应保持相同：

- generator；
- base system prompt；
- current dialogue context；
- retrieval backend；
- top-k；
- decoding settings；
- token caps。

主要 baseline：

- validation-selected best fixed action；
- strong rule policy；
- budget-matched fixed action；
- `M0+RS` and `M0+R0`；
- raw-session / full-history RAG only as diagnostic ceiling when applicable。

如果 PM 不超过 strong rule，但质量非劣且成本或 misuse 更低，可以报告 resource-efficiency 或 reliability benefit。若 PM 既不能质量非劣，也不能降低风险/成本，则不能写 positive PM claim。

## 6. Success and Failure Interpretation

成功模式 A：

- response quality 显著优于 strongest baseline；
- memory/strategy misuse 不更差；
- cost 不超过冻结上限。

成功模式 B：

- response quality 非劣；
- memory decision quality 或 misuse/omission risk 更好，或 cost 显著更低；
- final external evaluation 不出现新的安全退化。

失败模式：

- 若 PM 不优于 strong rule：报告强规则在当前可见信息下已足够，学习型 PM 未表现出稳定优势；
- 若 PM 只降低 cost：报告质量和风险非劣前提下的 resource-efficiency benefit；
- 若 PM 只提高 memory appropriateness：不能声称 response quality improvement；
- 若 response non-inferiority 失败：停止主 positive claim，回到 generator / data / policy design。

## 7. Freeze Rule

Protocol V2 是根据 small pilot 的 measurement diagnostics 制定的 development-stage measurement protocol。它必须在以下步骤前冻结：

1. full synthetic judging；
2. PM training；
3. validation threshold / baseline selection；
4. ESConv / EvoEmo confirmatory evaluation；
5. final judge or human blind evaluation。

冻结后不得再根据 validation、test、external 或 human-eval 结果修改 hard gate、non-inferiority margin、baseline selection rule 或 success criteria。
