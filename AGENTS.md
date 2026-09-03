# Repository Research Authority for Codex / Agents

Before making any research-design, evaluation, baseline, training-data, PM-semantics, feature, measurement, CI, or Paper-1 execution change, read first:

1. `project/docs/PM_PAPER1_CLIENT_OBSERVED_LATENCY_AND_FRONTIER_AMENDMENT_20260903_V2_ZH.md`
2. `project/data/paper1_authority/paper1_client_observed_latency_and_frontier_amendment_20260903_v2.json`
3. `project/data/paper1_authority/paper1_client_latency_measurement_contract_v2.json`
4. `project/docs/PM_PAPER1_LATENCY_CONSTRAINED_SELECTIVE_POLICY_AMENDMENT_20260903_ZH.md`
5. `project/data/paper1_authority/paper1_latency_constrained_selective_policy_amendment_20260903_v1.json`
6. `project/docs/PM_PAPER1_OFFICIAL_ESC_EVAL_COMPATIBILITY_AMENDMENT_20260902_ZH.md`
7. `project/data/paper1_authority/paper1_official_esc_eval_compatibility_amendment_20260902_v1.json`
8. `project/docs/PM_PAPER1_THRESHOLD_POLICY_CALIBRATION_AMENDMENT_20260831_ZH.md`
9. `project/data/paper1_authority/paper1_threshold_policy_calibration_amendment_20260831_v1.json`
10. `project/docs/PM_PAPER1_PREQUALIFICATION_CONSOLIDATION_AMENDMENT_20260820_ZH.md`
11. `project/data/paper1_authority/paper1_prequalification_consolidation_amendment_20260820_v1.json`
12. `project/data/paper1_authority/paper1_master_decision_register_20260820_v1.json`
13. `project/docs/PM_PAPER1_RESOURCE_AMOUNT_AND_EVALUATOR_CALIBRATION_AMENDMENT_20260820_ZH.md`
14. `project/data/paper1_authority/paper1_resource_amount_and_evaluator_calibration_amendment_20260820_v1.json`
15. `project/docs/PM_PAPER1_SEMANTIC_MEMORY_COMPILER_AMENDMENT_20260817_ZH.md`
16. `project/data/paper1_authority/paper1_semantic_memory_compiler_amendment_20260817_v1.json`
17. `project/docs/PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md`
18. `project/data/paper1_authority/paper1_execution_reconciliation_20260816_v1.json`
19. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
20. `project/docs/PM_PAPER1_OFFICIAL_EVALUATION_PRIORITY_20260816_ZH.md`
21. `project/data/pm_v1_5_contracts/pm_paper1_official_evaluation_priority_20260816_v1.json`
22. `project/docs/PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md`
23. `project/data/pm_v1_5_contracts/pm_paper1_final_execution_blueprint_20260816_v1.json`
24. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
25. `project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`

These are the active Paper-1 authorities.

The 2026-09-03 amendments are operationalized by the active machine contracts
`paper1_client_latency_measurement_contract_v2.json`,
`paper1_training_evaluation_alignment_contract_v1.json`,
`paper1_pairwise_effect_oracle_contract_v1.json`,
`paper1_pairwise_teacher_qualification_plan_v1.json`,
`paper1_task_effect_coding_v1.json`,
`paper1_decision_correctness_evaluation_v1.json`,
`paper1_end_to_end_latency_policy_contract_v1.json`, and
`paper1_natural_turn_appropriateness_rubric_v1.json` under
`project/data/paper1_authority/`.

## Authority precedence

