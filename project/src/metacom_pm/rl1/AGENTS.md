# PM-RL1 scoped implementation

Start with `project/docs/PM_RL1_SOLUTION_PLAN_V3_20261116_ZH.md` and
`project/docs/plans/pm_rl1_v3_20261116/EXECUTION_STATE.json` for current work
(the document's content version is **V3.1**, despite its stable V3 filename;
PR #4 must be researcher-merged before adoption; thereafter its 30-task JSON DAG
supersedes the V2/11-16 work-package ordering. New code goes to `rl1v3/`;
this package remains reusable baseline code).
The user requested the new session-summary candidate; preserve MS-RAW history
and give MS-SUM separate source, representation, renderer and result identities.
Read `project/docs/PM_RL1_SCOPED_IMPLEMENTATION_20260928_ZH.md` and the user-supplied
`project/docs/PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md` for this namespace
(the byte-identical copy of the user-supplied local plan). Current progress is
indexed in `project/docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md`.
The user authorized this successor direction and engineering on 2026-09-28;
do not re-request approval for dynamics/Step-2 solely because old Paper-1
contracts placed those topics in future work. Preserve all old result identities.

Runtime actors and critics receive only Observation, never EpisodeSpec, private
inventories, receipts or snapshots. GET never calls G/J. Missing measurement is
pending, never reward zero. All paid execution remains within the inherited
shared budget and requires its atomic integration; local-only work has no paid
provider fallback. Document partial milestones honestly.
