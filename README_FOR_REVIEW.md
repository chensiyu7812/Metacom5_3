# Current review entry — PM-RL1, 2026-10-22

Start with the [research review](project/docs/pm_rl1_workspace_20261022/RESEARCH_REVIEW_ZH.md),
[current status](project/docs/PM_RL1_CURRENT_STATUS.md), and
[controlling plan](project/docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md).
P1/P2 are complete with disclosed limitations. Human development references have
been received, but reward qualification remains unresolved. There are 308 cumulative
attempts: 307 judge/audit attempts and one rejected Claude configuration request.
Claude is deferred. Qualified BC checkpoints and natural-task RL updates remain
zero. BC/OneShot/NoText coordination and source-bound replay of 586 historical
generations have engineering checks; eight new blinded development pairs and six
regression cases have been delivered for human review, with no new answers returned.
Formal policy comparisons and independent final evaluation are incomplete.
See the [version review](project/docs/reviews/20261022/pm_rl1/VERSION_REVIEW_ZH.md)
for local and clean-checkout verification and reproducibility limitations.
The [publication validation](project/docs/reviews/20261022/pm_rl1_publication/VALIDATION.json)
uses a fresh Python 3.11 environment with CPU PyTorch and declared dependencies:
1,429 passed, 131 skipped, exit code 0; all 32 integration checks passed.
Skipped private-engine/input, optional BGE and frozen-tokenizer checks are not
verified integrations. The missing `jsonschema` runtime dependency is now declared.

The historical [2026-10-02 publication](project/docs/PM_RL1_STAGE_PUBLICATION_20261002_ZH.md)
and its public
[results notebook](project/docs/reviews/20261002/pm_rl1/stage_results.ipynb)
check that snapshot's hashes and arithmetic; they do not describe today's
measurement status. The [repository README](README.md) gives the CPU test command.

Everything below is the preserved **2026-06-28 historical V3.3 package**. Its
training claims, review instructions and all-tests commands are not the current
PM-RL1 state or active CI contract.

---

# Historical MetaCom V3.3 GitHub/GPT Review Package 2026-06-28

> **Current PM-v1.5 review:** start with
> [`README_PM_V1_5_REVIEW_ZH.md`](README_PM_V1_5_REVIEW_ZH.md). The historical
> `pm-v1.5-supplemental` label meant a no-retraining PM-v1 diagnostic; the
> current conference-track PM-v1.5 is a separate retrained fast-track design.
> Do not mix their claims or results.

This package is for external code/science audit before final ESConv/EvoEmo evaluation. It contains current V3.3 code, tests, docs, internal development data/labels, PM CV checkpoints, validation selections, confirmatory-ready ESConv/EvoEmo inputs, generated ESConv action outcomes, fixed EvoEmo seeker tracks, and audit reports.

Important boundary:
- Full judging and M2b labels are complete and attested.
- Internal development selection/CI results are included.
- ESConv response generation and GPT-4o final pairwise judging are complete for the strategy-only comparison (`M0+RS` vs `M0+R0`).
- EvoEmo fixed seeker tracks are complete, but EvoEmo policy generation / final judging has not been run yet.
- Raw API call logs are intentionally excluded. `project/outputs/esconv_sweep/artifact_attestation.json` is regenerated as a package-local attestation so the GitHub package can be verified after relocation; it binds the same action outcome hashes and marks raw calls as excluded.
- Do not interpret this package as final paper evidence or `CONFIRMATORY_READY`.

Recommended audit entry points:
0. `snap_reports/METACOM_V33_EXTERNAL_EVALUATION_PLAN_FOR_GPT55_ZH.md`
0b. `snap_reports/METACOM_V33_ESCONV_STRATEGY_EVAL_RESULT_ZH.md`
1. `snap_reports/METACOM_V33_GITHUB_REVIEW_FIX_REPORT_20260628_ZH.md`
2. `snap_reports/METACOM_V33_PRE_GITHUB_AUDIT_20260628_ZH.md`
3. `project/docs/CLAIM_BOUNDARIES_CN.md`
4. `project/docs/RUNBOOK_CN.md`
5. `project/scripts/14a_eval_esconv_strategy_only.py`
6. `project/src/metacom_pm/training.py`, `selection.py`, `evoemo.py`, `esconv.py`, `evo_metrics.py`
7. `project/tests/`

Verification commands from `project/`:

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src python -m pytest -q
PYTHONNOUSERSITE=1 PYTHONPATH=src python scripts/99_release_preflight.py --skip-tests --out release_preflight_review.json
PYTHONNOUSERSITE=1 PYTHONPATH=src python scripts/14a_eval_esconv_strategy_only.py --dry-run --overwrite
```
