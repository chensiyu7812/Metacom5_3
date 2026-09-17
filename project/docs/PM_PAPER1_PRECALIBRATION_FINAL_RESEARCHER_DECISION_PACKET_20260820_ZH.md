# Paper-1 PRE-CALIBRATION FINAL REVIEW — Researcher Decision Packet（2026-08-20）

状态：**NO-GO TO OPEN `CALIBRATION_OUTCOME_LOCK`**
`CALIBRATION_OUTCOME_LOCK=CLOSED`；`CONFIRMATORY_OUTCOME_LOCK=CLOSED`；outcome calls=`0`；PM training=`0`；formal GPT-4o evaluation=`0`。

本结论不推翻 engineering GO。阻断来自两项 pre-calibration research qualification：当前 MP/ME semantic catalog 的固定种子人工审计出现明确错误；official ESC-RANK 尚未在可承载其 fp16 stack 的 GPU 上完成初始化、延迟和重复性 qualification。

## A. Memory candidate expansion audit

### A1. 3→378、401→1411、3→80 的精确原因

旧 `MP=3/MS=401/ME=3` 是 pre-semantic diagnostic：MP/ME 是极窄 regex，MS 是每个 source session 整段拼成一个 document，所以 401 sessions 恰好得到 401 MS。新口径在同一 401-session public runtime 上让 Qwen v6 提出 exact-span-grounded typed atomic units，经 local schema/grounding、semantic verifier、deterministic renderer 后得到 2,745 accepted units（MP 607/MS 1,997/ME 141）；outcome-blind version resolver 再停用 876 个旧版本（MP 229/MS 586/ME 61），留下 active `378/1411/80`。增长来自**构造器与原子粒度**，不是 ontology 扩张，也没有读取 `basic_info`。

### A2. 统一口径

`unique` 均指 full-history version resolution 后 active semantic units；edge 指 owner-matched unit 可供该 target 使用的一条 target×candidate edge。

| Task | Head | Unique units | Owners | Target-candidate edges | Target coverage |
|---|---:|---:|---:|---:|---:|
| QA | MP | 378 | 18 | 34130 | 1427/1427 |
| QA | MS | 1411 | 18 | 114868 | 1427/1427 |
| QA | ME | 80 | 18 | 6077 | 1427/1427 |
| Summary | MP | 378 | 18 | 2662 | 125/125 |
| Summary | MS | 1411 | 18 | 10488 | 125/125 |
| Summary | ME | 80 | 18 | 615 | 125/125 |
| DG | MP | 378 | 18 | 720 | 34/34 |
| DG | MS | 1411 | 18 | 2673 | 34/34 |
| DG | ME | 80 | 18 | 156 | 34/34 |

三类任务都覆盖 18 owners，因此 unique pool 相同；edge 不同是各 task target 数与 owner 分布不同，不是重复候选被重新算成 unique。

### A3. 分层随机人工审计

固定规则：`SHA256('paper1-precalibration-seed0' | memory_id)`，MP 每 field type 取 2，ME 每 outcome type 最多取 5。完整 20 个 MP 与 12 个 ME（含每条 full exact source turn、offset、prior relations、verifier reason）在 machine packet 内。代表性每层一例如下：

- **MP/age — smu_0576a6bbec8bc7334671542d — PASS**
  - source: `p15/esc1138`, rank=1, time=2024-06-10; strict-past `1 < 22`
  - exact source turn: `esc1138:turn:17` (seeker): I'm 26 [exact: I'm 26]
  - rendered: Profile fact [age]: I'm 26
  - compiler: MP must be a durable current owner profile fact; verifier: The span 'I'm 26' (span_17) directly supports the factual claim about the owner's current age, which is a durable profile fact. It is explicitly stated and contextually current.
  - audit reason: direct durable owner age
