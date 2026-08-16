# Repository Research Authority for Codex / Agents

Before making any research-design, evaluation, baseline, training-data, PM-semantics, feature, measurement, CI, or Paper-1 execution change, read first:

1. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
2. `project/docs/PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md`
3. `project/data/pm_v1_5_contracts/pm_paper1_final_execution_blueprint_20260816_v1.json`
4. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
5. `project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`

These are the active Paper-1 authorities.

## Authority precedence

- **Research scope / claims** are governed by `PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`.
- **Implementation-level feature schema, measurement rules, leakage controls, CI migration, freeze items, and execution order** are governed by the newer `PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md` and its machine-readable contract.
- If the older training contract or V5.3 code conflicts with the execution blueprint, **do not change the research design to match old code**. Report the conflict and migrate the implementation.
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
- `RS`: inject-or-not the retrieved Strategy-RAG candidate; not strategy-category prediction.
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
- Full-scale effect generation is blocked until the public-source repeated-effect qualification passes.

## Feature rule — outcome-blind raw observables only

The feature layer may describe the current state and exact eligible candidate, but it must not estimate resource utility before the PM.

Allowed examples: fixed similarity, raw candidate/profile type, already-visible/redundancy flags, relative age, deterministic entity/thread overlap, explicit current-turn request markers, structural token cost.

Forbidden examples: `worth_opening`, subjective `helpfulness`, subjective `response_feasibility_impact`, subjective `transferability`, subjective `continuity_need`, subjective `scope_specificity`, response/judge/gold/future fields, preference metadata, other-component bits.

The active feature schema is defined in `PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md`.

## Evaluation authority

- RQ1 final benchmark: ESC-Eval; arms `R0 / RS Fixed-High / RS Matched-Random / Learned RS-PM`.
- Because the Strategy Bank is ESConv-derived, the primary RQ1 transfer analysis uses non-ESConv-source English role cards; the full frozen English set is secondary and ESConv-derived cards are an overlap sensitivity slice.
- RQ2 final benchmark: ES-MemEval; arms `No Memory / Full History / Official RAG Top-4 / Typed Fixed-High / Typed Matched-Random / Learned Typed-Memory PM`.
- RS stays fixed in ES-MemEval main analysis.
- Component-minus `-MP/-MS/-ME` are ablations.
- Formal claims require same-stack reruns with the frozen Generator.
- Use official ESC-Eval / ES-MemEval metrics for capability outcomes; do not create a post-hoc composite or pick only favorable metrics.
- Cost is separately logged and cannot compensate for material quality/integrity failure.

## Data / leakage authority

- Strategy Bank: ESConv train only.
- Formal RS effect construction must use leave-current-dialogue-out / fold-exclusive Strategy Bank retrieval.
- Memory training/effect/candidate source: public ES-MemEval/EvoEmo only, with outcome-isolated cross-fitting.
- Runtime PM never sees evaluation gold, outcome, reference, or future sessions.
- Same-user longitudinal adaptation is allowed only with target/fact-event cluster outcome isolation.
- No synthetic rescue for a sparse or failed head.

## Immediate implementation order

Do not start formal PM training first.

1. **Repository-to-contract audit** against the execution blueprint.
2. Phase 0: disconnect obsolete synthetic active paths/configs/tests; remove MP_PREFERENCE/background-bit/utility-like active features; add fail-closed CI guards; establish a public-only Paper-1 config.
3. Phase 1: run a **public-only zero-outcome coverage audit** on ESConv + ES-MemEval/EvoEmo.
4. Phase 2: before any formal effect outcome is opened, freeze candidate bundles/top-k/token caps, exact feature schema, cross-fit, formal N, task-specific comparators/margins, cost threshold, Generator full-stack manifest, qualification sample, reviewer overlap and API call plan.
5. Phase 3: run public-source 32-state repeated-effect qualification.
6. If it passes, generate final public-source effect labels and train four L2 heads.
7. Freeze thresholds/baselines/matched-random schedules.
8. Run RQ1, RQ2, and component-minus ablations.

## Drift prevention

Do not silently change the active authority to match old code.

Any proposed change to frozen research scope must first be written as:

`PROPOSED RESEARCH CHANGE — NOT AUTHORIZED`

and must state what clause changes, why, what prior results become invalid, what must be rerun, and whether the paper claim changes. Wait for explicit user approval.

Any implementation limitation that prevents the active public-data-only plan must be written as:

`IMPLEMENTATION BLOCKER — RESEARCHER DECISION REQUIRED`

with the missing public evidence, affected head/RQ/claim, and the smallest scientifically valid alternatives. Do not fall back to synthetic 11/80-user data.
