# Repository Research Authority for Codex / Agents

Before making any research-design, evaluation, baseline, training-data, PM-semantics, or paper-claim change in this repository, read these files first:

1. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260814_ZH.md`
2. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260814_v1.json`

These two files are the active single source of research truth for Paper 1. Older PM-v1/v1.5/v2/V3/V5, synthetic-user, EvoEmo, Function/Risk/Quality, and historical execution documents are evidence/history unless the active authority explicitly incorporates them.

## Non-negotiable semantics

- The method name is **Policy Manager (PM)**. `MetaCom` is not the method name.
- PM is a selective external-resource allocator, not a direct emotional-support strategy classifier.
- `RS` means **whether to inject the retrieved Strategy-RAG candidate**, not which ESConv strategy category to predict.
- `MP`, `MS`, `ME`, and `RS` are four binary component gates. The 16 joint combinations remain a runtime action space, but Paper 1 does **not** train a direct 16-class classifier.
- Primary learner: four L2-regularized logistic-regression binary heads trained from matched ON/OFF component-effect labels.
- Step 1 decides resource ON/OFF. Step 2 only executes the already-approved exact resource. The Generator does not become a second PM.
- Current Paper-1 boundary is post-candidate-discovery, pre-injection/pre-generation. Do not claim that already-incurred retrieval cost was saved.

## Evaluation authority

- RQ0: ESC-Eval qualifies/freezes the Generator.
- RQ1: ESConv train-only builds/teaches Strategy-RAG; final Strategy-RAG outcome is evaluated on ESC-Eval.
- RQ1 formal arms: `R0`, `RS Fixed-High`, `RS Matched-Random`, `Learned RS-PM`.
- ESConv gold strategy/Oracle is a retriever diagnostic, not the RS gate gold or main baseline.
- RQ2: ES-MemEval evaluates typed-memory allocation.
- RQ2 formal arms: `No Memory`, `Full History`, `Official RAG Top-4`, `Typed Fixed-High`, `Typed Matched-Random`, `Learned Typed-Memory PM`.
- ES-MemEval Dialogue Generation keeps RS fixed in the official main analysis.
- MP/MS/ME component-minus tests are ablations, not baselines.
- Published historical model scores are references only. Formal PM claims require same-stack reruns with the frozen Generator.
- Main capability outcomes come from official ESC-Eval / ES-MemEval metrics. Legacy self-defined Quality/Function/Risk panels are diagnostics, not the paper verdict.
- Cost remains a co-primary systems axis; actual token/latency/cost logs are reported separately and cannot compensate for material quality or integrity failure.

## Data / leakage authority

- Strategy Bank: ESConv train only.
- ES-MemEval runtime PM must never see evaluation gold, evaluation outcome, or future sessions.
- Same-user longitudinal adaptation is allowed, but target questions/fact-event clusters/future information must be isolated.
- Do not generate synthetic users or synthetic gold merely to rescue a failed component head.

## Drift prevention

Do not silently change any item above because an older implementation or document differs.

If you believe a research change is necessary, do **not** edit the authority files directly. First write a proposal titled exactly:

`PROPOSED RESEARCH CHANGE — NOT AUTHORIZED`

The proposal must state:

- what active-authority clause would change;
- why it is necessary;
- what prior results become invalid;
- what experiments must be rerun;
- whether the paper claim changes.

Wait for explicit user approval before changing the active authority.

Implementation changes that merely bring code into compliance with the active authority do not require a research redesign; record them as implementation migration/fixes.