- **The 2026-09-03 client-observed latency/frontier V2 amendment has scoped precedence only** over V1's PM-runtime timing boundary, mandatory tighter task SLA, and hard-SLA-first primary selection. Primary latency is client send-to-final-visible p95; client send-to-first-visible p95 is the experience guardrail. The only primary catastrophic constraint is Client E2E Completion `< 60000 ms`; tighter budgets are optional named deployment scenarios/sensitivities and cannot block Paper execution. Among catastrophic-feasible policies, use official-quality one-SE admissibility then minimize client p95/median completion, p95 TTFT, tokens and ON rate. Report the quality-latency frontier without a project composite or binary PASS/FAIL.
- **The 2026-09-03 latency-constrained selective-policy V1 amendment remains the historical base** for separating pure quality effect from deployment action-worthiness and for natural-turn restraint. Its backend timing boundary, mandatory tighter task SLA and hard-SLA-first Paper selection are superseded by the V2 clause immediately above.
- **The 2026-09-02 official ESC-Eval compatibility amendment has scoped precedence only** over the project-added full-string ESC-RANK parser, its runtime readiness gate, and any evaluator-winner wording that could replace the official RQ1 scorer. The primary RQ1 capability scorer must reproduce the pinned official `score.py` parser and seven adapter/rubric mappings. Strict/full-string and multi-label checks are supplemental diagnostics only. Qwen, DeepSeek, and an independent-family judge remain blinded qualification/sensitivity candidates but cannot replace official ESC-Eval in the RQ1 main capability table. It does not open any outcome lock or alter PM, Generator, arms, splits, metrics, or claims.
- **The 2026-08-31 threshold-policy-calibration amendment has scoped precedence only** over the fixed-0.5-primary-policy clause. The four heads still learn materially-positive paired-effect probability with Cost excluded from label/loss. The primary operating point is selected only from grouped OOF or outer-training/inner-OOF effects by the frozen quality-first one-standard-error then minimum-Generator-input-token rule. Confirmatory and held-out outer-target outcomes are forbidden; fixed 0.5, eligible-always-on, and always-off remain mandatory references. It does not alter the learner, ontology, Route A, public sources, Generator, benchmark arms, or official metric hierarchy.
- **The 2026-08-20 pre-qualification consolidation amendment has scoped precedence only** for the six-layer qualification/calibration/evaluation sequence, the four independent RQ1/RQ2 calibration/confirmatory locks, exact-treatment canonical Top-8 materialization, qualification packet/harness requirements, semantic-compiler precision requalification, and master decision status vocabulary. It does not alter the core research route, learner, threshold, Generator, public-source rule, benchmark arms, or official metric hierarchy.
- **The 2026-08-20 resource-amount/evaluator-calibration amendment has scoped precedence only** for downgrading RS Top-1 from final primary to a calibration candidate, the amount/evaluator calibration sequence, the split calibration/confirmatory outcome locks, exact treatment-alias canonicalization, and outcome-blind split/fold feasibility. It does not alter the four heads, Route A, L2 learners, 0.5 threshold, public-only sources, Generator, official metric hierarchy, or benchmark arms.
- **The 2026-08-17 semantic-memory-compiler amendment has scoped precedence only** for MP/MS/ME semantic candidate construction, factual extraction/verification, the BGE-M3 formal-similarity requirement, diagnostic-only regex/Jaccard status, and compiler API/cache/cost rules. It does not alter the four-head ontology, research claims, learning route, Generator, public-only rule, cross-fitting, threshold, outcome lock, or official-evaluation hierarchy.
- **The execution reconciliation override remains controlling** for Generator identity, benefit-only soft targets, removal of empirical PASS gates, treatment-delivery validity, exact-evidence cross-fitting, and per-head claim reporting. Its fixed-0.5-primary-policy clause alone is superseded by the 2026-08-31 scoped amendment.
- **Research scope / claims** are governed by `PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`.
- **Final evaluation / measurement hierarchy** is governed by `PM_PAPER1_OFFICIAL_EVALUATION_PRIORITY_20260816_ZH.md` and its machine-readable contract. Official ESC-Eval / ES-MemEval capability metrics outrank all internally defined Quality/Risk/Function rubrics.
- **Implementation-level feature schema, leakage controls, CI migration, freeze items, and execution order** are governed by `PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md` and its machine-readable contract.
- If the older training contract or V5.3 code conflicts with these authorities, **do not change the research design to match old code**. Report the conflict and migrate the implementation.
- Do not silently resolve a pre-outcome research choice. If a required freeze item is not determined by the zero-outcome audit, mark it `IMPLEMENTATION BLOCKER — RESEARCHER DECISION REQUIRED`.

## Critical data rule — public sources only