- **MP/education — smu_84af73261d0cfa43329a8722 — FAIL**
  - source: `p4/esc508`, rank=7, time=2025-03-01; strict-past `7 < 22`
  - exact source turn: `esc508:turn:4` (seeker): She's a year ahead of me in college and will be graduating in May. She's looking at jobs in the northwestern region, but I'd planned on looking at graduate schools in the south. However, we've always planned on living together after college, but my career path would be best served in the southern states. I don't know how to bring this up to her. [exact: She's a year ahead of me in college and will be graduating in May. She's looking at jobs in the northwestern region, but I'd planned on looking at graduate schools in the south.]
  - rendered: Profile fact [education]: The seeker is currently in college and plans to apply to graduate schools.
  - compiler: MP must be a durable current owner profile fact; verifier: The span 'She's a year ahead of me in college and will be graduating in May. She's looking at jobs in the northwestern region, but I'd planned on looking at graduate schools in the south.' clearly indicates the seeker is currently in college and plans to apply to graduate schools, supporting a current education status (MP).
  - audit reason: compound future plan is included in a current education fact
- **MP/enduring_interest_habit — smu_cca3b3479250db2ee9211765 — PASS**
  - source: `p16/p16_conv_19`, rank=23, time=2025-08-30; strict-past `23 < 25`
  - exact source turn: `p16_conv_19:turn:14` (seeker): I started painting a while back, mostly to manage stress, but now it feels like another thing I need to perfect. It's paradoxically stressing me out more. [exact: I started painting a while back, mostly to manage stress, but now it feels like another thing I need to perfect. It's paradoxically stressing me out more.]
  - rendered: Profile fact [enduring_interest_habit]: The seeker continues to engage in painting as a hobby intended for stress management.
  - compiler: MP must be a durable current owner profile fact; verifier: The seeker confirms they continue painting as a hobby originally intended for stress management, reaffirming a prior enduring interest/habit.
  - audit reason: ongoing owner hobby is durable despite a current consequence
- **MP/health_condition — smu_b7dad680d4ac06c9d6cc49d6 — FAIL**
  - source: `p3/p3_conv_15`, rank=18, time=2025-12-15; strict-past `18 < 28`
  - exact source turn: `p3_conv_15:turn:11` (seeker): Honestly, not great. I've had setbacks in my studies due to health issues recently, and this news just added to it. [exact: Honestly, not great. I've had setbacks in my studies due to health issues recently, and this news just added to it.]
  - rendered: Profile fact [health_condition]: The seeker is experiencing health issues affecting their studies.
  - compiler: MP must be a durable current owner profile fact; verifier: The seeker says, 'I've had setbacks in my studies due to health issues recently,' which directly supports the factual claim about experiencing health issues affecting studies. This reaffirms the existing MP 'The seeker is experiencing headaches and fatigue' (memory_id: smu_df7c08e4a82ebc5fbb806e03) as a current profile fact relevant to academic functioning.
  - audit reason: recent unspecified health difficulty is situational/insufficiently durable
- **MP/identity — smu_b0bcb752c4f581b626728e7f — FAIL**
  - source: `p16/esc538`, rank=3, time=2024-09-01; strict-past `3 < 25`
  - exact source turn: `esc538:turn:13` (seeker): That's a great idea. It is possible. I am the new kid on the block. I will try by being non confrontational. Any specific ideas to how  I can do that? She gets offended easily. I want her to know I am helping.  [exact: That's a great idea. It is possible. I am the new kid on the block. I will try by being non confrontational. Any specific ideas to how  I can do that? She gets offended easily. I want her to know I am helping. ]
  - rendered: Profile fact [identity]: The seeker identifies as 'the new kid on the block' at work.
  - compiler: MP must be a durable current owner profile fact; verifier: The seeker self-identifies as 'the new kid on the block,' establishing a current work identity relevant to role dynamics, qualifying as an identity-type MP.
  - audit reason: temporary new-kid-at-work narration is not stable identity
