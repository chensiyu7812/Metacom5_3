# Paper 1：RS/R0 与 MS 根治方案及分层通过标准

日期：2026-08-13  
状态：`ACTIVE_ZERO_API_R0_DELTA_TREATMENT_REPAIR / GENERATOR FROZEN`

机器合同：

`data/pm_v1_5_contracts/paper1_rs_ms_r0_delta_root_repair_v1.json`

## 技术结论

这轮不是“MS 又失败了”。11 个 owner 上 7 正、2 负、2 平，风险方向 3 个改善、0 个恶化，足以作为**第一版 PM 的开发晋级证据**；开发阶段没有理由把每个小 slice 的 `p<0.05` 当硬门。它仍不能直接写成 `MS_pass`，因为新 MS-only 回复尚无独立 source-aware Function，且多数质量收益发生在没有实际使用记忆的 13/19 样本上。

RS 的结论更明确：失败的是现行“RS 替换 R0”的 treatment。31/33 baseline 获胜，说明把 dominant Restatement 当唯一回复动作会破坏完整性；它并没有检验“在完整 R0 上按状态增加一个合适策略动作”是否有价值。

因此当前最短正确路线不是换 generator，而是先把 treatment 的因果对象改对：

```text
完整 R0 基座
  + 可选 MS 记忆增量（USE / ASK / IGNORE）
  + 可选 RS 策略增量（一个局部策略动作）
  = 一条完整、当前导向、安全、可继续对话的回复
```

Llama 3.1 8B 在这一步冻结。只有修复 treatment 在当前 generator 上通过开发晋级门后，才把更强 generator 作为第二阶段稳健性/interaction 实验。

## 一、为什么现有设计无法正确回答 RS 与 MS 是否有用

### RS：把资源增量和基础回复能力混在了一起

现行 compiler 写的是“RS 是唯一 primary act”。dominant Restatement 卡又要求一句复述、禁止问题、建议和第二动作。于是比较实际变成：

```text
baseline = 完整 R0 回复
routed   = 狭窄的一句复述
```

这不是公平的 `R0` 对 `R0+RS`，而是基础回复完整性的实验。warm-close 虽让质量稍回升，却使 unsupported-personal-fact risk 翻倍，也说明在旧架构上补一句话不能解决责任边界。

### MS：通用 prompt 风格和记忆做功混在了一起

19 对中 routed 赢 12 对，但 8 个赢来自 `clean_safe_personal_nonuse`。这些回复可能因 MS arm 的通用措辞、提问或篇幅而更好，却没有使用具体过去事实。若继续把这类赢计为 MS 做功，PM 可以通过“开了 MS prompt 但没用 memory”获益，论文主张就不成立。

所以必须把所有 arm 的 R0 指令完全相同；MS arm 唯一允许增加的是“当前上下文无法独立解释的、来源支持的过去信息贡献”。

## 二、第一版 PM 是否被要求过高

要把三个层级分开。

### 开发晋级门

用途只是决定“是否值得冻结后做一次正式确认”，不承担论文结论。要求：

- requested→received=`1.00`，wrong-owner/future/scaffold/answer leakage=`0`；
- selector 在 eligible 状态上同时产生 ON/OFF；
- learned-ON slice 的 dialogue/owner 级 Quality 方向为正；
- 无 critical risk，material risk 没有方向性增加；
- 至少两个独立复核案例出现 source-aware、不可由 current context 单独解释的 Function；
- **不要求小开发 slice 的 `p<0.05`**。

按这个标准，当前 MS 是“晋级 treatment repair 与 Function 复核”，不是失败；当前 RS replacement treatment 不晋级，必须先改 treatment。

### 正式 head pass

这是论文中写 `RS_pass` 或 `MS_pass` 的门：

- grouped/cross-fitted selector 非退化，并在 incremental-benefit estimand 下优于 transparent rule；
- source-aware Function 非零、可归因、可复现，generator self-report 不算；
- 整体 Quality 相对 component-OFF 在 `-0.05` NetWin margin 内非劣；
- learned-ON slice 点估计为正，并满足“cluster interval 下界大于零”或“另一个独立 track 同向且无 material regression”之一；
- material-risk 差值上界不超过 `+0.05`，critical event 不得被平均掩盖；
- component ON/OFF、full-minus-component、matched-cost 或 matched-ON-rate control 仍能看到独立贡献。

过去的 single-component functional-use `0.80` 应保留为工程参考目标，而不是覆盖上述完整证据的独立硬门。第一版研究需要“非零、可归因、可复现”，不需要假装每次 ON 都必须完美做功。

### Paper 1 最终通过

最终 predicate 仍是：

```text
RS_pass
AND count_pass(MP,MS,ME) >= 2
AND 三个互补外测分别通过
```

这比第一版单头晋级严格得多是合理的，因为它支撑的是整篇论文主张，不应反过来作为每次开发迭代的停止门。

## 三、三项外测的正确覆盖矩阵

