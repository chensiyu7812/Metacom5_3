# MetaCom V3.3 GitHub/GPT Review Package 2026-06-28

This package is for external code/science audit before GitHub publication. It contains current V3.3 code, tests, docs, internal development data/labels, PM CV checkpoints, validation selections, and audit reports.

Important boundary:
- Full judging and M2b labels are complete and attested.
- Internal development selection/CI results are included.
- Confirmatory ESConv/EvoEmo external evaluation is not complete yet.
- Do not interpret this package as final paper evidence or `CONFIRMATORY_READY`.

Recommended audit entry points:
1. `snap_reports/METACOM_V33_GITHUB_REVIEW_FIX_REPORT_20260628_ZH.md`
2. `snap_reports/METACOM_V33_PRE_GITHUB_AUDIT_20260628_ZH.md`
3. `project/docs/CLAIM_BOUNDARIES_CN.md`
4. `project/docs/RUNBOOK_CN.md`
5. `project/src/metacom_pm/training.py`, `selection.py`, `evoemo.py`, `esconv.py`, `evo_metrics.py`
6. `project/tests/`

Verification commands from `project/`:

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src python -m pytest -q
PYTHONNOUSERSITE=1 PYTHONPATH=src python scripts/99_release_preflight.py --skip-tests --out release_preflight_review.json
```
