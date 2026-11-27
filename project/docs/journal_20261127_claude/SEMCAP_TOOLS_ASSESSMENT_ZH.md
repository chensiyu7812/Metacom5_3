# 外部语义工具实际核查与能力测试

日期2026-11-27（JST）。只读浅克隆至本机`/opt/tokkio-data0/tokkio_runs/pmrl1-j-gsws-claude-20261127/external`，未执行其仓库代码；Maverick按PyPI官方包安装，MiniCheck按官方推理协议写最小适配层。全部在独立环境`/opt/tokkio-data0/tokkio_envs/semcap-tools-py311`（Python 3.11、torch 2.5.1+cpu、transformers 4.46.3），冻结GSWS推理环境未改。仅CPU，GPU调用0，付费调用0，未上传任何对话。

## 一、逐项核查

| 候选 | 代码/版本 | 公开权重 | 许可 | 输入→输出 | 本机运行 | 与已知失败的关系 | 结论 |
|---|---|---|---|---|---|---|---|
| Maverick coref | `SapienzaNLP/maverick-coref` 5c1fa62；PyPI `maverick-coref==1.0.7` | `sapienzanlp/maverick-mes-ontonotes` rev 087a90f，2.02GB，DeBERTa-v3-large编码器+mention-entity相似度 | CC BY-NC-SA 4.0（非商用；论文研究可用，产品部署需另行授权）；训练数据OntoNotes为LDC授权 | 纯文本或OntoNotes分词句列表，可带逐token说话人（说话人变化处插入`[SPEAKER_START] name [SPEAKER_END]`）→ 共指簇（token/char偏移）；OntoNotes模型不输出单例 | CPU加载6–30秒，平均0.38秒/前缀 | 第二人称“you/your”绑定到对方说话人、第三方指代链 | **接入**为说话人锚定共指组件 |
| MiniCheck | `Liyan06/MiniCheck` b58b9fa，Apache-2.0 | `lytang/MiniCheck-Flan-T5-Large` rev 96eafd0，MIT，3.14GB(fp32)，770M | 模型MIT；7B版另需商用联系 | 文档+单句claim → P(supported)；官方500词分块、取最大、`>0.5` | CPU加载0.3–6秒，0.3–0.55秒/条 | 证据支持；二分类，不能给出矛盾 | **接入**为支持判断组件，不当Judge |
| Bespoke-MiniCheck-7B | 同上，vLLM | 15.5GB InternLM2 | 非商用，商用需联系 | 同上 | 需GPU；本轮未批准 | 同上，更强 | 列入GPU申请候选 |
| MAVEN-FACT官方方法 | `THU-KEG/MAVEN-FACT` 6754471 | **无发布checkpoint**；DMBert(RoBERTa-large)、GenEFD(T5)、LLM prompting训练/推理代码 | 仓库无LICENSE；上游MAVEN-ED CC BY-SA 4.0，ARG/ERE GPLv3（沿用既有来源核查） | 句子+已标触发词 → CT+/PS+/PS-/CT-/Uu | 官方配方需GPU | 计划/可能/否定等事实性 | 复用已处理73,939条；**自建训练入口**，完整训练列入申请 |
| Generative Belief | `jmurzaku/generative-belief` b778a99（2023） | 仓库只有flan-t5-base config；权重在Google Drive | 代码未声明；训练数据FactBank为LDC授权 | 句子 → 来源/目标/事实性值序列 | 未下载 | 主体（信念持有者）+事实性联合表示有借鉴价值 | **只借鉴表示**，不作为可运行候选 |
| Graphiti | `getzep/graphiti` 2a4f079（2026-11-26），Apache-2.0 | 无模型，依赖外部LLM与图数据库 | Apache-2.0 | 消息episode → 实体/边，`valid_at/invalid_at`（事实时间）与`created_at/expired_at`（系统时间） | 未运行（需LLM+图库） | 报告时间vs事件时间、计划时间、冲突更新 | **借鉴时间机制**，不引入整套图库 |

## 二、Graphiti可迁移与不可迁移部分

可迁移到Memory Writer、Event Skill及GSWS：

1. 每个episode用自己的`reference_time`解释相对时间；多episode消息不共用当前日期。对应我们“历史中出现‘明天’不能按当前日期解释”。
2. 未来计划/承诺/排程：`valid_at`取**陈述时间**，未来发生日期保留在事实文本；软截止（“by Friday”）不是`invalid_at`。这正是“报告了计划 ≠ 计划已发生”的数据结构表达。
3. 双时间：事实有效区间与系统记录区间分开。旧记录失效时保留原记录及失效时间，不删除。

不直接迁移：

1. `resolve_edge_contradictions`在LLM判定矛盾后按`valid_at`先后**自动**让旧边失效，本质是“较新者自动为真”。我们保持冲突可见，只有明确的变化陈述才写失效时间。
2. Graphiti没有行动阶段（建议/计划/尝试/执行/结果）字段，计划被存为普通fact；GSWS的`stage`更细，应保留。
3. 其未来时检测本身就是正则（`_FUTURE_ASSERTION_RE`），说明成熟系统也只把词面规则用作日期归一化的护栏，而不是语义判断。我们同样只在确定性日期换算处使用。

## 三、实际能力测试（CPU，开发诊断）

两组材料：

