# Policy Manager (PM) — PM-RL1 and Paper-1 Research Repository

> `Metacom5_3` is a historical repository name. **The method name is Policy Manager (PM), not MetaCom.**

**最新研究入口（2026-10-02）：[PM-RL1 全部进展、结果与数据诊断](project/docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md) · [本阶段发布说明](project/docs/PM_RL1_STAGE_PUBLICATION_20261002_ZH.md)。**

PM-RL1 is the authorized successor: one conversational turn, at most four resource acquisitions, then one executor reply. P1 source/role representation and P2 weak-supervision executor development are complete with disclosed limitations: 493 training/development targets, one three-epoch LoRA run, and 639 naturally completed comparison replies. P3 has completed 32 initial development scores plus one full-source recheck probe and prepared a fixed 40-pair human calibration instrument. **Human calibration and reward qualification remain pending; no natural-support PPO result or support-quality improvement is claimed.**

- [Feasible completion plan](project/docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md) · [capability backward design](project/docs/PM_RL1_CAPABILITY_BACKWARD_DESIGN_20261001_ZH.md) · [runbook](project/docs/pm_rl1_completion_20260930_v2/runbook.md)
- [P1 representation results](project/docs/PM_RL1_P1_REPRESENTATION_RESULTS_20261001_ZH.md) · [P2 executor results and limitations](project/docs/PM_RL1_P2_EXECUTOR_RESULTS_20261001_ZH.md) · [P3 measurements and costs](project/docs/pm_rl1_completion_20260930_v2/p3_development_results.json)
- [October 2 results manifest](project/docs/reviews/20261002/pm_rl1/MANIFEST.json) · [public overview notebook](project/docs/reviews/20261002/pm_rl1/stage_results.ipynb)

Earlier stages and the first publication:

- [Original PM-RL1 plan](project/docs/PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md) · [scoped implementation](project/docs/PM_RL1_SCOPED_IMPLEMENTATION_20260928_ZH.md)
- [Executor training results](project/docs/PM_RL1_COVERAGE_TRAINING_RESULTS_20260930_ZH.md) · [R04B judge results](project/docs/PM_RL1_R04B_CANDIDATE_RESULTS_20260930_ZH.md)
- [Dataset diagnosis and next steps](project/docs/PM_RL1_DATASET_DIAGNOSTICS_AND_RESEARCH_PATH_20260930_ZH.md) · [portable notebook](project/docs/reviews/20260930/pm_rl1/dataset_diagnostics_20260930_v1/dataset_diagnostics.ipynb)
- [Published results manifest](project/docs/reviews/20260930/pm_rl1/MANIFEST.json) · [CI failure diagnosis](project/docs/PM_RL1_PUBLICATION_AND_CI_20260930_ZH.md)

## Run the current CPU checks

```bash
cd project
python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.3.1+cpu"
python -m pip install -e ".[dev]"
pytest -q -m "not gpu" tests/test_paper1_*.py tests/test_rl1_*.py
python scripts/paper1/00_validate_integration_base.py
```

These checks need no local `outputs/`, GPU, model weights or provider credentials. Research runs still require their versioned local models and run artifacts; provenance paths in historical reports are not installation dependencies. The repository also contains retired experiments: running every historical test is not the active public-data-only CI contract.

## Preserved Paper-1 scope

The remainder of this page documents the earlier Paper-1 route. Its result identities and outcome locks remain intact; PM-RL1's scoped successor authorization governs the new `rl1` namespace. Earlier local judge development and calibration are recorded in the [September 17 review](project/docs/PM_PAPER1_WEB_REVIEW_20260917_ZH.md).

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
