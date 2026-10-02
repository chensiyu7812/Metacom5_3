# Paper-1 pre-outcome amendment：v1 → v2 逐项差异

> `PROPOSED RESEARCH CHANGE — NOT AUTHORIZED`

| 主题 | v1 | v2 |
|---|---|---|
| 主问题 | ontology 与执行清理 | 保留 ontology，并新增“effect 老师能否定义正确 ON/OFF”的测量可识别性 |
| threshold | 错误恢复 fixed 0.5 primary | 继承 8/31 grouped-OOF / outer-training-inner-OOF one-SE→minimum-token；0.5 仅 reference |
| Matched-Random | token-bin 候选置换措辞有歧义 | 只随机 opening location；state-specific exact bundle不变，不跨 state换内容 |
| MP | current profile/state 较宽 | 仅 stable/slot-like current profile；transient state进入 ME |
| joint memory | interaction audit | 另预冻结 global budget、whole-session packing、collision/overflow与 trace |
| factuality | 小 audit、无比例门 | 固定分层样本/错误 taxonomy；系统性 bug仅一次 general repair；不无限 DEV loop |
| amount claim | calibration/dose-response混合 | calibration选 k；held-out secondary才支持 diminishing-returns claim |
| effect coding | 未写清四 task 的 exact hierarchy | ESC/QA/Summary/DG 分别定义 primary、guard、tie与 uncertain |
| 当前代码 Pareto | 未识别为主缺陷 | 明确撤回所有指标等权、任意非零差值的 Pareto overlay |
| judge角色 | official metric笼统作为老师 | final official scorer、resource auditor、realized pairwise teacher三者分开 |
| judge输入 | 未冻结 | task-specific visibility matrix；只给 official rubric允许的 context/gold/reference/observation |
| judge blindness | arm blind原则 | 再加 resource-bundle blind、A/B order hash、dual-order stability与 equivalent类别 |
| teacher qualification | 无 | 96-pair 双人盲评 reference；按 human agreement→order stability→equivalent recall→reliability→cost选择，不按正例率/PM结果 |
| ESC | ESC-RANK final scorer | final scorer不变；Overall primary、Empathy/Information guards，tie由 calibrated pairwise teacher处理 |
| QA | 等权 Pareto F1/BERT/judge | 0–2 semantic judge primary；gold-based pairwise解决 tie/conflict；F1/BERT辅助 |
| Summary | 两 arm 可分别抽 reference events | 共用冻结 reference-event inventory；Event F1 primary、0–5 LLM guard、ROUGE explanatory |
| DG official models | 笼统 GPT-4o | Mistral‑24B做 observation relevance/usage；GPT‑4o做完整 dialogue三维 ratings |
| DG因果层次 | 未区分 | fixed-prefix local decision effect与 interactive end-to-end trajectory分开 |
| repeats | 沿用 soft/binomial repeats | temp=0/seed=null相同 prompt输出不视为独立；独立 state为 primary unit；judge repeats仅估噪声 |
| “正确 ON/OFF” | 未定义 oracle来源 | 定义为 frozen-stack、task-specific official hierarchy下的 local counterfactual benefit/nonbenefit |
| decision proof | 主要靠最终 arm对照 | 新增 OOF/held-out local decision audit：ON recall、OFF specificity、unnecessary-open、missed-benefit、BA与 calibration |
| selector proof | Learned vs Random | 保留；明确与 local accuracy不同，要求 same ON count/token distribution |
| global regret | 未讨论 | 交互式任务不从 myopic local oracle声称 global policy regret |
| curriculum | 资源 correctness为主 | 分开 resource correctness与 effect-label correctness；用 runtime-visible strata，不用 gold capability labels |
| failure处理 | 容易继续修门 | teacher弱则 uncertain/claim contraction；不阻塞整篇、不换能制造更多 ON 的 judge |
| 新 artifacts | 无 oracle一级 artifacts | alignment、oracle、teacher qualification、task coding、decision audit五个 machine contracts |
| outcome locks | CLOSED | 继续 CLOSED；v2获批后先物化 contracts/implementation，再申请 calibration/formal calls |

v2 没有修改 frozen Generator、四个 L2 heads、Route A、public-only sources、RQ1/RQ2 official final metrics、cross-fitting原则或 Cost与label分离原则。它修正的是 ontology、effect measurement 与可解释性，不是 outcome-conditioned方法搜索。