Paper 1 uses only public prior-work resources for active training/effect/evaluation:

- `ESConv` -> RS Strategy-RAG resource/training;
- `ESC-Eval` -> RQ1 evaluation only;
- `ES-MemEval/EvoEmo` -> MP/MS/ME training/candidate source and RQ2 evaluation.

**Do not read, sample, audit, repair, compile, retrieve from, train on, validate on, or cite for Paper 1 any obsolete synthetic longitudinal training data.**

In particular, the entire path below is deprecated and off-limits for active Paper-1 work:

`project/data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/`

The same applies to any old synthetic 80-user/11-user derivatives, old 256 effect labels, old background-conditioned effect rows, and old MS fallback labels. Historical files may remain in Git history/archive branches only for provenance.

## Non-negotiable semantics

- Method name: **Policy Manager (PM)**, not MetaCom.
- Generator is already frozen, but formal Paper-1 work must bind it in a new full-stack freeze manifest.
- `RS`: inject-or-not the globally amount-calibrated retrieved Strategy-RAG bundle of atomic-move units; not strategy-category prediction. Top-1 remains a candidate amount, not a predeclared final primary.
- `MP`: **Profile Memory only**. No MP_PREFERENCE / response_preference_history.
- `MS`: strictly-past same-user cross-session/session-continuity memory; no current/last-message fallback.
- `ME`: strictly-past action -> user-observed-outcome experience memory.
- Four binary heads; runtime still admits 16 combined resource configurations; no direct 16-class learner.

## Paper-1 learning route A

- Each head learns first-order state x eligible-candidate marginal utility.
- Formal ON/OFF effect contrasts use the canonical background: **all other optional components OFF**.
- Other-component ON/OFF bits are not final head features.
- Interaction-aware/background-conditioned learning is future work only.
- `ineligible` is deterministic OFF and not a learned negative example.
- Primary learner remains four standardized L2-regularized logistic-regression heads.
- Repeated effects are retained as soft/binomial supervision and uncertainty; they do not create a 70%/agreement/uncertain-fraction PASS gate.
- Cost is not part of the pure quality-effect training label or loss. Client-observed text latency enters deployment action-worthiness and the quality-latency frontier. The Paper primary rejects only catastrophic p95 completion at or above 60000 ms, then uses quality one-SE admissibility followed by minimum client p95/median completion, p95 TTFT, tokens and ON rate. Tighter deployment budgets are optional named sensitivities, not research blockers or PASS gates. Fixed 0.5 remains a mandatory transparent reference, not the unique primary.

## Feature rule — outcome-blind raw observables only

The feature layer may describe the current state and exact eligible candidate, but it must not estimate resource utility before the PM.

Allowed examples: fixed similarity, raw candidate/profile type, already-visible/redundancy flags, relative age, deterministic entity/thread overlap, explicit current-turn request markers, structural token cost.

Forbidden examples: `worth_opening`, subjective `helpfulness`, subjective `response_feasibility_impact`, subjective `transferability`, subjective `continuity_need`, subjective `scope_specificity`, response/judge/gold/future fields, preference metadata, other-component bits.

The active feature schema is defined in `PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md`.

## Evaluation authority — official benchmark first

- **Paper-1 final capability verdict is based on prior-work official metrics, not our internal Quality/Risk/Function rubric.**
- RQ1 final benchmark: ESC-Eval; arms `R0 / RS Fixed-High / RS Matched-Random / Learned RS-PM`; report official `Fluency / Expression / Empathy / Information / Skillful / Humanoid / Overall`.
- Because the Strategy Bank is ESConv-derived, the primary RQ1 transfer analysis uses non-ESConv-source English role cards; the full frozen English set is secondary and ESConv-derived cards are an overlap sensitivity slice.
- RQ2 final benchmark: ES-MemEval; arms `No Memory / Full History / Official RAG Top-4 / Typed Fixed-High / Typed Matched-Random / Learned Typed-Memory PM`; report official QA / Summarization / Dialogue Generation metrics.
- RS stays fixed in ES-MemEval main analysis.
- Component-minus `-MP/-MS/-ME` are ablations and must be interpreted through official ES-MemEval metrics.
- Formal claims require same-stack reruns with the frozen Generator.
- Do not create a post-hoc composite or pick only favorable metrics.
- **Internal Quality/Risk scorers are training-only / qualification / supplemental diagnostics. They must not become Paper-1 primary metrics or the final verdict.**
- Objective Cost is a separate efficiency axis and may be reported beside official metrics, but it is not a capability score and cannot compensate for material official-metric degradation.
- Formal benchmark runners must not use internal Q/R as their primary scorer or aggregate internal Q/R into a paper result composite.

