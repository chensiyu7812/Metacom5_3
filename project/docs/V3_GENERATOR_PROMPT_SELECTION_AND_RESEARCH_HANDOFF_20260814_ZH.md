# V3 Generator提示词、ESC-Eval选型与研究主链交接

日期：2026-08-14  
状态：`72 DIALOGUES / TWO BLINDED HUMAN PACKETS READY / HUMAN SCORES PENDING`

## 当前结论

尚未选定generator。当前可进入选型的只有：

| 配置 | 24卡完整率 | median latency | 本轮USD | 当前身份 |
|---|---:|---:|---:|---|
| Llama 3.1 8B | 24/24 | 0.39s | 0 | incumbent |
| Qwen 3.7 Plus non-thinking | 24/24 | 2.79s | 0.04935 | deployment challenger |
| Qwen 3.7 Plus thinking | 24/24 | 20.40s | 0.24697 | capability upper bound |
| Nemotron 3 Nano 30B A3B hosted route | 21/24 | 2.15s（成功请求） | 0 | reliability hard fail；退出winner计算 |

ESC-RANK的651/651本地推理已经完成，但严格parser为0/651、预注册anchored sensitivity虽然651/651有效却高度饱和。它完成了描述性外部自动评分责任，不能选出winner。此前E-I-A的144-call LLM judge方案已在调用前废止，0调用、`$0`。

## 唯一生效的supporter prompt

权威文件：`data/v3_authority/g0_research_aligned_supporter_prompt_v1.json`

- artifact SHA256：`f4cabca6c4d0ad2bdc3a4614405957c4220dffd92896cf28a7799ff91fe42661`
- 实际拼接文本SHA256：`e5d9c937c729dcd6214ace6fff3421659ed9eab06d04b976f6df0b3589a9e73f`
- researcher output cap：无；provider output参数省略；自然完成是测量结果。

提示词要求generator作为非临床情绪支持supporter：使用完整对话；根据readiness在Exploration、Insight、Action之间选择；不确定时先探索而非抢跑建议；只使用当下必要的支持动作；不虚构个人事实、诊断、动机或自身经历；回复自然、低负担且不泄露策略、计划、资源或内部scaffold。

设计谱系是ESConv、LLM emotional-support评测、ExTES、ESCoT和ESC-Judge。它不是官方`You are a helpful assistant!`零样本wrapper，因此论文命名固定为`ESC-Eval English research-aligned protocol repair`。所有candidate、所有后续PM arm与所有baseline必须使用完全相同的prompt；不允许根据人评或PM结果再改。

## Prompt公平性与剩余风险

已经通过：

- 无候选模型名、provider名、PM head或测试答案；
- 四候选同prompt、同24张卡、同五轮、同role-player revision；
- 无候选特异token cap；
- candidate动态轨迹不同，但这属于ESC-Eval互动协议本身；统计单位仍是card/dialogue。

必须单列的边界：

- 官方Information rubric会奖励建议数量，可能与低负担原则冲突，因此`low_burden`与`no_premature_action`只作独立项目guardrail，不改写官方分数；
- Qwen thinking的隐藏reasoning显著增加token、费用与延迟，只有官方Quality达到预注册优势才可保留；
- 24张卡已被开发使用，只能选development winner；不得称完整ESC-Eval或paper-grade资格；
- 无真实用户或临床安全外推。

## 当前唯一正确的选型步骤

1. Human A与Human B分别打开各自HTML，对全部72段对话按官方七维0–4分独立评分；每人只看单段对话，顺序不同且看不到模型/provider/card/source。
2. 任一维度分差至少2分，或packet/项目guardrail出现异常，才交给Human C独立盲裁决；Human C看不到前两人的分数。
3. 聚合程序按冻结规则计算：小分歧取双评均值，大分歧取三评中位数；不会自动修改门槛。
4. development decision contract先过可靠性、绝对下限和完整性硬门，再看Overall主指标以及Empathy、Skill、Information。
5. 若质量等价，才以实际USD、再以median latency决胜；thinking若不能优于non-thinking，不得靠“理论更强”保留。
6. development winner继续通过approved-plan/evidence executor，并与最强非支配challenger进入冻结英文确认集；二者完成后才能称本研究generator合格。

## 选定generator后的完整研究主链

1. 冻结generator route、thinking mode、prompt、decoding、retry、token与cost accounting。
2. 在同一generator下分别资格化RS additive delta、MP plan constraint、MS response-plan-relevant USE/ASK；Function只需非零、source-aware、可复现，不再作为主观绝对否决权。
3. 只有固定treatment有安全正向边际价值后，才训练低容量selector。
4. 同时冻结always-off、fixed-high、transparent-rule、cost-matched-fixed、cost/ON-rate-matched-random、full-minus-component与safe-oracle。
5. 正式运行ESConv RS、EvoEmo纵向response/joint policy、ES-MemEval-Public-v1.0.0-1427三条外测；按dialogue/user聚类，EvoEmo与ES-MemEval不得冒充独立人群复现。
6. 第一主张要求`RS_pass AND count_pass(MP,MS,ME)>=2`，最快组合仍是RS+MP+MS；ME只在主链稳定后有界救援。
7. 正式结果不回流修改prompt、sample、head、threshold或baseline。若需要generator-agnostic主张，在主结果成立后再加一个更强跨家族generator复现。

## 现在的人工交付物

- Human A：`outputs/v3_g0_esc_eval_human_review_v1_20260814/human_a_review.html`
- Human B：`outputs/v3_g0_esc_eval_human_review_v1_20260814/human_b_review.html`
- 聚合：`scripts/v3/28_aggregate_g0_esc_eval_human_review.py`
- 决策：`scripts/v3/29_decide_g0_esc_eval_development_generator.py`

当前真正的阻塞不是API、prompt或程序，而是两份独立人类评分。任何自动LLM分数都可以后补作敏感性分析，但不能冒充这一步。
