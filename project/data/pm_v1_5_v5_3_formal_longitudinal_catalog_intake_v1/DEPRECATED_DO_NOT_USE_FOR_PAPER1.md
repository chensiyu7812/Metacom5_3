# DEPRECATED — DO NOT USE FOR PAPER 1

This entire directory is an obsolete synthetic-data experiment from the pre-2026-08-14 phase when Paper 1 still considered building an 80-user synthetic longitudinal training corpus.

## Hard rule

**Do not read, sample, audit, repair, compile, retrieve from, train on, validate on, or cite any file in this directory for the active Paper-1 pipeline.**

This includes the tracked 11-user intake, its repair manifest, canonical users, pre-repair sources, response preferences, profile items, MS/ME items, and any derived audit counts.

The active Paper-1 training/evaluation route is public-data based:

- RS training/resource source: ESConv train-only;
- RQ1 evaluation: ESC-Eval;
- MP/MS/ME training and candidate source: the public EvoEmo histories distributed with / underlying ES-MemEval, under strict target/gold/future isolation and cross-fitting;
- RQ2 evaluation: ES-MemEval official QA / Summarization / Dialogue Generation tasks and metrics.

`MP` in Paper 1 means **Profile Memory only**. Historical `MP_PREFERENCE` assets in this directory are not part of the active ontology.

For provenance, the obsolete synthetic assets were snapshotted before deprecation on an archive branch (for example `archive/obsolete-synthetic-11user-20260816`). Their presence on `main` is historical only and must never be interpreted as active training data.

Active authority:

1. `project/docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
2. `project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
3. `project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`