## Data / leakage authority

- Strategy Bank: ESConv train only.
- Formal RS effect construction must use leave-current-dialogue-out / fold-exclusive Strategy Bank retrieval.
- Memory training/effect/candidate source: public ES-MemEval/EvoEmo only, with outcome-isolated cross-fitting.
- Runtime PM never sees evaluation gold, outcome, reference, or future sessions.
- Same-user longitudinal adaptation is allowed with target-outcome isolation. Primary folds use exact mechanical target/evidence lineage; broad semantic/shared-session components are sensitivity only.
- No synthetic rescue for a sparse or failed head.

## Treatment validity

- Hard invalidation is limited to mechanical delivery/identity/integrity failures: compiler/schema failure, missing or mismatched assigned resource, wrong owner, future/gold leakage, arm/seed/prompt/candidate mismatch, terminal empty generation, or unparseable official scorer.
- If the assigned resource was correctly delivered, Generator non-use, misuse, omission, or harm is a valid realized end-to-end effect. Semantic adoption is diagnostic only and must not filter rows.

## Immediate implementation order

Do not start formal PM training first.

1. **Repository-to-contract audit** against the execution blueprint and official-evaluation-priority authority.
2. Phase 0: disconnect obsolete synthetic active paths/configs/tests; remove MP_PREFERENCE/background-bit/utility-like active features; add fail-closed CI guards; establish a public-only Paper-1 config; audit that internal Q/R is not wired as a formal benchmark verdict.
3. Phase 1: run a **public-only zero-outcome coverage audit** on ESConv + ES-MemEval/EvoEmo.
4. Phase 2: build zero-outcome amount surfaces; qualify the evaluator against a PM-blind human reference; run only authorized external calibration; then freeze global k/bundle/token budgets, exact feature schema, exact mechanical cross-fit grouping, task-specific effect anchors, Generator/Step2 full-stack manifest, seed schedule, operating-point selection protocol, matched-random construction and API call plan.
5. Generate repeated matched effects and preserve ON wins/OFF wins/ties/uncertain as soft supervision; no empirical qualification PASS gate.
6. Train four L2 heads with grouped/fold-specific OOF probability predictions.
7. Select head/task/fold Paper-primary operating points only from grouped OOF or outer-training/inner-OOF effects: reject catastrophic client p95 completion at or above 60000 ms, apply official-quality one-SE admissibility, then minimize client p95/median completion, p95 TTFT, tokens and ON rate; tighter deployment scenarios are sensitivity outputs and never use confirmatory or held-out outer-target outcomes.
8. Keep confirmatory outcomes locked until the full stack, including operating points, is frozen; then freeze baselines/matched-random schedules and run RQ1, RQ2, and component-minus using official outcomes.
9. Report realized N, coverage, fixed-0.5/always-on/always-off references, official metric contrasts, Cost and clustered uncertainty without a binary Paper-1 PASS/FAIL or head-count gate.

## Drift prevention

Do not silently change the active authority to match old code.

Any proposed change to frozen research scope must first be written as:

`PROPOSED RESEARCH CHANGE — NOT AUTHORIZED`

and must state what clause changes, why, what prior results become invalid, what must be rerun, and whether the paper claim changes. Wait for explicit user approval.

Any implementation limitation that prevents the active public-data-only plan must be written as:

`IMPLEMENTATION BLOCKER — RESEARCHER DECISION REQUIRED`

with the missing public evidence, affected head/RQ/claim, and the smallest scientifically valid alternatives. Do not fall back to synthetic 11/80-user data.
