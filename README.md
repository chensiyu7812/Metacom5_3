# Policy Manager (PM) — Paper 1 Research Repository

> `Metacom5_3` is a historical repository name. **The method name is Policy Manager (PM), not MetaCom.**

## Active Paper-1 authority

Read these files first:

1. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
2. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
3. `project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`
4. `AGENTS.md`

The 2026-08-16 authority supersedes the 2026-08-14 research freeze and all older PM-v1/v1.5/v2/V3/V5 execution plans when they conflict.

## Current Paper-1 route

- frozen Generator;
- four optional resources: `RS`, `MP`, `MS`, `ME`;
- **MP = Profile Memory only**; `MP_PREFERENCE` is excluded from Paper 1;
- **Route A / first-order factorized PM**: each component is trained under the canonical background where the other optional resources are OFF;
- four L2-regularized logistic-regression heads; no direct 16-class policy;
- RQ1: ESConv train-only -> Strategy-RAG training -> ESC-Eval final evaluation;
- RQ2: ES-MemEval/EvoEmo strict-past memory -> ES-MemEval QA/Summary/DG final evaluation;
- same-stack Fixed/Random/official baselines and real token/latency/cost reporting;
- legacy Quality/Function/Risk panels are diagnostics, not the Paper-1 verdict.

## Immediate work

The research question is no longer being redesigned. The current work is implementation/training migration:

1. remove preference data and background-bit features from the Paper-1 learner;
2. audit natural MP/MS/ME coverage in ES-MemEval/EvoEmo;
3. freeze source-specific candidate bundles and outcome-blind features;
4. run repeated matched-effect qualification;
5. generate final matched ON/OFF effect data and train the four first-order heads;
6. run the frozen same-stack RQ1/RQ2 experiments and component-minus ablations.

Older review/snapshot files remain in the repository for provenance only.