- **MP/location — smu_5d8e2c68bf39543a653b765f — PASS**
  - source: `p9/esc88`, rank=1, time=2024-07-15; strict-past `1 < 21`
  - exact source turn: `esc88:turn:15` (seeker): I'm in a rural area, and I'm interested in women. [exact: I'm in a rural area, and I'm interested in women.]
  - rendered: Profile fact [location]: The seeker lives in a rural area.
  - compiler: MP must be a durable current owner profile fact; verifier: The seeker states 'I'm in a rural area, and I'm interested in women.' in turn esc88:turn:15, which directly supports the claim about living in a rural area. This qualifies as a relatively durable location-based profile fact.
  - audit reason: direct current owner location
- **MP/occupation — smu_dceff7d7a9c7453af231d82b — FAIL**
  - source: `p3/p3_conv_17`, rank=20, time=2026-01-15; strict-past `20 < 28`
  - exact source turn: `p3_conv_17:turn:4` (seeker): Well, after everything that happened last year, with switching my major and the issues with my family and friends, I felt like something needed to change. [exact: after everything that happened last year, with switching my major and the issues with my family and friends]
  - rendered: Profile fact [occupation]: The seeker is in college and has switched to a new major.
  - compiler: MP must be a durable current owner profile fact; verifier: The seeker states they switched majors last year, which aligns with prior MP updates about changing to psychology. This reaffirms and updates the durable profile fact about their occupation as being in college with a new major, supported by direct seeker utterance and consistent with historical MS transitions.
  - audit reason: education/major history is mislabeled occupation and adds prior-table inference
- **MP/other_durable_profile — smu_6a6f47b47a3102227aea9bde — FAIL**
  - source: `p16/p16_conv_1`, rank=2, time=2024-07-25; strict-past `2 < 25`
  - exact source turn: `p16_conv_1:turn:2` (seeker): Hey! I've been feeling a bit off after attending my aunt's memorial service last week. [exact: Hey! I've been feeling a bit off after attending my aunt's memorial service last week.]
  - rendered: Profile fact [other_durable_profile]: The seeker attended their aunt's memorial service last week.
  - compiler: MP must be a durable current owner profile fact; verifier: The seeker explicitly states they attended their aunt's memorial service last week. This is a durable current-state fact supported by the exact span and co-refers with prior memories about the aunt's passing, making it a valid MP.
  - audit reason: one memorial attendance event is MS narration, not durable profile
- **MP/stable_social_role — smu_208c6bad2a293f000f4cda4c — REVIEW**
  - source: `p18/p18_conv_8`, rank=11, time=2025-07-25; strict-past `11 < 14`
  - exact source turn: `p18_conv_8:turn:3` (seeker): Well, Jane and I planned a surprise weekend getaway to try and reconnect, but I'm feeling a bit overwhelmed. [exact: Jane and I planned a surprise weekend getaway]
  - rendered: Profile fact [stable_social_role]: is married
  - compiler: MP must be a durable current owner profile fact; verifier: The span 'Jane and I planned a surprise weekend getaway' supports that the seeker is in a committed relationship with Jane, consistent with being married. The prior memory 'is married' (smu_5df6d661dd80ee1d529de3a5) is reaffirmed, and the actor matches. MP class requires durable current state, which marriage satisfies.
  - audit reason: marriage is stable but this turn only reaffirms it indirectly through a prior memory
- **MP/trait_tendency — smu_d4bc26a7361570f79b6ce3f5 — PASS**
  - source: `p15/esc119`, rank=3, time=2024-09-15; strict-past `3 < 22`
  - exact source turn: `esc119:turn:8` (seeker): I want to be in the program, it's just that I feel like everyone is so much smarter than me and my performance in that class makes me question my admission into the programs sometimes. When I feel like this after submitting homework, I end up crying because I just want to do well. I enjoy this field, just not this  class in particular.  [exact: I want to be in the program, it's just that I feel like everyone is so much smarter than me and my performance in that class makes me question my admission into the programs sometimes.]
  - rendered: Profile fact [trait_tendency]: I tend to doubt my academic worthiness despite wanting to be in the program
  - compiler: MP must be a durable current owner profile fact; verifier: The claim 'I tend to doubt my academic worthiness despite wanting to be in the program' is directly entailed by the seeker's statement in ss_2: questioning admission due to feeling less smart and poor performance. This reflects a stable tendency, suitable for MP with trait_tendency subtype, and is durably stated.
  - audit reason: recurrent self-doubt tendency is directly expressed
