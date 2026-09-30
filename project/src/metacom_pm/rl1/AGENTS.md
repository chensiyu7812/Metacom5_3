# PM-RL1 scoped implementation

Read `project/docs/PM_RL1_SCOPED_IMPLEMENTATION_20260928_ZH.md` and the user-supplied
`/home/tokkio/PM_RL1_单轮资源选择与执行_环境及训练实施方案_20260928.md` for this namespace.
The user authorized this successor direction and engineering on 2026-09-28;
do not re-request approval for dynamics/Step-2 solely because old Paper-1
contracts placed those topics in future work. Preserve all old result identities.

Runtime actors and critics receive only Observation, never EpisodeSpec, private
inventories, receipts or snapshots. GET never calls G/J. Missing measurement is
pending, never reward zero. All paid execution remains within the inherited
shared budget and requires its atomic integration; local-only work has no paid
provider fallback. Document partial milestones honestly.
