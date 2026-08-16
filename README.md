# Policy Manager (PM) — Paper 1 Research Repository

> `Metacom5_3` is a historical repository name. **The method name is Policy Manager (PM), not MetaCom.**

## Active Paper-1 authority

1. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
2. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
3. `project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`
4. `AGENTS.md`

## Public-data-only route

Active Paper-1 data come only from prior-work public resources:

- `ESConv`: RS Strategy-RAG resource/training source;
- `ESC-Eval`: RQ1 evaluation only;
- `ES-MemEval/EvoEmo`: MP/MS/ME training/candidate source and RQ2 evaluation.

Old synthetic 80-user/11-user longitudinal assets are **deprecated and off-limits** for Paper 1. The directory

`project/data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/`

contains an explicit deprecation marker and must not be read/used by active Paper-1 code or agents.

## Current route

- frozen Generator;
- four optional resources: `RS`, `MP`, `MS`, `ME`;
- **MP = Profile Memory only**; no MP_PREFERENCE;
- **Route A / first-order factorized PM**: formal effect contrast for one component uses a canonical background where all other optional resources are OFF;
- four L2-regularized logistic-regression heads; no direct 16-class policy;
- RQ1: ESConv -> ESC-Eval;
- RQ2: ES-MemEval/EvoEmo -> ES-MemEval;
- same-stack Fixed/Random/official baselines + real token/latency/cost logs;
- official ESC-Eval/ES-MemEval metrics provide the capability verdict.

## Immediate work

1. disconnect all obsolete synthetic paths/configs/tests;
2. migrate MP to public Profile-only and remove final background-bit features;
3. run a public-only zero-outcome coverage audit on ESConv + ES-MemEval/EvoEmo;
4. freeze candidate bundles/features/cross-fit;
5. run public repeated-effect qualification;
6. generate final public-source matched effects and train four heads;
7. run frozen same-stack RQ1/RQ2 and component-minus ablations.
