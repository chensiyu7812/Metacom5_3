# Paper 1 双 Codex 并行交接边界

状态：`ACTIVE / PRE-PARALLEL HANDOFF`

两个 Codex 必须从 integration-base 分支各自建立独立 worktree，不得在旧 `work/v3-research-program-20260813` 脏工作树上开发。

## Codex A — integration / official benchmark / RQ1

独占：

- `AGENTS.md`
- `project/docs/PM_PAPER1_*AUTHORITY*` 与 reconciliation/handoff 文档
- `project/data/paper1_authority/`
- `.github/workflows/`
- `project/configs/paper1_public_only.yaml`
- `project/src/metacom_pm/paper1/core/`
- `project/src/metacom_pm/paper1/evaluation/`
- `project/src/metacom_pm/paper1/rs/`
- official ESC-Eval / ES-MemEval adapter、Cost logger、Matched-Random control、RQ1 runner

## Codex B — public candidate / policy / memory / RQ2

独占：

- `project/src/metacom_pm/paper1/data/`
- `project/src/metacom_pm/paper1/candidates/`
- `project/src/metacom_pm/paper1/features/`
- `project/src/metacom_pm/paper1/splits/`
- `project/src/metacom_pm/paper1/learning/`
- `project/src/metacom_pm/paper1/memory/`
- public-only zero-outcome census、MP/MS/ME compiler、exact-evidence OOF、soft-target L2、RQ2/component-minus

## 共享边界

- `project/src/metacom_pm/paper1/contracts.py` 由 Codex A 冻结；Codex B 只消费，修改需先发接口提案。
- Codex A 是唯一 integrator；Codex B 提交小型、可 cherry-pick commits。
- 两边都不得修改旧 V1.5 ontology 来“兼容”新 pipeline；新 active code 只在 `paper1/` namespace。
- 正式 API/outcome 在 `outcome_lock` 解锁前禁止。
- 两边都不得加入经验性 PASS gate、CostWorthIt label、MP_PREFERENCE、background component bits 或 synthetic rescue。

## 合并检查点

1. `M0`：authority + RQ0/data identity + shared contracts；
2. `M1`：official adapters 与 zero-outcome census；
3. `M2`：一次性 pre-outcome freeze；
4. `M3`：RS 与 memory effect construction；
5. `M4`：RQ1/RQ2 official evaluation 与 final reporting。

任何跨 lane 依赖必须通过已提交的 schema/manifest，不通过复制未提交文件或口头约定传递。
