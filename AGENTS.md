# Repository Research Authority for Codex / Agents

Before making any research-design, evaluation, baseline, training-data, PM-semantics, or paper-claim change, read first:

1. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
2. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
3. `project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`

These are the active Paper-1 authority.

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
- Generator is already frozen.
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

## Evaluation authority

- RQ1 final benchmark: ESC-Eval; arms `R0 / RS Fixed-High / RS Matched-Random / Learned RS-PM`.
- RQ2 final benchmark: ES-MemEval; arms `No Memory / Full History / Official RAG Top-4 / Typed Fixed-High / Typed Matched-Random / Learned Typed-Memory PM`.
- RS stays fixed in ES-MemEval main analysis.
- Component-minus `-MP/-MS/-ME` are ablations.
- Formal claims require same-stack reruns with the frozen Generator.
- Use official ESC-Eval / ES-MemEval metrics for capability outcomes; do not create a post-hoc composite or pick only favorable metrics.
- Cost is separately logged and cannot compensate for material quality/integrity failure.

## Data / leakage authority

- Strategy Bank: ESConv train only.
- Memory training/effect/candidate source: public ES-MemEval/EvoEmo only, with outcome-isolated cross-fitting.
- Runtime PM never sees evaluation gold, outcome, reference, or future sessions.
- Same-user longitudinal adaptation is allowed only with target/fact-event cluster outcome isolation.
- No synthetic rescue for a sparse or failed head.

## Immediate implementation order

1. disconnect all synthetic 11/80-user active paths/configs/tests;
2. migrate MP to public MP_PROFILE-only and remove final background-bit features;
3. run a **public-only** zero-outcome coverage audit on ESConv + ES-MemEval/EvoEmo;
4. freeze candidate bundles, feature schema, and cross-fit plan;
5. run public-source 32-state repeated-effect qualification;
6. if it passes, freeze formal N/splits/call plan and generate final public-source effect labels;
7. train four L2 first-order heads;
8. freeze thresholds/baselines/matched-random schedules;
9. run RQ1, RQ2, and component-minus ablations.

## Drift prevention

Do not silently change the active authority to match old code.

Any proposed research change must first be written as:

`PROPOSED RESEARCH CHANGE — NOT AUTHORIZED`

and must state what clause changes, why, what prior results become invalid, what must be rerun, and whether the paper claim changes. Wait for explicit user approval.
