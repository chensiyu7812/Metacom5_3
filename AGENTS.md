# Repository Research Authority for Codex / Agents

Before making any research-design, evaluation, baseline, training-data, PM-semantics, or paper-claim change in this repository, read these files first:

1. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
2. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
3. `project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`

These files are the active research truth for Paper 1. The 2026-08-14 authority and older PM-v1/v1.5/v2/V3/V5, synthetic-user, EvoEmo-external, Function/Risk/Quality, and historical execution documents are evidence/history unless the 2026-08-16 authority explicitly incorporates them.

## Non-negotiable semantics

- The method name is **Policy Manager (PM)**. `MetaCom` is not the method name.
- The Generator is already frozen. Do not change Generator identity, base prompt, mode, decoding, or seed schedule after Paper-1 effect generation begins.
- PM is a selective external-resource allocator, not a direct emotional-support strategy classifier.
- `RS` means whether to inject the retrieved Strategy-RAG candidate, not which ESConv strategy category to predict.
- **`MP` means Profile Memory only in Paper 1. `MP_PREFERENCE` / `response_preference_history` are excluded.**
- `MS` means strictly-past cross-session/session-continuity memory. Current/last-message fallback is not MS.
- `ME` means strictly-past action -> user-observed-outcome experience memory.
- `MP`, `MS`, `ME`, and `RS` are four binary component gates. The 16 joint combinations remain a runtime action space, but Paper 1 does not train a direct 16-class classifier.

## Paper-1 learning route: A / first-order factorized

- Each head learns first-order state x eligible-candidate marginal utility.
- Formal ON/OFF component-effect contrasts use the canonical background: **all other optional components OFF**.
- Other-component ON/OFF bits are **not final head features**.
- Historical background-conditioned effects are interaction diagnostics/future work only.
- `ineligible` is a deterministic OFF mask and is not a learned negative example.
- Primary learner remains four standardized L2-regularized logistic-regression binary heads.
- Full-scale effect generation is blocked until repeated-effect measurement qualification passes as defined by the 2026-08-16 training contract.

## Evaluation authority

- RQ0: ESC-Eval qualified/froze the Generator before the current training stage.
- RQ1: ESConv train-only builds/teaches Strategy-RAG; final Strategy-RAG outcome is evaluated on ESC-Eval.
- RQ1 formal arms: `R0`, `RS Fixed-High`, `RS Matched-Random`, `Learned RS-PM`.
- ESConv gold strategy/Oracle is a retriever diagnostic, not the RS gate gold or main baseline.
- RQ2: ES-MemEval evaluates typed-memory allocation.
- RQ2 formal arms: `No Memory`, `Full History`, `Official RAG Top-4`, `Typed Fixed-High`, `Typed Matched-Random`, `Learned Typed-Memory PM`.
- ES-MemEval Dialogue Generation keeps RS fixed in the official main analysis.
- MP/MS/ME component-minus tests are ablations, not baselines.
- Published historical model scores are references only. Formal PM claims require same-stack reruns with the frozen Generator.
- Main capability outcomes come from official ESC-Eval / ES-MemEval metrics. Do not create a cross-task custom quality total or post-hoc select only the metric that favors PM.
- Cost remains a formal systems axis; actual token/latency/cost logs are separate and cannot compensate for material quality or integrity failure.

## Data / leakage authority

- Strategy Bank: ESConv train only.
- Paper-1 MP candidate pool: MP_PROFILE only.
- ES-MemEval runtime PM must never see evaluation gold, evaluation outcome, or future sessions.
- Same-user longitudinal adaptation is allowed, but target questions/fact-event clusters/future information must be outcome-isolated/cross-fitted.
- Old 256 effect labels are diagnostics, not final Paper-1 gold.
- Old MS effect labels are invalid for formal training because the historical treatment used last-message fallback rather than the frozen strictly-prior MS construct.
- Do not generate synthetic users or synthetic gold merely to rescue a failed or sparse component head.

## Immediate implementation order

1. migrate code to MP_PROFILE-only and remove final background-bit features;
2. run zero-outcome ES-MemEval/EvoEmo eligibility and feature-coverage audit;
3. freeze candidate-bundle top-k/token caps and final feature schema;
4. run the 32-state repeated-effect qualification;
5. only after it passes, freeze formal N/splits/call plan and generate final effect labels;
6. train four L2 first-order heads;
7. freeze thresholds, same-stack baselines, and matched-random schedules;
8. run RQ1, RQ2, and component-minus ablations.

## Drift prevention

Do not silently change any item above because an older implementation or document differs.

If you believe a research change is necessary, do not edit the authority files directly. First write a proposal titled exactly:

`PROPOSED RESEARCH CHANGE — NOT AUTHORIZED`

The proposal must state:

- what active-authority clause would change;
- why it is necessary;
- what prior results become invalid;
- what experiments must be rerun;
- whether the paper claim changes.

Wait for explicit user approval before changing the active authority.

Implementation changes that merely bring code into compliance with the active authority do not require a research redesign; record them as implementation migration/fixes.