- **event32**：Codex已冻结的8前缀×4命题（ESConv 4家族、EvoEmo p5/p6训练owner），参考由前一助手编写，已暴露。
- **speaker32（新）**：同一资格规则（fold6封存、train split、GSWS家族及event32家族排除），从294个“支持者用第一人称讲自己经历、随后用户发言”的候选中按加盐家族哈希选8前缀（ESConv 7、EvoEmo p5 1；p6无此类前缀）。在任何工具预测前由本助手冻结32条命题与参考（supported 16、unknown 14、contradicted 2），SHA见下方复跑。无独立真人，仅开发参考。

比较项（同模型、同阈值，未调参）：B=既有DeBERTa NLI，C=MiniCheck-FT5，D=MiniCheck判支持+仅NLI明确矛盾才判矛盾。前提渲染：`tagged`（原NLI格式`[C1] (seeker; report …) text`）、`attributed`（宿主确定性“The seeker (the user) said: "…"”）、`scoped`（自报型命题只核对其报告者本人的话轮；报告者取自命题的结构化主体字段）、`scoped+coref`（再用Maverick把已锚定到说话人的I/you改写为显式参与者）。

**speaker32（支持者自我披露，主体绑定压力最大）**

| 比较项 | 平衡准确率 | Macro-F1 | 非支持被判支持 | 主体交换误通过 | 缺证据判为矛盾 | 支持召回 |
|---|---:|---:|---:|---:|---:|---:|
| B NLI tagged | 0.637 | 0.529 | 8/16 | 8/13 | 2/14 | 0.625 |
| C MiniCheck tagged | 0.381 | 0.316 | 12/16 | 12/13 | 0/14 | 1.000 |
| C MiniCheck attributed | 0.503 | 0.484 | 6/16 | 6/13 | 0/14 | 0.938 |
| D attributed | 0.789 | 0.683 | 6/16 | 6/13 | 2/14 | 0.938 |
| B NLI scoped | 0.860 | 0.729 | 1/16 | 1/13 | 4/14 | 0.938 |
| D scoped | **0.881** | **0.751** | 1/16 | 1/13 | 4/14 | 1.000 |
| D scoped+coref | 0.863 | 0.734 | **0/16** | **0/13** | 4/14 | 0.875 |

**event32（旧开发对照）**

| 比较项 | 平衡准确率 | Macro-F1 | 非支持被判支持 | 主体交换误通过 | 缺证据判为矛盾 | 支持召回 |
|---|---:|---:|---:|---:|---:|---:|
| B NLI tagged（复现Codex） | 0.825 | 0.785 | 3/24 | 3/4 | 3/15 | 0.875 |
| D tagged | 0.911 | 0.881 | 1/24 | 1/4 | 3/15 | 1.000 |
| B NLI scoped | 0.867 | 0.833 | 0/24 | 0/4 | 6/15 | 1.000 |
| B NLI scoped+coref | 0.911 | 0.881 | 1/24 | 1/4 | 3/15 | 1.000 |

B tagged与Codex在paper1-py311中的原结果逐项一致（false-pass 3/24、正例拒判1、unknown过度判否3），说明新环境未改变既有NLI行为。

Maverick说话人锚定：16个前缀中289个单token I/you指称，与“两人对话中I=本说话人、you=对方”的确定性读法一致289/289，跨说话人合并簇0。第三方指代链只做了冒烟级检查，没有系统参考，不报告准确率。

## 四、能力判断

1. **主体误归属的大部分不需要训练语义模型。** 通用文档级grounding模型（NLI与MiniCheck）都不会自行把对话中的“I”绑定到说话人：即使显式写出“The supporter said”，MiniCheck仍让6/13的主体交换通过。把宿主已知的报告者身份变成结构（只核对报告者本人话轮）后降到1/13；剩下的1条是支持者话轮中指向用户的第二人称，由Maverick把you绑定到用户后为0/13。这符合“第一类确定性系统信息由宿主交付，第三类再交给模型”的分工。
2. **未知与否定仍是真正的语义缺陷。** MiniCheck从不把缺证据判为矛盾（0/14、0/15），但它天然不能给出矛盾；NLI能识别显式否定，却在证据受限时把“没看到”判成“矛盾”（scoped后4/14、6/15）。这类错误——“计划→已完成”“担心→已发生”“询问是否去做→已做”——正是第四节“缺少证据不等于没有发生”的核心，不能靠调阈值解决，是首个值得针对性学习的能力缺口（三分类：supported / contradicted / not-established，并要求说话人和行动阶段条件化）。
3. **MiniCheck的支持判断可复用，矛盾判断不能由它承担。** 组合D在两组都优于单用任一工具；但D的矛盾分支完全继承NLI的“缺证据判矛盾”问题。
4. 以上是64条暴露或助手编写材料上的开发诊断，差异1–2条在噪声范围内，尤其scoped与scoped+coref之间不能称显著。不得作为最终独立验证、自然支持Judge或reward。

## 五、MAVEN-FACT训练入口

`project/scripts/rl1v3/semcap/factuality_train.py`：触发词以`<t>…</t>`标记，前一句作上下文，DeBERTa-v3-base（本机已缓存）CLS五分类，逆平方根频率加权交叉熵，文档不相交internal_dev上报告Macro-F1、平衡准确率与各类召回。官方测试集不使用。明确为“条件化事件事实性识别”，不是端到端事件发现；CT+（文本断言确定发生）不等于现实中已发生。CPU冒烟只验证入口；完整训练需GPU，列入集中申请。冒烟实际结果见`semcap_v1/FACTUALITY_SMOKE_PUBLIC.json`。