- **ME/mixed — smu_a27fb1d5fef2cf374dba67f2 — PASS**
  - source: `p6/p6_conv_10`, rank=14, time=2025-03-20; strict-past `14 < 25`
  - exact source turn: `p6_conv_10:turn:5` (seeker): We actually had a really deep conversation a few days ago. Lots of tears but good ones, I think. [exact: We actually had a really deep conversation a few days ago. Lots of tears but good ones, I think.] / `p6_conv_10:turn:7` (seeker): It was a mix of relief and lingering sadness. I’m happy we cleared the air, but all those pent-up emotions were exhausting. [exact: It was a mix of relief and lingering sadness. I’m happy we cleared the air, but all those pent-up emotions were exhausting.]
  - rendered: Past action: The seeker had a deep, emotional conversation with Eliza to reconcile after a prior argument. User-observed outcome [mixed]: The seeker experienced a mix of relief and emotional exhaustion, feeling that they cleared the air but were drained by the release of pent-up emotions.
  - compiler: ME must be an explicit completed owner action plus owner-observed outcome in one experience lineage; verifier: The seeker reports having a deep emotional conversation with Eliza involving tears and resolution, resulting in mixed feelings of relief and exhaustion. The action (conversation) and observed outcome (emotional mix and exhaustion) are directly stated by the seeker and grounded in the dialogue spans.
  - audit reason: explicit conversation action followed by mixed self-observed result
- **ME/negative — smu_5e2faa22b0229adba561ddae — FAIL**
  - source: `p13/p13_conv_4`, rank=5, time=2024-12-20; strict-past `5 < 23`
  - exact source turn: `p13_conv_4:turn:4` (seeker): It's been a lot at work. The pressure has really been getting to me lately, and I actually had a panic attack a few days ago. [exact: It's been a lot at work. The pressure has really been getting to me lately, and I actually had a panic attack a few days ago.]
  - rendered: Past action: had a panic attack User-observed outcome [negative]: I actually had a panic attack a few days ago.
  - compiler: ME must be an explicit completed owner action plus owner-observed outcome in one experience lineage; verifier: The seeker explicitly states 'I actually had a panic attack a few days ago' in turn 4, which supports both the action and observed outcome. The event is self-observed, completed, and within the owner's experience lineage.
  - audit reason: panic attack is duplicated as both action and outcome; no action-to-result lineage
