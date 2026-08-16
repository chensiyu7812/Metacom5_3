# Policy Manager (PM) — Paper 1 Research Repository

> `Metacom5_3` is a historical repository name. **The method name is Policy Manager (PM), not MetaCom.**

## Active Paper-1 authority

Read in this order:

1. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md` — research scope / claims
2. `project/docs/PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md` — **latest implementation / measurement / execution authority**
3. `project/data/pm_v1_5_contracts/pm_paper1_final_execution_blueprint_20260816_v1.json` — machine-readable execution contract
4. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
5. `project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md` — older subordinate training reference; where implementation details conflict, the execution blueprint wins
6. `AGENTS.md`

## Public-data-only route

Active Paper-1 data come only from prior-work public resources:

- `ESConv`: RS Strategy-RAG resource/training source;
- `ESC-Eval`: RQ1 evaluation only;
- `ES-MemEval/EvoEmo`: MP/MS/ME training/candidate source and RQ2 evaluation.

Old synthetic 80-user/11-user longitudinal assets are **deprecated and off-limits** for Paper 1. The directory

`project/data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/`

must not be read/used by active Paper-1 code or agents.

## Current route

- frozen Generator, with a Paper-1 full-stack freeze manifest still required before formal effects;
- four optional resources: `RS`, `MP`, `MS`, `ME`;
- **MP = Profile Memory only**; no MP_PREFERENCE;
- **Route A / first-order factorized PM**: formal effect contrast for one component uses a canonical background where all other optional resources are OFF;
- four L2-regularized logistic-regression heads; no direct 16-class policy;
- RQ1: ESConv -> ESC-Eval;
- RQ2: ES-MemEval/EvoEmo -> ES-MemEval;
- same-stack Fixed/Random/official baselines + real token/latency/cost logs;
- official ESC-Eval/ES-MemEval metrics provide the capability verdict.

## Feature principle

**Availability/relevance is not the ON/OFF answer.** The PM feature layer only exposes reproducible, outcome-blind descriptors of the current state and exact candidate: e.g. fixed similarity, raw type, already-visible flags, relative age, deterministic overlap/request markers and structural cost.

Do not use subjective pre-scorers such as `worth_opening`, resource helpfulness, `response_feasibility_impact`, `transferability`, `continuity_need`, `scope_specificity`, or other component bits as final head features.

## Immediate work

**Do not start formal training yet.**

1. repository-to-contract audit against the final execution blueprint;
2. Phase 0 public-only code/CI migration: disconnect synthetic active paths/tests/configs, remove MP_PREFERENCE/background bits/utility-like features, add fail-closed guards;
3. Phase 1 public-only zero-outcome coverage audit on ESConv + ES-MemEval/EvoEmo;
4. Phase 2 pre-outcome freeze: bundles/top-k/token caps, exact features, cross-fit, formal N, task-specific comparators/margins, cost threshold, Generator full-stack manifest and API plan;
5. public repeated-effect qualification;
6. final public-source matched effects + four L2 heads;
7. frozen same-stack RQ1/RQ2 + component-minus ablations.

See `project/docs/PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md` for the full phase gates, known repository conflicts, leakage rules, success criteria, and Codex handoff instructions.
