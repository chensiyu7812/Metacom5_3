# Policy Manager (PM) — Paper 1 Research Repository

> `Metacom5_3` is a historical repository name. **The method name is Policy Manager (PM), not MetaCom.**

**Latest review package (2026-09-17):** [中文版审阅入口：人评复核、Gemini 资格结果、修复与候选提案](project/docs/PM_PAPER1_WEB_REVIEW_20260917_ZH.md). Gemini qualification is complete; the candidate was not promoted. New local judges remain proposals, and all outcome locks remain closed.

## Active Paper-1 authority

Read in this order:

1. `AGENTS.md` — complete authority order and scoped precedence of later amendments
2. `project/configs/paper1_public_only.yaml` — active artifact pointers and outcome locks
3. `project/docs/PM_PAPER1_EXECUTION_CHECKLIST_20260903_ZH.md` — current progress and dependencies
4. `project/docs/PM_PAPER1_HUMAN_REFERENCE_V2_AMENDMENT_20260908_ZH.md` — current human/teacher evidence amendment
5. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md` — research scope / claims, subject to scoped amendments in `AGENTS.md`
6. `project/docs/PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md` — base execution blueprint, subject to those later amendments

The active Pre-Effect, Latency V2, Effect V2, Multi-View and teacher contracts are linked by the config. Historical qualification PASS gates do not govern current progression.

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
- **MP = target-time Current Profile View; ME = strict-past Atomic Event/Experience Timeline; MS = complete strict-past raw Session transcript**;
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

1. Preserve the completed joint-human A review, exploratory AI B and six-case followup; use the September 17 closeout rather than restarting human review.
2. Gemini qualification completed 96 presentations / 100 physical calls, with 92 valid verdicts and USD 0.0654614 conservatively accounted. The candidate was not promoted; review task applicability and any explicitly authorized alternative candidates before adopting a teacher.
3. Under the appropriate calibration locks, calibrate RS/MP/ME/MS amount/top-k and capacity; the teacher sample's `k ∈ {1,2,4}` is only a coverage probe.
4. Freeze final amounts/caps, exact features and leakage-safe folds, Generator/Step2 stack, operating-point protocol, seeds and API call manifests before formal effect labels and PM training.
5. Run frozen same-stack RQ1/RQ2, component-minus ablations and the separately specified natural-turn audit.

V2 preserves the existing 80 base pairs, 16 reversals and 142 generated replies. DG now includes complete past history, shared byte-for-byte with the future teacher; generating V2 made no new model calls. See `project/docs/PM_PAPER1_HUMAN_REFERENCE_V2_HANDOFF_20260908_ZH.md` for offline forms and submission instructions.