- **ME/positive — smu_f88245e046ae62574296a29d — PASS**
  - source: `p3/p3_conv_5`, rank=7, time=2025-06-15; strict-past `7 < 28`
  - exact source turn: `p3_conv_5:turn:13` (seeker): Yeah, you're right. I did sort things out with him. It was tough, but I'm glad I pushed through. [exact: Yeah, you're right. I did sort things out with him. It was tough, but I'm glad I pushed through.]
  - rendered: Past action: resolved conflict with a friend previously User-observed outcome [positive]: felt glad about pushing through the conflict resolution process
  - compiler: ME must be an explicit completed owner action plus owner-observed outcome in one experience lineage; verifier: The seeker explicitly states they resolved a conflict with a friend ('I did sort things out with him') and expresses a positive observed outcome ('I'm glad I pushed through'), which aligns with prior MS memories about the conflict and reconciliation with Henry. The action and outcome are completed, self-observed, and form a coherent experience lineage.
  - audit reason: explicit conflict resolution and self-observed positive reaction

固定样本判定：MP `PASS=10/FAIL=8/REVIEW=2`；ME `PASS=10/FAIL=2`。因此结构门通过不能替代语义门：例如 panic attack 同时占 action/outcome slots 在 schema 上合法，却没有 action→observed-result lineage。

### A4. 硬隔离证明

- 401/401 ordered sessions 的 `source_sha256` 全量重建一致；401/401 `prior_memory_table_sha256` 一致；strict-prior violations=`0`。
- 实际 request projection keys 只包含 session turn 与 strictly-past accepted-memory slots；forbidden key hits=`0`。
- `basic_info=0`、simulator-only metadata=`0`、gold=`0`、future session=`0`、target outcome=`0`。
- enclosing user 上虽存在 QA questions/summaries，但 401 个存档 request hash 证明它们没有进入 `SessionCompileInput`。prior ME 的 historical outcome 是已发生 source-dialogue fact，不是 target outcome。

**A 决策：structural lineage PASS；current semantic MP/ME catalog NO-GO for calibration。** 本轮不改 ontology/compiler，也不为数量 rescue；`378/80` 只能继续作为 descriptive current counts，不能称为已审计有效的 formal inventories。

## B. RS pure-k calibration protocol

旧 `(1,48)/(2,64)/(4,128)` 作废，因为同时改变 k 与 cap。冻结协议：initial `k={0,1,2,3,4}`，所有 arm 共用 non-binding resource cap=`384`，actual injected tokens 每 trajectory 单独记录，Step2 utility filter 继续禁止。

| k | Current prefix full-k fraction | Token median | Token p95 | Token max | Family median | Same-source-card fraction |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1.0000 | 0 | 0 | 0 | 0 | 0.0000 |
| 1 | 0.9989 | 16 | 22 | 38 | 1 | 0.0000 |
| 2 | 0.9926 | 32 | 42 | 56 | 2 | 0.1303 |
| 3 | 0.9731 | 49 | 61 | 76 | 2 | 0.2528 |
| 4 | 0.9281 | 66 | 80 | 101 | 3 | 0.3518 |

初始 grid 的 observed truncation=`0/11,883` at every k。表中 k>0 的少量 zero/full-k 缺口来自旧 raw top-4 prefix 先排序后 collapse exact aliases、无法 rank>4 backfill；因此这张 surface 只验证 cap，不授权 Generator call。正式调用前须在 canonical catalog 上重排并 backfill。

预注册 expansion：只有 `k=4` calibration mean 为最高，且 `k=3` 落在相对 k=4 的 one-SE admissible set 之外，才一次扩展 `k={6,8}`。扩展前先 materialize canonical top-8，并为所有 k 重审同一个 non-binding cap；不读 confirmatory outcome。

## C. Exact-treatment canonicalization

- 15,061 raw atomic units → 13,172 exact treatments；extra exact aliases=1,889。
- identity 仅为 UTF-8 byte-exact `rendered_card_text` SHA-256。
- union 完整保存 `atomic_card_ids/source_card_ids/source_dialogue_ids/families`；leave-dialogue-out 对 union 保守排除。
- 每个 treatment 只有一个 deterministic representative：最小 `(source_card_id, atomic_card_id)`，每 query 只产生一个 BGE score；禁止 duplicate max/mean pooling 或 occurrence-frequency prior。
- near duplicate 一律保留；没有 cosine/semantic threshold deletion。
- 三个机械回归覆盖 exact collapse+union、duplicate 不增加 ranking ticket、near duplicate 不删除。

**C 决策：规则关闭；当前 old top-4 census 尚须按该规则重排，不能直接用于 calibration。**

## D. ESC evaluator final feasibility

official ESC-RANK 是 reference/primary candidate；缺少公开 item-level human labels 不构成 ESC evaluation blocker，只限制 alternative judge agreement qualification。

| Check | Result |
|---|---|
| Pinned repo | `9ad46e7b5e247e824dae4633910eaa82be668beb` |
| Local GPU/RAM | RTX 2070 8,192 MiB；RAM 7.7 GiB |
| Actual `score.py` initialization | exit 1 after 4.76 s; max RSS 546868 KiB |
| Failure | `peft` absent，模型加载前失败；GPU allocation=0 |
| Capacity | InternLM2-chat-7B fp16 shards ≈15.49 GB，权重本身已超过 8 GiB |
| Official-code issue | first adapter path 写作 `ESC-RANK1/*`，与下载目录 `ESC-RANK/*` 不一致；需 pinned minimal correction |
| Latency/reproducibility | 本机无法测；不得伪填 |

**D 决策：不改用 alternative；租用 ≥24 GiB GPU 对 official ESC-RANK 做一次 pinned qualification。** 记录 load peak VRAM、cold/warm latency、seven-dimension vector latency、parse rate，并让至少 3 条 blind dialogue 重复两次得到 exact same vectors。只有 ESC-RANK 在该环境仍不实用，才由 researcher 提名 alternative。Qwen 永远只是 proxy，按 agreement/cost 与 ESC-RANK 比，禁止按 PM/Ours 得分选。

## E. Split/fold human-readable packet

### ESC non-ESConv English role cards

| Scenario | Calibration | Confirmatory | Calibration source counts | Calibration category counts | Max source/category fraction gap | Non-ESConv primary | ESConv overlap slice |
|---|---:|---:|---|---|---:|---:|---:|
| small_24 | 24 | 149 | {'EPITOME': 3, 'ExTES': 7, 'MHP': 10, 'Psych': 4} | {'家庭生活': 12, '工作学习': 6, '社会与其他': 6} | 0.1130/0.0491 | 173 | 158 |
| medium_36 | 36 | 137 | {'EPITOME': 3, 'ExTES': 13, 'MHP': 15, 'Psych': 5} | {'家庭生活': 20, '工作学习': 8, '社会与其他': 8} | 0.0544/0.0064 | 173 | 158 |
| large_52 | 52 | 121 | {'EPITOME': 3, 'ExTES': 21, 'MHP': 21, 'Psych': 7} | {'家庭生活': 29, '工作学习': 11, '社会与其他': 12} | 0.0288/0.0139 | 173 | 158 |

population=`173` non-ESConv cards（EPITOME 5/ExTES 70/MHP 73/Psych 25；家庭生活 95/工作学习 39/社会与其他 39）。三个 scenario 只用 metadata、seed=0；比例仍未选择。158 ESConv-source cards 始终是 overlap sensitivity slice，不进入 primary split。

### RQ2 K=5, seed=0

`component_count` 即 exact mechanical fact/event evidence clusters。

| Fold | Users | QA | Summary | DG | Fact/event clusters | Total targets |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 17 | 286 | 25 | 6 | 94 | 317 |
| 1 | 18 | 285 | 25 | 7 | 95 | 317 |
| 2 | 18 | 285 | 25 | 7 | 95 | 317 |
| 3 | 18 | 286 | 25 | 6 | 96 | 317 |
| 4 | 18 | 285 | 25 | 8 | 97 | 318 |

最大 range：users=1、QA=1、Summary=0、DG=2、clusters=3、total targets=1；最大 max/mean 分别为 1.0112/1.0021/1.0000/1.1765/1.0168/1.0025。1,586 targets exactly once，477 components atomic，无 missing/duplicate target；held-out target outcome isolation=true；semantic shared-session grouping 仅 sensitivity；seed shopping=FORBIDDEN。K=5 seed=0 保留。

## Researcher decision

1. **现在不得开启 calibration outcome lock。**
2. RS pure-k、exact canonicalization 和 split/fold 决策已关闭；尚需 canonical rerank 的工程物化。
3. Memory 当前计数解释成立，但 MP/ME formal semantic validity 未通过这次 sample audit；先处理该问题，再做 calibration。
4. ESC-RANK 保持 official reference/primary；先租 ≥24 GiB GPU qualification，不先烧 Qwen proxy。
5. 全程 outcome calls=`0`、PM training=`0`、formal GPT-4o=`0`。

机器包：`project/data/paper1_authority/paper1_precalibration_final_researcher_decision_packet_20260820_v1.json`
Memory 全例审计：`project/data/paper1_authority/paper1_precalibration_memory_candidate_audit_20260820_v1.json`
