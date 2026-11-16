# PM-RL1 网页审阅入口 2026-11-16

本次上传用于审阅本地项目的完整研究脉络与可同步证据。先读[仓库同步说明](project/docs/REPOSITORY_SYNC_20261116_ZH.md)，用[逐文件清单](project/docs/repository_sync_20261116/FILES.jsonl)核对实际上传范围；不要仅凭文件路径或方案中的步骤判定实验已经完成。

推荐阅读顺序：

1. [原始研究目标](project/docs/PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md) → [最新状态](project/docs/PM_RL1_CURRENT_STATUS.md) → [完整进度索引](project/docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md)。
2. [自然支持历史价值的负面结果](project/docs/reviews/20261105/pm_rl1_history_necessity_human_review/RESULTS_ZH.md) → [QA 与资源视图实测](project/docs/reviews/20261111/pm_rl1_typed_resources/RESULTS_ZH.md)。QA 收益不能代替自然支持帮助性收益。
3. [研究审计与路线](project/docs/reviews/20261115/pm_rl1_research_audit_and_route/REPORT_ZH.md) → [资源准备实物及尚未完成项](project/docs/reviews/20261115/pm_rl1_resource_organization_and_execution/RESULTS_ZH.md) → [MS 会后摘要设计与样例说明](project/docs/reviews/20261116/pm_rl1_session_summary_design/DESIGN_ZH.md)。
4. 对照 [Codex 主方案](project/docs/PM_RL1_MASTER_EXECUTION_PLAN_20261116_ZH.md)与 [Claude V2](project/docs/PM_RL1_EXECUTION_PLAN_V2_20261116_ZH.md)，检查其目标覆盖、动作域、可靠反馈、基线公平性、来源隔离及执行依赖。再阅读 `project/src/metacom_pm/rl1/`、`project/scripts/rl1/`、`project/tests/test_rl1_*.py` 和引用到的 Paper-1 共享模块。

**采用状态提示：**部分入口已宣告 V2 取代原方案，但 V2 本文仍待研究者确认，且[状态表](project/docs/plans/pm_rl1_v2_20261116/EXECUTION_STATE.json)记录 `plan_adopted_by_researcher=false`。这是需要审阅的现有元数据冲突；本次同步没有解决该冲突，也没有采用 V2。主方案与候选方案都应与实际代码、运行记录和结果分开判断。

已有工程训练及成本负对照，不表示自然支持正收益或完整研究已完成。下面 2026-10-22 的零训练、裁判次数和待回收状态仅是历史快照；2026-06-28 的 V3.3 部分更不是当前 PM-RL1 的结果。

## Historical review snapshot — PM-RL1, 2026-10-22

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