| 外测 | 该测什么 | 不该测什么 | 合格结果形状 |
|---|---|---|---|
| ESConv | RS/R0 的单会话策略选择与即时支持 | MS/MP/ME 长期记忆 | learned RS 整体 Quality/Risk 不劣于 R0；learned-ON slice 正向；优于 rule 或 ON-rate-matched random 的 selection；比 fixed-high 少开资源并在满足 10% input-token 门时主张成本优势 |
| EvoEmo | `R0 / R0+RS / R0+MS / R0+RS+MS`，以及完整多头联合系统 | 把 state 数当独立 user 数 | RS、MS 分别有 Function 与 marginal evidence；整体 Quality/Risk 非劣；ON slice 正向；联合 policy 在 matched cost/ON rate 下有 adaptive value；16-action safety/frontier 通过 |
| ES-MemEval | typed memory retrieval、QA、temporal/conflict、abstention 与成本 | RS 支持回复质量 | learned typed memory 优于 no-memory 的 memory-required QA；相对 fixed-high 准确率/风险非劣且 input token 至少低 10%；相对 session-RAG/full history 有预注册 accuracy-cost 优势；should-abstain false answer 不增加 |

正确表述是：**整个系统在三个外测上通过；RS 由 ESConv+EvoEmo 闭环，MS 由 EvoEmo+ES-MemEval 闭环。** 要求 RS 和 MS 各自在三个数据集都通过是类别错误，因为 ESConv 没有纵向 memory，ES-MemEval 也不测支持性回复策略。

## 四、需要实现的 treatment

### 不变的 R0 基座

四个 factorial arm 必须逐字共享：当前 turn grounding、同理回应、安全/拒绝/停止边界、完整回复、至多一个适当的 forward move。不能因为资源 ON 才额外加入温暖、问题、建议或更长篇幅。

### RS 是 delta，不是 backbone

- `RS OFF = R0`；
- `RS ON = R0 + one bounded strategy delta`；
- Restatement 只能占一个局部槽，不能成为整条回复；
- RS selector 学的是“相对 R0 的增量收益”，不是“这个场景能不能复述”；
-训练 outcome 只能在 development 用 grouped nested/cross-fitting，不能读 confirmatory outcome 调 selector。

### MS 是 USE / ASK / IGNORE

- `USE`：过去事实具体、相关、同 owner、严格过去、无冲突、且 current context 中没有同义信息；
- `ASK`：连续性不确定，但基于该事实做一次 tentative check 有价值；
- `IGNORE`：echo、stale、resolved、conflict、wrong owner、vague 或对当前回复无增量；
- safe non-use 可以证明安全，但不能证明 MS Function；
- verified Function 由盲审看到 current context、原始过去 source、R0、R0+MS 后判断：差异是否由过去事实支持，且不能由 current context 单独解释。无需逐字提到 source。

### 联合顺序

```text
1. current turn / safety
2. MS grounding（若 USE/ASK）
3. RS strategy delta
4. 一个 coherent forward move 或 closure
```

开发阶段跑四臂 factorial，分别估 RS main effect、MS main effect 与 interaction，避免任何一个头搭另一个头的便车。

## 五、最快执行顺序

1. 零新增 generator 调用：独立复核现有 6 个 MS claimed-use rows，并配 matched safe-nonuse controls，先补 Function 洞。
2. 完成并测试 V4 compiler：`src/metacom_pm/v1_5_response_program_v4.py`。当前已建立 R0-invariant、RS delta、MS USE/ASK/IGNORE 和联合顺序。
3. 构建 outcome-blind development panels：Restatement/closure、current echo、stale/resolved、conflict、wrong owner、uncertain continuity 均要覆盖。
4. 继续用当前 Llama 跑小型四臂 development factorial；ESConv 以 dialogue 聚类，EvoEmo 以 owner 聚类，重复 state 只能提高簇内精度，不能膨胀独立样本数。
5. 只要开发晋级门通过，就一次冻结 selector、threshold、compiler、judge、margin、baseline 和 confirmatory sample；然后运行 ESConv RS、EvoEmo RS/MS、ES-MemEval memory QA。
6. 当前 generator 上成功后，再运行预先设计的 generator robustness 比较。它是后续 moderator/泛化研究，不是本轮救火变量。

## 六、当前研究状态应如何写

- RS：`CURRENT_REPLACEMENT_TREATMENT_FAILED; R0_PLUS_RS_DELTA_IMPLEMENTED_ZERO_API, QUALIFICATION PENDING`。
- MS：`DIRECTIONAL_POSITIVE DEVELOPMENT EVIDENCE; PROMOTED TO FUNCTION REVIEW AND R0_PLUS_MS QUALIFICATION; NOT FORMAL MS_pass`。
- generator：`FROZEN AT LLAMA FOR ROOT REPAIR; STRONGER-GENERATOR FACTORIAL DEFERRED`。
- Paper 1：尚未通过；但现在的下一步是在修复可识别性，而不是继续用错误 treatment 追求显著性，也不是换模型掩盖问题。

本文件与机器合同只授权零 API compiler、测试、已有输出复核和执行设计；不授权新 generator、judge、fit 或外测调用。
